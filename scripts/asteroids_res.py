#!/usr/bin/env python3
"""Asteroids canvas-resolution variants in the firmware sim (docs/asteroids-resolution.md). Nothing touches hardware.

usage: asteroids_res.py build [NAME ...] | cost [NAME ...] [--window S] | render [NAME ...] [--seconds S] | compare
  build   one image per variant: `dev.py build --unit 3 --tag ar-NAME -D AWTO_AST_COLS / ROWS / RES -D AWTO_SAVER_INFO=_OFF` (XDATA floor off).
  cost    saver_frame_cost.py --case asteroids per image -> tmp/logs/asteroids_res.tsv (frames/s, instr, saver ms, port bytes per frame).
  render  runs the saver, captures every AwtoScTile upload (cell = address -> tile bits), writes the canvas + the panel-scale picture
          tmp/asteroids_res/NAME.png (canvas, nearest-neighbour to the panel as the OSD scale-up).
  compare one picture: the same panel crop of every rendered variant side by side -> tmp/asteroids_res/compare.png
Variants: name -> (cols, rows, res); res 1 = objects 2 x larger in px (finer pixels at the same screen size).
Log: ./tmp/logs/asteroids_res.log
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/asteroids_res.log"
TSV = ROOT / "tmp/logs/asteroids_res.tsv"
OUT = ROOT / "tmp/asteroids_res"
SERIAL = "AWT26110003"
TILE_W, TILE_H, TILE_B = 12, 18, 27
PANEL_W, PANEL_H = 3840, 2160
VARIANTS = {                                   # name: (cols, rows, res)
    "c30x11": (30, 11, 0),                     # today, info overlay off
    "c35x13": (35, 13, 0),                     # 420 x 234, scale 7, identity glyph map (455 of 512 ids): fits as is
    "c40x15": (40, 15, 0),                     # 480 x 270, scale 8 (as Scope 2)
    "c60x22": (60, 22, 0),                     # 720 x 396, same px objects (smaller on screen)
    "c80x30": (80, 30, 0),                     # 960 x 540
    "r2x40x15": (40, 15, 1),                   # 480 x 270 raster, objects 2 x px: finer pixels need 2 x the canvas of today
    "r2x60x22": (60, 22, 1),                   # 720 x 396, objects 2 x px = today's screen size, 2 x finer
}
BUILD_LIMIT_S = 600                            # cold build 90 s on a loaded box (load 30); expiry = a hung build
FRAME_COST_LIMIT_S = 1200                      # 20 s fw window at ~15 x real time on a loaded box


def say(s: str) -> None:
    _log_line(s, LOG)


def binp(name: str) -> Path:
    return ROOT / f"tmp/fw/{SERIAL}-ar-{name}-be.bin"


def build(names) -> int:
    for n in names:
        c, r, res = VARIANTS[n]
        cmd = [sys.executable, "dev.py", "build", "--unit", "3", "--tag", f"ar-{n}", "--force",
               "-D", f"AWTO_AST_COLS={c}", "-D", f"AWTO_AST_ROWS={r}", "-D", f"AWTO_AST_RES={res}", "-D", "AWTO_SAVER_INFO=_OFF", "-D", "AWTO_AST_ODD_BAR_OK=1",
               "--savers", "asteroids", "--fw-args=--xdata-floor 0"]       # Asteroids-only image (docs/saver-mode.md "Selecting savers"): the XDATA the other savers freed
        say(f"build {n}: {' '.join(cmd[2:])}")
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=BUILD_LIMIT_S, check=False)
        say(f"build {n}: rc {p.returncode} {(p.stdout + p.stderr).strip().splitlines()[-1:]}")
        if p.returncode != 0:
            return p.returncode
    return 0


def cost(names, window: float) -> int:
    rows = []
    for n in names:
        cmd = [sys.executable, "scripts/saver_frame_cost.py", str(binp(n)), "--case", "asteroids", "--window", str(window), "--top", "0"]
        say(f"cost {n}: window {window} s")
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=FRAME_COST_LIMIT_S, check=False)  # rc ignored: missing result lines are reported below
        txt = p.stdout + p.stderr
        m1 = re.search(r"frames -> ([\d.]+) /s, ([\d.]+) ms each; (\d+) instr, (\d+) cycles", txt)
        m2 = re.search(r"saver slot ([\d.]+) ms, rest of the main loop ([\d.]+) ms.*?port (\d+) B \(glyph (\d+) B in ([\d.]+) uploads, map (\d+) B = ([\d.]+) words\), (\d+) address sets; flash fetch stall ([\d.]+) ms", txt)
        if not (m1 and m2):
            say(f"cost {n}: no result: {txt[-400:]}")
            return 1
        c, r, res = VARIANTS[n]
        rows.append([n, c, r, res, *m1.groups(), *m2.groups()])
        say(f"cost {n}: " + " ".join(rows[-1][4:]))
    hdr = "name\tcols\trows\tres\tfps\tms_per_frame\tinstr\tcycles\tsaver_ms\tmain_ms\tport_B\tglyph_B\tglyph_uploads\tmap_B\tmap_words\taddr_sets\tstall_ms"
    TSV.write_text(hdr + "\n" + "".join("\t".join(map(str, r)) + "\n" for r in rows))
    say(f"-> {TSV}")
    return 0


def render(names, seconds: float) -> int:
    import ddc_sim as D
    import numpy as np
    import osd_render as R
    from PIL import Image
    OUT.mkdir(parents=True, exist_ok=True)
    for n in names:
        cols, rws, _res = VARIANTS[n]
        eng = D.DdcEngine()
        sess = R.Session(binp(n), binp(n).with_suffix(".map"), "1080p60", devs=[eng])
        sess.boot()
        m, bus = sess.bus.m, sess.bus
        ddc = D.Mccs(bus, eng)
        ddc.set(0xE0, 32)                      # disp_rotate row: upright, as asteroids_sim.py
        ddc.set(0xE1, 0)
        bus.wait(6.0)
        pix = m.addr("g_aucScPix")
        cells = cols * rws
        base = rws + 1 + cells
        tiles = {}

        def tap(mm, r, base=base, cols=cols, tiles=tiles, pix=pix):
            cell = (r["a1"] - base) // 9
            row = cell // cols % 6                                  # canvas tile row of the band
            tiles[cell] = bytes(mm.rd(pix + row * TILE_B, TILE_B))

        m.stub("AwtoScTile", tap)
        ddc.set(0xEB, 8)
        bus.wait(seconds)
        canvas = np.zeros((rws * TILE_H, cols * TILE_W), np.uint8)
        for cell, bs in tiles.items():
            bits = np.unpackbits(np.frombuffer(bs, np.uint8))[:TILE_W * TILE_H].reshape(TILE_H, TILE_W)
            y, x = divmod(cell, cols)
            canvas[y * TILE_H:(y + 1) * TILE_H, x * TILE_W:(x + 1) * TILE_W] = bits
        np.save(OUT / f"{n}.npy", canvas)
        panel = scale_to_panel(canvas)
        Image.fromarray(panel).save(OUT / f"{n}.png")
        say(f"render {n}: {len(tiles)} of {cells} tiles uploaded, canvas {canvas.shape[1]} x {canvas.shape[0]} -> {OUT / (n + '.png')}")
        bus.close()
    return 0


def scale_to_panel(canvas):
    """Canvas -> panel: nearest neighbour at the OSD scale-up ratio (64 / factor, factor = 64 x W / panel width), centred; phosphor green on near black."""
    import numpy as np
    h, w = canvas.shape
    fac = 64 * w // PANEL_W
    out_w, out_h = w * 64 // fac, h * 64 // fac
    xs = (np.arange(out_w) * fac // 64).clip(0, w - 1)
    ys = (np.arange(out_h) * fac // 64).clip(0, h - 1)
    big = canvas[np.ix_(ys, xs)]
    img = np.zeros((PANEL_H, PANEL_W, 3), np.uint8)
    img[:] = (2, 2, 6)
    y0, x0 = (PANEL_H - out_h) // 2, (PANEL_W - out_w) // 2
    img[y0:y0 + out_h, x0:x0 + out_w][big > 0] = (0, 255, 65)
    return img


def compare(names, crop: int) -> int:
    import numpy as np
    from PIL import Image, ImageDraw
    from scipy import ndimage
    imgs = []
    for n in names:
        a = np.array(Image.open(OUT / f"{n}.png"))
        ink = a[..., 1] > 128
        ink[:300], ink[-300:], ink[:, :400], ink[:, -400:] = False, False, False, False     # away from the HUD and the edges
        lab, k = ndimage.label(ndimage.binary_dilation(ink, iterations=40))              # one object = one blob
        box = ndimage.find_objects(lab)
        big = max(range(k), key=lambda i: (box[i][0].stop - box[i][0].start) * (box[i][1].stop - box[i][1].start))    # the largest object
        cy, cx = (box[big][0].start + box[big][0].stop) // 2, (box[big][1].start + box[big][1].stop) // 2
        c = a[max(0, cy - crop // 2):cy + crop // 2, max(0, cx - crop // 2):cx + crop // 2]
        im = Image.fromarray(c).resize((crop, crop), Image.NEAREST)
        d = ImageDraw.Draw(im)
        d.text((8, 8), f"{n}  crop {crop} px of the 3840 x 2160 panel", fill=(255, 255, 255))
        imgs.append(im)
    sheet = Image.new("RGB", (crop * len(imgs) + 8 * (len(imgs) - 1), crop), (60, 60, 60))
    for i, im in enumerate(imgs):
        sheet.paste(im, (i * (crop + 8), 0))
    p = OUT / "compare.png"
    sheet.save(p)
    say(f"compare {names}: {p}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "cost", "render", "compare"])
    ap.add_argument("names", nargs="*")
    ap.add_argument("--window", type=float, default=12.0)
    ap.add_argument("--seconds", type=float, default=14.0)
    ap.add_argument("--crop", type=int, default=720)
    a = ap.parse_args()
    names = a.names or list(VARIANTS)
    if a.cmd == "build":
        return build(names)
    if a.cmd == "cost":
        return cost(names, a.window)
    if a.cmd == "render":
        return render(names, a.seconds)
    return compare(names, a.crop)


if __name__ == "__main__":
    sys.exit(main())
