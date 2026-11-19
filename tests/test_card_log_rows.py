"""#266 pop-up log rows: sync.tsv ED args are the AWTO_CT_* text ids of console.c."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CT = {"input selector": "INPUT", "information": "INFO", "backlight": "BACKLIGHT", "reset to defaults (key held)": "RESET", "no signal": "NOSIGNAL",
      "no cable": "NOCABLE", "no support": "NOSUPPORT", "auto adjust": "AUTOADJ", "auto colour": "AUTOCOL", "DDC/CI port switch": "DDCCI",
      "power saving": "PSAVE", "panel uniformity": "PANEL", "saving to memory": "SAVING"}


def test_args_match_console_defines():
    src = (ROOT / "fw/osd/console.c").read_text()
    ids = {m.group(1): int(m.group(2)) for m in re.finditer(r"^#define AWTO_CT_(\w+)\s+(\d+)", src, re.MULTILINE)}
    seen = set()
    for ln in (ROOT / "fw/awto/sync.tsv").read_text().splitlines():
        f = ln.split("\t")
        if f[0] == "ED" and f[3].startswith("pop-up opened: "):
            name = f[3][len("pop-up opened: "):-len(" card")]
            assert ids[CT[name]] == int(f[1], 16), name
            seen.add(name)
    assert seen == set(CT)
