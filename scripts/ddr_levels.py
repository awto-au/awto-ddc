#!/usr/bin/env python3
"""Pack an arbitrary byte stream into video levels that survive the limited-range capture (awto-ddc#347), and unpack what DDR holds.

- Stored byte = LUT(sent byte) per channel (run 1, unit 3, Intel HDMI limited range). ddr_levels.json lists the stored values (16..234, 217 seen)
  and ONE sent value for each; payload digits are levels 0..N-1 = those stored values in ascending order.
- Two sent values with the same stored value: the lower sent value is used (either maps there; both observed). A sent value that stored two
  different bytes: none occurred (0 of 254 seen); build() refuses such a table.
- Packing: 8 B big-endian length + data, zero padded to 31 B chunks; chunk = 248-bit integer = 32 base-N digits (N^32 >= 2^248 needs N >= 216).
- Layout: memory linear order (line L of block 1, pixel p, B G R), 12 441 600 levels; memory (L, p, c) = frame row 2L, x 3839 - p, channel c;
  odd frame rows copy the row above; levels past the data are PRNG filler (seeded).
usage: ddr_levels.py build [READS.json]     rebuild ddr_levels.json from a ddr_capture_check reads file (needs the same seed frame)
Log: ./tmp/logs/ddr_levels.log
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _log import log_line as _log_line
from _repo import ROOT

LOG = ROOT / "tmp/logs/ddr_levels.log"
TABLE = Path(__file__).resolve().parent / "ddr_levels.json"
W, H = 3840, 2160
LINES = H // 2
LINE_B = W * 3                    # 11520 bytes per memory line
CAP_LEVELS = LINES * LINE_B       # 12 441 600
CHUNK_B = 31                      # 248 bits
HDR_B = 8


def load_table() -> tuple[np.ndarray, np.ndarray]:
    """(sent[N], stored[N]) ascending in stored."""
    t = json.loads(TABLE.read_text())
    return np.array(t["sent"], np.uint8), np.array(t["stored"], np.uint8)


def digits_per_chunk(n: int) -> int:
    d = 1
    while n ** d < 1 << (8 * CHUNK_B):
        d += 1
    return d


def capacity_bytes(n: int) -> int:
    return CAP_LEVELS // digits_per_chunk(n) * CHUNK_B - HDR_B


def to_levels(data: bytes, n: int) -> np.ndarray:
    d = digits_per_chunk(n)
    buf = len(data).to_bytes(HDR_B, "big") + data
    buf += bytes(-len(buf) % CHUNK_B)
    out = np.empty(len(buf) // CHUNK_B * d, np.uint8 if n <= 256 else np.uint16)
    for k in range(len(buf) // CHUNK_B):
        v = int.from_bytes(buf[k * CHUNK_B:(k + 1) * CHUNK_B], "big")
        for j in range(d - 1, -1, -1):
            v, out[k * d + j] = divmod(v, n)
    return out


def from_levels(levels: np.ndarray, n: int, whole: bool = True) -> bytes:
    """Inverse of to_levels. whole: the stream starts with the length header and the result is the data; else the raw chunk bytes (no header handling)."""
    d = digits_per_chunk(n)
    if len(levels) % d:
        raise ValueError("level count is not a multiple of the chunk digits")
    out = bytearray()
    for k in range(len(levels) // d):
        v = 0
        for x in levels[k * d:(k + 1) * d]:
            if int(x) >= n:
                raise ValueError(f"level {int(x)} >= {n}")
            v = v * n + int(x)
        if v >> (8 * CHUNK_B):
            raise ValueError("chunk value does not fit 248 bits")
        out += v.to_bytes(CHUNK_B, "big")
    if not whole:
        return bytes(out)
    ln = int.from_bytes(out[:HDR_B], "big")
    if ln > len(out) - HDR_B:
        raise ValueError("length header exceeds the stream")
    return bytes(out[HDR_B:HDR_B + ln])


def filler(count: int, n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).integers(0, n, count, dtype=np.uint16).astype(np.uint8)


def memory_levels(data: bytes, seed: int) -> np.ndarray:
    """All CAP_LEVELS levels of block 1 in memory order: data levels then filler."""
    sent, _ = load_table()
    lv = to_levels(data, len(sent))
    if len(lv) > CAP_LEVELS:
        raise ValueError(f"{len(data)} B needs {len(lv)} levels, capacity {CAP_LEVELS}")
    return np.concatenate([lv, filler(CAP_LEVELS - len(lv), len(sent), seed)])


def stored_memory(levels: np.ndarray) -> np.ndarray:
    return load_table()[1][levels]


def frame_from_levels(levels: np.ndarray) -> np.ndarray:
    """(H, W, 3) sent bytes, B G R: memory (L, p, c) -> row 2L, x 3839 - p; odd rows copy the row above."""
    sent, _ = load_table()
    m = sent[levels].reshape(LINES, W, 3)
    f = np.empty((H, W, 3), np.uint8)
    f[0::2] = m[:, ::-1, :]
    f[1::2] = f[0::2]
    return f


def levels_from_stored(stored: np.ndarray) -> np.ndarray:
    """Stored bytes -> levels; 255 where the byte is not a table value."""
    _, st = load_table()
    inv = np.full(256, 255, np.uint8)
    inv[st] = np.arange(len(st), dtype=np.uint8)
    return inv[stored]


def build(reads_file: Path) -> None:
    import ddr_capture_check as C
    j = json.loads(reads_file.read_text())
    f = C.build_frame(j["seed"])
    seen: dict[int, set] = {}
    for r in j["reads"]:
        if not r["hex"] or r["addr"] // C.PITCH_U >= LINES:
            continue
        b = bytes.fromhex(r["hex"])
        b = b[8:] + b[:8]
        for i, v in enumerate(b):
            p, c = divmod(8 * r["addr"] % LINE_B + i, 3)
            seen.setdefault(int(f[2 * (r["addr"] // C.PITCH_U), W - 1 - p, c]), set()).add(v)
    bad = {e: s for e, s in seen.items() if len(s) > 1}
    if bad:
        raise SystemExit(f"sent values with two stored bytes: {bad}; table refused")
    pick: dict[int, int] = {}
    for e in sorted(seen):
        pick.setdefault(next(iter(seen[e])), e)           # lowest sent value per stored value
    stored = sorted(pick)
    TABLE.write_text(json.dumps({"note": "awto-ddc#347 run 1 unit 3 (Intel limited range): stored byte for each sent byte, one sent value per stored value",
                                 "sent_values_seen": len(seen), "stored": stored, "sent": [pick[s] for s in stored]}) + "\n")
    _log_line(f"table: {len(seen)} sent values seen, {len(stored)} levels, stored {stored[0]}..{stored[-1]}, missing in range "
              f"{[s for s in range(stored[0], stored[-1] + 1) if s not in pick]}", LOG)


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        build(Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "tmp/logs/ddr_capture_check.reads.json")
