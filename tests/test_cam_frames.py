"""cam_frames event detector on a synthetic clip: picture, dark, 3 white flash frames, picture with green console text."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cam_frames as cf


def _clip(path: Path) -> None:
    size = f"{cf.TILE_W}x{cf.TILE_H}"
    pic = f"color=c=0x606080:s={size}:r=25:d={{d}}"
    text = ",drawbox=x=20:y=80:w=120:h=60:color=0x00ff00:t=fill"
    srcs = [pic.format(d=2), f"color=c=0x080808:s={size}:r=25:d=1", f"color=c=white:s={size}:r=25:d=0.12",
            pic.format(d=3)]
    fx = ["", "", "", text]
    cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error"]
    for s, f in zip(srcs, fx, strict=True):
        cmd += ["-f", "lavfi", "-i", s + f]
    cmd += ["-filter_complex", "[0][1][2][3]concat=n=4:v=1:a=0,format=yuv420p", "-c:v", "libx264", "-crf", "12", "-g", "50", str(path)]
    subprocess.run(cmd, check=True)


@pytest.fixture(scope="module")
def events(tmp_path_factory):
    clip = tmp_path_factory.mktemp("cam") / "synthetic.mkv"
    _clip(clip)
    return cf.analyse(clip, cf.ROI_BG)


def test_blackout_and_light(events):
    assert abs(events.dark - 50) <= 1
    assert abs(events.last_good - 49) <= 1
    assert abs(events.first_light - 75) <= 1


def test_flash_counted(events):
    assert len(events.flash) == 3
    assert abs(events.stable - 78) <= 1


def test_console_after_flash(events):
    assert events.console is not None and abs(events.console - 78) <= 1
    assert events.span(events.dark, events.first_light)[0] == events.first_light - events.dark


def test_sweep_clip_split_per_restart(tmp_path):
    size = f"{cf.TILE_W}x{cf.TILE_H}"
    pic = f"color=c=0x606080:s={size}:r=25:d="
    parts = [pic + "3", f"color=c=0x080808:s={size}:r=25:d=1", f"color=c=white:s={size}:r=25:d=0.2", pic + "4"] * 2
    cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error"]
    for p in parts:
        cmd += ["-f", "lavfi", "-i", p]
    clip = tmp_path / "sweep.mkv"
    cmd += ["-filter_complex", f"concat=n={len(parts)}:v=1:a=0,format=yuv420p", "-c:v", "libx264", "-crf", "12", str(clip)]
    subprocess.run(cmd, check=True)
    res = cf.analyse_sweep(clip, sheet_dir=tmp_path / "sheets", expect=2)
    assert len(res) == 2
    for _off, ev in res:
        assert len(ev.flash) == 5 and ev.stable is not None
    assert (tmp_path / "sheets" / "run-02.png").is_file()
