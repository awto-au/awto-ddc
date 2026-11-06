"""sdcc_layout / sdcc_bank layout-file guards (#51.3, #51.4). Run: python3 -m pytest tests/test_sdcc_layout.py"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sdcc_layout as L  # noqa: E402

ROW = "fn\tFoo\tC\t0x0c00\t64\n"


def _file(tmp_path, header):
    p = tmp_path / "bank_layout.tsv"
    p.write_text(header + ROW)
    return p


def test_header_mismatch_common_refused(tmp_path):
    lay = L.Layout.load(_file(tmp_path, "#common 0x5000\n#resid_end 0xc00\n"))
    with pytest.raises(SystemExit, match="common=0x5000"):
        lay.check_header(0x6000, 0xC00, "x")


def test_header_mismatch_resid_end_refused(tmp_path):
    lay = L.Layout.load(_file(tmp_path, "#common 0x5000\n#resid_end 0xc00\n"))
    with pytest.raises(SystemExit, match="resid_end"):
        lay.check_header(0x5000, 0xD00, "x")


def test_header_match_and_headerless_accepted(tmp_path):
    L.Layout.load(_file(tmp_path, "#common 0x5000\n#resid_end 0xc00\n")).check_header(0x5000, 0xC00)
    L.Layout().check_header(0x6000, 0xC00)           # new layout / no header: nothing to compare


def test_sdcc_bank_cli_refuses_mismatched_layout(tmp_path):
    """sdcc_bank --common-max differing from the layout header exits non-zero before any placement."""
    import os
    import subprocess
    (tmp_path / "asm").mkdir()
    lay = _file(tmp_path, "#common 0x5000\n#resid_end 0xc00\n")
    env = dict(os.environ, AWTO_DDC_REPO=str(tmp_path))
    r = subprocess.run([sys.executable, str(Path(L.__file__).parent / "sdcc_bank.py"), "--asm", str(tmp_path / "asm"),
                        "--out", str(tmp_path / "out"), "--common-max", "0x6000", "--layout", str(lay)],
                       env=env, capture_output=True, text=True, timeout=30)   # 30 s: stall backstop, run takes ~0.1 s
    assert r.returncode != 0 and "refusing" in r.stderr
    assert lay.read_text().startswith("#common 0x5000")
