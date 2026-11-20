"""cam_frames event detector on a synthetic clip: picture, dark, 3 white flash frames, picture with green console text."""
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import cam_frames as cf


TEXT = ",drawbox=x=20:y=80:w=120:h=60:color=0x00ff00:t=fill,drawbox=x=200:y=20:w=100:h=200:color=0x202040:t=fill"


def _concat(path: Path, parts: list[str]) -> None:
    cmd = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error"]
    for p in parts:
        cmd += ["-f", "lavfi", "-i", p]
    cmd += ["-filter_complex", f"concat=n={len(parts)}:v=1:a=0,format=yuv420p", "-c:v", "libx264", "-crf", "12", "-g", "50", str(path)]
    subprocess.run(cmd, check=True)


def _restart(secs: str) -> list[str]:
    size = f"{cf.TILE_W}x{cf.TILE_H}"
    return [f"color=c=0x606080:s={size}:r=25:d={secs}" + TEXT, f"color=c=0x080808:s={size}:r=25:d=1",
            f"color=c=white:s={size}:r=25:d=0.12", f"color=c=0x606080:s={size}:r=25:d=3" + TEXT]


def _clip(path: Path) -> None:
    _concat(path, _restart("2"))


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
    clip = tmp_path / "sweep.mkv"
    _concat(clip, _restart("3") + _restart("4"))
    res = cf.analyse_sweep(clip, sheet_dir=tmp_path / "sheets", expect=2)
    assert len(res) == 2
    for _off, ev in res:
        assert len(ev.flash) == 3 and ev.stable is not None
    assert (tmp_path / "sheets" / "run-02.png").is_file()
