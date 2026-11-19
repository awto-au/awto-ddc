"""mcs51_core PCON.IDL: an IRQ accepted right after the PCON write wakes the CPU at once (no idle wait for a second IRQ).

Bug: the idle fast-forward ran anyway with the ISR just entered and a priority-1 level in service, so it waited 2^26 clk for an
IRQ that cannot preempt; the hardware watchdog model then reset the chip (87 / 175 MHz clock variants, awto-ddc gates).
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

ISR_COUNT = 0x30
MARK = 0x31
IDLE_LIMIT_CLK = 1 << 20        # far below the core's 2^26 clk no-IRQ stop; a woken CPU idles at most one timer period
RELOADS = (200, 250, 300)       # Timer2 counts per period, one per clock variant of the same code path


def _image(body: bytes, reload: int) -> bytes:
    rc = 0x10000 - reload
    isr = bytes([0xC2, 0xCF, 0x05, ISR_COUNT, 0x32])                  # clr TF2; inc count; reti
    init = bytes([0x75, 0xB8, 0x20,                                    # IP = PT2 (priority 1)
                  0x75, 0xCB, rc >> 8, 0x75, 0xCA, rc & 255, 0x75, 0xCD, rc >> 8, 0x75, 0xCC, rc & 255,
                  0x75, 0xC8, 0x84,                                    # T2CON = TR2 | TF2 (overflow already pending)
                  0x75, 0xA8, 0x20,                                    # IE = ET2, EA still off
                  0xD2, 0xAF])                                         # setb EA: no IRQ before the next instruction
    code = bytearray(0x400)
    code[0:3] = bytes([0x02, 0x01, 0x00])
    code[0x2B:0x2E] = bytes([0x02, 0x02, 0x00])
    code[0x100:0x100 + len(init) + len(body)] = init + body
    code[0x200:0x200 + len(isr)] = isr
    return bytes(code)


def _core(img: bytes):
    import fastmachine as F
    core = F.Core(img)
    core.set_dw(json.loads((ROOT / "scripts/dw8051_model.json").read_text()))
    return core


@pytest.mark.parametrize("reload", RELOADS)
def test_irq_at_the_pcon_write_does_not_idle(reload):
    core = _core(_image(bytes([0x43, 0x87, 0x01, 0x75, MARK, 0x01, 0x80, 0xFE]), reload))     # orl PCON,#1; mov MARK,#1; sjmp $
    try:
        core.run(400)
        assert core.iram[MARK] == 1 and core.iram[ISR_COUNT] >= 1
        assert core.p.idle_clk < IDLE_LIMIT_CLK and core.p.pc != 0
    finally:
        core.free()


@pytest.mark.parametrize("chunk", (1, 7, 1000, 100_000))
@pytest.mark.parametrize("reload", RELOADS)
def test_idle_loop_keeps_taking_irqs(reload, chunk):
    delay = bytes([0xAF, 0x32, 0x8F, 0x33, 0xD5, 0x33, 0xFD,           # r7 = sweep; 0x33 = r7; djnz 0x33,$ (delay = alignment sweep)
                   0x05, 0x32, 0x43, 0x87, 0x01, 0x80, 0xF2])        # sweep++; orl PCON,#1; loop
    core = _core(_image(delay, reload))
    try:
        for _ in range(3_000_000 // chunk):
            core.run(chunk)
        want = core.p.clk // (reload * 12)                              # Timer2 slow clock: 12 clk per count
        assert core.p.pc != 0 and abs(core.p.nirq - want) <= want // 50, f"{core.p.nirq} IRQs, Timer2 gives {want}"
    finally:
        core.free()
