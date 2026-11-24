"""fw/awto/savers.tsv feeds both the C defines (gen_awto_savers.py) and the host names (saver_names.py)."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import saver_names


def test_c_block_current():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/gen_awto_savers.py"), "--check"], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout + r.stderr


def test_vcp_values():
    assert saver_names.vcp("stop") == 0
    assert [saver_names.vcp(n) for n in ("flash", "alert", "splash")] == [5, 6, 7]
    assert saver_names.names() == ["stop", "flash", "splash", "alert"]


def test_removed_games_gone():
    # run ids 1..4, 7 and VCP values 1..4, 8 are not reused (docs/games.md)
    assert all(r["run"] not in (1, 2, 3, 4, 7) and r["vcp"] not in (1, 2, 3, 4, 8) for r in saver_names.SAVERS)


def test_unknown_name_refused():
    try:
        saver_names.vcp("nosuch")
    except KeyError:
        return
    raise AssertionError("expected KeyError")
