#!/usr/bin/env python3
"""Run a firmware image in fw_sim, capture its OSD writes and render what the panel shows: PNG / video (#46, #63).

usage: osd_render.py BIN MAP [--mode 1080p60|2160p60] [--at WHEN ...] [--do MS:ACTION ...] [--out tmp/osd/NAME.png]
                     [--video OUT.mp4 --every MS --until MS [--vscale 4]] [--bg grey|black|white|checker|bars] [--scale N]
  WHEN  = sim ms after the firmware reaches ACTIVE (e.g. 500), or `end` (last action + 1 s). Several --at give several
          PNGs (NAME_<when>.png). Power-on screens (no logo since #144, the console): scripts/boot_sim.py.
  ACTION = osd_test.py name: events (info nosignal ...), keys (menu right left exit), debug, clear, ...
          written to the firmware test byte (isr_g_stAwtoDiag + 0x28) over the simulated debug slave (osd_test --cmd).
  --video: a frame every --every ms of sim time from 0 to --until (frames downscaled by --vscale), mp4 via ffmpeg
          (image sequence in OUT_frames/ when ffmpeg is missing).
Model: scripts/osd_model.py (gaps listed there). Timing: ms = firmware Timer2 ms (sim runs ~3x time-dilated, see fw_sim).
Log: tmp/logs/osd_render.log ; JSON of the OSD state (grid size, ids, window, regs) next to each PNG.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import fw_sim as S  # noqa: E402
import osd_model as M  # noqa: E402
import osd_test as T  # noqa: E402

ROOT = S.ROOT
LOG = ROOT / "tmp/logs/osd_render.log"
PANEL = {"1080p60": (1920, 1080), "2160p60": (3840, 2160)}      # D-domain size of the 4K panel is 3840x2160 for both input modes
PANEL_W, PANEL_H = 3840, 2160
BGS = {"grey": (128, 128, 128), "black": (0, 0, 0), "white": (255, 255, 255)}


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


def background(kind: str, W: int, H: int) -> np.ndarray:
    """Test picture under the OSD: flat (BGS), checker, or bars = 75 % colour bars (top 2/3) over a black-to-white ramp."""
    if kind == "checker":
        yy, xx = np.mgrid[0:H, 0:W]
        c = (((yy // 60) + (xx // 60)) % 2) * 40 + 100
        return np.repeat(c[:, :, None].astype(np.uint8), 3, axis=2)
    if kind == "bars":
        img = np.empty((H, W, 3), np.uint8)
        cols = [(191, 191, 191), (191, 191, 0), (0, 191, 191), (0, 191, 0), (191, 0, 191), (191, 0, 0), (0, 0, 191)]
        for i, c in enumerate(cols):
            img[:H * 2 // 3, i * W // 7:(i + 1) * W // 7] = c
        img[H * 2 // 3:] = np.linspace(0, 255, W, dtype=np.float32).astype(np.uint8)[None, :, None]
        return img
    return np.full((H, W, 3), BGS[kind], np.uint8)


def render_snap(st: M.OsdState, bg: str, scale: int = 1, opaque: bool = False) -> Image.Image:
    out = M.render(st, PANEL_W, PANEL_H, bg=background(bg, PANEL_W, PANEL_H), alpha_opaque=opaque)
    im = Image.fromarray(out)
    return im if scale <= 1 else im.resize((PANEL_W // scale, PANEL_H // scale), Image.BOX)


class Session:
    def __init__(self, binp: Path, mapp: Path, mode: str):
        self.binp, self.mapp, self.mode = binp, mapp, mode
        self.model = M.OsdModel()
        self.model.img = binp.read_bytes()
        self.bus = S.SimBus(binp, mapp, "osdr-" + binp.stem, None, boot=False, devs=[self.model], video=mode)
        self.diag = T.diag_addr(mapp)
        self.t0 = None

    def boot(self, sync_console: bool = False):
        """sync_console False: the #139 console auto-open is switched off right after the crt init (g_ucAwtoSyncCon = 0),
        so screen tests start from an empty OSD as before; True = the firmware default (on). #144: the power-on console
        opens at mode INITIAL, so the switch-off is written every 50 k instructions until the main loop runs."""
        bus, m, used = self.bus, self.bus.m, 0
        con = None
        if not sync_console:
            try:
                con = m.addr("g_ucAwtoSyncCon")              # XDATA symbol (map D: line); images before #139 lack it
            except S.SimError:
                con = None
        while used < 160_000_000:
            step = 50_000 if (con and bus.diag()["stage"] < 8) else 1_000_000
            m.run(step); used += step
            if con and not sync_console:
                m.wr(con, bytes([0]))
            if bus.diag()["stage"] >= 8:
                break
        if not bus.run_until_mode(3):
            raise SystemExit("never reached ACTIVE")
        bus.dbg_link_on()                                          # #79 images: 0x35 is parked off the host port until this
        self.t0 = bus.now()
        say(f"{self.binp.name}: ACTIVE at fw {self.t0:.3f} s ({bus.m.instr} instr)")

    def ms(self) -> float:
        return (self.bus.now() - self.t0) * 1000.0

    def act(self, name: str):
        val = T.CMD_ONLY.get(name) or ((0x10 + T.EVENTS[name]) if name in T.EVENTS else (1 + T.KEYS[name]))
        ok = self.bus.write(0x6A, 0x01, bytes([(self.diag + T.TESTCMD_OFF) >> 8])) and \
            self.bus.write(0x6A, 0x03, bytes([val])) and self.bus.write(0x6A, 0x3B, bytes([(self.diag + T.TESTCMD_OFF) & 0xFF]))
        say(f"  t={self.ms():.0f} ms: action {name} (test byte 0x{val:02X}) {'sent' if ok else 'NAK'}")

    def run_to(self, ms: float):
        d = ms - self.ms()
        if d > 0:
            self.bus.wait(d / 1000.0)

    def snap(self) -> M.OsdState:
        return self.model.snapshot(self.bus.m, self.ms())


def save(st: M.OsdState, out: Path, bg: str, scale: int):
    out.parent.mkdir(parents=True, exist_ok=True)
    render_snap(st, bg, scale).save(out)
    info = M.summary(st)
    out.with_suffix(".json").write_text(json.dumps(info, indent=1, default=str))
    import pickle
    out.with_suffix(".state.pkl").write_bytes(pickle.dumps(st))      # OsdState for offline analysis / re-render
    say(f"png {out}  OSD en={info['en']} {info['cols']}x{info['rows']} cells, {info['uniq_ids']} unique ids (max {info['max_id']}), "
        f"scale {info['sx']}x{info['sy']}, {info['nwin']} windows, font SRAM {info['font_words']} words")


def video(frames: list, out: Path, fps: int):
    d = out.with_name(out.stem + "_frames")
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    for i, im in enumerate(frames):
        im.save(d / f"f{i:04d}.png")
    if shutil.which("ffmpeg"):
        r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps), "-i", str(d / "f%04d.png"),
                            "-pix_fmt", "yuv420p", "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", str(out)], capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            shutil.rmtree(d)
            say(f"video {out} ({len(frames)} frames @ {fps} fps)")
            return
        say("ffmpeg failed: " + r.stderr[-300:])
    say(f"image sequence {d} ({len(frames)} frames)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="2160p60", choices=sorted(PANEL))
    ap.add_argument("--at", action="append", default=[])
    ap.add_argument("--do", action="append", default=[], metavar="MS:ACTION")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--bg", default="grey", choices=["grey", "black", "white", "checker", "bars"])
    ap.add_argument("--scale", type=int, default=1, help="downscale PNGs by N")
    ap.add_argument("--video", type=Path)
    ap.add_argument("--every", type=float, default=200.0)
    ap.add_argument("--until", type=float, default=3000.0)
    ap.add_argument("--vscale", type=int, default=4)
    ap.add_argument("--fps", type=int, default=10)
    a = ap.parse_args()
    out = a.out or ROOT / "tmp/osd" / (a.bin.stem + ".png")
    acts = sorted((float(x.split(":", 1)[0]), x.split(":", 1)[1]) for x in a.do)
    whens = a.at or ["end"]
    s = Session(a.bin, a.map, a.mode)
    try:
        s.boot()
        marks = sorted({float(w) for w in whens if w != "end"} | {t for t, _ in acts})
        frames, vt = [], 0.0
        timeline = sorted(set(marks) | (set(np.arange(0, a.until + 1e-9, a.every).tolist()) if a.video else set()))
        snaps = {}
        for t in timeline:
            s.run_to(t)
            for at, name in acts:
                if at == t:
                    s.act(name)
            if str(int(t)) in whens or str(t) in whens or f"{t:g}" in whens:
                snaps[f"{t:g}"] = s.snap()
            if a.video and t % a.every == 0 and t <= a.until:
                frames.append(render_snap(s.snap(), a.bg, a.vscale))
        if "end" in whens:
            s.run_to((max([t for t, _ in acts], default=0.0) + 1000.0) if acts else s.ms() + 100.0)
            snaps["end"] = s.snap()
        (ROOT / "tmp/logs/osd_bursts.txt").write_text("\n".join(map(str, s.model.log)))
        for k, st in snaps.items():
            save(st, out if len(snaps) == 1 else out.with_name(f"{out.stem}_{k}.png"), a.bg, a.scale)
        if a.video:
            video(frames, a.video, a.fps)
    finally:
        s.bus.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
