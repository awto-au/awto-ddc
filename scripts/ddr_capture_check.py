#!/usr/bin/env python3
"""Does a video frame land byte-exact in DDR? (awto-ddc DDR-capture question for awto-games-dw8051#1, option A)

usage: ./dev.py ddr-capture [--unit N] run [--seed S] [--cap-s S]   one session on the unit (debug link, frame mode, freeze, sampled read-back)
       ./dev.py ddr-capture [--unit N] run-rows [--seed S]              #348 test 1: independent rows, port A vs row 2L, port B vs row 2L+1
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

    def __init__(self, d, port: str = "a"):
        import ddr_frame_test as T
        self.d, self.T, self.cur = d, T, [None] * 4
        self.r = T.MCU_DC[port]
        ln = d.rd(self.r["len"])
        log(f"MCU_DC port {port} LEN read {ln:#04x} (regdb reset 0x02; A: other values kill the port, #255; B: kept at 2, never written)")
        if port == "a":
            d.wr(self.r["len"], 2)
        elif ln != 2:
            raise SystemExit(f"port B LEN {ln:#04x} != 2: refused (no write to MCU_DC_LEN_B)")

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


REGDB = ROOT / "re/regdb/RTD2795T-CG.tsv.gz"


def decode_regs(snap: dict) -> None:
    """One log line per field of the snapshot registers (regdb names, first line of the description)."""
    import gzip
    by_addr: dict[int, list] = {}
    with gzip.open(REGDB, "rt") as fh:
        for ln in fh:
            c = ln.rstrip("\n").split("\t")
            if len(c) > 16 and c[4] == "FIELD" and c[1].startswith("0x"):
                by_addr.setdefault(int(c[1], 16), []).append(c)
    for nm, a in CAP_REGS:
        v = snap.get(nm)
        if v is None:
            continue
        for c in by_addr.get(a, []):
            hi, lo = int(c[6]), int(c[7])
            fv = (v >> lo) & ((1 << (hi - lo + 1)) - 1)
            log(f"  {nm} 0x{a:04X} [{hi}:{lo}] {c[8]} = {fv:#x}  ({c[16].replace(chr(92) + 'n', ' | ')[:110]})")


def run_levels(a) -> int:
    """Encoded payload (scripts/ddr_levels.py) as the frame; compare sampled bursts of block 1 by exact equality of the stored bytes,
    and decode the contiguous reads back to payload bytes."""
    import ddr_frame_test as T
    import ddr_freeze_test as F
    import ddr_levels as LV
    T.LOG = LOG
    payload = np.random.default_rng(a.seed ^ 0x5A5A).integers(0, 256, a.payload_kb * 1000, dtype=np.uint8).tobytes()
    n = len(LV.load_table()[0])
    lv = LV.memory_levels(payload, a.seed)
    stored = LV.stored_memory(lv)                       # expected bytes of block 1, memory order
    data_levels = len(LV.to_levels(payload, n))
    data_bursts = data_levels // 16                     # 16 levels = 16 B = one burst
    write_frame_file(LV.frame_from_levels(lv))
    stream = len(payload).to_bytes(LV.HDR_B, "big") + payload
    log(f"levels run: {len(payload)} B payload, {n} levels, {data_levels} levels = {data_bursts} bursts "
        f"({data_levels / LV.LINE_B:.1f} memory lines) of {LV.CAP_LEVELS // 16} bursts in block 1; capacity {LV.capacity_bytes(n)} B of "
        f"{LV.CAP_LEVELS} raw ({100 * LV.capacity_bytes(n) / LV.CAP_LEVELS:.1f} %); filler = seeded PRNG levels")

    def exp(ad: int) -> bytes:
        return stored[UNIT_B * ad + 8:UNIT_B * ad + 16].tobytes() + stored[UNIT_B * ad:UNIT_B * ad + 8].tobytes()   # swapped halves
    d = T.Dbg(a.unit, a.bus)
    reads, marks, proc, t_on, snap = [], {}, None, None, {}
    try:
        F.frame_mode(d.io)
        snap = snapshot(d)
        decode_regs(snap)
        rd = Reader(d)
        t_on = time.monotonic()
        proc = pattern_start(F, a.connector)
        last = LV.LINES * PITCH_U - 2
        want = {"unit0": 0, "last_burst": last}
        while time.monotonic() - t_on < MARK_WAIT_S and len(marks) < len(want):
            for nm, ad in want.items():
                if nm not in marks:
                    g = rd.read(ad)
                    if g is not None and g == exp(ad):
                        marks[nm] = round(time.monotonic() - t_on, 2)
        log(f"markers (exact, s after window start): {marks} of {list(want)}")
        t = time.monotonic()
        while time.monotonic() - t < SETTLE_FRAMES * FRAME_S:
            F.prd(d.io, F.P5_AC)
        F.freeze(d.io, True)
        t_frz = time.monotonic() - t_on
        log(f"freeze on at {t_frz:.2f} s after window start")
        rnd = random.Random(a.seed)
        plan = list(range(0, 120, 2))                      # 60 contiguous bursts = 30 chunks
        for _ in range(4000):
            plan.append(2 * rnd.randrange(data_bursts))                           # payload area (unit address = 2 x burst index)
            plan.append(2 * rnd.randrange(data_bursts, LV.CAP_LEVELS // 16))      # filler area of block 1
        for ad in plan:
            if time.monotonic() - t_on > a.cap_s - 0.3:
                break
            g = rd.read(ad)
            reads.append({"addr": ad, "hex": g.hex() if g else None, "t": round(time.monotonic() - t_on, 3)})
        log(f"reads: {len(reads)} bursts in {time.monotonic() - t_on - t_frz:.2f} s after the freeze")
    finally:
        if proc is not None:
            F.finish(d, proc, t_on)
        else:
            F.freeze(d.io, False)
            F.cmd(d.io, F.TC_SDK)
        d.io.close()
        READS.write_text(json.dumps({"mode": "levels", "seed": a.seed, "payload_kb": a.payload_kb, "unit": a.unit, "markers": marks, "regs": snap, "reads": reads}))
        log(f"reads saved: {READS}")
    return 0 if analyse_levels(reads, payload, a.seed, data_bursts, stream) else 1


def analyse_levels(reads: list[dict], payload: bytes, seed: int, data_bursts: int, stream: bytes) -> bool:
    import ddr_levels as LV
    n = len(LV.load_table()[0])
    stored = LV.stored_memory(LV.memory_levels(payload, seed))
    tot = {"payload": [0, 0], "filler": [0, 0]}
    timeouts = 0
    bad_bytes = [0, 0, 0]
    first = []
    contig = {}
    for r in reads:
        if not r["hex"]:
            timeouts += 1
            continue
        ad = r["addr"]
        got = bytes.fromhex(r["hex"])
        e = stored[UNIT_B * ad + 8:UNIT_B * ad + 16].tobytes() + stored[UNIT_B * ad:UNIT_B * ad + 8].tobytes()
        k = "payload" if ad // 2 < data_bursts else "filler"
        tot[k][0] += 1
        if got == e:
            tot[k][1] += 1
        else:
            for i in range(16):
                if got[i] != e[i]:
                    bad_bytes[(UNIT_B * ad + i) % 3] += 1
            if len(first) < 8:
                first.append(f"@unit {ad} (line {ad // PITCH_U}) got {got.hex()} expected {e.hex()}")
        if ad < 120:
            contig[ad] = got[8:] + got[:8]
    cmp_n = tot["payload"][0] + tot["filler"][0]
    exact = tot["payload"][1] + tot["filler"][1]
    log(f"RESULT sampled {len(reads)} bursts of 777600 in block 1 (payload area = {data_bursts} bursts): compared {cmp_n}, "
        f"exact {exact}, mismatching {cmp_n - exact}, read-flag timeouts (not compared) {timeouts}")
    log(f"  payload area: {tot['payload'][1]}/{tot['payload'][0]} exact; filler area: {tot['filler'][1]}/{tot['filler'][0]} exact; "
        f"mismatching bytes B/G/R = {bad_bytes}")
    for ln in first:
        log("  first mismatch " + ln)
    dec_ok = None
    if len(contig) == 60 and sorted(contig) == list(range(0, 120, 2)):
        lv = LV.levels_from_stored(np.frombuffer(b"".join(contig[x] for x in range(0, 120, 2)), np.uint8))
        if (lv == 255).any():
            log(f"  contiguous 960 B: {int((lv == 255).sum())} stored bytes are not table values")
            dec_ok = False
        else:
            out = LV.from_levels(lv, n, whole=False)
            dec_ok = out == stream[:len(out)]
            log(f"  contiguous 960 B decoded to {len(out)} B (length header + payload): {'EQUAL to the payload' if dec_ok else 'DIFFERENT'}")
    ok = cmp_n > 0 and exact == cmp_n and dec_ok is not False
    log(f"VERDICT {'BYTE-EXACT on every compared burst' if ok else 'NOT byte-exact (or nothing compared)'}")
    return ok


def rows_levels(seed: int) -> np.ndarray:
    """(H, W, 3) levels, every frame row independent (seeded PRNG): odd rows differ from the even rows."""
    import ddr_levels as LV
    return LV.filler(H * W * 3, len(LV.load_table()[0]), seed).reshape(H, W, 3)


_STORED: list = []


def rows_line(lv: np.ndarray, row: int, mirror: bool) -> np.ndarray:
    """Stored bytes of frame row `row` as one memory line (pixel p = frame x 3839 - p when mirrored), B G R."""
    import ddr_levels as LV
    if not _STORED:
        _STORED.append(LV.load_table()[1])
    r = lv[row, ::-1, :] if mirror else lv[row]
    return _STORED[0][r].reshape(-1)


ROW_HYPS = [(nm, dr, mir) for nm, dr in (("row 2L", 0), ("row 2L+1", 1)) for mir in (True, False)]


def lane_perm(pairs: list[tuple[bytes, bytes]]) -> list[set]:
    """For each read byte i: the expected byte positions j that agree on every pair (got, expected natural)."""
    cand = [set(range(16)) for _ in range(16)]
    for got, exp in pairs:
        for i in range(16):
            cand[i] = {j for j in cand[i] if exp[j] == got[i]}
    return cand


def analyse_rows(reads: list[dict], seed: int) -> bool:
    """Exact equality per read against frame rows 2L / 2L+1 (mirror on / off), lane order swap 1 / 0; then the lane permutation that fits."""
    lv = rows_levels(seed)
    verdict = {}
    for port in ("a", "b"):
        rs = [r for r in reads if r["port"] == port]
        got = [(r, bytes.fromhex(r["hex"])) for r in rs if r["hex"]]
        tmo = len(rs) - len(got)
        log(f"port {port.upper()}: {len(rs)} line-start reads, {len(got)} with data, {tmo} read-flag timeouts (not compared)")
        tab = {}
        for nm, dr, mir in ROW_HYPS:
            for sw in (1, 0):
                n = 0
                for r, g in got:
                    e = rows_line(lv, 2 * (r["addr"] // PITCH_U) + dr, mir)[:16].tobytes()
                    n += g == (e[8:] + e[:8] if sw else e)
                tab[(nm, mir, sw)] = n
                log(f"  {nm:9s} mirror {int(mir)} halves-swap {sw}: exact {n} / {len(got)}")
        best = max(tab, key=tab.get)
        nm, mir, sw = best
        dr = 1 if nm == "row 2L+1" else 0
        pairs = [(g, rows_line(lv, 2 * (r["addr"] // PITCH_U) + dr, mir)[:16].tobytes()) for r, g in got]
        multiset = sum(sorted(g) == sorted(e) for g, e in pairs)
        perm = lane_perm(pairs)
        log(f"  best: {nm} mirror {int(mir)} swap {sw} = {tab[best]}/{len(got)}; same bytes in any order {multiset}/{len(got)}; "
            f"lane map read byte i <- memory byte j: " + " ".join(f"{i}<-{sorted(p)}" for i, p in enumerate(perm)))
        bad = [(r, g) for (r, g), (_, e) in zip(got, pairs, strict=True) if g != (e[8:] + e[:8] if sw else e)]
        for r, g in bad[:6]:
            log(f"  mismatch @unit {r['addr']} (line {r['addr'] // PITCH_U}): got {g.hex()}")
        verdict[port] = (nm, mir, sw, tab[best], len(got), tmo)
    a, b = verdict["a"], verdict["b"]
    ok = a[0] == "row 2L" and b[0] == "row 2L+1" and a[3] == a[4] > 0 and b[3] == b[4] > 0
    log(f"VERDICT chip A (port A) = frame row 2L: {a[3]}/{a[4]} exact (mirror {int(a[1])}, swap {a[2]}); "
        f"chip B (port B) = {b[0]}: {b[3]}/{b[4]} exact (mirror {int(b[1])}, swap {b[2]}) -> "
        f"{'chip B holds the odd rows' if ok else 'NOT confirmed'}")
    return ok


def run_rows(a) -> int:
    """Test 1 of #348: frame with independent odd rows (levels table), freeze, port A and port B read at the same line starts."""
    import ddr_frame_test as T
    import ddr_freeze_test as F
    import ddr_levels as LV
    T.LOG = LOG
    lv = rows_levels(a.seed)
    sent, _ = LV.load_table()
    write_frame_file(sent[lv])
    log(f"rows run: seed {a.seed:#x}, {W}x{H} frame, every row PRNG levels ({len(sent)} levels, table ddr_levels.json); "
        f"expected chip A line L = row 2L, chip B line L = row 2L+1 (mirrored, stored bytes)")
    lines = list(range(H // 2))
    random.Random(a.seed).shuffle(lines)
    d = T.Dbg(a.unit, a.bus)
    reads, marks, proc, t_on, snap = [], {}, None, None, {}
    try:
        F.frame_mode(d.io)
        snap = snapshot(d)
        rda, rdb = Reader(d, "a"), Reader(d, "b")
        e0a = rows_line(lv, 0, True)[:16].tobytes()
        e0b = rows_line(lv, 1, True)[:16].tobytes()
        t_on = time.monotonic()
        proc = pattern_start(F, a.connector)
        while time.monotonic() - t_on < MARK_WAIT_S and len(marks) < 2:     # lane-order agnostic: same 16 bytes in any order
            for nm, rd, e in (("a", rda, e0a), ("b", rdb, e0b)):
                if nm not in marks:
                    g = rd.read(0)
                    if g is not None and sorted(g) == sorted(e):
                        marks[nm] = round(time.monotonic() - t_on, 2)
        log(f"markers (unit 0, same bytes as row 0 / row 1, s after window start): {marks}")
        t = time.monotonic()
        while time.monotonic() - t < SETTLE_FRAMES * FRAME_S:
            F.prd(d.io, F.P5_AC)
        F.freeze(d.io, True)
        t_frz = time.monotonic() - t_on
        log(f"freeze on at {t_frz:.2f} s after window start")
        for ln in lines:
            if time.monotonic() - t_on > a.cap_s - 0.3:
                break
            for port, rd in (("a", rda), ("b", rdb)):
                g = rd.read(ln * PITCH_U)
                reads.append({"port": port, "addr": ln * PITCH_U, "hex": g.hex() if g else None, "t": round(time.monotonic() - t_on, 3)})
        log(f"reads: {len(reads)} bursts ({len(reads) // 2} lines x 2 ports) in {time.monotonic() - t_on - t_frz:.2f} s after the freeze")
    finally:
        if proc is not None:
            F.finish(d, proc, t_on)
        else:
            F.freeze(d.io, False)
            F.cmd(d.io, F.TC_SDK)
        d.io.close()
        READS.write_text(json.dumps({"mode": "rows", "seed": a.seed, "unit": a.unit, "markers": marks, "regs": snap, "reads": reads}))
        log(f"reads saved: {READS}")
    return 0 if analyse_rows(reads, a.seed) else 1


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
        if j.get("mode") == "rows":
            return 0 if analyse_rows(j["reads"], j["seed"]) else 1
        if j.get("mode") == "levels":
            import ddr_levels as LV
            pl = np.random.default_rng(j["seed"] ^ 0x5A5A).integers(0, 256, j["payload_kb"] * 1000, dtype=np.uint8).tobytes()
            nb = len(LV.to_levels(pl, len(LV.load_table()[0]))) // 16
            return 0 if analyse_levels(j["reads"], pl, j["seed"], nb, len(pl).to_bytes(8, "big") + pl) else 1
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
    ap.add_argument("what", choices=("run", "run-levels", "run-rows", "analyse", "gen"))
    ap.add_argument("reads", nargs="?")
    ap.add_argument("--unit", type=int, default=3)
    ap.add_argument("--bus", type=int)
    ap.add_argument("--connector", default="HDMI-2")
    ap.add_argument("--seed", type=lambda v: int(v, 0), default=SEED_DEFAULT)
    ap.add_argument("--recover", help="analyse: rebuild the reads from the raw I2C log lines at/after this ISO stamp, or freeze@STAMP = after the first freeze write at/after STAMP")
    ap.add_argument("--locate", action="store_true", help="analyse: also look each mismatching 8 B half up in the frame (aligned, 3 transforms)")
    ap.add_argument("--payload-kb", type=int, default=300, help="run-levels: payload size in KB (1000 B)")
    ap.add_argument("--cap-s", type=float, default=SCREEN_CAP_S)
    a = ap.parse_args()
    if a.what == "gen":
        write_frame_file(build_frame(a.seed))
        log(f"frame file written: {FRAME_FILE}")
        return 0
    if a.what == "run-levels":
        return run_levels(a)
    if a.what == "run-rows":
        return run_rows(a)
    return run(a) if a.what == "run" else offline(a)


if __name__ == "__main__":
    sys.exit(main())
