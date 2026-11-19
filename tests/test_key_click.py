"""key_click registry row and ring lines (#229): bool, default off, stored + live, audio group."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COLS = ["id", "name", "type", "unit", "group", "flags", "min", "max", "step", "default", "nv_slot", "vcp", "apply", "label", "options", "note"]


def row():
    for ln in (ROOT / "fw/rtdfw/settings/registry.tsv").read_text().splitlines():
        f = ln.split("\t")
        if len(f) > 2 and f[1] == "key_click":
            return dict(zip(COLS, f))
    raise AssertionError("no key_click row")


def test_default_off_bool_stored_live():
    r = row()
    assert r["type"] == "bool" and r["default"] == "0" and r["group"] == "audio"
    assert {"nv", "live"} <= set(r["flags"].split(","))


def test_sync_rows_exist():
    t = (ROOT / "fw/awto/sync.tsv").read_text()
    for a in ("50", "51"):
        assert f"E5\t{a}\t" in t
