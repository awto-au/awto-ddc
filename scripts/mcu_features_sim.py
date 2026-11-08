#!/usr/bin/env python3
"""Assemble and simulate the optional CPU probe. No physical hardware operations.

Uses only sdas8051/sdld/ucsim_51 from --tools (default AWTO_SDCC_BIN).
No vendor SDK or firmware compiler is needed; generated IHX is a SIMULATION FIXTURE,
not a monitor image. Never flash it. Assertions compare complete register-bank and
SFR snapshots, both buffer canaries, and positive/negative feature observations.
"""
import argparse
import os
from pathlib import Path
import re
import subprocess

from mcu_features import decode

ROOT = Path(__file__).resolve().parent.parent
PRESERVED = (0x81, 0x82, 0x83, 0x84, 0x85, 0x86, 0x8E, 0xA8, 0xD0, 0xE0, 0xF0)


def run(command, **kwargs):
    proc = subprocess.run([str(x) for x in command], text=True, capture_output=True,
                          timeout=20, **kwargs)
    if proc.returncode:
        raise RuntimeError(f"{command[0]} failed:\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout + proc.stderr


def wrapper(address, bank, enabled, stretch):
    # Initialise before snapshotting; parity and CPU-specific reserved bits are
    # compared with their actual entry values, not assumed reset values.
    return f""".module feature_probe_fixture
.globl _AwtoMcuFeatures
.area HOME (ABS,CODE)
.org 0
ljmp 0x100
.org 0x100
mov 0xa8,#0
mov 0x81,#0x80
mov 0x86,#0
mov 0x84,#0x72
mov 0x85,#0x9d
mov 0x8e,#{stretch}
mov dptr,#{address}
mov 0xf0,#0xb9
mov 0xd0,#{0xC4 | bank << 3}
mov a,#0x6b
mov 0xa8,#{0x80 if enabled else 0}
ljmp 0x200
.org 0x200
lcall _AwtoMcuFeatures
ljmp 0x300
.org 0x300
sjmp .
"""


def dump_rows(output):
    """Collect each dump occurrence without confusing echoed command lines."""
    rows = {}
    for line in output.splitlines():
        m = re.match(r"^\s*0x([0-9a-fA-F]+)\s+((?:[0-9a-fA-F]{2}(?:\s+|$))+)", line)
        if m:
            start = int(m[1], 16)
            values = bytes.fromhex(m[2])
            for off, value in enumerate(values):
                rows.setdefault(start + off, []).append(value)
    return rows


def one(tools, work, cpu, address, bank, enabled, stretch, *, probe=None, expected_passed=None):
    work.mkdir(parents=True, exist_ok=True)
    fixture = work / "fixture.asm"
    fixture.write_text(wrapper(address, bank, enabled, stretch))
    probe = probe or ROOT / "fw/sdcc/mcu_features.asm"
    for src, obj in ((fixture, work / "fixture.rel"), (probe, work / "probe.rel")):
        run([tools / "sdas8051", "-plosgff", "-o", obj, src])
    image = work / "fixture.ihx"
    run([tools / "sdld", "-n", "-i", "-m", "-b", "CSEG=0x0400", image,
         work / "fixture.rel", work / "probe.rel"])
    commands = (
        "fill iram 0 0x7f 0xa5\n"
        + "".join(f"fill iram {8 * b} {8 * b + 7} {0x31 + b * 17}\n" for b in range(4))
        +
        f"fill xram {address - 1} {address + 16} 0xcc\n"
        "break 0x200\nbreak 0x300\nstep 2000\n"
        "dump /h sfr 0x80 0xff 16\ndump /h iram 0 0x7f 16\n"
        "step 10000\n"
        "dump /h sfr 0x80 0xff 16\ndump /h iram 0 0x7f 16\n"
        f"dump /h xram {address - 1} {address + 16} 16\nquit\n"
    )
    command_file = work / "commands.txt"
    command_file.write_text(commands)
    log = run([tools / "ucsim_51", "-q", "-t", cpu, "-c", "-", image], input=commands)
    (work / "sim.log").write_text(log)
    rows = dump_rows(log)
    for reg in PRESERVED:
        observed = rows.get(reg, [])
        if len(observed) != 2 or observed[0] != observed[1]:
            raise AssertionError(f"SFR 0x{reg:02x} not preserved: {observed}")
    for reg in range(128):
        observed = rows.get(reg, [])
        expected = 0x31 + (reg // 8) * 17 if reg < 32 else 0xA5
        if len(observed) != 2 or observed != [expected] * 2:
            raise AssertionError(f"IRAM 0x{reg:02x} not preserved: {observed}")
    if rows.get(address - 1) != [0xCC] or rows.get(address + 16) != [0xCC]:
        raise AssertionError("output buffer canary overwritten")
    record = bytes(rows[address + i][0] for i in range(16))
    (work / "record.bin").write_bytes(record)
    report = decode(record)
    if report["snapshots"]["record_address"] != address:
        raise AssertionError("wrong record address")
    if report["snapshots"]["movx_stretch_setting"] != stretch:
        raise AssertionError("wrong CKCON snapshot")
    if expected_passed is None:
        expected_passed = 15 if cpu == "DS320" else 0
    attempted = 15 if cpu == "DS320" else 1
    expected = ["not-tested" if not attempted & (1 << i)
                else "pass" if expected_passed & (1 << i) else "fail" for i in range(4)]
    if list(report["checks"].values()) != expected:
        raise AssertionError(f"{cpu}: {report['checks']}")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tools", type=Path, default=Path(os.environ.get(
        "AWTO_SDCC_BIN", str(Path.home() / "opt/awto-sdcc/bin"))))
    parser.add_argument("--work", type=Path, default=ROOT / "tmp/mcu-features")
    args = parser.parse_args(argv)
    count = 0
    for cpu in ("DS320", "52"):
        for bank in range(4):
            for enabled in (False, True):
                for address in (0xD700, 0xD7F8):
                    name = f"{cpu}-bank{bank}-ea{int(enabled)}-{address:x}"
                    one(args.tools, args.work / name, cpu, address, bank, enabled, 5)
                    count += 1
    print(f"{count} simulator cases passed (two-pointer positive and one-pointer negative controls)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
