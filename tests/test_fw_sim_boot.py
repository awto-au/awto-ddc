"""fw_sim.py --boot-check / --isr-check on real images (#11, #38). Offline; image: fixture fw_image."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(mode, binp, mapp):
    # 120 s = stall backstop, ~10x the ~10 s measured cold run
    return subprocess.run([sys.executable, str(ROOT / "scripts/fw_sim.py"), mode, str(binp), str(mapp)],
                          capture_output=True, text=True, timeout=120, check=False)


def test_good_image_boots_to_main_loop(fw_image):
    GOOD = fw_image.stem
    r = run("--boot-check", GOOD.with_suffix(".bin"), GOOD.with_suffix(".map"))
    assert r.returncode == 0 and any(ln.startswith("PASS") for ln in r.stdout.splitlines()), r.stdout + r.stderr


def test_trap_in_banked_function_fails(tmp_path, fw_image):
    GOOD = fw_image.stem
    img = bytearray(GOOD.with_suffix(".bin").read_bytes())
    m = re.search(r"^C:\s+([0-9A-F]{8})\s+_ScalerDisplayDPTx1VideoStreamOu\b", GOOD.with_suffix(".map").read_text(errors="replace"), re.MULTILINE)
    assert m
    off = int(m.group(1), 16)
    img[off:off + 2] = b"\x80\xfe"                      # SJMP $ at the function entry
    b = tmp_path / "trap-be.bin"
    b.write_bytes(img)
    r = run("--boot-check", b, GOOD.with_suffix(".map"))
    assert r.returncode == 1 and "FAIL" in r.stdout and "ScalerDisplayDPTx1VideoStreamOu" in r.stdout, r.stdout


def test_isr_returns_to_the_interrupted_bank(fw_image):
    GOOD = fw_image.stem
    r = run("--isr-check", GOOD.with_suffix(".bin"), GOOD.with_suffix(".map"))
    assert r.returncode == 0 and "FAIL" not in r.stdout, r.stdout
