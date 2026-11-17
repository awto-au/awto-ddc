#!/usr/bin/env python3
"""Flash warning screen (#232): a huge Pac-Man on red while the host flashes, mouth opening / closing per sector.

usage: flash_screen.py show --bus N          start the screen in the running firmware (DDC/CI VCP 0xEB = 5)
       flash_screen.py test --bus N [--ticks K]   show, enter ISP, K mouth toggles, OSD off, reset (a flash dry run for the screen)
  Library (rtd_flash_image.py): show(bus), tick(isp, n) between sectors, clear(isp) before the exit reset. Every call is best effort:
  a failure is logged and never fails the flash.
  The firmware (fw/test/flash_screen.c) draws the screen; the OSD circuit keeps it while the MCU is held in ISP; this module only swaps the
  glyph id of the one map cell (font / map SRAM word FS_CHAR_WORD) over the ISP F4/F5 window (rtd_osd.Osd), and turns the OSD off at the end.
Log: ./tmp/logs/flash_screen.log
"""
import argparse
import os
import re
import subprocess
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/flash_screen.log"
C_SRC = ROOT / "fw/test/flash_screen.c"
VCP_SAVER = 0xEB
VCP_FLASH_SCREEN = 5            # screensaver_now value "Flash warning" (registry row 121)
DRAW_WAIT_S = 0.6               # firmware: the draw is one main-loop pass (~50 ms of data port writes) after the DDC write; 12 x
DDC_LIMIT_S = 20                # ddcutil retries a busy unit for up to ~10 s; expiry = the screen is skipped, the flash goes on
# Values mirrored from fw/test/flash_screen.c (tests/test_flash_screen.py checks them): the char command of the one cell
MARKER = ROOT / "tmp/flash_screen.shown"   # written by show(), read by tick / clear in the flasher process, removed by clear
FS_CHAR_WORD = 2
CHAR_B0 = 0x4C
CHAR_B2 = 0x21
GLYPH_OPEN, GLYPH_CLOSED = 0, 1


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def _vcp_max(bus: int) -> int:
    """Highest value the running firmware accepts for VCP 0xEB (the registry row's max); 0 when it does not answer."""
    try:
        r = subprocess.run(["ddcutil", "--bus", str(bus), "getvcp", f"{VCP_SAVER:02X}"], capture_output=True, text=True, timeout=DDC_LIMIT_S)
    except (OSError, subprocess.TimeoutExpired):
        return 0
    m = re.search(r"ml=0x([0-9a-f]+)", r.stdout)
    return int(m.group(1), 16) if m else 0


def show(bus: int) -> bool:
    """Ask the running firmware for the screen. False = not shown (old firmware, DDC busy): the flash goes on without it."""
    MARKER.unlink(missing_ok=True)
    top = _vcp_max(bus)
    if top < VCP_FLASH_SCREEN:                              # an older image clamps the value to its max (a scope would start instead)
        say(f"show: firmware accepts VCP {VCP_SAVER:02X} up to {top} < {VCP_FLASH_SCREEN}: no flash screen this time")
        return False
    try:
        r = subprocess.run(["ddcutil", "--bus", str(bus), "setvcp", f"{VCP_SAVER:02X}", str(VCP_FLASH_SCREEN)],
                           capture_output=True, text=True, timeout=DDC_LIMIT_S)
    except (OSError, subprocess.TimeoutExpired) as e:
        say(f"show: ddcutil failed ({e!r}); no flash screen")
        return False
    ok = r.returncode == 0
    say(f"show: setvcp {VCP_SAVER:02X} {VCP_FLASH_SCREEN} on bus {bus}: {'ok' if ok else 'FAILED ' + r.stderr.strip()[:120]}")
    if ok:
        MARKER.parent.mkdir(parents=True, exist_ok=True)
        MARKER.write_text(isostamp.now())
        time.sleep(DRAW_WAIT_S)
    return ok


def _osd(isp):
    import rtd_osd as O
    o = O.Osd.__new__(O.Osd)            # the flasher's ISP session, not a second one
    o.isp, o.path, o.page, o.halted = isp, "f4f5", None, True
    return o


def tick(isp, n: int) -> None:
    """Mouth open on even n, closed on odd n."""
    if not MARKER.exists():
        return
    try:
        import rtd_osd as O
        o = _osd(isp)
        o.set_opt(O.SRAM_FONT)
        o.write_word(FS_CHAR_WORD, CHAR_B0, GLYPH_CLOSED if n % 2 else GLYPH_OPEN, CHAR_B2)
    except Exception as e:                                  # noqa: BLE001 - best effort: never fail a flash for the picture
        say(f"tick {n}: {e!r}")


def clear(isp) -> None:
    """OSD circuit off before the exit reset: the new firmware starts with an empty OSD."""
    if not MARKER.exists():
        return
    MARKER.unlink(missing_ok=True)
    try:
        _osd(isp).osd_enable(False)
        say("clear: OSD off")
    except Exception as e:                                  # noqa: BLE001
        say(f"clear: {e!r}")


def test(bus: int, ticks: int) -> int:
    import rtd_osd as O
    if not show(bus):
        return 1
    o = O.Osd(bus)
    o.enter()
    for k in range(ticks):
        tick(o.isp, k)
        time.sleep(0.3)                                     # human-visible blink for the dry run only
    clear(o.isp)
    o.reset()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=("show", "test"))
    ap.add_argument("--bus", type=int, required=True)
    ap.add_argument("--ticks", type=int, default=8)
    a = ap.parse_args()
    return (0 if show(a.bus) else 1) if a.cmd == "show" else test(a.bus, a.ticks)


if __name__ == "__main__":
    sys.exit(main())
