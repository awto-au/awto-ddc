#!/usr/bin/env python3
"""Info card beside the open console in its own OSD map (font B, delay set 2), in fw_sim (awto-ddc#357, Dan 2026-11-27).

usage: AWTO_SIM_CORE=fast card_window_sim.py BIN MAP [--mode 1080p60] [--rotate] [--out tmp/card_window] [--golden PNG] [--update]
- console_mode Always (stubbed), --rotate: disp_rotate 180 (stubbed). Boot to ACTIVE: the ACTIVE info card opens in map B.
- Checks: one map B open line (ED 7D), no "pop-up suppressed: the console" line (ED 82); font B on (FRAME_CTRL_18 fontx2_en)
  while the card is up; the console open all the time; the card's open and close write no OSD SRAM / window word outside map B
  and never call OsdFuncDisableOsd (no console blink); the card box clear of the console box; the close after
  _AWTO_INFO_POPUP_SEC (ED 7C, up ms within TIME_SLACK_MS); after the close the console renders exactly as it did under the card.
- PNGs in --out: console + card (panel at 1/2), the card crop at 1x. --golden: the card crop must equal that PNG pixel for pixel
  (--update writes it). Log: tmp/logs/card_window_sim.log
"""
import argparse
import re
import sys
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import osd_model as M
import osd_render as R
import sync_log as S
from _repo import ROOT
from PIL import Image

LOG = ROOT / "tmp/logs/card_window_sim.log"
HDR = ROOT / "fw/sdk/Project/Header/RL6449_Project.h"
SET_CONSOLE_MODE, CON_ALWAYS = 110, 2   # registry id 110 console_mode, value Always
SET_DISP_ROTATE, ROT_180 = 32, 1        # registry id 32 disp_rotate, value 180
EV_CARD, MAPB_OPEN, MAPB_TIMEOUT = 0xED, 0x7D, 0x7C
FONTX2 = 0x08                           # FRAME_CTRL_18 fontx2_en (regdb)
BUDGET_INSTR = 160_000_000              # boot to ACTIVE ~75 M instructions (boot_sim.py); x2; expiry = FAIL
STEP = 100_000                          # instructions per sample (~1-2 ms fw time)
TIME_SLACK_MS = 50                      # as info_card_sim: timer list polled per main-loop pass + one pass, x~1.25
CARD_WAIT_S = 3.0                       # ACTIVE -> card open: the one-time OSD event runs within a few passes; 3 s = a slow display set


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def hdr_int(name: str, t: str, seen=None) -> int:
    """integer #define of the header (+ - * of numbers and other defines)"""
    m = re.search(rf"^#define {name}\s+([^\n/]+)", t, re.MULTILINE)
    if not m:
        raise SystemExit(f"{name} not in {HDR.name}")
    e = re.sub(r"\b[A-Z_][A-Z0-9_]+\b", lambda k: str(hdr_int(k.group(0), t)), m.group(1).strip())
    if not re.fullmatch(r"[\d\s+\-*()]+", e):
        raise SystemExit(f"{name}: not an integer expression: {e!r}")
    return int(eval(e, {"__builtins__": {}}))


def b_box(st):
    """panel px box of font B: delay set 2 origin + font B offset, row widths / heights from map B (osd_model geometry)"""
    g = M.frame_geometry(st)
    rws = M.layout_rows(st, g, g["row_base1"], g["fs_base1"])
    w = max((sum((c["width"] or M.GW) for c in r["chars"]) for r in rws), default=0)
    h = sum(r["h"] for r in rws)
    x0 = (g["hd2"] * g["step"] + g["fhb"]) * g["sx"]
    y0 = (g["vd2"] + g["fvb"]) * g["sy"]
    return x0, y0, x0 + w * g["sx"] - 1, y0 + h * g["sy"] - 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/card_window")
    ap.add_argument("--golden", type=Path)
    ap.add_argument("--update", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    t = HDR.read_text()
    want_ms = (hdr_int("_AWTO_INFO_POPUP_BASE_SEC", t) + hdr_int("_AWTO_INFO_POPUP_EXTRA_SEC", t)) * 1000
    room = hdr_int("AWTO_MAPB_WORDS", t)
    tag = "_rot" if a.rotate else ""
    say(f"card_window_sim {a.bin.name}{' rotate 180' if a.rotate else ''}: card up {want_ms} ms, map B room {room} words")
    s = R.Session(a.bin, a.map, a.mode)
    m = s.bus.m
    stub_val = {SET_CONSOLE_MODE: CON_ALWAYS, **({SET_DISP_ROTATE: ROT_180} if a.rotate else {})}
    m.stub("set_get", lambda m_, r: {"val": stub_val[r["a1"] & 0xFF]} if (r["a1"] & 0xFF) in stub_val else None)
    rows = S.load_rows(S.tsv_for(a.map))
    ring = S.sym(a.map, "g_stAwtoSync")
    a_mapb, a_row, a_gpio = m.addr("g_ucAwtoMapB"), m.addr("g_ucAwtoMapBRow"), m.addr("g_stAwtoGpio") + 3
    snaps, phase, blinks, opens = {}, [None], [], []

    def snap(key):
        snaps[key] = s.model.snapshot(m, 0.0)

    def on_open(m_, r):
        snap("open0")
        phase[0] = "open"

    def on_off(m_, r):
        if m.rd(a_mapb)[0] != 0 and (r["a1"] & 0xFF) == MAPB_TIMEOUT:      # the timeout close (ucWhy)
            snap("close0")
            phase[0] = "close"

    def on_push(m_, r):
        ev, arg = r["a1"] & 0xFF, r["a2"] & 0xFF
        if ev == EV_CARD and arg == MAPB_OPEN and phase[0] == "open":
            opens.append(s.bus.now())
            snap("open1")
            phase[0] = None
        if ev == EV_CARD and arg == MAPB_TIMEOUT and phase[0] == "close":
            snap("close1")
            phase[0] = None

    def on_disable(m_, r):
        if phase[0] is not None:
            blinks.append(phase[0])

    m.stub("osd_tc_b_open", on_open)
    m.stub("osd_tc_b_off", on_off)
    m.stub("AwtoSyncPushL", on_push)
    m.stub("OsdFuncDisableOsd", on_disable)
    fails = []

    def check(ok, what, det=""):
        say(f"  {'PASS' if ok else 'FAIL'} {what}{(': ' + det) if det else ''}")
        if not ok:
            fails.append(what)

    used = 0
    while used < BUDGET_INSTR and s.bus.mode_state() != 3:
        m.run(STEP)
        used += STEP
    if s.bus.mode_state() != 3:
        say(f"  FAIL no ACTIVE after {used} instr")
        return 1
    t_act = s.bus.now()
    while not opens and s.bus.now() - t_act < CARD_WAIT_S:
        s.bus.wait(0.1)
    check(len(opens) == 1, "the info card opened in map B", f"{len(opens)} open lines, {(opens[0] - t_act) * 1000 if opens else 0:.0f} ms after ACTIVE")
    if not opens:
        return 1
    s.bus.wait(0.5)
    up = s.model.snapshot(m, 0.0)
    check(up.reg(M.FRAME + 0x18) & FONTX2 != 0, "font B on while the card is up", f"FRAME_CTRL_18 = 0x{up.reg(M.FRAME + 0x18):02X}")
    check(m.rd(a_gpio)[0] != 0, "console open with the card up")
    rb = m.rd(a_row)[0]
    inb = range(rb, rb + room)
    bx0, by0, bx1, by1 = b_box(up)
    img = np.array(R.render_snap(up, "grey", 1))
    Image.fromarray(img).resize((R.PANEL_W // 2, R.PANEL_H // 2), Image.BOX).save(a.out / f"card_window{tag}.png")
    crop = img[by0:by1 + 1, bx0:bx1 + 1]
    Image.fromarray(crop).save(a.out / f"card_window{tag}_card.png")
    say(f"  png {a.out / f'card_window{tag}.png'}, card {bx1 - bx0 + 1}x{by1 - by0 + 1} px at ({bx0},{by0}) -> {a.out / f'card_window{tag}_card.png'}")
    if a.golden and a.update:
        a.golden.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(crop).save(a.golden)
        say(f"  golden written: {a.golden}")
    elif a.golden:
        g = np.array(Image.open(a.golden).convert("RGB")) if a.golden.is_file() else None
        check(g is not None and g.shape == crop.shape and bool((g == crop).all()), "card crop = golden", str(a.golden))
    s.bus.wait(want_ms / 1000.0 + 1.0)
    evs = S.read_ring(m.rd, ring)
    _h, lines = S.decode(evs, rows)
    for ln in lines:
        if "pop-up" in ln:
            say(f"    {ln}")
    closes = [ln for ln in lines if "pop-up closed (font B): its on-screen time ran out" in ln]
    ups = [int(x) for x in re.findall(r"up (\d+) ?ms", " ".join(closes))]
    check(not any("pop-up suppressed: the console" in ln for ln in lines), "no 'suppressed: the console' line")
    check(len(closes) == 1 and len(ups) == 1 and abs(ups[0] - want_ms) <= TIME_SLACK_MS, f"one close line, up {want_ms} ms (+-{TIME_SLACK_MS})", str(ups))
    check(m.rd(a_gpio)[0] != 0, "console still open after the close")
    after = s.model.snapshot(m, 0.0)
    check(after.reg(M.FRAME + 0x18) & FONTX2 == 0, "font B off after the close", f"FRAME_CTRL_18 = 0x{after.reg(M.FRAME + 0x18):02X}")
    for k0, k1, what in (("open0", "open1", "open"), ("close0", "close1", "close")):
        if k0 not in snaps or k1 not in snaps:
            check(False, f"card {what}: hooks hit", f"{sorted(snaps)}")
            continue
        s0, s1 = snaps[k0], snaps[k1]
        out0 = {k: v for k, v in s0.font.items() if k not in inb}
        out1 = {k: v for k, v in s1.font.items() if k not in inb}
        check(out0 == out1 and s0.win == s1.win, f"card {what}: no SRAM / window word outside map B written")
        check(s0.ovl[0] & 1 == s1.ovl[0] & 1 == 1, f"card {what}: overlay port on before and after")
        r0, r1 = np.array(R.render_snap(s0, "grey", 1)), np.array(R.render_snap(s1, "grey", 1))
        d = np.any(r0 != r1, axis=2)
        d[by0:by1 + 1, bx0:bx1 + 1] = False
        if d.any():                                          # evidence for the failure below
            for k, r_ in ((k0, r0), (k1, r1)):
                Image.fromarray(r_).resize((R.PANEL_W // 2, R.PANEL_H // 2), Image.BOX).save(a.out / f"card_window{tag}_{k}.png")
        check(not d.any(), f"card {what}: console pixels unchanged outside the card box", f"{int(d.sum())} px differ")
        if what == "open":
            cy, cx = np.nonzero(np.any(r0 != R.background("grey", R.PANEL_W, R.PANEL_H), axis=2))
            ok = cx.size and (bx1 < cx.min() or bx0 > cx.max() or by1 < cy.min() or by0 > cy.max())
            check(bool(ok), "card box clear of the console box", f"card ({bx0},{by0})-({bx1},{by1}), console "
                  f"({cx.min() if cx.size else -1},{cy.min() if cy.size else -1})-({cx.max() if cx.size else -1},{cy.max() if cy.size else -1})")
        else:
            Image.fromarray(r1).resize((R.PANEL_W // 2, R.PANEL_H // 2), Image.BOX).save(a.out / f"card_window{tag}_after.png")
    check(not blinks, "OsdFuncDisableOsd never called during the card open / close", str(blinks))
    say(f"=== {a.bin.name}{tag}: {'ALL PASS' if not fails else f'{len(fails)} FAIL'} ===")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
