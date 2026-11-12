#!/usr/bin/env python3
"""READ-ONLY 0x35 diag-magic read in every transaction shape; shows which shapes a bus/adapter serves (#28).

usage: i2c_shapes.py <bus>   (a sane result starts 41 44 02 'AD' v2; 6e 6e.. = slave not serving the read)
Reads: the staging writes are 0x01/0x3A/0x3C read commands only. Log: ./tmp/logs/i2c_shapes.log
"""
import sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import i2cbus  # noqa: E402

A, BASE = 0x35, 0xF6D0          # BASE = g_stAwtoDiag (docs/diag-block.md)


def main() -> int:
    root = i2cbus.ROOT
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (root / "tmp/logs/i2c_shapes.log").open("a")
    b = i2cbus.Bus(int(sys.argv[1]))

    def show(name, f):
        try:
            r = " ".join(f"{x:02x}" for x in f())
        except OSError as e:
            r = f"ERR {e}"
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} bus {b.bus} ({i2cbus.adapter_name(b.bus)}) {name}: {r}"
        print(line); log.write(line + "\n")

    def stage():
        b.write(A, 0x01, bytes([BASE >> 8])); b.write(A, 0x3A, bytes([BASE & 0xFF]))
    stage(); show("rdwr W08+R4 (repeated start on i915, STOP on NVIDIA)", lambda: b.ops(A, [b"\x08", 4])[0])
    stage(); b.raw_write(A, b"\x08"); show("write(08) then read(4)", lambda: b.raw_read(A, 4))
    stage(); show("rdwr read only R4", lambda: b.ops(A, [4])[0])
    stage(); show("smbus byte data cmd 08", lambda: b.smbus_read(A, 2, 8)[:1])
    stage(); show("smbus i2c-block cmd 08 n=4", lambda: b.smbus_read(A, 8, 8, 4))
    b.write(A, 0x3C, bytes([BASE & 0xFF, BASE >> 8, 4, 0]))
    show("0x3C block len 4, rdwr W08+R5", lambda: b.ops(A, [b"\x08", 5])[0])
    b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
