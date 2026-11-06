#!/usr/bin/env python3
"""SDK struct/enum/union types + global declarations -> re/jxc-4k/sdk_types.tsv (consumed by re/ghidra/ApplySdkTypes.java).

usage: ghidra_sdk_types.py [--no-pp]
Source: every C file of STD_FW_1P.Uv2 (target RL6449_Project) preprocessed with `sdcc -E` (same flags as the port build),
types/globals unioned by name from tmp/sdcc-port/src headers (read only). Preprocessed text cached in ./tmp/ghidra_types/.
Layout model = Keil C51 (what the vendor firmware was built with): big-endian, char 1, int/short 2, long/float 4,
enum = 1 byte if all values < 256 else 2 (else 4), no padding, pointers by memory space (xdata/code 2, data/idata/pdata 1,
generic 3). Bit fields: consecutive same-type fields packed into units of the base type, emitted as ONE plain member
`bf_<first>` (comment lists the fields in declaration order; bit order not verified against the vendor build).
Config caveat: struct bodies depend on #if of OUR port config; the vendor build can differ (sizes are checked in Ghidra only
where the global's address map agrees, see docs/re-full-reversal.md).
Outputs: re/jxc-4k/sdk_types.tsv, ./tmp/ghidra_types/sdk_globals.tsv (name, space, type, size, module), log ./tmp/logs/ghidra_sdk_types.log
sdk_types.tsv format (tab separated):
  E name size  NAME=val,NAME=val,...
  S name size / U name size, then  F offset fieldname typeref dim comment   (dim = array count, 1 if scalar)
  typeref = u8 s8 u16 s16 u32 s32 f32 ptr1 ptr2 ptr3 or another type name; blank line ends a type
"""
import os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("AWTO_DDC_REPO") or HERE.parent)
sys.path.insert(0, str(HERE))
import keil2sdcc as K  # noqa: E402

TMP = ROOT / "tmp" / "ghidra_types"
LOG = ROOT / "tmp" / "logs" / "ghidra_sdk_types.log"
OUT = ROOT / "re" / "jxc-4k" / "sdk_types.tsv"
GLOBALS = TMP / "sdk_globals.tsv"
SRCMARK = str(K.SRC)

PRIM = {"unsigned char": ("u8", 1), "char": ("s8", 1), "signed char": ("s8", 1), "unsigned short": ("u16", 2),
        "short": ("s16", 2), "unsigned int": ("u16", 2), "int": ("s16", 2), "signed int": ("s16", 2),
        "unsigned long": ("u32", 4), "long": ("s32", 4), "float": ("f32", 4), "void": ("u8", 1),
        "unsigned": ("u16", 2), "signed": ("s16", 2), "bit": ("bit", 0)}
QUAL = re.compile(r"\b(volatile|const|register|static|extern|__reentrant|__critical|__near|__far|__nonbanked|__banked|restrict)\b")
SPACE = re.compile(r"\b__(xdata|data|idata|pdata|code|bit|sfr|sbit)\b")


def log(m):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(m + "\n")
    print(m)


def preprocess(use_cache):
    uv2 = K.SRC / "STD_FW_1P.Uv2"
    files, defines, incs, model = K.parse_uv2(uv2, "RL6449_Project")
    cs = [(uv2.parent / f).resolve() for f in files if f.lower().endswith(".c")]
    TMP.mkdir(parents=True, exist_ok=True)

    def one(c):
        out = TMP / (c.stem + ".i")
        if use_cache and out.exists():
            return out
        r = subprocess.run(K.sdcc_cmd(c, uv2.parent, defines, incs, model) + ["-E", str(c)],
                           capture_output=True, text=True, errors="replace", timeout=120)
        out.write_text(r.stdout)
        return out
    with ThreadPoolExecutor(os.cpu_count() or 4) as ex:
        return list(ex.map(one, [c for c in cs if c.exists()]))


def strip_text(path):
    """Preprocessed text without #line markers; statements from system headers dropped."""
    out, keep = [], True
    for ln in path.read_text(errors="replace").splitlines():
        if ln.startswith("#line"):
            m = re.match(r'#line \d+ "([^"]*)"', ln)
            keep = bool(m) and (m.group(1).startswith(SRCMARK) or m.group(1).endswith("keil_compat.h"))
            continue
        if keep:
            out.append(ln)
    return "\n".join(out)


def statements(text):
    """Top-level statements: (kind, text, body) where kind in 'decl' (ended by ;) or 'func'."""
    i, n, buf = 0, len(text), []
    res = []
    while i < n:
        c = text[i]
        if c == "{":
            head = "".join(buf)
            depth, j = 1, i + 1
            while j < n and depth:
                depth += (text[j] == "{") - (text[j] == "}")
                j += 1
            body = text[i + 1:j - 1]
            is_type = re.search(r"\b(struct|union|enum)\b", head) and "(" not in head.split("=")[0]
            is_init = "=" in head or head.rstrip().endswith("]")
            if is_type or is_init:
                k = j
                while k < n and text[k] != ";":
                    k += 1
                tail = text[j:k]
                res.append(("type" if is_type and "=" not in head else "init", head, body, tail))
                i, buf = k + 1, []
            else:
                i, buf = j, []                      # function body
            continue
        if c == ";":
            res.append(("decl", "".join(buf), "", ""))
            buf = []
        else:
            buf.append(c)
        i += 1
    return res


class Types:
    def __init__(self):
        self.td = {}           # typedef name -> ("prim", ref, size) | ("agg", name)
        self.agg = {}          # name -> dict(kind, fields, size) / enum
        self.order = []
        self.anon = 0

    def resolve(self, base):
        base = " ".join(base.split())
        if base in PRIM:
            r, s = PRIM[base]
            return ("prim", r, s)
        if base in self.td:
            return self.td[base]
        m = re.match(r"(struct|union|enum) (\w+)$", base)
        if m and m.group(2) in self.agg:
            return ("agg", m.group(2))
        if base in self.agg:
            return ("agg", base)
        return None

    def size(self, t):
        if t[0] == "prim":
            return t[2]
        return self.agg[t[1]]["size"]

    def ref(self, t):
        return t[1]

    def parse_decl(self, text):
        """'<type words> [*] name[dims]' -> (basetype or None, ptrsize or None, name, dims, bits)"""
        text = text.strip()
        bits = None
        m = re.search(r":\s*(\d+)\s*$", text)
        if m:
            bits, text = int(m.group(1)), text[:m.start()].strip()
        sp = SPACE.findall(text)
        text = SPACE.sub(" ", QUAL.sub(" ", text))
        try:
            dims = [int(re.sub(r"[uUlL]+$", "", x.strip()), 0) if x.strip() else 0 for x in re.findall(r"\[([^\]]*)\]", text)]
        except ValueError:
            return None                                   # non-constant dim (compile-time assert typedefs)
        text = re.sub(r"\[[^\]]*\]", " ", text)
        fp = re.search(r"\(\s*\*\s*(\w+)\s*\)\s*\(", text)
        if fp:
            return ("fnptr", 2, fp.group(1), dims, None, sp)
        stars = text.count("*")
        words = re.sub(r"\s+", " ", text.replace("*", " ")).split()
        name = words[-1]
        base = " ".join(words[:-1])
        return (base, stars, name, dims, bits, sp)

    def ptr_size(self, sp):
        if "code" in sp or "xdata" in sp:
            return 2
        if "data" in sp or "idata" in sp or "pdata" in sp:
            return 1
        return 3

    def add_typedef(self, text, body="", tail=""):
        text = " ".join(text.split())
        m = re.match(r"typedef (struct|union|enum)\s*(\w*)\s*$", text)
        if m and body is not None and tail is not None and (body or m.group(1)):
            kind, tag = m.group(1), m.group(2)
            names = [x.strip() for x in tail.split(",") if x.strip()]
            nm = names[0] if names else tag
            if not nm:
                return
            self.define(kind, nm, body)
            for other in names[1:]:
                self.td[other] = ("agg", nm)
            if tag and tag != nm:
                self.td.setdefault(tag, ("agg", nm))
            return
        m = re.match(r"typedef (.*)$", text)
        if m:
            d = self.parse_decl(m.group(1))
            if not d:
                return
            base, stars, name, dims, bits, sp = d
            if base == "fnptr":
                self.td[name] = ("prim", "ptr2", 2); return
            if stars:
                self.td[name] = ("prim", f"ptr{self.ptr_size(sp)}", self.ptr_size(sp)); return
            t = self.resolve(base)
            if t and not dims:
                self.td[name] = t

    def define(self, kind, name, body):
        if name in self.agg:
            return
        if kind == "enum":
            vals, cur = [], 0
            for item in body.split(","):
                item = item.strip()
                if not item:
                    continue
                if "=" in item:
                    k, v = [x.strip() for x in item.split("=", 1)]
                    try:
                        cur = int(re.sub(r"[uUlL]+$", "", v), 0)
                    except ValueError:
                        mm = re.fullmatch(r"\(?(-?\d+)\)?", v)
                        cur = int(mm.group(1)) if mm else cur
                else:
                    k = item
                vals.append((k, cur)); cur += 1
            mx = max([v for _, v in vals] + [0]); mn = min([v for _, v in vals] + [0])
            size = 1 if mx < 256 and mn >= 0 else 2 if mx < 65536 and mn > -32768 else 4
            self.agg[name] = dict(kind="E", size=size, vals=vals)
            self.order.append(name)
            return
        fields, size = self.layout(kind, body)
        if fields is None:
            return
        self.agg[name] = dict(kind="S" if kind == "struct" else "U", size=size, fields=fields)
        self.order.append(name)

    def split_members(self, body):
        out, depth, buf = [], 0, []
        for c in body:
            if c == "{":
                depth += 1
            if c == "}":
                depth -= 1
            if c == ";" and depth == 0:
                out.append("".join(buf)); buf = []
            else:
                buf.append(c)
        return out

    def layout(self, kind, body):
        fields, off, unit, maxsize = [], 0, None, 0

        def flush():
            nonlocal off, unit
            if unit:
                ref = {1: "u8", 2: "u16", 4: "u32"}[unit["size"]]
                fields.append((unit["start"], "bf_" + unit["names"][0].split(":")[0], ref, 1, "bit fields (decl order, " + str(unit["cap"]) + " bits): " + ", ".join(unit["names"])))
                unit = None

        for st in self.split_members(body):
            st = " ".join(st.split())
            if not st:
                continue
            nested = re.match(r"^(struct|union)\s*(\w*)\s*\{(.*)\}\s*(.*)$", st)
            if nested:
                flush()
                nk, nt, nb, rest = nested.groups()
                sub, ssz = self.layout(nk, nb)
                if sub is None:
                    return None, 0
                self.anon += 1
                tname = nt or f"_anon{self.anon}"
                self.agg[tname + "_t"] = dict(kind="S" if nk == "struct" else "U", size=ssz, fields=sub)
                self.order.append(tname + "_t")
                m = re.match(r"^(\w+)\s*((?:\[[^\]]*\])*)$", rest)
                if not m:
                    continue
                dims = [int(x, 0) for x in re.findall(r"\[(\w+)\]", m.group(2))]
                cnt = 1
                for d in dims:
                    cnt *= d
                fields.append((off if kind == "struct" else 0, m.group(1), tname + "_t", cnt, ""))
                if kind == "struct":
                    off += ssz * cnt
                else:
                    maxsize = max(maxsize, ssz * cnt)
                continue
            for d in self.multi_decl(st):
                if d is None:
                    return None, 0
                base, stars, name, dims, bits, sp = d
                if base == "fnptr":
                    t, sz, ref = None, 2, "ptr2"
                elif stars:
                    sz = self.ptr_size(sp); ref = f"ptr{sz}"
                else:
                    t = self.resolve(base)
                    if t is None:
                        log(f"  unresolved type '{base}' in {name}")
                        return None, 0
                    sz, ref = (self.size(t), t[1]) if True else (0, "")
                    if t[0] == "prim" and t[1] == "bit":
                        bits = bits or 1
                if bits is not None and not dims:
                    usz = sz if sz in (1, 2, 4) else 1
                    if unit is None or unit["size"] != usz or unit["used"] + bits > unit["cap"]:
                        flush()
                        unit = dict(start=off, size=usz, cap=8 * usz, used=0, names=[])
                        off += usz
                    unit["used"] += bits; unit["names"].append(f"{name}:{bits}")
                    continue
                flush()
                cnt = 1
                for dd in dims:
                    cnt *= dd
                fields.append((off if kind == "struct" else 0, name, ref, cnt, ""))
                if kind == "struct":
                    off += sz * cnt
                else:
                    maxsize = max(maxsize, sz * cnt)
        flush()
        return fields, (off if kind == "struct" else maxsize)

    def multi_decl(self, st):
        """'BYTE a, b[2]' -> list of parse_decl tuples sharing the base type."""
        parts = st.split(",")
        first = self.parse_decl(parts[0])
        if first is None:
            return [None]
        res = [first]
        base = first[0]
        for p in parts[1:]:
            d = self.parse_decl(f"{base} {p}")
            res.append(d)
        return res


def main():
    a = sys.argv[1:]
    LOG.write_text("")
    files = preprocess("--no-pp" in a)
    T = Types()
    texts = [strip_text(f) for f in files]
    stmts = []
    for t in texts:
        stmts.append(statements(t))
    # pass 1: typedefs/aggregates in encounter order, repeated until fixed point (dependencies across files)
    for _ in range(3):
        for ss in stmts:
            for kind, head, body, tail in ss:
                head = " ".join(head.split())
                if kind == "type" and head.startswith("typedef"):
                    T.add_typedef(head, body, tail)
                elif kind == "type" and re.match(r"^(struct|union|enum) \w+$", head):
                    T.define(head.split()[0], head.split()[1], body)
                elif kind == "decl" and head.startswith("typedef"):
                    T.add_typedef(head)
    # globals: `extern` declarations and definitions at top level
    glob = {}
    for f, ss in zip(files, stmts):
        for kind, head, body, tail in ss:
            head = " ".join(head.split())
            if kind not in ("decl", "init") or head.startswith("typedef") or "(" in head.split("=")[0].replace("(*", "") and "(*" not in head:
                continue
            if kind == "init":
                head = head.split("=")[0]
            d = T.parse_decl(head.split("=")[0]) if head else None
            if not d:
                continue
            base, stars, name, dims, bits, sp = d
            if not re.match(r"^(g_|pData|_?[A-Za-z]\w*)$", name) or "bit" in sp or "sfr" in sp or "code" in sp:
                continue
            if base == "fnptr" or not base:
                continue
            t = T.resolve(base)
            if stars:
                ref, sz = f"ptr{T.ptr_size(sp)}", T.ptr_size(sp)
            elif t:
                ref, sz = T.ref(t), T.size(t)
            else:
                continue
            if ref == "bit":
                continue
            cnt = 1
            for dd in dims:
                cnt *= dd
            space = sp[0] if sp else "xdata"
            glob.setdefault(name, (space, ref, sz * cnt, dims, f.stem))
    # write
    lines = ["# sdk_types.tsv - generated by scripts/ghidra_sdk_types.py (Keil C51 layout: big-endian, no padding). Do not edit."]
    for nm in T.order:
        g = T.agg[nm]
        if g["kind"] == "E":
            lines.append("E\t%s\t%d\t%s" % (nm, g["size"], ",".join(f"{k}={v}" for k, v in g["vals"])))
        else:
            lines.append(f"{g['kind']}\t{nm}\t{g['size']}")
            for off, fn, ref, cnt, cm in g["fields"]:
                lines.append(f"F\t{off}\t{fn}\t{ref}\t{cnt}\t{cm}")
            lines.append("")
    OUT.write_text("\n".join(lines) + "\n")
    with GLOBALS.open("w") as f:
        f.write("name\tspace\ttype\tsize\tdims\tfile\n")
        for nm, (sp, ref, sz, dims, fl) in sorted(glob.items()):
            f.write(f"{nm}\t{sp}\t{ref}\t{sz}\t{'x'.join(map(str, dims))}\t{fl}\n")
    ne = sum(1 for g in T.agg.values() if g["kind"] == "E")
    log(f"{len(files)} files; types: {len(T.agg)} ({ne} enums, {len(T.agg)-ne} struct/union); globals: {len(glob)}; -> {OUT}, {GLOBALS}")


if __name__ == "__main__":
    main()
