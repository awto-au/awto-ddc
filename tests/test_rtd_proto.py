"""Offline tests for scripts/rtd_proto.py (decoder) and scripts/rtd_log.py. No hardware, no bus.

tests/data/*.log are our own protocol traffic: dbg_write/diag_block/dbg_*.old = excerpts of tmp/logs from real runs
(2026-11-05/06); isp_sector.raw.log = recorded from the real flash routines against the simulated chip
(tests/test_flash_burst.py BusRtd), not from hardware. *.decoded = reviewed expected output.
Run: pytest tests/test_rtd_proto.py -q
"""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(__file__).parent / "data"
sys.path.insert(0, str(ROOT / "scripts"))
import rtd_log as L  # noqa: E402
import rtd_proto as P  # noqa: E402


def decode_file(name: str) -> str:
    out = io.StringIO()
    L.decode_lines((DATA / name).open(), out, DATA / "mini.map", merge_pages=True, root=ROOT)
    return out.getvalue()


@pytest.mark.parametrize("raw", ["dbg_write.raw", "diag_block.raw", "dbg_messages.old", "bridge_blocked.old",
                                 "dbg_read.old", "isp_sector.raw"])
def test_golden(raw):
    assert decode_file(raw + ".log") == (DATA / (raw + ".decoded")).read_text()


def run(txns, **kw) -> list[str]:
    out = []
    d = P.Decoder(lambda ts, tag, text: out.append(f"{tag} {text}"), P.Symbols.load(ROOT, DATA / "mini.map"), **kw)
    for t in txns:
        d.feed(P.Txn("t", *t) if not isinstance(t, P.Txn) else t)
    d.flush()
    return out


def w(dev, sub, *data):
    return (dev, "w", sub, bytes(data))


def r(dev, sub, *data):
    return (dev, "r", sub, bytes(data), len(data))


def test_diag_block_is_one_line():
    lines = decode_file("diag_block.raw.log").splitlines()
    assert len(lines) == 1 and "read XDATA 0xF6D0..0xF6FF (48 B)  g_stAwtoDiag" in lines[0]


def test_test_cmd_write_named():
    (line,) = decode_file("dbg_write.raw.log").splitlines()
    assert "write XDATA 0xF6F8 <- 0x1A = test cmd: raise event info" in line


def test_osd_info_fields_and_values():
    base = 0xEA89
    out = run([w(0x35, 1, base >> 8), w(0x35, 3, 10), w(0x35, 0x3B, (base + 5) & 0xFF),
               w(0x35, 3, 1), w(0x35, 0x3B, (base + 6) & 0xFF)])
    assert out == ["dbg write XDATA 0xEA8E..0xEA8F (2 B)  g_stOsdInfo.ucOsdEventMsg..g_stOsdInfo.ucOsdKeyMessage <- 0a 01"]
    out = run([w(0x35, 1, base >> 8), w(0x35, 3, 10), w(0x35, 0x3B, (base + 5) & 0xFF)])
    assert out == ["dbg write XDATA 0xEA8E <- 0x0A = event info  g_stOsdInfo.ucOsdEventMsg"]


def test_struct_fields_from_header():
    s = P.Symbols.load(ROOT, DATA / "mini.map")
    assert s.name(0xF6D3) == "g_stAwtoDiag.ucStage"
    assert s.name(0xF6D4 + 1) == "g_stAwtoDiag.usStageMs[0]+1"
    assert s.range_name(0xF6B0, 0xF6CF) == "g_stAwtoSafe"


def test_page_select_and_write_coalesce():
    out = run([w(0x35, 1, 0), w(0x35, 3, 0x9C), w(0x35, 0x3B, 0x9F),
               w(0x35, 1, 0xF6), w(0x35, 3, 1), w(0x35, 0x3B, 0xB0), w(0x35, 3, 2), w(0x35, 0x3B, 0xB1)])
    assert out[0] == "dbg select scaler page 0x9C"
    assert out[1].startswith("dbg write XDATA 0xF6B0..0xF6B1 (2 B)")


def test_halt_resume_and_blocked():
    out = run([w(0x35, 0x80, 1), w(0x35, 0x80, 0), P.Txn("t", 0x35, "w", 0x3B, b"\x01", 0, None, True)])
    assert out == ["dbg halt main loop (0x80 <- 1)", "dbg resume main loop (0x80 <- 0)",
                   "dbg BLOCKED (not sent) write reg 0x3B 01"]


def test_message_protocol():
    hdr = bytes.fromhex("faf5040000009 67e27".replace(" ", ""))
    chunk = bytes.fromhex("050ebd05e5")
    out = run([w(0x35, 0x55, 0x5A), r(0x35, 8, 0xFC), r(0x35, 8, 0xFC), r(0x35, 8, 0xF1), w(0x35, 0x25, 0),
               (0x35, "r", 8, hdr, 9), w(0x35, 0x25, 1), (0x35, "r", 8, chunk, 5), w(0x35, 0x2A), w(0x35, 0x2F)])
    assert out == ["dbg message channel: enable", "dbg message channel status: none (x2)",
                   "dbg message channel status: message pending", 'dbg message "\\x05\\x0e\\xbd\\x05" = 150',
                   "dbg message channel: stop"]


def test_isp_flash_lines():
    lines = decode_file("isp_sector.raw.log").splitlines()
    text = "\n".join(lines)
    for want in ("enter ISP", "erase sector 0x13000 (4 KiB)", "program 0x13000..0x132FF (3 pages, 768 B)",
                 "program page 0x13800 (256 B)", "read flash 0x13000..0x137FF (2048 B)", "CRC 0x13000-0x13FFF",
                 "reset 0xEE <- 0x02", "SPI WREN", "SPI RDSR = 0x00"):
        assert want in text, want
    assert len(lines) < 30                                  # ~11k raw transfers collapse to meanings


def test_pages_not_merged_by_default():
    raw = (DATA / "isp_sector.raw.log").read_text().splitlines()
    out = io.StringIO()
    L.decode_lines(raw, out, DATA / "mini.map", merge_pages=False, root=ROOT)
    assert out.getvalue().count("program page 0x13") == 4


def test_isp_scaler_window_runs():
    seq = [w(0x4A, 0xF4, 0x9F), w(0x4A, 0xF5, 0x9C)]
    for i in range(4):
        seq += [w(0x4A, 0xF4, i), r(0x4A, 0xF5, 0x10 + i)]
    seq += [w(0x4A, 0xF4, 0x92)] + [w(0x4A, 0xF5, b) for b in (1, 2, 3)]
    out = run(seq)
    assert out[0] == "isp select scaler page 0x9C"
    assert out[1].startswith("isp scaler read 0x9C00..0x9C03 (4 B): 10 11 12 13")
    assert out[2].startswith("isp scaler write 0x9C92 <- 3 B: 01 02 03")


def test_jedec_and_crc():
    out = run([w(0x4A, 0x60, 0x46), w(0x4A, 0x61, 0x9F), w(0x4A, 0x60, 0x47), r(0x4A, 0x60, 0x01), r(0x4A, 0x60, 0x00),
               r(0x4A, 0x67, 0xC2), r(0x4A, 0x68, 0x20), r(0x4A, 0x69, 0x14)])
    assert out == ["isp SPI JEDEC ID = C2 20 14"]
    crc = [w(0x4A, a, v) for a, v in ((0x64, 0), (0x65, 0), (0x66, 0), (0x72, 0x0B), (0x73, 0xFF), (0x74, 0xFF))]
    out = run(crc + [w(0x4A, 0x6F, 0x84), r(0x4A, 0x6F, 0x80), r(0x4A, 0x6F, 0x82), r(0x4A, 0x75, 0x3A)])
    assert out == ["isp CRC 0x00000-0xBFFFF = 0x3A"]


def test_edid_scdc_ddc():
    e = bytearray(128)
    e[:8] = bytes.fromhex("00ffffffffffff00")
    e[54 + 3] = 0xFF
    e[54 + 5:54 + 18] = b"AWT26110003\n "
    out = run([w(0x50, 0), (0x50, "r", 0, bytes(e), 128)])
    assert out == ["edid read 0x00..0x7F (128 B) serial AWT26110003"]
    out = run([r(0x54, 0x20, 0x03), w(0x54, 0x20, 0x01)])
    assert out == ["scdc read 0x20 (1 B): TMDS_CONFIG=0x03", "scdc write 0x20 TMDS_CONFIG <- 01"]
    out = run([w(0x37, 0x51, 0x82, 0x01, 0x10, 0), (0x37, "r", 0, bytes([0x6E, 0x88, 0x02, 0, 0x10, 0, 0, 100, 0, 50, 0]), 11),
               w(0x37, 0x51, 0x84, 0x03, 0xD6, 0, 4, 0)])
    assert out == ["ddc get VCP 0x10 brightness = 50 (max 100)", "ddc set VCP 0xD6 power mode = 4"]


def test_raw_roundtrip_and_failures():
    for t in (P.Txn("2026-11-06T14:22:01+1100", 0x35, "w", 0x3B, b"\xf8"),
              P.Txn("x", 0x35, "r", 8, b"\x41", 1), P.Txn("x", 0x4A, "w", 0x70, bytes(range(256))),
              P.Txn("x", 0x35, "w", 0x3B, b"\x01", 0, None, True)):
        back = P.parse_raw("ts " + P.raw_line(t))
        assert (back.dev, back.kind, back.sub, len(back.data), back.blocked) == (t.dev, t.kind, t.sub, len(t.data), t.blocked)
    f = P.parse_raw("ts " + P.raw_line(P.Txn("x", 0x35, "r", 8, None, 1, "[Errno 110] timeout")))
    assert f.data is None and "110" in f.err
    assert run([f]) == ["dbg read reg 0x08 FAILED ([Errno 110] timeout)"]


def test_setup_logs_splits_decoded_and_raw(tmp_path):
    lg = P.setup_logs("t_tool", root=tmp_path)
    try:
        P.trace(0x35, "w", 1, b"\xf6"); P.trace(0x35, "w", 0x3A, b"\xd3"); P.trace(0x35, "r", 8, b"\x08", 1)
        lg.log("my own line")
        lg.close()
    finally:
        P.TAPS.clear()
    main = (tmp_path / "tmp/logs/t_tool.log").read_text().splitlines()
    raw = (tmp_path / "tmp/logs/t_tool.raw.log").read_text().splitlines()
    assert len(raw) == 3 and all("REAL" in x for x in raw)
    assert "dbg  read XDATA 0xF6D3 = 0x08" in main[0]
    assert main[1].endswith("my own line") and "REAL" not in "".join(main)


def test_old_mixed_log_passthrough():
    text = decode_file("dbg_read.old.log")
    assert "2026-11-05T16:22:13+1100 0x0000 @0x0000: cf" in text           # tool line kept in place
    assert "REAL" not in text
