"""Control-port client and flash job parsing, no Qt (the offscreen port tests: tools/osd_editor/test_control_port.py; #276)."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import flash_job
import gui_client as GC
import i2c_raw


def test_translate_ddc_and_settings():
    assert GC.translate("ddc", ["get", "0x62", "0x8D"], "1") == [("vcp", {"unit": "1", "link": "hdmi", "op": "get", "codes": ["0x62", "0x8D"]})]
    assert GC.translate("ddc", ["set", "0x62", "30", "--dp"], "2")[0][1]["link"] == "dp"
    assert GC.translate("ddc", ["sleep"], "1")[0][0] == "passthrough"
    assert GC.translate("settings", ["set", "gamma", "2", "--no-confirm"], "3")[0] == (
        "set", {"unit": "3", "link": "hdmi", "name": "gamma", "value": "2", "confirm": True})
    assert GC.translate("settings", ["list"], "1")[0][0] == "get"
    assert GC.translate("settings", ["save"], "1")[0][0] == "save"
    assert GC.translate("settings", ["defaults"], "1")[0][0] == "passthrough"


def test_translate_refuses_what_the_port_cannot_carry():
    with pytest.raises(GC.PortCannotCarry):
        GC.translate("kvm", ["hdmi1"], "1")                       # no --units: the port acts on named test units only
    with pytest.raises(GC.PortCannotCarry):
        GC.translate("ddc", ["get", "0x62", "--force"], "1")
    assert [m for m, _ in GC.translate("kvm", ["D2", "--units", "1,3", "--verify"], "1")] == ["kvm", "kvm"]


def test_is_write():
    assert GC.is_write("ddc", ["set", "0x62", "3"]) and not GC.is_write("ddc", ["get", "0x62"])
    assert GC.is_write("settings", ["save"]) and not GC.is_write("settings", ["get", "gamma"])
    assert GC.is_write("flash", []) and GC.is_write("kvm", ["D1"]) and not GC.is_write("synclog", [])
    assert GC.is_write("i2c", ["0x34", "0x22"]) and not GC.is_write("i2c", ["0x34", "--read", "2"])


def test_gui_forms():
    reqs, _ = GC.parse_gui(["--serial", "S", "--kvm", "hdmi-1", "--save"])
    assert reqs == [("kvm", {"serial": "S", "target": "hdmi-1"}), ("save", {"serial": "S", "verify": ["input"]})]
    reqs, _ = GC.parse_gui(["get", "volume", "--unit", "1"])
    assert reqs == [("get", {"unit": "1", "names": ["volume"]})]
    reqs, _ = GC.parse_gui(["list"], default_unit="1")
    assert reqs == [("list", {})]                                  # no unit invented for a list
    reqs, _ = GC.parse_gui(["set", "mute", "on"], default_unit="2")
    assert reqs[0][1]["unit"] == "2"
    with pytest.raises(GC.PortCannotCarry):
        GC.parse_gui(["--bogus"])


def test_i2c_args_are_bounded():
    for bad in (["--addr", "0x80", "--write", "1"], ["--addr", "0x34"], ["--addr", "0x34", "--write", "256"]):
        with pytest.raises(SystemExit):
            i2c_raw.parse_args(["--bus", "1", "--serial", "S", *bad])


def test_flash_progress_parse():
    p = flash_job.Progress(time.time() - 10)
    for ln in ("per-sector mode: 4 sectors, boot/common last", "written+verified 2/4 sectors (3s)",
               "0x001000: 'x'; try 1/3", "ERROR: boom", "redo sector alone", "recover (x): ok",
               "burst failures redone in byte mode: 2; ISP recoveries 3; aux"):
        p.feed(ln)
    s = p.snapshot()
    assert (s["total"], s["written"], s["percent"], s["phase"]) == (4, 2, 50.0, "write")
    assert s["errors"] == 1 and (s["redo"], s["recoveries"]) == (2, 3) and s["eta_s"] > 0
    p.rc = 7
    assert p.snapshot()["phase"] == "failed" and p.snapshot()["eta_s"] is None


def test_flash_progress_erase_all_mode():
    p = flash_job.Progress(time.time())
    p.feed("erased 8/8 sectors (1s)")
    p.feed("written+verified 4/8 sectors (2s)")
    assert p.percent() == 75.0
