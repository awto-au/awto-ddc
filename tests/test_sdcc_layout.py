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


# --- #51.4: the tracked layout is only replaced by fw_build after link + check ---------------------------------

def test_sdcc_bank_writes_layout_out_not_tracked_file(tmp_path):
    import os
    import subprocess
    (tmp_path / "asm").mkdir()
    (tmp_path / "tmp/sdcc-port").mkdir(parents=True)
    lay = _file(tmp_path, "#common 0x6000\n#resid_end 0xc00\n")
    before = lay.read_text()
    new = tmp_path / "new.tsv"
    env = dict(os.environ, AWTO_DDC_REPO=str(tmp_path))
    r = subprocess.run([sys.executable, str(Path(L.__file__).parent / "sdcc_bank.py"), "--asm", str(tmp_path / "asm"),
                        "--out", str(tmp_path / "out"), "--layout", str(lay), "--layout-out", str(new)],
                       env=env, capture_output=True, text=True, timeout=30)   # 30 s: stall backstop, run takes ~0.1 s
    assert r.returncode == 0, r.stderr
    assert new.exists() and lay.read_text() == before


def test_fw_build_promote_layout(tmp_path, monkeypatch):
    import fw_build
    monkeypatch.setattr(fw_build, "LOG", open(tmp_path / "log", "w"))
    new, tracked = tmp_path / "new.tsv", tmp_path / "bank_layout.tsv"
    new.write_text("#common 0x5000\nfn\tA\tC\t0x0c00\t8\n")
    tracked.write_text("old\n")
    fw_build.promote_layout(new, tracked)
    assert tracked.read_text() == new.read_text()


def test_fw_build_promotes_after_link_and_check():
    src = (Path(L.__file__).parent / "fw_build.py").read_text()
    main = src[src.index("def main()"):]
    assert main.index('"link"') < main.index("check_layout(") < main.index("promote_layout(") if '"link"' in main else \
        main.index("sdcc_link.link(") < main.index("check_layout(") < main.index("promote_layout(")
