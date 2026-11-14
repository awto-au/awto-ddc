#!/usr/bin/env python3
"""Failure rate of the firmware debug slave 0x35 per DDC bus rate (#12). Read-only: same 48 B diag-block reads as rtd_diag.

usage: i2c_rate_test.py [--bus 11] [--unit AWT26110003] [--n 300] [--rates 100,1000,50] [--gap-us 0] [--paths byte,block]
  byte path: cmd 0x01 [hi], then 48 x (cmd 0x3A [lo] write, cmd 0x08 read 1) = 97 transfers (every firmware).
  block path: 2 x (cmd 0x3C [lo hi 24 seq] write, cmd 0x08 read 25 = data + checksum, no retry here) = 4 transfers (diag version 2, docs/diag-block.md).
  Rates other than 100 load tools/gmbus_rate around the batch (i2cbus.fast_bus, unloaded in finally).
  Failure classes: nak-addr (ENXIO on the first transfer), nak-mid (ENXIO later; phase + byte index kept),
  timeout (EAGAIN/ETIMEDOUT), garbled (bytes differ from the stable bytes of a reference block; positions kept,
  'stale' = equals the previous byte read, i.e. the slave answered before the new value was staged).
  --gap-us: host delay between each staging write and its read (discriminating experiment, not a fix).
Refuses to run while another tool owns the unit (rtd_flash_image/osd_test/rtd_diag/dev.py).
Log: ./tmp/logs/i2c_rate_test.log (one line per batch), ./tmp/logs/i2c_rate_test.raw.log (every failure).
"""
import argparse, errno, os, statistics, sys, time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X  # noqa: E402
import i2cbus  # noqa: E402

ROOT = i2cbus.ROOT
SLAVE, BASE, SIZE = 0x35, 0xF6D0, 48
CMD_HI, CMD_READ, READ_SUB = 0x01, 0x3A, 0x08
OTHERS = ("rtd_flash_image", "osd_test", "rtd_diag", "dev.py", "rtd_dbg_write")
# Bytes that change while the firmware runs: counters 0x14-0x19, trace 0x28-0x2F (rtd_diag.py block layout)
VOLATILE = set(range(0x14, 0x1A)) | set(range(0x28, 0x30))
SETTLE_S = 0.2      # after a failed read: firmware bus watchdog is 100 ms (_AWTO_BUS_STUCK_MS), 2x for margin
LOGS = ROOT / "tmp" / "logs"
PATH = "byte"          # set per run from --paths


def _is_ours(proc: Path, args: list[bytes]) -> bool:
    """True when the script arg resolves (against the process cwd) into this repo; other projects' dev.py do not count."""
    try:
        cwd = Path(os.readlink(proc / "cwd"))
    except OSError:
        return False
    for a in args:
        n = Path(a.decode("latin-1"))
        if n.suffix == ".py" and any(o in n.name for o in OTHERS):
            f = (n if n.is_absolute() else cwd / n).resolve()
            return ROOT in f.parents
    return False


def others_running() -> list[str]:
    me, out = os.getpid(), []
    for p in Path("/proc").iterdir():
        if not p.name.isdigit() or int(p.name) == me:
            continue
        try:
            argv = (p / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if argv and argv[0].endswith((b"python", b"python3", b"python3.13", b"python3.14")) or (argv and b"python" in argv[0]):
            s = " ".join(a.decode("latin-1") for a in argv[1:3])
            if any(o in s for o in OTHERS) and "i2c_rate_test" not in s and _is_ours(p, argv[1:3]):
                out.append(f"{p.name}: {s}")
    return out


class ReadFail(Exception):
    def __init__(self, cls: str, detail: str):
        self.cls, self.detail = cls, detail


def read_block_chunks(bus: i2cbus.Bus) -> bytes:
    """One 48 B block as 0x3C chunks; raises ReadFail(class, detail) at the first failing transfer."""
    out = bytearray()
    for k, off in enumerate(range(0, SIZE, X.BLK_MAX)):
        n = min(X.BLK_MAX, SIZE - off)
        a = BASE + off
        X._seq = (X._seq + 1) & 0xFF
        seq, rep = X._seq, []
        for what, fn in (("write", lambda: bus.write(SLAVE, X.CMD_BLOCK, X.chunk_cmd(a, n, seq))),
                         ("read", lambda: rep.append(bus.read(SLAVE, READ_SUB, n + 1)))):
            try:
                fn()
            except OSError as e:
                where = f"chunk {k} ({what})"
                if e.errno == errno.ENXIO:
                    raise ReadFail("nak-addr" if (k == 0 and what == "write") else "nak-mid", where) from None
                if e.errno in (errno.EAGAIN, errno.ETIMEDOUT):
                    raise ReadFail("timeout", f"{where} {e}") from None
                raise ReadFail("other", f"{where} {e}") from None
        if not X.chunk_ok(a, n, seq, rep[0]):
            raise ReadFail("checksum", f"chunk {k} reply {rep[0].hex()}")
        out += rep[0][:n]
    return bytes(out)


def read_block(bus: i2cbus.Bus, gap_s: float) -> bytes:
    """One 48 B block (module PATH); raises ReadFail(class, detail) at the first failing transfer."""
    if PATH == "block":
        return read_block_chunks(bus)
    n_tx = 0
    out = bytearray()
    steps = [("hi", None, bytes([BASE >> 8]), CMD_HI)]
    for i in range(SIZE):
        steps.append(("w", i, bytes([(BASE + i) & 0xFF]), CMD_READ))
    for kind, i, data, cmd in steps:
        try:
            bus.write(SLAVE, cmd, data)
            n_tx += 1
            if kind == "w":
                if gap_s:
                    time.sleep(gap_s)
                out.append(bus.read(SLAVE, READ_SUB, 1)[0])
                n_tx += 1
        except OSError as e:
            where = f"transfer {n_tx + 1}/{len(steps) * 2 - 1} byte {i if i is not None else '-'} ({'write' if kind != 'w' or n_tx % 2 == 1 else 'read'})"
            if e.errno == errno.ENXIO:
                raise ReadFail("nak-addr" if n_tx == 0 else "nak-mid", where) from None
            if e.errno in (errno.EAGAIN, errno.ETIMEDOUT):
                raise ReadFail("timeout", f"{where} {e}") from None
            raise ReadFail("other", f"{where} {e}") from None
    return bytes(out)


def stable_reference(bus: i2cbus.Bus) -> tuple[bytes, set]:
    blocks = []
    for _ in range(40):                                       # failures at the fast rate are expected: retry
        try:
            blocks.append(read_block(bus, 0))
        except ReadFail:
            time.sleep(SETTLE_S)
        if len(blocks) == 5:
            break
    if len(blocks) < 5:
        raise SystemExit("no 5 good reference reads in 40 tries")
    ref = blocks[0]
    if ref[:2] != b"AD":
        raise SystemExit(f"reference block bad magic {ref[:2].hex()}: firmware without diag block / not stage 8?")
    vol = set(VOLATILE) | {i for i in range(SIZE) if len({b[i] for b in blocks}) > 1}
    return ref, vol


def batch(bus, khz: int, n: int, ref: bytes, vol: set, gap_s: float, raw) -> dict:
    ok, times, fails, classes = 0, [], [], {}
    prev_val = None
    for k in range(n):
        t = time.monotonic()
        try:
            b = read_block(bus, gap_s)
        except ReadFail as f:
            classes[f.cls] = classes.get(f.cls, 0) + 1
            fails.append(f.cls)
            raw.write(f"{isostamp.now()} {khz} kHz read {k}: {f.cls} {f.detail}\n")
            if f.cls == "timeout":
                i2cbus.gmbus_nudge(bus.bus)
            time.sleep(SETTLE_S)
            continue
        dt = time.monotonic() - t
        bad = [i for i in range(SIZE) if i not in vol and b[i] != ref[i]]
        if bad:
            stale = [i for i in bad if i > 0 and b[i] == ref[i - 1]]
            classes["garbled"] = classes.get("garbled", 0) + 1
            raw.write(f"{isostamp.now()} {khz} kHz read {k}: garbled positions "
                      f"{[f'{i:#04x}:{ref[i]:02x}->{b[i]:02x}' for i in bad]} stale(prev byte)={len(stale)}/{len(bad)}\n")
            continue
        ok += 1
        times.append(dt * 1000)
    raw.flush()
    return {"khz": khz, "n": n, "ok": ok, "classes": classes, "ms": statistics.mean(times) if times else float("nan")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bus", type=int, default=11)
    ap.add_argument("--unit", default="AWT26110003")
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--rates", default="100,1000,50")
    ap.add_argument("--gap-us", type=int, default=0)
    ap.add_argument("--paths", default="byte", help="byte,block")
    a = ap.parse_args()
    LOGS.mkdir(parents=True, exist_ok=True)
    log, raw = open(LOGS / "i2c_rate_test.log", "a"), open(LOGS / "i2c_rate_test.raw.log", "a")

    def say(s):
        line = f"{isostamp.now()} {s}"
        print(line, flush=True); log.write(line + "\n"); log.flush()

    busy = others_running()
    if busy:
        raise SystemExit("unit in use by: " + "; ".join(busy))
    i2cbus.require_unit(a.bus, a.unit)
    i2cbus.reset_rate()
    gap_s = a.gap_us / 1e6
    try:
        for khz in (int(r) for r in a.rates.split(",")):
            def run(rate):
                global PATH
                for PATH in a.paths.split(","):
                    run_path(rate)

            def run_path(rate):
                with i2cbus.Bus(a.bus) as bus:
                    ref, vol = stable_reference(bus)           # reference at the active rate; mismatch = garble
                    r = batch(bus, rate, a.n, ref, vol, gap_s, raw)
                cls = " ".join(f"{k}={v}" for k, v in sorted(r["classes"].items())) or "none"
                say(f"bus {a.bus} unit {a.unit} {rate} kHz {PATH} path gap {a.gap_us} us: {r['ok']}/{r['n']} ok "
                    f"({100 * (r['n'] - r['ok']) / r['n']:.1f}% fail), failures: {cls}, {r['ms']:.1f} ms per good read")
            if khz == 100:
                run(100)
            else:
                with i2cbus.fast_bus(a.bus, khz) as got:
                    if got != khz:
                        say(f"requested {khz} kHz, got {got}: skipping"); continue
                    run(khz)
    finally:
        i2cbus.reset_rate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
