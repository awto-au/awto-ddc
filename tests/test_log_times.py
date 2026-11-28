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


def _v4_image(entries, gen=7, boot=1):
    """a DRAM log image (sync_log V4 header + 32-entry tail) and a DDR reader for entries [(id, arg, ms32, val)], oldest first"""
    n_all = len(entries)
    hdr = bytearray(SL.V4_HDR)
    seq = n_all % 176
    hdr[0:2], hdr[2], hdr[3], hdr[4], hdr[12], hdr[13], hdr[14], hdr[16], hdr[18] = b"SY", 4, seq, 0, 88, 176, gen, 0, n_all & 0xFF
    hdr[19:23] = n_all.to_bytes(4, "big")
    tail = bytearray(SL.V4_TAIL * SL.V4_TL)
    for a in range(max(0, n_all - SL.V4_TAIL), n_all):
        i, g, m, v = entries[a]
        o = SL.V4_TL * (a & (SL.V4_TAIL - 1))
        tail[o:o + SL.V4_TL] = bytes([i, g, (m >> 8) & 0xFF, m & 0xFF]) + v.to_bytes(4, "big") + ((m >> 16) & 0xFFFF).to_bytes(2, "big")
    ddr = {}
    for a, (i, g, m, v) in enumerate(entries):
        e = bytes([i, g]) + (m & 0xFFFFFFFF).to_bytes(4, "big") + v.to_bytes(4, "big") + a.to_bytes(3, "big") + bytes([gen, boot])
        ddr[D.C["AWTO_DLOG_UNITS0"] + (a % D.C["AWTO_DLOG_SLOTS"]) * D.C["AWTO_DLOG_ENTRY_UNITS"]] = e + bytes([D._sum(e + b"\0")])
    img = bytes(hdr) + bytes(tail)
    return img, (lambda u: ddr.get(u))


def test_boot_over_88_lines_uptime_over_1000s_wall_clock(monkeypatch):
    """#358 item 2: a boot of 130 lines (> the 88-line window), gaps > 65 s, host sync at fw 1155255 ms: every line at its true host time"""
    rows = SL.load_rows(Path(__file__).resolve().parent.parent / "fw/awto/sync.tsv")
    ents = [(0xD0, 1, 0xFFFFFFFC, 0), (0xD2, 2, 0, 31), (0xC0, 1, 1, 0xFF)]
    t = 10
    for k in range(126):
        t += 9000 if k % 10 else 70_000                       # every tenth gap over the 16-bit wrap
        ents.append((0xE7, 3, t, 0))
    ents.append((0xD8, 1, 1155255, 1155255))
    img, rd = _v4_image(ents)
    monkeypatch.setattr(SL, "DDR_UNIT", rd)
    raw = SL.read_ring(lambda a, k: img[a:a + k], 0, False)
    h, lines = SL.decode(bytes(raw), rows, False, None, raw.ms32)
    assert len(lines) == len(ents) and h["lost"] == 0 and lines[0].split(":", 1)[1].startswith("boot:")
    out = [ln for ln, _ in SL.ring_rows(h, lines, HT, 0, join=False)]
    assert out[0].startswith(" " + dt_wall(-4)) and dt_wall(-4).startswith("14:58:59") and "-- boot:" in out[0]   # 1155 s before the sync
    want = dt_wall(ents[-2][2])
    assert out[-2].startswith(" " + want)
    assert not any(SL.WRAP_TEXT in x for x in out) and sum("+70.0 s" in x for x in out) == 13
    assert "+ 27 ms:-- boot:" in out[0]                                     # boot row zero = the MCU reset: -4 + 31 ms
    assert SL.con_rows(h["events"], [x.split(":", 1)[1] for x in lines], SL.unwrap(h["events"], None, h["ms32"]))[0]["delta"] == 27   # since reset: -4 + 31


def dt_wall(fw: int) -> str:
    import datetime as dt
    t = HT["epoch"] + (HT["frac"] + fw - HT["fw"]) / 1000
    return dt.datetime.fromtimestamp(t, dt.timezone(dt.timedelta(minutes=15 * HT["ofs"]))).strftime("%H:%M:%S.%f")[:12]


ROWS = SL.load_rows(Path(__file__).resolve().parent.parent / "fw/awto/sync.tsv")


def _rows_of(ents, ht=None, base=None, join=True):
    """[(id, arg, ms32, val)] -> console rows as text, every line 32-bit (DRAM log)"""
    evs = [(i, a, m & 0xFFFF, v) for i, a, m, v in ents]
    ms = [m for _, _, m, _ in ents]
    texts = [SL.line(ROWS, e, 0).split(":", 1)[1] for e in evs]
    ts = SL.unwrap(evs, None, ms)
    return SL.row_lines(SL.con_rows(evs, texts, ts, ht, join=join, boot_base=base), ts, evs)


def test_gap_just_under_a_wrap_is_positive_not_negative():
    """#358 item 2: a gap within 256 ms of 65.536 s read negative from 16 bits; hand values: 65436 ms and 65536 + 30 ms"""
    out = _rows_of([(0xE7, 3, 1000, 0), (0xE7, 3, 1000 + 65436, 0), (0xE7, 3, 1000 + 65436 + 65566, 0)], join=False)
    assert "+65.4 s:" in out[1] and "+65.5 s:" in out[2] and not any(" -" in x.split(":", 3)[2][:9] for x in out[1:])


def test_start_rows_say_started_one_per_start():
    """the boot line and a real BEGIN are red '-- ... started --' rows; a BEGIN flagged AWTO_SYNC_BEGIN_IN (inside an unsettled start) is not"""
    ents = [(0xD0, 1, 0xFFFFFFFC, 0), (0xD2, 2, 0, 31), (0xC0, 1, 5, 0xFF),
            (0xC0, 5, 400, (1 << 24) | 5),             # picture lost inside the unsettled power-on: a line, no red row
            (0xC0, 3, 9000, 5),                        # wake on D2: a start
            (0xC0, 3, 9020, (1 << 24) | 5),            # the hold's fast wake inside it: a line
            (0xC0, 2, 20000, 6)]                       # switch to D3: a start
    out = _rows_of(ents)
    st = [x for x in out if " started --" in x]
    assert len(st) == 3 and st[0].split(":", 3)[3].startswith("-- boot:") and "wake on" in st[1] and "switch to" in st[2]
    assert "+  0 ms:-- wake on" in st[1] and "+  0 ms:-- switch to" in st[2]
    assert "+ 27 ms:-- boot:" in st[0]                                          # since the MCU reset: -4 + 31 (Timer2 start line)


def test_boot_row_zero_from_the_firmware_base_when_the_timer2_line_is_gone():
    """the 88-line window lost the Timer2 start line: the boot row still counts from the MCU reset (g_usAwtoBootBase = 122)"""
    out = _rows_of([(0xD0, 1, 0xFFFFFFFC, 0), (0xE7, 3, 5000, 0)], base=122)
    assert "+118 ms:-- boot:" in out[0] and out[0].startswith("u00:00:00.118") and out[1].startswith("u00:00:05.122")


def test_16bit_ring_gap_over_the_wrap_is_a_wrap_row():
    """version 3 ring (no 32-bit ms): two lines 70 s apart with no anchor between -> a red wrap row, no number; anchors around -> sure"""
    evs = [(0xD8, 1, 1000, 1000), (0xE7, 3, (1000 + 70_000) & 0xFFFF, 0)]
    ts = SL.unwrap(evs, None)
    out = SL.row_lines(SL.con_rows(evs, ["a", "b"], ts), ts, evs)
    assert sum(SL.WRAP_TEXT in x for x in out) == 1 and "+ 4.4 s" not in out[-1]
    evs.append((0xD8, 2, (1000 + 70_000 + 10) & 0xFFFF, 1000 + 70_000 + 10))   # the next full time: 70 s did wrap, still not sure
    ts = SL.unwrap(evs, None)
    assert ts[1][1] is False


def test_dram_previous_boot_row_from_its_own_reset():
    """dram_log history: a previous boot's boot row counts from its own MCU reset (its D2 02 line: 40 ms), not negative"""
    ents = [{"abs": 0, "boot": 6, "id": 0xD0, "arg": 3, "ms": 0xFFFFFFFB, "val": 0}, {"abs": 1, "boot": 6, "id": 0xD2, "arg": 2, "ms": 0, "val": 40},
            {"abs": 2, "boot": 7, "id": 0xD0, "arg": 1, "ms": 0xFFFFFFFC, "val": 0}]
    out = D.con_lines(ROWS, ents, 7, None)
    assert "+ 35 ms:-- boot:warm reset" in out[1] and out[1].split()[1].startswith("u00:00:00.035")
    assert "+118 ms:-- boot:cold" in D.con_lines(ROWS, ents, 7, None, 122)[-1]     # this boot: g_usAwtoBootBase read with the history


def test_dram_page_and_progress_and_poll_wall_sign():
    """GUI requests (#358): --since A --count K is one page; progress every PROGRESS_N; a line before Timer2 (ms < 0) has its poll time
    a few ms before the boot, not 49 days off"""
    import datetime as dt
    ents = [(0xD0, 1, 0xFFFFFFFC, 0)] + [(0xE7, 3, 10 * k, 0) for k in range(1, 250)]
    _img, rd = _v4_image(ents)
    hdr = {"gen": 7}
    seen = []
    page = D.entries(rd, hdr, len(ents), 120, 100, lambda k, n: seen.append((k, n)))
    assert [e["abs"] for e in page] == list(range(100, 220)) and seen == [(100, 120)]
    t = dt.datetime(2026, 11, 27, 17, 0, tzinfo=dt.UTC)
    monkey = D.header
    try:
        D.header = lambda read, diag=None: {"gen": 7, "boot": 1, "hint": 0}
        snap = D.snapshot(rd, ROWS, None, None, "S", 5000, t, 0, len(ents), 2)
    finally:
        D.header = monkey
    assert snap["entries"][0]["poll_wall"] == (t - dt.timedelta(milliseconds=5004)).isoformat(timespec="milliseconds")
