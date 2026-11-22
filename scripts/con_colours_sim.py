#!/usr/bin/env python3
"""Console log colour classes in fw_sim: one sample line per class injected into the ring, drawn BEFORE (old image) and AFTER side by side.

usage: AWTO_SIM_CORE=fast con_colours_sim.py AFTER.bin [--before BEFORE.bin] [--out tmp/scratch/colours]
- Each image boots to ACTIVE with the console open, SAMPLES are pushed into the ring (con_wrap_sim.Sim.inject), the console is rendered.
- Checks (AFTER): every row's glyph cells carry the palette entry of its class (named constants of RL6449_Project.h via sync_classes);
  an unclassified row keeps the green text entry; BEFORE has no class colours (all rows the text entry).
- PNG: <out>/colours_before_after.png (BEFORE left, AFTER right), one crop per image beside it.
Log: tmp/logs/con_colours_sim.log. Exit 1 on a failed check.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import con_wrap_sim as W
import numpy as np
import osd_model as M
import osd_render as R
import sync_classes
import sync_log as SL
from _repo import ROOT
from PIL import Image, ImageDraw

LOG = ROOT / "tmp/logs/con_colours_sim.log"
# (id, arg, value): one or two rows of every class, from fw/awto/sync.tsv
SAMPLES = (
    (0xD0, 0x01, 0),                                    # boot
    (0xD1, 0x03, 0),                                    # boot
    (0x11, 0x01, 87),                                   # timing (panel machine ms)
    (0xC5, 0x04, (3840 << 16) | 2160),                  # timing (port timing)
    (0xC8, 0x04, 594000),                               # timing (pixel clock)
    (0xC0, 0x02, 0x02),                                 # normal (switch)
    (0xE0, 0x01, 0x02),                                 # normal (input selector)
    (0xA0, 0x01, 0),                                    # warning
    (0x12, 0x02, 0),                                    # warning
    (0x10, 0x0C, 0x01),                                 # warning
    (0xD4, 0x11, 0),                                    # flash
    (0xD4, 0x20, (1 << 27) | (2 << 19) | (32 << 9) | 4),  # flash (NVRAM flush result)
    (0xD0, 0x02, 0x010BFFD0),                           # error (watchdog bite)
    (0x12, 0x01, 0),                                    # error (link training)
    (0xC4, 0x04, 0),                                    # error (signal lost)
    (0xC1, 0x04, 0),                                    # normal again
)
PAL = {"AWTO_T_STYLE_TEXT": "AWTO_PAL_DIAG_TEXT", "AWTO_T_STYLE_ALERT": "AWTO_PAL_DIAG_ALERT", "AWTO_T_STYLE_WARN": "AWTO_PAL_DIAG_WARN",
       "AWTO_T_STYLE_TIMING": "AWTO_PAL_DIAG_TIMING", "AWTO_T_STYLE_BOOT": "AWTO_PAL_DIAG_BOOT"}


def say(s: str):
    _log_line(s, LOG)


def run(binp: Path, name: str):
    s = W.Sim(binp, binp.with_suffix(".map"))
    s.check(s.bus.run_until_mode(W.MODE_ACTIVE, 160_000_000), f"{name}: boot to ACTIVE")
    s.bus.wait(W.NV_IDLE_S)
    s.cmd(0x26)                                         # console on
    s.until(lambda: "AWTO DIAGNOSTICS" in (s.text() or [""])[0], 4.0)
    for k in range(0, len(SAMPLES), 4):                 # a few lines at a time: the draw takes one line per main-loop pass
        s.inject(SAMPLES[k:k + 4])
        s.bus.wait(0.3)
    s.bus.wait(W.DRAW_S)
    st = s.model.snapshot(s.m, 0)
    return s, R.render_snap(st, "black", 1).convert("RGB"), st


def fg_of(s, st, ev, rowsd) -> int | None:
    """palette index of the first glyph of the sample's console row (the row whose text holds the ring line's text)"""
    want = W.norm(SL.line(rowsd, (*ev[:2], 0, ev[2]), 0).split(":", 1)[1]).strip()[:10]
    text = s.text()
    lay = M.layout_rows(st, M.frame_geometry(st))
    for t, r in zip(text, lay):
        if W.norm(t.split(":", 1)[-1].strip())[:10] == want:
            return next((c["fg"] for c in r["chars"] if c["kind"] == "1bit" and c["id"] != r["chars"][0]["id"]), None)
    return None


def crop(img: Image.Image) -> Image.Image:
    a = np.array(img)
    ys, xs = np.nonzero(a.sum(axis=2) > 0)
    return img.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


def header(path: Path) -> dict:
    return {m.group(1): int(m.group(2)) for m in re.finditer(r"^#define (AWTO_PAL_\w+)\s+(\d+)", path.read_text(), re.MULTILINE)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("after", type=Path)
    ap.add_argument("--before", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/scratch/colours")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    say(f"=== con_colours_sim after {a.after.name} before {a.before.name if a.before else '-'} ===")
    shots = []
    fails = 0
    for label, binp in (("BEFORE", a.before), ("AFTER", a.after)):
        if binp is None:
            continue
        s, img, st = run(binp, label)
        fails += s.fails
        c = crop(img)
        c.save(a.out / f"colours_{label.lower()}.png")
        shots.append((label, c))
        say(f"  {label}: {c.size[0]}x{c.size[1]} px crop")
        rowsd = SL.load_rows(SL.tsv_for(binp.with_suffix(".map")))
        pals = header(ROOT / "fw/sdk/Project/Header/RL6449_Project.h")
        cls = sync_classes.load()
        for ev in SAMPLES:
            row = next(r for r in SL.load_rows(ROOT / "fw/awto/sync.tsv") if r["id"] == ev[0] and (r["arg"] is None or r["arg"] == ev[1]))
            want = pals[PAL[cls[row["cls"]]["style"]]] if label == "AFTER" else pals["AWTO_PAL_DIAG_TEXT"]
            got = fg_of(s, st, ev, rowsd)
            ok = got == want
            fails += not ok
            say(f"  {'PASS' if ok else 'FAIL'} {label} {ev[0]:02X} {ev[1]:02X} class {row['cls'] if label == 'AFTER' else 'normal (old image)'}: glyph palette {got}, want {want}")
    if shots:
        h = max(c.size[1] for _l, c in shots) + 24
        w = sum(c.size[0] for _l, c in shots) + 16 * (len(shots) - 1)
        sheet = Image.new("RGB", (w, h), (40, 40, 40))
        d = ImageDraw.Draw(sheet)
        x = 0
        for label, c in shots:
            d.text((x + 4, 4), label, fill=(255, 255, 255))
            sheet.paste(c, (x, 24))
            x += c.size[0] + 16
        sheet.save(a.out / "colours_before_after.png")
        say(f"  side by side: {a.out / 'colours_before_after.png'}")
    say(f"{'PASS' if fails == 0 else 'FAIL'} con_colours_sim: {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
