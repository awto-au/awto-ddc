#!/usr/bin/env python3
"""Build Comm_LinuxI2C.dll and rtd_gui.exe (32-bit, mingw) next to this script. Log: ./tmp/logs/rtd_shim_build.log"""
import os, subprocess, sys
from pathlib import Path

here = Path(__file__).resolve().parent
root = Path(os.environ.get("AWTO_DDC_REPO") or here.parent.parent)
(root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
cmds = [
    ["i686-w64-mingw32-gcc", "-O2", "-Wall", "-shared", "-o", str(here / "Comm_LinuxI2C.dll"),
     str(here / "Comm_LinuxI2C.c"), "-lws2_32", "-static-libgcc", "-Wl,--kill-at"],
    ["i686-w64-mingw32-gcc", "-O2", "-Wall", "-o", str(here / "rtd_gui.exe"),
     str(here / "rtd_gui.c"), "-static-libgcc", "-luser32"],
]
log, rc = [], 0
for cmd in cmds:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)  # compile ~1 s; 60 s backstop
    log.append(" ".join(cmd) + "\n" + r.stdout + r.stderr)
    rc = rc or r.returncode
(root / "tmp" / "logs" / "rtd_shim_build.log").write_text("\n".join(log))
print("\n".join(log[i].split("\n", 1)[1] for i in range(len(log))).strip() or "built", "exit", rc)
sys.exit(rc)
