"""Thin adapter over the repo's one VLC codec, scripts/osd_vlc.py (#87)."""
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import osd_vlc as _enc  # noqa: E402
import font_compare as _fc  # noqa: E402  (Variant, SRAM_WORDS)

SRAM_WORDS = _fc.SRAM_WORDS
Variant = _fc.Variant
CHUNK = 24000                                   # blob length field is 16 bit; same split as font_compare.blob_sizes


def vlc_encode(data: bytes) -> bytes:
    return _enc.encode(data)


def vlc_decode(blob: bytes) -> bytes:
    return _enc.decode(blob)
