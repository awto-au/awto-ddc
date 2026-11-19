"""fw/awto/savers.tsv feeds both the C defines (gen_awto_savers.py) and the host names (saver_names.py)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import saver_names  # noqa: E402


def test_c_block_current():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/gen_awto_savers.py"), "--check"], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_vcp_rule_matches_firmware():
    # saver.c: value 1 = selected saver, 2.. = run id + 1 for Pac-Man / Scope 2 (VCP 3 = retired Scope 1, not in the TSV)
    for name in ("pacman", "scope2"):
        row = next(r for r in saver_names.SAVERS if r["name"] == name)
        assert row["vcp"] == row["run"] + 1
    assert saver_names.vcp("selected") == 1 and saver_names.vcp("stop") == 0


def test_retired_scope1_gone():
    assert all(r["name"] != "scope1" and r["run"] != 2 and r["vcp"] != 3 for r in saver_names.SAVERS)


def test_build_options_in_header():
    # each saver that can be left out has a default _ON option in the project header (dev.py build --savers)
    hdr = (ROOT / "fw/sdk/Project/Header/RL6449_Project.h").read_text()
    opts = saver_names.options()
    assert set(opts) == {"pacman", "scope2", "asteroids"}
    for o in opts.values():
        assert f"#ifndef {o}\n#define {o}" in hdr


def test_unknown_name_refused():
    try:
        saver_names.vcp("nosuch")
    except KeyError:
        return
    raise AssertionError("expected KeyError")
