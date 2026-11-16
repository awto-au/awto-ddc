#!/usr/bin/env python3
"""Render every Realtek QC OSD frame (awto-ddc#227): Realtek's own QC code runs in the firmware simulator, our OSD model paints it.

usage: qc_frames_shot.py BIN MAP [--out DIR] [--frames 0,1,..] [--wait S]
  BIN / MAP = an image with the QC OSD file compiled in and the test command 0xB2 + n (AwtoQcRun: init + test pattern for n = 0,
  frames 0..n - 1 as ScalerQC_OSDTestProc runs them, then frame n - 1 left on screen). Per frame: DIR/qc_<n>_<name>.png = the
  OSD area at 1x; DIR/qc_sheet.png = all of them with their frame names. The model draws map A / B, fonts 1 / 2 / 4 bpp, blank cells
  and plain windows; effects it does not model yet (gradient, grid lines, shadow / border, chessboard, highlight ...) show as flat
  windows - see the doc line under each tile.
Log: ./tmp/logs/qc_frames_shot.log
"""
import argparse
import os
import sys
import isostamp  # noqa: E402
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402
import osd_model as M  # noqa: E402
import osd_render as R  # noqa: E402
import card_shot as C  # noqa: E402

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
LOG = ROOT / "tmp/logs/qc_frames_shot.log"
TC = 0xB2
# frame order of Realtek's enum OSDQCFrameDef: _OSD_FRAME_1, 2, 2_1, 2_2, 2_3, 3 .. 20
NAMES = ["pattern (init)"] + ["frame 1", "frame 2", "frame 2_1 (cw270)", "frame 2_2", "frame 2_3 (cw180)"] + [f"frame {i}" for i in range(3, 21)]
CALLS = {1: "blank font, 1-bit shrink / colour, 2-bit swap, 4-bit bg, window priority", 2: "gradient + grid line windows",
         3: "map rotation cw270", 4: "", 5: "map rotation cw180"}


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/scratch/qc_frames")
    ap.add_argument("--frames", default=",".join(str(i) for i in range(len(NAMES))))
    ap.add_argument("--bg", default="grey", help="picture under the OSD: grey, checker or bars (bars shows the blending)")
    ap.add_argument("--wait", type=float, default=4.0, help="sim seconds after the command (the QC run waits for many frames)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    tiles = []
    for n in (int(x) for x in a.frames.split(",")):
        s = R.Session(a.bin, a.map, "1080p60")          # fresh boot per frame: after a rotated frame the MCU stays in the run and NAKs
        s.boot()
        C.send(s, TC + n)
        s.bus.wait(a.wait)
        st = s.snap()
        img = np.array(R.render_snap(st, a.bg, 1, False))
        mask = np.any(img != R.background(a.bg, R.PANEL_W, R.PANEL_H), axis=2)
        info = M.summary(st)
        name = NAMES[n] if n < len(NAMES) else f"frame {n}"
        if not mask.any():
            say(f"{n} {name}: OSD off / nothing drawn (windows {info['nwin']}, en {info['en']})")
            continue
        ys, xs = np.nonzero(mask)
        crop = img[max(0, ys.min() - 8):ys.max() + 9, max(0, xs.min() - 8):xs.max() + 9]
        p = a.out / (f"qc_{n:02d}.png" if a.bg == "grey" else f"qc_{n:02d}_{a.bg}.png")
        Image.fromarray(crop).save(p)
        say(f"{n} {name}: box {xs.max() - xs.min() + 1}x{ys.max() - ys.min() + 1} at ({xs.min()},{ys.min()}), {info['nwin']} windows, "
            f"blend type {info['blend_type']}, map {info['cols']}x{info['rows']} -> {p}")
        tiles.append((f"{n}: {name}", crop))
    if tiles:
        cell_w = 640
        ims = []
        for label, c in tiles:
            im = Image.fromarray(c)
            k = min(1.0, cell_w / im.width)
            im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.BOX)
            lab = Image.new("RGB", (cell_w, 18), (30, 30, 34))
            ImageDraw.Draw(lab).text((4, 3), label, fill=(235, 235, 235))
            t = Image.new("RGB", (cell_w, im.height + 18 + 6), (50, 50, 54))
            t.paste(lab, (0, 0))
            t.paste(im, (0, 18))
            ims.append(t)
        cols = 3
        rows = (len(ims) + cols - 1) // cols
        rh = [max(t.height for t in ims[r * cols:(r + 1) * cols]) for r in range(rows)]
        sheet = Image.new("RGB", (cols * (cell_w + 6), sum(rh) + 6 * rows), (50, 50, 54))
        y = 0
        for r in range(rows):
            for c, t in enumerate(ims[r * cols:(r + 1) * cols]):
                sheet.paste(t, (c * (cell_w + 6), y))
            y += rh[r] + 6
        sp = a.out / "qc_sheet.png"
        sheet.save(sp)
        say(f"sheet {len(tiles)} frames -> {sp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
