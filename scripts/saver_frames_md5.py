#!/usr/bin/env python3
"""md5 of each complete saver frame in the firmware sim: proves a refactor changed no pixel (docs/saver-library.md). Nothing touches hardware.

usage: saver_frames_md5.py BIN [MAP] --saver scope|scope2|asteroids|pacman [--frames N] [--rotate] [--tsv OUT]
       saver_frames_md5.py --compare A.tsv B.tsv
  - Starts the saver by DDC/CI VCP 0xEB; a hook on AwtoSyncPush catches the saver's own "frame complete" sync line (E9 arg below):
    the OSD state at that instant (font SRAM + map words, palette, OSD registers) is hashed, and its render (panel / RENDER_SHRINK).
  - Frame content depends on the frame number only (phase / game tick), not on how fast it was drawn: images of different speed compare.
  - --compare: exit 0 when both TSVs hold the same hashes for the frames they share (at least MIN_SHARED).
Log: ./tmp/logs/saver_frames_md5.log
"""
import argparse
import hashlib
import os
import sys
from pathlib import Path

os.environ.setdefault("AWTO_SIM_CORE", "fast")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp  # noqa: E402
import osd_render as R  # noqa: E402
import ddc_sim as D  # noqa: E402

ROOT = R.ROOT
LOG = ROOT / "tmp/logs/saver_frames_md5.log"
VCP_SAVER = 0xEB
SYNC_EV_ODEMO = 0xE9                    # AWTO_SYNC_EV_ODEMO
SAVERS = {                              # VCP 0xEB value, sync args that close a frame (ON = first frame, FRAME = later ones)
    "pacman": (2, (0x74,)),
    "scope2": (4, (0x7B, 0x7C)),
    "asteroids": (8, (0x90, 0x91)),
}
ROW_DISP_ROTATE = 32                    # registry row id of disp_rotate
ROTATE_SETTLE_S = 6.0                   # fw time for the display re-set after Rotate changes (saver_sim.py)
RENDER_SHRINK = 4
WAIT_CHUNK_S = 0.25                     # fw time per wait between frame-count checks
LIMIT_S_PER_FRAME = 3.0                 # slowest saver frame ~1.5 s (Scope 2, saver-mode.md) x 2: expiry = logged FAIL
MIN_SHARED = 5


def say(s: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{isostamp.now()} {s}"
    with LOG.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def state_md5(st) -> str:
    h = hashlib.md5()
    for k in sorted(st.font):
        h.update(k.to_bytes(4, "big") + bytes(st.font[k]))
    for k in sorted(st.win):
        h.update(k.to_bytes(4, "big") + bytes(st.win[k]))
    h.update(repr(list(st.pal)).encode() + st.regs + bytes(st.ovl))
    return h.hexdigest()


def run(a) -> int:
    vcp, args = SAVERS[a.saver]
    eng = D.DdcEngine()
    sess = R.Session(a.bin, a.map or a.bin.with_suffix(".map"), "1080p60", devs=[eng])
    sess.boot()
    ddc = D.Mccs(sess.bus, eng)
    if a.rotate:
        ddc.set(0xE0, ROW_DISP_ROTATE)
        ddc.set(0xE1, 1)
        sess.bus.wait(ROTATE_SETTLE_S)
    rows = []

    def hook(m, r):
        if (r["a1"] & 0xFF) == SYNC_EV_ODEMO and (r["a2"] & 0xFF) in args and len(rows) < a.frames:
            st = sess.snap()
            img = R.render_snap(st, "black", RENDER_SHRINK)
            rows.append((len(rows), state_md5(st), hashlib.md5(img.tobytes()).hexdigest(), round(sess.ms())))
        return None

    sess.bus.m.stub("AwtoSyncPush", hook)
    t0 = sess.bus.now()
    ddc.set(VCP_SAVER, vcp)
    limit = LIMIT_S_PER_FRAME * (a.frames + 1)
    while len(rows) < a.frames and sess.bus.now() - t0 < limit:
        sess.bus.wait(WAIT_CHUNK_S)
    sess.bus.close()
    out = "frame\tstate_md5\trender_md5\tfw_ms\n" + "".join(f"{f}\t{s}\t{p}\t{t}\n" for f, s, p, t in rows)
    if a.tsv:
        a.tsv.parent.mkdir(parents=True, exist_ok=True)
        a.tsv.write_text(out)
    whole = hashlib.md5("".join(s + p for _, s, p, _ in rows).encode()).hexdigest()
    span = (rows[-1][3] - rows[0][3]) / max(1, len(rows) - 1) if rows else 0
    say(f"{a.bin.name} {a.saver}{' rotate' if a.rotate else ''}: {len(rows)} frames, md5 of all {whole}, {span:.0f} ms per frame -> {a.tsv}")
    if len(rows) < a.frames:
        say(f"FAIL: {len(rows)} of {a.frames} frames within {limit:.0f} s fw time")
        return 1
    return 0


def compare(pa: Path, pb: Path) -> int:
    def load(p):
        return {ln.split("\t")[0]: tuple(ln.split("\t")[1:3]) for ln in p.read_text().splitlines()[1:]}
    ra, rb = load(pa), load(pb)
    shared = sorted(set(ra) & set(rb), key=int)
    diff = [f for f in shared if ra[f] != rb[f]]
    ok = not diff and len(shared) >= MIN_SHARED
    say(f"compare {pa.name} vs {pb.name}: {len(shared)} shared frames, {len(diff)} differ{(' (first ' + diff[0] + ')') if diff else ''}: {'IDENTICAL' if ok else 'FAIL'}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path, nargs="?")
    ap.add_argument("map", type=Path, nargs="?")
    ap.add_argument("--saver", choices=sorted(SAVERS))
    ap.add_argument("--frames", type=int, default=12)
    ap.add_argument("--rotate", action="store_true")
    ap.add_argument("--tsv", type=Path)
    ap.add_argument("--compare", nargs=2, type=Path)
    a = ap.parse_args()
    if a.compare:
        return compare(*a.compare)
    if not (a.bin and a.saver):
        ap.error("BIN and --saver are needed")
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
