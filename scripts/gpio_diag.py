#!/usr/bin/env python3
"""Input monitor over the running firmware's debug I2C slave 0x35.

`_g_stAwtoGpio` holds the current value of every input in the firmware table (fw/awto/inputs.tsv in awto-ddc-ui, read here for
names and pins) and a 32-entry change ring (5 B: seq, tick, input id, value). `snapshot` prints all values; `watch` follows the ring,
reading the 16-byte header and the ring only when its sequence moves. `open`/`close` drive the console through the test-command byte.
"""
import argparse, os, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X
import i2cbus
import rtd_i2c_bridge as B

INPUTS_TSV = Path(os.environ.get("AWTO_DDC_UI", "/mnt/2tb/git/awto-ddc-ui")) / "fw/awto/inputs.tsv"   # the firmware's input table (same index = ring id)
HDR_N, ENTRY_N, LOG_N = 16, 5, 32
DEV8, TESTCMD_OFF = 0x6A, 0x28


def load_inputs(path: Path = INPUTS_TSV) -> list:
    """[(name, pin, kind, text, screen, log)] in firmware index order."""
    out = []
    for ln in path.read_text().splitlines():
        if ln.strip() and not ln.startswith("#"):
            n, pin, kind, _src, _a, _b, text, screen, lg = ln.split("\t")
            out.append((n, int(pin), kind, text, screen == "y", lg == "y"))
    return out


def symbol(text: str, name: str) -> int:
    # SDCC emits some absolute XDATA symbols without the leading ``D:`` that
    # it uses for relocatable data symbols.  Both forms are data addresses.
    m = re.search(rf"^(?:D:\s+|\s+)([0-9A-Fa-f]{{8}})\s+_{re.escape(name)}\b", text, re.M)
    if not m:
        raise SystemExit(f"_{name} is not present in this image map")
    return int(m.group(1), 16)


def read_stable(io, addr: int, n: int):
    """Header + value table + ring in one consistent read (re-read when the ring sequence moved meanwhile)."""
    total = HDR_N + n + LOG_N * ENTRY_N
    for _ in range(4):
        data = X.read_blocks(io, addr, total)
        tail = X.read_blocks(io, addr, HDR_N)
        if data and tail and data[:2] == b"GP" and data[2] == 4 and data[7] == n and data[5] == tail[5]:
            return data
    raise SystemExit("input monitor block was changing, unreadable, or not version 4 (image older than txt17?)")


def label(ins, idx: int) -> str:
    if idx >= len(ins):
        return f"input{idx}"
    n, pin, *_ = ins[idx]
    return f"{n}({pin})" if pin else n


def show_snapshot(data: bytes, ins: list) -> None:
    vals = data[HDR_N:HDR_N + len(ins)]
    groups = (("GPIO", ("GPIO",)), ("ADC", ("ADC0", "ADC1", "ADC2")), ("POWER", ("POWER",)), ("KEYS", ("SOURCE", "MENU", "DOWN", "UP", "AUTO")))
    line = []
    for gname, names in groups:
        cells = []
        for i, (n, pin, kind, text, scr, lg) in enumerate(ins):
            if n in names:
                v = vals[i]
                cells.append(f"{label(ins, i)}={v}({v * 3.3 / 255:.3f}V)" if kind == "analog" else f"{label(ins, i)}={v}")
        line.append(f"{gname}: " + " ".join(cells))
    print("snapshot " + "  ".join(line) + f"  VGA_SYNC=0x{vals[[i for i, x in enumerate(ins) if x[0] == 'AVS'][0]]:02x} VGA_CMP=0x{vals[[i for i, x in enumerate(ins) if x[0] == 'BM'][0]]:02x}  transitions={data[5]}")
    io = [(i, x) for i, x in enumerate(ins) if x[3] in ("IN", "OUT")]
    print("board IO inputs: " + " ".join(f"{label(ins, i)}={vals[i]}" for i, x in io if x[3] == "IN"))
    print("board IO outputs read back: " + " ".join(f"{label(ins, i)}={vals[i]}" for i, x in io if x[3] == "OUT"))


def write_cmd(io, diag: int, cmd: int) -> None:
    a = diag + TESTCMD_OFF
    ok = (io.write(DEV8, 0x01, bytes([a >> 8])) and io.write(DEV8, 0x03, bytes([cmd])) and
          io.write(DEV8, 0x3B, bytes([a & 0xFF])))
    if not ok:
        raise SystemExit(f"I2C write of GPIO OSD command 0x{cmd:02x} failed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("command", choices=("snapshot", "watch", "open", "close"), nargs="?", default="snapshot")
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--secs", type=float, default=30.0)
    ap.add_argument("--inputs", type=Path, default=INPUTS_TSV, help="the firmware input table the image was built from")
    a = ap.parse_args()
    i2cbus.require_unit(a.bus, a.serial)
    ins = load_inputs(a.inputs)
    mp = a.map.read_text(errors="replace")
    base, diag = symbol(mp, "g_stAwtoGpio"), symbol(mp, "g_stAwtoDiag")
    logs = B.setup_logs("gpio_diag", map=str(a.map))
    io = B.Real(a.bus, allow_write=True)
    try:
        if a.command in ("open", "close"):
            write_cmd(io, diag, 0x43 if a.command == "open" else 0x44)
            print(f"GPIO input screen {a.command} command sent")
            return 0
        data = read_stable(io, base, len(ins))
        show_snapshot(data, ins)
        if a.command == "snapshot":
            return 0
        last = data[5]
        end = time.monotonic() + a.secs
        while time.monotonic() < end:
            h = X.read_blocks(io, base, HDR_N)
            if not h or h[:2] != b"GP":
                time.sleep(0.02)
                continue
            cur = h[5]
            if cur == last:
                time.sleep(0.02)
                continue
            data = read_stable(io, base, len(ins))
            cur = data[5]
            delta = (cur - last) & 0xFF
            if delta > LOG_N:
                print(f"lost {delta - LOG_N} transitions (ring holds {LOG_N})")
                last = (cur - LOG_N) & 0xFF
            ring = HDR_N + len(ins)
            while last != cur:
                off = ring + (last & (LOG_N - 1)) * ENTRY_N
                seq, hi, lo, idx, val = data[off:off + ENTRY_N]
                if seq != last:
                    print(f"ring overwrite at sequence {last}; resynchronising")
                    break
                kind = ins[idx][2] if idx < len(ins) else "bit"
                shown = f"{val} ({val * 3.3 / 255:.3f}V)" if kind == "analog" else str(val)
                line = f"seq={seq:03d} tick={(hi << 8 | lo):05d}ms input={label(ins, idx)} value={shown}"
                print(line, flush=True)
                logs.main.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {line}\n"); logs.main.flush()
                last = (last + 1) & 0xFF
            last = cur
        return 0
    finally:
        io.close()


if __name__ == "__main__":
    sys.exit(main())
