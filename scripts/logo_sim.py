#!/usr/bin/env python3
"""Boot-logo check in the fw_sim model: run an image to the logo draw, capture the OSD char-map writes, render a PNG (#46).

usage: logo_sim.py BIN MAP [--tag T] [--ref REF.json]
  Runs BIN (boot path calls OsdDispShowLogo) until OsdFuncEnableOsd after it; taps the OSD address/data port
  (P0_90/91/92, write option P0_94). Char map = last 3-byte (ByteAll) write per SRAM address.
  Render = char-map ids -> tiles decoded from the VLC blobs tICON_*_LOGO0/1 as they sit in BIN (bank:addr from MAP).
  Wrong-bank read of the tile map (tiOSD_*) shows as a different id grid vs the reference.
  --ref: JSON from a previous run (id grid); exit 1 when the grid differs.
Out: tmp/logs/logo_sim_<tag>.png + .json; log tmp/logs/logo_sim.log
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402
import fw_sim as S  # noqa: E402
from glyph_decode import decode_blob, tile  # noqa: E402

ROOT = S.ROOT
TW, TH, WIDTH, ROWS = 12, 18, 70, 10
OSD_ADR_H, OSD_ADR_L, OSD_DATA, OSD_OPT = 0x0090, 0x0091, 0x0092, 0x0094
LOG = ROOT / "tmp/logs/logo_sim.log"


class OsdTap(S.Dev):
    """Write tap on the OSD port: char entries {sram_addr: [b0, b1, b2]} for ByteAll writes (P0_94[7:5] = 111)."""
    writes = (OSD_ADR_L, OSD_DATA)

    def __init__(self):
        self.chars, self.addr, self.pend, self.nwr = {}, 0, [], 0

    def on_write(self, m, a):
        v = m.rd(a)[0]
        if a == OSD_ADR_L:
            self.addr = (m.rd(OSD_ADR_H)[0] & 0x7F) << 8 | v
            self.pend = []
            return
        self.nwr += 1
        if (m.rd(OSD_OPT)[0] >> 5) != 7:
            return
        self.pend.append(v)
        if len(self.pend) == 3:
            self.chars[self.addr] = self.pend
            self.addr, self.pend = self.addr + 1, []        # auto-increment per 3-byte entry


def blob_at(img, sym, name):
    v = sym["_" + name]
    return decode_blob(img[v:v + 4000], 0)[2]


def run(binp: Path, mapp: Path, tag: str):
    img = binp.read_bytes()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (ROOT / "tmp/logs/fw_sim_logo.log").open("w", buffering=1)
    devs, hdmi = S.video_devs(img, "1080p60")
    tap = OsdTap()
    m = S.Machine(img, mapp, "logo-" + tag, log, [*devs, tap])
    m.t2_scale = S.T2_SCALE
    S.video_stubs(m, hdmi)
    st = {"show": None, "done": None}
    m.stub("OsdDispShowLogo", lambda m_, r: st.__setitem__("show", m_.instr))
    m.stub("OsdFuncEnableOsd", lambda m_, r: st.__setitem__("done", m_.instr) if st["show"] is not None and st["done"] is None else None)
    used = 0
    while used < 60_000_000 and st["done"] is None:
        m.run(1_000_000); used += 1_000_000
    if st["done"] is None:
        m.close()
        raise SystemExit(f"{tag}: OsdDispShowLogo not reached/finished in {used} instr (show={st['show']})")
    m.run(300_000)
    m.close()
    # char map: ids of the 70x10 grid (the block of ByteAll entries with the lowest address that has 700 entries)
    base = min(tap.chars)
    grid = [[tap.chars.get(base + r * WIDTH + c, [0, 0, 0])[1] for c in range(WIDTH)] for r in range(ROWS)]
    t0, t1 = blob_at(img, m.sym, "tICON_REALTEK_1BIT_LOGO0"), blob_at(img, m.sym, "tICON_REALTEK_1BIT_LOGO1")
    return img, m, grid, t0, t1, st, tap


def render(grid, t0, t1, base1):
    g = np.zeros((ROWS * TH, WIDTH * TW), np.uint8)
    for r in range(ROWS):
        for c in range(WIDTH):
            i = grid[r][c]
            try:
                tl = tile(t0, i) if i < base1 else tile(t1, i - base1)
            except Exception:
                tl = np.full((TH, TW), 1, np.uint8)
            g[r * TH:(r + 1) * TH, c * TW:(c + 1) * TW] = tl
    return g


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("bin"); ap.add_argument("map")
    ap.add_argument("--tag"); ap.add_argument("--ref")
    ap.add_argument("--base1", type=int, default=80, help="font id of LOGO1 tile 0 (LOGO0 has 80 slots)")
    a = ap.parse_args()
    b = Path(a.bin)
    tag = a.tag or b.stem
    img, m, grid, t0, t1, st, tap = run(b, Path(a.map), tag)
    out = ROOT / f"tmp/logs/logo_sim_{tag}"
    json.dump({"grid": grid}, out.with_suffix(".json").open("w"))
    g = render(grid, t0, t1, a.base1)
    Image.fromarray(255 - g * 255).save(out.with_suffix(".png"))
    msg = f"{tag}: logo drawn at instr {st['show']}..{st['done']}, {len(tap.chars)} char entries, png {out.with_suffix('.png')}"
    rc = 0
    if a.ref:
        ref = json.load(open(a.ref))["grid"]
        diff = sum(x != y for r1, r2 in zip(grid, ref) for x, y in zip(r1, r2))
        msg += f"; id grid vs ref: {diff} of {WIDTH * ROWS} cells differ"
        rc = 1 if diff else 0
    print(msg)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(msg + "\n")
    return rc


if __name__ == "__main__":
    sys.exit(main())
