#!/usr/bin/env python3
"""Live watcher for input-port status registers over debug slave 0x35 (awto-ddc#139): cable, HPD, TMDS lock, DDC, DP AUX.

usage: port_watch.py <bus> --serial AWT2611000N [--secs 120] [--period-ms 50] [--slow-every 2] [--mark FILE]
       port_watch.py --sim BIN MAP [--sim-poke T:ADDR=VAL ...] --secs 3      (firmware simulator, no hardware)
       port_watch.py --list | --plan                                         (register list / read plan with timing, offline)
  Registers: scripts/port_watch_regs.tsv (side-effect-free reads only); skipped ones + reason: port_watch_excluded.tsv.
  Output: one line per change `+ 1234 ms  FE32.0 PA.2_H1_CABLE 0->1`; rate bits print edges/s per 1 s window.
  Markers: type a line on stdin or append to the --mark file (default tmp/port_watch.mark): `echo "unplug HDMI1" >> tmp/port_watch.mark`.
  End: summary per bit with change count and the nearest marker for each change.
Cost (100 kHz, 9 clocks per byte): one block read = write 6 B (addr, sub 0x3C, lo, hi, len, seq) + read phase
  (addr, sub 0x08, addr, n data, 1 checksum) = (10 + n) bytes x 9 / 100 kHz = 0.9 ms + 0.09 ms/byte; --plan prints the totals.
  Reads merge into <=24 B chunks (gap <= 8 B). Default 50 ms period: fast set (pins, DDC flags) ~5 ms, slow set (HDMI RX, DP) every 2nd sweep.
  Period 50 ms = bus ~10-30 % busy, so the debug ISR does not starve the firmware main loop (0x35 wedged under continuous polling, #11).
Stall guard: no successful chunk read for 2 s -> log the error and exit 2 (6 sweeps lost at 50 ms + retries; a longer gap is a wedge).
Log: ./tmp/logs/port_watch.log (decoded), port_watch.detail.log (protocol), port_watch.raw.log (bytes).
"""
from __future__ import annotations

import argparse
import csv
import os
import queue
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dbg_xdata as X  # noqa: E402

STALL_S = 2.0              # no successful chunk read for this long = wedged debug slave
RATE_WINDOW_S = 1.0        # edges/s window for mode=rate bits (DPS17 pulses every 60-100 ms -> ~10-16 edges/s)
GAP_MAX = 8                # merge reads with <= 8 unread bytes between them (8 x 9 bits < one 10-byte transaction overhead)
BIT_US = 10.0              # 100 kHz


def repo_root() -> Path:
    return Path(os.environ.get("AWTO_DDC_REPO") or HERE.parent)


class Bit:
    def __init__(self, row):
        self.addr = int(row["addr"], 16)
        hi, _, lo = row["bits"].partition(":")
        self.hi, self.lo = int(hi), int(lo or hi)
        self.name, self.set, self.mode, self.note = row["name"], row["set"], row["mode"], row["note"]
        self.mask = ((1 << (self.hi - self.lo + 1)) - 1) << self.lo
        self.key = f"{self.addr:04X}.{self.hi}" + (f":{self.lo}" if self.hi != self.lo else "")
        self.cur = None
        self.changes = []           # (t_ms, old, new)
        self.rates = []             # rate: (t_ms, old edges/s, new edges/s)
        self.edges = 0              # rate: total edges
        self.win_edges = 0
        self.last_rate = None

    def val(self, byte: int) -> int:
        return (byte & self.mask) >> self.lo

    def fmt(self, v) -> str:
        return str(v) if self.hi == self.lo else f"0x{v:02X}"


def load_bits(path: Path) -> list[Bit]:
    lines = [l for l in path.read_text().splitlines() if l.strip() and not l.startswith("#")]
    return [Bit(r) for r in csv.DictReader(lines, delimiter="\t")]


def plan(bits: list[Bit], sset: str) -> list[tuple[int, int]]:
    """Address list of the set -> [(start, n)] chunks, merged across small gaps, <= X.BLK_MAX bytes each."""
    addrs = sorted({b.addr for b in bits if b.set == sset})
    out: list[list[int]] = []
    for a in addrs:
        if out and a - (out[-1][0] + out[-1][1] - 1) - 1 <= GAP_MAX and a - out[-1][0] + 1 <= X.BLK_MAX:
            out[-1][1] = a - out[-1][0] + 1
        else:
            out.append([a, 1])
    return [(s, n) for s, n in out]


def chunk_ms(n: int) -> float:
    return (10 + n) * 9 * BIT_US / 1000


def print_plan(bits, out=print):
    tot = {}
    for s in ("fast", "slow"):
        ch = plan(bits, s)
        t = sum(chunk_ms(n) for _, n in ch)
        tot[s] = t
        out(f"{s}: {len(ch)} chunks, {sum(n for _, n in ch)} B, {t:.1f} ms at 100 kHz (before firmware ISR latency)")
        for a, n in ch:
            out(f"  0x{a:04X} x{n:<2} {chunk_ms(n):.2f} ms")
    out(f"full sweep {tot['fast'] + tot['slow']:.1f} ms; default period 50 ms with slow every 2nd sweep")


class Marks:
    """Markers from stdin lines and an appended file; stamped when drained (<= one sweep late)."""

    def __init__(self, path: Path | None):
        self.q: queue.Queue = queue.Queue()
        self.path, self.off = path, 0
        if path:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        if sys.stdin and not sys.stdin.closed:
            threading.Thread(target=self._stdin, daemon=True).start()

    def _stdin(self):
        try:
            for line in sys.stdin:
                if line.strip():
                    self.q.put(line.strip())
        except (OSError, ValueError):
            pass

    def drain(self) -> list[str]:
        out = []
        while not self.q.empty():
            out.append(self.q.get())
        if self.path and self.path.stat().st_size > self.off:
            with self.path.open() as f:
                f.seek(self.off)
                data = f.read()
                self.off = f.tell()
            out += [l.strip() for l in data.splitlines() if l.strip()]
        return out


class Watch:
    def __init__(self, io, bits, now, wait, emit, marks, period, slow_every):
        self.io, self.bits, self.now, self.wait, self.emit = io, bits, now, wait, emit
        self.marks, self.period, self.slow_every = marks, period, slow_every
        self.chunks = {"fast": plan(bits, "fast"), "slow": plan(bits, "slow")}
        self.by_addr: dict[int, list[Bit]] = {}
        for b in bits:
            self.by_addr.setdefault(b.addr, []).append(b)
        self.block, self.t0, self.last_ok = True, None, None
        self.marker_list: list[tuple[float, str]] = []
        self.sweeps, self.reads, self.errs, self.sweep_ms = 0, 0, 0, []
        self.win_start = None

    def ms(self) -> int:
        return int((self.now() - self.t0) * 1000)

    def read_chunk(self, a: int, n: int):
        r = X.read_chunk(self.io, a, n) if self.block else X.read_bytes(self.io, a, n)
        if r is None and self.block and self.reads == 0:
            self.emit("block read (0x3C) not answered: falling back to the byte path")
            self.block = False
            r = X.read_bytes(self.io, a, n)
        return r

    def sweep(self, sets):
        t_in = self.now()
        for s in sets:
            for a, n in self.chunks[s]:
                r = self.read_chunk(a, n)
                if r is None:
                    self.errs += 1
                    if self.last_ok is not None and self.now() - self.last_ok > STALL_S:
                        self.emit(f"STALL: no successful read for {self.now() - self.last_ok:.2f} s (limit {STALL_S} s) at 0x{a:04X} x{n}; exit")
                        raise SystemExit(2)
                    continue
                self.reads += 1
                self.last_ok = self.now()
                for i, v in enumerate(r):
                    for b in self.by_addr.get(a + i, ()):
                        if b.set == s:
                            self.update(b, b.val(v))
        self.sweeps += 1
        self.sweep_ms.append((self.now() - t_in) * 1000)

    def update(self, b: Bit, v: int):
        t = self.ms()
        if b.cur is None:
            b.cur = v
            self.emit(f"= {t:5d} ms  {b.key} {b.name} {b.fmt(v)}")
            return
        if v == b.cur:
            return
        if b.mode == "rate":
            b.edges += 1
            b.win_edges += 1
        else:
            b.changes.append((t, b.cur, v))
            self.emit(f"+ {t:5d} ms  {b.key} {b.name} {b.fmt(b.cur)}->{b.fmt(v)}")
        b.cur = v

    def rate_window(self, force=False):
        t = self.now()
        if self.win_start is None:
            self.win_start = t
        if not force and t - self.win_start < RATE_WINDOW_S:
            return
        dt = max(t - self.win_start, 1e-3)
        for b in self.bits:
            if b.mode != "rate" or b.cur is None:
                continue
            rate = b.win_edges / dt
            ref = b.last_rate
            if (ref is None and rate > 0) or (ref is not None and (abs(rate - ref) >= max(2.0, 0.5 * ref))):
                self.emit(f"~ {self.ms():5d} ms  {b.key} {b.name} {rate:.0f} edges/s (was {'-' if ref is None else f'{ref:.0f}'})")
                b.rates.append((self.ms(), round(ref or 0), round(rate)))
                b.last_rate = rate
            b.win_edges = 0
        self.win_start = t

    def run(self, secs: float):
        self.t0 = self.now()
        self.last_ok = self.t0
        n = 0
        try:
            while self.now() - self.t0 < secs:
                ts = self.now()
                for m in self.marks.drain():
                    self.marker_list.append((self.ms(), m))
                    self.emit(f"# {self.ms():5d} ms  MARK {m}")
                sets = ["fast"] + (["slow"] if n % self.slow_every == 0 else [])
                self.sweep(sets)
                n += 1
                self.rate_window()
                left = self.period - (self.now() - ts)
                if left > 0:
                    self.wait(left)
        except KeyboardInterrupt:
            self.emit("interrupted")
        self.rate_window(force=True)

    def summary(self):
        self.emit("--- summary ---")
        sw = sorted(self.sweep_ms)
        if sw:
            self.emit(f"sweeps {self.sweeps}, chunk reads {self.reads}, failed {self.errs}; sweep time ms: median {sw[len(sw) // 2]:.1f}, max {sw[-1]:.1f}; markers {len(self.marker_list)}")
        for b in self.bits:
            if b.cur is None:
                self.emit(f"{b.key} {b.name}: never read")
                continue
            if b.mode == "rate":
                self.emit(f"{b.key} {b.name}: {b.edges} edges counted, final level {b.fmt(b.cur)}, rate changes {len(b.rates)}")
                for t, o, n in b.rates:
                    self.emit(f"    {t:5d} ms {o}->{n} edges/s  nearest mark: {self.nearest(t)}")
                continue
            elif not b.changes:
                continue
            else:
                self.emit(f"{b.key} {b.name}: {len(b.changes)} change(s), now {b.fmt(b.cur)}")
            for t, o, n in b.changes:
                self.emit(f"    {t:5d} ms {b.fmt(o)}->{b.fmt(n)}  nearest mark: {self.nearest(t)}")
        quiet = sum(1 for b in self.bits if b.cur is not None and not b.changes and b.mode != "rate")
        self.emit(f"{quiet} bit(s) never changed")

    def nearest(self, t: int) -> str:
        if not self.marker_list:
            return "(none)"
        mt, m = min(self.marker_list, key=lambda x: abs(x[0] - t))
        return f"'{m}' at {mt} ms ({t - mt:+d} ms)"


def make_emit(lg):
    def emit(s: str):
        print(s, flush=True)
        lg.main.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}\n")
    return emit


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bus", type=int, nargs="?")
    ap.add_argument("--serial")
    ap.add_argument("--secs", type=float, default=120.0, help="run length")
    ap.add_argument("--period-ms", type=float, default=50.0, help="time between sweep starts")
    ap.add_argument("--slow-every", type=int, default=2, help="slow set every Nth sweep")
    ap.add_argument("--mark", type=Path, default=repo_root() / "tmp/port_watch.mark")
    ap.add_argument("--regs", type=Path, default=HERE / "port_watch_regs.tsv")
    ap.add_argument("--sim", nargs=2, type=Path, metavar=("BIN", "MAP"))
    ap.add_argument("--sim-port", default="D2", choices=("D2", "D3"))
    ap.add_argument("--sim-poke", action="append", default=[], metavar="T:ADDR=VAL", help="sim: write XDATA at sim second T")
    ap.add_argument("--no-raw", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--plan", action="store_true")
    a = ap.parse_args()
    bits = load_bits(a.regs)
    if a.list:
        for b in bits:
            print(f"{b.key:10} {b.set:4} {b.mode:5} {b.name:24} {b.note}")
        print("excluded:")
        print((HERE / "port_watch_excluded.tsv").read_text())
        return 0
    if a.plan:
        print_plan(bits)
        return 0
    import rtd_proto as P
    lg = P.setup_logs("port_watch", raw=not a.no_raw, detail=True)
    emit = make_emit(lg)
    marks = Marks(a.mark)
    period = a.period_ms / 1000
    if a.sim:
        import fw_sim
        bus = fw_sim.SimBus(a.sim[0], a.sim[1], video="1080p60", port=a.sim_port)
        bus.run_until_mode(3)
        pokes = sorted((float(p.split(":")[0]), int(p.split(":")[1].split("=")[0], 0), int(p.split("=")[1], 0)) for p in a.sim_poke)
        t_base = bus.now()
        orig_wait = bus.wait

        def wait(s):                                  # apply pokes at their sim time while the sim idles
            orig_wait(s)
            while pokes and bus.now() - t_base >= pokes[0][0]:
                _, ad, v = pokes.pop(0)
                bus.m.wr(ad, bytes([v]))
                emit(f"(sim) poke 0x{ad:04X} <- 0x{v:02X}")
        emit(f"sim {a.sim[0].name}; regs {len(bits)} bits")
        w = Watch(bus, bits, bus.now, wait, emit, marks, period, a.slow_every)
        try:
            w.run(a.secs)
        finally:
            w.summary()
            bus.close()
        return 0
    if a.bus is None or not a.serial:
        ap.error("bus and --serial are required (or --sim BIN MAP)")
    import i2cbus
    import rtd_i2c_bridge as B
    import unit_lock
    if i2cbus.rate_khz() != 100:
        emit(f"bus rate {i2cbus.rate_khz()} kHz; port_watch costs assume 100 kHz")
    i2cbus.require_unit(a.bus, a.serial)
    with unit_lock.held(a.serial, "port_watch"):
        io = B.Real(a.bus, allow_write=False, regread=True)    # debug read commands only; never writes memory
        emit(f"bus {a.bus} unit {a.serial}; regs {len(bits)} bits; period {a.period_ms:.0f} ms; marks via stdin or {a.mark}")
        print_plan(bits, emit)
        w = Watch(io, bits, time.monotonic, time.sleep, emit, marks, period, a.slow_every)
        rc = 0
        try:
            w.run(a.secs)
        except SystemExit as e:
            rc = int(e.code or 0)
        finally:
            w.summary()
        return rc


if __name__ == "__main__":
    sys.exit(main())
