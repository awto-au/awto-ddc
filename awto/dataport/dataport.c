/* dataport.c: indexed ports (index register at port, data at port + 1). Spec: dataport section 2. */
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
    return dp_rd(port, idx) & mask;
}

/* the index is written again: the read may have advanced it */
void dp_rmw(uint16_t port, uint8_t idx, uint8_t keep, uint8_t set)
{
    uint8_t old = dp_rd(port, idx);
    REG8_WR(port, idx);
    REG8_WR(port + 1, (old & keep) | set);
}

void dp_wr16(uint16_t port, uint8_t idx, uint16_t v)
{
    dp_wr(port, idx, v >> 8);
    dp_wr(port, (uint8_t)(idx + 1), v);
}

void dp_rd_n(uint16_t port, uint8_t idx, uint8_t *dst, uint16_t n, uint8_t step)
{
    uint16_t k;
    for (k = 0; k < n; k++)
        dst[k] = dp_rd(port, step == DP_SW_STEP ? (uint8_t)(idx + k) : idx);
}

uint16_t dp_rd16(uint16_t port, uint8_t idx, uint8_t step)
{
    uint8_t hi = dp_rd(port, idx);
    uint8_t lo = dp_rd(port, step == DP_SW_STEP ? (uint8_t)(idx + 1) : idx);
    return ((uint16_t)hi << 8) | lo;
}
