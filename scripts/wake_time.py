#!/usr/bin/env python3
"""Wake time (#78): host DPMS off -> on, firmware switch log (StAwtoSw) decoded per phase, ms from the host's DPMS-on.

usage: wake_time.py <bus> --serial S --map MAP [--off-s 3] [--runs N] [--label L]
- Arms g_stAwtoSw from the host (XDATA writes over 0x35: ucN = 0, usT0 = Timer2 count), so any image with the #60 log works.
- DPMS via Mutter PowerSaveMode (busctl; 3 = off, 0 = on): every monitor of this desktop blanks for --off-s.
- Host timestamps: busctl call, then the connector's sysfs dpms "On". Firmware ms are mapped by the arm's host time.
- Ends when the log shows UNBLANK / BACKLIGHT_ON after the DPMS-on, or WAKE_LIMIT_S passes.
Log: ./tmp/logs/wake_time.log (decoded lines)
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dbg_xdata as X  # noqa: E402
import i2cbus  # noqa: E402
import rtd_i2c_bridge as B  # noqa: E402
import sw_timeline as T  # noqa: E402

DIAG_T2 = 22                # StAwtoDiag.usT2Isr offset (RL6449_Project.h)
WAKE_LIMIT_S = 6.0          # full-path wake: 1.0-1.2 s mode ACTIVE at cold boot (#63) + search 3 s worst; expiry = logged FAIL
POLL_S = 0.05               # log poll while waking: 50 ms resolution on the stop condition only (event times are firmware ms)
MUTTER = ["busctl", "--user", "set-property", "org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
          "org.gnome.Mutter.DisplayConfig", "PowerSaveMode", "i"]
PICTURE = {(0x80, 0)}                    # UNBLANK (blank event arg 0); the SDK path turns the backlight on in the same ms


def sym(map_path: Path, name: str) -> int:
    import re
    m = re.search(rf"^(?:D:)?\s+([0-9A-F]{{8}})\s+_{name}\b", map_path.read_text(errors="replace"), re.M)
    if not m:
        raise SystemExit(f"{name} not in {map_path}")
    return int(m.group(1), 16) & 0xFFFF


def wr(io, addr: int, val: int) -> bool:
    return (io.write(X.DEV8, 0x01, bytes([addr >> 8])) and io.write(X.DEV8, 0x03, bytes([val]))
            and io.write(X.DEV8, 0x3B, bytes([addr & 0xFF])))


def arm(io, sw: int, diag: int) -> float:
    t2 = X.read_blocks(io, diag + DIAG_T2, 2)
    t_host = time.monotonic()
    if t2 is None or not (wr(io, sw + 4, t2[0]) and wr(io, sw + 5, t2[1]) and wr(io, sw + 3, 0)):
        raise SystemExit("arm: 0x35 write/read failed")
    return t_host


def dpms(conn: str, on: bool, limit_s: float = 3.0) -> float:
    """Mutter PowerSaveMode; returns host time when sysfs dpms reached the state (limit: one modeset ~0.3 s x ~10)."""
    subprocess.run(MUTTER + ["0" if on else "3"], check=True, timeout=5)
    t0 = time.monotonic()
    want = "On" if on else "Off"
    p = Path("/sys/class/drm") / conn / "dpms"
    while time.monotonic() - t0 < limit_s:
        if p.read_text().strip() == want:
            return time.monotonic()
        time.sleep(0.005)       # 5 ms: resolution of the host-side timestamp
    raise SystemExit(f"dpms {want}: {conn} not {want} after {limit_s} s")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bus", type=int)
    ap.add_argument("--serial", required=True)
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--conn", default="card1-HDMI-A-2")
    ap.add_argument("--off-s", type=float, default=3.0)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--label", default="")
    ap.add_argument("--watch-s", type=float, help="no DPMS: arm, wait this long, decode (what the unit does on its own)")
    a = ap.parse_args()
    root = Path(__file__).resolve().parent.parent
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lf = (root / "tmp/logs/wake_time.log").open("a", buffering=1)

    def say(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line)
        lf.write(line + "\n")

    i2cbus.require_unit(a.bus, a.serial)
    sw, diag = sym(a.map, "g_stAwtoSw"), sym(a.map, "g_stAwtoDiag")
    io = B.Real(a.bus, allow_write=True, regread=True)
    rc = 0
    if a.watch_s is not None:
        t_arm = arm(io, sw, diag)
        time.sleep(a.watch_s)       # the observation window asked for
        raw = X.read_blocks(io, sw, 12 + 4 * T.N_EV)
        io.close()
        if raw is None:
            say("watch: log read failed"); return 1
        hdr, evs = T.decode(raw)
        say(f"watch {a.watch_s:.1f} s {a.label}: {hdr['n']} events")
        for ms, i, g in evs:
            say(f"  +{ms:7d} ms  {T.name(i, g)}")
        return 0
    try:
        for run in range(a.runs):
            t_arm = arm(io, sw, diag)
            t_off = dpms(a.conn, False)
            time.sleep(a.off_s)     # the off period under test (no-signal / power-saving depth)
            t_cmd = time.monotonic()
            t_on = dpms(a.conn, True)
            on_ms = (t_on - t_arm) * 1000
            evs, hit = [], None
            while time.monotonic() - t_on < WAKE_LIMIT_S:
                raw = X.read_blocks(io, sw, 12 + 4 * T.N_EV)
                if raw is not None:
                    _h, evs = T.decode(raw)
                    hit = next((ms for ms, i, g in evs if (i, g) in PICTURE and ms >= on_ms - 50), None)
                    if hit is not None:
                        break
                time.sleep(POLL_S)
            say(f"run {run + 1} {a.label}: off {a.off_s:.1f} s; host DPMS-on call -> sysfs On {(t_on - t_cmd) * 1000:.0f} ms; "
                f"picture {'%.0f ms after sysfs On' % (hit - on_ms) if hit is not None else 'NOT seen in %.1f s' % WAKE_LIMIT_S}")
            for ms, i, g in evs:
                say(f"  {ms - on_ms:+7.0f} ms  {T.name(i, g)}")
            if hit is None:
                rc = 1
            time.sleep(4.0)         # > AWTO_REHOLD_MS (3 s): the next off may hold again; one info pop-up is 6 s, not counted
    finally:
        subprocess.run(MUTTER + ["0"], timeout=5)
        io.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
