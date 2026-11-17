"""scripts/gmbus_rate.py rebuilds the module when the kernel changed (#12)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import gmbus_rate as G  # noqa: E402


def test_vermagic_release():
    assert G.vermagic_release("7.3.4-300.fc45.x86_64 SMP preempt mod_unload \n") == "7.3.4-300.fc45.x86_64"
    assert G.vermagic_release("") == ""


def test_built_module_matches_running_kernel_or_is_rebuilt(monkeypatch):
    calls = []
    monkeypatch.setattr(G, "ko_matches_kernel", lambda: False)
    monkeypatch.setattr(G, "run", lambda cmd, t: calls.append(cmd) or type("R", (), {"returncode": 0})())
    monkeypatch.setattr(G.KO.__class__, "exists", lambda self: True, raising=False)
    assert G.ensure_built() == 0
    assert any("clean" in c for c in calls) and any(c[-1] == str(G.SRC) for c in calls)


def test_current_module_is_not_rebuilt(monkeypatch):
    monkeypatch.setattr(G, "ko_matches_kernel", lambda: True)
    monkeypatch.setattr(G, "run", lambda *a: (_ for _ in ()).throw(AssertionError("must not run make")))
    assert G.ensure_built() == 0
