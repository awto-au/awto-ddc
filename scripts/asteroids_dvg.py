#!/usr/bin/env python3
"""Asteroids DVG vector-ROM decoder (host tool, local ROM only, output stays in ./tmp/asteroids/).

Clean-room from public DVG documentation (opcode set, scale rule); no ROM bytes in the repo.
Usage: asteroids_dvg.py [--zip PATH] [--out DIR] [--disasm]
Logs: ./tmp/logs/asteroids_dvg.log
"""
import argparse
import hashlib
import json
import logging
import os
import sys
import zipfile
from pathlib import Path

LOG = logging.getLogger(__name__)
ROM_NAME = "035127-02.np3"
DEFAULT_ZIP = "/vendors/atari/asteroids-mame/sources/asteroid.zip"
ROM_BASE_WORD = 0x800  # vector ROM at 6502 0x5000 -> DVG word address 0x800
OP_CUR, OP_HALT, OP_JSR, OP_RTS, OP_JMP, OP_SVEC = 0xA, 0xB, 0xC, 0xD, 0xE, 0xF


from _repo import repo_root


def setup_log(root):
    d = root / "tmp" / "logs"
    d.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(d / "asteroids_dvg.log"),
                                  logging.StreamHandler(sys.stdout)])


def load_rom(zip_path):
    with zipfile.ZipFile(zip_path) as z:
        d = z.read(ROM_NAME)
    return [d[i] | d[i + 1] << 8 for i in range(0, len(d), 2)]


def sgn(mag, neg):
    return -mag if neg else mag


class Dvg:
    def __init__(self, words):
        self.w = words

    def fetch(self, a):
        i = a - ROM_BASE_WORD
        if not 0 <= i < len(self.w):
            raise IndexError(f"word address {a:#x} outside ROM")
        return self.w[i]

    def decode(self, addr, gs=0, max_ops=400):
        """Run from word address addr. Returns (segments, trace).
        segments: (x0,y0,x1,y1,bright) in units of 1/512 DVG pixel-steps; beam starts at 0,0
        (CUR positions are recorded as a 'cur' marker, drawn as a blank move)."""
        x = y = 0.0
        segs, ops, stack = [], [], []
        pc = addr
        for _ in range(max_ops):
            try:
                w0 = self.fetch(pc)
            except IndexError:
                ops.append(("EXT", pc))  # target outside this ROM (vector RAM / other ROM)
                break
            op = w0 >> 12
            if op <= 9:  # VCTR: two words
                w1 = self.fetch(pc + 1)
                dy = sgn(w0 & 0x3FF, w0 & 0x400)
                dx = sgn(w1 & 0x3FF, w1 & 0x400)
                br, s = w1 >> 12, (gs + op) & 0xF
                pc += 2
                ops.append(("VCTR", dx, dy, s, br))
            elif op == OP_SVEC:
                dy = sgn((w0 & 0x300), w0 & 0x400)
                dx = sgn((w0 & 0x003) << 8, w0 & 0x004)
                br = (w0 >> 4) & 0xF
                s = (gs + 2 + ((w0 >> 11) & 1) + ((w0 >> 2) & 2)) & 0xF
                pc += 1
                ops.append(("SVEC", dx, dy, s, br))
            elif op == OP_CUR:
                w1 = self.fetch(pc + 1)
                gs = w1 >> 12
                x, y = float(w1 & 0xFFF), float(w0 & 0xFFF)
                pc += 2
                ops.append(("CUR", x, y, gs, 0))
                continue
            elif op == OP_HALT:
                ops.append(("HALT",))
                break
            elif op == OP_JSR:
                stack.append(pc + 1)
                pc = w0 & 0xFFF
                ops.append(("JSR", pc))
                continue
            elif op == OP_RTS:
                ops.append(("RTS",))
                if not stack:
                    break
                pc = stack.pop()
                continue
            else:  # OP_JMP
                pc = w0 & 0xFFF
                ops.append(("JMP", pc))
                continue
            _kind, dx, dy, s, br = ops[-1]
            sc = 2.0 ** s / 512.0 if s <= 9 else 0.0  # scale 9 = x1; >= 10 gives no motion
            nx, ny = x + dx * sc, y + dy * sc
            if br:
                segs.append((x, y, nx, ny, br))
            x, y = nx, ny
        return segs, ops


def rel_segs(segs, x0, y0):
    return [(a - x0, b - y0, c - x0, d - y0, br) for a, b, c, d, br in segs]


def pointer_tables(words):
    """Runs of >= 3 consecutive JSR words whose targets lie in the ROM."""
    tabs, cur = [], []
    for i, w in enumerate(words):
        t = w & 0xFFF
        if w >> 12 == OP_JSR and ROM_BASE_WORD <= t < ROM_BASE_WORD + len(words):
            cur.append((i, t))
        else:
            if len(cur) >= 3:
                tabs.append(cur)
            cur = []
    if len(cur) >= 3:
        tabs.append(cur)
    return tabs


def sweep(dvg, n_words):
    """Linear sweep: split ROM into subroutines ending at RTS / HALT / JMP."""
    subs, pc, st = [], ROM_BASE_WORD, ROM_BASE_WORD
    while pc < ROM_BASE_WORD + n_words:
        op = dvg.fetch(pc) >> 12
        pc += 2 if op <= 0xA else 1
        if op in (OP_HALT, OP_RTS, OP_JMP):
            subs.append((st, pc - 1, op))
            st = pc
    return subs


def bbox(segs):
    xs = [p for s in segs for p in (s[0], s[2])]
    ys = [p for s in segs for p in (s[1], s[3])]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0, 0, 0, 0)


def render(segs, path, size=240, pad=8, scale=None):
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (size, size), (0, 0, 0))
    dr = ImageDraw.Draw(img)
    if segs:
        x0, y0, x1, y1 = bbox(segs)
        span = max(x1 - x0, y1 - y0, 1e-6)
        k = scale or (size - 2 * pad) / span
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        for a, b, c, d, br in segs:
            g = 80 + br * 11
            dr.line([(size / 2 + (a - cx) * k, size / 2 - (b - cy) * k),
                     (size / 2 + (c - cx) * k, size / 2 - (d - cy) * k)], fill=(g, g, g))
    img.save(path)




def brm_delta(mag, scale):
    """Displacement from a 12-bit rate-multiplier model of the DVG (independent of Dvg.decode)."""
    steps, m, c, n = (2 << scale) & 0x7FF, (mag << 2) & 0xFFF, 0, 0
    for _ in range(steps):
        for bit in range(12):
            if (c & ((1 << (bit + 1)) - 1)) == ((1 << bit) - 1) and m & (1 << (11 - bit)):
                n += 1
                break
        c = (c + 1) & 0xFFF
    return n


def verify_ops(dvg, words):
    """Cross-check every vector op in the ROM: analytic delta vs rate-multiplier model."""
    worst, n = 0.0, 0
    for st, _, _ in sweep(dvg, len(words)):
        _, ops = dvg.decode(st)
        for o in ops:
            if o[0] in ("VCTR", "SVEC") and o[3] <= 9:
                for mag in (abs(o[1]), abs(o[2])):
                    worst = max(worst, abs(brm_delta(mag, o[3]) - mag * 2.0 ** o[3] / 512.0))
                    n += 1
    return n, worst


def catalog(dvg, words):
    """Named shapes by ROM address: chars (table of 37), asteroids, saucer, ship, debris."""
    cat = {}
    tab4 = max(pointer_tables(words), key=len)
    for i, (_, t) in enumerate(tab4):
        cat["char_" + (" " if i == 0 else "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"[i - 1])] = t
    for i, a in enumerate((0x8F3, 0x8FF, 0x90D, 0x91A)):
        cat[f"rock{i}"] = a
    cat["saucer"] = 0x929
    for i, a in enumerate((0x880, 0x896, 0x8B5, 0x8D0)):
        cat[f"debris{i}"] = a
    ship = [s for s in sweep(dvg, len(words)) if 0x951 <= s[0] <= 0xA77]
    for i in range(17):
        cat[f"flame{i:02d}"] = ship[2 * i][0]
        cat[f"hull{i:02d}"] = ship[2 * i + 1][0]
    return cat


def polylines(segs, nd=1):
    """Merge consecutive segments into pen-down polylines (rounded to nd decimals)."""
    out, cur, last = [], [], None
    for a, b, c, d, _ in segs:
        p0, p1 = (round(a, nd), round(b, nd)), (round(c, nd), round(d, nd))
        if cur and last == p0:
            cur.append(p1)
        else:
            if cur:
                out.append(cur)
            cur = [p0, p1]
        last = p1
    if cur:
        out.append(cur)
    return out


def sample_frame(shapes, path, w=1024, h=768):
    """Synthetic frame (not a 6502 capture): rocks, saucer, ship + flame, score and lives."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (w, h), (0, 0, 0))
    dr = ImageDraw.Draw(img)

    def put(name, x, y, k):
        if name.startswith("flame"):  # drawn from where the hull's closed outline ends
            ex, ey = shapes["hull" + name[5:]]["lines"][-1][-1]
            x, y = x + ex * k, y + ey * k
        for pl in shapes[name]["lines"]:
            dr.line([(x + px * k, h - (y + py * k)) for px, py in pl], fill=(230, 230, 230), width=2)

    for name, x, y, k in (("rock1", 200, 560, 3), ("rock0", 780, 600, 3), ("rock2", 300, 180, 1.5),
                          ("rock3", 860, 200, 1.5), ("rock1", 560, 120, 0.75), ("saucer", 520, 480, 1.6),
                          ("hull06", 500, 340, 1.6), ("flame06", 500, 340, 1.6)):
        put(name, x, y, k)
    for i, ch in enumerate("1250"):
        put("char_" + ch, 100 + i * 14 * 2, 740, 2)
    for i in range(3):
        put("hull16", 150 + i * 24, 700, 0.5)
    img.save(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--zip", default=os.environ.get("ASTEROIDS_ZIP", DEFAULT_ZIP))
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    root = repo_root()
    setup_log(root)
    out = Path(a.out) if a.out else root / "tmp" / "asteroids"
    out.mkdir(parents=True, exist_ok=True)
    words = load_rom(a.zip)
    dvg = Dvg(words)
    LOG.info("ROM %s: %d words, sha256 %s", ROM_NAME, len(words),
                 hashlib.sha256(b"".join(w.to_bytes(2, "little") for w in words)).hexdigest()[:16])
    n, worst = verify_ops(dvg, words)
    LOG.info("verify: %d vector deltas vs rate-multiplier model, worst error %.2f px", n, worst)
    shapes = {}
    for name, addr in catalog(dvg, words).items():
        segs, _ = dvg.decode(addr)
        shapes[name] = {"addr": addr, "nseg": len(segs), "lines": polylines(segs), "bbox": bbox(segs)}
        render(segs, out / (name.replace(" ", "sp") + ".png"))
        if name.startswith("rock"):
            LOG.info("%s closed: start %s end %s", name, segs[0][:2], segs[-1][2:4])
    (out / "shapes.json").write_text(json.dumps(shapes))
    for grp in ("char_", "rock", "saucer", "debris", "hull", "flame"):
        sel = {k: v for k, v in shapes.items() if k.startswith(grp)}
        blob = json.dumps({k: v["lines"] for k, v in sorted(sel.items())}, sort_keys=True).encode()
        LOG.info("%-7s %2d shapes %3d segments %4d polylines sha256 %s", grp, len(sel),
                     sum(v["nseg"] for v in sel.values()), sum(len(v["lines"]) for v in sel.values()),
                     hashlib.sha256(blob).hexdigest()[:16])
    sample_frame(shapes, out / "frame_sample.png")
    LOG.info("wrote %s", out)


if __name__ == "__main__":
    main()
