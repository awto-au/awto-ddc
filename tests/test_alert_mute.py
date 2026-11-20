"""Automatic alert tone (flash warning, saver tour) honours mute and AWTO_SOUND=off; explicit alert always plays."""
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import alert as A


def fake(monkeypatch, tmp_path, mute_out, env=None):
    calls = []

    def ddc(bus, *args, **kw):
        calls.append(args)
        if args[:2] == ("getvcp", "8D"):
            return None if mute_out is None else SimpleNamespace(stdout=f"VCP code 0x8d (Audio mute): (sl=0x{mute_out:02x})")
        if args[:2] == ("getvcp", "EB"):
            return SimpleNamespace(stdout="ml=0x0a")
        return SimpleNamespace(stdout="")
    monkeypatch.setattr(A, "_ddc", ddc)
    monkeypatch.setattr(A, "LOG", tmp_path / "alert.log")
    monkeypatch.setattr(A.time, "sleep", lambda s: None)
    monkeypatch.delenv("AWTO_SOUND", raising=False)
    if env:
        monkeypatch.setenv("AWTO_SOUND", env)
    return calls


def tone_calls(calls):
    return [c for c in calls if c[0] == "setvcp"]


def test_muted_skips(monkeypatch, tmp_path, capsys):
    c = fake(monkeypatch, tmp_path, 1)
    assert A.alert_auto(5, True) is False and not tone_calls(c)
    assert "alert tone skipped: unit muted" in capsys.readouterr().out


def test_unmuted_plays(monkeypatch, tmp_path, capsys):
    c = fake(monkeypatch, tmp_path, 2)
    assert A.alert_auto(5, True) is True and tone_calls(c) == [("setvcp", "EB", "6")]
    assert "alert tone played" in capsys.readouterr().out


def test_unreadable_skips(monkeypatch, tmp_path, capsys):
    c = fake(monkeypatch, tmp_path, None)
    assert A.alert_auto(5) is False and not tone_calls(c)
    assert "unreadable" in capsys.readouterr().out


def test_env_off_skips_without_reading(monkeypatch, tmp_path, capsys):
    c = fake(monkeypatch, tmp_path, 2, env="off")
    assert A.alert_auto(5) is False and not c
    assert "AWTO_SOUND=off" in capsys.readouterr().out


def test_explicit_alert_ignores_mute(monkeypatch, tmp_path):
    c = fake(monkeypatch, tmp_path, 1)
    assert A.alert(5) is True and tone_calls(c)


def test_auto_call_sites_pass_auto():
    assert '"--wait", "--auto"' in (ROOT / "dev.py").read_text()
    assert '"--wait", "--auto"' in (ROOT / "scripts/saver_ctl.py").read_text()
