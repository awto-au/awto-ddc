#!/usr/bin/env python3
"""Read-only SPI flash dump of the Philips 288E2 over the MStar ISP slave 0x49 (HDMI DDC, i915 gmbus) (#381).

- Read only: flashrom probe / -r with noreset=1 (build with read-unlock skipped); own reader sends SPI 0x03 only.
- ~50-70 % of transfers truncate to prefix + FF while the scaler MCU runs: dump (3 reads) -> resolve -> ffcheck.
- One ISP session: noreset everywhere; ISP exit = one 0x24 to 0x49 at the end (resets the scaler, ~4 s).
- Guard: adapter 'i915 gmbus', card1-HDMI-A-2 ddc -> i2c-11, EDID serial UK52307000611 before the session.
- Log: tmp/logs/philips_dump.log. Store: /vendors/philips/288E2/dumps/ (vendor firmware, never the repo).

  ./scripts/philips_dump.py probe | dump | read N | resolve | ffcheck --image F | exit | check   [--chip NAME]
"""
import argparse
import datetime
import hashlib
import os
import select
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import i2cbus

BUS, ISP_ADDR, SERIAL = 11, 0x49, "UK52307000611"
CONNECTOR = "card1-HDMI-A-2"
ISP_EXIT = 0x24                                   # chenxing docs isp/index.md: "Exit ISP / Reset"
MAX_SIZE = 16 << 20                               # >16 MiB would need 4-byte addressing (0xB7): stop instead
STORE = Path("/vendors/philips/288E2/dumps")
STALL_S = 60                                      # host-process stall rule (awto-dan#53)
PROBE_TRIES = 3                                   # RDID misreads intermittently (#381); probe is read-only
PROBE_BACKSTOP_S = 30                            # probe = a few RDID/REMS/RES transfers, well under 1 s
# Read estimate: per 256 B chunk ~2400 bits at 100 kHz = 24 ms, +25 % gmbus overhead; backstop 3x.
CHUNK_S = 0.030
POST_WAIT_S = 5                                   # monitor back after reset: 5 s max (memory monitor-wait-5s)


def repo() -> Path:
    r = os.environ.get("AWTO_DDC_REPO")
    return Path(r) if r else Path(__file__).resolve().parent.parent


ROOT = repo()
# Upstream flashrom runs the chip's block-protect unlock (WREN + WRSR) even for -r; this build skips it
# (one-line patch in prepare_flash_access, tmp/flashrom-src, #381).
FLASHROM = ROOT / "tmp/flashrom-build-ro/flashrom"
WORK = ROOT / "tmp/philips/dump"
LOG = ROOT / "tmp/logs/philips_dump.log"
PROG = f"mstarddc_spi:dev=/dev/i2c-{BUS}:0x{ISP_ADDR:02x},noreset=1"


def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def log(msg: str) -> None:
    line = f"{now()} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def guard() -> None:
    name = i2cbus.adapter_name(BUS)
    link = Path(f"/sys/class/drm/{CONNECTOR}/ddc").resolve().name
    if not name.startswith("i915 gmbus") or link != f"i2c-{BUS}":
        raise SystemExit(f"bus {BUS}: adapter {name!r}, {CONNECTOR} ddc -> {link}; refusing")
    s = i2cbus.edid_serial(BUS) or i2cbus.edid_serial(BUS)   # first read after idle came back None once
    if s != SERIAL:
        raise SystemExit(f"bus {BUS}: EDID serial {s!r} != {SERIAL!r}; refusing")
    log(f"guard ok: /dev/i2c-{BUS} {name!r}, {CONNECTOR} ddc -> {link}, EDID serial {s}")


def proc_syscw(pid: int) -> int:
    try:
        for ln in Path(f"/proc/{pid}/io").read_text().splitlines():
            if ln.startswith("syscw:"):
                return int(ln.split()[1])
    except OSError:
        pass
    return -1


def flashrom(args: list[str], backstop_s: float) -> tuple[int, str, float]:
    cmd = [str(FLASHROM), "-p", PROG, *args]
    log("run: " + " ".join(cmd) + f" (stall {STALL_S} s, backstop {backstop_s:.0f} s)")
    t0 = time.monotonic()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    out, last, buf, syscw, shown = [], t0, b"", -1, t0
    while True:
        r, _, _ = select.select([p.stdout], [], [], 1.0)
        t = time.monotonic()
        w = proc_syscw(p.pid)       # --progress prints nothing for -r here; i2c write() count = liveness
        if w != syscw:
            syscw, last = w, t
        if t - shown >= 30:
            shown = t
            log(f"  ... {t - t0:.0f} s, i2c writes {syscw} (~{syscw // 2 * 256 // 1024} KiB)")
        if r:
            chunk = os.read(p.stdout.fileno(), 4096)
            if not chunk:
                break
            last = t
            buf += chunk
            *lines, buf = buf.replace(b"\r", b"\n").split(b"\n")
            for ln in lines:
                if ln.strip():
                    out.append(ln.decode(errors="replace"))
                    log("  " + out[-1])
        elif t - last > STALL_S or t - t0 > backstop_s:
            p.kill()
            log(f"KILLED: {'stall' if t - last > STALL_S else 'backstop'} after {t - t0:.1f} s, "
                f"silent {t - last:.1f} s, last line {out[-1] if out else ''!r}, load {os.getloadavg()}")
            break
    rc = p.wait()
    el = time.monotonic() - t0
    log(f"rc={rc} elapsed {el:.1f} s")
    return rc, "\n".join(out), el


def probe(extra: list[str] | None = None) -> tuple[str | None, int | None]:
    _, out, _ = flashrom(["-V", *(extra or [])], PROBE_BACKSTOP_S)
    name = size = None
    for ln in out.splitlines():
        if ln.startswith("Found ") and "flash chip" in ln:
            name = ln.split('"')[1]
            kb = ln.split("(")[1].split(" kB")[0]
            size = int(kb) * 1024
    log(f"probe: chip {name!r} size {size}")
    return name, size


def isp_exit() -> None:
    with i2cbus.Bus(BUS) as b:
        b.raw_write(ISP_ADDR, bytes([ISP_EXIT]))
    log(f"ISP exit: wrote 0x{ISP_EXIT:02x} to 0x{ISP_ADDR:02x}")


def check() -> bool:
    t0 = time.monotonic()
    ok = False
    while time.monotonic() - t0 < POST_WAIT_S:
        p = subprocess.run(["ddcutil", "--bus", str(BUS), "getvcp", "10"], capture_output=True, text=True,
                           timeout=POST_WAIT_S, check=False)
        if p.returncode == 0:
            ok = True
            log(f"DDC/CI back after {time.monotonic() - t0:.1f} s: {p.stdout.strip()}")
            break
        time.sleep(0.2)
    if not ok:
        log(f"DDC/CI NOT back within {POST_WAIT_S} s")
    g = subprocess.run(["gdctl", "show"], capture_output=True, text=True, timeout=10, check=False).stdout
    blk = g.split("Monitor DP-3")[1].split("├──Monitor")[0].split("└──Monitor")[0] if "Monitor DP-3" in g else ""
    dp3 = "Current mode" in blk
    log(f"gdctl: DP-3 current mode {'present' if dp3 else 'MISSING'}")
    return ok and dp3


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def chip_size(extra: list[str]) -> int | None:
    for _ in range(PROBE_TRIES):
        name, size = probe(extra)
        if name and size:
            return size if size <= MAX_SIZE else None
    return None


def read_one(n: int, extra: list[str], size: int) -> int:
    """One full read to tmp/philips/dump/dump<n>.bin (ISP stays active: noreset=1)."""
    WORK.mkdir(parents=True, exist_ok=True)
    f = WORK / f"dump{n}.bin"
    for _ in range(PROBE_TRIES):
        rc, out, el = flashrom([*extra, "-r", str(f)], 3 * (size / 256) * CHUNK_S)
        if "No EEPROM/flash device found" not in out:
            break
        log("probe misread inside -r (RDID C2 FF FF); retrying, read-only")
    if rc:
        return rc
    log(f"read {n}: {el:.1f} s, {f.stat().st_size} B, sha256 {sha(f)}")
    return 0


SPI_READ = 0x03                                   # the only SPI opcode resolve() may send
ISP_SPI_WRITE, ISP_SPI_READ, ISP_SPI_END = 0x10, 0x11, 0x12     # chenxing docs isp/index.md


def isp_read(b: "i2cbus.Bus", addr: int, n: int, ops: dict) -> bytes:
    """SPI READ (0x03) of n bytes at addr through the ISP bridge; ISP must already be active (noreset)."""
    cmd = bytes([ISP_SPI_WRITE, SPI_READ, addr >> 16 & 0xFF, addr >> 8 & 0xFF, addr & 0xFF])
    assert cmd[1] == SPI_READ
    b.ops(ISP_ADDR, [cmd])
    data = b.ops(ISP_ADDR, [bytes([ISP_SPI_READ]), n])[0]
    b.ops(ISP_ADDR, [bytes([ISP_SPI_END])])
    ops[SPI_READ] = ops.get(SPI_READ, 0) + 1
    return data


def accept(cands: list[bytes]) -> bytes | None:
    """A chunk value v seen in >= 2 reads, where every other read is v with some bytes FF (a truncated transfer).
    Any read with a non-FF byte that v lacks rejects v."""
    for v in {c for c in cands if cands.count(c) >= 2}:
        if all(all(x == y or x == 0xFF for x, y in zip(c, v)) for c in cands):
            return v
    return None


def ff_tail(v: bytes) -> bool:
    """Ends in an FF run after a non-FF byte: the same shape as a truncated transfer."""
    k = len(v.rstrip(b"\xff"))
    return 0 < k < len(v)


def union(cands: list[bytes]) -> bytes | None:
    """Per byte the non-FF value (None on a non-FF conflict)."""
    out = bytearray()
    for col in zip(*cands):
        vals = set(col) - {0xFF}
        if len(vals) > 1:
            return None
        out.append(vals.pop() if vals else 0xFF)
    return bytes(out)


def bytewise(b: "i2cbus.Bus", c: int, ops: dict) -> bytes:
    """Chunk read from 1-byte transfers: byte 0 of a transfer was never truncated in 3 full reads (#381)."""
    return b"".join(isp_read(b, c + o, 1, ops) for o in range(256))


def resolve() -> int:
    """Per 256 B chunk: accept() over the full reads unless the value has an FF tail; otherwise a 1-byte-transfer
    read must equal the union of the full reads, or two 1-byte-transfer reads must equal each other.
    Stores raw reads + the resolved image."""
    reads = sorted(WORK.glob("dump*.bin"))
    data = [x.read_bytes() for x in reads]
    n = len(data[0])
    out = bytearray(n)
    stats = {"disputed": 0, "fftail": 0, "reread": 0, "union_ok": 0, "two_pass": 0, "unresolved": []}
    ops: dict = {}
    t0 = time.monotonic()
    with i2cbus.Bus(BUS) as b:
        b.ops(ISP_ADDR, [bytes([ISP_SPI_END])])          # CS high before the first command, as flashrom init
        for c in range(0, n, 256):
            cands = [d[c:c + 256] for d in data]
            v = accept(cands)
            if v is not None and not ff_tail(v):
                out[c:c + 256] = v
                continue
            stats["disputed" if v is None else "fftail"] += 1
            stats["reread"] += 1
            u = union(cands)
            r = bytewise(b, c, ops)
            if r == u:
                stats["union_ok"] += 1
                out[c:c + 256] = r
            else:
                r2 = bytewise(b, c, ops)
                if r2 == r:
                    stats["two_pass"] += 1
                    out[c:c + 256] = r
                    log(f"chunk 0x{c:06x}: 1-byte read != union of full reads, two 1-byte reads agree")
                else:
                    stats["unresolved"].append(c)
                    out[c:c + 256] = u or cands[0]
            if stats["reread"] % 100 == 0:
                log(f"  ... {stats['reread']} chunks re-read, at 0x{c:06x}, {time.monotonic() - t0:.0f} s")
    log(f"resolve of {len(data)} reads in {time.monotonic() - t0:.0f} s: {n // 256} chunks, disputed {stats['disputed']}, "
        f"FF-tail {stats['fftail']}, re-read {stats['reread']} (1-byte read = union {stats['union_ok']}, "
        f"two 1-byte reads agree {stats['two_pass']}), unresolved {len(stats['unresolved'])} "
        f"{[hex(x) for x in stats['unresolved'][:32]]}; SPI opcodes sent by resolve: "
        + ", ".join(f"0x{k:02x} x{v}" for k, v in ops.items()))
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    STORE.mkdir(parents=True, exist_ok=True)
    files = []
    for i, x in enumerate(reads, 1):
        dst = STORE / f"{SERIAL}-{ts}-read{i}.bin"
        shutil.copyfile(x, dst)
        files.append((dst, sha(dst)))
    dst = STORE / f"{SERIAL}-{ts}.bin"
    dst.write_bytes(out)
    files.append((dst, sha(dst)))
    ver = subprocess.run([str(FLASHROM), "-R"], capture_output=True, text=True, check=False).stdout.splitlines()[0]
    with (STORE / "README.md").open("a") as m:
        m.write(f"\n## {SERIAL}-{ts}\n- Date: {now()}\n- Tool: `{ver}` ({FLASHROM}, read-unlock skipped), "
                f"`-p {PROG}`, then awto-ddc scripts/philips_dump.py resolve (#381)\n"
                f"- Path: Intel HDMI DDC /dev/i2c-{BUS} ({CONNECTOR}), MStar ISP 0x{ISP_ADDR:02x}, 100 kHz; "
                f"scaler MCU running (no SERDB halt)\n- Size: {n} B per file\n"
                f"- Raw reads differ: ~10 % of 256 B transfers per read return a good prefix + FF to the chunk end.\n"
                f"- `{dst.name}` = resolved image: each 256 B chunk seen identical in >= 2 reads, every other read "
                f"of it only FF-truncated and no FF tail; else a 1-byte-transfer read equal to the union of the full "
                f"reads, or two equal 1-byte-transfer reads. "
                f"Disputed {stats['disputed']}, FF-tail {stats['fftail']}, re-read {stats['reread']}, "
                f"unresolved {len(stats['unresolved'])} {[hex(x) for x in stats['unresolved']]}\n"
                + "".join(f"- `{d.name}`: sha256 `{h}`\n" for d, h in files)
                + "- Good copy: size and sha256 as listed.\n")
    for x in reads:
        x.unlink()
    log("stored: " + ", ".join(str(d) for d, _ in files))
    return 1 if stats["unresolved"] else 0


def ffcheck(image: Path) -> int:
    """All-FF chunks of a resolved image: two more 256 B reads each (aligned at 0 and +128). Any non-FF byte
    -> two 1-byte-transfer reads of that chunk, written into the image if they agree. Returns unresolved count."""
    img = bytearray(image.read_bytes())
    ops: dict = {}
    found, bad, t0 = [], [], time.monotonic()
    with i2cbus.Bus(BUS) as b:
        b.ops(ISP_ADDR, [bytes([ISP_SPI_END])])
        for c in range(0, len(img), 256):
            if img[c:c + 256] != b"\xff" * 256:
                continue
            x = isp_read(b, c, 256, ops) + isp_read(b, c + 128, 128, ops)
            if x != b"\xff" * 384:
                r, r2 = bytewise(b, c, ops), bytewise(b, c, ops)
                (found if r == r2 else bad).append(c)
                if r == r2:
                    img[c:c + 256] = r
    image.write_bytes(img)
    log(f"ffcheck {image.name} in {time.monotonic() - t0:.0f} s: data found in {len(found)} all-FF chunks "
        f"{[hex(x) for x in found]}, unresolved {[hex(x) for x in bad]}; SPI opcodes: "
        + ", ".join(f"0x{k:02x} x{v}" for k, v in ops.items()) + f"; sha256 now {sha(image)}")
    return len(bad)


def dump(extra: list[str]) -> int:
    size = chip_size(extra)
    if not size:
        log("stop: chip unknown or > 16 MiB; see RDID in the -V output above")
        return 2
    for n in (1, 2):
        if rc := read_one(n, extra, size):
            return rc
    if (WORK / "dump1.bin").read_bytes() != (WORK / "dump2.bin").read_bytes() and (rc := read_one(3, extra, size)):
        return rc
    return resolve()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["probe", "dump", "read", "resolve", "ffcheck", "exit", "check"])
    ap.add_argument("n", nargs="?", type=int, help="read: read number (file tmp/philips/dump/dump<n>.bin)")
    ap.add_argument("--image", help="ffcheck: resolved image in the store")
    ap.add_argument("--chip", help="flashrom -c name when the probe matches several definitions")
    a = ap.parse_args()
    log(f"=== philips_dump {a.cmd}")
    if a.cmd == "check":
        return 0 if check() else 1
    if a.cmd == "merge":
        return resolve()
    if a.cmd == "exit":
        isp_exit()
        return 0 if check() else 1
    guard()
    extra = ["-c", a.chip] if a.chip else []
    if a.cmd == "probe":
        probe(extra)
        return 0
    if a.cmd == "resolve":
        return resolve()
    if a.cmd == "ffcheck":
        return ffcheck(Path(a.image))
    if a.cmd == "read":
        size = chip_size(extra)
        return read_one(a.n, extra, size) if size else 2
    return dump(extra)


if __name__ == "__main__":
    sys.exit(main())
