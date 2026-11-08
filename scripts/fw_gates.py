#!/usr/bin/env python3
"""Offline gates for one firmware image (health sims in parallel): boot-check, isr-check, link check, health --sim 1080p60 + 2160p60.

usage: fw_gates.py IMAGE_STEM [--tree WORKTREE] [--speed LABEL] [--only boot,isr,link,h1080,h2160,menu,ddc]
  menu, ddc: only for images with the settings registry (#67): menu_cli walk + ddc_sim (MCCS) in fw_sim.
  IMAGE_STEM = tmp/fw/<tag> (.bin + .map beside it). link: 0 findings (#66, no baseline).
  --speed LABEL: also append a speed_bench row (docs/speed-bench.tsv) for the image.
  Each gate's output -> tmp/logs/fw_gates/<stem>.<gate>.log; one PASS/FAIL line per gate; exit 1 if any fails.
Stall guard (awto-dan#53): a gate silent for STALL_S is killed and FAILs; backstop LIMIT_S per gate.
Log: ./tmp/logs/fw_gates.log
"""
import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root

ROOT = repo_root()
STALL_S = 60          # no output line for 60 s = hung (awto-dan#53)
SILENT_S = {"h1080": 480, "h2160": 480, "menu": 480, "ddc": 480}   # health --sim prints only at the end: 3x its cold 160 s (2026-11-07); menu/ddc boot silently first
LIMIT_S = 900         # backstop: 3x the slowest gate seen (health --sim 2160p60 ~ 5 min cold, 2026-11-07)
PY = [sys.executable, "-u"]


def gates(b: Path, m: Path, ref, tree):
    s = str(ROOT / "scripts")
    link = [*PY, f"{s}/fw_link_check.py", "--bin", b, "--map", m,
            "--save", ROOT / "tmp/logs/fw_gates" / f"{b.stem}.link-findings.txt"]
    if tree:
        link += ["--layout", Path(tree) / "fw/bank_layout.tsv", "--asm", Path(tree) / "tmp/sdcc-port/asm_bank"]
    g = {}
    mt = Path(m).read_text(errors="replace")
    if " _menu_diag" in mt:                    # #67 images: menu walk + MCCS over the spare DDC engine
        # with video (osd_render session, 1080p60 ACTIVE): without it the main loop sits in the SDK's DP RX PHY CTS routine (sim: the
        # PHY registers read 0) and the mailbox goes silent after a few seconds (#88); earlier images only passed because the
        # sim image was powered off by a phantom POWER key (ADC 0 under the old decode)
        g["menu"] = [*PY, f"{s}/menu_cli.py", "--sim", b, "--map", m, "walk", "--png", ROOT / "tmp/osd67/gate" / b.stem]
    if " _vcp_box" in mt and " _AwtoDdcciPoll" in mt:
        g["ddc"] = [*PY, f"{s}/ddc_sim.py", b, "--map", m]
    return {
        **g,
        "boot": [*PY, f"{s}/fw_sim.py", "--boot-check", b, m],
        "isr": [*PY, f"{s}/fw_sim.py", "--isr-check", b, m],
        "link": link,
        "h1080": [*PY, f"{s}/unit_health.py", "--sim", b, m, "--host-mode", "1920x1080@60"],
        "h2160": [*PY, f"{s}/unit_health.py", "--sim", b, m, "--host-mode", "3840x2160@60"],
    }


def run(name, cmd, out: Path, res: dict, log):
    t0 = time.monotonic()
    last = [t0, ""]
    with out.open("w") as f:
        p = subprocess.Popen(list(map(str, cmd)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT,
                             env=dict(os.environ, PYTHONHASHSEED="0"))

        def watch():
            while p.poll() is None:
                now = time.monotonic()
                stall = SILENT_S.get(name, STALL_S)
                if now - last[0] > stall or now - t0 > LIMIT_S:
                    why = "stall" if now - last[0] > stall else "limit"
                    log(f"{name}: KILL ({why}) after {now - t0:.0f}s, silent {now - last[0]:.0f}s, last: {last[1][:160]!r}, "
                        f"loadavg {os.getloadavg()[0]:.1f}")
                    p.kill()
                    return
                try:
                    p.wait(timeout=1)            # 1 s watchdog tick; returns at once when the gate exits
                except subprocess.TimeoutExpired:
                    pass

        threading.Thread(target=watch, daemon=True).start()
        for line in p.stdout:
            f.write(line); f.flush()
            last[0], last[1] = time.monotonic(), line.strip()
        rc = p.wait()
    res[name] = (rc, time.monotonic() - t0, last[1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stem")
    ap.add_argument("--against", default="", help="ignored (#66: link findings must be 0, no baseline)")
    ap.add_argument("--speed", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--tree", default="", help="worktree the image was built in (its bank_layout.tsv + asm_bank)")
    a = ap.parse_args()
    (ROOT / "tmp/logs/fw_gates").mkdir(parents=True, exist_ok=True)
    lf = (ROOT / "tmp/logs/fw_gates.log").open("a", buffering=1)

    def log(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line, flush=True); lf.write(line + "\n")

    stem = Path(a.stem)
    b, m = stem.with_suffix(".bin") if stem.suffix != ".bin" else stem, None
    m = b.with_suffix(".map")
    g = gates(b, m, a.against, a.tree)
    if a.only:
        g = {k: v for k, v in g.items() if k in a.only.split(",")}
    if a.speed:
        g["speed"] = [*PY, str(ROOT / "scripts/speed_bench.py"), b.with_suffix(""), "--label", a.speed]
    log(f"=== gates {b.name}: {', '.join(g)} ===")
    res = {}
    # boot/isr/link first, one at a time: boot-check shares tmp/fwsim/<stem>/ with the health sims (a parallel run FAILed at
    # gsinit, 2026-11-07); then the two health sims (separate SimBus machines) in parallel
    for group in ([k for k in g if k in ("boot", "isr", "link")], [k for k in g if k not in ("boot", "isr", "link")]):
        th = []
        for k in group:
            t = threading.Thread(target=run, args=(k, g[k], ROOT / "tmp/logs/fw_gates" / f"{b.stem}.{k}.log", res, log))
            t.start(); th.append(t)
            if k in ("boot", "isr", "link"):
                t.join()                 # short ones in turn; the health sims run in parallel (per-process sim dir, fw_sim)
        for t in th:
            t.join()
    bad = 0
    for k in g:
        rc, dt, last = res[k]
        ok = rc == 0 or (k.startswith("h") and last.endswith("FAIL: delay cal"))   # delay cal needs wb-delaycal (#54)
        bad += not ok
        log(f"{'PASS' if ok else 'FAIL'} {k:6s} rc={rc} {dt:5.0f}s  {last[:150]}")
    log(f"=== {b.name}: {'ALL PASS' if not bad else f'{bad} FAIL'} ===")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
