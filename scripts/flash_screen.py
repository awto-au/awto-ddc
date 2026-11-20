#!/usr/bin/env python3
"""Flash warning screen (#232): red screen, a static 36 x 36 px Pac-Man (drawn once by the firmware), progress text, while the host flashes.

usage: flash_screen.py show --bus N          start the screen in the running firmware (DDC/CI VCP 0xEB = 5)
       flash_screen.py test --bus N [--ticks K]   show, enter ISP, K updates with fake progress, OSD off, reset (a flash dry run for the screen)
  Library (rtd_flash_image.py): show(bus), tick(isp, n, info) per sector, clear(isp) before the exit reset. Every call is best effort:
  a failure is logged and never fails the flash.
  The firmware (fw/test/flash_screen.c) draws the screen; the OSD circuit keeps it while the MCU is held in ISP; this module rewrites map words
  (char commands) over the ISP F4/F5 window (rtd_osd.Osd): the text rows only, the cells that changed, at most once per THROTTLE_S (5 s);
  a change of the error counts and the last sector draw at once. The Pac-Man is never rewritten.
  Layout = scripts/gen_flash_screen.py. Text rows: 1 bank / sector / percent, 2 interface (env AWTO_FLASH_IFACE, set by dev.py), 3 errors.
  Display Rotate 180 (marker file): logical cell c is written at cells - 1 - c; the firmware already turned the glyphs.
Log: ./tmp/logs/flash_screen.log
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import isostamp
from ddcutil_run import ddc as _ddc

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gen_flash_screen as L

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/flash_screen.log"
BUS = None                      # set by show() / the flasher: one marker per bus so flashes of several units can run in parallel
# marker: written by show() (JSON: rot), read by tick / clear in the flasher process, removed by clear
VCP_SAVER = 0xEB
VCP_FLASH_SCREEN = 5            # screensaver_now value "Flash warning" (registry row 121)
VCP_PAGED_ID, VCP_PAGED_VAL = 0xE0, 0xE1
ROW_DISP_ROTATE = 32            # registry row id of disp_rotate
DRAW_WAIT_S = 0.6               # firmware draws in one main-loop pass: ~330 cells + 90 glyphs of data port writes (~0.1 s) after the DDC write; 6 x
THROTTLE_S = 5.0                # text rows redraw at most once per 5 s on every bus (Dan 2026-11-20); errors and the last sector draw at once
ENV_IFACE = "AWTO_FLASH_IFACE"
ENV_OFF = "AWTO_FLASH_SCREEN_OFF"   # =1: never show (a flash from an image whose screen layout differs from this script)
# Values mirrored from fw/test/flash_screen.c (tests/test_flash_screen.py checks them)
CHAR_B0 = 0x4C
FG_SHIFT = 4
BG, YELLOW, WHITE = 1, 2, 3
CHAR_WORD = L.ROWS + 1          # first char command word (row commands 0..ROWS-1, end word ROWS)
CELLS = L.COLS * L.ROWS

_prev: dict[int, int] = {}      # logical cell -> glyph id last written (this process)
_next_at = 0.0                  # monotonic time of the next allowed redraw
_errs: tuple = ()               # (bad, recov) at the last redraw
_rot = 0


def _marker() -> Path:
    return ROOT / f"tmp/flash_screen.{BUS}.shown"


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def _vcp_max(bus: int) -> int:
    """Highest value the running firmware accepts for VCP 0xEB (the registry row's max); 0 when it does not answer."""
    r = _ddc(bus, "getvcp", f"{VCP_SAVER:02X}")
    m = re.search(r"ml=0x([0-9a-f]+)", r.stdout) if r else None
    return int(m.group(1), 16) if m else 0


def _rotated(bus: int) -> int:
    """1 when display Rotate 180 is stored (registry row 32 through the paged pair 0xE0 / 0xE1)."""
    if _ddc(bus, "setvcp", f"{VCP_PAGED_ID:02X}", str(ROW_DISP_ROTATE)) is None:
        return 0
    r = _ddc(bus, "getvcp", f"{VCP_PAGED_VAL:02X}")
    m = re.search(r"sl=0x([0-9a-f]+)", r.stdout) if r else None
    return 1 if m and int(m.group(1), 16) == 1 else 0


def show(bus: int) -> bool:
    """Ask the running firmware for the screen. False = not shown (old firmware, DDC busy): the flash goes on without it."""
    global BUS
    BUS = bus
    _marker().unlink(missing_ok=True)
    if os.environ.get(ENV_OFF) == "1":
        say(f"show: {ENV_OFF}=1: no flash screen")
        return False
    top = _vcp_max(bus)
    if top < VCP_FLASH_SCREEN:                              # an older image clamps the value to its max (a scope would start instead)
        say(f"show: firmware accepts VCP {VCP_SAVER:02X} up to {top} < {VCP_FLASH_SCREEN}: no flash screen this time")
        return False
    rot = _rotated(bus)
    ok = _ddc(bus, "setvcp", f"{VCP_SAVER:02X}", str(VCP_FLASH_SCREEN)) is not None
    say(f"show: setvcp {VCP_SAVER:02X} {VCP_FLASH_SCREEN} on bus {bus} (rotate 180: {rot}): {'ok' if ok else 'FAILED'}")
    if ok:
        _marker().parent.mkdir(parents=True, exist_ok=True)
        _marker().write_text(json.dumps({"rot": rot, "at": isostamp.now()}))
        time.sleep(DRAW_WAIT_S)
    return ok


def _osd(isp):
    import rtd_osd as O
    o = O.Osd.__new__(O.Osd)            # the flasher's ISP session, not a second one
    o.isp, o.path, o.page, o.halted = isp, "f4f5", None, True
    return o


def _mmss(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 60:02d}:{sec % 60:02d}"


def rows_text(info: dict) -> list[str]:
    """The five text rows for a progress dict: phase, bank, addr, sec, nsec, pct, iface, bad, recov, t (s since the first sector); optional skip + nimg."""
    eta = info["t"] * (info["nsec"] - info["sec"]) / info["sec"] if info["sec"] else 0
    skip = f" SKIP {info['skip']}/{info['nimg']}" if info.get("nimg") else ""     # sectors already matching / image sectors
    return [f"{info['phase']} BANK {info['bank']:02d}/{info['nbank']:02d}{skip}",
            f"ADDR {info['addr']:05X} SEC {info['sec']}/{info['nsec']} {info['pct']}%",
            info.get("iface") or os.environ.get(ENV_IFACE, ""),
            f"BURST FAIL {info['bad']} RECOVER {info['recov']}",
            f"TIME {_mmss(info['t'])} ETA {_mmss(eta)}"]


def _cells(info: dict) -> dict[int, int]:
    """Logical cell -> glyph id for everything the host owns: the text rows."""
    out = {}
    for row, txt in zip(L.ROW_LINES, rows_text(info)):
        for c, g in enumerate(L.ids(txt.upper().replace("_", "-"))):
            out[row * L.COLS + c] = g
    return out


def _put(o, cell: int, gid: int) -> None:
    phys = CELLS - 1 - cell if _rot else cell
    o.write_word(CHAR_WORD + phys, CHAR_B0, gid, (WHITE << FG_SHIFT) | BG)


def due(info: dict, now: float) -> bool:
    """Redraw when the THROTTLE_S deadline passed, the error counts changed, or this is the last sector (100 %)."""
    return now >= _next_at or (info["bad"], info["recov"]) != _errs or info["sec"] >= info["nsec"]


def tick(isp, n: int, info: dict) -> None:
    """Update the text rows for sector n (changed cells only), at most once per THROTTLE_S; errors and the last sector at once."""
    global _rot, _next_at, _errs
    if not _marker().exists():
        return
    now = time.monotonic()
    if _prev and not due(info, now):
        return
    try:
        import rtd_osd as O
        if not _prev:
            _rot = json.loads(_marker().read_text()).get("rot", 0)
        o = _osd(isp)
        o.set_opt(O.SRAM_FONT)
        for cell, gid in _cells(info).items():
            if _prev.get(cell) != gid:
                _put(o, cell, gid)
                _prev[cell] = gid
        _errs = (info["bad"], info["recov"])
        _next_at = now + THROTTLE_S
    except Exception as e:                                  # noqa: BLE001 - best effort: never fail a flash for the picture
        import traceback
        say(f"tick {n}: {e!r}: " + " <- ".join(f"{f.name}:{f.lineno}" for f in reversed(traceback.extract_tb(e.__traceback__)[-5:])))


def clear(isp) -> None:
    """OSD circuit off before the exit reset: the new firmware starts with an empty OSD."""
    global _next_at, _errs
    if not _marker().exists():
        return
    _marker().unlink(missing_ok=True)
    _prev.clear()
    _next_at, _errs = 0.0, ()
    try:
        _osd(isp).osd_enable(False)
        say("clear: OSD off")
    except Exception as e:                                  # noqa: BLE001
        say(f"clear: {e!r}")


def test(bus: int, ticks: int) -> int:
    import rtd_isp_probe as P
    import rtd_osd as O
    if not show(bus):
        return 1
    P.LOG = (ROOT / "tmp/logs/flash_screen_isp.log").open("a")          # rtd_osd logs through the probe module
    o = O.Osd(bus)
    o.enter()
    os.environ.setdefault(ENV_IFACE, "I2C DDC 100KHZ BURST")
    for k in range(ticks):
        tick(o.isp, k, {"phase": ("BANKED", "BANK0", "COMMON", "BOOT")[k * 4 // ticks], "bank": k * 14 // max(1, ticks - 1), "nbank": 15, "addr": k * 0x10000 + 0x1000,
                        "sec": k * 10 + 1, "nsec": ticks * 10, "pct": k * 100 // max(1, ticks - 1), "bad": k // 3, "recov": 0, "t": k * 7.0})
        time.sleep(0.5)                                     # human-visible pacing for the dry run only
    clear(o.isp)
    o.reset()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("show", "test"))
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--ticks", type=int, default=12)
    a = ap.parse_args()
    if a.cmd == "show":
        show(a.bus)                                         # not shown = logged, not an error: the flash goes on
        return 0
    return test(a.bus, a.ticks)


if __name__ == "__main__":
    sys.exit(main())
