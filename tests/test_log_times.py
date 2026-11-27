"""Host log times across gaps longer than the 16-bit ring ms (65.536 s): sync_log.unwrap / con_rows / row_lines, dram_log.con_lines.

Data: unit 3 (826fcb36) monitor uptime rows 2026-11-27, uptime 10 / 295 / 580 / 860 / 1150 s at ring ms 10117 / 32982 / 56383 / 8718 / 36572;
the 16-bit delta read 22.9 s (or negative) for gaps of ~285 s, and the wall clock was mapped into the last 65 s window (awto-ddc#354).
"""
import itertools
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dram_log as D
import sync_log as SL

UP_S = [10, 295, 580, 860, 1150]
MS16 = [10117, 32982, 56383, 8718, 36572]
# host sync: fw 1155255 ms = 2026-11-27T15:18:14.833+11:00 (unit 3, ht read 15:20:33)
HT = {"syncs": 2, "ofs": 44, "frac": 833, "epoch": 1795753094, "fw": 1155255, "drift": -2, "up_hi": 0}


def full_ms() -> list[int]:
    """the 32-bit fw ms of each row: the value with that low word nearest uptime x 1000"""
    return [round((u * 1000 - m) / 65536) * 65536 + m for u, m in zip(UP_S, MS16)]


def evs_of(ms: list[int]) -> list[tuple]:
    return [(0xEA, 4, m & 0xFFFF, u << 8 | 0xD4) for u, m in zip(UP_S, ms)]


def texts(evs):
    return [f"monitor: {SL.mon_text(e[1], e[3])}" for e in evs]


def test_32bit_entries_give_true_deltas_and_wall_clock():
    ms = full_ms()
    evs = evs_of(ms)
    ts = SL.unwrap(evs, None, ms)
    rs = SL.con_rows(evs, texts(evs), ts, HT)
    assert [r["delta"] for r in rs[1:]] == [b - a for a, b in itertools.pairwise(ms)]
    assert all(r["delta"] > 65536 for r in rs[1:]) and not any(r["wrap"] for r in rs)
    assert [SL.fmt_delta(r["delta"]) for r in rs[1:]] == ["+ 285 s", "+ 285 s", "+ 280 s", "+ 289 s"]
    # boot ~14:59:04 local: the 10 s row is at 14:59:14, not in the last 65 s window before the sync (15:17..15:18)
    assert rs[0]["real"].startswith(" 14:59:")
    assert rs[-1]["real"] == SL.real_col(ms[-1], HT, True) and rs[-1]["real"].startswith(" 15:18:")
    line = SL.row_lines(rs, ts, evs)[1]
    assert f"[fw {ms[1]} ms, ring {MS16[1]}]" in line and "+ 285 s:monitor: up 295s stk D4" in line


def test_16bit_only_gap_is_a_wrap_row_not_a_number():
    evs = evs_of(full_ms())
    ts = SL.unwrap(evs, None)                    # no anchor, no 32-bit time: nothing is known for certain
    rs = SL.con_rows(evs, texts(evs), ts, HT)
    assert all(r["wrap"] and r["delta"] is None for r in rs[1:])
    out = SL.row_lines(rs, ts, evs)
    assert sum(SL.WRAP_TEXT in x for x in out) == 4 and not any("+22." in x or "+23." in x for x in out)
    assert all(r["real"].strip() == "" for r in rs)  # no guessed real time either


def test_16bit_chain_between_anchors_is_sure():
    """a version 3 ring: lines between two full times are sure when the 16-bit steps land exactly on the second one"""
    evs = [(0xD8, 1, 1000, 1000), (0x93, 0, 1500, 0), (0x93, 0, 2000, 0), (0xD8, 2, 2500, 2500)]
    ts = SL.unwrap(evs, None)
    assert ts == [(1000, True), (1500, True), (2000, True), (2500, True)]
    evs[3] = (0xD8, 2, 2500, 2500 + 65536)      # a hidden wrap between the anchors
    assert [s for _, s in SL.unwrap(evs, None)] == [True, False, False, True]


def test_dram_lines_previous_boot_uptime_current_boot_host_clock():
    rows = SL.load_rows(Path(__file__).resolve().parent.parent / "fw/awto/sync.tsv")
    ms = full_ms()
    ents = [{"abs": k, "boot": 7, "id": 0xEA, "arg": 4, "ms": m, "val": u << 8 | 0xD4} for k, (u, m) in enumerate(zip(UP_S, ms))]
    ents.insert(0, {"abs": 99, "boot": 6, "id": 0xEA, "arg": 4, "ms": 5000, "val": 5 << 8 | 0xD4})
    out = D.con_lines(rows, ents, 7, HT)
    assert out[0] == "--- boot 6" and "u00:00:05.000" in out[1] and out[2] == "--- boot 7"
    assert " 14:59:" in out[3] and "+ 285 s:" in out[4]


def test_ring_v4_keeps_32bit_ms():
    """_ring_v4 tail entries: bytes 8..9 = ms bits 31..16 reach decode() (h["ms32"])"""
    rows = SL.load_rows(Path(__file__).resolve().parent.parent / "fw/awto/sync.tsv")
    ms = full_ms()
    n, wrap = 8, 128
    hdr = bytearray(SL.V4_HDR)
    hdr[0:2], hdr[2], hdr[3], hdr[4], hdr[12], hdr[13], hdr[16], hdr[18] = b"SY", 4, len(ms), 0, n, wrap, 0, len(ms)
    hdr[19:23] = len(ms).to_bytes(4, "big")
    tail = bytearray(SL.V4_TAIL * SL.V4_TL)
    for k, (e, m) in enumerate(zip(evs_of(ms), ms)):
        tail[k * SL.V4_TL:(k + 1) * SL.V4_TL] = bytes([e[0], e[1], (m >> 8) & 0xFF, m & 0xFF]) + e[3].to_bytes(4, "big") + (m >> 16).to_bytes(2, "big")
    img = bytes(hdr) + bytes(tail)
    raw = SL.read_ring(lambda a, k: img[a:a + k], 0, True)
    h, lines = SL.decode(raw, rows, whole=True)
    assert h["ms32"] == ms
    assert SL.decode(bytes(raw), rows, whole=True, ms32=raw.ms32)[0]["ms32"] == ms     # main() passes it over the bytes() copy
    out = [ln for ln, _ in SL.ring_rows(h, lines, HT, 0)]
    assert sum("+ 285 s" in x for x in out) == 2 and not any(SL.WRAP_TEXT in x for x in out)
