/* burst.c: host-bus burst engine (spec reg section 2) and OSD item gap (spec reg section 5, D1). */
#include <stdint.h>
#include "reg.h"
#include "mode.h"
#include "names.h"

/* T2: 100 busy checks, reference behaviour (sdk-value; spec reg section 4) */
#define HB_BUSY_CHECKS 100

uint8_t hb_burst(uint32_t src24, uint16_t len, uint16_t target, uint8_t kind, uint8_t from_xram)
{
    uint8_t go = (kind == HB_CMDS) ? HB_CTRL_CMD_GO : HB_CTRL_DATA_GO;
    uint8_t ctl, gap, start, checks, ret, hd;

    /* S1, S2, S3: each read-modify-write is one read then one write */
    REG8_WR(REG_PAGE, target >> 8);
    REG8_WR(HB_CTRL, REG8_RD(HB_CTRL) & (uint8_t)~(HB_CTRL_CMD_GO | HB_CTRL_DATA_GO));
    REG8_WR(HB_CTRL, REG8_RD(HB_CTRL) | HB_CTRL_NOINC);

    /* S4..S7 */
    if (kind != HB_CMDS)
        REG8_WR(HB_TARGET, target);
    REG8_WR(HB_SRC_BANK, src24 >> 16);
    REG8_WR(HB_SRC_HI, src24 >> 8);
    REG8_WR(HB_SRC_LO, src24);
    REG8_WR(HB_LEN_HI, len >> 8);
    REG8_WR(HB_LEN_LO, len);

    /* S8r, S8: gap 3 for non-OSD kinds is sdk-value (spec reg S8) */
    if (kind == HB_OSD) {
        hd = (REG8_RD(OSD_FRAME_0A) & OSD_HDOUBLE) ? 1 : 0;
        gap = hb_osd_gap(mode_dclk_khz(), hd);
    } else {
        gap = 3;
    }
    REG8_WR(HB_GAP, gap);

    /* S9 */
    if (from_xram)
        REG8_WR(MCU_MAP, REG8_RD(MCU_MAP) | MCU_MAP_BURST_FROM_XRAM);

    /* S10: start; the CPU stalls until the engine is done or an interrupt releases it */
    if (kind == HB_CMDS)
        start = HB_CTRL_CMD_GO;
    else if (kind == HB_STEP)
        start = HB_CTRL_DATA_GO;
    else
        start = HB_CTRL_DATA_GO | HB_CTRL_NOINC;
    REG8_WR(HB_CTRL, start);

    /* S11: a check read; while busy, a restart is its own RMW (read, then write read | go) */
    checks = 0;
    for (;;) {
        ctl = REG8_RD(HB_CTRL);
        if (!(ctl & go)) {
            ret = 0;
            break;
        }
        if (++checks == HB_BUSY_CHECKS) {
            ret = 1;
            break;
        }
        REG8_WR(HB_CTRL, REG8_RD(HB_CTRL) | go);
    }

    /* S12 runs on the timeout path too */
    REG8_WR(MCU_MAP, REG8_RD(MCU_MAP) & (uint8_t)~MCU_MAP_BURST_FROM_XRAM);
    return ret;
}

uint8_t hb_osd_gap(uint32_t dclk_khz, uint8_t hdouble)
{
    /* 12,109,500 = 69 x 351 x 1000 x 2 / 4, derived (spec reg D1) */
    uint16_t g;

    if (!dclk_khz)
        return 0xFF;   /* q = 0xFFFFFFFF: g > 0xFF with or without doubling */
    g = (uint16_t)(12109500UL / dclk_khz - 2);

    if (hdouble)
        g = (uint16_t)(g << 1);
    if (g > 0xFF)
        return 0xFF;
    if (g < 2)
        return 2;
    return (uint8_t)g;
}
