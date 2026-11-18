"""Health monitor host side (fw/diag/monitor.c): g_stAwtoMon decode, sync row text, registry row, constants (docs/monitoring.md)."""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mon_decode as D  # noqa: E402
import sync_log as SL  # noqa: E402

BLOCK = bytes([ord("M"), ord("N"), 1, 1, 7, 0xF8, 0xF8, 0x58, 0x20, 0x07, 0xCF, 0x02, 0xBC, 0x0F, 3, 0xBC, 1, 0, 0x0E, 0x10, 9])


def test_decode_block():
    d = D.decode(BLOCK)
    assert d["adc"] == [0xF8, 0xF8, 0x58, 0x20] and d["trim"] == 0x07CF == 1999 and d["loop"] == 700
    assert d["up_s"] == 3600 and d["stack"] == 0xBC and d["rows"] == 9 and d["poke_ms"] == round(15 * 293 / 64)
    assert "ADC A0 F8 A1 F8 A2 58 A3 20" in D.text(d) and "boot cold power-up" in D.text(d)


def test_decode_no_sample():
    assert D.decode(bytes(D.SIZE)) is None and D.decode(b"MN") is None


def test_sync_row_text():
    assert SL.mon_text(1, 0xF8F85820) == "ADC A0 F8 A1 F8 A2 58 A3 20"
    assert SL.mon_text(2, 1999) == "IOSC trim count 1999"
    assert SL.mon_text(3, 700 << 16 | 18) == "main loop 700 passes/s, longest watchdog gap 18ms"
    assert SL.mon_text(4, 3600 << 8 | 0xBC) == "uptime 3600 s, stack high BC"
    rows = SL.load_rows(ROOT / "fw/awto/sync.tsv")
    ev = (0xEA, 2, 0, 1999)
    assert SL.line(rows, ev, 0).endswith("monitor: IOSC trim count 1999")


def test_constants_and_registry():
    h = (ROOT / "fw/sdk/Project/Header/RL6449_Project.h").read_text()
    v = {k: int(x) for k, x in re.findall(r"#define (AWTO_MON_\w+)\s+(\d+)", h)}
    assert v["AWTO_MON_MS"] == 10000 and v["AWTO_MON_BEAT_K"] == 30
    assert v["AWTO_MON_ADC_STEP"] == 2 * 8                 # two 5-bit codes
    reg = [ln.split("\t") for ln in (ROOT / "fw/rtdfw/settings/registry.tsv").read_text().splitlines() if ln.startswith("124\t")]
    assert reg and reg[0][1] == "monitor" and reg[0][9] == "1"    # default on: the cost is measured (docs/monitoring.md)
