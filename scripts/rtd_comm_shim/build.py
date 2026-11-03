#!/usr/bin/env python3
"""Build Comm_LinuxI2C.dll (32-bit, mingw) next to this script. Log: ./tmp/logs/rtd_shim_build.log"""
import os, subprocess, sys
from pathlib import Path

here = Path(__file__).resolve().parent
root = Path(os.environ.get("AWTO_DDC_REPO") or here.parent.parent)
(root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
cmd = ["i686-w64-mingw32-gcc", "-O2", "-Wall", "-shared", "-o", str(here / "Comm_LinuxI2C.dll"),
       str(here / "Comm_LinuxI2C.c"), "-lws2_32", "-static-libgcc", "-Wl,--kill-at"]
r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)  # compile ~1 s; 60 s backstop
(root / "tmp" / "logs" / "rtd_shim_build.log").write_text(" ".join(cmd) + "\n" + r.stdout + r.stderr)
print(r.stdout + r.stderr or "built", "exit", r.returncode)
sys.exit(r.returncode)
