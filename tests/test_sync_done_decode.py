"""sync DONE / link health / FAILED rows of the sync log (docs/sync-log-design.md): host decoder, tsv rows, generator."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sync_log as S

ROWS = S.load_rows(ROOT / "fw/awto/sync.tsv")
SDONE, SFAIL, SLINK = 0xEF, 0xFE, 0xFF


def done_value(scan, timing, phy):
    return (scan << 20) | (timing << 8) | phy


def test_done_hdmi_first_try():
    arg = 1 | (2 << 2) | (0 << 4) | (1 << 6)             # D2, HDMI 2.0, no retry, 1 PHY set-up
    assert S.sync_done(arg, done_value(120, 380, 34), 452) == \
        "D2 HDMI 2.0 (1:40), first try: PHY 34ms (1 set-up), scan ok 120ms, timing 380ms, ACTIVE 452ms"


def test_done_retries_and_unseen_stamps():
    arg = 1 | (2 << 2) | (3 << 4) | (3 << 6)
    out = S.sync_done(arg, done_value(0xFFF, 0xFFE, 0xFF), 9000)
    assert out == "D2 HDMI 2.0 (1:40), after 3+ retries: PHY - (3+ set-ups), scan ok -, timing 4094+ms, ACTIVE 9000ms"
    assert "after 1 retry:" in S.sync_done(1 | (1 << 4), 0, 5)


def test_done_dp_counts_trainings():
    arg = 0 | (3 << 2) | (1 << 6)
    assert S.sync_done(arg, done_value(150, 200, 120), 300).startswith("D1 DP, first try: link trained 120ms (1 training), ")


def test_link_hdmi():
    arg = 1 | (2 << 2) | (3 << 4)                         # scrambling on + ratio 1:40, no scrambled data seen
    v = (100 << 24) | (0 << 16) | (7 << 8) | 255
    assert S.sync_link(arg, v) == "D2 HDMI 2.0 (1:40): SCDC ratio 1:40, scrambling on, no scrambled data, errors 0/7/255+, 100ms after ACTIVE"


def test_link_dp_lane_status():
    arg = 0 | (3 << 2) | (4 << 4)                         # 4 lanes
    v = (100 << 24) | (0x14 << 16) | (0x77 << 8) | 0x37  # HBR2; 202h both lanes CR+EQ+SL; 203h: lane 3 lacks symbol lock
    out = S.sync_link(arg, v)
    assert out == "D1 DP HBR2 x4: lanes CR 4/4, EQ 4/4, symbol lock 3/4, 100ms after ACTIVE"


def test_link_not_available_is_said():
    assert "no link health on this input" in S.sync_link(0x80 | 0 | (0 << 2), 100 << 24)


def test_rows_and_line_decode():
    line = S.line(ROWS, (SDONE, 1 | (2 << 2) | (1 << 6), 452, done_value(120, 380, 34)), 0)
    assert line == "  452:sync DONE D2 HDMI 2.0 (1:40), first try: PHY 34ms (1 set-up), scan ok 120ms, timing 380ms, ACTIVE 452ms"
    assert "sync link D2" in S.line(ROWS, (SLINK, 1 | (2 << 2) | (3 << 4), 552, 100 << 24), 0)
    fail = S.line(ROWS, (SFAIL, 0x12, 3012, (5 << 16) | 3012), 0)
    assert fail == " 3012:sync FAILED:CDR not locked at 1:10, retry 1:40 not done (D2, 3012ms)"
    assert S.line(ROWS, (SFAIL, 0x99, 5, (4 << 16) | 5), 0).startswith("    5:sync FAILED:last scan outcome not listed")


def test_failed_reasons_cover_every_scan_code():
    scan_codes = {r["arg"] for r in ROWS if r["id"] == 0xF2 and r["text"].startswith("scan fail")}
    failed = {r["arg"] for r in ROWS if r["id"] == SFAIL}
    assert scan_codes <= failed, f"scan fail codes without a sync FAILED row: {sorted(scan_codes - failed)}"
    assert {0x00, 0x40, 0x41} <= failed


def test_generated_tables_current():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/gen_awto_sync.py"), "--check"], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout[-400:]


@pytest.mark.parametrize("fmt", ["sdone", "slink"])
def test_fmts_known_to_generator(fmt):
    import gen_awto_sync as G
    assert fmt in G.FMTS
