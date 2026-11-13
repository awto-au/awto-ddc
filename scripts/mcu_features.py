#!/usr/bin/env python3
"""Decode an already captured MCU feature record. Offline only; no monitor access."""
import argparse
import json
from pathlib import Path

SIZE = 16
CHECKS = (
    "independent_data_pointers",
    "selected_pointer_increment_and_carry",
    "selected_pointer_code_read",
    "selected_pointer_xdata_read_write",
)
UNTESTED = (
    "pointer_auto_toggle", "pointer_auto_increment", "pointer_decrement",
    "extended_arithmetic_unit", "internal_ram_size", "xram_extent",
    "instruction_timing", "cache_timing", "uart_count", "usb_controller",
)


def decode(record):
    if len(record) != SIZE:
        raise ValueError(f"expected exactly {SIZE} bytes, got {len(record)}")
    if record[:4] != b"MF\x01\x10":
        raise ValueError("wrong magic, version or record size")
    if record[15] != 0xA5:
        raise ValueError("incomplete record (completion marker missing)")
    attempted, passed = record[4:6]
    if attempted not in (1, 15) or passed & ~attempted:
        raise ValueError("invalid attempted/passed masks")
    if attempted == 1 and passed or attempted == 15 and not passed & 1:
        raise ValueError("dependent tests require independent data pointers")
    if record[6] & 1:
        raise ValueError("entry DPS.0 must be zero")
    if any(record[12:15]):
        raise ValueError("reserved record bytes must be zero")
    if passed & 4 and record[10:12] != b"\x3c\xa7":
        raise ValueError("MOVC observations disagree with passed mask")
    return {
        "version": 1,
        "checks": {name: "not-tested" if not attempted & (1 << i)
                   else "pass" if passed & (1 << i) else "fail"
                   for i, name in enumerate(CHECKS)},
        "snapshots": {"dps": record[6], "ckcon": record[7],
                      "movx_stretch_setting": record[7] & 7,
                      "record_address": record[8] | record[9] << 8,
                      "movc_bytes": list(record[10:12]) if attempted & 4 else None},
        "untested": list(UNTESTED),
        "scope": "CPU behaviour in the execution environment; simulation is not hardware evidence",
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("record", type=Path, help="16-byte binary capture")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = decode(args.record.read_bytes())
    except (OSError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for name, status in report["checks"].items():
            print(f"{status:10} {name}")
        snap = report["snapshots"]
        print(f"DPS=0x{snap['dps']:02x} CKCON=0x{snap['ckcon']:02x} "
              f"MOVX stretch setting={snap['movx_stretch_setting']} (timing not measured)")
        print("Untested: " + ", ".join(report["untested"]))
    return 1 if "fail" in report["checks"].values() else 0


if __name__ == "__main__":
    raise SystemExit(main())
