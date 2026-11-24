#!/usr/bin/env python3
"""Drive the SmartControl backend (Wine, emulated 288E2) over its local REST API and log DDC traffic.

Sequence: start backend -> Rescan (Wine wipes its EDID keys on the first enumeration) -> inject EDID
-> Rescan -> calls given on the command line (METHOD?query, e.g. "GetStandardDDC?eVCPOpCode_e=16").
Each call has a 90 s limit (Start reads every feature at ~150 ms per I2C transaction) (the backend spins when it has no usable monitor). Kills wine at the end.
Logs: tmp/logs/smartcontrol_probe.log (calls + replies), tmp/logs/smartcontrol_ddc.log (shim),
tmp/logs/smartcontrol_backend.log (copy of the app's own NLog). Real hardware is never touched.
"""

import glob
import os
import shutil
import subprocess
import sys
import time
import urllib.request

from _log import Logger

ROOT = os.environ.get("AWTO_DDC_REPO") or os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
PORT = 19400
BASE = f"http://127.0.0.1:{PORT:d}/Main/"
HERE = os.path.join(ROOT, "scripts/smartcontrol_wine.py")
LOG = Logger(os.path.join(ROOT, "tmp/logs/smartcontrol_probe.log"))


def say(msg):
    LOG.say(msg)


def get(path, limit):
    try:
        with urllib.request.urlopen(BASE + path, timeout=limit) as r:
            return r.read().decode("utf-8", "replace")
    except Exception as e:  # noqa: BLE001 - logged, caller decides
        return f"ERR {e}"


def wait_up():
    # backend cold start under Wine is ~5 s; 30 s = 6x, then give up with a log line
    t0 = time.time()
    while time.time() - t0 < 30:
        if get_swagger():
            return True
        time.sleep(0.5)
    return False


def get_swagger():
    try:
        urllib.request.urlopen(
            f"http://127.0.0.1:{PORT:d}/swagger/v1/swagger.json", timeout=2
        ).read(10)
        return True
    except Exception:  # noqa: BLE001
        return False


def main():
    calls = sys.argv[1:]
    env = dict(os.environ)
    backend = subprocess.Popen(
        [sys.executable, "-I", HERE, "backend", "--urls", f"http://127.0.0.1:{PORT:d}"]
    )
    try:
        if not wait_up():
            say("backend did not come up in 30 s")
            return 1
        say("backend up")
        get("Rescan", 15)
        subprocess.run([sys.executable, "-I", HERE, "edid"], check=True, env=env)
        r = get("Rescan", 15)
        say(f"Rescan(2) {len(r)} bytes; EDID name present: {'PHL 288E2' in r}")
        for c in calls:
            r = get(c, 90)
            with open(
                os.path.join(
                    ROOT, "tmp/logs/smartcontrol_reply_{}.json".format(c.split("?")[0])
                ),
                "w",
            ) as _f:
                _f.write(r)
            say("CALL {} -> {}".format(c, r[:300].replace("\n", " ")))
            if r.startswith("ERR"):
                say("call timed out/failed; stopping (backend may be spinning)")
                break
    finally:
        env["WINEPREFIX"] = os.path.join(ROOT, "tmp/wine/prefix")
        subprocess.run(["wineserver", "-k"], env=env, check=False)  # rc ignored: cleanup kill
        backend.wait()
        for f in glob.glob(
            os.path.join(
                ROOT,
                "tmp/wine/prefix/drive_c/users/*/AppData/Roaming/SmartControlData/backserver/logs/*.log",
            )
        ):
            if os.path.getsize(f) < 50_000_000:
                shutil.copy(f, os.path.join(ROOT, "tmp/logs/smartcontrol_backend.log"))
            os.remove(f)
    return 0


if __name__ == "__main__":
    sys.exit(main())
