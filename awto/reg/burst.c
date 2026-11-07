/* burst.c: host-bus burst engine (spec reg section 2) and OSD item gap (spec reg section 5, D1). */
#include <stdint.h>
#include "reg.h"
#include "mode.h"
#include "names.h"

#ifndef REG8_WR
#define REG8_WR(a, v) (REG8(a) = (uint8_t)(v))
#endif

/* S11 restart limit: 100 busy checks (reference behaviour, vendor-value; spec reg T2) */
#define HB_BUSY_CHECKS 100

/* one read, then one write: new = (old & keep) | set */
static void rmw8(uint16_t a, uint8_t keep, uint8_t set)
{
    uint8_t old = reg_rd(a);
    REG8_WR(a, (old & keep) | set);
}

static uint8_t osd_gap_for(uint32_t dclk_khz)
{
    uint8_t hd = (reg_rd(OSD_FRAME_0A) & OSD_HDOUBLE) ? 1 : 0;
    return hb_osd_gap(dclk_khz, hd);
}

uint8_t hb_burst(uint32_t src24, uint16_t len, uint16_t target, uint8_t kind, uint8_t from_xram)
{
    uint8_t go = (kind == HB_CMDS) ? HB_CTRL_CMD_GO : HB_CTRL_DATA_GO;
    uint8_t ctl;
    uint8_t gap;
    uint8_t checks;
    uint8_t start;
    uint8_t ret;

    /* S1 */
    REG8_WR(REG_PAGE, target >> 8);
    /* S2, S3 */
    rmw8(HB_CTRL, (uint8_t)~(HB_CTRL_CMD_GO | HB_CTRL_DATA_GO), 0);
    rmw8(HB_CTRL, 0xFF, HB_CTRL_NOINC);
    /* S4..S9 */
    if (kind != HB_CMDS)
        REG8_WR(HB_TARGET, target & 0xFF);
    REG8_WR(HB_SRC_BANK, src24 >> 16);
    REG8_WR(HB_SRC_HI, src24 >> 8);
    REG8_WR(HB_SRC_LO, src24);
    REG8_WR(HB_LEN_HI, len >> 8);
    REG8_WR(HB_LEN_LO, len);
    /* gap 3: non-OSD item gap, vendor-value (spec reg S8) */
    gap = (kind == HB_OSD) ? osd_gap_for(mode_dclk_khz()) : 3;
    REG8_WR(HB_GAP, gap);
    if (from_xram)
        rmw8(MCU_MAP, 0xFF, MCU_MAP_BURST_FROM_XRAM);

    /* S10: start; the CPU stalls until the engine is done or an interrupt releases it */
    if (kind == HB_CMDS)
        start = HB_CTRL_CMD_GO;
    else if (kind == HB_STEP)
        start = HB_CTRL_DATA_GO;
    else
        start = HB_CTRL_DATA_GO | HB_CTRL_NOINC;
    REG8_WR(HB_CTRL, start);

    /* S11: restart while the go bit reads 1; the check read is the RMW read */
    checks = 0;
    for (;;) {
        ctl = reg_rd(HB_CTRL);
        if (!(ctl & go)) {
            ret = 0;
            break;
        }
        if (++checks == HB_BUSY_CHECKS) {
            ret = 1;
            break;
        }
        REG8_WR(HB_CTRL, ctl | go);
    }

    /* S12 runs on the timeout path too */
    rmw8(MCU_MAP, (uint8_t)~MCU_MAP_BURST_FROM_XRAM, 0);
    return ret;
}

uint8_t hb_osd_gap(uint32_t dclk_khz, uint8_t hdouble)
{
    /* 48438000 = 69 x 351 x 1000 x 2, derived (spec reg D1) */
    uint32_t q = dclk_khz ? 48438000UL / (dclk_khz * 4UL) : 0xFFFFFFFFUL;
    uint16_t g = (uint16_t)(q - 2);

    if (hdouble)
        g = (uint16_t)(g << 1);
    if (g > 0xFF)
        return 0xFF;
    if (g < 2)
        return 2;
    return (uint8_t)g;
}
