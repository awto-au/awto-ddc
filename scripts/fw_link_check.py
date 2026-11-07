#!/usr/bin/env python3
"""Static reachability verifier for a banked SDCC image + linker map (awto-ddc#11, #16).

usage: fw_link_check.py --bin IMG --map MAP [--layout bank_layout.tsv] [--common 0x5000] [--against OTHER_FINDINGS]
Checks every code chunk of the image (disassembled from the .bin) against where the CPU will be:
- common chunk: executes in ANY bank, so it may only touch common addresses
- bank-n chunk: 16-bit addresses >= COMMON resolve inside bank n
Finding kinds (key = kind|src|detail, address-free so two images can be diffed):
  call_common_to_banked  lcall/ljmp/acall/ajmp from common to an address >= COMMON
  call_no_target         banked source, target address has no code chunk in the same bank
  call_into_const        target is a const chunk, not code
  call_mid_chunk         call/jmp lands inside a function (not its first byte)
  rel_leaves_chunk       sjmp/jcc out of its own chunk
  fallthrough            chunk does not end in ret/jmp: runs into the next address
  const_other_bank       mov dptr,#imm: imm is a const in another bank only (or banked const from common)
  gptr_const_xbank       banked const pointer set up, then a stub call into another bank (#16 class)
  stub_bad_target        stub data (lo,hi,bank) is not the first byte of a code chunk in that bank
  fnptr_banked           address of a banked function taken in code / data without a stub
  vector_banked          interrupt vector jumps to a banked address
  bank_reg_access        movx on 0xFFFF that no proof below covers (write outside __bs_call/__bs_ret, or a bank read whose
                         tables are not all in the reader's bank)
  const_ptr_gptr_xbank   asm (post-bank pass, --asm): address of a banked const passed to a function that reads generic pointers
                         (__gptrget) and sits in another bank: it reads its OWN bank at that address (#46: boot logo tile map)
  stack_arg_via_stub     function reads stack-passed args via SP/_bp but is reached through a bank stub (+4 B between args and
                         callee, #11): must be common or share its callers' bank
  isr_reach_stub         stub reachable from an ISR, and the ISR register / bank-switch proof fails
  kind_source            CH areas with no kind (fn/const) from --asm .rst or --layout: not checked
  kind_stale             --asm .rst disagrees with this map (area address or kind vs --layout): not this image's build tree
Chunk kinds: the linked .rst in --asm (an area of data directives only = const, never disassembled), else --layout.
Proofs (one `proven` log line each, no finding), all from this image + its .rst:
  bank switch   __bs_call/__bs_ret: `mov __bs_cur,Rn` .. `mov a,Rn; movx @dptr(=0xFFFF),a`, Rn untouched in between
                (an ISR between the two writes saves/restores __bs_cur = the bank being entered)
  bank read     `movx a,@0xFFFF` (GET_CURRENT_BANK_NUMBER) in bank-n code: every const it references, and every entry of a
                pointer table it references, is in bank n or common; in common code: all common (it reads the caller's bank)
  DMA callee    gptr_const_xbank where the caller also reads 0xFFFF (the DMA bank argument) and the callee's call closure has
                no movc @a+dptr / indirect jump: only the flash DMA, with the caller's bank number, reads the table
  ISR via stub  every ISR that reaches a stub pushes ACC,B,DPL,DPH,PSW,R0-R3 (register bank 0) before anything else
  literal imm   `#0x566c` written as a number in the .rst is a value (message id, register), not a const/fn address
Exit 1 if any finding. Logs: tmp/logs/fw_link_check.log
"""
import argparse, bisect, os, re, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import d8051  # noqa: E402

REPO = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
BANK = 0x10000
TERM = ("RET", "RETI", "LJMP", "SJMP", "AJMP", "JMP @A+DPTR")
BANK_REG = 0xFFFF
FLOW = ("RET", "LJMP", "SJMP", "AJMP", "LCALL", "ACALL", "JMP")


def parse_map(path):
    """areas: name -> dict(addr,size,syms[(name,addr)]) with code-space symbols ('C:'); dsyms: other symbols (DATA etc.)."""
    areas, cur, dsyms = {}, None, {}
    for l in Path(path).read_text(errors="replace").splitlines():
        m = re.match(r"^(\S+)\s+([0-9A-F]{8})\s+([0-9A-F]{8}) =\s+\d+\. bytes \((.*)\)", l)
        if m:
            cur = areas.setdefault(f"{m.group(1)}@{m.group(2)}", dict(    # names are cut to 32 chars: not unique
                name=m.group(1), addr=int(m.group(2), 16), size=int(m.group(3), 16), attr=m.group(4), syms=[]))
            continue
        m = re.match(r"^C:\s+([0-9A-F]{8})\s+(\S+)", l)
        if m and cur is not None and not m.group(2).startswith(("l_", "s_")):
            cur["syms"].append((m.group(2), int(m.group(1), 16)))
            continue
        m = re.match(r"^\s+([0-9A-F]{8})\s+(\w+)\s+\w+\s*$", l)
        if m:
            dsyms.setdefault(m.group(2), int(m.group(1), 16))
    return areas, dsyms


# .rst line: addr, bytes, [cycles], source line number, source text
RST_LINE = re.compile(r"^ {6}([0-9A-F]{6})?(?: [0-9A-F]{2})*\s*(?:\[\s*\d+\])?\s*\d+ (.*)$")
DATA_DIR = re.compile(r"^\.(db|byte|dw|word|ascii|asciz|ascis|ds|blkb|blkw|str|strz|strs)\b", re.I)
LIT_IMM = re.compile(r"#\s*\(?\s*(?:0x[0-9a-fA-F]+|\d+)\s*\)?\s*$")
SIG = re.compile(r"^;\s+\S.*\.c:\d+: [\w\s\*]*?\b(\w+)\s*\((.*)\)\s*$")


class Rst:
    """The build's linked listings (*.rst in the post-bank asm dir): kind and address of every CH_ area, and which
    instructions carry a numeric-literal immediate (a value, not a symbol address)."""

    def __init__(self, asm_dir):
        self.areas, self.by_name, self.lit = {}, defaultdict(set), set()
        self.syms_at, self.sig = {}, {}                       # abs insn addr -> symbols in its # operand; fn -> C params
        for f in sorted(Path(asm_dir).glob("*.rst")):
            cur = None
            for l in f.read_text(errors="replace").splitlines():
                m = RST_LINE.match(l)
                if not m:
                    continue
                a = int(m.group(1), 16) if m.group(1) else None
                ms = SIG.match(m.group(2))
                if ms and cur and cur[0][3:] == ms.group(1):
                    self.sig.setdefault(cur[0][:32], ms.group(2))
                src = m.group(2).split(";", 1)[0].strip()
                ma = re.match(r"\.area\s+(\S+)", src)
                if ma:
                    self._close(cur)
                    cur = [ma.group(1), None, False, False]          # name, first addr, has insn, has data
                    continue
                if cur is None or not src:
                    continue
                if cur[1] is None and a is not None:
                    cur[1] = a
                if re.match(r"^(\w+::?|\d+\$:)$", src):
                    continue
                if src.startswith("."):
                    cur[3] |= bool(DATA_DIR.match(src))
                    continue
                cur[2] = True
                if a is not None and LIT_IMM.search(src):
                    self.lit.add(a)
                if a is not None and "#" in src:
                    s = set(re.findall(r"(?<![\w$])(_\w+)", src.split("#", 1)[1]))
                    if s:
                        self.syms_at[a] = s
            self._close(cur)

    def _close(self, cur):
        if cur and cur[0].startswith("CH_") and cur[1] is not None and (cur[2] or cur[3]):
            self.areas[(cur[0][:32], cur[1])] = "fn" if cur[2] else "const"
            self.by_name[cur[0][:32]].add(cur[1])


class Image:
    def __init__(self, bin_path, map_path, layout, common, asm_dir=None):
        self.img = Path(bin_path).read_bytes()
        self.common = common
        self.areas, self.dsyms = parse_map(map_path)
        rst_ok = asm_dir and Path(asm_dir).is_dir() and any(Path(asm_dir).glob("*.rst"))
        self.rst = Rst(asm_dir) if rst_ok else None
        self.kinds = {}                                       # symbol -> fn|const
        if layout and Path(layout).exists():
            for ln in Path(layout).read_text().splitlines():
                f = ln.split("\t")
                if len(f) == 5 and f[0] in ("fn", "const"):
                    self.kinds[f[1][:32]] = f[0]          # the map cuts symbol names to 32 chars
        self.chunks, self.unknown, self.stale = [], [], []    # chunk dict(kind,name,addr,size,reg,area)
        for a in self.areas.values():
            an = a["name"]
            if "CODE" not in a["attr"] or not a["size"] or an.startswith("VECTORS"):
                continue
            if an.startswith("ST"):
                kind, name = "stub", (a["syms"][0][0] if a["syms"] else an)
            elif an.startswith("CH"):
                name = a["syms"][0][0] if a["syms"] else an
                lk = self.kinds.get(name[:32]) or self.kinds.get(an[2:34]) or self.kinds.get(an[2:])
                kind = lk
                if self.rst:
                    kind = self.rst.areas.get((an[:32], a["addr"]))
                    if kind is None:
                        at = sorted(self.rst.by_name.get(an[:32], ()))
                        self.stale.append(f"{an} map 0x{a['addr']:06x}, .rst {[hex(x) for x in at] or 'absent'}")
                    elif lk and lk != kind:
                        self.stale.append(f"{an} .rst {kind}, layout {lk}")
                if kind is None:
                    self.unknown.append(an)
            else:
                kind, name = "fn", an                         # residual: HOME, GSINIT*, CSEG (library), CONST, XINIT
                if an in ("XINIT", "CONST"):
                    kind = "const"
            reg = "C" if a["addr"] < common else a["addr"] >> 16
            self.chunks.append(dict(kind=kind, name=name, addr=a["addr"], size=a["size"], reg=reg, area=an,
                                    syms=a["syms"]))
        self.by_reg = defaultdict(list)
        for c in self.chunks:
            self.by_reg[c["reg"]].append(c)
        for v in self.by_reg.values():
            v.sort(key=lambda c: c["addr"])
        self.gsyms = {n: ad for a in self.areas.values() for n, ad in a["syms"]}

    def sym_consts(self, c):
        """const chunks named in the .rst `#` operands of chunk c's instructions (complete for c's own code)."""
        if not self.rst:
            return []
        if not hasattr(self, "_cbn"):
            self._cbn = defaultdict(list)
            for k in self.chunks:
                if k["kind"] == "const":
                    self._cbn[k["name"][:32]].append(k)
            self._sa = sorted(self.rst.syms_at)
        out = []
        for a in self._sa[bisect.bisect_left(self._sa, c["addr"]):bisect.bisect_left(self._sa, c["addr"] + c["size"])]:
            for s in self.rst.syms_at[a]:
                out += self._cbn.get(s[:32], [])
        return out

    def ptr_params(self, c):
        """True if c's C signature (from the .rst source comment) has a pointer parameter; None if unknown."""
        if not self.rst or not c["area"].startswith("CH"):
            return None
        s = self.rst.sig.get(c["area"][:32])
        return None if s is None else "*" in s

    def const_starts(self):
        if not hasattr(self, "_cst"):
            self._cst = {c["addr"] & 0xFFFF for c in self.chunks if c["kind"] == "const"}
        return self._cst

    def literal(self, c, a16):
        """True if the insn at 16-bit a16 of chunk c has a numeric-literal immediate in the .rst source."""
        return bool(self.rst) and ((c["addr"] & ~0xFFFF) | a16) in self.rst.lit

    def find(self, reg, a16):
        """chunk containing 16-bit address a16 as seen from bank `reg` (common chunks everywhere)."""
        lo = a16 if a16 < self.common else reg * BANK + a16
        for r in (("C",) if a16 < self.common else (reg,)):
            for c in self.by_reg.get(r, ()):
                if c["addr"] <= lo < c["addr"] + c["size"]:
                    return c
        return None

    def consts_at(self, a16):
        """[(bank, chunk)] of banked const chunks covering 16-bit address a16."""
        out = []
        for r, cs in self.by_reg.items():
            if r == "C":
                continue
            for c in cs:
                if c["kind"] == "const" and c["addr"] & 0xFFFF <= a16 < (c["addr"] & 0xFFFF) + c["size"] and c["addr"] >> 16 == r:
                    out.append((r, c))
        return out

    def code(self, c):
        return self.img[c["addr"]:c["addr"] + c["size"]]


def short(c):
    return c["name"] if c else "?"


def sweep(code, base):
    """Instructions of a chunk; skips SDCC's inline jump tables (`add a,#k; movc a,@a+pc` lo/hi byte tables
    after `jmp @a+dptr`). Yields ('i', insn) and ('t', addr, [targets])."""
    off, pend = 0, []
    while off < len(code):
        ins = d8051.decode(code, off, base)
        yield "i", ins
        off += ins.n
        pend = (pend + [ins])[-14:]
        if ins.text == "JMP @A+DPTR":
            pcs = [x for k, x in enumerate(pend) if x.text == "MOVC A,@A+PC" and k and pend[k - 1].text.startswith("ADD A,#")]
            if len(pcs) >= 2:
                st = [x.addr + 1 + code[x.off - 1] for x in pcs[-2:]]
                n = st[1] - st[0]
                lo = code[st[0] - base:st[0] - base + n]
                hi = code[st[1] - base:st[1] - base + n]
                if 0 < n < 256 and len(lo) == n == len(hi):
                    yield "t", st[0], [h << 8 | l for l, h in zip(lo, hi)]
                    off = st[1] - base + n
                    pend = []
                    continue
            # variant: `mov dptr,#lo_tab; movc a,@a+dptr` ... `mov dptr,#hi_tab; movc ...` (tables follow the jmp)
            dp = [x.dptr for k, x in enumerate(pend) if x.dptr is not None and k + 1 < len(pend)
                  and pend[k + 1].text == "MOVC A,@A+DPTR" or False]
            dp = [x.dptr for k, x in enumerate(pend[:-1]) if x.dptr is not None and pend[k + 1].text == "MOVC A,@A+DPTR"]
            if len(dp) >= 2 and 0 < dp[-1] - dp[-2] < 256 and base <= dp[-2] < base + len(code):
                n = dp[-1] - dp[-2]
                lo = code[dp[-2] - base:dp[-2] - base + n]
                hi = code[dp[-1] - base:dp[-1] - base + n]
                if len(lo) == n == len(hi):
                    yield "t", dp[-2], [h << 8 | l for l, h in zip(lo, hi)]
                    off = dp[-1] - base + n
                    pend = []


def movx_after(nxt):
    """The MOVX @DPTR that uses a just-loaded DPTR, or None if flow/DPTR changes first (`mov dptr,#0xffff; ret` = a value)."""
    for x in nxt[:6]:
        if x.text in ("MOVX @DPTR,A", "MOVX A,@DPTR"):
            return x
        if x.text.startswith(FLOW) or x.dptr is not None or x.text.startswith(("MOV DPL", "MOV DPH", "INC DPTR", "POP DP")):
            return None
    return None


def writes_rn(x, n):
    """insn x may write register Rn (bank 0 address n)."""
    op = x.raw[0]
    if op in (0x78 | n, 0xA8 | n, 0xF8 | n, 0x08 | n, 0x18 | n, 0xD8 | n, 0xC8 | n):
        return True
    return (op in (0xD0, 0xF5, 0x75, 0x05, 0x15) and len(x.raw) > 1 and x.raw[1] == n) or (op == 0x85 and x.raw[2] == n)


def switch_proof(im):
    """([(lo, hi)] proven bank-switch routines, [problems]). Proof per routine: `mov __bs_cur,Rn` precedes
    `mov dptr,#0xFFFF; mov a,Rn; movx @dptr,a` (the routine's last insn before its _sw label) and Rn is not written in
    between: an ISR taken between the two writes pushes the restore entry of __bs_cur = the bank being entered."""
    ranges, bad = [], []
    cur = im.dsyms.get("__bs_cur")
    for lo_s, hi_s in (("__bs_call", "__bs_call_sw"), ("__bs_ret", "__bs_ret_sw")):
        lo, hi = im.gsyms.get(lo_s), im.gsyms.get(hi_s)
        if lo is None or hi is None or cur is None or not 0 < hi - lo < 64:
            bad.append(f"{lo_s}: __bs_cur/{lo_s}/{hi_s} missing from the map")
            continue
        ins = list(d8051.disasm(im.img[lo:hi], base=lo))
        st = [k for k, x in enumerate(ins) if len(x.raw) == 2 and x.raw[0] & 0xF8 == 0x88 and x.raw[1] == cur]
        w = len(ins) - 1
        n = ins[st[0]].raw[0] & 7 if len(st) == 1 else None
        ok = (n is not None and w >= 2 and ins[w].text == "MOVX @DPTR,A" and ins[w - 1].raw == bytes([0xE8 | n])
              and ins[w - 2].dptr == BANK_REG and st[0] < w - 2 and not any(writes_rn(x, n) for x in ins[st[0] + 1:w]))
        if ok:
            ranges.append((lo, hi))
        else:
            bad.append(f"{lo_s}: no `mov __bs_cur,Rn .. mov dptr,#0xFFFF; mov a,Rn; movx @dptr,a` sequence")
    return ranges, bad


def ptr_entries(im, k):
    """16-bit entries of const chunk k if it is a code-pointer table (every 2-byte word, BE or LE, is the start of a
    const chunk somewhere); else []."""
    if k["size"] < 2 or k["size"] % 2:
        return []
    starts = im.const_starts()
    b = im.code(k)
    for order in ("BE", "LE"):
        w = [(b[o] << 8 | b[o + 1]) if order == "BE" else (b[o + 1] << 8 | b[o]) for o in range(0, len(b), 2)]
        if all(x in starts for x in w):
            return w
    return []


def bank_read_bad(im, c, refs, xconst, callers, by_addr, depth=4):
    """'' if a 0xFFFF read in chunk c is proven, else why not. The value is c's own bank (banked c) or the caller's
    (common c); a table can reach the DMA only from c's code or, through pointer parameters, from its callers. So every
    const referenced there (binary + .rst symbols, pointer-table entries included) must be in c's bank or common;
    a caller with pointer parameters itself adds its callers, up to `depth` levels."""
    reg, bad, seen, todo = c["reg"], [], set(), [(c, 0)]
    while todo:
        f, d = todo.pop()
        if f["addr"] in seen:
            continue
        seen.add(f["addr"])
        if xconst[f["addr"]]:
            bad.append(f"{f['name']} references a const in another bank ({xconst[f['addr']][0]})")
        for k in refs[f["addr"]] + im.sym_consts(f):
            if k["reg"] != "C" and (reg == "C" or k["reg"] != reg):
                bad.append(f"{f['name']} references {k['name']} in bank {k['reg']}")
            for w in ptr_entries(im, k):
                t = None if w < im.common or reg == "C" else im.find(reg, w)
                if w >= im.common and (t is None or t["kind"] != "const"):
                    bad.append(f"{k['name']} entry 0x{w:04x} is not a const in {'common' if reg == 'C' else f'bank {reg}'}")
        pp = im.ptr_params(f)
        if pp is None:
            bad.append(f"{f['name']}: C signature unknown (no .rst)")
        elif pp:
            if d >= depth:
                bad.append(f"{f['name']}: pointer parameter chain deeper than {depth}")
            todo += [(by_addr[a], d + 1) for a in sorted(callers.get(f["addr"], ()))]
    return "; ".join(sorted(set(bad))[:3])


def segment(im, reg, a16):
    """(chunk, abs lo, abs hi) of the code holding a16 seen from reg; residual areas (library CSEG) split at global symbols."""
    c = im.find(reg if reg != "C" else 0, a16)
    if c is None:
        return None
    if c["area"].startswith(("CH", "ST")):
        return c, c["addr"], c["addr"] + c["size"]
    ab = a16 if a16 < im.common else reg * BANK + a16
    cuts = sorted({a for _, a in c["syms"] if c["addr"] <= a < c["addr"] + c["size"]} | {c["addr"]})
    lo = max(a for a in cuts if a <= ab)
    hi = min([a for a in cuts if a > ab] + [c["addr"] + c["size"]])
    return c, lo, hi


def code_read_closure(im, start, reg, visited=None):
    """None if nothing reachable from chunk `start` (running in region reg) reads code space, else why not provable.
    `visited` (list) collects the names of the segments walked.
    Follows calls/jumps/branches out of a segment, jump-table entries, and stubs to their targets."""
    work, seen = [(reg, start["addr"] & 0xFFFF)], set()
    while work:
        r, a = work.pop()
        seg = segment(im, r, a)
        if seg is None:
            return f"0x{a:04x} (region {r}): no code chunk"
        c, lo, hi = seg
        if lo in seen:
            continue
        seen.add(lo)
        if visited is not None:
            visited.append(c["name"] if c["area"].startswith(("CH", "ST")) else f"{c['area']}+0x{lo - c['addr']:x}")
        if c["kind"] == "stub":
            t = stub_target(im.code(c))
            if t is None:
                return f"stub {c['name']} undecodable"
            work.append((t[1], t[0]))
            continue
        if c["kind"] != "fn":
            return f"enters {c['kind']} {c['name']}"
        b16 = lo & 0xFFFF
        items = list(sweep(im.img[lo:hi], b16))
        for n, it in enumerate(items):
            if it[0] == "t":
                work += [(r, x) for x in it[2]]
                continue
            x = it[1]
            if x.text == "MOVC A,@A+DPTR":
                return f"{c['name']} reads code (movc a,@a+dptr at 0x{x.addr:04x})"
            if x.text == "JMP @A+DPTR" and not (n + 1 < len(items) and items[n + 1][0] == "t"):
                return f"{c['name']} indirect jump at 0x{x.addr:04x}"
            if x.target is not None and not b16 <= x.target < b16 + (hi - lo):
                work.append((r, x.target))
    return None


def check(im, xdata=(), regnames=None, proven=None):
    F = []
    proven = [] if proven is None else proven
    add = lambda kind, src, det, addr, **kw: F.append(dict(kind=kind, src=src, det=det, addr=addr, **kw))
    # kind None = unclassified CH area (its own kind_source finding): still a valid stub target
    fn_start = {(c["reg"], c["addr"] & 0xFFFF): c for c in im.chunks if c["kind"] in ("fn", None)}
    stubs = {}
    in_xdata = lambda v: any(lo <= v < hi for lo, hi in xdata)
    # stub decode: lcall __bs_call + lo, hi, bank (6 B), mov r0,#bank; mov r1,#lo; mov r2,#hi; ljmp (9 B), mov r0,#bank; mov dptr,#t; ljmp (8 B)
    for c in im.chunks:
        if c["kind"] != "stub":
            continue
        b = im.code(c)
        t = stub_target(b)
        if t is None:
            add("stub_bad_target", c["name"], f"unexpected stub bytes {b.hex()}", c["addr"])
            continue
        tgt, bank = t
        tc = fn_start.get((bank, tgt)) if tgt >= im.common else fn_start.get(("C", tgt))
        stubs[c["addr"]] = (tgt, bank, tc)
        if tc is None:
            add("stub_bad_target", c["name"], f"-> bank {bank} 0x{tgt:04x} is not a function start", c["addr"])
    stub_lo = {a & 0xFFFF: a for a in stubs}
    gx = []                                                   # gptr_const_xbank candidates, judged after the sweep

    def xbank_stub(own, nxt, reg, c, at):
        """pointer to a banked const set up: does a stub call into another bank follow?"""
        for x in nxt:
            if x.text.startswith(("RET", "LJMP", "SJMP", "AJMP", "JMP")):
                break
            if x.text.startswith("LCALL") and x.target is not None and x.target in stub_lo:
                tgt, bank, tc = stubs[stub_lo[x.target]]
                if bank != reg:
                    gx.append((c, own[0], tc, bank, at))
                break
    sp_read = re.compile(r"^MOV (A|R[0-7]|DPL|DPH|B),SP$")
    for sa, (tgt, bank, tc) in stubs.items():
        if tc is None or tc["reg"] == "C":
            continue
        if any(it[0] == "i" and sp_read.match(it[1].text) for it in sweep(im.code(tc), tc["addr"] & 0xFFFF)):
            add("stack_arg_via_stub", tc["name"], f"stub at 0x{sa:04x} -> bank {bank}: callee reads its args at SP-n", sa)
    vecs = im.img[0:0x53]
    for i in range(0, 0x53, 8):
        if vecs[i] == 0x02:
            t = vecs[i + 1] << 8 | vecs[i + 2]
            if t >= im.common:
                add("vector_banked", f"vec{i:02x}", f"-> 0x{t:04x}", i)
    fnaddrs = {}
    for c in im.chunks:
        if c["kind"] == "fn" and c["reg"] != "C":
            fnaddrs.setdefault(c["addr"] & 0xFFFF, []).append(c)
    reads, writes = [], []                                    # (chunk, 16-bit addr) of movx on 0xFFFF
    refs, xconst = defaultdict(list), defaultdict(list)       # per chunk: own-bank/common consts, other-bank const hits
    callers = defaultdict(set)                                # fn chunk addr -> addrs of chunks calling it (direct / stub)

    def other_bank(c, det, at):
        add("const_other_bank", c["name"], det, at)
        xconst[c["addr"]].append(det)
    for c in im.chunks:
        if c["kind"] != "fn":                                 # const, stub, or no kind (kind_source finding)
            continue
        code = im.code(c)
        reg, base = c["reg"], c["addr"] & 0xFFFF
        src = c["name"]
        ins = []
        for item in sweep(code, base):
            if item[0] == "t":
                for T in item[2]:
                    if not (base <= T < base + c["size"]) and c["area"].startswith("CH"):
                        add("rel_leaves_chunk", src, f"jump table entry 0x{T:04x}", item[1])
            else:
                ins.append(item[1])
        last = ins[-1] if ins else None
        resid = not c["area"].startswith("CH")
        if last and not last.text.startswith(TERM) and not resid:
            add("fallthrough", src, f"ends with '{last.text}'", last.addr)
        for k, i in enumerate(ins):
            t = i.text
            if t.startswith(("LCALL", "LJMP", "ACALL", "AJMP")) and i.target is not None:
                T = i.target
                if reg == "C":
                    if T >= im.common:
                        add("call_common_to_banked", src, f"{t.split()[0]} 0x{T:04x}", i.addr,
                            tgt=short(next((x for r, cs in im.by_reg.items() if r != "C" for x in cs
                                            if x["addr"] & 0xFFFF == T and x["kind"] == "fn"), None)))
                        continue
                tc = im.find(reg if reg != "C" else 0, T)
                if tc is not None and tc["kind"] == "stub" and tc["addr"] in stubs and stubs[tc["addr"]][2] is not None:
                    callers[stubs[tc["addr"]][2]["addr"]].add(c["addr"])
                elif tc is not None and (tc["addr"] & 0xFFFF) == T:
                    callers[tc["addr"]].add(c["addr"])
                if tc is None:
                    add("call_no_target", src, f"{t.split()[0]} 0x{T:04x}", i.addr)
                elif tc["kind"] == "const":
                    add("call_into_const", src, f"{t.split()[0]} {tc['name']}", i.addr)
                elif tc is not c and tc["area"].startswith("CH") and (tc["addr"] & 0xFFFF) != T and not t.startswith(("LJMP", "AJMP")):
                    add("call_mid_chunk", src, f"{t.split()[0]} {tc['name']}+{T - (tc['addr'] & 0xFFFF)}", i.addr)
            elif i.target is not None and t.split()[0] in ("SJMP", "JC", "JNC", "JZ", "JNZ", "JB", "JNB", "JBC",
                                                           "CJNE", "DJNZ"):
                if not (base <= i.target < base + c["size"]) and not resid:
                    add("rel_leaves_chunk", src, f"{t}", i.addr)
            if t.startswith("ADD A,#") and not resid and not im.literal(c, i.addr):   # table base: add a,#t; mov a,#(t>>8); addc a,b
                lo = int(t[7:9], 16)
                for y in ins[k + 1:k + 8]:
                    m3 = re.match(r"MOV A,#([0-9A-F]{2})h$", y.text)
                    if m3:
                        v = int(m3.group(1), 16) << 8 | lo
                        if v >= im.common and any(z.text.startswith("ADDC A,") for z in ins[k + 1:k + 10]):
                            cs = im.consts_at(v)
                            own = [x for r, x in cs if r == reg]
                            refs[c["addr"]] += own
                            if reg == "C" and cs:
                                other_bank(c, f"arith base 0x{v:04x}: common code, const {cs[0][1]['name']} in bank {cs[0][0]}", i.addr)
                            elif cs and not own and not im.find(reg, v):
                                other_bank(c, f"arith base 0x{v:04x}: {cs[0][1]['name']} is in bank {cs[0][0]}, code in bank {reg}", i.addr)
                        break
            mr = R2_IMM.match(t)
            if mr and not im.literal(c, i.addr):     # Keil ABI generic pointer argument: R3 tag, R2 hi, R1 lo
                lo = next((int(m1.group(1), 16) for y in ins[max(0, k - 4):k + 5] if (m1 := R1_IMM.match(y.text))), None)
                v = int(mr.group(1), 16) << 8 | (lo or 0)
                if lo is not None and v >= im.common:
                    own = [x for r, x in im.consts_at(v) if r == reg]
                    if own:
                        refs[c["addr"]] += own
                        xbank_stub(own, ins[k + 1:k + 15], reg, c, i.addr)
            if i.dptr is None:
                continue
            v = i.dptr
            nxt = ins[k + 1:k + 1 + 14]
            if v == BANK_REG:
                mx = movx_after(nxt)
                if mx is not None:
                    (writes if mx.text.startswith("MOVX @") else reads).append((c, i.addr))
                    continue
            if im.literal(c, i.addr):                         # numeric literal in the source: a value, not an address
                continue
            movx_next = any(x.text.startswith("MOVX") for x in nxt[:3])
            movc_next = False
            for x in nxt:
                if x.dptr is not None or x.text.startswith(("RET", "LJMP", "SJMP", "AJMP", "LCALL")):
                    break
                if x.text == "MOVC A,@A+DPTR":
                    movc_next = True
                    break
            is_reg = (regnames and v in regnames) or movx_next or in_xdata(v)
            if v < im.common and not is_reg:
                cc = im.find(0, v)
                if cc is not None and cc["kind"] == "const":
                    refs[c["addr"]].append(cc)
            if v >= im.common and not is_reg:
                cs = [(r, x) for r, x in im.consts_at(v) if movc_next or x["addr"] & 0xFFFF == v]
                own = [x for r, x in cs if r == reg]
                refs[c["addr"]] += own
                if reg == "C" and cs:
                    other_bank(c, f"common code reads banked const {cs[0][1]['name']} (bank {cs[0][0]})", i.addr)
                elif cs and not own and not im.find(reg, v):
                    other_bank(c, f"{cs[0][1]['name']} is in bank {cs[0][0]}, code in bank {reg}", i.addr)
                elif own:
                    xbank_stub(own, nxt, reg, c, i.addr)
                if reg != "C" or v >= im.common:              # address of a banked fn taken in code
                    for fc in fnaddrs.get(v, ()):
                        if not cs and fc["reg"] == reg and not in_xdata(v):
                            add("fnptr_banked", src, f"mov dptr,#{fc['name']}", i.addr)
    sw, sw_bad = switch_proof(im)
    for lo, hi in sw:
        proven.append(f"bank switch  0x{lo:04x}-0x{hi:04x}: __bs_cur written before 0xFFFF from the same register")
    for c, at in writes:
        if c["reg"] == "C" and any(lo <= at < hi for lo, hi in sw):
            continue
        add("bank_reg_access", c["name"], "movx @0xFFFF,a outside a proven bank switch routine"
            + (f" ({'; '.join(sw_bad)})" if sw_bad else ""), at)
    reader = {c["addr"] for c, _ in reads}
    by_addr = {c["addr"]: c for c in im.chunks}
    for c, at in reads:
        why = bank_read_bad(im, c, refs, xconst, callers, by_addr)
        if why:
            add("bank_reg_access", c["name"], f"bank read not proven: {why}", at)
        else:
            n = len({k["addr"] for k in refs[c["addr"]] + im.sym_consts(c)})
            pp = " (pointer params: callers checked)" if im.ptr_params(c) else ""
            proven.append(f"bank read    {c['name']} (region {c['reg']}) 0x{at:04x}: {n} referenced const(s) in its bank/common{pp}")
    for c, k, tc, bank, at in gx:
        det = f"{k['name']} (bank {c['reg']}) -> stub {short(tc)} (bank {bank})"
        walked = []
        why = "caller does not read 0xFFFF (no DMA bank argument)" if c["addr"] not in reader else \
            (code_read_closure(im, tc, bank, walked) if tc is not None else "stub target unknown")
        if why:
            add("gptr_const_xbank", c["name"], f"{det}: {why}", at)
        else:
            proven.append(f"DMA callee   {c['name']}: {det}: caller reads 0xFFFF, callee closure ({len(walked)} fns) reads no code")
    return F


def symbolize(im, stubmap, reg, v):
    """(function/const name, offset) for 16-bit address v seen from region reg; stubs resolve to their target fn."""
    c = im.find(reg if reg != "C" else 0, v)
    if c is None:
        return None
    if c["kind"] == "stub":
        return stubmap.get(c["addr"], (c["name"], 0))
    nm = c["name"] if c["area"].startswith("CH") else c["area"]
    return (nm, v - (c["addr"] & 0xFFFF))


R1_IMM, R2_IMM = re.compile(r"MOV R1,#([0-9A-F]{2})h$"), re.compile(r"MOV R2,#([0-9A-F]{2})h$")


def stub_target(b):
    """(target 16-bit address, bank) of a stub's bytes, or None. 6 B: lcall __bs_call + lo hi bank;
    9 B: mov r0,#bank; mov r1,#lo; mov r2,#hi; ljmp __bs_call; 8 B (Keil ABI): mov r0,#bank; mov dptr,#target; ljmp __bs_call."""
    if len(b) == 6 and b[0] == 0x12:
        return b[3] | b[4] << 8, b[5]
    if len(b) == 9 and (b[0], b[2], b[4], b[6]) == (0x78, 0x79, 0x7A, 0x02):
        return b[3] | b[5] << 8, b[1]
    if len(b) == 8 and (b[0], b[2], b[5]) == (0x78, 0x90, 0x02):
        return b[3] << 8 | b[4], b[1]
    return None


def stub_targets(im):
    fn_start = {(c["reg"], c["addr"] & 0xFFFF): c for c in im.chunks if c["kind"] == "fn"}
    out = {}
    for c in im.chunks:
        b = im.code(c)
        t = stub_target(b) if c["kind"] == "stub" else None
        if t:
            tc = fn_start.get((t[1], t[0])) or fn_start.get(("C", t[0]))
            out[c["addr"]] = (tc["name"], 0) if tc else ("?bad", 0)
    return out


def equiv(good, bad):
    """Same source, other layout: every chunk must decode to the same instruction stream, and every absolute
    operand (call target, mov dptr,#imm, jump-table entry) must resolve to the same symbol+offset in both."""
    F = []
    gs, bs = stub_targets(good), stub_targets(bad)
    gc = {c["name"]: c for c in good.chunks if c["area"].startswith("CH") and c["kind"] != "stub"}
    bc = {c["name"]: c for c in bad.chunks if c["area"].startswith("CH") and c["kind"] != "stub"}
    add = lambda kind, src, det, addr: F.append(dict(kind=kind, src=src, det=det, addr=addr))
    for n in sorted(set(gc) | set(bc)):
        if n not in gc or n not in bc:
            add("equiv_chunk_missing", n, "only in " + ("bad" if n in bc else "good"), 0)
    for n in sorted(set(gc) & set(bc)):
        g, b = gc[n], bc[n]
        if g["size"] != b["size"]:
            add("equiv_size", n, f"{g['size']} vs {b['size']}", b["addr"]); continue
        if g["kind"] == "const":
            gb, bb = good.code(g), bad.code(b)
            if gb != bb:
                covered = set()
                for o in range(len(gb) - 1):
                    if gb[o:o + 2] == bb[o:o + 2]:
                        continue
                    for order in ("BE", "LE"):
                        f = (lambda d: d[o] << 8 | d[o + 1]) if order == "BE" else (lambda d: d[o + 1] << 8 | d[o])
                        x = symbolize(good, gs, g["reg"], f(gb))
                        y = symbolize(bad, bs, b["reg"], f(bb))
                        if x and y and x == y:
                            covered.update((o, o + 1))
                            break
                for o in range(len(gb)):
                    if gb[o] != bb[o] and o not in covered:
                        add("equiv_const_ptr", n, f"+{o}: good {gb[o]:02x} bad {bb[o]:02x} not part of a relocated pointer", b["addr"] + o)
            continue
        gi = list(sweep(good.code(g), g["addr"] & 0xFFFF))
        bi = list(sweep(bad.code(b), b["addr"] & 0xFFFF))
        if len(gi) != len(bi):
            add("equiv_stream", n, "instruction count differs", b["addr"]); continue
        gbase, bbase = g["addr"] & 0xFFFF, b["addr"] & 0xFFFF
        imm8 = []
        for x, y in zip(gi, bi):
            if x[0] != y[0]:
                add("equiv_stream", n, "table/insn mismatch", b["addr"]); break
            if x[0] == "t":
                if [t - gbase for t in x[2]] != [t - bbase for t in y[2]]:
                    add("equiv_table", n, "jump table entries differ in offsets", y[1])
                continue
            i, j = x[1], y[1]
            if i.raw[0] != j.raw[0]:
                add("equiv_stream", n, f"{i.text} vs {j.text}", j.addr); break
            if i.raw == j.raw:
                continue
            if i.text.startswith(("LCALL", "LJMP", "ACALL", "AJMP")):
                a = symbolize(good, gs, g["reg"], i.target)
                c2 = symbolize(bad, bs, b["reg"], j.target)
                if i.text.startswith(("ACALL", "AJMP")) and a and c2 and a == c2:
                    continue
                if a != c2 or a is None:
                    add("equiv_call", n, f"{i.text.split()[0]} good {a} bad {c2}", j.addr)
            elif i.dptr is not None:
                a = symbolize(good, gs, g["reg"], i.dptr)
                c2 = symbolize(bad, bs, b["reg"], j.dptr)
                if a != c2:
                    add("equiv_dptr", n, f"#{i.dptr:04x}->{a} vs #{j.dptr:04x}->{c2}", j.addr)
            elif len(i.raw) == 2 and i.raw[1] != j.raw[1] and "#" in i.text and i.raw[0] == j.raw[0]:
                imm8.append((i.addr, i.raw[1], j.raw[1], j.text, i.text))
            elif len(i.raw) == 3 and i.raw[0] in (0x75, 0x43, 0x53, 0x63, 0xB4, 0xB5, 0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xBB, 0xBC, 0xBD, 0xBE, 0xBF) and i.raw[2] == j.raw[2] and i.raw[1] != j.raw[1] and "#" not in i.text:
                add("equiv_stream", n, f"{i.text} vs {j.text}", j.addr)
            elif len(i.raw) == 3 and "#" in i.text and i.raw[:2] == j.raw[:2]:
                imm8.append((i.addr, i.raw[2], j.raw[2], j.text, i.text))
            else:
                add("equiv_stream", n, f"{i.text} vs {j.text}", j.addr)
        # address halves: pair two differing 8-bit immediates within 16 insns whose (hi,lo) resolve to the same symbol
        cov = set()
        for u in range(len(imm8)):
            for v in range(len(imm8)):
                if u == v or abs(imm8[u][0] - imm8[v][0]) > 40 or imm8[u][0] in cov and imm8[v][0] in cov:
                    continue
                lo, hi = imm8[u], imm8[v]
                gv, bv = hi[1] << 8 | lo[1], hi[2] << 8 | lo[2]
                x = symbolize(good, gs, g["reg"], gv)
                y = symbolize(bad, bs, b["reg"], bv)
                if x and y and x == y:
                    cov.update((lo[0], hi[0]))
        for a_, gb_, bb_, jt, it in imm8:
            if a_ not in cov:
                add("equiv_imm8", n, f"{it} (good) vs {jt} (bad): no address pair resolves identically", a_)
    return F


def asm_const_ptr(im, asm_dir):
    """const_ptr_gptr_xbank from the post-bank asm: `mov a|dptr|rN,#_tK` (K a banked const) followed within 30 lines by the call that
    consumes it; the callee reads generic pointers (calls __gptrget) and lives in another bank than K (and is not common)."""
    F = []
    d = Path(asm_dir)
    if not d.is_dir():
        return F
    where = {c["name"]: c for c in im.chunks if c["kind"] in ("fn", "const")}
    texts = {f: f.read_text(errors="replace").splitlines() for f in sorted(d.glob("*.asm"))}
    reader, bodies = set(), {}
    for f, ls in texts.items():
        cur = None
        for l in ls:
            m = re.match(r"^(_\w+):\s*$", l)
            if m:
                cur = m.group(1)
            elif cur and re.match(r"^\s+[la]call\s+__gptrget", l):
                reader.add(cur)
    imm = re.compile(r"^\s+mov\s+(?:a|dptr|r[0-7]|ar[0-7]),\s*#\(?(_\w+)")
    call = re.compile(r"^\s+[lj]call\s+(?:__bs)?(_\w+)|^\s+ljmp\s+(?:__bs)?(_\w+)")
    for f, ls in texts.items():
        cur = None
        for i, l in enumerate(ls):
            m = re.match(r"^(_\w+):\s*$", l)
            if m:
                cur = m.group(1)
                continue
            m = imm.match(l)
            if not m or cur is None or m.group(1) not in where or where[m.group(1)]["kind"] != "const":
                continue
            k = where[m.group(1)]
            for l2 in ls[i + 1:i + 31]:
                c2 = re.match(r"^\s+lcall\s+(?:__bs)?(_\w+)", l2)
                if c2:
                    cal = c2.group(1)
                    fc = where.get(cal)
                    if cal in reader and fc and fc["reg"] != "C" and k["reg"] != "C" and fc["reg"] != k["reg"]:
                        F.append(dict(kind="const_ptr_gptr_xbank", src=cur, addr=k["addr"],
                                      det=f"{m.group(1)} (bank {k['reg']}) passed to gptr reader {cal} (bank {fc['reg']})"))
                    break
                if re.match(r"^\s+(ret|reti)\b", l2):
                    break
    seen, out = set(), []
    for f in F:                                              # lo and hi byte loads both match
        if (f["src"], f["det"]) not in seen:
            seen.add((f["src"], f["det"])); out.append(f)
    return out


def isr_reach(im):
    """{vector target: set(stub names)} called (directly, through common code) from each interrupt vector."""
    out = {}
    for i in range(3, 0x53, 8):
        if im.img[i] != 0x02:
            continue
        root = im.img[i + 1] << 8 | im.img[i + 2]
        seen, st, hits = set(), [root], set()
        while st:
            a = st.pop()
            c = im.find(0, a)
            if c is None or c["reg"] != "C" or c["addr"] in seen:
                continue
            seen.add(c["addr"])
            if c["kind"] == "stub":
                hits.add(c["name"]); continue
            for x in d8051.disasm(im.code(c), base=c["addr"]):
                if x.text.startswith(("LCALL", "LJMP", "ACALL", "AJMP")) and x.target is not None and x.target < im.common:
                    st.append(x.target)
        out[root] = hits
    return out


ISR_SAVE = {0xE0: "ACC", 0xF0: "B", 0x82: "DPL", 0x83: "DPH", 0xD0: "PSW", **{n: f"R{n}" for n in range(8)}}


def isr_saves(im, a):
    """Registers the ISR at a pushes before its first other insn (`mov psw,#0` allowed); None if it selects a register
    bank other than 0 (__bs_call's push ar1/ar2 address bank 0)."""
    pushed = set()
    for x in d8051.disasm(im.img[a:a + 64], base=a):
        if x.raw[0] == 0xC0:
            pushed.add(x.raw[1]); continue
        if x.raw[:2] == bytes([0x75, 0xD0]):
            if x.raw[2] & 0x18:
                return None
            continue
        break
    return pushed


def isr_findings(im, proven, sw_ok):
    """isr_reach_stub per stub an ISR reaches, unless the ISR saves every register the stub path and its callee can
    clobber (ACC,B,DPL,DPH,PSW,R0-R7, bank 0) and the bank switch routines are proven."""
    F = []
    for root, hits in sorted(isr_reach(im).items()):
        if not hits:
            continue
        name = short(im.find(0, root))
        sv = isr_saves(im, root)
        miss = [] if sv is None else [ISR_SAVE[r] for r in sorted(set(ISR_SAVE) - sv)]
        if sv is not None and not miss and sw_ok:
            proven.append(f"ISR via stub {name}: saves ACC,B,DPL,DPH,PSW,R0-R7 first; {len(hits)} stub(s): {', '.join(sorted(hits))}")
            continue
        why = ("selects a register bank != 0" if sv is None else f"does not save {','.join(miss)}" if miss
               else "bank switch not proven")
        F += [dict(kind="isr_reach_stub", src=name, det=f"{s}: {why}", addr=root) for s in sorted(hits)]
    return F


def xdata_ranges(areas):
    return [(a["addr"], a["addr"] + a["size"]) for a in areas.values() if "XDATA" in a["attr"] and a["size"]]


def run(bin_path, map_path, layout, common, log=print, asm_dir=None):
    im = Image(bin_path, map_path, layout, common, asm_dir)
    xd = xdata_ranges(im.areas)
    log(f"{bin_path}: {len(im.img)} B, {len(im.chunks)} chunks "
        f"({sum(c['kind'] == 'fn' for c in im.chunks)} fn, {sum(c['kind'] == 'const' for c in im.chunks)} const, "
        f"{sum(c['kind'] == 'stub' for c in im.chunks)} stub), kinds from {'.rst ' + str(asm_dir) if im.rst else 'layout' if im.kinds else 'nothing'}, "
        f"xdata {[(hex(a), hex(b)) for a, b in xd]}")
    proven = []
    F = check(im, xd, d8051.load_regnames(), proven)
    if im.unknown:
        F.append(dict(kind="kind_source", src="image", addr=0,
                      det=f"{len(im.unknown)} CH areas have no kind from --asm .rst or --layout, not checked (e.g. {im.unknown[0]})"))
    if im.stale:                                             # one finding: a wrong tree makes every area disagree
        F.append(dict(kind="kind_stale", src="image", addr=0,
                      det=f"{len(im.stale)} CH areas disagree with --asm/.rst or --layout (e.g. {im.stale[0]})"))
    if asm_dir:
        F += asm_const_ptr(im, asm_dir)
    F += isr_findings(im, proven, not switch_proof(im)[1])
    for p in proven:
        log(f"proven {p}")
    return im, F


def key(f):
    return f"{f['kind']}|{f['src']}|{f['det']}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bin", required=True)
    ap.add_argument("--map", required=True)
    ap.add_argument("--layout", default="")
    ap.add_argument("--common", type=lambda x: int(x, 0), default=0x5000)
    ap.add_argument("--against", default="", help="findings file of the good image: print only keys not in it")
    ap.add_argument("--equiv-bin", default="", help="good image of the same source: compare chunk by chunk")
    ap.add_argument("--equiv-map", default="")
    ap.add_argument("--equiv-layout", default="")
    ap.add_argument("--asm", default=str(REPO / "tmp/sdcc-port/asm_bank"),
                    help="post-bank asm dir of THIS image's build (const_ptr_gptr_xbank; skipped when absent)")
    ap.add_argument("--save", default="", help="write finding keys here")
    a = ap.parse_args()
    (REPO / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (REPO / "tmp/logs/fw_link_check.log").open("a")

    def log(s):
        print(s); lf.write(s + "\n"); lf.flush()
    im, F = run(a.bin, a.map, a.layout, a.common, log, a.asm)
    if a.equiv_bin:
        gim = Image(a.equiv_bin, a.equiv_map, a.equiv_layout, a.common)
        F += equiv(gim, im)
    cnt = defaultdict(int)
    for f in F:
        cnt[f["kind"]] += 1
    log("findings by kind: " + (", ".join(f"{k}={v}" for k, v in sorted(cnt.items())) or "none"))
    keys = {key(f) for f in F}
    if a.save:
        Path(a.save).write_text("\n".join(sorted(keys)) + "\n")
    base = set(Path(a.against).read_text().split("\n")) if a.against else set()
    shown = [f for f in F if key(f) not in base]
    for f in sorted(shown, key=lambda f: (f["kind"], f["src"])):
        log(f"{f['kind']:22s} 0x{f['addr']:06x} {f['src']}: {f['det']}")
    bad = shown
    log(f"RESULT: {len(bad)} problem findings{' (not in --against)' if a.against else ''}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
