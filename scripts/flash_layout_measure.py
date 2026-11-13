#!/usr/bin/env python3
"""Measure how many 4 KiB flash sectors a small source edit changes, legacy packing vs sticky layout (awto-ddc#12).

usage: flash_layout_measure.py [--serial AWT26110003] [--layout fw/bank_layout.tsv] [--edits panel,osd,scaler]
  Needs AWTO_SDCC_BIN / AWTO_SDCC_BE=1 in the environment (as for fw_build.py).
  Per edit: build old (no layout) and new (copy of --layout) with the edit applied via fw_build.py --src-patch,
  diff each against its own unedited baseline image (SHA-256 per sector; shorter image padded with 0xFF).
  Edits keep the line count of the file (the warning gate keys on file:line, #26).
  Counts: all changed sectors; of which common-area sectors (copied into every bank); banks touched.
Log: tmp/logs/flash_layout_measure.log, result tmp/meas/result.json, images tmp/meas/<mode>_<edit>.bin
"""
import argparse, hashlib, json, os, shutil, subprocess, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402
import sdcc_layout as L  # noqa: E402

ROOT = repo_root()
SECTOR, BANK = 4096, 0x10000
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
              "old": "        AwtoDiagInit();\n        SysMainSystemInitial();",
              "new": "        AwtoDiagInit();\n        SysMainSystemInitial(); SysMainSystemInitial();"}],
}
LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True); LOG.write(line + "\n"); LOG.flush()


def build(serial, tag, layout=None, edit=None):
    meas = ROOT / "tmp/meas"
    cmd = [sys.executable, "scripts/fw_build.py", "--serial", serial]
    if layout:
        cmd += ["--layout", str(layout)]
    if edit:
        pf = meas / f"patch_{edit}.json"
        pf.write_text(json.dumps(EDITS[edit]))
        cmd += ["--src-patch", str(pf)]
    log(f"build {tag}: {' '.join(cmd[1:])}")
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=BUILD_TIMEOUT)
    (meas / f"{tag}.build.log").write_text(r.stdout + r.stderr)
    if r.returncode:
        sys.exit(f"build {tag} failed rc={r.returncode}: {(r.stdout + r.stderr)[-1500:]}")
    img = meas / f"{tag}.bin"
    shutil.copy(ROOT / "tmp/fw" / serial / "fw.bin", img)
    shutil.copy(ROOT / "tmp/fw" / serial / "fw.map", meas / f"{tag}.map")
    return img


def rows_changed(a: Path, b: Path):
    ra, rb = L.Layout.load(a).rows, L.Layout.load(b).rows
    return sum(1 for k in set(ra) | set(rb) if ra.get(k) != rb.get(k))


def stack_total(tag):
    r = subprocess.run([sys.executable, "scripts/fw_stack.py"], cwd=ROOT, capture_output=True, text=True, timeout=120)
    try:
        return json.loads(r.stdout)["total"]
    except Exception:
        return None


def sectors(img: bytes, n):
    img = img + b"\xff" * (n * SECTOR - len(img))
    return [hashlib.sha256(img[i:i + SECTOR]).hexdigest() for i in range(0, n * SECTOR, SECTOR)]


def diff(a: Path, b: Path):
    x, y = a.read_bytes(), b.read_bytes()
    n = (max(len(x), len(y)) + SECTOR - 1) // SECTOR
    sx, sy = sectors(x, n), sectors(y, n)
    ch = [i for i in range(n) if sx[i] != sy[i]]
    per = BANK // SECTOR
    return {"sectors": len(ch), "total": n, "common": sum(1 for i in ch if i % per < 5),
            "banks": sorted({i // per for i in ch})}


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--serial", default="AWT26110003")
    ap.add_argument("--layout", default="fw/bank_layout.tsv")
    ap.add_argument("--edits", default=",".join(EDITS))
    ap.add_argument("--reuse-baselines", action="store_true")
    a = ap.parse_args()
    meas = ROOT / "tmp/meas"
    meas.mkdir(parents=True, exist_ok=True)
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/flash_layout_measure.log").open("a")
    lay0 = ROOT / a.layout
    res = {}

    def newbuild(tag, edit=None):
        lp = meas / f"layout_{tag}.tsv"
        shutil.copy(lay0, lp)                                # every run starts from the same committed layout
        img = build(a.serial, tag, lp, edit)
        return img, lp

    if a.reuse_baselines and (meas / "base_old.bin").exists():
        base_old = meas / "base_old.bin"
    else:
        base_old = build(a.serial, "base_old")
    base_new, _ = newbuild("base_new")
    res["baseline"] = {"old_bytes": base_old.stat().st_size, "new_bytes": base_new.stat().st_size,
                       "new_vs_creation_build": diff(meas / "new0.bin", base_new) if (meas / "new0.bin").exists() else None}
    res["stack"] = {"old": None, "new": stack_total("new")}
    for e in a.edits.split(","):
        old_img = build(a.serial, f"old_{e}", None, e)
        s_old = stack_total("old")
        new_img, lp = newbuild(f"new_{e}", e)
        res[e] = {"old": diff(base_old, old_img), "new": diff(base_new, new_img),
                  "layout_rows_changed": rows_changed(lay0, lp)}
        log(f"edit {e}: old {res[e]['old']}  new {res[e]['new']}  layout rows changed {res[e]['layout_rows_changed']}")
        res.setdefault("stack_edit", {})[e] = {"old": s_old, "new": stack_total("new")}
    (meas / "result.json").write_text(json.dumps(res, indent=1))
    log("| edit | old sectors | new sectors | old common | new common | new banks touched |")
    for e in a.edits.split(","):
        o, n = res[e]["old"], res[e]["new"]
        log(f"| {e} | {o['sectors']}/{o['total']} | {n['sectors']}/{n['total']} | {o['common']} | {n['common']} | {n['banks']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
