"""Offline record checks and execution of the actual assembly in uCsim."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mcu_features as M
import mcu_features_sim as S


def record():
    return bytearray(b"MF\x01\x10\x0f\x0f\x00\x05\x00\xd7\x3c\xa7\x00\x00\x00\xa5")


def test_report_distinguishes_measured_checks_from_unknown_features():
    report = M.decode(record())
    assert list(report["checks"].values()) == ["pass"] * 4
    assert report["snapshots"]["movx_stretch_setting"] == 5
    assert report["snapshots"]["record_address"] == 0xD700
    assert {"internal_ram_size", "extended_arithmetic_unit", "pointer_auto_toggle"} <= set(report["untested"])


def test_no_second_pointer_skips_dependent_checks():
    data = record()
    data[4:6] = b"\x01\x00"
    data[10:12] = b"\x00\x00"
    report = M.decode(data)
    assert list(report["checks"].values()) == ["fail"] + ["not-tested"] * 3


@pytest.mark.parametrize("length", range(16))
def test_truncated_capture_rejected(length):
    with pytest.raises(ValueError, match="exactly 16 bytes"):
        M.decode(record()[:length])


@pytest.mark.parametrize("offset,value", [
    (0, 0), (2, 2), (3, 15), (4, 0x80), (4, 1), (5, 0x80), (5, 14),
    (6, 1), (10, 0), (11, 0), (12, 1), (13, 1), (14, 1), (15, 0),
])
def test_malformed_or_uncommitted_capture_rejected(offset, value):
    data = record()
    data[offset] = value
    with pytest.raises(ValueError):
        M.decode(data)


def test_cli_only_reads_capture(tmp_path):
    sample = tmp_path / "record.bin"
    sample.write_bytes(record())
    proc = subprocess.run([sys.executable, ROOT / "scripts/mcu_features.py", sample, "--json"],
                          capture_output=True, text=True, timeout=5)
    assert proc.returncode == 0
    assert '"pointer_auto_toggle"' in proc.stdout
    data = record()
    data[5] = 7
    sample.write_bytes(data)
    proc = subprocess.run([sys.executable, ROOT / "scripts/mcu_features.py", sample],
                          capture_output=True, text=True, timeout=5)
    assert proc.returncode == 1
    assert "fail       selected_pointer_xdata_read_write" in proc.stdout


def test_dump_parser_does_not_parse_echo_or_instruction_rows():
    log = "dump /h xram 0xd700 0xd70f 16\n0x0200 F? 12 04 00 LCALL 0x0400\n0xd700 4d 46 MF\n"
    assert S.dump_rows(log) == {0xD700: [0x4D], 0xD701: [0x46]}


@pytest.fixture
def tools():
    value = os.environ.get("AWTO_MCU_TEST_TOOLS") or os.environ.get("AWTO_SDCC_BIN")
    directory = Path(value) if value else Path.home() / "opt/awto-sdcc/bin"
    if not all((directory / name).is_file() for name in ("sdas8051", "sdld", "ucsim_51")):
        pytest.skip("set AWTO_MCU_TEST_TOOLS to assembler/linker/uCsim directory")
    return directory


@pytest.mark.parametrize("cpu", ["DS320", "52"])
@pytest.mark.parametrize("bank", range(4))
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("address,stretch", [(0xD700, 0), (0xD7F8, 7)])
def test_cpu_probe_restores_state_and_bounds_writes(tools, tmp_path, cpu, bank, enabled, address, stretch):
    S.one(tools, tmp_path, cpu, address, bank, enabled, stretch)


@pytest.mark.parametrize("before,after,passed", [
    ("inc  dptr                 ; carry must affect only DPTR1", "nop", 13),
    ("mov  r1,a", "mov  r1,#0", 11),
    ("mov  a,#0x96", "mov  a,#0x69", 7),
])
def test_faults_fail_the_relevant_check(tools, tmp_path, before, after, passed):
    source = (ROOT / "fw/sdcc/mcu_features.asm").read_text()
    assert before in source
    mutant = tmp_path / "mutant.asm"
    mutant.write_text(source.replace(before, after, 1))
    S.one(tools, tmp_path / "run", "DS320", 0xD7F8, 3, True, 5,
          probe=mutant, expected_passed=passed)


def test_harness_detects_failed_register_restoration(tools, tmp_path):
    source = (ROOT / "fw/sdcc/mcu_features.asm").read_text()
    mutant = tmp_path / "mutant.asm"
    # Discard saved DPH1 without restoring it; leave stack balanced.
    mutant.write_text(source.replace("pop  0x85", "dec  0x81", 1))
    with pytest.raises(AssertionError, match="SFR 0x85 not preserved"):
        S.one(tools, tmp_path / "run", "DS320", 0xD700, 0, False, 5, probe=mutant)


def test_missing_completion_rejected_after_execution(tools, tmp_path):
    source = (ROOT / "fw/sdcc/mcu_features.asm").read_text()
    mutant = tmp_path / "mutant.asm"
    mutant.write_text(source.replace("mov  a,#0xa5", "mov  a,#0", 1))
    with pytest.raises(ValueError, match="incomplete record"):
        S.one(tools, tmp_path / "run", "DS320", 0xD700, 0, False, 5, probe=mutant)
