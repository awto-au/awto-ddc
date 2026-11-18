"""Front-key ADC bands: the Dahua firmware's table next to ours (fw/awto/inputs.tsv key0 / key1 rows), and the edge values to test.

Dahua firmware key_scan_adc (bank 6 CODE:3944, compares at 39e9-3a60, docs/reversing/realtek-rtd/buttons.md): raw byte R, band lo <= R < hi.
Used by tests/test_key_bands.py (table equality, disjoint, edges) and scripts/key_sim_test.py (decode of every edge value in the sim).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

IDLE = 0xF8                                  # regdb ADC_Ax_CONVERT_RESULT reset; live on units 1 / 2 (docs/live-register-scan.md)
CODE_STEP = 8                                # 5-bit result in [7:3]: raw values are multiples of 8
DAHUA = {                                    # key -> (ladder, lo, hi)
    "MENU": ("A0", 0xC0, 0xE0), "UP": ("A0", 0x28, 0x48), "AUTO": ("A0", 0x70, 0x90),
    "DOWN": ("A1", 0x28, 0x48), "SOURCE": ("A1", 0x68, 0x88),
}
KM = {"POWER": 0x01, "AUTO": 0x02, "UP": 0x04, "DOWN": 0x08, "MENU": 0x10, "SOURCE": 0x20}    # RL6449_Project.h AWTO_KM_*


def ours() -> dict:
    """key -> (ladder, lo, hi) from fw/awto/inputs.tsv (the firmware's one table)."""
    import rtd_keywatch as W
    return {n: ("A0" if reg == 0xFF09 else "A1", lo, hi) for _, reg, lo, hi, n in W.load_bands()}


def keys_for(table: dict, a0: int, a1: int) -> set:
    """keys whose band holds the raw value of its ladder (several only if the bands overlap)."""
    return {k for k, (lad, lo, hi) in table.items() if lo <= (a0 if lad == "A0" else a1) < hi}


def edge_values(table: dict) -> list:
    """(ladder, value) cases: every 5-bit code (0, 8, .. 248), each band's lo - 1 / lo / hi - 1 / hi, 0xFF (#214 edge values)."""
    out = {("A0", v) for v in range(0, 256, CODE_STEP)} | {("A1", v) for v in range(0, 256, CODE_STEP)}
    for lad, lo, hi in table.values():
        out |= {(lad, lo - 1), (lad, lo), (lad, hi - 1), (lad, hi)}
    out |= {("A0", 0xFF), ("A1", 0xFF)}
    return sorted(out)
