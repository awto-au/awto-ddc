/* dataport.c: indexed ports (index register at port, data at port + 1). Spec: dataport sections 2, 4.
 * Hot path: no call between functions; every access is an inline REG8_WR / reg_rd. */
#include <stdint.h>
#include "reg.h"
#include "dataport.h"

void dp_wr(uint16_t port, uint8_t idx, uint8_t v)
{
    REG8_WR(port, idx);
    REG8_WR(port + 1, v);
}

uint8_t dp_rd(uint16_t port, uint8_t idx)
{
    REG8_WR(port, idx);
    return reg_rd(port + 1);
}

uint8_t dp_test(uint16_t port, uint8_t idx, uint8_t mask)
{
    REG8_WR(port, idx);
    return reg_test(port + 1, mask);
}

/* the index is written again: the read may have advanced it */
void dp_rmw(uint16_t port, uint8_t idx, uint8_t keep, uint8_t set)
{
    uint8_t old;
    REG8_WR(port, idx);
    old = reg_rd(port + 1);
    REG8_WR(port, idx);
    REG8_WR(port + 1, (old & keep) | set);
}

/* index idx + 1 wraps at 0x100 (spec section 1) */
void dp_wr16(uint16_t port, uint8_t idx, uint16_t v)
{
    REG8_WR(port, idx);
    REG8_WR(port + 1, (uint8_t)(v >> 8));
    REG8_WR(port, (uint8_t)(idx + 1));
    REG8_WR(port + 1, (uint8_t)v);
}

/* inc is 1 (SW step) or 0 (HW step); idx wraps at 0x100 */
void dp_rd_n(uint16_t port, uint8_t idx, uint8_t *dst, uint16_t n, uint8_t step)
{
    uint16_t k;
    uint8_t inc = (step == DP_SW_STEP);
    for (k = 0; k < n; k++) {
        REG8_WR(port, idx);
        dst[k] = reg_rd(port + 1);
        idx += inc;
    }
}

uint16_t dp_rd16(uint16_t port, uint8_t idx, uint8_t step)
{
    uint8_t hi, lo;
    REG8_WR(port, idx);
    hi = reg_rd(port + 1);
    idx += (step == DP_SW_STEP);
    REG8_WR(port, idx);
    lo = reg_rd(port + 1);
    return ((uint16_t)hi << 8) | lo;
}
