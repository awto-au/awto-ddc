"""Reference monitor (Philips 288E2, devices.json `reference`, #390): registry, refusals, bus choice, pacing, write guard. Fake bus, no hardware."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO / "tests"))
import i2cbus
import reference_mon as R
import unit_ops as U
from reference_fakes import PHILIPS, Clock, FakeMonitor

FORBIDDEN_ADDRS = (0x49, 0x59, 0x4A)          # MStar ISP, MStar SERDB, Realtek ISP


@pytest.fixture()
def ddc():
    clk = Clock()
    FakeMonitor.log, FakeMonitor.clock = [], clk
    FakeMonitor.values = {0x10: (100, 100), 0x12: (50, 100), 0x14: (0x05, 0x0B), 0x60: (0x2F0F, 0x200E), 0xC0: (0x367D, 0xFFFF),
                          0xE9: (2, 2)}
    return R.ReferenceDdc(PHILIPS, find=lambda ref: 11, guard=lambda bus, serial: None, bus_cls=FakeMonitor, clock=clk, nap=clk.nap)


# --- registry + refusals
def test_devices_json_reference_entry():
    d = json.loads((REPO / "scripts/devices.json").read_text())
    assert PHILIPS["kind"] == "reference" and PHILIPS["test"] is False and PHILIPS["serial"] == "UK52307000611"
    assert PHILIPS["serial"] not in {u["serial"] for u in d["units"].values()}          # never in a unit loop
    assert i2cbus.reference_serials() == {"UK52307000611"}


def test_require_unit_refuses_reference_even_when_serial_matches(monkeypatch):
    monkeypatch.setattr(i2cbus, "edid_serial", lambda bus: "UK52307000611")
    for serial, identity in (("UK52307000611", None), ("AWT26110003", None), ("AWT26110003", "relay cycle")):
        with pytest.raises(SystemExit, match="reference monitor"):
            i2cbus.require_unit(11, serial, identity)


@pytest.fixture()
def dev():
    spec = importlib.util.spec_from_file_location("dev_ref_test", REPO / "dev.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["dev_ref_test"] = m
    spec.loader.exec_module(m)
    yield m
    sys.modules.pop("dev_ref_test", None)


@pytest.mark.parametrize("name", ["philips", "UK52307000611"])
def test_dev_unit_refuses_reference(dev, name):
    """_unit() is the door of every dev.py unit command (flash, recover, isp, ddc, dbg link, ...)"""
    with pytest.raises(SystemExit, match="reference monitor"):
        dev._unit(["--unit", name, "--force"])


def test_dev_default_unit_never_reference(dev):
    assert dev._default_unit() in dev._units()


# --- bus choice
def test_candidates_connector_first_and_no_nvidia():
    names = {3: "NVIDIA i2c adapter 3", 11: "i915 gmbus tc3", 15: "AUX USBC1/DDI TC1/PHY TC1", 20: "NVIDIA i2c adapter 7"}
    got = R.candidates(PHILIPS, conn=lambda c: 11, buses=[3, 11, 15, 20], name=lambda b: names[b])
    assert got == [11, 15]
    assert R.candidates(PHILIPS, conn=lambda c: 20, buses=[3, 20], name=lambda b: names[b]) == []    # an NVIDIA link is dropped too


def test_find_bus_by_edid_serial():
    names = {11: "i915 gmbus tc3", 12: "i915 gmbus tc4"}
    edid = {11: "AWT26110003", 12: "UK52307000611"}
    assert R.find_bus(PHILIPS, edid=edid.get, conn=lambda c: 11, buses=[11, 12], name=names.get) == 12
    with pytest.raises(SystemExit, match="no Intel bus"):
        R.find_bus(PHILIPS, edid={}.get, conn=lambda c: None, buses=[11, 12], name=names.get)


def test_prove_refuses_other_monitor():
    R.prove(11, "UK52307000611", edid=lambda b: "UK52307000611")
    with pytest.raises(SystemExit):
        R.prove(11, "UK52307000611", edid=lambda b: "AWT26110003")


# --- traffic: standard Get only, paced
def test_read_all_standard_get_frames_paced(ddc):
    rows = R.read_all(ddc, codes=((0x10, ""), (0x12, ""), (0xF6, ""), (0x60, ""), (0xC0, "")))
    assert [r[1] for r in rows][:2] == ["100 / 100", "50 / 100"] and rows[2][1].startswith("error:")
    assert rows[3][1] == "DP-1" and rows[3][2] == "20 0e 2f 0f" and rows[4][1] == "13949 h"
    writes = [(t, a, f) for t, a, f in FakeMonitor.log if not isinstance(f, tuple)]
    assert {a for _t, a, _f in FakeMonitor.log} == {0x37}
    assert [f for _t, _a, f in writes] == [U.get_frame(c) for c in (0x10, 0x12, 0xF6, 0x60, 0xC0)]
    ends = [t for t, _a, f in FakeMonitor.log if isinstance(f, tuple)]           # each transaction ends with its reply read
    starts = [t for t, _a, _f in writes]
    assert all(s - e >= R.GAP_S - 1e-9 for e, s in zip(ends, starts[1:]))


# --- writes
def test_writes_off_by_default(ddc):
    ddc.get(0x10)
    with pytest.raises(PermissionError, match="writes are off"):
        ddc.set(0x10, 50)
    assert all(f[2] == 0x01 for _t, _a, f in FakeMonitor.log if not isinstance(f, tuple))   # Get opcodes only


@pytest.mark.parametrize("code,value", [(0xD6, 4), (0x62, 10), (0xE9, 0), (0xF6, 1), (0x04, 1), (0xFE, 0)])
def test_write_refuses_other_codes(ddc, code, value):
    ddc.enable_writes(True)
    with pytest.raises(PermissionError, match="not a reference write code"):
        ddc.set(code, value)


def test_write_value_checks(ddc):
    ddc.enable_writes(True)
    with pytest.raises(PermissionError, match="max not read"):
        ddc.set(0x12, 40)
    ddc.get(0x12)
    with pytest.raises(PermissionError, match="outside"):
        ddc.set(0x12, 101)
    with pytest.raises(PermissionError, match="not one of"):
        ddc.set(0x14, 0x03)
    with pytest.raises(PermissionError, match="not one of"):
        ddc.set(0x60, 0x21)                                  # a PIP sub-input value, not a main input


def test_allowed_writes_are_standard_set_vcp(ddc):
    ddc.enable_writes(True)
    ddc.get(0x10)
    for code, v in ((0x10, 70), (0x14, 0x0B), (0x60, 0x11)):
        ddc.set(code, v)
    sets = [f for _t, a, f in FakeMonitor.log if not isinstance(f, tuple) and f[2] == 0x03]
    assert sets == [U.set_frame(0x10, 70), U.set_frame(0x14, 0x0B), U.set_frame(0x60, 0x11)]
    assert not any(a in FORBIDDEN_ADDRS for _t, a, _f in FakeMonitor.log)
    assert not any(f[3:5] in (b"\xfe\xef", b"\xfe\xe1") for _t, _a, f in FakeMonitor.log if not isinstance(f, tuple))


def test_lookup_failure_drops_session():
    calls = []

    def find(ref):
        calls.append(1)
        raise SystemExit("no Intel bus")
    d = R.ReferenceDdc(PHILIPS, find=find, guard=lambda b, s: None, bus_cls=FakeMonitor)
    for _ in range(2):
        with pytest.raises(LookupError):
            d.get(0x10)
    assert len(calls) == 2 and d.session is None


def test_bus_under_no_hw_refuses(monkeypatch):
    monkeypatch.setenv(i2cbus.NO_HW_ENV, "1")
    d = R.ReferenceDdc(PHILIPS, find=lambda ref: 11, guard=lambda b, s: None)
    with pytest.raises(i2cbus.NoHardware):
        d.get(0x10)
