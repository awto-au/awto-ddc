"""size_log: map measure, history row writer, reference pick, diff report, graph selection (docs/size-log.md)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import chip_mem as CM
import size_log as S

CE = 0x2800


def _area(name, addr, size, attrs):
    return f"{name:<36}{addr:08X}    {size:08X} = {size:>11}. bytes ({attrs})"


def _map(chunks, extra=()):
    lines = [_area("HOME", 0x53, 0x10, "REL,CON,CODE"), _area("DSEG", 0, 0x20, "REL,CON"), _area("DDOVL0", 0x28, 0x40, "REL,CON"),
             _area("SSEG", 0x80, 0x80, "REL,OVR"), _area("XSEG", 0xE780, 0x100, "REL,CON,XDATA"), "C:   00000035  l_BSEG"]
    lines += [_area(f"CH_{n}", a, s, "REL,CON,CODE") for n, a, s in chunks] + list(extra)
    return "\n".join(lines * 2) + "\n"        # the map repeats the area table per page


def _image(tmp, chunks):
    b, m = tmp / "AWT1-x-be.bin", tmp / "AWT1-x-be.map"
    b.write_bytes(b"\x01" * 0x100 + b"\xff" * (2 * CM.BANK_SIZE - 0x100))
    m.write_text(_map(chunks))
    return b, m


def test_measure_banks_iram_xdata(tmp_path):
    b, m = _image(tmp_path, [("f", CE, 0x100), ("g", CM.BANK_SIZE + CE, 0x30), ("h", CM.BANK_SIZE + CE + 0x30, 0x10)])
    row, funcs = S.measure(b, m)
    assert row["common_b"] == 0x10
    assert S.bank_map(row["bank_used"]) == {0: 0x100, 1: 0x40}
    assert S.bank_map(row["bank_free"]) == {0: CM.BANK_SIZE - CE - 0x100, 1: CM.BANK_SIZE - CE - 0x40}
    assert row["min_bank_free"] == f"0:{CM.BANK_SIZE - CE - 0x100}"
    assert (row["direct_used"], row["direct_free"]) == (0x60, CM.DIRECT_END - 0x60)
    assert (row["xdata_used"], row["bseg_bits"], row["stack"]) == (0x100, 0x35, 0x80)
    assert funcs == {"f": 0x100, "g": 0x30, "h": 0x10}


def test_tree_build_json_wins(tmp_path):
    b, m = _image(tmp_path, [("f", CE, 0x100)])
    tb = {"common_max": CE, "banks": [0, 1], "xdata_free": 77, "compiler": {"commit": "f8d34cffc15be"},
          "iram": {"free_direct": [["0x1e", 2], ["0x7d", 3]], "stack_bytes": 120}}
    row, _ = S.measure(b, m, tb)
    assert (row["direct_free"], row["direct_used"], row["stack"], row["xdata_free"], row["compiler"]) == (5, CM.DIRECT_END - 5, 120, 77, "f8d34cffc1")
    assert S.bank_map(row["bank_used"])[1] == 0


def test_row_writer_roundtrip(tmp_path):
    h = tmp_path / "size" / "size-history.tsv"
    S.append_row(h, {"commit": "abc", "serial": "AWT1", "image_crc": "00000001", "tag": "a\tb"}, {"f": 3})
    S.append_row(h, {"commit": "def", "serial": "AWT1", "image_crc": "00000002"})
    lines = h.read_text().splitlines()
    assert lines[0].split("\t") == S.COLS and len(lines) == 3
    rows = S.read_history(h)
    assert [r["commit"] for r in rows] == ["abc", "def"] and rows[0]["tag"] == "a b"
    assert S.read_funcs(h.parent, "00000001") == {"f": 3} and S.read_funcs(h.parent, "00000002") is None


def _row(commit, crc, dirty=0, serial="AWT1", variant="default", t="2026-11-27T10:00:00+11:00", **kw):
    return {"commit": commit, "image_crc": crc, "dirty": str(dirty), "serial": serial, "variant": variant, "layout": "dev", "time": t, **kw}


def test_pick_refs():
    fp = ["c3", "c2", "c1"]
    rows = [_row("c1", "1"), _row("c2", "2", serial="AWT2"), _row("c2", "3"), _row("x9", "4", dirty=1), _row("c3", "5", variant="clk87")]
    prev, main = S.pick_refs(rows, _row("x9", "6", dirty=1), fp)
    assert prev["image_crc"] == "4"
    assert main["image_crc"] == "3"          # newest main commit with a default build; same serial first


def test_report_deltas_and_top_functions(tmp_path):
    S.append_row(tmp_path / "h.tsv", {"image_crc": "aa"}, {"f": 100, "g": 50, "k": 7})
    old = _row("c1", "aa", common_b="1000", bank_free="0:500,1:900", xdata_free="40")
    new = _row("c2", "bb", dirty=1, diff_hash="1234abcd", common_b="1010", bank_free="0:480,1:900", xdata_free="40")
    out = "\n".join(S.report(new, {"f": 120, "g": 40, "h": 5}, old, None, tmp_path))
    assert "c2*1234abcd" in out
    assert "+10 (+1.00 %)" in out and "+0 (+0.00 %)" in out
    assert "bank free vs prev: b0 -20" in out
    assert "smallest bank free: b0 480 B, b1 900 B" in out
    assert "grew vs prev: f +20, h +5" in out and "shrank vs prev: g -10, k -7" in out


def test_select_main_order_and_dirty():
    fp = ["c3", "c2", "c1"]
    rows = [_row("c2", "1", t="2026-11-27T01:00:00+11:00"), _row("c1", "2"), _row("c2", "3", t="2026-11-27T02:00:00+11:00"),
            _row("c3", "4", dirty=1, diff_hash="aa"), _row("c3", "5", variant="clk87"), _row("zz", "6", branch="b")]
    sel = S.select(rows, fp)
    assert [r["image_crc"] for r in sel] == ["2", "3", "4"]
    assert [r["image_crc"] for r in S.select(rows, fp, branch="b")] == ["2", "3", "6"]
    assert [r["image_crc"] for r in S.select(rows, fp, everything=True)][-2:] == ["5", "4"]


def test_variant_and_label():
    assert S.variant_of([]) == "default"
    assert S.variant_of(["-DAWTO_CLOCK_MHZ=87", "_AWTO_FRC=_OFF"]) == "AWTO_CLOCK_MHZ=87+_AWTO_FRC=_OFF"
    assert S.label({"commit": "0123456789ab", "dirty": "1", "diff_hash": "ff00ff00"}) == "01234567*ff00ff00"


def test_report_skips_direct_delta_across_iram_sources(tmp_path):
    old = _row("c1", "aa", direct_free="3", iram_src="map", common_b="10")
    new = _row("c2", "bb", direct_free="5", iram_src="link", common_b="10")
    out = "\n".join(S.report(new, None, old, None, tmp_path))
    assert "(map source)" in out and "+2" not in out
