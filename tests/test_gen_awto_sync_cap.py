"""sync log row index is a WORD (0 = no row): more than 254 logged rows generate, the id -> first row table holds the row."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gen_awto_sync as G

ROWS = 600


def test_rows_beyond_a_byte(tmp_path):
    tsv = tmp_path / "sync.tsv"
    tsv.write_text("".join(f"{0x30 + k // 8:02X}\t{k % 8:02X}\t-\trow {k}\n" for k in range(ROWS)))
    r = G.rows(tsv)
    assert len(r) == ROWS
    blk = G.rows_block(r)
    assert f"#define AWTO_SYNC_ROWS {ROWS}" in blk and "WORD AwtoSyncRow(" in blk
    assert f"{(ROWS - 8) + 1}" in blk                # first row + 1 of the last id, above 255


def test_cap_is_enforced(tmp_path):
    tsv = tmp_path / "sync.tsv"
    tsv.write_text("".join(f"{0x30 + k // 8:02X}\t{k % 8:02X}\t-\trow {k}\n" for k in range(G.ROW_MAX + 1)))
    try:
        G.rows(tsv)
    except AssertionError:
        return
    raise AssertionError("cap not enforced")
