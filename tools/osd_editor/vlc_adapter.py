"""Thin adapter over the repo's VLC encoder. Swap the import to osd_vlc when #87 lands it (one line)."""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import font_compare as _enc  # noqa: E402  (-> `import osd_vlc as _enc`)

SRAM_WORDS = _enc.SRAM_WORDS
Variant = _enc.Variant
CHUNK = 24000                                   # blob length field is 16 bit; same split as font_compare.blob_sizes


def vlc_encode(data: bytes) -> bytes:
    return _enc.vlc_encode(data)


def vlc_decode(blob: bytes) -> bytes:
    return _enc.vlc_decode(blob)
