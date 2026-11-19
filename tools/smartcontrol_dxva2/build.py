#!/usr/bin/env python3
"""Build the 32-bit fake dxva2.dll and copy it next to the extracted SmartControl backend.

SmartControl's DDCHelperLib.dll is i386, so the shim is i686. Output: tmp/wine/shim/dxva2.dll,
copy: tmp/wine/app/resources/bin/dxva2.dll. Log: tmp/logs/smartcontrol_build.log.
"""
import os
import shutil
import subprocess
import sys

root = os.environ.get("AWTO_DDC_REPO") or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(root, "tmp/wine/shim")
os.makedirs(out, exist_ok=True)
os.makedirs(os.path.join(root, "tmp/logs"), exist_ok=True)
cmd = ["i686-w64-mingw32-gcc", "-shared", "-static", "-static-libgcc", "-O2", "-Wall", "-o", os.path.join(out, "dxva2.dll"),
       os.path.join(here, "dxva2_shim.c"), os.path.join(here, "dxva2.def"), "-Wl,--kill-at,--enable-stdcall-fixup","-lkernel32"]
r = subprocess.run(cmd, capture_output=True, text=True)
open(os.path.join(root, "tmp/logs/smartcontrol_build.log"), "a").write(" ".join(cmd) + "\n" + r.stdout + r.stderr)
sys.stderr.write(r.stderr)
if r.returncode:
    sys.exit(r.returncode)
dst = os.path.join(root, "tmp/wine/app/resources/bin")
if os.path.isdir(dst):
    shutil.copy(os.path.join(out, "dxva2.dll"), dst)
print("built", os.path.join(out, "dxva2.dll"))
