"""ddc_ctl --bus resolves the connector from DRM sysfs without `ddcutil detect` (a detect probes every bus incl. DP AUX)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import ddc_ctl


def test_bus_monitor_from_sysfs(tmp_path):
    for name, bus in (("card1-DP-1", 15), ("card1-HDMI-A-2", 11)):
        (tmp_path / name).mkdir()
        (tmp_path / f"i2c-{bus}").mkdir()
        (tmp_path / name / "ddc").symlink_to(tmp_path / f"i2c-{bus}")
    (tmp_path / "card1-eDP-9").mkdir()                       # connector without a ddc link
    assert ddc_ctl.bus_monitor(15, tmp_path) == [{"connector": "card1-DP-1", "bus": 15, "model": "?"}]
    assert ddc_ctl.bus_monitor(11, tmp_path)[0]["connector"] == "card1-HDMI-A-2"
    assert ddc_ctl.bus_monitor(99, tmp_path) == []
