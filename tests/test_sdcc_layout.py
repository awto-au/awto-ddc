"""sdcc_layout / sdcc_bank layout-file guards (#51.3, #51.4). Run: python3 -m pytest tests/test_sdcc_layout.py"""
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sdcc_layout as L

ROW = "fn\tFoo\tC\t0x0c00\t64\n"


def _chip(tmp_path):
    """chip_mem reads <AWTO_DDC_REPO>/fw/rl6449_memory.toml: the subprocess repo gets the tracked chip file."""
    (tmp_path / "fw").mkdir(exist_ok=True)
    shutil.copy(Path(L.__file__).resolve().parent.parent / "fw/rl6449_memory.toml", tmp_path / "fw/rl6449_memory.toml")


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


# A bank map made with another common / resid_end is repacked (offsets are build output): no CLI refusal any more.


# --- #51.4: the tracked layout is only replaced by fw_build after link + check ---------------------------------

def test_sdcc_bank_writes_layout_out_not_tracked_file(tmp_path):
    import os
    import subprocess
    (tmp_path / "asm").mkdir()
    (tmp_path / "tmp/sdcc-port").mkdir(parents=True)
    lay = _file(tmp_path, "#common 0x6000\n#resid_end 0xc00\n")
    before = lay.read_text()
    new = tmp_path / "new.tsv"
    _chip(tmp_path)
    env = dict(os.environ, AWTO_DDC_REPO=str(tmp_path))
    r = subprocess.run([sys.executable, str(Path(L.__file__).parent / "sdcc_bank.py"), "--asm", str(tmp_path / "asm"),
                        "--out", str(tmp_path / "out"), "--layout", str(lay), "--layout-out", str(new)],
                       env=env, capture_output=True, text=True, timeout=30, check=False)   # 30 s: stall backstop, run takes ~0.1 s
    assert r.returncode == 0, r.stderr
    assert new.exists() and lay.read_text() == before


def test_fw_build_promote_layout(tmp_path, monkeypatch):
    import fw_build
    monkeypatch.setattr(fw_build, "LOG", open(tmp_path / "log", "w"))  # noqa: SIM115 - test-lifetime log
    new, tracked = tmp_path / "new.tsv", tmp_path / "bank_map.tsv"
    (tmp_path / "bank_map.new.tsv").write_text("#common 0x5000\nfn\tA\tC\n")
    tracked.write_text("old\n")
    fw_build.promote_layout(new, tracked)
    assert tracked.read_text() == "#common 0x5000\nfn\tA\tC\n"


def test_fw_build_promotes_after_link_and_check():
    src = (Path(L.__file__).parent / "fw_build.py").read_text()
    main = src[src.index("def main()"):]
    assert main.index('"link"') < main.index("check_layout(") < main.index("promote_layout(") if '"link"' in main else \
        main.index("sdcc_link.link(") < main.index("check_layout(") < main.index("promote_layout(")


# --- #51.5 / #51.6 fw_build defaults, --cluster, FW_TAG ---------------------------------------------------------

def test_fw_build_default_layout_is_tracked_file():
    import fw_build
    assert fw_build.parse_args(["--serial", "X"]).layout == "fw/bank_map.tsv"
    assert fw_build.parse_args(["--serial", "X", "--layout", ""]).layout == ""


def test_fw_build_cluster_refused_unless_layout_created(tmp_path, monkeypatch):
    import fw_build
    monkeypatch.setattr(fw_build, "ROOT", tmp_path)
    (tmp_path / "fw").mkdir()
    with pytest.raises(SystemExit, match="--cluster"):                         # no layout at all
        fw_build.parse_args(["--serial", "X", "--layout", "", "--cluster", "fn"])
    (tmp_path / "fw/bank_map.tsv").write_text(ROW)
    with pytest.raises(SystemExit, match="existing layout"):                   # layout in use
        fw_build.parse_args(["--serial", "X", "--cluster", "fn"])
    (tmp_path / "fw/bank_map.tsv").unlink()                                 # being created: allowed
    assert fw_build.parse_args(["--serial", "X", "--cluster", "fn"]).cluster == "fn"


def test_sdcc_bank_cluster_refused_with_existing_layout(tmp_path):
    import os
    import subprocess
    (tmp_path / "asm").mkdir()
    _chip(tmp_path)
    lay = _file(tmp_path, "#common 0x6000\n#resid_end 0xc00\n")
    r = subprocess.run([sys.executable, str(Path(L.__file__).parent / "sdcc_bank.py"), "--asm", str(tmp_path / "asm"),
                        "--out", str(tmp_path / "out"), "--layout", str(lay), "--cluster", "fn"],
                       env=dict(os.environ, AWTO_DDC_REPO=str(tmp_path)), capture_output=True, text=True, timeout=30, check=False)
    assert r.returncode != 0 and "--cluster" in r.stderr


def test_fw_tag_env_override_and_no_dirty(tmp_path, monkeypatch):
    import subprocess

    import msg_tokenise
    monkeypatch.setenv("AWTO_FW_TAG", "fixed-1")
    assert msg_tokenise.fw_tag(tmp_path) == "fixed-1"
    monkeypatch.delenv("AWTO_FW_TAG")
    g = lambda *a: subprocess.run(["git", *a], cwd=tmp_path, check=True, capture_output=True)
    g("init", "-q"); g("-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "x")
    clean = msg_tokenise.fw_tag(tmp_path)
    (tmp_path / "f").write_text("x"); g("add", "f")                            # staged change: --dirty would append
    assert msg_tokenise.fw_tag(tmp_path) == clean and "dirty" not in clean and len(clean) == 7


def test_new_item_beats_slack_rule():
    """Every foreign bank would drop below the slack reserve, the item still fits: placed, not an error (#268)."""
    cap = 1000
    lay = L.Layout()
    it = L.Item("fn", "Big", 40, 0, "m")
    fill = [L.Item("const", f"Pad{b}", 1, b, "m", slot=cap - it.slot - 5) for b in (0, 1)]
    for f in fill:
        f.fixed = True
    placed, _ = L.assign(fill + [it], lay, 0, 0, 2, cap, log=lambda *_: None)
    assert placed[("fn", "Big")][0] in (0, 1)


def _mod_layout(a_slot, b_slot):
    lay = L.Layout()
    lay.rows[("fn", "A")] = (1, 0, a_slot)         # module m: more code in bank 1 than in bank 0
    lay.rows[("fn", "B")] = (0, 0, b_slot)
    return lay, [L.Item("fn", "A", a_slot - 8, 1, "m", slot=a_slot), L.Item("fn", "B", b_slot - 8, 0, "m", slot=b_slot)]


def test_new_fn_goes_to_module_bank_with_most_code():
    lay, its = _mod_layout(400, 100)
    new = L.Item("fn", "New", 40, 0, "m")          # sdcc_bank's guess (bank 0) is ignored: bank 1 holds more of m
    placed, _ = L.assign([*its, new], lay, 0, 0, 3, 1000, log=lambda *_: None)
    assert placed[("fn", "New")][0] == 1


def test_new_fn_takes_next_module_bank_when_first_is_full():
    lay, its = _mod_layout(400, 100)
    pad = L.Item("const", "Pad", 1, 1, "x", slot=1000 - 400 - 8)
    pad.fixed = True
    placed, _ = L.assign([*its, pad, L.Item("fn", "New", 40, 1, "m")], lay, 0, 0, 3, 1000, log=lambda *_: None)
    assert placed[("fn", "New")][0] == 0


def test_fixed_const_falls_back_to_common_when_bank_full():
    lay = L.Layout()
    pad = L.Item("const", "Pad", 1, 0, "a", slot=990)
    pad.fixed = True
    c = L.Item("const", "T", 12, 0, "m")
    c.fixed = True
    placed, _ = L.assign([pad, c], lay, 0, 100, 1, 1000, log=lambda *_: None)
    assert placed[("const", "T")][0] == "C"


def test_assign_packs_back_to_back_without_padding():
    lay = L.Layout()
    lay.rows[("fn", "A")] = (0, 0, 400)                 # an old row's offset / slot is ignored: packed by size
    its = [L.Item("fn", "B", 100, 0, "m"), L.Item("fn", "A", 100, 0, "m")]
    placed, _ = L.assign(its, lay, 0, 0, 1, 1000, log=lambda *_: None)
    assert placed[("fn", "A")] == (0, 0, 100) and placed[("fn", "B")] == (0, 100, 100)


def test_map_text_has_regions_only():
    lay = L.Layout()
    lay.rows[("fn", "A")] = (3, 40, 100)
    lay.rows[("stub", "S")] = ("C", 0, 8)
    txt = lay.map_text()
    assert "fn\tA\t3\n" in txt and "stub" not in txt
