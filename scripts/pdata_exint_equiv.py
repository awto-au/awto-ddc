#!/usr/bin/env python3
"""Proof for #328: the pData_EXINT -> local rewrite changed nothing else.

usage: pdata_exint_equiv.py [--old-ref REF]   (default origin/main)
  Per rewritten function: NEW text with the local names mapped back to pData_EXINT[k] and the added declaration dropped must
  equal OLD text from REF. Tp1Check / Tp2Check are also covered by tp_check_equiv.py (gcc, CRC of every side effect).
Log: ./tmp/logs/pdata_exint_equiv.log
"""

import argparse
import re
import subprocess
import sys

from _log import log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/pdata_exint_equiv.log"
B = "fw/sdk/Kernel/Scaler/"
JOBS = [
    (B + "ScalerFunction/Code/ScalerDPRx1_INT_SeptPhy.c", [
        ("void ScalerDpRx1HDCPResetDpcdInfo_EXINT0(void)", {"ucIndex": 0}, ["BYTE ucIndex;"]),
        ("void ScalerDpRx1HDCPSetKsvFifo_EXINT0(void)", {"ucIndex": 0}, ["BYTE ucIndex;"]),
        ("BYTE ScalerDpRx1Tp1Check_EXINT0(", {"ucIndex": 0}, ["BYTE ucIndex;"]),
        ("BYTE ScalerDpRx1Tp2Check_EXINT0(", {}, ["BYTE pucLevel[4];"]),
        ("BYTE ScalerDpRx1CheckSourceOUI_EXINT0(", {"ucIndex": 0}, ["BYTE ucIndex;"])]),
    (B + "ScalerCommonFunction/Code/ScalerCommonDPRx1.c", [("void ScalerDpRx1MstReset_EXINT0(void)", {"ucIndex": 0}, ["BYTE ucIndex;"])]),
    (B + "RL6449_Series_Scaler/Code/RL6449_Series_DP_INT.c", [
        ("BYTE ScalerDpAuxJudgeHandler_EXINT0(void)", {"ucLength": 1, "ucAddress": 2}, ["BYTE ucLength;", "BYTE ucAddress;"])]),
    (B + "ScalerFunction/Code/ScalerDP_SeptPhy.c", [("void ScalerDpMstReset_EXINT0(", {"ucIndex": 0}, ["BYTE ucIndex;"])]),
    (B + "ScalerFunction/Code/ScalerDPRx1_SeptPhy.c", [("void ScalerDpRx1CpIRQ_EXINT0(", {"ucCpIrq": 0}, ["BYTE ucCpIrq;"])]),
]


def body(lines, sig):
    s = [i for i, ln in enumerate(lines) if ln.startswith(sig) and not ln.rstrip().endswith(";")]
    assert len(s) == 1, sig
    e = next(i for i in range(s[0], len(lines)) if lines[i] == "}")
    return lines[s[0]:e + 1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--old-ref", default="origin/main")
    a = ap.parse_args()
    bad = 0
    for path, fns in JOBS:
        old = subprocess.run(["git", "show", f"{a.old_ref}:{path}"], capture_output=True, text=True, check=True, cwd=ROOT).stdout.split("\n")
        new = (ROOT / path).read_text().split("\n")
        for sig, names, decls in fns:
            o, n = body(old, sig), body(new, sig)
            n = [ln for ln in n if ln.strip() not in decls]
            n = [re.sub(r"\bpucLevel\b", "pData_EXINT", ln) if not names else ln for ln in n]
            for nm, k in names.items():
                n = [re.sub(r"\b" + nm + r"\b", f"pData_EXINT[{k}]", ln) for ln in n]
            ok = o == n
            bad += not ok
            log_line(f"{path.split('/')[-1]} {sig}: {'EQUAL' if ok else 'MISMATCH'}", LOG, stamp_stdout=False)
            print(sig, "EQUAL" if ok else "MISMATCH")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
