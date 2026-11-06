#!/usr/bin/env python3
"""A function that reads stack-passed args via SP/_bp must be common (stub frames shift SP offsets, #11)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sdcc_bank as B  # noqa: E402


def chunk(body):
    c = B.Chunk("CSEG", "_f", ["_f:"] + body, None)
    c.finish()
    return c


def main():
    assert chunk(["\tmov\ta,sp", "\tadd\ta,#0xfc", "\tret"]).stack_args
    assert chunk(["\tmov\tar7,sp", "\tret"]).stack_args
    assert chunk(["\tmov\ta,_bp", "\tret"]).stack_args
    assert not chunk(["\tmov\ta,r7", "\tdec\tsp", "\tret"]).stack_args    # popping own pushes is fine
    assert not chunk(["\tmov\tdptr,#_x", "\tret"]).stack_args
    print("PASS sdcc_bank_stackargs_test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
