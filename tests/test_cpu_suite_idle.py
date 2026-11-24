"""CPU suite image: no host request for AWTO_CPU_IDLE_MS = the watchdog resets the chip and the mailbox loop comes up again (sim, 87.7 MHz image)."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

IDLE_S = 30.0
T2_OFF = 0x16               # diag block: usT2Isr (Timer2 ISR count = ms), zeroed by AwtoDiagInit at every boot


@pytest.mark.xfail(run=False, reason="awto-ddc#340: the cpu-suite image does not build (XDATA)")
def test_idle_watchdog_reset(fw_cpu_suite):
    IMG = fw_cpu_suite(87).bin
    import cpu_suite as C
    dev = C.Sim(IMG, IMG.with_suffix(".map"), "cpusidle", C.CLOCKS[87])
    try:
        diag = dev.m.addr("isr_g_stAwtoDiag")
        last, resets, t_reset = 0, 0, None
        for _ in range(4000):
            dev.m.run(1_000_000)
            t2 = int.from_bytes(dev.m.rd(diag + T2_OFF, 2), "big")
            if t2 < last - 1000:
                resets, t_reset = resets + 1, last
                break
            last = t2
        assert resets == 1, "no watchdog reset while the host was idle"
        assert IDLE_S * 1000 <= t_reset + 1 and t_reset < (IDLE_S + 2) * 1000, f"reset at {t_reset} ms uptime"
        dev.m.run(10_000_000)                            # the suite loop restarts (ready byte is kept by the warm reset: wait out the boot)
        r = C.run_one(dev, C.BY_NAME["T_RELOAD"], C.Run())
        assert r["done"] and r["fwpass"] == 1
    finally:
        dev.close()
