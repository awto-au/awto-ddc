import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from pacman_cli import KEY_CMD


def test_arrow_commands_are_directional():
    assert KEY_CMD[b"\x1b[A"] == 0x62
    assert KEY_CMD[b"\x1b[B"] == 0x63
    assert KEY_CMD[b"\x1b[D"] == 0x64
    assert KEY_CMD[b"\x1b[C"] == 0x65
