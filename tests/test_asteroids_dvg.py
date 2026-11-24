"""scripts/asteroids_dvg.py: DVG decoder checks on the local ROM (skipped when absent) + repo hygiene (no ROM files tracked)."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import asteroids_dvg as D

ZIP = Path(D.DEFAULT_ZIP)
needs_rom = pytest.mark.skipif(not ZIP.exists(), reason="Asteroids ROM set not present (local only)")


def test_no_rom_derived_files_tracked():
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.split("\n")
    bad = [f for f in files if f.endswith((".np3", ".ef2", ".h2", ".j2", ".c8", "asteroid.zip")) or "asteroids_shapes" in f or "/asteroids/" in f or f.startswith("tmp/asteroids")]
    assert not bad, bad


@pytest.mark.parametrize("path", ["tmp/asteroids/shapes.json", "asteroid.zip", "x/035127-02.np3", "docs/asteroids_shapes.json"])
def test_gitignore_covers(path):
    r = subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT, check=False)
    assert r.returncode == 0, path


def test_scale_rule_without_rom():
    d = D.Dvg([0] * 1024)
    d.w[0:3] = [0x6000 | 0x200, 0xC000 | 0x200, 0xD000]  # VCTR op 6, y = 512, x = 512, bright 12; then RTS
    segs, _ = d.decode(D.ROM_BASE_WORD)
    assert segs == [(0.0, 0.0, 64.0, 64.0, 12)]                  # 512 * 2^6 / 512
    d.w[0:2] = [0xF000 | 0x400 | 0x100 | 0x00C0, 0xD000]  # SVEC y = -256, bright 12, then RTS
    segs, _ = d.decode(D.ROM_BASE_WORD)
    assert segs and segs[0][3] == -256 * 2.0 ** 2 / 512       # scale 2 + (bit 11, bit 3 clear) = 2


@needs_rom
def test_rom_shapes():
    words = D.load_rom(ZIP)
    dvg = D.Dvg(words)
    cat = D.catalog(dvg, words)
    assert sum(k.startswith("char_") for k in cat) == 37
    assert sum(k.startswith("hull") for k in cat) == 17 and sum(k.startswith("flame") for k in cat) == 17
    for i in range(4):                                           # rocks: closed outline, 64 x 64 units
        segs, _ = dvg.decode(cat[f"rock{i}"])
        assert segs[0][:2] == segs[-1][2:4]
        x0, y0, x1, y1 = D.bbox(segs)
        assert (x1 - x0, y1 - y0) == (64, 64)
    n, worst = D.verify_ops(dvg, words)
    assert n > 1000 and worst <= 1.0
