"""fw_stack.py on a call cycle (#174): the cycle branch returned a bare 0, the caller unpacked it (TypeError)."""
import json
import os
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ASM = """; function main
_main:
\tlcall _a
\tret
; function a
_a:
\tlcall _b
\tret
; function b
_b:
\tlcall _a
\tret
; function isr
_isr:
\tpush acc
\tlcall _a
\tpop acc
\treti
"""


def test_cycle_reported_not_crashing(tmp_path):
    asm = tmp_path / "asm"
    asm.mkdir()
    (asm / "x.asm").write_text(ASM)
    r = subprocess.run([sys.executable, str(SCRIPTS / "fw_stack.py"), "--asm", str(asm)],
                       env={**os.environ, "AWTO_DDC_REPO": str(tmp_path)}, capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    assert "TypeError" not in r.stderr
    res = json.loads(r.stdout)
    assert res["cycles"] == ["_a"], res
    assert res["main"] > 0 and res["total"] > res["main"], res
