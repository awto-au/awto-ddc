#!/usr/bin/env python3
"""No magic numbers in OUR firmware (awto-ddc#161): fail on a raw register address or raw palette value.

usage: magic_lint.py [--tree DIR]     exit 1 on any finding
Flags in our files (comments stripped):
  - hex literal as the address of Scaler*/AWTO_XB/AWTO_XFR/AWTO_MEAS_RD
  - `#define <..REG..> 0x....` and (type *)0x.... pointer casts
  - bare 0xFE00-0xFFFE literal (XFR address; 0xFFFF is a sentinel)
  - numeric literal arguments of ScalerOsdSetColorPalette (use AWTO_PAL_* / AWTO_RGB_*)
Allow-list: scripts/magic_allow.tsv  `file-suffix<TAB>line-substring<TAB>reason`, every entry needs a reason.
Our files: fw/sdcc/awto_*.inc, fw/sdcc/glue*.inc, fw/awto/**, awto-marked fw/sdk headers; the generated AwtoRegs.h is the one place addresses live.
Log: ./tmp/logs/magic_lint.log
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ACCESS_RE = re.compile(r"((?:Scaler(?:Get|Set)\w*|AWTO_XB|AWTO_XFR|AWTO_MEAS_RD)\(\s*)0[xX]([0-9A-Fa-f]{3,4})\b")
DEFINE_RE = re.compile(r"#define\s+\w*REG\w*\s+\(?0[xX][0-9A-Fa-f]{3,4}\b")
CAST_RE = re.compile(r"\*\s*\)\s*\(?0[xX][0-9A-Fa-f]{3,4}\b")
XFR_RE = re.compile(r"\b0[xX]F[EF][0-9A-Fa-f]{2}\b")
PAL_RE = re.compile(r"ScalerOsdSetColorPalette\s*\(([^;]*)\)\s*;")
OVERLAY_OURS = ["fw/sdk/Project/Header/RL6449_Project.h", "fw/sdk/Project/Header/AwtoSetIds.h",
                "fw/sdk/Kernel/Common/Debug.h", "fw/sdk/Kernel/Scaler/ScalerCommonFunction/Code/AwtoMsg.h",
                "fw/sdk/Panel/AWTO_M280DCA_E3B.h", "fw/sdk/Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h",
                "fw/sdk/Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K_PINSHARE.h"]


def tree_root(arg):
    if arg:
        return Path(arg)
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


def our_files(root):
    fs = sorted((root / "fw/sdcc").glob("awto_*.inc")) + sorted((root / "fw/sdcc").glob("glue*.inc"))   # glue = settings glue (was fw/awto/settings)
    for sub in ("*.inc", "*.c", "*.h"):
        fs += sorted((root / "fw/awto").rglob(sub))
    fs += [root / p for p in OVERLAY_OURS if (root / p).is_file()]
    return fs


def strip(line, in_block):
    out, i = "", 0
    while i < len(line):
        if in_block:
            j = line.find("*/", i)
            if j < 0:
                return out, True
            i, in_block = j + 2, False
        elif line.startswith("/*", i):
            in_block = True
            i += 2
        elif line.startswith("//", i):
            break
        else:
            out += line[i]
            i += 1
    return out, in_block


def allow_list():
    p = Path(__file__).resolve().parent / "magic_allow.tsv"
    ent = []
    if p.is_file():
        for n, ln in enumerate(p.read_text().splitlines(), 1):
            if not ln.strip() or ln.startswith("#"):
                continue
            f = ln.split("\t")
            if len(f) < 3 or not f[2].strip():
                sys.exit(f"magic_allow.tsv:{n}: needs file<TAB>substring<TAB>reason")
            ent.append((f[0], f[1]))
    return ent


def lint(root):
    allow, bad = allow_list(), []
    for p in our_files(root):
        rel = str(p.relative_to(root))
        blk = False
        for n, raw in enumerate(p.read_text(errors="replace").splitlines(), 1):
            code, blk = strip(raw, blk)
            why = None
            if ACCESS_RE.search(code):
                why = "raw address in a register access"
            elif DEFINE_RE.search(code):
                why = "raw address in a #define ..REG.."
            elif CAST_RE.search(code):
                why = "raw address in a pointer cast"
            elif XFR_RE.search(code.replace("0xFFFF", "")):
                why = "raw XFR address"
            else:
                m = PAL_RE.search(code)
                if m and re.search(r"\b\d+\b", re.sub(r"\[\d+\]", "", m.group(1))):
                    why = "numeric palette argument"
            if why and not any(rel.endswith(f) and s in raw for f, s in allow):
                bad.append(f"{rel}:{n}: {why}: {raw.strip()[:110]}")
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default="")
    a = ap.parse_args()
    root = tree_root(a.tree)
    bad = lint(root)
    log = root / "tmp/logs/magic_lint.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(bad) + (f"\nmagic_lint: {len(bad)} finding(s)" if bad else "magic_lint: 0 findings")
    log.write_text(text + "\n")
    print(text)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
