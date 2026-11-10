#!/usr/bin/env python3
"""Live view of a firmware image in fw_sim: the OSD re-rendered every FRAME_S, driven by test commands from a file.

usage: sim_live.py BIN MAP [--mode 1080p60] [--out tmp/sim_live] [--port 8099]
  Serves the live picture as MJPEG on http://127.0.0.1:PORT/stream (VLC: `vlc http://127.0.0.1:8099/stream`; any browser shows it too)
  and writes OUT/frame.png each frame.
  Commands: append lines to OUT/cmd.txt, one per line; each is an osd_test action name (gpio, gpio-off, keytest, font3, cols120, probe48,
  scroll, scroll-reset, clear, ...) or a raw test byte (0x43). `quit` stops. Log: tmp/logs/sim_live.log (also stdout).
Timing: FRAME_S wall seconds between frames (a render costs ~0.3 s, enough for a text screen); the sim advances SIM_MS per frame
  (fw_sim runs about 3x slower than real time, so a frame = SIM_MS of firmware time, not wall time).
"""
import argparse
import io
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import osd_render as R  # noqa: E402
import osd_test as T  # noqa: E402

ROOT = HERE.parent
LOG = ROOT / "tmp/logs/sim_live.log"
FRAME_S = 0.5            # wall seconds between frames: a text screen re-renders in about 0.3 s
STREAM_S = 0.25         # MJPEG client refresh: faster than a frame so a new frame shows within 250 ms
LATEST = {"jpg": b""}
SIM_MS = 150             # firmware time advanced per frame: long enough for the 20 ms GPIO / 500 ms debug refresh to show change


def log(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


class Stream(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/frame.jpg":
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.end_headers()
            self.wfile.write(LATEST["jpg"])
            return
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        try:
            while True:
                jpg = LATEST["jpg"]
                if jpg:
                    self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: %d\r\n\r\n" % len(jpg) + jpg + b"\r\n")
                time.sleep(STREAM_S)
        except (BrokenPipeError, ConnectionResetError):
            return

    def log_message(self, *args):
        pass


def send(s, word):
    word = word.strip()
    if not word:
        return
    if word.lower().startswith("0x") or word.isdigit():
        val = int(word, 0)
        a = s.diag + T.TESTCMD_OFF
        ok = (s.bus.write(0x6A, 0x01, bytes([a >> 8])) and s.bus.write(0x6A, 0x03, bytes([val])) and s.bus.write(0x6A, 0x3B, bytes([a & 0xFF])))
        log(f"cmd 0x{val:02X} {'sent' if ok else 'NAK'}")
    else:
        try:
            s.act(word)
        except (KeyError, TypeError):
            log(f"unknown command '{word}'")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("map", type=Path)
    ap.add_argument("--mode", default="1080p60")
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/sim_live")
    ap.add_argument("--port", type=int, default=8099)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    cmd = a.out / "cmd.txt"
    cmd.write_text("")
    (a.out / "index.html").write_text(
        "<!doctype html><meta charset=utf-8><meta http-equiv=refresh content=1><title>sim live</title>"
        "<style>body{margin:0;background:#222}img{width:100%;image-rendering:pixelated}</style><img src=frame.png>")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Stream)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    log(f"stream: http://127.0.0.1:{a.port}/stream")
    s = R.Session(a.bin, a.map, a.mode)
    s.boot()
    done, frame = 0, 0
    while True:
        lines = cmd.read_text().splitlines()
        for w in lines[done:]:
            if w.strip() == "quit":
                log("quit")
                return 0
            send(s, w)
        done = len(lines)
        t0 = time.monotonic()
        i0 = s.bus.m.instr
        s.run_to(s.ms() + SIM_MS)
        t1 = time.monotonic()
        tmp = a.out / "frame.tmp.png"
        st = s.snap()
        t2 = time.monotonic()
        img = R.render_snap(st, "grey", 2)
        t3 = time.monotonic()
        img.save(tmp)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, "JPEG", quality=88)
        LATEST["jpg"] = buf.getvalue()
        tmp.replace(a.out / "frame.png")                   # atomic: the page never reads half a file
        frame += 1
        if frame % 10 == 1:
            log(f"frame {frame} at sim {s.ms():.0f} ms: run {t1 - t0:.2f} s ({s.bus.m.instr - i0} instr), snapshot {t2 - t1:.2f} s, "
                f"render {t3 - t2:.2f} s, encode {time.monotonic() - t3:.2f} s")
        time.sleep(max(0.0, FRAME_S - (time.monotonic() - t0)))   # pacing between frames, not a wait for hardware


if __name__ == "__main__":
    sys.exit(main())
