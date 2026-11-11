"""Tool-hazard fixes from reviews #52 / #50 (dev.py level). No hardware."""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import json
import pytest

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def dev(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location("dev_under_test", REPO / "dev.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["dev_under_test"] = m
    spec.loader.exec_module(m)
    monkeypatch.setattr(m, "REPO", tmp_path)
    monkeypatch.setattr(m, "TMP", tmp_path / "tmp")
    monkeypatch.setattr(m, "FW", tmp_path / "tmp" / "fw")
    monkeypatch.setattr(m, "LOGS", tmp_path / "tmp" / "logs")
    monkeypatch.setattr(m, "LOG", tmp_path / "tmp" / "logs" / "dev.log")
    import json
    real = json.loads((REPO / "scripts/devices.json").read_text())["units"]
    real = {k: {**v, "test": True} for k, v in real.items()}     # no hardware here; the working-screen guard is not under test
    monkeypatch.setattr(m, "_units", lambda: real)
    yield m
    sys.modules.pop("dev_under_test", None)


def test_clean_keeps_images_state_regs_logs(dev, tmp_path):
    t = tmp_path / "tmp"
    keep = ["fw/AWT1-abc-be.bin", "fw/AWT1-abc-be.map", "fw/AWT1-abc-be.ids.tsv", "fw/AWT1-flashed.json",
            "fw/AWT1-flash-state.json", "regs/dump.txt", "logs/x.log", "notes.md"]
    gone = ["sdcc-port/asm/a.asm", "fw/AWT1/fw.bin", "fw/AWT1/fw.map"]
    for f in keep + gone:
        (t / f).parent.mkdir(parents=True, exist_ok=True)
        (t / f).write_text("x")
    assert dev.cmd_clean([]) == 0
    for f in keep:
        assert (t / f).exists(), f
    for f in gone:
        assert not (t / f).exists(), f


# --- #52.9 power_cycle honours the relay name --------------------------------

def _run_power_cycle(monkeypatch, tmp_path, argv):
    spec = importlib.util.spec_from_file_location("pc_under_test", REPO / "scripts" / "power_cycle.py")
    pc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pc)
    calls = []
    monkeypatch.setitem(pc.OUTLETS, "so-th-1", lambda state, log=print: calls.append(state))
    monkeypatch.setattr(pc, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(pc.time, "sleep", lambda s: None)
    monkeypatch.setattr(sys, "argv", ["power_cycle.py", *argv])
    return pc.main(), calls


def test_power_cycle_requires_relay(monkeypatch, tmp_path):
    with pytest.raises(SystemExit):
        _run_power_cycle(monkeypatch, tmp_path, ["--off"])


def test_power_cycle_refuses_unknown_relay(monkeypatch, tmp_path):
    rc, calls = _run_power_cycle(monkeypatch, tmp_path, ["--relay", "so-th-9", "--off"])
    assert rc == 2 and calls == []


def test_power_cycle_known_relay_cycles(monkeypatch, tmp_path):
    rc, calls = _run_power_cycle(monkeypatch, tmp_path, ["--relay", "so-th-1"])
    assert rc == 0 and calls == [False, True]


def test_dev_passes_unit_relay(dev, monkeypatch):
    seen = []
    monkeypatch.setattr(dev, "_py", lambda script, *a, env=None, shield=False: seen.append((script, a)) or 0)
    assert dev.cmd_power_cycle(["--unit", "3", "--off"]) == 0
    assert seen == [("power_cycle.py", ("--relay", "so-th-1", "--off"))]


# --- #52.7 mode: every logical monitor copied, only the target changed --------

SHOW = (REPO / "tests/data/gdctl_show.txt").read_text()


def _groups(args):
    out, cur = [], None
    for a in args:
        if a == "--logical-monitor":
            cur = []
            out.append(cur)
        else:
            cur.append(a)
    return out


def test_mode_copies_all_monitors_changes_target(dev):
    args = dev.gdctl_set_args(SHOW, "HDMI-2", dev.MODES["4k30"])
    g = _groups(args)
    assert len(g) == 4
    flat = [" ".join(x) for x in g]
    assert "--primary --monitor DP-4 --mode 3840x2160@60.000 --x 0 --y 0" in flat
    assert "--monitor DP-2 --mode 3840x2160@59.997 --x 3840 --y 0" in flat
    assert "--monitor HDMI-3 --mode 3840x2160@60.000 --x 7680 --y 0" in flat
    assert "--monitor HDMI-2 --mode 3840x2160@30.000 --x 11520 --y 0" in flat


def test_mode_dp_connector_not_in_layout_refused(dev):
    with pytest.raises(SystemExit):
        dev.gdctl_set_args(SHOW, "DP-1", dev.MODES["4k30"])


def test_mode_dp_flag_targets_dp_connector(dev, monkeypatch):
    shown = SHOW.replace("HDMI-2", "DP-1")
    calls = []

    def fake_run(cmd, **kw):
        assert kw.get("timeout")
        class R: returncode, stdout, stderr = 0, shown, ""
        return R()
    monkeypatch.setattr(dev.subprocess, "run", fake_run)
    monkeypatch.setattr(dev.subprocess, "call", lambda cmd, **kw: calls.append((cmd, kw)) or 0)
    assert dev.cmd_mode(["--unit", "3", "--dp", "4k30"]) == 0
    cmd, kw = calls[0]
    assert kw.get("timeout")
    assert cmd[cmd.index("DP-1") + 2] == "3840x2160@30.000"


def test_mode_gdctl_timeout_changes_nothing(dev, monkeypatch):
    def boom(cmd, **kw):
        raise dev.subprocess.TimeoutExpired(cmd, kw["timeout"])
    monkeypatch.setattr(dev.subprocess, "run", boom)
    monkeypatch.setattr(dev.subprocess, "call", lambda *a, **k: pytest.fail("gdctl set must not run"))
    assert dev.cmd_mode(["--unit", "3", "4k30"]) == 1


def test_mode_set_timeout_reported(dev, monkeypatch):
    class R: returncode, stdout, stderr = 0, SHOW, ""
    monkeypatch.setattr(dev.subprocess, "run", lambda *a, **k: R())

    def boom(cmd, **kw):
        raise dev.subprocess.TimeoutExpired(cmd, kw["timeout"])
    monkeypatch.setattr(dev.subprocess, "call", boom)
    assert dev.cmd_mode(["--unit", "3", "4k30"]) == 1


def test_mode_keeps_nondefault_scale_and_transform(dev):
    show = SHOW.replace("Scale: 1.0", "Scale: 2.0", 1).replace("Transform: normal", "Transform: 90", 1)
    g = " ".join(dev.gdctl_set_args(show, "HDMI-2", dev.MODES["4k30"]))
    assert "--x 0 --y 0 --scale 2.0 --transform 90" in g


# --- #50.28 / #52.10-11 flasher identity --------------------------------------

sys.path.insert(0, str(REPO / "scripts"))


def _flash_main(monkeypatch, tmp_path, extra, require):
    import rtd_flash_image as I
    img = tmp_path / "AWT26110003-x-be.bin"
    img.write_bytes(b"\xff" * 4096)
    monkeypatch.setattr(sys, "argv", ["rtd_flash_image.py", "7", str(img), "--serial", "AWT26110003", *extra])
    monkeypatch.setattr(I.F, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(I.i2cbus, "require_unit", require)
    opened = []

    def no_rtd(bus):
        opened.append(bus)
        raise AssertionError("ISP session opened")
    monkeypatch.setattr(I, "Rtd", no_rtd)
    return I, opened


def test_flasher_refuses_wrong_unit_before_isp(monkeypatch, tmp_path):
    def require(bus, serial, identity=None):
        raise SystemExit("EDID serial mismatch")
    I, opened = _flash_main(monkeypatch, tmp_path, ["--write"], require)
    with pytest.raises(SystemExit):
        I.main()
    assert opened == []


def test_flasher_passes_identity_to_guard(monkeypatch, tmp_path):
    seen = []

    def require(bus, serial, identity=None):
        seen.append((bus, serial, identity))
        return None
    I, opened = _flash_main(monkeypatch, tmp_path, ["--identity", "relay cycle"], require)
    with pytest.raises(AssertionError):             # guard passed, reached Rtd()
        I.main()
    assert seen == [(7, "AWT26110003", "relay cycle")] and opened == [7]


def _img(tmp_path, name, body):
    p = tmp_path / name
    p.write_bytes(body)
    return p


def test_image_identity_accepts_matching(dev, tmp_path):
    u = {"serial": "AWT26110003"}
    dev.check_image_identity(u, _img(tmp_path, "AWT26110003-abc-be.bin", b"xx AWT26110003 yy"))


@pytest.mark.parametrize("name,body", [
    ("AWT26110002-abc-be.bin", b"AWT26110003"),             # tag says unit 2
    ("AWT26110003-abc-be.bin", b"AWT26110002\0AWT26110003"),  # embedded foreign serial
    ("AWT26110003-abc-be.bin", b"AWT26110002"),             # only foreign serial
    ("anything-be.bin", b"no serial here"),                 # unknown provenance
])
def test_image_identity_refuses(dev, tmp_path, name, body):
    with pytest.raises(SystemExit):
        dev.check_image_identity({"serial": "AWT26110003"}, _img(tmp_path, name, body))


def test_dev_flash_refuses_other_unit_image_before_bus(dev, tmp_path, monkeypatch):
    img = _img(tmp_path, "AWT26110002-abc-be.bin", b"AWT26110002")
    monkeypatch.setattr(dev, "_bus", lambda u: pytest.fail("bus touched"))
    with pytest.raises(SystemExit):
        dev.cmd_flash(["--unit", "3", str(img)])


def test_deploy_uses_shared_image_then_programs_unit_edid(dev, tmp_path, monkeypatch):
    img = _img(tmp_path, "shared.bin", b"shared firmware")
    dev.FW.mkdir(parents=True)
    calls = []
    monkeypatch.setattr(dev, "_firmware_edid_sector", lambda p: 0x5000)
    monkeypatch.setattr(dev, "_bus", lambda u: 21)
    monkeypatch.setattr(dev, "cmd_flash", lambda a: calls.append(("flash", a)) or 0)
    monkeypatch.setattr(dev, "_py", lambda script, *a, env=None, shield=False:
                        calls.append((script, list(a), shield)) or 0)
    assert dev.cmd_deploy(["--unit", "3", "--force", "--force-ungated", str(img)]) == 0
    flash = next(x for x in calls if x[0] == "flash")
    assert "--any-image" in flash[1] and "--force-ungated" in flash[1]
    sector = next(x for x in calls if x[0] == "rtd_flash_sector.py")
    assert sector[1][0:2] == [21, "0x5000"]
    assert "--expect-current" in sector[1] and "--write" in sector[1]
    state = json.loads((dev.FW / "AWT26110003-flashed.json").read_text())
    assert state["edid_serial"] == "AWT26110003"


def test_edid_recovery_uses_caller_proven_bus_without_reflashing(dev, tmp_path, monkeypatch):
    img = _img(tmp_path, "shared.bin", b"shared firmware")
    dev.FW.mkdir(parents=True)
    patched, expected = dev.FW / "patched.bin", dev.FW / "expected.bin"
    patched.write_bytes(b"p" * 4096)
    expected.write_bytes(b"e" * 4096)
    calls = []
    monkeypatch.setattr(dev, "_build_unit_edid_sector", lambda u, p: (0x5000, patched, expected, 0))
    monkeypatch.setattr(dev, "_bus", lambda u: pytest.fail("must not identify by temporary EDID"))
    monkeypatch.setattr(dev, "_py", lambda script, *a, env=None, shield=False:
                        calls.append((script, list(a), shield)) or 0)
    assert dev.cmd_edid(["--unit", "3", "--force", "--bus", "21", str(img)]) == 0
    assert calls == [("rtd_flash_sector.py",
                      [21, "0x5000", patched, "--expect-current", expected, "--write"], True)]


def test_dev_flash_bus_passes_identity(dev, tmp_path, monkeypatch):
    img = _img(tmp_path, "AWT26110003-abc-be.bin", b"AWT26110003")
    seen = []
    dev.FW.mkdir(parents=True)
    monkeypatch.setattr(dev, "_py", lambda script, *a, env=None, shield=False: seen.append(a) or 0)

    class FB:
        def __init__(s, bus): pass
        def __enter__(s): return 1000
        def __exit__(s, *a): return False
    monkeypatch.setattr(dev.i2cbus, "fast_bus", FB)
    assert dev.cmd_flash(["--unit", "3", "--bus", "11", "--force-ungated", str(img)]) == 0
    assert "--identity" in seen[0]


# --- #52.12 flashed.json invalidated before the write ---------------------------

class _FB:
    def __init__(s, bus): pass
    def __enter__(s): return 1000
    def __exit__(s, *a): return False


def _flash_setup(dev, tmp_path, monkeypatch):
    img = _img(tmp_path, "AWT26110003-new-be.bin", b"AWT26110003")
    dev.FW.mkdir(parents=True)
    fj = dev.FW / "AWT26110003-flashed.json"
    fj.write_text('{"tag": "AWT26110003-old-be", "image": "old.bin"}')
    monkeypatch.setattr(dev, "_bus", lambda u: 11)
    monkeypatch.setattr(dev.i2cbus, "fast_bus", _FB)
    return img, fj


def test_failed_flash_leaves_no_stale_tag(dev, tmp_path, monkeypatch):
    import json
    img, fj = _flash_setup(dev, tmp_path, monkeypatch)
    monkeypatch.setattr(dev, "_py", lambda *a, env=None, shield=False: 7)
    assert dev.cmd_flash(["--unit", "3", "--force-ungated", str(img)]) == 7
    d = json.loads(fj.read_text())
    assert d["tag"] == "" and d["image"] == str(img)
    with pytest.raises(SystemExit):                 # dbg/osd/health map lookup refuses
        dev._fwmap(dev._units()["3"], None)


def test_flash_exception_leaves_no_stale_tag(dev, tmp_path, monkeypatch):
    import json
    img, fj = _flash_setup(dev, tmp_path, monkeypatch)

    def boom(*a, env=None, shield=False):
        raise KeyboardInterrupt
    monkeypatch.setattr(dev, "_py", boom)
    with pytest.raises(KeyboardInterrupt):
        dev.cmd_flash(["--unit", "3", "--force-ungated", str(img)])
    assert json.loads(fj.read_text())["tag"] == ""


def test_successful_flash_records_new_tag(dev, tmp_path, monkeypatch):
    import json
    img, fj = _flash_setup(dev, tmp_path, monkeypatch)
    monkeypatch.setattr(dev, "_py", lambda *a, env=None, shield=False: 0)
    assert dev.cmd_flash(["--unit", "3", "--force-ungated", str(img)]) == 0
    assert json.loads(fj.read_text()) == {"tag": "AWT26110003-new-be", "image": str(img)}


# --- #52.2 / #52.3 / #48 recover, probe --bus; #52.1 hold bounded ---------------------------------------------

def _recover_setup(dev, tmp_path, monkeypatch, bus_results):
    """bus_results: iterable of ints / SystemExit instances returned by successive _bus calls."""
    img = _img(tmp_path, "AWT26110003-r-be.bin", b"AWT26110003")
    dev.FW.mkdir(parents=True, exist_ok=True)
    (dev.FW / "AWT26110003-r-be.gates.json").write_text(json.dumps(
        {"sha256": __import__("hashlib").sha256(img.read_bytes()).hexdigest(), "complete": True, "gates": {"link": {"result": "PASS"}}}))
    events, it = [], iter(bus_results)

    def fake_bus(u, wait_s=0.0):
        events.append(("bus", wait_s))
        r = next(it)
        if isinstance(r, BaseException):
            raise r
        return r
    monkeypatch.setattr(dev, "_bus", fake_bus)
    monkeypatch.setattr(dev, "cmd_power_cycle", lambda e: events.append(("relay",)) or 0)
    monkeypatch.setattr(dev, "_diag", lambda u, *a, bus=None: events.append(("diag", a, bus)) or 0)
    monkeypatch.setattr(dev, "cmd_flash", lambda e: events.append(("flash", e)) or 0)
    _flashed_map(dev, "AWT26110003-r-be", with_safe=True)      # default: the flashed image has the safe block
    return img, events


def _flashed_map(dev, tag, with_safe):
    """flashed.json + map fixture for unit 3; with_safe adds the _g_stAwtoSafe symbol line."""
    dev.FW.mkdir(parents=True, exist_ok=True)
    (dev.FW / "AWT26110003-flashed.json").write_text(json.dumps({"tag": tag, "image": ""}))
    safe = "     0000F6B0  _g_stAwtoSafe                      SysMain\n" if with_safe else ""
    (dev.FW / f"{tag}.map").write_text("     0000EA89  _g_stOsdInfo                       RTD2014Osd\n" + safe
                                       + "     0000F6D0  _g_stAwtoDiag                      SysMain\n")


def test_recover_bad_image_refused_before_relay(dev, tmp_path, monkeypatch):
    _img_, events = _recover_setup(dev, tmp_path, monkeypatch, [11])
    with pytest.raises(SystemExit):
        dev.cmd_recover(["--unit", "3"])                # no flashed.json, no image
    with pytest.raises(SystemExit):
        dev.cmd_recover(["--unit", "3", str(_img(tmp_path, "AWT26110002-x-be.bin", b"AWT26110002"))])
    assert events == []


def test_recover_scans_bus_once_before_relay_when_unit_answers(dev, tmp_path, monkeypatch):
    img, events = _recover_setup(dev, tmp_path, monkeypatch, [11])
    assert dev.cmd_recover(["--unit", "3", str(img)]) == 0
    assert [e[0] for e in events] == ["bus", "relay", "diag", "flash"]
    assert events[2][2] == 11                           # hold gets the resolved bus, no second scan
    assert events[3][1][events[3][1].index("--bus") + 1] == "11"


def test_recover_wedged_unit_short_deadline_lookup_after_relay(dev, tmp_path, monkeypatch):
    img, events = _recover_setup(dev, tmp_path, monkeypatch, [SystemExit("silent"), 11])
    assert dev.cmd_recover(["--unit", "3", str(img)]) == 0
    assert [e[0] for e in events] == ["bus", "relay", "bus", "diag", "flash"]
    assert 0 < events[2][1] <= 5.0


def test_recover_hold_failure_still_flashes(dev, tmp_path, monkeypatch):
    img, events = _recover_setup(dev, tmp_path, monkeypatch, [11])
    monkeypatch.setattr(dev, "_diag", lambda u, *a, bus=None: 1)
    monkeypatch.setattr(dev, "cmd_flash", lambda e: events.append(("flash",)) or 0)
    assert dev.cmd_recover(["--unit", "3", str(img)]) == 0
    assert ("flash",) in events


def test_recover_skips_hold_without_safe_block_in_map(dev, tmp_path, monkeypatch):
    """#52: hold writes 0xF6B0, live XDATA on images without _g_stAwtoSafe (working-base line)."""
    img, events = _recover_setup(dev, tmp_path, monkeypatch, [11])
    _flashed_map(dev, "AWT26110003-r-be", with_safe=False)
    assert dev.cmd_recover(["--unit", "3", str(img)]) == 0
    assert [e[0] for e in events] == ["bus", "relay", "flash"]


def test_recover_skips_hold_when_flashed_map_missing(dev, tmp_path, monkeypatch):
    img, events = _recover_setup(dev, tmp_path, monkeypatch, [11])
    (dev.FW / "AWT26110003-r-be.map").unlink()
    assert dev.cmd_recover(["--unit", "3", str(img)]) == 0
    assert "diag" not in [e[0] for e in events]


def test_bus_wait_rescans_until_edid_appears(dev, monkeypatch):
    u = dict(dev._units()["3"])
    seq = iter([None, None, "AWT26110003"])
    monkeypatch.setattr(dev.i2cbus, "edid_serial", lambda b: next(seq))
    monkeypatch.setattr(dev.i2cbus, "list_buses", lambda display_only=True: [])
    monkeypatch.setattr(dev.i2cbus, "reset_rate", lambda: False)
    monkeypatch.setattr(dev, "BUS_RESCAN_S", 0.001)
    monkeypatch.setattr(dev.Path, "resolve", lambda self: Path("/sys/class/drm/x/i2c-11"))
    assert dev._bus(u, wait_s=2.0) == 11


def test_probe_accepts_bus_without_edid_scan(dev, monkeypatch):
    seen = []
    monkeypatch.setattr(dev, "_bus", lambda u, wait_s=0.0: pytest.fail("EDID scan"))
    monkeypatch.setattr(dev, "_py", lambda script, *a, env=None, shield=False: seen.append((script, a)) or 0)
    assert dev.cmd_probe(["--unit", "3", "--bus", "11", "--window", "3"]) == 0
    assert seen == [("rtd_boot_probe.py", (11, "--window", "3"))]


def _diag_mod():
    import rtd_diag
    return rtd_diag


def test_hold_is_bounded_and_closes_one_fd(monkeypatch, tmp_path):
    D = _diag_mod()
    assert D.HOLD_WAIT_S <= 5.0
    made = []

    class FakeReal:
        def __init__(self, bus, allow_write=False, regread=False):
            self.closed = False
            made.append(self)
        def write(self, *a):
            return False                                # never ACKs
        def close(self):
            self.closed = True
    clock = [0.0]
    monkeypatch.setattr(D.B, "Real", FakeReal)
    monkeypatch.setattr(D.B, "setup_logs", lambda name: type("L", (), {"main": open(os.devnull, "w")})())
    monkeypatch.setattr(D, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(D.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(D.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    monkeypatch.setattr(sys, "argv", ["rtd_diag.py", "11", "--hold"])
    assert D.main() == 1
    holders = [m for m in made if m.closed]
    assert len(made) == 2 and len(holders) == 2          # io (regread) + ONE hold handle, both closed
    assert clock[0] <= 5.0 + 0.1



# --- #52.4 / #52.18 diag --messages / --release / extra args ----------------------------------------------------

class FakeDbg:
    """Debug slave 0x35 fake: records writes; write_fail(cmd) -> number of leading NAKs for that cmd."""
    def __init__(self, nak=None, reads=None):
        self.nak = dict(nak or {})
        self.reads = list(reads or [])
        self.log = []

    def write(self, dev8, sub, data):
        if self.nak.get(sub, 0) > 0:
            self.nak[sub] -= 1
            self.log.append(("nak", sub))
            return False
        self.log.append(("w", sub))
        return True

    def read(self, dev8, sub, n):
        return self.reads.pop(0) if self.reads else bytes([0xFC])


@pytest.fixture()
def D(monkeypatch):
    d = _diag_mod()
    monkeypatch.setattr(d, "LOG", open(os.devnull, "w"))
    monkeypatch.setattr(d.time, "sleep", lambda s: None)
    return d


def _acked(io):
    return [x[1] for x in io.log if x[0] == "w"]


def test_release_retries_each_command(D):
    io = FakeDbg(nak={0x2A: 3, 0x2F: 2})
    assert D._release(io) is True
    assert _acked(io) == [0x2A, 0x2F]


def test_release_gives_up_after_bounded_tries_and_reports(D):
    io = FakeDbg(nak={0x2A: 99, 0x2F: 99})
    assert D._release(io) is False
    assert sum(1 for x in io.log if x[0] == "nak") == 2 * D.RELEASE_TRIES


@pytest.mark.parametrize("reads", [
    [None],                                              # header read fails
    [bytes([0x00] * 9)],                                 # bad header magic
])
def test_fetch_message_failure_paths_still_send_end(D, reads):
    io = FakeDbg(reads=reads)
    assert D.fetch_message(io) is None
    assert 0x2A in _acked(io)


def test_fetch_message_enable_nak_still_sends_end(D):
    io = FakeDbg(nak={0x25: 99})
    assert D.fetch_message(io) is None
    assert 0x2A in _acked(io)


def test_messages_secs_limit_then_release(D, monkeypatch, tmp_path):
    clock = [0.0]
    monkeypatch.setattr(D.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(D.time, "sleep", lambda s: clock.__setitem__(0, clock[0] + s))
    io = FakeDbg()                                       # status always 0xFC: no message
    assert D.messages(io, tmp_path, secs=0.5) == 0
    assert 0.5 <= clock[0] < 0.6
    assert _acked(io)[-2:] == [0x2A, 0x2F]


def test_messages_read_failure_releases(D, tmp_path):
    class Dead(FakeDbg):
        def read(self, *a):
            return None
    io = Dead()
    assert D.messages(io, tmp_path, secs=5) == 1
    assert _acked(io)[-2:] == [0x2A, 0x2F]


def test_messages_interrupt_releases(D, tmp_path):
    class Intr(FakeDbg):
        def read(self, *a):
            raise KeyboardInterrupt
    io = Intr()
    assert D.messages(io, tmp_path, secs=5) == 0
    assert _acked(io)[-2:] == [0x2A, 0x2F]


def test_messages_mode_installs_sighup_handler(D, monkeypatch, tmp_path):
    import signal
    seen = {}
    monkeypatch.setattr(D.signal, "signal", lambda sig, h: seen.__setitem__(sig, h))
    monkeypatch.setattr(D.B, "Real", lambda *a, **k: type("R", (), {"close": lambda s: None})())
    monkeypatch.setattr(D.B, "setup_logs", lambda name: type("L", (), {"main": open(os.devnull, "w")})())
    monkeypatch.setattr(D, "repo_root", lambda: tmp_path)
    monkeypatch.setattr(D, "messages", lambda io, root, secs=None: seen.__setitem__("secs", secs) or 0)
    monkeypatch.setattr(sys, "argv", ["rtd_diag.py", "11", "--messages", "--secs", "7"])
    assert D.main() == 0
    assert signal.SIGHUP in seen and signal.SIGTERM in seen and seen["secs"] == 7
    with pytest.raises(SystemExit):
        seen[signal.SIGHUP](signal.SIGHUP, None)         # handler exits -> finally in messages() runs


def test_dev_diag_passes_messages_release_secs(dev, monkeypatch):
    seen = []
    monkeypatch.setattr(dev, "_diag", lambda u, *a, bus=None: seen.append(a) or 0)
    assert dev.cmd_diag(["--unit", "3", "--release"]) == 0
    assert dev.cmd_diag(["--unit", "3", "--messages", "--secs", "5"]) == 0
    assert dev.cmd_diag(["--unit", "3"]) == 0
    assert seen == [("--release",), ("--messages", "--secs", "5"), ()]


@pytest.mark.parametrize("fn,args", [
    ("cmd_diag", ["--bogus"]), ("cmd_diag", ["--messages", "--release"]), ("cmd_diag", ["--secs", "5"]),
    ("cmd_diag", ["--messages", "--secs", "x"]), ("cmd_safe", ["--watch", "2"]), ("cmd_trace", ["--messages"]),
])
def test_dev_diag_safe_trace_refuse_extra_args(dev, monkeypatch, fn, args):
    monkeypatch.setattr(dev, "_diag", lambda *a, **k: pytest.fail("bus touched"))
    with pytest.raises(SystemExit):
        getattr(dev, fn)(["--unit", "3", *args])


# --- flash refuses ungated images (tmp/fw/<stem>.gates.json from scripts/fw_gates.py) -------------

def _gated_setup(dev, tmp_path, monkeypatch, gates=None, sha_of=None, complete=True, write=True):
    import hashlib
    img, fj = _flash_setup(dev, tmp_path, monkeypatch)
    ran = []
    monkeypatch.setattr(dev, "_py", lambda script, *a, env=None, shield=False: ran.append(script) or 0)
    if write:
        sha = hashlib.sha256(sha_of if sha_of is not None else img.read_bytes()).hexdigest()
        (dev.FW / f"{img.stem}.gates.json").write_text(json.dumps(
            {"image": img.name, "sha256": sha, "complete": complete,
             "gates": gates or {"link": {"result": "PASS"}, "keys": {"result": "SKIP"}}}))
    return img, ran


def test_flash_refuses_image_without_gate_record(dev, tmp_path, monkeypatch):
    img, ran = _gated_setup(dev, tmp_path, monkeypatch, write=False)
    with pytest.raises(SystemExit, match="no AWT26110003-new-be.gates.json"):
        dev.cmd_flash(["--unit", "3", str(img)])
    assert ran == []


def test_flash_refuses_gate_record_for_changed_image(dev, tmp_path, monkeypatch):
    img, ran = _gated_setup(dev, tmp_path, monkeypatch, sha_of=b"another build")
    with pytest.raises(SystemExit, match="SHA-256 mismatch"):
        dev.cmd_flash(["--unit", "3", str(img)])
    assert ran == []


def test_flash_refuses_failed_gate(dev, tmp_path, monkeypatch):
    img, ran = _gated_setup(dev, tmp_path, monkeypatch, gates={"link": {"result": "PASS"}, "wake": {"result": "FAIL"}})
    with pytest.raises(SystemExit, match="FAILED: wake"):
        dev.cmd_flash(["--unit", "3", str(img)])
    assert ran == []


def test_flash_refuses_partial_gate_record(dev, tmp_path, monkeypatch):
    img, ran = _gated_setup(dev, tmp_path, monkeypatch, complete=False)
    with pytest.raises(SystemExit, match="partial"):
        dev.cmd_flash(["--unit", "3", str(img)])


def test_flash_accepts_pass_and_skip(dev, tmp_path, monkeypatch):
    img, ran = _gated_setup(dev, tmp_path, monkeypatch)
    assert dev.cmd_flash(["--unit", "3", str(img)]) == 0
    assert "rtd_flash_image.py" in ran


def test_force_ungated_flashes_and_logs_loudly(dev, tmp_path, monkeypatch):
    img, ran = _gated_setup(dev, tmp_path, monkeypatch, gates={"link": {"result": "FAIL"}})
    lines = []
    monkeypatch.setattr(dev, "log", lambda msg, level="INFO": lines.append((level, msg)))
    assert dev.cmd_flash(["--unit", "3", "--force-ungated", str(img)]) == 0
    assert any(l == "ALERT" and "UNGATED IMAGE FLASHED ON PURPOSE" in m and "FAILED: link" in m for l, m in lines)


def test_archived_image_needs_no_gate_record(dev, tmp_path, monkeypatch):
    img, ran = _gated_setup(dev, tmp_path, monkeypatch, write=False)
    (tmp_path / "fw" / "images").mkdir(parents=True)
    (tmp_path / "fw" / "images" / img.name).write_bytes(img.read_bytes())
    assert dev.cmd_flash(["--unit", "3", str(img)]) == 0


def test_archived_name_with_other_bytes_is_not_accepted(dev, tmp_path, monkeypatch):
    img, ran = _gated_setup(dev, tmp_path, monkeypatch, write=False)
    (tmp_path / "fw" / "images").mkdir(parents=True)
    (tmp_path / "fw" / "images" / img.name).write_bytes(b"different")
    with pytest.raises(SystemExit, match="flash refused"):
        dev.cmd_flash(["--unit", "3", str(img)])


def test_deploy_refuses_ungated_before_any_step(dev, tmp_path, monkeypatch):
    img = _img(tmp_path, "shared.bin", b"shared firmware")
    dev.FW.mkdir(parents=True)
    monkeypatch.setattr(dev, "_py", lambda *a, **k: pytest.fail("ran a tool"))
    with pytest.raises(SystemExit, match="flash refused"):
        dev.cmd_deploy(["--unit", "3", "--force", str(img)])
