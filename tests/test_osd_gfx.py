"""scripts/osd_gfx.py: glyph packing and the generated includes staying byte-identical (the generators' --check modes). No hardware."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import osd_gfx as OG  # noqa: E402


def test_pack_rows_word_layout():
    rows = [[1] + [0] * 11, [0] * 11 + [1]] + [[0] * 12] * 16
    out = OG.pack_rows(rows)
    assert len(out) == 27
    assert out[:3] == (1 << 23 | 1).to_bytes(3, "little")      # pixel 0 = bit 23, pixel 23 = bit 0


def test_turned_twice_is_identity():
    rows = [[1 if (x < 3 and y < 5) else 0 for x in range(12)] for y in range(18)]
    assert OG.turned(OG.turned(rows)) == rows
    assert OG.pack_rows(OG.turned(rows)) != OG.pack_rows(rows)


def test_add_unique():
    items, index = [], {}
    assert [OG.add_unique(items, index, k) for k in (b"a", b"b", b"a")] == [0, 1, 0] and items == [b"a", b"b"]


def test_generated_includes_unchanged():
    for g in ("gen_scope2", "gen_flash_screen", "gen_pacman_classic"):
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / f"{g}.py"), "--check"], capture_output=True, text=True)
        assert r.returncode == 0, f"{g}: {r.stdout[-300:]}"
