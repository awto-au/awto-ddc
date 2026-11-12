#!/usr/bin/env python3
"""Render every OSD card, the source selector, the console and the awto menu in one fw_sim boot (awto-ddc#124, #134).

usage: AWTO_SIM_CORE=fast card_shot.py BIN MAP [--out DIR] [--prefix new_] [--mode 1080p60] [--only NAME,...]
- One boot, then per shot: test command bytes (fw/sdcc/awto_testcmd.inc), a wait, a snapshot, then clear (0x27) and MENU.
- Per shot: DIR/<prefix><name>.png = panel at 1/2 size (centring), DIR/<prefix><name>_crop.png = the OSD box at 1x.
- Checks logged per shot: OSD on, box centre vs panel centre (px), box size. A shot whose OSD is off is flagged.
Log: tmp/logs/card_shot.log
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import osd_model as M  # noqa: E402
import osd_render as R  # noqa: E402
import osd_test as T  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/card_shot.log"
CLEAR, K_UP, K_DOWN, K_MENU, K_AUTO, K_SOURCE = 0x27, 0x02, 0x03, 0x04, 0x01, 0x05
# name -> test command bytes; selector steps chain (no clear between them). 0x17 = OSD event 7, the no-signal way in: it also
# arms the SDK power-saving card (3 s, then power saving), so it goes last.
SHOTS = [
    ("selector_source", [K_SOURCE]), ("selector_up", [K_UP]), ("selector_up2", [K_UP]), ("selector_down", [K_DOWN]),
    ("selector_upkey", [K_UP]),
    ("nosignal", [0x50]), ("nocable", [0x51]), ("nosupport", [0x52]), ("failsafe", [0x53]), ("autoadjust", [0x54]),
    ("info", [0x55]), ("autocolour", [0x56]), ("ddcci_port", [0x57]), ("powersaving", [0x58]), ("panel", [0x59]),
    ("info_down", [K_DOWN]), ("console", [0x20]), ("menu", [K_AUTO]), ("selector", [0x17]),
]
CHAIN = {"selector_up", "selector_up2", "selector_down"}


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


def send(s, c):
    addr = s.diag + T.TESTCMD_OFF
    ok = (s.bus.write(0x6A, 0x01, bytes([addr >> 8])) and s.bus.write(0x6A, 0x03, bytes([c]))
          and s.bus.write(0x6A, 0x3B, bytes([addr & 0xFF])))
    if not ok:
        say(f"  test cmd 0x{c:02X} NAK")
    s.bus.wait(0.5)                                  # the main loop consumes one command per pass


def shot(st, out: Path, name: str):
    img = np.array(R.render_snap(st, "grey", 1))
    info = M.summary(st)
    mask = np.any(img != np.array(R.BGS["grey"], np.uint8), axis=2)
    Image.fromarray(img).resize((R.PANEL_W // 2, R.PANEL_H // 2), Image.BOX).save(out)
    if not info["en"] or not mask.any():
        say(f"{name}: OSD OFF / nothing drawn -> {out}")
        return
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    dx = (x0 + x1 + 1) / 2 - R.PANEL_W / 2
    dy = (y0 + y1 + 1) / 2 - R.PANEL_H / 2
    crop = out.with_name(out.stem + "_crop.png")
    Image.fromarray(img[max(0, y0 - 16):y1 + 17, max(0, x0 - 16):x1 + 17]).save(crop)
    say(f"{name}: box {x1 - x0 + 1}x{y1 - y0 + 1} px at ({x0},{y0}), centre offset ({dx:+.1f},{dy:+.1f}) px, "
        f"grid {info['cols']}x{info['rows']}, {info['nwin']} windows -> {crop}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/card_port")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--only", default="")
    ap.add_argument("--wait", type=float, default=1.0, help="sim seconds after the last command before the snapshot")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    only = set(filter(None, a.only.split(",")))
    say(f"{a.bin.name}: shots -> {a.out}/{a.prefix}*")
    s = R.Session(a.bin, a.map, a.mode)
    try:
        s.boot()
        for name, cmds in SHOTS:
            if only and name not in only:
                continue
            if name not in CHAIN:
                send(s, CLEAR)
                send(s, K_MENU)                      # closes an awto menu / selector left open
            for c in cmds:
                send(s, c)
            s.bus.wait(a.wait)
            shot(s.snap(), a.out / f"{a.prefix}{name}.png", name)
    finally:
        s.bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
