#!/usr/bin/env python3
"""Picture check of the firmware's OSD cards / selector / awto menu: fw_sim render vs golden PNGs (#263).

usage: AWTO_SIM_CORE=fast osd_golden.py BIN MAP [--bless] [--only NAME,...]   (entry: ./dev.py osd-golden, gate osdgold)
- One fw_sim boot at 1080p60, the card_shot.py shot list (same commands, same order), grey picture, model osd_model.render.
- Per shot (OSD off = golden.tsv origin -1, -1): the OSD box crop (16 px margin) at 1x vs tests/golden/osd_cards/<name>.png, pixels exact; box origin vs golden.tsv.
- Not checked: SKIP shots (console, console_info, gpio): they show the build tag and boot timings, which change with every image.
- --bless: write the renders as the new goldens (after a deliberate UI or model change; review the diff PNGs first).
- A difference writes tmp/osd_golden/<name>_{got,diff}.png (diff = changed pixels red).
Exact compare, no tolerance: the sim is deterministic (same image -> same pixels, checked twice 2026-11-27).
Log: tmp/logs/osd_golden.log
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import card_shot as CS
import numpy as np
import osd_model as M
import osd_render as R
from _log import log_line as _log_line
from _repo import ROOT
from PIL import Image

LOG = ROOT / "tmp/logs/osd_golden.log"
GOLD = ROOT / "tests/golden/osd_cards"
OUT = ROOT / "tmp/osd_golden"
MODE, BG, MARGIN = "1080p60", "grey", 16
SKIP = {"console", "console_info", "gpio", "selector_key"}   # build tag + boot timings on screen: differ per image. selector_key: its sync-log pane shows live AwtoMs ms-since-reset stamps (cycle-exact, shift a few ms per build) (#396)


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def crop(st) -> tuple[np.ndarray, tuple] | None:
    """OSD box crop (MARGIN px around what differs from the picture) and its origin; None = nothing drawn."""
    img = np.array(R.render_snap(st, BG, 1))
    mask = np.any(img != R.background(BG, R.PANEL_W, R.PANEL_H), axis=2)
    if not M.summary(st)["en"] or not mask.any():
        return None
    ys, xs = np.nonzero(mask)
    y0, x0 = max(0, ys.min() - MARGIN), max(0, xs.min() - MARGIN)
    return img[y0:ys.max() + 1 + MARGIN, x0:xs.max() + 1 + MARGIN], (int(x0), int(y0))


def shots(a) -> dict:
    out = {}
    s = R.Session(a.bin, a.map, MODE)
    try:
        s.boot()
        for name, cmds in CS.SHOTS:
            if name not in CS.CHAIN:
                CS.send(s, CS.CLEAR)
                CS.send(s, CS.K_MENU)
            for c in cmds:
                CS.send(s, c)
            s.bus.wait(a.wait)
            if name in SKIP or (a.only and name not in a.only):
                continue
            out[name] = crop(s.snap())
    finally:
        s.bus.close()
    return out


def read_tsv() -> dict:
    p = GOLD / "golden.tsv"
    if not p.is_file():
        return {}
    rows = [ln.split("\t") for ln in p.read_text().splitlines()[1:] if ln]
    return {r[0]: (int(r[1]), int(r[2])) for r in rows}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--bless", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--wait", type=float, default=1.0, help="sim seconds after the last command (card_shot default)")
    a = ap.parse_args()
    a.only = set(filter(None, a.only.split(",")))
    say(f"{a.bin.name}: {'bless' if a.bless else 'check'} vs {GOLD.relative_to(ROOT)}")
    got = shots(a)
    pos = read_tsv()
    if a.bless:
        GOLD.mkdir(parents=True, exist_ok=True)
        for name, r in got.items():
            if r is None:                                # a shot whose OSD is off stays off (golden.tsv origin -1, -1)
                (GOLD / f"{name}.png").unlink(missing_ok=True)
                pos[name] = (-1, -1)
                say(f"  blessed {name}: OSD off")
                continue
            Image.fromarray(r[0]).save(GOLD / f"{name}.png", optimize=True)
            pos[name] = r[1]
            say(f"  blessed {name}: {r[0].shape[1]}x{r[0].shape[0]} at {r[1]}")
        (GOLD / "golden.tsv").write_text("shot\tx0\ty0\n" + "".join(f"{k}\t{x}\t{y}\n" for k, (x, y) in sorted(pos.items())))
        return 0
    bad = 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, r in got.items():
        p = GOLD / f"{name}.png"
        off = pos.get(name) == (-1, -1)
        if r is None or off:
            if r is None and off:
                say(f"  ok {name} (OSD off, as golden)")
                continue
            say(f"  FAIL {name}: OSD {'off' if r is None else 'on'}, golden {'off' if off else 'on'}")
            bad += 1
            continue
        if not p.is_file():
            say(f"  FAIL {name}: no golden {p.relative_to(ROOT)} (./dev.py osd-golden --bless after review)")
            bad += 1
            continue
        g = np.asarray(Image.open(p).convert("RGB"))
        same = g.shape == r[0].shape and np.array_equal(g, r[0])
        if same and pos.get(name) == r[1]:
            say(f"  ok {name}")
            continue
        bad += 1
        Image.fromarray(r[0]).save(OUT / f"{name}_got.png")
        if g.shape == r[0].shape:
            d = r[0].copy()
            d[np.any(g != r[0], axis=2)] = (255, 0, 0)
            Image.fromarray(d).save(OUT / f"{name}_diff.png")
            why = f"{int(np.any(g != r[0], axis=2).sum())} px differ"
        else:
            why = f"size {r[0].shape[1]}x{r[0].shape[0]} vs golden {g.shape[1]}x{g.shape[0]}"
        if same:
            why = "pixels equal"
        say(f"  FAIL {name}: {why}; origin {r[1]} vs golden {pos.get(name)} -> {OUT.relative_to(ROOT)}/{name}_got.png")
    say(f"{'PASS' if not bad else 'FAIL'}: {len(got)} shots, {bad} differ (skipped {', '.join(sorted(SKIP))})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
