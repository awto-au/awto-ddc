"""Unit locks guard shared hardware: one lock dir for every worktree (the main checkout)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import unit_lock as U


def test_lock_dir_is_the_main_checkout_for_every_worktree():
    assert U.LOCKS == U.lock_root() / "tmp" / "locks"
    assert (U.lock_root() / ".git").exists()
