#!/usr/bin/env python3
"""Run Philips SmartControl (extracted installer tree) under Wine against the emulated monitor.

  smartcontrol_wine.py prepare   unpack /vendors/philips/sources/smartcontrol zip, build profile + shim
  smartcontrol_wine.py run [-- extra args]   launch with the fake dxva2 (log: tmp/logs/smartcontrol_ddc.log)
  smartcontrol_wine.py edid      write the measured EDID into the prefix registry (run while the backend runs)
  smartcontrol_wine.py backend   launch only the .NET backend (bin/SmartControl.exe) for call tracing

Prefix + run tree: tmp/wine/ (untracked). Nothing touches real hardware: the shim answers every
DDC/CI call from tmp/wine/monitor_profile.txt. Console output: tmp/logs/smartcontrol_wine.log.
"""

import os
import subprocess
import sys

ROOT = os.environ.get("AWTO_DDC_REPO") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
WINE = os.path.join(ROOT, "tmp/wine")
ZIP = "/vendors/philips/sources/smartcontrol/SmartControl.exe.zip"
APP = os.path.join(WINE, "app")
LOGS = os.path.join(ROOT, "tmp/logs")


def sh(args, **kw):
    return subprocess.run(args, **kw)


def prepare():
    os.makedirs(LOGS, exist_ok=True)
    dl, nsis = os.path.join(WINE, "dl"), os.path.join(WINE, "nsis")
    os.makedirs(dl, exist_ok=True)
    os.makedirs(nsis, exist_ok=True)
    os.makedirs(APP, exist_ok=True)
    sh(["7z", "x", "-y", "-o" + dl, ZIP], stdout=subprocess.DEVNULL, check=True)
    sh(
        [
            "7z",
            "x",
            "-y",
            "-o" + nsis,
            os.path.join(dl, "SmartControl Setup 7.2.0.exe"),
        ],
        stdout=subprocess.DEVNULL,
        check=True,
    )
    sh(
        ["7z", "x", "-y", "-o" + APP, os.path.join(nsis, "$PLUGINSDIR", "app-64.7z")],
        stdout=subprocess.DEVNULL,
        check=True,
    )
    sh(
        [sys.executable, "-I", os.path.join(ROOT, "scripts/smartcontrol_profile.py")],
        check=True,
    )
    sh(
        [sys.executable, "-I", os.path.join(ROOT, "tools/smartcontrol_dxva2/build.py")],
        check=True,
    )


def env():
    e = dict(os.environ)
    e.pop(
        "ELECTRON_RUN_AS_NODE", None
    )  # set by the VS Code host; makes Electron act as plain node
    e["DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"] = (
        "1"  # Wine has no usable icu.dll for .NET 9
    )
    e["WINEPREFIX"] = os.path.join(WINE, "prefix")
    e["WINEDLLOVERRIDES"] = "dxva2=n;nvapi=n;winemenubuilder.exe=d"
    e["WINEDEBUG"] = os.environ.get("WINEDEBUG", "-all")
    e["SC_PROFILE"] = "Z:" + os.path.join(WINE, "monitor_profile.txt").replace(
        "/", "\\"
    )
    e["SC_DDC_LOG"] = "Z:" + os.path.join(LOGS, "smartcontrol_ddc.log").replace(
        "/", "\\"
    )
    return e


def inject_edid():
    """Put the measured 288E2 EDID where DDCHelperLib looks (Enum\\DISPLAY\\*\\Device Parameters\\EDID)."""
    edid = (
        open(os.path.join(ROOT, "tmp/wine/monitor_profile.txt"))
        .read()
        .split("edid ")[1]
        .split()[0]
    )
    hexs = ",".join(edid[i : i + 2] for i in range(0, len(edid), 2))
    base = "HKEY_LOCAL_MACHINE\\System\\CurrentControlSet\\Enum\\DISPLAY\\Default_Monitor\\%s\\Device Parameters"
    reg = "Windows Registry Editor Version 5.00\n\n"
    for inst in ("0000&0000", "0001&0000"):
        reg += f'[{base % inst}]\n"EDID"=hex:{hexs}\n\n'
    p = os.path.join(WINE, "edid.reg")
    open(p, "w").write(reg)
    sh(["wine", "regedit", "/S", "Z:" + p.replace("/", "\\")], env=env(), check=True)


def run(exe, args):
    os.makedirs(LOGS, exist_ok=True)
    log = open(os.path.join(LOGS, "smartcontrol_wine.log"), "a")
    p = sh(
        ["wine", exe] + args,
        env=env(),
        cwd=os.path.dirname(exe),
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    return p.returncode


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    extra = sys.argv[2:]
    if cmd == "prepare":
        prepare()
    elif cmd == "run":
        sys.exit(run(os.path.join(APP, "SmartControl.exe"), extra))
    elif cmd == "edid":
        inject_edid()
    elif (
        cmd == "wine"
    ):  # raw wine command in the emulation env, e.g. wine reg query KEY
        sys.exit(sh(["wine"] + extra, env=env()).returncode)
    elif cmd == "backend":
        sys.exit(run(os.path.join(APP, "resources/bin/SmartControl.exe"), extra))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
