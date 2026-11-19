"""scripts/gen_asteroids.py: shape data of the Asteroids screensaver (own outlines without the ROM, ROM geometry with it) + the repo keeps none of it."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import asteroids_dvg as D
import gen_asteroids as G

needs_rom = pytest.mark.skipif(not Path(D.DEFAULT_ZIP).exists(), reason="Asteroids ROM set not present (local only)")
C_SRC = (ROOT / "fw/test/asteroids.c").read_text()


def shapes(fallback=True):
    sh = G.fallback_shapes() if fallback else G.rom_shapes(D.DEFAULT_ZIP)
    for i, d in enumerate(G.DIGITS):
        sh[G.ID_DIGIT + i] = [list(pl) for pl in d]
    return sh


def test_fallback_has_every_shape_and_fits_int8():
    sh = shapes()
    assert sorted(sh) == list(range(G.N_SHAPES))
    blob, offs = G.encode(sh)
    assert len(offs) == G.N_SHAPES and offs == sorted(offs) and len(blob) < 1000


def test_fallback_rocks_closed_and_ship_tip_turns_a_quarter():
    sh = shapes()
    for i in range(G.N_ROCKS):
        assert sh[i][0][0] == sh[i][0][-1]
    tips = [max(sh[G.ID_HULL + r][0], key=lambda p: p[0] ** 2 + p[1] ** 2) for r in range(G.STEPS)]
    import math
    ang = [math.degrees(math.atan2(y, x)) for x, y in tips]
    assert all(abs(a - r * G.STEP_DEG) < 3 for r, a in enumerate(ang))


def test_inc_text_defines_match_c_use():
    text, n = G.inc_text(shapes(), "fallback")
    for name in ("AWTO_AST_FROM_ROM", "AWTO_AST_SH_ROCK0", "AWTO_AST_SH_SAUCER", "AWTO_AST_SH_HULL", "AWTO_AST_SH_FLAME", "AWTO_AST_SH_DIGIT"):
        assert name in text and name in C_SRC
    assert "#define AWTO_AST_FROM_ROM 0" in text and f"#define AWTO_AST_DATA_BYTES {n}" in text


def test_data_bank_is_the_banks_of_the_readers_in_c():
    banks = set(re.findall(r"#pragma place bank\((\d+)\)", C_SRC))
    assert banks == {str(G.CODE_BANK)}


def test_no_rom_falls_back_and_include_is_ignored_not_tracked(tmp_path):
    out = tmp_path / "a.inc"
    r = subprocess.run([sys.executable, str(ROOT / "scripts/gen_asteroids.py"), "--out", str(out), "--zip", str(tmp_path / "none.zip")], capture_output=True, text=True, check=False)
    assert r.returncode == 0 and "fallback" in r.stdout
    assert "#define AWTO_AST_FROM_ROM 0" in out.read_text()
    assert subprocess.run(["git", "check-ignore", "-q", "fw/test/asteroids_data.inc"], cwd=ROOT, check=False).returncode == 0
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=False).stdout.split("\n")
    assert "fw/test/asteroids_data.inc" not in tracked


@needs_rom
def test_rom_shapes_in_range_and_flame_hangs_from_the_hull():
    sh = shapes(fallback=False)
    G.encode(sh)
    assert all(sh[i][0][0] == sh[i][0][-1] for i in range(G.N_ROCKS))
    for r in range(G.STEPS):
        hull_end = sh[G.ID_HULL + r][-1][-1]
        assert any(abs(p[0] - hull_end[0]) + abs(p[1] - hull_end[1]) <= 1 for pl in sh[G.ID_FLAME + r] for p in pl)
