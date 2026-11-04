#!/usr/bin/env python3
"""Sleep/wake the monitors on GNOME screen-lock/idle (org.gnome.ScreenSaver ActiveChanged)."""
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
CTL = REPO / "scripts" / "ddc_ctl.py"
LOG = REPO / "tmp" / "logs" / "ddc_idle.log"

# Waits for one `ddc_ctl.py sleep|wake` (detect + 3x set + 3x read-back; measured ~3-6 s worst).
# Limit 3x = 20 s. On expiry: log, kill child, keep listening.
CTL_TIMEOUT_S = 20.0

log = logging.getLogger("ddc_idle")


def ctl(action):
    try:
        p = subprocess.run([sys.executable, str(CTL), action], capture_output=True, text=True, timeout=CTL_TIMEOUT_S)
        log.info("ddc_ctl %s rc=%d", action, p.returncode)
    except subprocess.TimeoutExpired:
        log.error("TIMEOUT ddc_ctl %s limit=%.0fs", action, CTL_TIMEOUT_S)


def main():
    LOG.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        datefmt="%Y-%m-%dT%H:%M:%S", handlers=[logging.FileHandler(LOG), logging.StreamHandler()])
    cmd = ["gdbus", "monitor", "--session", "--dest", "org.gnome.ScreenSaver"]
    log.info("start: %s", " ".join(cmd))
    # No Python dbus bindings installed; gdbus prints: /org/gnome/ScreenSaver: org.gnome.ScreenSaver.ActiveChanged (true,)
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True) as p:
        for line in p.stdout:
            m = re.search(r"ActiveChanged \((true|false),?\)", line)
            if m:
                active = m.group(1) == "true"
                log.info("ActiveChanged active=%s", active)
                ctl("sleep" if active else "wake")
    log.error("gdbus monitor exited rc=%s", p.returncode)
    return 1


if __name__ == "__main__":
    sys.exit(main())
