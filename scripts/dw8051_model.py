#!/usr/bin/env python3
"""DW8051 timing / SFR model as data (#162 step 1, awto-sdcc#67): scripts/dw8051_model.json.

usage: dw8051_model.py --write | --check
- Source: Synopsys DesignWare DW8051 databook v3.2a (docs: tmp/wdt/prior/DW8051-databook.pdf): table 2-4 (instruction cycles),
  2-5 (MOVX stretch), 2-6 / 2-7 (SFR map, reset values), p. 3-9 (timer rate), p. 3-49 (interrupt latency).
- JSON is the only copy of the tables: fastmachine.py loads it into mcs51_core.c (core_set_dw); an RL6449 ucsim can load the same file.
- Opcode classes below are the databook rows; cycles[op] = instruction cycles (1 cycle = 4 clk). MOVX rows are base + CKCON[2:0].
"""
import json, sys
from pathlib import Path

OUT = Path(__file__).resolve().parent / "dw8051_model.json"


def cycles() -> list[int]:
    c = [0] * 256

    def put(ops, n):
        for o in ops:
            assert c[o] == 0, hex(o)
            c[o] = n
    r = lambda lo, n=8: range(lo, lo + n)
    put([0x00, 0xA5], 1)                                          # NOP, reserved A5 = NOP
    put([o for o in range(256) if o & 0x0F == 0x01], 3)           # AJMP / ACALL addr11
    put([0x02, 0x12, 0x22, 0x32], 4)                              # LJMP LCALL RET RETI
    put([0x80, 0x40, 0x50, 0x60, 0x70, 0x73], 3)                  # SJMP JC JNC JZ JNZ JMP @A+DPTR
    put([0x10, 0x20, 0x30], 4)                                    # JBC JB JNB
    put([0xB4, 0xB5, 0xB6, 0xB7, *r(0xB8)], 4)                    # CJNE x4
    put([*r(0xD8)], 3)                                            # DJNZ Rn
    put([0xD5], 4)                                                # DJNZ direct
    for base in (0x20, 0x30, 0x90):                               # ADD ADDC SUBB: Rn / dir / @Ri / #d
        put([*r(base + 0x08)], 1); put([base + 5], 2); put([base + 6, base + 7], 1); put([base + 4], 2)
    for base in (0x50, 0x40, 0x60):                               # ANL ORL XRL
        put([*r(base + 0x08)], 1); put([base + 5], 2); put([base + 6, base + 7], 1); put([base + 4], 2)
        put([base + 2], 2); put([base + 3], 3)                    # op dir,A / op dir,#data
    put([0x04, 0x14, *r(0x08), *r(0x18), 0x06, 0x07, 0x16, 0x17], 1)    # INC DEC A, Rn, @Ri
    put([0x05, 0x15], 2)                                          # INC DEC direct
    put([0xA3], 3); put([0xA4, 0x84], 5); put([0xD4], 1)          # INC DPTR, MUL, DIV, DA
    put([0xE4, 0xF4, 0xC4, 0x23, 0x33, 0x03, 0x13], 1)            # CLR CPL SWAP RL RLC RR RRC A
    put([*r(0xE8), 0xE6, 0xE7, 0x74, *r(0xF8), 0xF6, 0xF7], 1)    # MOV A,Rn A,@Ri A,#d Rn,A @Ri,A
    put([0xE5, *r(0xA8), *r(0x78), 0xF5, *r(0x88), 0x86, 0x87, 0x76, 0x77, 0xA6, 0xA7], 2)
    put([0x85, 0x75, 0x90, 0x93, 0x83], 3)                        # MOV dir,dir / dir,#d / DPTR,#d / MOVC x2
    put([0xE0, 0xE2, 0xE3, 0xF0, 0xF2, 0xF3], 2)                  # MOVX: base, + CKCON[2:0] at run time
    put([0xC0, 0xD0], 2)                                          # PUSH POP
    put([*r(0xC8), 0xC6, 0xC7, 0xD6, 0xD7], 1); put([0xC5], 2)    # XCH Rn @Ri, XCHD; XCH direct
    put([0xC3, 0xD3, 0xB3], 1)                                    # CLR C SETB C CPL C
    put([0xC2, 0xD2, 0xB2, 0x82, 0xB0, 0x72, 0xA0, 0xA2, 0x92], 2)  # bit rows
    assert all(c), [hex(i) for i, v in enumerate(c) if not v]
    return c


def lengths() -> list[int]:
    """Instruction bytes per opcode (databook table 2-4, Byte column)."""
    n = [1] * 256
    for o in range(256):
        if o & 0x0F == 0x01:                                       # AJMP / ACALL addr11
            n[o] = 2
    for o in (0x02, 0x12, 0x10, 0x20, 0x30, 0xB4, 0xB5, *range(0xB6, 0xC0), 0xD5, 0x43, 0x53, 0x63, 0x75, 0x85, 0x90):
        n[o] = 3
    for o in (0x80, 0x40, 0x50, 0x60, 0x70, 0x24, 0x34, 0x44, 0x54, 0x64, 0x74, 0x94, 0x05, 0x15, 0x25, 0x35, 0x45, 0x55, 0x65, 0x95,
              0xE5, 0xF5, 0xC0, 0xD0, 0xC5, 0x86, 0x87, *range(0x88, 0x90), 0xA6, 0xA7, *range(0xA8, 0xB0), 0x76, 0x77, *range(0x78, 0x80),
              0x42, 0x52, 0x62, 0xC2, 0xD2, 0xB2, 0xA2, 0x92, 0x82, 0xB0, 0x72, 0xA0, *range(0xD8, 0xE0)):
        n[o] = 2
    return n


def model() -> dict:
    return {
        "source": "DW8051 databook v3.2a: tables 2-4, 2-5, 2-6, 2-7; p. 3-9 timer rate; p. 3-49 interrupt latency",
        "clk_per_cycle": 4,
        "cycles": cycles(),
        "movx": {"base_cycles": 2, "extra_from": "CKCON[2:0] (MD2..0): cycles = base + value (table 2-5)"},
        "irq_cycles": 4,
        "irq_note": "accepted interrupt = the LCALL to the vector (databook p. 3-49: 1 detect + 4 LCALL; detect overlaps the last cycle)",
        "timer_clk_div": {"slow": 12, "fast": 4, "ckcon_bits": {"T0M": 3, "T1M": 4, "T2M": 5}},
        "sfr": {"DPL0": "0x82", "DPH0": "0x83", "DPL1": "0x84", "DPH1": "0x85", "DPS": "0x86 (bit0 SEL)", "CKCON": "0x8E"},
        "reset": {"CKCON": "0x01", "DPS": "0x00"},
        "oplen": lengths(),
        "flash_fetch": {
            "note": "code is read from the SPI flash: uncached while FDA0[0] cache_en = 0 (reset state; the SDK enables it in ScalerMcuInitial), "
                    "else through a line cache. Stall = flash clocks x (CPU clk per flash clk = FFE9[3:0] / FFEE[5:2]) minus the base byte cycles.",
            "common_end": 0x5000,
            "line_bytes": 16,
            "line_bytes_source": "regdb 0xFDA2..0xFDAF: cache address registers resolve [7:4] = 16 B",
            "cmd_flash_clk": 40,
            "cmd_source": "fast read 0x0B (SDK ScalerMcu: FF6C[6] fast read mode): 8 opcode + 24 address + 8 dummy clocks, 1 bit per clock",
            "byte_flash_clk": 8,
            "sets": 64, "ways": 2,
            "cache_source": "ASSUMED 2 KB: regdb FDA1 size_div says 'minimum 128x2 cache size' at 1/8; two ways, 16 B lines; real geometry unverified",
        },
    }


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--check"
    text = json.dumps(model(), indent=1) + "\n"
    if mode == "--write":
        OUT.write_text(text)
        print(f"wrote {OUT}")
        return 0
    ok = OUT.exists() and OUT.read_text() == text
    print(f"{'PASS' if ok else 'FAIL'} dw8051_model.json {'current' if ok else 'differs from dw8051_model.py (run --write)'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
