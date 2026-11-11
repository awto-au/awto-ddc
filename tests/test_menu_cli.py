import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from menu_cli import keyboard_action


def test_keyboard_arrow_mappings_are_user_facing():
    assert keyboard_action(b"\x1b[A") == "left"    # Up = previous
    assert keyboard_action(b"\x1b[B") == "right"   # Down = next
    assert keyboard_action(b"\x1b[C") == "menu"    # Right = select
    assert keyboard_action(b"\x1b[D") == "exit"    # Left = back


def test_keyboard_select_back_and_quit_aliases():
    assert keyboard_action(b"\r") == "menu"
    assert keyboard_action(b"\x1b") == "exit"
    assert keyboard_action(b"\x7f") == "exit"
    assert keyboard_action(b"q") == "quit"
    assert keyboard_action(b"?") is None
