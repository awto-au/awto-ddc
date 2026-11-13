#!/usr/bin/env python3
"""Render every OSD card, the source selector, the console and the awto menu in one fw_sim boot (awto-ddc#124, #134).

usage: AWTO_SIM_CORE=fast card_shot.py BIN MAP [--out DIR] [--prefix new_] [--mode 1080p60] [--only NAME,...]
- One boot, then per shot: test command bytes (fw/test/testcmd.c), a wait, a snapshot, then clear (0x27) and MENU.
- Per shot: DIR/<prefix><name>.png = panel at 1/2 size (centring), DIR/<prefix><name>_crop.png = the OSD box at 1x.
- Checks logged per shot: OSD on, box centre vs panel centre (px), box size. A shot whose OSD is off is flagged.
- --bg grey,white,black,bars: one render per test picture (name_<bg>.png when several); --opaque: also name_<bg>_opaque.png
  with blending off in the model (transparency comparison, awto-ddc#176). Blend model: osd_model.render / blend_alpha.
  DIR/<prefix>sheet.png: every crop, one row per shot, one column per picture (+ opaque), tiles at most SHEET_H px high.
Log: tmp/logs/card_shot.log
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
import osd_model as M  # noqa: E402
import osd_render as R  # noqa: E402
import osd_test as T  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
LOG = ROOT / "tmp/logs/card_shot.log"
CLEAR, K_UP, K_DOWN, K_MENU, K_AUTO, K_SOURCE, CON_CLOSE = 0x27, 0x02, 0x03, 0x04, 0x01, 0x05, 0x44
# name -> test command bytes; selector steps chain (no clear between them). 0x17 = OSD event 7, the no-signal way in: it also
# arms the SDK power-saving card (3 s, then power saving), so it goes last.
SHOTS = [
    ("selector_source", [K_SOURCE]), ("selector_up", [K_UP]), ("selector_up2", [K_UP]), ("selector_down", [K_DOWN]),
    ("selector_upkey", [K_UP]),
    ("nosignal", [0x50]), ("nocable", [0x51]), ("nosupport", [0x52]), ("failsafe", [0x53]), ("autoadjust", [0x54]),
    ("info", [0x55]), ("autocolour", [0x56]), ("ddcci_port", [0x57]), ("powersaving", [0x58]), ("panel", [0x59]),
    ("info_down", [K_DOWN]), ("console", [0x20]), ("gpio", [0x43]), ("backlight", [CON_CLOSE, K_UP]), ("selector_key", [K_SOURCE]),
    ("awto_menu", [K_MENU, K_MENU]), ("menu", [K_AUTO]), ("selector", [0x17]),
]
CHAIN = {"selector_up", "selector_up2", "selector_down", "backlight", "selector_key", "awto_menu"}   # after gpio: console closed, UP /
# SOURCE with nothing open; MENU closes the selector, MENU again opens the awto menu


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


SHEET_H = 420                                    # sheet tile height cap, px (the console crop is 1836 px high)


def sheet(cells: dict, out: Path):
    """cells: (name, column label) -> crop path; rows in shot order, columns in first-seen order"""
    names = list(dict.fromkeys(n for n, _ in cells))
    cols = list(dict.fromkeys(c for _, c in cells))
    tiles = {}
    for k, p in cells.items():
        im = Image.open(p)
        if im.height > SHEET_H:
            im = im.resize((im.width * SHEET_H // im.height, SHEET_H), Image.BOX)
        tiles[k] = im
    cw = [max((tiles[n, c].width for n in names if (n, c) in tiles), default=0) + 8 for c in cols]
    rh = [max((tiles[n, c].height for c in cols if (n, c) in tiles), default=0) + 8 for n in names]
    lab = 16
    img = Image.new("RGB", (sum(cw), sum(rh) + lab), (40, 40, 40))
    d = ImageDraw.Draw(img)
    x = 0
    for j, c in enumerate(cols):
        d.text((x + 4, 2), c, fill=(255, 255, 255))
        y = lab
        for i, n in enumerate(names):
            if (n, c) in tiles:
                img.paste(tiles[n, c], (x + 4, y + 4))
            y += rh[i]
        x += cw[j]
    img.save(out)
    say(f"sheet {len(names)} shots x {len(cols)} pictures -> {out}")


def shot(st, out: Path, name: str, bg: str = "grey", opaque: bool = False):
    img = np.array(R.render_snap(st, bg, 1, opaque))
    info = M.summary(st)
    mask = np.any(img != R.background(bg, R.PANEL_W, R.PANEL_H), axis=2)
    Image.fromarray(img).resize((R.PANEL_W // 2, R.PANEL_H // 2), Image.BOX).save(out)
    if not info["en"] or not mask.any():
        say(f"{name}: OSD OFF / nothing drawn -> {out}")
        return None
    ys, xs = np.nonzero(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    dx = (x0 + x1 + 1) / 2 - R.PANEL_W / 2
    dy = (y0 + y1 + 1) / 2 - R.PANEL_H / 2
    crop = out.with_name(out.stem + "_crop.png")
    Image.fromarray(img[max(0, y0 - 16):y1 + 17, max(0, x0 - 16):x1 + 17]).save(crop)
    say(f"{name} [{bg}{' opaque' if opaque else ''}]: box {x1 - x0 + 1}x{y1 - y0 + 1} px at ({x0},{y0}), centre offset "
        f"({dx:+.1f},{dy:+.1f}) px, grid {info['cols']}x{info['rows']}, {info['nwin']} windows, blend type "
        f"{info['blend_type']} level {round(M.blend_alpha(st) * 256)}/256 -> {crop}")
    return crop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/card_port")
    ap.add_argument("--prefix", default="")
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--only", default="")
    ap.add_argument("--wait", type=float, default=1.0, help="sim seconds after the last command before the snapshot")
    ap.add_argument("--bg", default="grey", help="test pictures, comma separated: " + ", ".join([*R.BGS, "checker", "bars"]))
    ap.add_argument("--opaque", action="store_true", help="also render each shot with blending off (model)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    only = set(filter(None, a.only.split(",")))
    say(f"{a.bin.name}: shots -> {a.out}/{a.prefix}*")
    cells = {}
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
            st = s.snap()
            bgs = a.bg.split(",")
            for bg in bgs:
                stem = f"{a.prefix}{name}" + (f"_{bg}" if len(bgs) > 1 else "")
                for op in (False, True) if a.opaque else (False,):
                    c = shot(st, a.out / f"{stem}{'_opaque' if op else ''}.png", name, bg, op)
                    if c:
                        cells[name, bg + (" opaque" if op else "")] = c
    finally:
        s.bus.close()
    if cells:
        sheet(cells, a.out / f"{a.prefix}sheet.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
