"""MCU clock of the RL6449 as the firmware programs it (#162 step 1): f_cpu from the clock registers, no per-phase constants.

- f_cpu = source / FLASH_CLK_DIV / MCU_CLK_DIV   (SDK ScalerMcuFlashClockGroupSetting; regdb 0xFFED / 0xFFEE)
  - source (FFED[1] mcu_clk_sel): 1 = M2PLL, 0 = "crystal domain" (0x0009[3] xtal_clk_sel: 0 external crystal, 1 internal OSC)
  - M2PLL = crystal * M / (N * O): 0x01E0 = M - 2, 0x01E1[3:0] = N - 2, 0x01E1[5:4] = O / 2 (0 = O 1)  (ScalerPLLM2PLLPower, M_N type)
  - FLASH_CLK_DIV = FFED[5:2], MCU_CLK_DIV = FFEE[5:2] (enum _DIV_n = n)
- Crystal 14.31818 MHz (board, SDK _XTAL14318K); internal OSC 28 MHz nominal (SDK _INTERNAL_OSC_XTAL 28000K, trimmed at run time).
- Flash clock = source / FLASH_CLK_DIV / FLASH_CLK_DIV2 (FFE9[3:0]); ratio_x256 = CPU clk per flash clk for the core's code-fetch stall model.
"""
XTAL_HZ = 14_318_180
IOSC_HZ = 28_000_000
A_CLK_SEL, A_MCU_DIV, A_XTAL_SEL = 0xFFED, 0xFFEE, 0x0009
A_PLL_M, A_PLL_N = 0x01E0, 0x01E1
A_FLASH2 = 0xFFE9


class ClockModel:
    """Dev-protocol object (fw_sim.Dev): hooks the clock registers; .f_cpu is current after every write to them."""
    reads = ()
    writes = (A_CLK_SEL, A_XTAL_SEL, A_PLL_M, A_PLL_N, A_FLASH2)
    shared = (A_MCU_DIV,)                                  # also hooked by fw_sim.ChipReset: the machine calls update() after it

    def __init__(self):
        self.f_cpu, self.src = float(XTAL_HZ), "crystal"
        self.ratio_x256 = 256                         # CPU clk per flash clk x 256 (flash fetch stall model)
        self.log = []                                     # (wall ms, f_cpu Hz, source name) per change

    def init(self, m):
        self.update(m)

    def on_read(self, m, a):
        pass

    def on_write(self, m, a):
        self.update(m)

    def update(self, m):
        sel, mdiv, xs = m.rd(A_CLK_SEL)[0], m.rd(A_MCU_DIV)[0], m.rd(A_XTAL_SEL)[0]
        xtal = IOSC_HZ if xs & 0x08 else XTAL_HZ
        if sel & 0x02:
            pm, pn = m.rd(A_PLL_M)[0] + 2, m.rd(A_PLL_N)[0]
            o = ((pn >> 4) & 3) * 2 or 1
            src, name = XTAL_HZ * pm / (((pn & 0x0F) + 2) * o), "M2PLL"
        else:
            src, name = xtal, "iosc" if xs & 0x08 else "crystal"
        md, fd2 = max(1, (mdiv >> 2) & 0x0F), max(1, m.rd(A_FLASH2)[0] & 0x0F)
        f = src / max(1, (sel >> 2) & 0x0F) / md
        self.ratio_x256 = int(round(256.0 * fd2 / md))       # f_flash = source / FLASH_CLK_DIV / FLASH_CLK_DIV2, f_cpu = source / FLASH_CLK_DIV / MCU_CLK_DIV
        if f != self.f_cpu or name != self.src:
            self.f_cpu, self.src = f, name
            self.log.append((getattr(m, "wall_ms", 0.0), f, name))
