/* test_dataport.c: host test for awto/dataport/dataport.c against spec dataport section 2.
 * Build and run from the repo root:
 *   gcc -std=gnu11 -Wall -Wextra -Iawto/include -Ifacts tests/host/test_dataport.c -o tmp/test_dataport
 *   tmp/test_dataport */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

/* recording mocks: the data register returns a counter, so returned values are checked too */
#define REG8_RD(a)    mock_rd((uint16_t)(a))
#define REG8_WR(a, v) mock_wr((uint16_t)(a), (uint8_t)(v))

struct acc {
    char op;
    uint16_t a;
    uint8_t v;
};

static struct acc logv[256];
static int nlog;
static struct acc expv[256];
static int nexp;
static uint8_t cnt;   /* mock data-register counter */
static uint8_t ecnt;  /* expected value of the next data read */
static int checks, fails;

static void log_add(struct acc *arr, int *n, char op, uint16_t a, uint8_t v)
{
    arr[*n].op = op;
    arr[*n].a = a;
    arr[*n].v = v;
    (*n)++;
}

static uint8_t mock_rd(uint16_t a)
{
    uint8_t v = cnt++;
    log_add(logv, &nlog, 'R', a, v);
    return v;
}

static void mock_wr(uint16_t a, uint8_t v)
{
    log_add(logv, &nlog, 'W', a, v);
}

#include "reg.h"
#include "dataport.h"
#include "../../awto/dataport/dataport.c"

static void begin(uint8_t start)
{
    nlog = 0;
    nexp = 0;
    cnt = start;
    ecnt = start;
}

static void exW(uint16_t a, uint8_t v)
{
    log_add(expv, &nexp, 'W', a, v);
}

/* data read: the value is the next counter value */
static void exR(uint16_t a)
{
    log_add(expv, &nexp, 'R', a, ecnt++);
}

static void check_log(const char *name)
{
    int i, bad = nexp != nlog;
    checks++;
    for (i = 0; !bad && i < nexp; i++)
        bad = expv[i].op != logv[i].op || expv[i].a != logv[i].a || expv[i].v != logv[i].v;
    if (!bad)
        return;
    fails++;
    printf("FAIL %s: expected %d accesses, got %d\n", name, nexp, nlog);
    for (i = 0; i < nexp || i < nlog; i++) {
        if (i < nexp)
            printf("  exp %c %04X %02X", expv[i].op, expv[i].a, expv[i].v);
        else
            printf("  exp -");
        if (i < nlog)
            printf("   got %c %04X %02X", logv[i].op, logv[i].a, logv[i].v);
        else
            printf("   got -");
        printf("\n");
    }
}

static void check_val(const char *name, unsigned got, unsigned want)
{
    checks++;
    if (got == want)
        return;
    fails++;
    printf("FAIL %s: got %02X want %02X\n", name, got, want);
}

static void test_ports(void)
{
    static const uint8_t idxs[] = {0x00, 0x7F, 0xFF};
    static const uint8_t ns[] = {0, 1, 2, 5};
    static const uint8_t steps[] = {DP_SW_STEP, DP_HW_STEP};
    const uint16_t p = 0x3F10;
    const uint8_t start = 0xC3;   /* counter start: exercises the masks */
    size_t ii, ni, si;

    for (ii = 0; ii < sizeof idxs; ii++) {
        const uint8_t i = idxs[ii];
        uint8_t got, dst[5];
        uint16_t got16;
        char name[64];

        snprintf(name, sizeof name, "dp_wr idx=%02X", i);
        begin(start);
        dp_wr(p, i, 0x5A);
        exW(p, i);
        exW(p + 1, 0x5A);
        check_log(name);

        snprintf(name, sizeof name, "dp_rd idx=%02X", i);
        begin(start);
        got = dp_rd(p, i);
        exW(p, i);
        exR(p + 1);
        check_log(name);
        check_val(name, got, start);

        snprintf(name, sizeof name, "dp_test idx=%02X", i);
        begin(start);
        got = dp_test(p, i, 0x0F);
        exW(p, i);
        exR(p + 1);
        check_log(name);
        check_val(name, got, start & 0x0F);

        /* dp_rmw: the index is written before the old read and again before the write */
        snprintf(name, sizeof name, "dp_rmw idx=%02X", i);
        begin(start);
        dp_rmw(p, i, 0xF0, 0x05);
        exW(p, i);
        exR(p + 1);
        exW(p, i);
        exW(p + 1, (start & 0xF0) | 0x05);
        check_log(name);

        snprintf(name, sizeof name, "dp_wr16 idx=%02X", i);
        begin(start);
        dp_wr16(p, i, 0x1234);
        exW(p, i);
        exW(p + 1, 0x12);
        exW(p, (uint8_t)(i + 1));
        exW(p + 1, 0x34);
        check_log(name);

        for (ni = 0; ni < sizeof ns; ni++) {
            for (si = 0; si < sizeof steps; si++) {
                const uint8_t n = ns[ni];
                const uint8_t step = steps[si];
                uint16_t k;
                snprintf(name, sizeof name, "dp_rd_n idx=%02X n=%d step=%d", i, n, step);
                begin(start);
                memset(dst, 0xEE, sizeof dst);
                dp_rd_n(p, i, dst, n, step);
                for (k = 0; k < n; k++) {
                    exW(p, step == DP_SW_STEP ? (uint8_t)(i + k) : i);
                    exR(p + 1);
                    check_val(name, dst[k], (uint8_t)(start + k));
                }
                check_log(name);
            }
        }

        for (si = 0; si < sizeof steps; si++) {
            const uint8_t step = steps[si];
            snprintf(name, sizeof name, "dp_rd16 idx=%02X step=%d", i, step);
            begin(start);
            got16 = dp_rd16(p, i, step);
            exW(p, i);
            exR(p + 1);
            exW(p, step == DP_SW_STEP ? (uint8_t)(i + 1) : i);
            exR(p + 1);
            check_log(name);
            check_val(name, got16 >> 8, start);
            check_val(name, got16 & 0xFF, (uint8_t)(start + 1));
        }
    }
}

int main(void)
{
    test_ports();
    printf("test_dataport: %d checks, %d failures\n", checks, fails);
    return fails ? 1 : 0;
}
