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
        "D2 HDMI 2.0 (1:40), first try: PHY 34ms (1 set-up), scan ok +120ms, timing +380ms, ACTIVE 452ms"


def test_done_retries_and_unseen_stamps():
    arg = 1 | (2 << 2) | (3 << 4) | (3 << 6)
    out = S.sync_done(arg, done_value(0xFFF, 0xFFE, 0xFF), 9000)
    assert out == "D2 HDMI 2.0 (1:40), after 3+ retries: PHY - (3+ set-ups), scan ok -, timing +4094+ms, ACTIVE 9000ms"
    assert "after 1 retry:" in S.sync_done(1 | (1 << 4), 0, 5)


def test_done_dp_counts_trainings():
    arg = 0 | (3 << 2) | (1 << 6)
    assert S.sync_done(arg, done_value(150, 200, 120), 300).startswith("D1 DP, first try: link trained 120ms (1 training), ")


def test_link_hdmi():
    arg = 1 | (2 << 2) | (3 << 4)                         # SCDC 20h bits both 1, no scrambled data seen
    v = (100 << 24) | (0 << 16) | (7 << 8) | 255
    assert S.sync_link(arg, v) == "D2 HDMI 2.0 (1:40): no scrambled data, SCDC 20h as the source left it: ratio bit 1 scrambling bit 1, errors 0/7/255+, 100ms after ACTIVE"


def test_link_dp_lane_status():
    arg = 0 | (3 << 2) | (4 << 4)                         # 4 lanes
    v = (100 << 24) | (0x14 << 16) | (0x77 << 8) | 0x37  # HBR2; 202h both lanes CR+EQ+SL; 203h: lane 3 lacks symbol lock
    out = S.sync_link(arg, v)
    assert out == "D1 DP HBR2 x4: lanes CR 4/4, EQ 4/4, symbol lock 3/4, 100ms after ACTIVE"


def test_link_not_available_is_said():
    assert "no link health on this input" in S.sync_link(0x80 | 0 | (0 << 2), 100 << 24)


def test_rows_and_line_decode():
    line = S.line(ROWS, (SDONE, 1 | (2 << 2) | (1 << 6), 452, done_value(120, 380, 34)), 0)
    assert line == "  452:sync DONE D2 HDMI 2.0 (1:40), first try: PHY 34ms (1 set-up), scan ok +120ms, timing +380ms, ACTIVE 452ms"
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


def test_link_scdc_zero_is_raw_evidence_not_a_verdict():
    out = S.sync_link(1 | (2 << 2) | (4 << 4), 147 << 24)           # PHY 1:40, scrambled data seen, SCDC bits left 0 by the source
    assert out.startswith("D2 HDMI 2.0 (1:40): scrambled data seen, SCDC 20h as the source left it: ratio bit 0 scrambling bit 0")


def test_visit_reached_and_left():
    d2 = 5 << 16                                          # _D2_INPUT_PORT = 5
    assert S.sync_visit(0x80 | 1 | 2, d2) == "reached D2: predetect on, cable detected"
    assert S.sync_visit(0x80, d2) == "reached D2: predetect off, no cable"
    assert S.sync_visit(0x04 | 0x08, (6 << 24) | d2 | 4975) == "left D2 after 4975ms: predetect seen, 6 edges, dwell re-armed"
    assert S.sync_visit(0, d2 | 12) == "left D2 after 12ms: no signal, 0 edges"
    assert S.sync_visit(0x02, d2 | 1) == "left D2 after 1ms: port disabled, skipped"


def test_gap_rows_decode():
    line = S.line(ROWS, (0xF3, 0x80 | 3, 500, 6 << 16), 0)
    assert line == "  500:search reached D3: predetect on, cable detected"
    assert S.line(ROWS, (0x94, 0, 700, (102 << 16) | 100), 0) == "  700:ACTIVE wait:timer 100ms, panel ready 102ms"
    assert S.line(ROWS, (0x93, 0x0F, 400, 0x09090909), 0).endswith(":INITIAL:SDK flags set until: source 36ms, mode 36ms, OSD 36ms, other 36ms")
    assert S.line(ROWS, (0x93, 0x04, 400, 120 << 8), 0).endswith(":INITIAL:SDK flags set until: OSD 480ms")
    assert S.line(ROWS, (0x93, 0, 166, (68 << 16) | 36), 0).endswith(":INITIAL:first exit check at 36ms, longest gap between checks 68ms")
    assert S.line(ROWS, (0x95, 5, 900, 4025), 0).startswith("  900:D2 search dwell re-armed")



def test_pins_row_decode():
    """#359 HPD edges of one poll: one line listing each changed port"""
    assert S.line(ROWS, (0xFA, 5, 55, (7 << 8) | 6), 0).endswith(":HPD: D1 low, D2 high, D3 high")
    assert S.line(ROWS, (0xFA, 5, 548, (1 << 8) | 7), 0).endswith(":HPD: D1 high")
    assert S.line(ROWS, (0xFA, 0x10, 56, (3 << 8) | 3), 0).endswith(":cable pin: D1 high, D2 high")
    assert S.line(ROWS, (0xFA, 3, 48, 6 << 16), 0).endswith(":EDID load: took 0ms (HPD mask 6)")

def test_pass_rows_decode():
    """#311 main-loop stage timing: slow stage line (96) and boot passes line (97); names / words from RL6449_Project.h AWTO_PSTG_NAMES"""
    names = S.pass_names()[0]
    osd, sub = names.index("OSD handler"), names.index("console: panel tick (open)")
    initial = 2                                                    # AWTO_SYS_INITIAL
    assert S.line(ROWS, (0x96, osd, 500, (initial << 24) | (4 << 16) | 214), 0) == "  500:slow pass stage OSD handler took 214ms in INITIAL (#4)"
    assert S.line(ROWS, (0x97, sub, 700, (initial << 24) | 268), 0) == "  700:boot passes:INITIAL longest 268ms in stage console: panel tick (open)"


def test_pass_stage_ids_match_names():
    """every AWTO_PSTG_* stage id of the header indexes its own name; the line words start at AWTO_PSTG_WORD0"""
    import re
    txt = (ROOT / "fw/sdk/Project/Header/RL6449_Project.h").read_text()
    names, w0 = S.pass_names()
    ids = {m.group(1): int(m.group(2)) for m in re.finditer(r"^#define AWTO_PSTG_([A-Z0-9_]+)\s+(\d+)\b", txt, re.MULTILINE)}
    stages = {k: v for k, v in ids.items() if k not in ("SLOW_MS", "NOTE_MS", "STATES", "WORD0")}
    assert len(stages) == len(set(stages.values())) and max(stages.values()) < w0
    assert all(names[v] for v in stages.values()), "a stage id without a name"
    assert len(names) == w0 + 7


def test_host_time_one_row():
    """host time + its fw ms line: one row, joined by a space as the console draws it (#358 / #359)"""
    evs = [(0xD7, 44, 6753, 1795757671), (0xD8, 1, 6753, 6753)]
    texts = [S.line(ROWS, e, 0).split(":", 1)[1] for e in evs]
    rs = S.con_rows(evs, texts, [(6753, True), (6753, True)])
    assert len(rs) == 1 and rs[0]["text"] == texts[0] + " (fw +6753 ms, first host sync since boot)"


def test_refresh_pixel_clock_one_row():
    """#359 refresh + pixel clock of one display setting (same ms): one row"""
    evs = [(0xC7, 5, 823, 59991), (0xC8, 5, 823, 593915)]
    texts = [S.line(ROWS, e, 0).split(":", 1)[1] for e in evs]
    rs = S.con_rows(evs, texts, [(823, True), (823, True)])
    assert len(rs) == 1 and rs[0]["text"] == "D2 refresh 59.991Hz | D2 pixel clock 593.915MHz"


def test_nvram_flush_one_line():
    """#359 (Dan 2026-11-27): NVRAM flush why + result on one line"""
    assert S.line(ROWS, (0xD4, 0x37, 5398, 0), 0).endswith(":NVRAM flush (DDC/CI save settings): nothing changed, no flash write (0ms)")
