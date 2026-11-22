#!/usr/bin/env python3
"""Display-on-time matrix (internal module of `./dev.py ontime`): time-to-ACTIVE per trigger, stage splits, health.

usage (via dev.py): ./dev.py ontime --unit N --trigger reset|ddc|switch [--runs 3] [--label L]
                    ./dev.py ontime --units 1,2,3 --trigger dpms [--label L]
- reset: ISP reset; ddc: DDC/CI power sleep then wake; switch: input --away then --back (default D1 then D2; the --back episode is the row);
  dpms: host Mutter PowerSaveMode 3 then 0 once (all units wake together; scripts/host_dpms.py guard).
- Row = the newest sync episode (`./dev.py synclog`) after the trigger, polled until its `sync DONE` line is there.
- Columns (ms from the episode start): init = INITIAL length, reached = first search visit, scan_ok, timing, disp = display
  setting stage, tail = ACTIVE wait timer, active = sync DONE ACTIVE; from_cmd = ACTIVE minus the D6 wake command (DDC/CI wake only); slow = slow pass stage lines.
Logs: ./tmp/logs/ontime/<label>.tsv (rows), <label>-U<unit>-<trigger><k>.txt (every synclog line of the run).
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time

import isostamp
from _repo import ROOT

OUT = ROOT / "tmp/logs/ontime"
# One synclog read ~1.5 s; the picture is back ~1.5-3 s after a trigger, DDC/CI wake ~3.5 s: 8 s = 2x the slowest path seen.
EPISODE_LIMIT_S = 8.0
# Panel power-down T4+T5+T6 ~1.4 s (sync log of a DDC/CI sleep) x 3 = 4 s asleep before the wake; no synclog read while asleep:
# on a DP AUX bus the read leaves the debug link on and DDC/CI NAKs the wake (unit 2).
SLEEP_S = 4.0
# Time on the away input before switching back: the away episode (no signal / other source) must start: 2 x one search cycle ~1 s.
AWAY_S = 2.0
COLS = [
    "unit",
    "trigger",
    "run",
    "active",
    "init",
    "reached",
    "scan_ok",
    "timing",
    "disp",
    "tail",
    "link",
    "health",
    "from_cmd",
    "slow",
]
LINE = re.compile(r"^\S+\s+(\d+):(.*)$")


def say(s: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    print(s, flush=True)


def dev(*args: str) -> str:
    r = subprocess.run(
        [str(ROOT / "dev.py"), *args],
        check=False,
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    return r.stdout + r.stderr


def synclog(unit: int) -> str:
    return dev("synclog", "--unit", str(unit))


def parse(text: str) -> dict:
    r: dict = dict.fromkeys(COLS)
    slow: list[str] = []
    for ln in text.splitlines():
        m = LINE.match(ln)
        if not m:
            continue
        ms, t = int(m.group(1)), m.group(2)
        mm = re.search(r"in INITIAL for (\d+)ms", t)
        if mm:
            r["init"] = int(mm.group(1))
        if t.startswith("search reached") and r["reached"] is None:
            r["reached"] = ms
        if t.startswith("scan ok:") and r["scan_ok"] is None:
            r["scan_ok"] = ms
        if re.match(r"D\d timing \d", t) and r["timing"] is None:
            r["timing"] = ms
        mm = re.match(r"stage:display setting took (\d+)ms", t)
        if mm:
            r["disp"] = int(mm.group(1))
        if "power on by DDC/CI VCP D6" in t:
            r["cmd"] = ms
        mm = re.match(r"ACTIVE wait:timer (\d+)ms", t)
        if mm:
            r["tail"] = int(mm.group(1))
        mm = re.search(r"ACTIVE (\d+)ms$", t)
        if t.startswith("sync DONE") and mm:
            r["active"] = int(mm.group(1))
        if t.startswith("sync FAILED"):
            r["active"] = "FAILED"
        if t.startswith("sync link"):
            r["link"] = (
                "ok" if ("errors 0/0/0" in t or "symbol lock 4/4" in t) else "ERR"
            )
        mm = re.match(r"slow pass stage (.*) took (\d+)ms in (\w[\w ]*?) \(#", t)
        if mm and int(mm.group(2)) >= 40:
            slow.append(f"{mm.group(3)}/{mm.group(1)}={mm.group(2)}")
    r["slow"] = ",".join(slow)
    r["from_cmd"] = (
        (r["active"] - r["cmd"])
        if isinstance(r["active"], int) and r.get("cmd") is not None
        else None
    )
    return r


def wait_episode(unit: int, marker: str, need: tuple[str, ...] = ("sync DONE",)) -> str:
    t0 = time.monotonic()
    while True:
        txt = synclog(unit)
        if marker not in txt and all(n in txt for n in need):
            return txt
        if time.monotonic() - t0 > EPISODE_LIMIT_S:
            say(
                f"U{unit}: no new {need} within {EPISODE_LIMIT_S} s (limit = 2x slowest path)"
            )
            return txt


def health(unit: int) -> str:
    out = dev("health", "--unit", str(unit))
    m = re.search(r"HEALTH \S+: (\d+/\d+) PASS", out)
    return m.group(1) if m else "FAIL"


def record(label: str, unit: int, trig: str, run: int, txt: str, hl: str) -> None:
    (OUT / f"{label}-U{unit}-{trig}{run}.txt").write_text(txt)
    row = parse(txt)
    row.update(unit=unit, trigger=trig, run=run, health=hl)
    tsv = OUT / f"{label}.tsv"
    new = not tsv.exists()
    with tsv.open("a") as f:
        if new:
            f.write("\t".join(COLS) + "\n")
        f.write("\t".join(str(row[c]) for c in COLS) + "\n")
    say(
        f"{isostamp.now()} U{unit} {trig}{run}: ACTIVE {row['active']} ms init {row['init']} reached {row['reached']} "
        f"scan_ok {row['scan_ok']} timing {row['timing']} disp {row['disp']} tail {row['tail']} cmd {row['from_cmd']} health {hl} slow {row['slow']}"
    )


def mark(unit: int) -> str:
    """Host note in the running episode: a log without it is a newer episode (the trigger's)."""
    m = f"ontime{time.time_ns() % 10**9}"
    dev("note", "--unit", str(unit), m)
    dev(
        "link", "off", "--unit", str(unit)
    )  # a DP AUX unit keeps the debug link on after the note: DDC/CI would NAK the sleep / wake
    return m


def run_one(label: str, unit: int, trig: str, run: int, away: str, back: str) -> None:
    before = mark(unit)
    if trig == "reset":
        dev("reset", "--unit", str(unit))
        txt = wait_episode(unit, before)
    elif trig == "ddc":
        dev("ddc", "--unit", str(unit), "sleep")
        time.sleep(SLEEP_S)
        dev("ddc", "--unit", str(unit), "wake")
        txt = wait_episode(unit, before, ("sync episode: wake", "sync DONE"))
    elif trig == "switch":
        dev("kvm", away, "--units", str(unit))
        time.sleep(AWAY_S)
        dev("kvm", back, "--units", str(unit))
        txt = wait_episode(unit, before)
    else:
        raise SystemExit(f"unknown trigger {trig}")
    record(label, unit, trig, run, txt, health(unit))


def run_dpms(label: str, units: list[int], off_s: float) -> None:
    before = {u: mark(u) for u in units}
    dev_env = dict(os.environ, AWTO_DPMS_FORCE="1")
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/host_dpms.py"),
            "off",
            "--guard-s",
            str(int(off_s) + 30),
        ],
        cwd=ROOT,
        env=dev_env,
        check=False,
    )
    time.sleep(off_s)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/host_dpms.py"), "on"],
        cwd=ROOT,
        env=dev_env,
        check=False,
    )
    for u in units:
        record(
            label,
            u,
            "dpms",
            1,
            wait_episode(u, before[u], ("sync episode: wake", "sync DONE")),
            health(u),
        )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--unit", type=int)
    ap.add_argument("--units", default="")
    ap.add_argument(
        "--trigger", required=True, choices=["reset", "ddc", "switch", "dpms"]
    )
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument(
        "--off-s",
        type=float,
        default=15.0,
        help="dpms: seconds the host outputs stay off (L1 hold < 60 s < L2)",
    )
    ap.add_argument("--away", default="D1")
    ap.add_argument("--back", default="D2")
    ap.add_argument("--label", default="run")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.trigger == "dpms":
        run_dpms(a.label, [int(x) for x in a.units.split(",")], a.off_s)
        return 0
    for k in range(1, a.runs + 1):
        run_one(a.label, a.unit, a.trigger, k, a.away, a.back)
    return 0


if __name__ == "__main__":
    sys.exit(main())
