"""OSD manual gates: the committed pictures equal the regenerated ones; every relative link and image in docs/osd resolves;
every picture on disk is linked from the manual."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs/osd"


def test_pictures_match_the_model():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/osd_manual.py"), "--check"], capture_output=True, text=True, cwd=ROOT, check=False)
    assert r.returncode == 0, r.stdout + r.stderr


def test_links_resolve():
    bad = []
    for md in sorted(DOCS.glob("*.md")):
        for m in re.finditer(r"\]\(([^)#\s]+)(#[^)]*)?\)", md.read_text()):
            tgt = m.group(1)
            if "://" in tgt or tgt.startswith("mailto:"):
                continue
            if not (md.parent / tgt).resolve().exists():
                bad.append(f"{md.name}: {tgt}")
    assert not bad, bad


def test_every_picture_is_linked():
    text = "".join(p.read_text() for p in DOCS.glob("*.md"))
    missing = [p.name for p in (DOCS / "img").glob("*.png") if f"img/{p.name}" not in text]
    assert not missing, missing
