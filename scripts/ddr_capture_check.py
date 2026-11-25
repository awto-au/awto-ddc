#!/usr/bin/env python3
"""Does a video frame land byte-exact in DDR? (awto-ddc DDR-capture question for awto-games-dw8051#1, option A)

usage: ./dev.py ddr-capture [--unit N] run [--seed S] [--cap-s S]   one session on the unit (debug link, frame mode, freeze, sampled read-back)
       ./dev.py ddr-capture analyse [READS.json]                    offline: compare a saved read set again (no hardware)
       scripts/ddr_capture_check.py gen [--seed S]                   write the frame file only
- Test frame 3840x2160 RGB888, left half x < 1920 = PRNG fill (numpy default_rng(seed)), right half = per channel a seeded
  permutation of 0..255 rotated by y * odd step per row (every value once per 256 px, a different order on every row).
- Expected memory = the frame in bytes B, G, R per pixel, line pitch 1440 units of 8 B (docs/data-channels.md), unit u = bytes 8u..8u+7;
  a 16 B burst at even unit a reads back unit a+1 then unit a (halves swapped, docs/ddr-draw.md); the other order is counted for the log only.
- Session: frame mode 0x0C, info pop-up waited out, register snapshot, host window (raw frame) on the unit's connector, markers
  (burst at unit 0 and at the last burst of the last line seen), 3 frames, freeze (P5_27 / P45_27 bit2), reads until the screen cap,
  freeze off, window quit, 0x0D, 0x27. Reads are SAMPLES (host debug link ~15 ms per 16 B), not the whole frame.
- Result = exact equality of every compared burst; bursts whose read flag never set are counted apart (not compared).
Log: ./tmp/logs/ddr_capture_check.log ; reads: ./tmp/logs/ddr_capture_check.reads.json ; raw I2C: ./tmp/logs/ddr_frame_test.raw.log
"""
from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/ddr_capture_check.log"
READS = ROOT / "tmp/logs/ddr_capture_check.reads.json"
FRAME_FILE = ROOT / "tmp/scratch/ddr_capture_frame.bgrx"
W, H, BPP = 3840, 2160, 3
UNIT_B = 8                       # one DDR address unit
PITCH_U = W * BPP // UNIT_B      # 1440 units per memory line
FRAME_U = H * PITCH_U            # 3 110 400 units
SEED_DEFAULT = 0x20261125
STEPS = (89, 149, 211)           # odd row steps of the sequence half, per channel B, G, R
SCREEN_CAP_S = 4.5               # test frame on screen: Dan's 5 s hard cap minus margin (short-visible-tests)
FRAME_S = 1 / 59.991             # input frame time measured on unit 3 (health: 3840x2160@59.991)
SETTLE_FRAMES = 3                # marker seen -> freeze: 1 frame to finish writing + 1 for the phase + 1 margin
MARK_WAIT_S = 2.0                # pattern lands within ~2 frames of the draw; window draw ~0.3 s; limit = stall cap


def log(s: str) -> None:
    _log_line(s, LOG)


# ---------------------------------------------------------------- frame
def build_frame(seed: int) -> np.ndarray:
    """(H, W, 3) uint8, channels in memory order B, G, R."""
    f = np.empty((H, W, 3), np.uint8)
    f[:, :W // 2, :] = np.random.default_rng(seed).integers(0, 256, (H, W // 2, 3), dtype=np.uint8)
    x = np.arange(W // 2)[None, :]
    y = np.arange(H)[:, None]
    for c in range(3):
        perm = np.random.default_rng(seed + 1 + c).permutation(256).astype(np.uint8)
        f[:, W // 2:, c] = perm[(x + y * STEPS[c]) & 255]
    return f


def write_frame_file(f: np.ndarray) -> None:
    out = np.empty((H, W, 4), np.uint8)
    out[..., :3] = f                                  # file bytes B, G, R, X: cairo RGB24 little endian
    out[..., 3] = 0xFF
    FRAME_FILE.parent.mkdir(parents=True, exist_ok=True)
    FRAME_FILE.write_bytes(out.tobytes())


def units_of(f: np.ndarray) -> np.ndarray:
    return np.ascontiguousarray(f).reshape(-1).view(np.uint64)      # FRAME_U units, memory byte order


def exp_burst(f_bytes: np.ndarray, a: int, swap: int) -> bytes | None:
    """Expected 16 B read at even unit a; None past the frame."""
    if a + 1 >= FRAME_U:
        return None
    lo, hi = f_bytes[UNIT_B * a:UNIT_B * a + 8].tobytes(), f_bytes[UNIT_B * a + 8:UNIT_B * a + 16].tobytes()
    return hi + lo if swap else lo + hi


# ---------------------------------------------------------------- analysis (offline)
def analyse(reads: list[dict], f: np.ndarray, swap: int = 1) -> dict:
    fb = np.ascontiguousarray(f).reshape(-1)
    res = {"n": len(reads), "timeouts": 0, "outside": 0, "compared": 0, "exact": 0, "bad": []}
    chan_bad = [0, 0, 0]
    diffs = [Counter(), Counter(), Counter()]
    pairs = [Counter(), Counter(), Counter()]
    exact_other = 0
    for r in reads:
        a = r["addr"]
        got = bytes.fromhex(r["hex"]) if r["hex"] else None
        if got is None:
            res["timeouts"] += 1
            continue
        exp = exp_burst(fb, a, swap)
        if exp is None:
            res["outside"] += 1
            continue
        res["compared"] += 1
        if got == exp:
            res["exact"] += 1
            continue
        if got == exp_burst(fb, a, 1 - swap):
            exact_other += 1
        res["bad"].append(r)
        for i in range(16):
            ch = (UNIT_B * a + i) % 3
            if got[i] != exp[i]:
                chan_bad[ch] += 1
                diffs[ch][got[i] - exp[i]] += 1
                pairs[ch][(exp[i], got[i])] += 1
    res.update(chan_bad=chan_bad, diffs=diffs, pairs=pairs, exact_other_swap=exact_other)
    return res


def locate(bad: list[dict], f: np.ndarray) -> list[str]:
    """Where did the bytes of a mismatching burst come from? 8 B halves looked up in the frame (unit aligned) under the transforms
    identity / rotate 180 (pixel order) / rotate 180 + channel order reversed. Only the PRNG half names a unique place."""
    out = []
    tf = {"identity": f, "rot180": f[::-1, ::-1, :], "rot180+bgr<->rgb": f[::-1, ::-1, ::-1]}
    idx = {}
    for name, g in tf.items():
        u = units_of(g)
        order = np.argsort(u, kind="stable")
        idx[name] = (u[order], order)
    for r in bad:
        got = bytes.fromhex(r["hex"])
        for h in (0, 1):
            v = np.frombuffer(got[8 * h:8 * h + 8], np.uint64)[0]
            hits = []
            for name, (su, order) in idx.items():
                k = np.searchsorted(su, v)
                if k < len(su) and su[k] == v:
                    hits.append(f"{name} unit {int(order[k])}")
            out.append(f"burst @{r['addr']} half {h}: " + ("; ".join(hits) if hits else "not in the frame under any transform"))
    return out


def report(res: dict, f: np.ndarray, swap: int) -> bool:
    log(f"RESULT reads {res['n']}: compared {res['compared']}, exact {res['exact']}, mismatching {len(res['bad'])}, "
        f"read-flag timeouts (not compared) {res['timeouts']}, past the frame {res['outside']}")
    if res["compared"]:
        log(f"per-channel mismatching bytes B/G/R = {res['chan_bad'][0]}/{res['chan_bad'][1]}/{res['chan_bad'][2]} (swap model {swap}; "
            f"mismatching bursts that equal the other swap order: {res['exact_other_swap']})")
    for ch, nm in enumerate("BGR"):
        if res["diffs"][ch]:
            log(f"  {nm}: got-expected {dict(sorted(res['diffs'][ch].items()))}")
            log(f"  {nm}: first (expected -> got) pairs {res['pairs'][ch].most_common(12)}")
            fn = {}
            for e, g in res["pairs"][ch]:
                fn.setdefault(e, set()).add(g)
            multi = sum(1 for v in fn.values() if len(v) > 1)
            log(f"  {nm}: {len(fn)} distinct expected values mismatched, {multi} of them with more than one got value "
                f"({'a fixed mapping (LUT / range / matrix)' if multi == 0 else 'not a fixed mapping (noise / dither / position)'})")
    for r in res["bad"][:8]:
        exp = exp_burst(np.ascontiguousarray(f).reshape(-1), r["addr"], swap)
        first = next(i for i in range(16) if bytes.fromhex(r["hex"])[i] != exp[i])
        log(f"  first mismatch @unit {r['addr']} (line {r['addr'] // PITCH_U}, x {(r['addr'] % PITCH_U) * UNIT_B // 3}) byte {first}: "
            f"got {r['hex']} expected {exp.hex()}")
    ok = res["compared"] > 0 and not res["bad"]
    log(f"VERDICT {'BYTE-EXACT on every compared burst' if ok else 'NOT byte-exact (or nothing compared)'}")
    return ok


# ---------------------------------------------------------------- hardware session
CAP_REGS = [("M1_I_DOMAIN_TEST_SELECT", 0x0021), ("SD_FILTER_CONTROL_REG_M1", 0x0026), ("I_DITHER_COMMON_CTRL1_SETA", 0x0089),
            ("I_DITHER_COMMON_CTRL2_SETA", 0x008A), ("DIGITAL_COLOR_CTRL", 0x0099), ("RGB2YCC_CTRL", 0x009C),
            ("INPUT_GAMMA_CTRL", 0x09A1), ("I_DLTI_CTRL_M1", 0x11A1), ("FC_SD_CTRL", 0x3105), ("YUV420_TO_422_CTL", 0x3131),
            ("YUV422_TO_444_PATH0", 0x3140), ("PORCH_COLOR_CTRL", 0x3150), ("RGB_GAMMA_CTRL_M1", 0x09D0), ("D_DITHER_COMMON_CTRL1", 0x006A),
            ("CAP_M1_DDR_CTRL1", 0x0527), ("CAP_M1_DDR_CTRL2", 0x0528), ("CAP_M1_DDR_CTRL3", 0x0529), ("CAP_M1_ROTATION", 0x0549),
            ("CAP_M1_4CH_CTRL1", 0x0543), ("CAP_M1_4CH_CTRL2", 0x0544), ("CAP_M1_PIXEL_NUM_H", 0x051F), ("CAP_M1_PIXEL_NUM_L", 0x0520),
            ("CAP_M1_LINE_NUM_H", 0x0521), ("CAP_M1_LINE_NUM_L", 0x0522), ("CAP_M1_WR_NUM_H", 0x0523), ("CAP_M1_WR_NUM_L", 0x0524),
            ("CAP_M1_WR_LEN", 0x0525), ("P5_AC", 0x05AC)]
CAP_BLOCKS = [("CAP_M1_MEM_ADDR", 0x0500, 4), ("CAP_M1_BL2_ADDR", 0x0504, 4), ("CAP_M1_BL3_ADDR", 0x0508, 4), ("CAP_M1_BLOCK_STEP", 0x0515, 4),
              ("CAP_M1_LINE_STEP", 0x0519, 4), ("CAP_M2_MEM_ADDR", 0x4500, 4), ("CAP_M2_BL2_ADDR", 0x4504, 4), ("CAP_M2_BLOCK_STEP", 0x4515, 4),
              ("CAP_M2_LINE_STEP", 0x4519, 4)]


def snapshot(d) -> dict:
    snap = {}
    for nm, a in CAP_REGS + [("CAP_M2_" + n[7:], a + 0x4000) for n, a in CAP_REGS if n.startswith("CAP_M1_")]:
        snap[nm] = d.rd(a)
    for nm, a, n in CAP_BLOCKS:
        snap[nm] = int.from_bytes(bytes(d.rd(a + i) for i in range(n)), "big")
    saved = {}
    try:                                        # newest saved 4K dump of this unit (tmp/regs), for the log only
        cand = sorted((ROOT / "tmp/regs").glob("AWT26110003-*4k*.json"))
        if cand:
            pg = json.loads(cand[-1].read_text())["pages"]
            for nm, a in CAP_REGS:
                if f"{a >> 8:02X}" in pg:
                    saved[nm] = pg[f"{a >> 8:02X}"][a & 255]
            log(f"saved dump for comparison: {cand[-1].name}")
    except (OSError, ValueError, KeyError, IndexError):
        pass
    for nm, v in snap.items():
        sv = saved.get(nm)
        log(f"  reg {nm:30s} live {v:#x}" + (f"  saved {sv:#04x}" if sv is not None else ""))
    return snap


def sample_addresses(seed: int) -> list[int]:
    lines = (1, 2, 540, 1079, 1080, 1081, 2158, 2159)
    pri = list(range(0, 32, 2)) + [y * PITCH_U for y in lines] + [y * PITCH_U + 720 for y in (0, 1080, 2159)] + [FRAME_U - 2]
    rnd = random.Random(seed)
    rest = [2 * rnd.randrange(FRAME_U // 2) for _ in range(4000)]
    return pri + rest


class Reader:
    """MCU_DC port A read, LEN 2 (16 B). The stale-flag clear costs one block read but a stale buffer would fake a mismatch."""

    def __init__(self, d):
        import ddr_frame_test as T
        self.d, self.T, self.cur = d, T, [None] * 4
        self.r = T.MCU_DC["a"]
        d.wr(self.r["len"], 2)

    def read(self, a: int, limit_s: float = 0.05) -> bytes | None:       # 50 ms = 3 frames of DDR arbitration (ddr_frame_test.dc_burst_read)
        d, r = self.d, self.r
        for i, sh in enumerate((24, 16, 8, 0)):
            b = (a >> sh) & 0xFF
            if self.cur[i] != b:
                d.wr(r["addr"] + i, b)
                self.cur[i] = b
        d.block(r["rbuf"], 16)
        d.wr(r["cmd"], self.T.DC_CMD_READ)
        t = time.monotonic()
        while time.monotonic() - t < limit_s:
            if d.rd(r["flag"]) & 1:
                return d.block(r["rbuf"], 16)
        return None


def pattern_start(F, connector: str) -> subprocess.Popen:
    if F.FIFO.exists():
        F.FIFO.unlink()
    return subprocess.Popen(["/usr/bin/python3", str(ROOT / "scripts/host_pattern.py"), "--connector", connector, "--fifo", str(F.FIFO),
                             "--initial", f"raw {FRAME_FILE}"], stdout=open(ROOT / "tmp/logs/host_pattern.out", "w"), stderr=subprocess.STDOUT)


def run(a) -> int:
    import ddr_frame_test as T
    import ddr_freeze_test as F
    T.LOG = LOG
    f = build_frame(a.seed)
    fb = np.ascontiguousarray(f).reshape(-1)
    write_frame_file(f)
    log(f"frame seed {a.seed:#x}: {W}x{H} RGB888 {f.nbytes} B, left half PRNG, right half permutation sequence; file {FRAME_FILE}")
    d = T.Dbg(a.unit, a.bus)
    reads, marks, proc, t_on = [], {}, None, None
    snap = {}
    try:
        F.frame_mode(d.io)
        # no pop-up wait: the diag console stays open during tests (tests-on-diag-screen); the overlay sits after the DDR, not in it
        snap = snapshot(d)
        rd = Reader(d)
        t_on = time.monotonic()
        proc = pattern_start(F, a.connector)
        def u(n: int) -> bytes:
            return fb[UNIT_B * n:UNIT_B * n + 8].tobytes()
        last = (H - 1) * PITCH_U + PITCH_U - 2
        want = {"unit0": (0, {u(0), u(1)}), "last_line": (last, {u(last), u(last + 1)})}
        while time.monotonic() - t_on < MARK_WAIT_S and len(marks) < len(want):
            for nm, (addr, halves) in want.items():
                if nm in marks:
                    continue
                g = rd.read(addr)
                if g is not None and (g[:8] in halves or g[8:] in halves):
                    marks[nm] = time.monotonic() - t_on
        log(f"markers seen (s after window start): {marks} of {list(want)}")
        t = time.monotonic()
        while time.monotonic() - t < SETTLE_FRAMES * FRAME_S:
            F.prd(d.io, F.P5_AC)
        F.freeze(d.io, True)
        t_frz = time.monotonic() - t_on
        log(f"freeze on at {t_frz:.2f} s after window start")
        addrs = sample_addresses(a.seed)
        n_to = 0
        for ad in addrs:
            if time.monotonic() - t_on > a.cap_s - 0.3:
                break
            g = rd.read(ad)
            n_to += g is None
            reads.append({"addr": ad, "hex": g.hex() if g else None, "t": round(time.monotonic() - t_on, 3)})
        log(f"reads: {len(reads)} bursts in {time.monotonic() - t_on - t_frz:.2f} s after the freeze")
    finally:
        if proc is not None:
            F.finish(d, proc, t_on)
        else:
            F.freeze(d.io, False)
            F.cmd(d.io, F.TC_SDK)
        d.io.close()
    READS.write_text(json.dumps({"seed": a.seed, "unit": a.unit, "swap": 1, "markers": marks, "regs": snap, "reads": reads}))
    log(f"reads saved: {READS}")
    ok = report(analyse(reads, f, 1), f, 1)
    geometry(reads, f)
    return 0 if ok else 1


def geometry(reads: list[dict], f: np.ndarray) -> None:
    """Analysis only (not the verdict): memory line L (L < 1080 = block 1) = frame row 2L, pixel p = frame x 3839 - p, bytes B, G, R.
    Per channel: is the got byte a function of the sent byte (a LUT: range / gamma stage) or position dependent (dither / filter)?"""
    from collections import defaultdict
    tab = [defaultdict(Counter) for _ in range(3)]
    blk2 = n1 = nbytes = 0
    dev = Counter()
    for r in reads:
        if not r["hex"]:
            continue
        a = r["addr"]
        if a // PITCH_U >= H // 2:
            blk2 += 1
            continue
        n1 += 1
        b = bytes.fromhex(r["hex"])
        b = b[8:] + b[:8]
        for i, v in enumerate(b):
            p, c = divmod(UNIT_B * a % (PITCH_U * UNIT_B) + i, 3)
            if p < W:
                e = int(f[2 * (a // PITCH_U), W - 1 - p, c])
                tab[c][e][v] += 1
                dev[v - (16 + e * 219 // 255)] += 1
                nbytes += 1
    log(f"GEOMETRY (model: line L < 1080 = frame row 2L, pixel p = frame x {W - 1} - p): {n1} bursts in block 1 ({nbytes} bytes), "
        f"{blk2} bursts at memory lines >= 1080 (not part of the capture, content unrelated to the frame)")
    for c, nm in enumerate("BGR"):
        amb = {e: dict(g) for e, g in tab[c].items() if len(g) > 1}
        mono = all(max(a) <= min(b) for (_, a), (_, b) in zip(sorted(((e, list(g)) for e, g in tab[c].items()))[:-1],
                                                              sorted(((e, list(g)) for e, g in tab[c].items()))[1:], strict=True))
        log(f"  {nm}: {len(tab[c])} distinct sent values seen, {len(amb)} with more than one stored value, monotonic {mono}")
    log(f"  stored - (16 + floor(sent * 219 / 255)) over {nbytes} bytes: {dict(sorted(dev.items()))}")
    lut = {e: next(iter(g)) for c in range(3) for e, g in tab[c].items() if len(g) == 1}
    log("  sent -> stored (limited-range shape, 0 -> 16, 255 -> " + str(lut.get(255, "?")) + "): "
        + " ".join(f"{e}:{lut[e]}" for e in (0, 1, 2, 64, 128, 192, 254, 255) if e in lut))


def recover(raw: Path, since: str) -> list[dict]:
    """Rebuild the read list from the raw I2C log (ddr_frame_test.raw.log) lines from the first line starting with SINCE (an ISO stamp)."""
    addr, pend, got_flag, out, seen = [0, 0, 0, 0], None, False, [], False
    for ln in raw.read_text().splitlines():
        if not seen:
            if since.startswith("freeze@"):                        # first freeze write (P45_27 <- ..) at/after the stamp
                seen = ln >= since[7:] and " wr 4527 <- " in ln
            else:
                seen = ln >= since
            continue
        t, _, rest = ln.partition(" ")
        w = rest.split()
        if w[0] == "wr" and w[1] in ("3704", "3705", "3706", "3707"):
            addr[int(w[1], 16) - 0x3704] = int(w[3], 16)
        elif w[0] == "wr" and w[1] == "3700" and w[3] == "A0":
            if pend is not None:
                out.append({"addr": pend[0], "hex": None, "t": pend[1]})
            pend, got_flag = (int.from_bytes(bytes(addr), "big"), t), False
        elif w[0] == "rd" and w[1] == "3734" and pend is not None:
            got_flag = got_flag or int(w[3], 16) & 1 == 1
        elif w[0] == "blk" and w[1] == "3720+16" and pend is not None and got_flag:
            out.append({"addr": pend[0], "hex": w[3], "t": pend[1]})
            pend = None
    if pend is not None:
        out.append({"addr": pend[0], "hex": None, "t": pend[1]})
    return out


def offline(a) -> int:
    if a.recover:
        reads = recover(ROOT / "tmp/logs/ddr_frame_test.raw.log", a.recover)
        k = next((i for i, r in enumerate(reads) if r["addr"] == 2), None)     # sample list starts 0, 2, 4 ..; the marker loop only reads 0 and the last burst
        if k:
            log(f"{k - 1} marker-loop reads dropped (addresses 0 / last burst before the sample list)")
            reads = reads[k - 1:]
        j = {"seed": a.seed, "swap": 1, "reads": reads}
        READS.write_text(json.dumps(j))
        log(f"recovered {len(reads)} reads from the raw log since {a.recover}; saved {READS}")
    else:
        j = json.loads(Path(a.reads or READS).read_text())
    f = build_frame(j["seed"])
    res = analyse(j["reads"], f, j.get("swap", 1))
    ok = report(res, f, j.get("swap", 1))
    geometry(j["reads"], f)
    if res["bad"] and a.locate:
        for line in locate(res["bad"][:40], f):
            log("  " + line)
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("what", choices=("run", "analyse", "gen"))
    ap.add_argument("reads", nargs="?")
    ap.add_argument("--unit", type=int, default=3)
    ap.add_argument("--bus", type=int)
    ap.add_argument("--connector", default="HDMI-2")
    ap.add_argument("--seed", type=lambda v: int(v, 0), default=SEED_DEFAULT)
    ap.add_argument("--recover", help="analyse: rebuild the reads from the raw I2C log lines at/after this ISO stamp, or freeze@STAMP = after the first freeze write at/after STAMP")
    ap.add_argument("--locate", action="store_true", help="analyse: also look each mismatching 8 B half up in the frame (aligned, 3 transforms)")
    ap.add_argument("--cap-s", type=float, default=SCREEN_CAP_S)
    a = ap.parse_args()
    if a.what == "gen":
        write_frame_file(build_frame(a.seed))
        log(f"frame file written: {FRAME_FILE}")
        return 0
    return run(a) if a.what == "run" else offline(a)


if __name__ == "__main__":
    sys.exit(main())
