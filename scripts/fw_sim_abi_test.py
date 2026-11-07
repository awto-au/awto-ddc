#!/usr/bin/env python3
"""Offline tests for fw_sim's ABI handling (SDCC levels 0-2 vs --sdcccall 3 Keil registers, awto-sdcc#7); no ucsim."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as F  # noqa: E402

OLD_SW = bytes([0x8D, 0x82, 0x8E, 0x83, 0xEC, 0x22])         # old __bs_call_sw: mov dpl,r5; mov dph,r6; mov a,r4; ret
KEIL_SW = bytes([0x22, 0x74, 0x00])                           # Keil __bs_call_sw: ret (then __bs_rtab)
STOP = ("Stop at 0x1234: (4) Breakpoint\n R0 R1 R2 R3 R4 R5 R6 R7\n 00 11 22 33 44 55 66 77\n"
        "ACC= 0x99 B= 0x0b DPTR= 0xabcd\n")


class FakeMachine(F.Machine):
    def __init__(self, keil):                                 # no ucsim: only the state _do_stub uses
        self.keil, self.ret_pc, self._q, self.stub_hits = keil, 0x2a0, [], {}
        self.stubs = {}

    def rd(self, a, n=1, space="xram"):
        return bytes(n)

    def flush(self):
        pass


def do(keil, ret):
    m, seen = FakeMachine(keil), {}
    m.stubs[0x1234] = [(None, "f", lambda m_, r: seen.update(r) or ret)]
    m._do_stub(0x1234, STOP)
    return seen, m._q


def main():
    assert F.keil_abi({"__bs_keil": 0x278}) and not F.keil_abi({"__bs_call": 0x278})
    assert F.sw_ret(OLD_SW, 0) == 5 and F.sw_ret(KEIL_SW, 0) == 0
    assert F.stub_size(bytes([0x78, 1, 0x90, 0x12, 0x34, 0x02, 0, 0]), 0) == 8
    assert F.stub_size(bytes([0x78, 1, 0x79, 0x34, 0x7A, 0x12, 0x02, 0, 0]), 0) == 9
    assert F.stub_size(bytes([0x12, 0, 0x50, 0x34, 0x12, 1]), 0) == 6
    r, q = do(False, {"val": 0x0102})
    assert (r["a1"], r["a2"]) == (0xABCD, 0x77), r            # SDCC: arg 1 DPH:DPL, char arg 2 R7
    assert "set memory sfr 0x82 0x2" in q and "set memory sfr 0x83 0x1" in q and "pc 0x2a0" in q, q
    r, q = do(True, {"val": 0x0102})
    assert (r["a1"], r["a2"]) == (0x6677, 0x55), r            # Keil: arg 1 R6:R7, char arg 2 R5
    assert "set memory iram 0x7 0x2" in q and "set memory iram 0x6 0x1" in q and not any("sfr 0x82" in c for c in q), q
    _, q = do(True, {"carry": 1})
    assert "set bit 0xd7 1" in q, q
    _, q = do(True, None)
    assert q == [], q                                         # watch only: no return injected
    print("PASS fw_sim_abi_test")
    return 0


if __name__ == "__main__":
    sys.exit(main())
