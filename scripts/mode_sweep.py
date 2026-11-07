#!/usr/bin/env python3
"""Eyes-free HDMI mode sweep of a test unit: which host modes actually work (awto-ddc#26, #36).

usage: ./dev.py sweep [--unit N] [--dry-run] [--modes WxH@HZ,...] [--label L]
  Per mode: gdctl set (same gdctl_set_args as dev.py mode, other monitors stay put) -> settle -> read firmware mode state,
  measured input timing vs host, P0_02 FIFO flags, FRC on/off (P5_27/P5_AC), DDR PHY flags (pages 8F/CF) when FRC is on
  -> verdict -> back to 1080p60 (rest state). Modes come from `gdctl show --verbose` for the unit's connector.
  Verdicts: OK, OK-FRC, GARBLE (FRC + DDR flags), FIFO, TIMING, NOSUPPORT, POWERSAVE, NOSIGNAL, STATE:<n>, HANG (bus silent -> recover).
Log: tmp/logs/mode_sweep.log (one line per mode), TSV tmp/logs/mode_sweep-<label>-<stamp>.tsv.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import dev  # noqa: E402  (gdctl_set_args, _bus, _fwmap, cmd_recover: the same code paths as dev.py mode/recover)
import dbg_xdata as X  # noqa: E402
import i2cbus  # noqa: E402
import unit_health as H  # noqa: E402

REST = "1920x1080@60.000"
# Settle after gdctl set: modeset ~2-3 s (dev.GDCTL_SET_S note) + HDMI link retrain + firmware SEARCH/DISPLAY_SETTING
# (~3 s at 4K, #26 observation) ~= 6-8 s. No 0x35 traffic during it: the debug ISR NAKs/wedges while the main loop
# re-programs the scaler (wedge seen 2026-11-06), and probing then would read transient states.
SETTLE_S = 7.0
FLAG_REAPPEAR_S = 0.5          # #26: cleared DDR flags are back within ~0.5 s under FRC traffic
GDCTL_SHOW_V_S = 5             # one D-Bus call ~0.1 s, verbose 49 modes; 50x; expiry = abort before any change
# FRC (DDR frame buffer) = P5_27 bit 5: A2/P5_AC 41 in FRC modes, 82/05 in line-buffer modes (dp sweep 2026-11-07, #26).
FRC_BIT = 0x20
DDR_FLAGS = [0x04 + i for i in range(8)] + [0xF1 + i for i in range(7)]      # VALID_WIN_DET SLIC0/1, INT_STATUS1
ROOT = Path(__file__).resolve().parent.parent
LOG = ROOT / "tmp/logs/mode_sweep.log"
RES_NAMES = {3: "ACTIVE", 4: "NOSUPPORT", 5: "NOSIGNAL", 6: "POWERSAVE"}


def say(lf, s: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    lf.write(line + "\n")
    lf.flush()


def host_modes(connector: str) -> list[str]:
    """Mode strings WxH@HZ.HHH of `Monitor <connector>` from `gdctl show --verbose` (49 for HDMI-2 on unit 3)."""
    r = subprocess.run(["gdctl", "show", "--verbose"], capture_output=True, text=True, timeout=GDCTL_SHOW_V_S)
    if r.returncode:
        raise SystemExit(f"sweep: gdctl show --verbose rc={r.returncode}; nothing done")
    out, inside = [], False
    for ln in r.stdout.split("Logical monitors:")[0].splitlines():
        s = ln.strip("│├└─ ")
        if s.startswith("Monitor "):
            inside = s.split(" ")[1] == connector
        elif inside and re.fullmatch(r"\d+x\d+@[\d.]+", s):
            out.append(s)
    if not out:
        raise SystemExit(f"sweep: no modes for {connector} in gdctl show --verbose; nothing done")
    return out


def gdctl_show() -> str:
    r = subprocess.run(["gdctl", "show"], capture_output=True, text=True, timeout=dev.GDCTL_SHOW_S)
    if r.returncode:
        raise SystemExit(f"sweep: gdctl show rc={r.returncode}; nothing changed")
    return r.stdout


def set_mode(u: dict, mode: str) -> tuple[bool, str]:
    """Same command shape as dev.py mode; keeps the other monitors. Fallbacks when mutter refuses the layout:
    scale 1.25/1.5/2 (mode wider than the footprint: dev.py's keep-footprint scale can be unsupported) and
    x right-aligned against the neighbour (mode narrower: gap = 'not adjacent'). REST: scale 1 at the original x."""
    t = u["gdctl"]
    args = dev.gdctl_set_args(gdctl_show(), t, mode)
    w = int(mode.split("x")[0])
    rx = str(int(ORIG_X[0]) + 1920 - w) if ORIG_X and w < 1920 else None
    if mode == REST:
        attempts = [("1", ORIG_X[0] if ORIG_X else None)]
    else:
        attempts = [(None, None)] + ([(None, rx)] if rx else []) + [(sc, x) for sc in OVERLAP_SCALES for x in ([None, rx] if rx else [None])]
    err = ""
    for scale, x in attempts:
        a2 = args if scale is None else with_scale(args, t, scale)
        if x is not None:
            a2 = set_block_val(a2, t, "--x", x)
        try:
            r = subprocess.run(["gdctl", "set", *a2], capture_output=True, text=True, timeout=dev.GDCTL_SET_S)
        except subprocess.TimeoutExpired:
            return False, f"gdctl set timed out after {dev.GDCTL_SET_S} s"
        if r.returncode == 0:
            return True, ", ".join(x_ for x_ in (f"scale {scale}" if scale not in (None, "1") else "", f"x {x}" if x and mode != REST else "") if x_)
        err = r.stderr.strip() or f"rc={r.returncode}"
        if not re.search(r"overlap|adjacent|scale", err):
            break
    return False, err


ORIG_X: list[str] = []          # target's x in the rest layout, recorded at start; every REST set restores it
OVERLAP_SCALES = ["1.25", "1.5", "2"]


def set_block_val_get(args: list[str], target: str) -> str:
    i = args.index(target)
    j = args.index("--logical-monitor", i) if "--logical-monitor" in args[i:] else len(args)
    return args[args.index("--x", i, j) + 1]


def set_block_val(args: list[str], target: str, flag: str, new: str) -> list[str]:
    i = args.index(target)
    j = args.index("--logical-monitor", i) if "--logical-monitor" in args[i:] else len(args)
    k = args.index(flag, i, j)
    return args[:k + 1] + [new] + args[k + 2:]


def with_scale(args: list[str], target: str, scale: str) -> list[str]:
    """args with the target's logical monitor block given --scale <scale> (any existing --scale replaced)."""
    blocks, cur = [], None
    for x in args:
        if x == "--logical-monitor":
            cur = []
            blocks.append(cur)
        cur.append(x)
    out = []
    for b in blocks:
        if target in b:
            while "--scale" in b:
                i = b.index("--scale")
                del b[i:i + 2]
            b += ["--scale", scale]
        out += b
    return out


def sym_map(u: dict) -> tuple[dict, str]:
    mp = Path(dev._fwmap(u, None))
    txt = mp.read_text(errors="replace")
    return {n: H.sym_addr(txt, n) for n in H.MAP_SYMS}, mp.name


def probe(u: dict, maps: dict, host: tuple[int, int, float]) -> dict:
    """One read pass at steady state. Raises H.DbgError / SystemExit when the bus is silent."""
    import rtd_i2c_bridge as B
    from p037_test import rd, wr
    bus = dev._bus(u)
    dbg = H.Dbg(B.Real(bus, allow_write=True))
    base = maps["g_stAwtoDiag"]
    hdr = dbg.read(base, 4)
    dbg.block = X.block_supported(hdr)
    r = {"stage": hdr[3]}
    r["ms"] = H.decode_mode(dbg.read(maps["g_stModeInfo"], 1))
    r["ps"] = H.decode_power(dbg.read(maps["g_stPowerInfo"], 1))[1]
    t = H.decode_timing(dbg.read(maps["g_stMDomainInputData"], 17))
    r["timing"] = f"{t['hwidth']}x{t['vheight']}@{t['vfreq'] / 10:.1f}"
    w, h, hz = host
    r["timing_ok"] = (t["hwidth"], t["vheight"]) == (w, h) and abs(t["vfreq"] - hz * 10) <= H.TIMING_VFREQ_TOL
    d = dbg.io
    r["p0_02"] = rd(d, 0x0002)
    r["p5_27"], r["p5_ac"] = rd(d, 0x0527), rd(d, 0x05AC)
    if None in (r["p0_02"], r["p5_27"], r["p5_ac"]):
        raise H.DbgError("scaler register read NAK")
    r["frc"] = bool(r["p5_27"] & FRC_BIT)
    r["ddr"] = None
    if r["frc"] and r["ms"] == H.MODE_ACTIVE:
        cnt = 0
        for pg in (0x8F, 0xCF):
            for off in DDR_FLAGS:
                wr(d, pg << 8 | off, 0)
        time.sleep(FLAG_REAPPEAR_S)        # waits for: flags to reappear under FRC traffic (#26: ~0.5 s); expiry: read as is
        for pg in (0x8F, 0xCF):
            cnt += sum(1 for off in DDR_FLAGS if (rd(d, pg << 8 | off) or 0) != 0)
        r["ddr"] = cnt
    return r


def verdict(r: dict) -> str:
    ms = r["ms"]
    if ms != H.MODE_ACTIVE:
        return RES_NAMES.get(ms) or f"STATE:{H.MODE_NAMES[ms] if ms < len(H.MODE_NAMES) else ms}"
    if r["ddr"]:
        return "GARBLE"
    if r["p0_02"]:
        return "FIFO"
    if not r["timing_ok"]:
        return "TIMING"
    return "OK-FRC" if r["frc"] else "OK"


def measure(u, maps, mode, lf) -> dict:
    host = H.parse_host_mode(mode)
    for attempt in range(2):               # 0x35 NAKs intermittently at 100 kHz: one retry after 0.5 s, then HANG
        try:
            r = probe(u, maps, host)
            r["verdict"] = verdict(r)
            return r
        except (H.DbgError, SystemExit, OSError) as e:
            err = str(e)
            say(lf, f"  probe failed ({err}); attempt {attempt + 1}/2")
            time.sleep(0.5)
    return {"verdict": "HANG", "err": err}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", default="3")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--modes", help="comma list WxH@HZ (default: all the host offers for the connector)")
    ap.add_argument("--label", default="")
    ap.add_argument("--resume", type=Path, help="TSV of an interrupted sweep: modes already in it (not SETFAIL) are skipped, rows appended")
    ap.add_argument("--recover-image", help="image for dev.py recover on HANG (default: flashed.json image)")
    a = ap.parse_args()
    u = dev._units()[a.unit]
    if not u.get("test"):
        raise SystemExit(f"unit {a.unit} is a working screen; nothing done")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    lf = LOG.open("a")
    modes = a.modes.split(",") if a.modes else host_modes(u["gdctl"])
    # the rest mode first (cheap), then the rest of the list in the host's order
    modes = [m for m in modes if m != REST]
    done = set()
    if a.resume:
        done = {ln.split("\t")[0] for ln in a.resume.read_text().splitlines()[1:] if ln.split("\t")[1] != "SETFAIL"}
        modes = [m for m in modes if m not in done]
    say(lf, f"sweep unit {a.unit} {u['serial']} connector {u['gdctl']}: {len(modes)} modes + rest {REST}")
    if a.dry_run:
        show = gdctl_show()
        for m in modes:
            args = dev.gdctl_set_args(show, u["gdctl"], m)
            say(lf, f"plan {m:<18} gdctl set {' '.join(args)}")
        say(lf, f"plan per mode: set -> settle {SETTLE_S:g} s (no 0x35 traffic) -> probe -> set {REST} -> settle {SETTLE_S:g} s; "
                f"~{len(modes) * (2 * SETTLE_S + 4) / 60:.0f} min total")
        return 0
    if i2cbus.rate_khz() != 100:
        raise SystemExit(f"bus rate {i2cbus.rate_khz()} kHz; the 0x35 probe runs at 100 kHz only; nothing done")
    maps, mapname = sym_map(u)
    ORIG_X[:] = [set_block_val_get(dev.gdctl_set_args(gdctl_show(), u["gdctl"], REST), u["gdctl"])]
    flashed = dev._flashed(u)
    image = a.recover_image or flashed.get("image", "")
    label = a.label or flashed.get("tag", "image")
    tsv = a.resume.resolve() if a.resume else ROOT / f"tmp/logs/mode_sweep-{label}-{time.strftime('%Y%m%d-%H%M%S')}.tsv"
    cols = ["mode", "verdict", "mode_state", "timing", "p0_02", "p5_27", "p5_ac", "frc", "ddr_flag_bytes", "note"]
    tf = tsv.open("a" if a.resume else "w")
    if not a.resume:
        tf.write("\t".join(cols) + "\n")
    say(lf, f"image {label} (map {mapname}); TSV {tsv.relative_to(ROOT)}")
    rc = 0
    for m in ([] if a.resume else [REST]) + modes:
        ok, why = set_mode(u, m)
        if not ok:
            r, note = {"verdict": "SETFAIL", "err": why}, why
            say(lf, f"{m:<18} SETFAIL {why}")
        else:
            time.sleep(SETTLE_S)                     # waits for: modeset + link retrain + fw mode state machine; no bus use
            r = measure(u, maps, m, lf)
            note = r.get("err", "")
            if r["verdict"] == "HANG":
                say(lf, f"{m:<18} HANG ({note}); dev.py recover {image}")
                rc_r = dev.cmd_reset(["--unit", a.unit])          # fast ISP reboot first; recover (relay cycle + reflash) if still silent
                if rc_r == 0:
                    time.sleep(SETTLE_S)                          # waits for: firmware boot + mode detect (same settle as a modeset)
                    r2 = measure(u, maps, m, lf)
                    if r2["verdict"] != "HANG":
                        say(lf, f"{m:<18} after reset: {r2['verdict']}")
                        r, note = {"verdict": "HANG"}, f"bus silent; dev.py reset recovered (then {r2['verdict']})"
                if note.startswith("bus silent"):
                    pass
                elif dev.cmd_recover(["--unit", a.unit, image]) != 0:
                    say(lf, "recover FAILED; stopping with the unit as is")
                    tf.write(f"{m}\tHANG\t\t\t\t\t\t\t\trecover failed\n")
                    return 1
                else:
                    note = "bus silent; recovered by relay cycle + reflash"
            else:
                s = r["ms"]
                say(lf, f"{m:<18} {r['verdict']:<10} state={H.MODE_NAMES[s] if s < len(H.MODE_NAMES) else s} "
                        f"measured={r['timing']} P0_02={r['p0_02']:02X} P5_27={r['p5_27']:02X} P5_AC={r['p5_ac']:02X} "
                        f"frc={'on' if r['frc'] else 'off'} ddr_flag_bytes={r['ddr'] if r['ddr'] is not None else '-'}")
        row = [m, r["verdict"]]
        if "ms" in r:
            row += [H.MODE_NAMES[r["ms"]] if r["ms"] < len(H.MODE_NAMES) else str(r["ms"]), r["timing"],
                    f"{r['p0_02']:02X}", f"{r['p5_27']:02X}", f"{r['p5_ac']:02X}", str(int(r["frc"])),
                    "" if r["ddr"] is None else str(r["ddr"]), note]
        else:
            row += [""] * 7 + [note]
        tf.write("\t".join(row) + "\n")
        tf.flush()
        if m != REST:                                # rest state 1080p60 after EACH mode (Dan's rule)
            ok, why = set_mode(u, REST)
            if not ok:
                say(lf, f"  return to {REST} FAILED: {why}; stopping")
                return 1
            time.sleep(SETTLE_S)
    say(lf, "sweep done; host back at " + REST)
    return rc


if __name__ == "__main__":
    sys.exit(main())
