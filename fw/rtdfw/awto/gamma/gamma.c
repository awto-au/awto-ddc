/* gamma.c: output gamma stage. Register sequence: spec gamma section 2. Curves: gamma_tab.inc (tools/gen_gamma.py).
 * Loader and tables stay in this one translation unit (integrator pins gamma chunks together). */
#include <stdint.h>
#include "cc.h"
#include "reg.h"
#include "timer.h"
#include "regs.h"
#include "gamma.h"
#include "gamma_tab.inc"

#define GM_PORT      P00_66                 /* table data port: bytes fill the selected table in order */
#define GM_CTRL      P00_67
#define GM_ACCESS    P00_67_B7              /* table access enabled */
#define GM_ON        P00_67_B6              /* gamma stage enabled */
#define GM_CH_MASK   P00_67_B5_4            /* channel select: 0 = R, 1 = G, 2 = B */
#define GM_PTR       P00_67_B3              /* offset load mode */
#define GM_LOC       P00_67_B2              /* 0 = table SRAM */
#define GM_TAB_LEN   2052u                  /* 1026 entries x 2 bytes, spec gamma section 5 */

void gamma_load(uint8_t kind)
{
    const __code uint8_t *src;
    uint8_t was_on, ch;
    uint16_t i;

    if (kind > 3)
        return;
    was_on = reg_test(GM_CTRL, GM_ON) != 0;               /* L1 */
    if (was_on) {
        /* timeout: return before any write, stage stays on with the old table */
        if (!tmr_wait_edge(TE_OUT_VEND))                  /* L2 */
            return;
        reg_rmw(GM_CTRL, (uint8_t)~GM_ON, 0);             /* L3 */
    }
    src = gm_tab[kind];
    for (ch = 0; ch < 3; ch++) {
        reg_rmw(GM_CTRL, (uint8_t)~(GM_ACCESS | GM_CH_MASK | GM_LOC),
                (uint8_t)(ch << P00_67_B5_4_SH));          /* C1 */
        reg_rmw(GM_CTRL, 0xFF, GM_PTR);                    /* C2 */
        reg_wr(GM_PORT, 0x00);                             /* C3: offset 0, high byte first */
        reg_wr(GM_PORT, 0x00);
        reg_rmw(GM_CTRL, (uint8_t)~GM_PTR, GM_ACCESS);     /* C4 */
        for (i = 0; i < GM_TAB_LEN; i++)                   /* T */
            reg_wr(GM_PORT, src[i]);
    }
    reg_rmw(GM_CTRL, (uint8_t)~GM_ACCESS, 0);              /* L4 */
    if (was_on) {
        /* timeout: stage left off (L3 done), table loaded; not re-enabled */
        if (!tmr_wait_edge(TE_OUT_VEND))                   /* L5 */
            return;
        reg_rmw(GM_CTRL, 0xFF, GM_ON);                     /* L6 */
    }
}

void gamma_enable(uint8_t on)
{
    reg_rmw(GM_CTRL, (uint8_t)~GM_ON, on ? GM_ON : 0);
}
