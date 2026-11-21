"""DRAM log host side (scripts/dram_log.py, sync_log.read_ring version 4, unit_log.Store.ingest_dram): DDR entry / header format, newest-entry scan,
virtual ring for the version 3 decoders, saver dedupe by absolute index."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import dram_log as D
import sync_log as S
import unit_log as U

SLOTS, U0, HDR_U, EU = D.C["AWTO_DLOG_SLOTS"], D.C["AWTO_DLOG_UNITS0"], D.C["AWTO_DLOG_HDR_UNITS"], D.C["AWTO_DLOG_ENTRY_UNITS"]
GEN = 3


def burst(id_: int, arg: int, ms: int, val: int, a: int, boot: int, gen: int = GEN) -> bytes:
    b = bytes([id_, arg]) + ms.to_bytes(4, "big") + val.to_bytes(4, "big") + (a & 0xFFFFFF).to_bytes(3, "big") + bytes([gen, boot])
    return b + bytes([D._sum(b + b"\0")])


def header(hint: int, boot: int = 2, gen: int = GEN) -> bytes:
    b = b"DL" + bytes([1, gen, boot]) + hint.to_bytes(4, "big") + bytes(6)
    return b + bytes([D._sum(b + b"\0")])


class Ddr:
    def __init__(self):
        self.mem: dict[int, bytes] = {}

    def put(self, a: int, **kw) -> None:
        self.mem[U0 + (a % SLOTS) * EU] = burst(a=a, **kw)

    def __call__(self, u: int) -> bytes | None:
        return self.mem.get(u)


def fill(d: Ddr, n: int, boot: int = 2) -> None:
    for a in range(n):
        d.put(a, id_=0x01, arg=a & 0xFF, ms=1000 + a, val=a, boot=boot)


def test_header_and_entry_validate():
    d = Ddr()
    d.mem[HDR_U] = header(64)
    d.put(5, id_=0xE6, arg=1, ms=0x12345678, val=0xDEADBEEF, boot=2)
    assert D.header(d) == {"gen": GEN, "boot": 2, "hint": 64}
    e = D.entry(d, 5, GEN)
    assert (e["id"], e["arg"], e["ms"], e["val"], e["boot"]) == (0xE6, 1, 0x12345678, 0xDEADBEEF, 2)
    assert D.entry(d, 5, GEN + 1) is None                      # another generation (a cold power-up bumped it)
    assert D.entry(d, 6, GEN) is None                          # an empty slot
    d.mem[U0 + 5 * EU] = bytes([d.mem[U0 + 5 * EU][0] ^ 1]) + d.mem[U0 + 5 * EU][1:]
    assert D.entry(d, 5, GEN) is None                          # check byte
    d.mem[HDR_U] = header(64)[:15] + b"\0"
    assert D.header(d) is None


def test_slot_of_another_lap_is_not_the_entry():
    d = Ddr()
    d.put(SLOTS + 7, id_=1, arg=0, ms=0, val=0, boot=1)        # index SLOTS + 7 sits in slot 7
    assert D.entry(d, 7, GEN) is None
    assert D.entry(d, SLOTS + 7, GEN)["abs"] == SLOTS + 7


def test_newest_scans_forward_from_the_hint():
    d = Ddr()
    d.mem[HDR_U] = header(64)
    fill(d, 100)
    assert D.newest(d, D.header(d)) == 100
    fill(d, 64 + 2 * D.C["AWTO_DLOG_HINT_EVERY"] + 50)          # a hint further behind than the scan reach: stops at the reach, never past the end
    assert D.newest(d, D.header(d)) == 64 + 2 * D.C["AWTO_DLOG_HINT_EVERY"] + 2


def test_entries_newest_k_after_a_wrap():
    d = Ddr()
    d.mem[HDR_U] = header(SLOTS + 128)
    n = SLOTS + 200
    for a in range(n - 300, n):                                 # the ring has lapped: older slots hold the newer lap
        d.put(a, id_=1, arg=a & 0xFF, ms=a, val=a, boot=2)
    h = D.header(d)
    assert D.newest(d, h) == n
    got = D.entries(d, h, n, 50)
    assert [e["abs"] for e in got] == list(range(n - 50, n))


def test_decode_prints_ms_since_boot_and_episode_time():
    rows = S.load_rows(ROOT / "fw/awto/sync.tsv")
    ents = [{"abs": 0, "id": 0xC0, "arg": 1, "ms": 5, "val": 0, "boot": 1},
            {"abs": 1, "id": 0xC0, "arg": 2, "ms": 70000, "val": 5, "boot": 1}]
    out = D.decode(rows, ents)
    assert out[0].startswith("    0.005s:") and "power on" in out[0]
    assert out[1].startswith("   70.000s:")                      # 32 bit stamp: no 16 bit wrap at 65.5 s


def xdata_v4(seq: int, ep: int, head: int, pend: int, wr: int, tail: dict[int, bytes], old: int = 0) -> bytes:
    h = bytearray(S.V4_HDR)
    h[0:3] = b"SY\x04"
    h[3], h[4], h[12], h[13] = seq, ep, 88, 176
    h[14:19] = bytes([GEN, 2, pend, 0, head])
    h[19:23] = wr.to_bytes(4, "big")
    h[23] = old
    t = bytearray(S.V4_TAIL * S.V4_TL)
    for slot, e in tail.items():
        t[slot * S.V4_TL:slot * S.V4_TL + 8] = e
    return bytes(h + t)


def test_read_ring_v4_is_a_version3_ring_with_the_older_lines_from_the_ddr():
    d = Ddr()
    fill(d, 40)                                                 # 40 lines written; the newest 32 also in the tail (flushed), 0 pending
    tail = {a % S.V4_TAIL: bytes([1, a & 0xFF, 0, 1, 0, 0, 0, a]) for a in range(8, 40)}
    img = xdata_v4(seq=40, ep=10, head=40, pend=0, wr=40, tail=tail)
    S.DDR_UNIT = d
    try:
        raw = S.read_ring(lambda a, n: img[:n], 0)
    finally:
        S.DDR_UNIT = None
    h, _ = S.decode(raw, S.load_rows(ROOT / "fw/awto/sync.tsv"), whole=True)
    assert h["seq"] == 40 and len(h["events"]) == 40
    assert [e[1] for e in h["events"]] == list(range(40))     # older than the tail: DDR; in the tail: XDATA; oldest first
    assert S.read_ring.dram_missing == 0


def test_read_ring_v4_without_a_ddr_reader_leaves_older_lines_unwritten():
    tail = {a % S.V4_TAIL: bytes([1, a & 0xFF, 0, 1, 0, 0, 0, a]) for a in range(8, 40)}
    img = xdata_v4(seq=40, ep=10, head=40, pend=0, wr=40, tail=tail)
    S.DDR_UNIT = None
    raw = S.read_ring(lambda a, n: img[:n], 0)
    h, _ = S.decode(raw, S.load_rows(ROOT / "fw/awto/sync.tsv"), whole=True)
    assert [e[1] for e in h["events"]] == list(range(8, 40))   # the 32 tail lines; the 8 older ones are zero entries (skipped)
    assert S.read_ring.dram_missing == 8


def test_saver_appends_by_absolute_index(tmp_path):
    s = U.Store("T1", tmp_path)

    def snap(lo: int, hi: int, boot: int = 2) -> dict:
        return {"dram": True, "serial": "T1", "read": "2026-11-22T10:00:00.000+10:00",
                "entries": [{"abs": a, "boot": boot, "ms": a, "id": 1, "val": a, "text": f"{a / 1000:9.3f}s:line {a}", "poll_wall": None} for a in range(lo, hi)]}

    assert len(s.ingest(snap(0, 10))) == 10
    assert s.ingest(snap(5, 10)) == []                          # re-read: nothing new
    out = s.ingest(snap(10, 13))
    assert [x.split()[2] for x in out] == ["10", "11", "12"]
    out = s.ingest(snap(20, 22))
    assert out[0].startswith("# ") and "gap: 7 entries" in out[0]
