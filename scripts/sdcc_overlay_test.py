#!/usr/bin/env python3
"""Offline test for sdcc_overlay.py --xparms (plan C8, #11): sibling callees share XDATA PARM slots, a callee's PARMs
sit after its caller's, and a PARM written before another call keeps private storage. Synthetic asm, no compiler."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def fn(name, body, parm=None):
    s = f";------------------------------------------------------------\n; function {name[1:]}\n" \
        f";------------------------------------------------------------\n{name}:\n{body}\tret\n"
    if parm:
        s += f"\t.area XSEG    (XDATA)\n{name}_PARM_4:\n\t.ds {parm}\n\t.area CSEG    (CODE)\n"
    return s


def tree(hazard: bool) -> str:
    call_g = "\tmov\tdptr,#_g_PARM_4\n\tmovx\t@dptr,a\n" + ("\tlcall\t_k\n" if hazard else "") + "\tlcall\t_g\n"
    call_k = "\tmov\tdptr,#_k_PARM_4\n\tmovx\t@dptr,a\n\tlcall\t_k\n"
    return ("\t.module t\n\t.globl _main\n\t.globl _g_PARM_4\n\t.globl _k_PARM_4\n\t.globl _h_PARM_4\n\t.area CSEG    (CODE)\n"
            + fn("_main", call_g + call_k)
            + fn("_g", "\tmov\tdptr,#_h_PARM_4\n\tmovx\t@dptr,a\n\tlcall\t_h\n", 2)
            + fn("_k", "", 1) + fn("_h", "", 1))


def run(hazard: bool):
    with tempfile.TemporaryDirectory() as d:
        src, out = Path(d, "asm"), Path(d, "out")
        src.mkdir()
        (src / "t.asm").write_text(tree(hazard))
        r = subprocess.run([sys.executable, str(HERE / "sdcc_overlay.py"), "--asm", str(src), "--out", str(out), "--xparms"],
                           env=dict(os.environ, AWTO_DDC_REPO=d), capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        rep = json.loads(Path(d, "tmp/sdcc-port/overlay.json").read_text())
        return rep, (out / "t.asm").read_text()


def main():
    rep, asm = run(False)
    assert rep["overlay_block"]["x"] == 3, rep          # g (2) and k (1) share offset 0; h after g at 2
    assert "#(__xovl + 0x0)" in asm and "#(__xovl + 0x2)" in asm and "_g_PARM_4" not in asm, asm
    rep, asm = run(True)
    assert rep["parm_hazard_fns"] == ["_g"], rep        # g's PARM written, then k called first: g keeps its own slot
    print("PASS sdcc_overlay_test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
