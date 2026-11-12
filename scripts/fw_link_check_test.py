#!/usr/bin/env python3
"""Offline tests for fw_link_check.py on synthetic 2-bank images (no firmware build needed)."""
import sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_link_check as L  # noqa: E402

MAP = """Area                                    Addr        Size        Decimal Bytes (Attributes)
--------------------------------        ----        ----        ------- ----- ------------
CH_a                                00005000    00000002 =           2. bytes (REL,CON,CODE)
C:   00005000  _a
CH_b                                00015000    00000001 =           1. bytes (REL,CON,CODE)
C:   00015000  _b
CH_c                                00000100    00000004 =           4. bytes (REL,CON,CODE)
C:   00000100  _c
ST_a                                00000200    00000006 =           6. bytes (REL,CON,CODE)
C:   00000200  __bs_a
"""


def build(extra_c):
    img = bytearray(b"\xff" * 0x20000)
    img[0x5000:0x5002] = bytes([0xE5, 0x81])                 # bank 0 _a: MOV A,SP (reads stack args)
    img[0x15000] = 0x22                                      # bank 1 _b: RET
    img[0x100:0x104] = extra_c                               # common _c
    img[0x200:0x206] = bytes([0x12, 0x00, 0x50, 0x00, 0x50, 0x00])   # stub: lcall x; target 0x5000 bank 0
    return bytes(img)


def run(extra_c):
    with tempfile.TemporaryDirectory() as d:
        b, m, lay = Path(d, "i.bin"), Path(d, "i.map"), Path(d, "l.tsv")
        b.write_bytes(build(extra_c)); m.write_text(MAP)
        lay.write_text("fn\t_a\t0\t0x0000\t8\nfn\t_b\t1\t0x0000\t8\nfn\t_c\tC\t0x0100\t8\n")
        _, F = L.run(b, m, lay, 0x5000, log=lambda s: None)
    return {f["kind"] for f in F}


MAP_K = MAP.replace("00015000    00000001 =           1.", "00015000    0000000A =          10.") + """CH_k                                00016000    00000004 =           4. bytes (REL,CON,CODE)
C:   00016000  _k
ST_b                                00000210    00000008 =           8. bytes (REL,CON,CODE)
C:   00000210  __bs_b
"""


def run_keil(tag_bank):
    """bank-1 fn passes a bank-1 const as a Keil generic pointer (R1 lo, R2 hi, R3 tag) through an 8 B stub to bank `tag_bank`."""
    img = bytearray(build(bytes([0x22, 0x22, 0x22, 0x22])))
    img[0x15000:0x1500a] = bytes([0x79, 0x00, 0x7A, 0x60, 0x7B, 0x80, 0x12, 0x02, 0x10, 0x22])  # mov r1/r2/r3; lcall __bs_b; ret
    img[0x210:0x218] = bytes([0x78, tag_bank, 0x90, 0x50, 0x00, 0x02, 0x02, 0x78])               # mov r0,#bank; mov dptr; ljmp
    with tempfile.TemporaryDirectory() as d:
        b, m, lay = Path(d, "i.bin"), Path(d, "i.map"), Path(d, "l.tsv")
        b.write_bytes(bytes(img)); m.write_text(MAP_K)
        lay.write_text("fn\t_a\t0\t0x0000\t8\nfn\t_b\t1\t0x0000\t16\nfn\t_c\tC\t0x0100\t8\nconst\t_k\t1\t0x1000\t4\n")
        _, F = L.run(b, m, lay, 0x5000, log=lambda s: None)
    return {f["kind"] for f in F}


# --- .rst-driven image: bank switch routines, a bank reader, a DMA callee, an ISR --------------------------------
def area(name, addr, size):
    return f"{name:<36s}{addr:08X}    {size:08X} = {size:11d}. bytes (REL,CON,CODE)\n"


class Img:
    """Synthetic image + map + .rst: add(name, addr, bytes, src lines, kind) places a CH area (or a residual CSEG)."""

    def __init__(self):
        self.img = bytearray(b"\xff" * 0x20000)
        self.map = "Area    Addr    Size    Decimal Bytes (Attributes)\n"
        self.rst, self.n = [], 1

    def line(self, src, a=None, raw=b""):
        hx = (f"{a:06X}" if a is not None else " " * 6) + "".join(f" {x:02X}" for x in raw)
        self.rst.append(f"      {hx:<26s}  {self.n:5d} {src}"); self.n += 1

    def add(self, name, a, insns, data=False, area_kind="CH", params="void"):
        """insns: [(bytes, src)]; data=True writes `.db` lines (a const area)."""
        size = sum(len(b) for b, _ in insns)
        an = f"CH_{name[1:]}" if area_kind == "CH" else area_kind
        self.map += area(an, a, size) + f"C:   {a:08X}  {name}\n"
        self.line(f"\t.area {an}    (CODE)")
        if not data:
            self.line(f";\t/t/x.c:1: void {name[1:]}({params})")       # C signature comment
        self.line(f"{name}:", a)
        p = a
        for b, s in insns:
            self.img[p:p + len(b)] = b
            self.line(f"\t.db {', '.join(hex(x) for x in b)}" if data else f"\t{s}", p, b)
            p += len(b)

    def files(self, d):
        b, m, asm = Path(d, "i.bin"), Path(d, "i.map"), Path(d, "asm")
        asm.mkdir()
        b.write_bytes(bytes(self.img)); m.write_text(self.map); (asm / "x.rst").write_text("\n".join(self.rst) + "\n")
        return b, m, asm


def switch(im, good=True):
    """common __bs_call/__bs_ret at 0x400 (fw/sdcc/bank.asm shape); good=False writes 0xFFFF before __bs_cur."""
    call = [(b"\x88\x14", "mov __bs_cur,r0"), (b"\xa9\x82", "mov r1,dpl"), (b"\x90\xff\xff", "mov dptr,#0xFFFF"),
            (b"\xe8", "mov a,r0"), (b"\xf0", "movx @dptr,a")]
    if not good:
        call = [call[2], call[3], call[4], call[0], call[1]]
    ret = [(b"\x89\x14", "mov __bs_cur,r1"), (b"\x90\xff\xff", "mov dptr,#0xFFFF"), (b"\xe9", "mov a,r1"), (b"\xf0", "movx @dptr,a")]
    tail = [(b"\x22", "ret")]
    body = call + tail + ret + tail
    p = 0x400
    for b, _ in body:
        im.img[p:p + len(b)] = b; p += len(b)
    n1 = sum(len(b) for b, _ in call)
    n2 = n1 + 1 + sum(len(b) for b, _ in ret)
    im.map += area("CSEG", 0x400, p - 0x400) + "".join(
        f"C:   {a:08X}  {s}\n" for s, a in (("__bs_call", 0x400), ("__bs_call_sw", 0x400 + n1), ("__bs_ret", 0x400 + n1 + 1),
                                           ("__bs_ret_sw", 0x400 + n2)))
    im.map += "     00000014  __bs_cur                           awto_bank\n"


def stub(im, name, a, target, bank):
    """9 B stub: mov r0,#bank; mov r1,#lo; mov r2,#hi; ljmp __bs_call."""
    b = bytes([0x78, bank, 0x79, target & 0xFF, 0x7A, target >> 8, 0x02, 0x04, 0x00])
    im.img[a:a + 9] = b
    im.map += area(f"ST_{name}", a, 9) + f"C:   {a:08X}  __bs_{name}\n"


def bank_image(table_bank=1, literal=False, callee_movc=False, isr_push_all=True, switch_ok=True, ret_ffff=False,
               ptr_caller=False):
    """bank-1 _r: reads 0xFFFF, loads const _k (bank table_bank), calls _v (bank 0) through a stub; ISR at vector 0x03
    calls the stub too. literal=True writes the const address as a number in the .rst. ptr_caller: _r takes a pointer
    and a bank-0 caller passes its own bank-0 const (the DMA would read it with bank number 1)."""
    im = Img()
    switch(im, switch_ok)
    k16 = 0x6000
    im.add("_k", (table_bank << 16) | k16, [(b"\x01\x02\x03\x04", "")], data=True)
    stub(im, "v", 0x300, 0x5100, 0)
    rd = [(b"\x90\xff\xff", "mov dptr,#_MCU_FFFF_PBANK_SWITCH"), (b"\xe0", "movx a,@dptr"), (b"\xf5\xf0", "mov b,a")]
    if ret_ffff:
        rd = [(b"\x90\xff\xff", "mov dptr,#0xffff"), (b"\x22", "ret")]
    im.add("_r", 0x15000, rd + [(bytes([0x90, k16 >> 8, k16 & 0xFF]), "mov dptr,#0x6000" if literal else "mov dptr,#_k"),
                               (b"\x12\x03\x00", "lcall __bs_v"), (b"\x22", "ret")],
           params="BYTE *pucArray" if ptr_caller else "void")
    if ptr_caller:
        im.add("_k0", 0x7000, [(b"\x05\x06", "")], data=True)
        stub(im, "r", 0x320, 0x5000, 1)
        im.add("_cl", 0x5200, [(b"\x90\x70\x00", "mov dptr,#_k0"), (b"\x12\x03\x20", "lcall __bs_r"), (b"\x22", "ret")])
    im.add("_v", 0x5100, ([(b"\x93", "movc a,@a+dptr")] if callee_movc else []) + [(b"\x22", "ret")])
    pushes = [0xE0, 0xF0, 0x82, 0x83, 0xD0] + list(range(8 if isr_push_all else 3))
    isr = b"".join(bytes([0xC0, r]) for r in pushes) + b"\x12\x03\x00" + b"\x32"
    im.add("_isr", 0x100, [(isr, "isr")])
    im.img[3:6] = bytes([0x02, 0x01, 0x00])                  # vector 0x03 -> ljmp _isr
    with tempfile.TemporaryDirectory() as d:
        b, m, asm = im.files(d)
        proven = []
        _, F = L.run(b, m, "", 0x5000, log=lambda s: proven.append(s), asm_dir=asm)
    return {f["kind"] for f in F}, [p for p in proven if p.startswith("proven")]


def main():
    ok = run(bytes([0x12, 0x50, 0x00, 0x22]))                # common calls banked 0x5000 directly
    assert "call_common_to_banked" in ok, ok
    assert "stack_arg_via_stub" in ok, ok                    # _a reads SP and has a stub
    clean = run(bytes([0x12, 0x02, 0x00, 0x22]))              # common calls the stub at 0x0200: fine
    assert "call_common_to_banked" not in clean, clean
    assert "stub_bad_target" not in clean, clean
    # stub forms: 6 B lcall + data, 9 B mov r0/r1/r2 + ljmp (SDCC 0-2), 8 B mov r0 + mov dptr + ljmp (Keil ABI, --sdcccall 3)
    assert L.stub_target(bytes([0x12, 0x00, 0x50, 0x34, 0x92, 0x03])) == (0x9234, 3)
    assert L.stub_target(bytes([0x78, 0x05, 0x79, 0x34, 0x7A, 0x92, 0x02, 0x02, 0x78])) == (0x9234, 5)
    assert L.stub_target(bytes([0x78, 0x07, 0x90, 0x92, 0x34, 0x02, 0x02, 0x78])) == (0x9234, 7)
    assert L.stub_target(bytes([0x78, 0x07, 0x90, 0x92, 0x34, 0x12, 0x02, 0x78])) is None    # lcall, not ljmp
    assert "gptr_const_xbank" in run_keil(0), "Keil gptr to a bank-1 const through a stub into bank 0 not flagged"
    assert "gptr_const_xbank" not in run_keil(1)              # callee in the const's own bank: fine

    # .rst image: every proof holds -> no finding, one `proven` line per proof
    F, P = bank_image()
    assert not F, F
    assert sum(p.startswith("proven bank switch") for p in P) == 2, P
    assert any(p.startswith("proven bank read") for p in P), P
    assert any(p.startswith("proven DMA callee") for p in P), P
    assert any(p.startswith("proven ISR via stub") for p in P), P
    # each proof broken on its own
    F, _ = bank_image(table_bank=0)                           # table not in the reader's bank (the DMA would read bank 1)
    assert "bank_reg_access" in F and "const_other_bank" in F, F
    F, _ = bank_image(callee_movc=True)                       # callee reads code in ITS bank: the #16 class
    assert F == {"gptr_const_xbank"}, F
    F, _ = bank_image(isr_push_all=False)                     # ISR does not save R3-R7 before reaching a stub
    assert F == {"isr_reach_stub"}, F
    F, _ = bank_image(switch_ok=False)                        # 0xFFFF written before __bs_cur
    assert "bank_reg_access" in F and "isr_reach_stub" in F, F
    F, P = bank_image(ptr_caller=True)                        # pointer param: the caller's tables count too
    assert "bank_reg_access" in F, (F, P)
    # literal immediate = a value: no const check (bank 0 has no const at 0x6000 seen from bank 1)
    F, _ = bank_image(table_bank=0, literal=True)
    assert "const_other_bank" not in F, F
    # `mov dptr,#0xffff; ret` (WORD return value) is not a bank register access
    F, P = bank_image(ret_ffff=True)
    assert "bank_reg_access" not in F and not any("bank read" in p for p in P), (F, P)
    # kinds: the const area is data (never disassembled); a wrong .rst address = kind_stale; no source = kind_source
    im = Img()
    im.add("_t", 0x15000, [(b"\x12\x50\x00\x02", "")], data=True)         # bytes that decode as lcall 0x5000; ljmp
    im.add("_f", 0x16000, [(b"\x22", "ret")])
    with tempfile.TemporaryDirectory() as d:
        b, m, asm = im.files(d)
        _, F = L.run(b, m, "", 0x5000, log=lambda s: None, asm_dir=asm)
        assert not F, F
        _, F = L.run(b, m, "", 0x5000, log=lambda s: None, asm_dir=None)
        assert {f["kind"] for f in F} == {"kind_source"}, F
        (asm / "x.rst").write_text((asm / "x.rst").read_text().replace("016000", "016004"))
        _, F = L.run(b, m, "", 0x5000, log=lambda s: None, asm_dir=asm)
        assert "kind_stale" in {f["kind"] for f in F}, F
    # arith table base (add a,#lo; mov a,#hi; addc a,..): an xdata symbol in the .rst is not the bank-0 const at that address
    for sym, want in (("_g_x", set()), ("_t0", {"const_other_bank"})):
        im = Img()
        im.add("_t0", 0xF512, [(b"\x01\x02", "")], data=True)
        im.add("_f", 0x16000, [(b"\x24\x12", f"add a,#{sym}"), (b"\x74\xf5", f"mov a,#({sym} >> 8)"),
                               (b"\x35\xf0", "addc a,b"), (b"\x22", "ret")])
        with tempfile.TemporaryDirectory() as d:
            b, m, asm = im.files(d)
            _, F = L.run(b, m, "", 0x5000, log=lambda s: None, asm_dir=asm)
        assert {f["kind"] for f in F} == want, (sym, F)
    print("PASS fw_link_check_test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
