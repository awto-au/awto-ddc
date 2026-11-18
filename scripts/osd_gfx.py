"""Shared helpers of the OSD generators (gen_pacman_classic, gen_scope2, gen_flash_screen, gen_asteroids): glyph packer, content dedup, array emit, log, repo root.

Glyph stream: a 12 px wide tile, two rows per 24-bit word, pixel p of a word = bit 23 - p, bytes low first (the OSD data port order). Docs: docs/saver-library.md
Fonts stay in their generators (the 5 x 7 glyph shapes differ per screen: '5', '6', '9', 'C', 'G').
"""
import os
import subprocess
from pathlib import Path

import isostamp

ROWS_PER_WORD = 2
WORD_BYTES = 3


def repo_root() -> Path:
    """$AWTO_DDC_REPO, else git toplevel, else file-relative."""
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).resolve().parent, capture_output=True, text=True)
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else Path(__file__).resolve().parents[1]


def logger(path: Path):
    """say(text): print + append to path with an ISO timestamp."""
    def say(s: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = f"{isostamp.now()} {s}"
        with path.open("a") as f:
            f.write(line + "\n")
        print(line, flush=True)
    return say


def pack_rows(rows, sel=lambda v: v & 1) -> bytes:
    """rows: lists of pixel values (one list per tile row) -> the glyph stream of one plane; sel picks the plane bit of a value."""
    out = bytearray()
    for y in range(0, len(rows), ROWS_PER_WORD):
        n = 0
        for row in rows[y:y + ROWS_PER_WORD]:
            for v in row:
                n = n * 2 + sel(v)
        out += n.to_bytes(WORD_BYTES, "little")
    return bytes(out)


def turned(rows):
    """A tile turned 180 inside itself (Rotate 180, docs/osd-rotation.md)."""
    return [list(r[::-1]) for r in rows[::-1]]


def add_unique(items: list, index: dict, key, data=None) -> int:
    """Id of key in index; appends data (default key) to items when new."""
    if key not in index:
        index[key] = len(items)
        items.append(key if data is None else data)
    return index[key]


def arr(name: str, data: bytes, per: int, bank: int) -> str:
    """C const byte array in a pinned bank."""
    rows = ["    " + ", ".join(f"0x{b:02X}" for b in data[i:i + per]) + "," for i in range(0, len(data), per)]
    return f"#pragma place bank({bank})\nstatic const uint8_t __code {name}[{len(data)}] = {{\n" + "\n".join(rows) + "\n};\n"
