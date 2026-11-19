"""Mutation tests of the sped-up firmware gates (deadport, inputrate): each injected fault must make the gate FAIL, the clean run PASSES.

Proves a speed-up did not weaken the check (awto-ddc gate speed task, Dan 2026-11-19). Offline; --slow (each run 10..25 s CPU).
Image: $AWTO_TEST_IMAGE (stem, no suffix) or the newest tmp/fw/*-be.bin; skipped when absent.
Faults: sim input (a cable on D2, a window too short, a pulse shorter than the worst read gap) and firmware (the GPIO scan RET'd).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ENV = {**os.environ, "AWTO_SIM_CORE": "fast"}
STALL_S = 300      # backstop only: 3x the measured cold worst case of the slowest run here


def _image():
    e = os.environ.get("AWTO_TEST_IMAGE")
    if e:
        return Path(e)
    c = sorted((ROOT / "tmp/fw").glob("*-be.bin"), key=lambda p: p.stat().st_mtime)
    return c[-1].with_suffix("") if c else None


IMG = _image()
pytestmark = [pytest.mark.slow, pytest.mark.skipif(IMG is None or not IMG.with_suffix(".map").exists(), reason="no image in tmp/fw")]


def gate(script, binp, mapp, *args):
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / script), str(binp), str(mapp), *args], capture_output=True, text=True,
                       env=ENV, timeout=STALL_S)
    return r.returncode, r.stdout + r.stderr


def patched(tmp_path, fn):
    """copy of the image with `fn` returning at once (RET at its entry)"""
    m = re.search(rf"^C:\s+([0-9A-F]{{8}})\s+_{fn}\b", IMG.with_suffix(".map").read_text(errors="replace"), re.MULTILINE)
    assert m, f"{fn} not in the map"
    img = bytearray(IMG.with_suffix(".bin").read_bytes())
    img[int(m.group(1), 16)] = 0x22
    b = tmp_path / (IMG.name + "-mut-be.bin")
    b.write_bytes(img)
    return b


def test_deadport_clean_passes():
    rc, out = gate("deadport_sim.py", IMG.with_suffix(".bin"), IMG.with_suffix(".map"))
    assert rc == 0, out[-800:]


def test_deadport_fails_when_d2_has_a_cable():
    rc, out = gate("deadport_sim.py", IMG.with_suffix(".bin"), IMG.with_suffix(".map"), "--d2-cabled", "--case", "vcp")
    assert rc != 0 and "vcp: FAIL" in out, out[-800:]


def test_deadport_fails_when_the_window_is_too_short():
    rc, out = gate("deadport_sim.py", IMG.with_suffix(".bin"), IMG.with_suffix(".map"), "--case", "cmd", "--secs", "1")
    assert rc != 0 and "cmd: FAIL" in out, out[-800:]


def test_inputrate_clean_passes():
    rc, out = gate("input_rate_sim.py", IMG.with_suffix(".bin"), IMG.with_suffix(".map"))
    assert rc == 0 and "ALL PASS" in out, out[-800:]


def test_inputrate_fails_with_a_pulse_shorter_than_the_worst_gap():
    rc, out = gate("input_rate_sim.py", IMG.with_suffix(".bin"), IMG.with_suffix(".map"), "--margin", "0.3")
    assert rc != 0 and "FAIL" in out, out[-800:]


def test_inputrate_fails_when_the_gpio_scan_never_runs(tmp_path):
    b = patched(tmp_path, "AwtoGpioPoll")
    rc, out = gate("input_rate_sim.py", b, IMG.with_suffix(".map"))
    assert rc != 0 and "FAIL" in out, out[-800:]


# ---- NORMAL-tier minimal variants (fw_gates.gates names): a function RET'd in the image must fail the variant; the clean image passes
sys.path.insert(0, str(ROOT / "scripts"))
import fw_gates as G

NORMAL_FAULTS = [("wake", "AwtoPsWakeFire"), ("wdt", "AwtoWdtHang"), ("crash", "AwtoWdtHang"), ("conwrap", "AwtoConLogSync"),
                 ("monitor", "AwtoMonSample"), ("keys", "AwtoSourceKey"), ("menu", "menu_open")]


def normal_cmd(name, binp):
    return [str(x) for x in G.gates(binp, IMG.with_suffix(".map"), None, ROOT)[name]]


def run_normal(name, binp):
    return subprocess.run(normal_cmd(name, binp), capture_output=True, text=True, env={**ENV, "PYTHONHASHSEED": "0"}, timeout=STALL_S, cwd=ROOT)


@pytest.mark.parametrize("name,fn", NORMAL_FAULTS)
def test_normal_variant_fails_with_a_dead_function(tmp_path, name, fn):
    r = run_normal(name, patched(tmp_path, fn))
    assert r.returncode != 0, f"{name} with {fn} RET'd still passes:\n" + (r.stdout + r.stderr)[-600:]


@pytest.mark.parametrize("name", ["wake", "wdt", "crash", "conwrap", "monitor", "keys", "menu"])
def test_normal_variant_passes_clean(name):
    r = run_normal(name, IMG.with_suffix(".bin"))
    assert r.returncode == 0, (r.stdout + r.stderr)[-600:]
