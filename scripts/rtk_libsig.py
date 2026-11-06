#!/usr/bin/env python3
"""Realtek library signature DB: build masked signatures from Keil .LIB files, match vendor firmware.

  rtk_libsig.py build <lib.LIB> --label <version-label>
      -> ~/vendors/realtek/analysis/libsigs/<label with / as __>.json  (derived from Realtek
         binaries: never commit). Per function: bytes + wildcard mask (link-time fixups masked).
  rtk_libsig.py match <banks dir | image file> [--labels all|a,b] [--out DIR]
      -> per-function EXACT / NEAR / ABSENT / SHORT over all selected labels, per-module best
         label, verdict, lib_match.tsv and lib_match_names_bank<N>.tsv (ghidra_names format).
  rtk_libsig.py srccheck <lib.LIB> <src dir>...   -> LIB publics vs C function definitions
  rtk_libsig.py list      -> stored labels

Classes: EXACT = all non-wildcard bytes match (n>1 placements = EXACT-MULTI, first reported);
NEAR = best placement >= 90% of non-wildcard bytes; SHORT = < 12 bytes or < 8 fixed bytes
(placements listed, never counted as evidence); else ABSENT.
Logs: ./tmp/logs/rtk_libsig.log. Repo root: $AWTO_DDC_REPO -> file-relative.
"""
import argparse, collections, json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import omf51_lib as omf

REPO = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
ANALYSIS = Path.home() / "vendors/realtek/analysis"
SIGDIR = ANALYSIS / "libsigs"
LOG = REPO / "tmp/logs/rtk_libsig.log"
SHORT_BYTES, SHORT_FIXED, NEAR_MIN, RUN_MIN = 12, 8, 0.90, 6


class Tee:
    def __init__(self):
        LOG.parent.mkdir(parents=True, exist_ok=True)
        self.f = open(LOG, "a")

    def __call__(self, *a):
        s = " ".join(str(x) for x in a)
        print(s)
        self.f.write(s + "\n"); self.f.flush()


log = Tee()


def sigfile(label):
    return SIGDIR / (label.replace("/", "__") + ".json")


def build(lib, label):
    fns = []
    for m in omf.parse_lib(lib):
        for pub, seg, off, size in m.functions():
            if size <= 0 or seg.data is None:
                continue
            data = bytes(seg.data[off:off + size])
            mask = bytes(0x00 if (off + i) in seg.reloc or not seg.known[off + i] else 0xFF
                         for i in range(size))
            fns.append(dict(name=omf.display_name(m, pub), sym=pub, module=m.name, size=size,
                            hex=data.hex(), mask=mask.hex()))
    SIGDIR.mkdir(parents=True, exist_ok=True)
    json.dump(dict(label=label, lib=str(lib), functions=fns), open(sigfile(label), "w"), indent=0)
    log(f"build {label}: {len(fns)} functions -> {sigfile(label)}")


def load_banks(p):
    p = Path(p).expanduser()
    if p.is_dir():
        return {int(f.stem[4:]): f.read_bytes() for f in sorted(p.glob("bank*.bin"))}
    return {0: p.read_bytes()}


def pattern(data, mask):
    return re.compile(b"(?s)(?=" + b"".join(re.escape(bytes([b])) if k else b"." for b, k in zip(data, mask)) + b")")


def fuzzy(data, mask, banks):
    fixed = [i for i, k in enumerate(mask) if k]
    runs, i = [], 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]:
                j += 1
            if j - i >= RUN_MIN:
                runs.append((i, j))
            i = j
        else:
            i += 1
    votes = collections.Counter()
    for bn, img in banks.items():
        for a, b in runs:
            pos = img.find(data[a:b])
            n = 0
            while pos >= 0 and n < 40:
                if pos - a >= 0:
                    votes[(bn, pos - a)] += b - a
                pos = img.find(data[a:b], pos + 1); n += 1
    best = (0.0, None)
    for (bn, st), _ in votes.most_common(8):
        img = banks[bn][st:st + len(data)]
        ok = sum(1 for i in fixed if i < len(img) and img[i] == data[i])
        sc = ok / len(fixed)
        if sc > best[0]:
            best = (sc, (bn, st))
    return best


def classify(f, banks):
    data, mask = bytes.fromhex(f["hex"]), bytes.fromhex(f["mask"])
    nfixed = sum(1 for k in mask if k)
    hits = []
    if nfixed:
        pat = pattern(data, mask)
        for bn, img in banks.items():
            hits += [(bn, m.start()) for m in pat.finditer(img)]
    short = f["size"] < SHORT_BYTES or nfixed < SHORT_FIXED
    if short:
        return "SHORT", hits, 1.0 if hits else 0.0
    if hits:
        return ("EXACT" if len(hits) == 1 else "EXACT-MULTI"), hits, 1.0
    sc, loc = fuzzy(data, mask, banks)
    return ("NEAR" if sc >= NEAR_MIN else "ABSENT"), ([loc] if loc and sc >= NEAR_MIN else []), sc


def match(image, labels, outdir):
    banks = load_banks(image)
    files = sorted(SIGDIR.glob("*.json")) if labels == "all" else [sigfile(l) for l in labels.split(",")]
    rows, names = [], {}
    for sf in files:
        db = json.load(open(sf))
        for f in db["functions"]:
            cls, hits, sc = classify(f, banks)
            bank = ";".join(f"{b}:{a:04x}" for b, a in hits[:4]) + (f";+{len(hits)-4}" if len(hits) > 4 else "")
            rows.append(dict(function=f["name"], module=f["module"], label=db["label"], size=f["size"],
                             cls=cls, where=bank, pct=round(sc * 100, 1), hits=hits))
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    with open(outdir / "lib_match.tsv", "w") as o:
        o.write("function\tmodule\tlabel\tsize\tclass\tbank:addr\tmatch%\n")
        for r in rows:
            o.write(f"{r['function']}\t{r['module']}\t{r['label']}\t{r['size']}\t{r['cls']}\t{r['where']}\t{r['pct']}\n")
    # per label summary + module best label
    log(f"image {image}: {len(banks)} bank(s)")
    modbest = collections.defaultdict(dict)
    for lab in sorted({r["label"] for r in rows}):
        c = collections.Counter(r["cls"] for r in rows if r["label"] == lab)
        log(f"  {lab}: {dict(c)}")
    for r in rows:
        if r["cls"] in ("EXACT", "EXACT-MULTI", "NEAR"):
            modbest[r["module"]][r["label"]] = modbest[r["module"]].get(r["label"], 0) + 1
    log(f"  modules with a match: {len(modbest)}; best label per module (modules won): "
        f"{dict(collections.Counter(max(v, key=v.get) for v in modbest.values()))}")
    long_ = [r for r in rows if r["cls"] != "SHORT"]
    ex = [r for r in long_ if r["cls"].startswith("EXACT")]
    ne = [r for r in long_ if r["cls"] == "NEAR"]
    log(f"  non-short functions {len(long_)}: exact {len(ex)}, near {len(ne)}, absent {len(long_)-len(ex)-len(ne)}")
    weak = [r for r in rows if r["cls"] == "ABSENT" and r["pct"] >= 60]
    log(f"  ABSENT but 60-90% similar (likely a variant of the lib function, or a look-alike): {len(weak)}")
    for r in weak:
        log(f"    {r['function']} ({r['module']}) {r['pct']}%")
    # names TSVs (EXACT unique only, one per bank; lowest-label order wins ties)
    seen = set()
    for r in ex:
        if r["cls"] != "EXACT":
            continue
        bn, a = r["hits"][0]
        key = (bn, a)
        if key in seen:
            continue
        seen.add(key)
        names.setdefault(bn, []).append((a, r))
    for bn, lst in sorted(names.items()):
        with open(outdir / f"lib_match_names_bank{bn}.tsv", "w") as o:
            o.write(f"# lib_match_names_bank{bn}.tsv - names from exact Realtek library signature matches (rtk_libsig.py)\n")
            o.write("# Format: address<TAB>name<TAB>type<TAB>comment<TAB>status\n")
            for a, r in sorted(lst, key=lambda x: x[0]):
                o.write(f"CODE:{a:04x}\t{r['function']}\tfunc\tRealtek lib {r['label']} module {r['module']}, exact masked match.\t[lib]\n")
    log(f"  names written: {sum(len(v) for v in names.values())} in {len(names)} bank file(s) under {outdir}")


def srccheck(lib, srcdirs):
    """Compare .LIB code publics with C functions defined in the given source trees."""
    pat = re.compile(r"^[A-Za-z_][\w \t\*]*?\b([A-Za-z_]\w*)[ \t]*\([^;{}]*\)[ \t]*(?://[^\n]*)?\n?[ \t]*\{", re.M)
    defs = set()
    for d in srcdirs:
        for f in Path(d).rglob("*.c"):
            t = re.sub(r"/\*.*?\*/", "", f.read_text(errors="replace"), flags=re.S)
            defs |= {m.group(1) for m in pat.finditer(t) if m.group(1) not in ("if", "while", "for", "switch")}
    libfn = {omf.display_name(m, n) for m in omf.parse_lib(lib) for n, *_ in m.functions()}
    log(f"srccheck {lib}: lib {len(libfn)} functions, sources define {len(defs)}")
    log(f"  in lib, not in sources ({len(libfn - defs)}): {sorted(libfn - defs)}")
    log(f"  in sources, not in lib ({len(defs - libfn)}): count only; sample {sorted(defs - libfn)[:10]}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build"); b.add_argument("lib"); b.add_argument("--label", required=True)
    m = sp.add_parser("match"); m.add_argument("image"); m.add_argument("--labels", default="all")
    m.add_argument("--out", default=str(ANALYSIS))
    c = sp.add_parser("srccheck"); c.add_argument("lib"); c.add_argument("srcdirs", nargs="+")
    sp.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "build":
        build(a.lib, a.label)
    elif a.cmd == "match":
        match(a.image, a.labels, a.out)
    elif a.cmd == "srccheck":
        srccheck(a.lib, a.srcdirs)
    else:
        for f in sorted(SIGDIR.glob("*.json")):
            print(json.load(open(f))["label"], len(json.load(open(f))["functions"]))


if __name__ == "__main__":
    main()
