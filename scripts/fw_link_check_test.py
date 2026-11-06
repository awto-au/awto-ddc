#!/usr/bin/env python3
"""Offline tests for fw_link_check.py on a synthetic 2-bank image (no firmware build needed)."""
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


def main():
    ok = run(bytes([0x12, 0x50, 0x00, 0x22]))                # common calls banked 0x5000 directly
    assert "call_common_to_banked" in ok, ok
    assert "stack_arg_via_stub" in ok, ok                    # _a reads SP and has a stub
    clean = run(bytes([0x12, 0x02, 0x00, 0x22]))              # common calls the stub at 0x0200: fine
    assert "call_common_to_banked" not in clean, clean
    print("PASS fw_link_check_test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
