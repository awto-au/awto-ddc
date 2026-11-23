#!/usr/bin/env python3
"""Measure how many 4 KiB flash sectors a small source edit changes with the compact layout (awto-ddc#12, #44).

usage: flash_layout_measure.py [--serial AWT26110003] [--layout fw/bank_map.tsv] [--edits panel,osd,scaler,main]
  Needs AWTO_SDCC_BIN / AWTO_SDCC_BE=1 in the environment (as for fw_build.py).
  Per edit: build with the edit applied via fw_build.py --src-patch (a copy of the bank map, so the tracked one stays),
  diff against the unedited build (SHA-256 per sector; shorter image padded with 0xFF).
  Counts: all changed sectors; of which common-area sectors (copied into every bank); banks touched.
Log: tmp/logs/flash_layout_measure.log, result tmp/meas/result.json, images tmp/meas/<tag>.bin
"""
import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import chip_mem as CM
from _log import Logger

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root

ROOT = repo_root()
SECTOR, BANK = 4096, 0x10000
COMMON_SECTORS = -(-CM.COMMON_END // SECTOR)       # sectors of each bank image that are the common copy
BUILD_TIMEOUT = 600          # full build ~100 s cold (port 15 s, compile ~70 s, link ~5 s); 3x + margin, awto-dan#53
EDITS = {
    "panel": [{"file": "Panel/AWTO_M280DCA_E3B.h", "old": "_PANEL_DH_START                         48",
               "new": "_PANEL_DH_START                         50"}],
    "osd": [{"file": "User/RTD Series/RTD2014Osd/Code/RTD2014OsdFunc.c",
             "old": "void OsdFuncEnableOsd(void)\n{\n    ScalerOsdEnableOsd();",
             "new": "void OsdFuncEnableOsd(void)\n{\n    ScalerOsdEnableOsd(); ScalerOsdEnableOsd();"}],
    "scaler": [{"file": "Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_Global.c",
                "old": "        // Select at internal Xtal.\n        ScalerSetBit(P0_09_GA_POWER_CTRL, ~_BIT3, _BIT3);",
                "new": "        // Select at internal Xtal.\n        ScalerSetBit(P0_09_GA_POWER_CTRL, ~_BIT3, _BIT3); ScalerTimerDelayXms(1);"}],
    "main": [{"file": "Kernel/System/Code/SysMain.c",
              "old": "        AwtoDiagInit();\n        AwtoMeasInit();",
              "new": "        AwtoDiagInit(); AwtoDiagInit();\n        AwtoMeasInit();"}],
}
LOG = None


def log(s):
    LOG.say(s)


def build(serial, tag, layout=None, edit=None):
    """dev.py build (it sets the env fw_build needs: ISR libs, compiler); the image is tmp/fw/<serial>-<tag>-be.bin."""
    meas = ROOT / "tmp/meas"
    cmd = [sys.executable, "dev.py", "build", "--serial", serial, "--tag", tag]
    fw = []
    if layout:
        fw += ["--layout", str(layout)]
    if edit:
        pf = meas / f"patch_{edit}.json"
        pf.write_text(json.dumps(EDITS[edit]))
        fw += ["--src-patch", str(pf)]
    if fw:
        cmd += [f"--fw-args={' '.join(fw)}"]
    log(f"build {tag}: {' '.join(cmd[1:])}")
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=BUILD_TIMEOUT, check=False)
    (meas / f"{tag}.build.log").write_text(r.stdout + r.stderr)
    if r.returncode:
        sys.exit(f"build {tag} failed rc={r.returncode}: {(r.stdout + r.stderr)[-1500:]}")
    img = meas / f"{tag}.bin"
    shutil.copy(ROOT / "tmp/fw" / f"{serial}-{tag}-be.bin", img)
    shutil.copy(ROOT / "tmp/fw" / f"{serial}-{tag}-be.map", meas / f"{tag}.map")
    return img


def sectors(img: bytes, n):
    img = img + b"\xff" * (n * SECTOR - len(img))
    return [hashlib.sha256(img[i:i + SECTOR]).hexdigest() for i in range(0, n * SECTOR, SECTOR)]


def diff(a: Path, b: Path):
    x, y = a.read_bytes(), b.read_bytes()
    n = (max(len(x), len(y)) + SECTOR - 1) // SECTOR
    sx, sy = sectors(x, n), sectors(y, n)
    ch = [i for i in range(n) if sx[i] != sy[i]]
    per = BANK // SECTOR
    return {"sectors": len(ch), "total": n, "common": sum(1 for i in ch if i % per < COMMON_SECTORS),
            "banks": sorted({i // per for i in ch})}


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="AWT26110003")
    ap.add_argument("--layout", default="fw/bank_map.tsv")
    ap.add_argument("--edits", default=",".join(EDITS))
    a = ap.parse_args()
    meas = ROOT / "tmp/meas"
    meas.mkdir(parents=True, exist_ok=True)
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = Logger(ROOT / "tmp/logs/flash_layout_measure.log")
    lay0 = ROOT / a.layout
    res = {}

    def newbuild(tag, edit=None):
        lp = ROOT / "fw" / f"bank_map_{tag}.tsv"             # under fw/ (the build refuses tmp/); promoted onto, so a copy
        shutil.copy(lay0, lp)                                # every run starts from the same committed bank map
        try:
            return build(a.serial, tag, lp, edit)
        finally:
            lp.unlink(missing_ok=True)

    base = newbuild("base")
    res["baseline"] = {"bytes": base.stat().st_size}
    for e in a.edits.split(","):
        res[e] = diff(base, newbuild(f"edit_{e}", e))
        log(f"edit {e}: {res[e]}")
    (meas / "result.json").write_text(json.dumps(res, indent=1))
    log("| edit | sectors | common sectors | banks touched |")
    for e in a.edits.split(","):
        r = res[e]
        log(f"| {e} | {r['sectors']}/{r['total']} | {r['common']} | {r['banks']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
