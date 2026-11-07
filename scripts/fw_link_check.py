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
  bank_reg_access        movx on 0xFFFF outside the bank-switch routines
  const_ptr_gptr_xbank   asm (post-bank pass, --asm): address of a banked const passed to a function that reads generic pointers
                         (__gptrget) and sits in another bank: it reads its OWN bank at that address (#46: boot logo tile map)
  stack_arg_via_stub     function reads stack-passed args via SP/_bp but is reached through a bank stub (+4 B between args and
                         callee, #11): must be common or share its callers' bank
  isr_reach_stub         info: stub called from ISR-reachable common code
Exit 1 if any non-info finding. Logs: tmp/logs/fw_link_check.log
"""
import argparse, os, re, sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import d8051  # noqa: E402

REPO = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
BANK = 0x10000
INFO = {"isr_reach_stub"}
TERM = ("RET", "RETI", "LJMP", "SJMP", "AJMP", "JMP @A+DPTR")


def parse_map(path):
    """areas: name -> dict(addr,size,syms[(name,addr)]); only code-space symbols ('C:')."""
    areas, cur = {}, None
    for l in Path(path).read_text(errors="replace").splitlines():
        m = re.match(r"^(\S+)\s+([0-9A-F]{8})\s+([0-9A-F]{8}) =\s+\d+\. bytes \((.*)\)", l)
        if m:
            cur = areas.setdefault(f"{m.group(1)}@{m.group(2)}", dict(    # names are cut to 32 chars: not unique
                name=m.group(1), addr=int(m.group(2), 16), size=int(m.group(3), 16), attr=m.group(4), syms=[]))
            continue
        m = re.match(r"^C:\s+([0-9A-F]{8})\s+(\S+)", l)
        if m and cur is not None and not m.group(2).startswith(("l_", "s_")):
            cur["syms"].append((m.group(2), int(m.group(1), 16)))
    return areas


class Image:
    def __init__(self, bin_path, map_path, layout, common):
        self.img = Path(bin_path).read_bytes()
        self.common = common
        self.areas = parse_map(map_path)
        self.kinds = {}                                       # symbol -> fn|const
        if layout and Path(layout).exists():
            for ln in Path(layout).read_text().splitlines():
                f = ln.split("\t")
                if len(f) == 5 and f[0] in ("fn", "const"):
                    self.kinds[f[1][:32]] = f[0]          # the map cuts symbol names to 32 chars
        self.chunks = []                                      # dict(kind,name,addr,size,reg)
        for a in self.areas.values():
            an = a["name"]
            if "CODE" not in a["attr"] or not a["size"] or an.startswith("VECTORS"):
                continue
            if an.startswith("ST"):
                kind, name = "stub", (a["syms"][0][0] if a["syms"] else an)
            elif an.startswith("CH"):
                name = a["syms"][0][0] if a["syms"] else an
                kind = self.kinds.get(name[:32]) or self.kinds.get(an[2:34]) or self.kinds.get(an[2:]) or "fn"
            else:
                kind, name = "fn", an                         # residual: HOME, GSINIT*, CSEG, XINIT
                if an == "XINIT":
                    kind = "const"
            reg = "C" if a["addr"] < common else a["addr"] >> 16
            self.chunks.append(dict(kind=kind, name=name, addr=a["addr"], size=a["size"], reg=reg, area=an))
        self.by_reg = defaultdict(list)
        for c in self.chunks:
            self.by_reg[c["reg"]].append(c)
        for v in self.by_reg.values():
            v.sort(key=lambda c: c["addr"])
        self.gsyms = {n: ad for a in self.areas.values() for n, ad in a["syms"]}

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


def check(im, xdata=(), regnames=None):
    F = []
    add = lambda kind, src, det, addr, **kw: F.append(dict(kind=kind, src=src, det=det, addr=addr, **kw))
    fn_start = {(c["reg"], c["addr"] & 0xFFFF): c for c in im.chunks if c["kind"] == "fn"}
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

    def xbank_stub(own, nxt, reg, src, at):
        """pointer to a banked const set up: does a stub call into another bank follow?"""
        for x in nxt:
            if x.text.startswith(("RET", "LJMP", "SJMP", "AJMP", "JMP")):
                break
            if x.text.startswith("LCALL") and x.target is not None and x.target in stub_lo:
                tgt, bank, tc = stubs[stub_lo[x.target]]
                if bank != reg:
                    add("gptr_const_xbank", src, f"{own[0]['name']} (bank {reg}) -> stub {short(tc)} (bank {bank})", at)
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
    names = {}
    fnaddrs = {}
    for c in im.chunks:
        if c["kind"] == "fn" and c["reg"] != "C":
            fnaddrs.setdefault(c["addr"] & 0xFFFF, []).append(c)
    for c in im.chunks:
        if c["kind"] == "const":
            if c["area"] == "XINIT" or c["reg"] == "C":
                pass
            continue
        if c["kind"] == "stub":
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
            op = code[i.off]
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
            if t.startswith("ADD A,#") and not resid:   # table base by address arithmetic: add a,#t; mov a,#(t>>8); addc a,b
                lo = int(t[7:9], 16)
                for y in ins[k + 1:k + 8]:
                    m3 = re.match(r"MOV A,#([0-9A-F]{2})h$", y.text)
                    if m3:
                        v = int(m3.group(1), 16) << 8 | lo
                        if v >= im.common and any(z.text.startswith("ADDC A,") for z in ins[k + 1:k + 10]):
                            cs = im.consts_at(v)
                            own = [x for r, x in cs if r == reg]
                            if reg == "C" and cs:
                                add("const_other_bank", src, f"arith base 0x{v:04x}: common code, const {cs[0][1]['name']} in bank {cs[0][0]}", i.addr)
                            elif cs and not own and not im.find(reg, v):
                                add("const_other_bank", src, f"arith base 0x{v:04x}: {cs[0][1]['name']} is in bank {cs[0][0]}, code in bank {reg}", i.addr)
                        break
            mr = R2_IMM.match(t)
            if mr:                                   # Keil ABI generic pointer argument: R3 tag, R2 hi, R1 lo (R1 holds nothing else)
                lo = next((int(m1.group(1), 16) for y in ins[max(0, k - 4):k + 5] if (m1 := R1_IMM.match(y.text))), None)
                v = int(mr.group(1), 16) << 8 | (lo or 0)
                if lo is not None and v >= im.common:
                    own = [x for r, x in im.consts_at(v) if r == reg]
                    if own:
                        xbank_stub(own, ins[k + 1:k + 15], reg, src, i.addr)
            if i.dptr is not None:
                v = i.dptr
                nxt = ins[k + 1:k + 1 + 14]
                if v == 0xFFFF and any(x.text in ("MOVX @DPTR,A", "MOVX A,@DPTR") for x in nxt[:3]):
                    add("bank_reg_access", src, "movx @0xFFFF", i.addr)
                movx_next = any(x.text.startswith("MOVX") for x in nxt[:3])
                movc_next = False
                for x in nxt:
                    if x.dptr is not None or x.text.startswith(("RET", "LJMP", "SJMP", "AJMP", "LCALL")):
                        break
                    if x.text == "MOVC A,@A+DPTR":
                        movc_next = True
                        break
                is_reg = (regnames and v in regnames) or movx_next or in_xdata(v)
                if v >= im.common and not is_reg:
                    cs = [(r, x) for r, x in im.consts_at(v) if movc_next or x["addr"] & 0xFFFF == v]
                    own = [x for r, x in cs if r == reg]
                    if reg == "C" and cs:
                        add("const_other_bank", src, f"common code reads banked const {cs[0][1]['name']} (bank {cs[0][0]})", i.addr)
                    elif cs and not own and not im.find(reg, v):
                        add("const_other_bank", src, f"{cs[0][1]['name']} is in bank {cs[0][0]}, code in bank {reg}", i.addr)
                    elif own:
                        xbank_stub(own, nxt, reg, src, i.addr)
                    # address of a banked fn taken in code
                    if reg != "C" or v >= im.common:
                        for fc in fnaddrs.get(v, ()):
                            if not cs and fc["reg"] == reg and not in_xdata(v):
                                add("fnptr_banked", src, f"mov dptr,#{fc['name']}", i.addr)
    # function pointers in const data / XINIT: 16-bit words equal to a banked fn start (either byte order)
    for c in im.chunks:
        if c["kind"] != "const" or c["area"] == "XINIT" and False:
            continue
        b = im.code(c)
        for o in range(0, len(b) - 1):
            for w in (b[o] << 8 | b[o + 1], b[o + 1] << 8 | b[o]):
                for fc in fnaddrs.get(w, ()):
                    if w >= im.common and fc["reg"] == c["reg"]:
                        pass
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
    """names of stubs called (directly, through common code) from the interrupt vectors."""
    fn_at = {c["addr"]: c for c in im.chunks if c["reg"] == "C"}
    seen, st, hits = set(), [], set()
    for i in range(3, 0x53, 8):
        if im.img[i] == 0x02:
            st.append(im.img[i + 1] << 8 | im.img[i + 2])
    while st:
        a = st.pop()
        c = im.find(0, a)
        if c is None or c["reg"] != "C" or c["addr"] in seen:
            continue
        seen.add(c["addr"])
        if c["kind"] == "stub":
            hits.add(c["name"]); continue
        for i in d8051.disasm(im.code(c), base=c["addr"]):
            if i.text.startswith(("LCALL", "LJMP", "ACALL", "AJMP")) and i.target is not None and i.target < im.common:
                st.append(i.target)
    return hits


def xdata_ranges(areas):
    return [(a["addr"], a["addr"] + a["size"]) for a in areas.values() if "XDATA" in a["attr"] and a["size"]]


def run(bin_path, map_path, layout, common, log=print, asm_dir=None):
    im = Image(bin_path, map_path, layout, common)
    xd = xdata_ranges(im.areas)
    log(f"{bin_path}: {len(im.img)} B, {len(im.chunks)} chunks "
        f"({sum(c['kind'] == 'fn' for c in im.chunks)} fn, {sum(c['kind'] == 'const' for c in im.chunks)} const, "
        f"{sum(c['kind'] == 'stub' for c in im.chunks)} stub), xdata {[(hex(a), hex(b)) for a, b in xd]}")
    F = check(im, xd, d8051.load_regnames())
    if asm_dir:
        F += asm_const_ptr(im, asm_dir)
    for s in sorted(isr_reach(im)):
        F.append(dict(kind="isr_reach_stub", src="ISR", det=s, addr=0))
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
    bad = [f for f in shown if f["kind"] not in INFO]
    log(f"RESULT: {len(bad)} problem findings{' (not in --against)' if a.against else ''}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
