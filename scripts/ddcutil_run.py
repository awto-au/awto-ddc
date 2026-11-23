#!/usr/bin/env python3
"""ddcutil with a bounded retry: one place for what alert.py, flash_screen.py and dev.py need (#232 review: the wrapper was copy-pasted).

Library: ddc(bus, *args, tries=DDC_TRIES) -> CompletedProcess | None (None = every try failed or ddcutil missing).
  DDC/CI is back ~0.1 s after the debug link goes off or a unit resets (dev.py log "DDC/CI 0x37 back after 52..102 ms"): 4 tries x 0.5 s = 2 s at most.
  One call is limited to DDC_LIMIT_S (ddcutil's own retry budget on a busy unit is ~10 s); expiry = None, the caller goes on.
Also: paged settings write for any registry row, set_row(bus, name, value) -> bool (VCP 0xE0 = row id, 0xE1 = option index; settings_table.py).
"""
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

DDC_TRIES = 4
DDC_RETRY_S = 0.5
DDC_LIMIT_S = 20
VCP_PAGED_ID, VCP_PAGED_VAL = 0xE0, 0xE1


def ddc(bus: int, *args: str, tries: int = DDC_TRIES):
    for k in range(tries):
        try:
            r = subprocess.run(["ddcutil", "--bus", str(bus), *args], capture_output=True, text=True, timeout=DDC_LIMIT_S, check=False)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if r.returncode == 0:
            return r
        if k + 1 < tries:
            time.sleep(DDC_RETRY_S)
    return None


def set_row(bus: int, name: str, value: str) -> bool:
    """Set a registry row through the paged pair; value = option label (enum) or number."""
    import settings_table as T
    row = T.BY_NAME[name]
    opts = row.get("options") or []
    idx = opts.index(value) if value in opts else int(value)
    ids = row.get("option_vcp") or list(range(len(opts)))
    raw = ids[idx] if opts else idx
    return (ddc(bus, "setvcp", f"{VCP_PAGED_ID:02X}", str(row["id"])) is not None
            and ddc(bus, "setvcp", f"{VCP_PAGED_VAL:02X}", str(raw)) is not None)
