"""awto-ddc#273 host note: truncation, slot bytes, decoder lines (matching / overwritten / not read), generator cap."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gen_awto_sync as G
import host_note as HN
import sync_log as SL

D = SL.note_defs()


def slot(seq: int, text: bytes) -> bytes:
    s = bytearray(D["SIZE"])
    for off, v in HN.slot_bytes(seq, text, D):
        s[off] = v
    return bytes(s)


def test_prepare_keeps_short_ascii():
    assert HN.prepare("ddr fill 3", D["CHARS"]) == (b"ddr fill 3", False)


def test_prepare_cuts_with_marker():
    b, cut = HN.prepare("x" * (D["CHARS"] + 1), D["CHARS"])
    assert cut and len(b) == D["CHARS"] and b.endswith(b">") and b[:-1] == b"x" * (D["CHARS"] - 1)
    assert HN.prepare("x" * D["CHARS"], D["CHARS"])[1] is False


def test_prepare_replaces_non_ascii_and_controls():
    assert HN.prepare("a\tbé", D["CHARS"])[0] == b"a?b??"


def test_slot_bytes_layout():
    w = HN.slot_bytes(0x0102, b"hi", D)
    assert w == [(D["TAG"], 1), (D["TAG"] + 1, 2), (D["LEN"], 2), (D["TXT"], ord("h")), (D["TXT"] + 1, ord("i"))]


def test_note_text_matching_overwritten_unread():
    s = slot(7, b"step 2")
    assert SL.note_text(s, 6, 7, D) == "step 2"
    assert SL.note_text(s, 6, 6, D) == "text overwritten"
    assert SL.note_text(s, 6, 7 + 65536, D) == "step 2"          # value is a DWORD, the tag a WORD
    assert SL.note_text(None, 6, 7, D) == "text not read (6 chars)"


def test_decode_prints_the_note_line():
    rows = SL.load_rows(Path(__file__).resolve().parents[1] / "fw/awto/sync.tsv")
    ring = bytearray(b"SY\x03" + bytes([2, 0, 1, 0, 0, 0, 0, 0, 0, 48, 240]))      # seq 2 of an N=48 ring
    ring = bytearray(ring.ljust(SL.HDR + 48 * SL.EV, b"\0"))
    for k, seq in enumerate((1, 2)):
        e = SL.HDR + k * SL.EV
        ring[e:e + 8] = bytes([SL.NOTE_EV, 4, 0, 10 * (k + 1)]) + seq.to_bytes(4, "big")
    note = slot(2, b"same")
    _h, lines = SL.decode(bytes(ring), rows, whole=True, note=note)
    assert lines[0].endswith("text overwritten") and lines[1].endswith(":same")
    assert SL.decode(bytes(ring), rows, whole=True)[1][1].endswith("text not read (4 chars)")


def test_note_fits_one_console_row():
    h = G.HEADER
    assert G.c_int("AWTO_NOTE_CHARS", h) + G.c_int("AWTO_LOG_TXT0", G.DBGPOP) <= G.c_int("AWTO_LOG_W_MAIN", G.DBGPOP)


def test_generator_counts_the_note_text_at_its_cap(tmp_path):
    r = G.rows()
    x = next(x for x in r if x["id"] == 0xEE)
    n, _word = G.seg_len(G.segments(x, r, ["D1"]))
    assert n >= G.c_int("AWTO_NOTE_CHARS", G.HEADER)               # the width check sees the full slot
    assert G.line_check(r) == 0


def test_note_cap_beyond_the_row_fails_the_generator(monkeypatch):
    r = G.rows()
    real = G.c_int
    monkeypatch.setattr(G, "c_int", lambda name, path: real(name, path) + (300 if name == "AWTO_NOTE_CHARS" else 0))
    assert G.line_check(r) >= 1
