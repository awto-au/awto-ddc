"""dp_rx_port_cutline.py (#326): the Rx1 global cut-line check passes on the tree and fails on a bypass."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/dp_rx_port_cutline.py"
HEADER = "#define g_pucDpRxLinkRate_P(p) g_ucDpRx1LinkRate\n"
SRC = "DPRX_T1(BYTE, g_pucDpRxLinkRate, g_ucDpRx1LinkRate);\nBYTE g_ucDpRx1Other;\nvoid f(void)\n{\n    g_pucDpRxLinkRate_P(0) = 1;\n}\n"
TSV = "name\tclass\tfile\tfunctions\ng_ucDpRx1LinkRate\tlt-hot\ta.c\t\ng_ucDpRx1Other\trx-other\ta.c\t\n"


def tree(tmp_path, src=SRC, tsv=TSV):
    d = tmp_path / "t"
    (d / "fw/sdk").mkdir(parents=True)
    (d / "docs").mkdir()
    (d / "fw/sdk/a.c").write_text(src)
    (d / "fw/sdk/a.h").write_text(HEADER)
    (d / "docs/dp-rx-port-state.tsv").write_text(tsv)
    subprocess.run(["git", "init", "-q"], cwd=d, check=True)
    subprocess.run(["git", "add", "-A"], cwd=d, check=True)
    return d


def run(d, *a):
    return subprocess.run([sys.executable, str(SCRIPT), "--tree", str(d), *a], capture_output=True, text=True, cwd=ROOT, check=False)


def test_clean_tree_passes(tmp_path):
    assert run(tree(tmp_path), "--check").returncode == 0


def test_new_unlisted_global_fails(tmp_path):
    r = run(tree(tmp_path, src=SRC + "BYTE g_ucDpRx1NewThing;\n"), "--check")
    assert r.returncode == 1 and "g_ucDpRx1NewThing" in r.stdout


def test_bare_use_of_hot_state_fails(tmp_path):
    r = run(tree(tmp_path, src=SRC.replace("g_pucDpRxLinkRate_P(0)", "g_ucDpRx1LinkRate")), "--check")
    assert r.returncode == 1 and "bare name" in r.stdout


def test_real_tree_passes():
    assert run(ROOT, "--check").returncode == 0
