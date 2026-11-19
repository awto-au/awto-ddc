"""Gate tiers: normal = flash gate, extensive = before a merge to main (fw_gates.EXTENSIVE, dev.py merge-check)."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import fw_gates as G  # noqa: E402


def test_extensive_names_are_real_gates_and_the_core_stays_normal():
    names = set(G.gates(Path("x-be.bin"), Path("tests/conftest.py"), None, ROOT))     # the map is only read for the menu / ddc keys
    assert set(G.EXTENSIVE) <= names | {"menu", "menu_full", "delays_full", "canary"}      # image-dependent: registry, a -clk87 sibling, the canary symbol
    for core in ("boot", "isr", "link", "panel", "delays", "htime", "nvlog", "bootsim", "pump", "ddc"):
        assert core not in G.EXTENSIVE


def _merge_check(tmp_path, **doc):
    img = tmp_path / "t-be.bin"
    img.write_bytes(b"image")
    (tmp_path / "t-be.gates.json").write_text(json.dumps({"sha256": hashlib.sha256(b"image").hexdigest(), "complete": True,
                                                          "gates": {"boot": {"result": "PASS"}}, **doc}))
    return subprocess.run([sys.executable, str(ROOT / "dev.py"), "merge-check", str(img)], capture_output=True, text=True, cwd=ROOT)


def test_merge_check_refuses_a_normal_record(tmp_path):
    r = _merge_check(tmp_path, tier="normal")
    assert r.returncode != 0 and "extensive required" in (r.stdout + r.stderr)


def test_merge_check_accepts_an_extensive_record(tmp_path):
    assert _merge_check(tmp_path, tier="extensive").returncode == 0


def test_merge_check_refuses_a_failed_gate(tmp_path):
    r = _merge_check(tmp_path, tier="extensive", gates={"keys": {"result": "FAIL"}})
    assert r.returncode != 0 and "FAIL: keys" in (r.stdout + r.stderr)
