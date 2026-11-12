"""sdk_rules_lint: the gate fails on an SDK patch path and passes on a clean tree (#162)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import sdk_rules_lint as L  # noqa: E402


def tree(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "fw/sdk").mkdir(parents=True)
    (tmp_path / "fw/awto/x").mkdir(parents=True)
    (tmp_path / "fw/sdk/a.c").write_text("int x; // awto: fine (#1)\n")
    return tmp_path


def test_clean(tmp_path):
    assert L.lint(tree(tmp_path))[0] == []


def test_findings(tmp_path):
    t = tree(tmp_path)
    (t / "scripts/keil2sdcc.py").write_text("")
    (t / "scripts/other.py").write_text("INSERTS = []\n")
    (t / "scripts/sdk_own.py").write_text("INSERTS = []\n")        # one-off, allowed
    (t / "fw/awto/x/rules.py").write_text("")
    (t / "fw/sdk/b.h").write_text("int y;  // [keil2sdcc] insert\n")
    bad = "\n".join(L.lint(t)[0])
    assert "keil2sdcc.py" in bad and "other.py:1" in bad and "rules.py" in bad and "b.h" in bad and "sdk_own" not in bad
