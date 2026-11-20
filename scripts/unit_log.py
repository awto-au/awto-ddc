#!/usr/bin/env python3
"""Unit log saver (awto-ddc log-keep): the monitor's sync ring, APPENDED to ./tmp/logs/units/<serial>-sync.log, never wiped.

usage: unit_log.py follow --unit N [--interval S] [--once]     poll the ring, append new lines (also `./dev.py synclog --follow --save`)
       (library) Store(serial, dir).ingest(snapshot) -> lines appended; note_written(serial, seq, text) (host_note.py)
- Read = `./dev.py synclog --unit N --whole --json` (GUI control port, one device-op path); never while a flash runs (flash_status).
- Dedupe by ring sequence: the ring entry at (last seq - 1) must still equal the saved raw bytes, else a gap marker and every
  entry is saved again (cold power-up restarted the ring, or N or more lines came between two polls: not told apart).
  A warm reset keeps the ring (RL6449_Project.h AWTO_SYNC_ADDR), so it continues; its new "boot:" line is the boundary.
- Line = ISO host time (event time when the unit has a host sync, else the read time marked '~'), ring seq, decoded text.
- Host notes: host_note.py appends its own line (text at write time) + a notes registry; the ring entry of that note is skipped.
- Poll interval: the ring takes 80 lines, a boot makes ~40 in ~2 s and idle ~1 line / min; 30 s keeps a burst of <= 80 lines whole
  and costs one debug-link swap (~100 ms) per poll. Expiry of a read: dev.py's own limit; a failed poll is logged and retried.
Log: tmp/logs/unit_log.log
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parents[1])
LOGDIR = ROOT / "tmp/logs/units"
LOG = ROOT / "tmp/logs/unit_log.log"
INTERVAL_S = 30
READ_LIMIT_S = 60                          # dev.py synclog through the port: server limit 45 s + 15 s
NOTE_EV = 0xEE


def say(s: str) -> None:
    import isostamp
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="milliseconds")


def log_path(serial: str, d: Path | None = None) -> Path:
    return (d or LOGDIR) / f"{serial}-sync.log"


def parse_output(out: str) -> dict | None:
    """the SYNCJSON line of a `dev.py synclog --json` output (dev.py prefixes its own timestamp)"""
    for ln in out.splitlines():
        i = ln.find("SYNCJSON ")
        if i >= 0:
            return json.loads(ln[i + 9:])
    return None


class Store:
    def __init__(self, serial: str, d: Path | None = None):
        self.serial, self.dir = serial, d or LOGDIR
        self.log, self.state = log_path(serial, self.dir), self.dir / f"{serial}-sync.state.json"
        self.notes = self.dir / f"{serial}-notes.tsv"

    def _state(self) -> dict | None:
        try:
            return json.loads(self.state.read_text())
        except (OSError, ValueError):
            return None

    def _noted(self) -> set[int]:
        try:
            return {int(x.split("\t")[0]) for x in self.notes.read_text().splitlines() if x}
        except OSError:
            return set()

    def _append(self, lines: list[str]) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with self.log.open("a") as f:
            f.writelines(x + "\n" for x in lines)

    def ingest(self, snap: dict) -> list[str]:
        """append the entries the log does not have yet; returns the lines written"""
        ents, wrap, n, seq = snap["entries"], snap["wrap"], snap["n"], snap["seq"]
        prev, read = self._state(), snap["read"]
        out: list[str] = []
        new = ents
        if prev is not None:
            d = (seq - prev["seq"]) % wrap
            tail_ok = any(e["seq"] == (prev["seq"] - 1) % wrap and e["raw"] == prev["raw"] for e in ents)
            if d < n and tail_ok:
                new = [e for e in ents if (e["seq"] - prev["seq"]) % wrap < d]       # d == 0: nothing new
            elif d >= n:
                out.append(f"# {read} ---- gap: the ring took {n} or more lines between two polls, or restarted (cold power-up) ----")
            else:
                out.append(f"# {read} ---- gap: unit ring restarted (cold power-up or a ring that was not kept) ----")
        noted = self._noted()
        for e in new:
            when = e["wall"] or read
            mark = " " if e["wall"] and e["sure"] else "~"
            if e["id"] == NOTE_EV and e["val"] in noted:
                continue                                   # host_note.py logged its text at write time
            out.append(f"{when}{mark} {e['seq']:3d} {e['text']}")
        if ents:
            last = ents[-1]
            self._append(out)
            self.dir.mkdir(parents=True, exist_ok=True)
            self.state.write_text(json.dumps({"seq": seq, "raw": last["raw"], "read": read}))
        return out


def note_written(serial: str, seq: int, text: str, d: Path | None = None) -> None:
    """host_note.py: the note's text with the write time, in the unit log and the registry (the ring keeps one text slot only)"""
    s = Store(serial, d)
    s.dir.mkdir(parents=True, exist_ok=True)
    with s.notes.open("a") as f:
        f.write(f"{seq}\t{now_iso()}\t{text}\n")
    with s.log.open("a") as f:
        f.write(f"{now_iso()}  --- host note {seq}: {text}\n")


def flash_running(unit: str) -> bool:
    import gui_client as G
    rep = G.try_call(G.socket_path(), "flash_status", {"unit": unit})
    res = (rep or {}).get("result") or {}
    return bool(rep and rep.get("ok") and res.get("job") and not res.get("done", True))


DIRECT = False                              # --direct: dev.py talks to the bus itself (no GUI app running / an app from another tree)


def read_snapshot(unit: str) -> dict:
    r = subprocess.run([sys.executable, str(ROOT / "dev.py"), "synclog", "--unit", unit, "--whole", "--json", *(["--direct"] if DIRECT else [])], cwd=ROOT, capture_output=True,
                       text=True, check=False, timeout=READ_LIMIT_S)
    snap = parse_output(r.stdout + r.stderr)
    if snap is None:
        raise OSError(f"no ring in the synclog output (rc {r.returncode}): {(r.stdout + r.stderr).strip().splitlines()[-1:]}")
    return snap


def poll_once(unit: str, store_for=None, read=read_snapshot, busy=flash_running) -> list[str]:
    if busy(unit):
        say(f"unit {unit}: flash running, not polling")
        return []
    snap = read(unit)
    st = (store_for or Store)(snap["serial"] or unit)
    out = st.ingest(snap)
    say(f"unit {unit} ({snap['serial']}): {len(out)} new lines -> {st.log}")
    return out


def follow(unit: str, interval: float, once: bool) -> int:
    while True:
        try:
            poll_once(unit)
        except (OSError, subprocess.TimeoutExpired, ValueError, KeyError) as e:
            say(f"unit {unit}: poll failed: {e}")
        if once:
            return 0
        time.sleep(interval)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["follow"])
    ap.add_argument("--unit", required=True)
    ap.add_argument("--interval", type=float, default=INTERVAL_S)
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--direct", action="store_true")
    a = ap.parse_args()
    global DIRECT
    DIRECT = a.direct
    return follow(a.unit, a.interval, a.once)


if __name__ == "__main__":
    sys.exit(main())
