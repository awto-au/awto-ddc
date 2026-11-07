/* test_reg.c: host test for awto/reg (reg.c, burst.c) against spec reg.
 * Build and run from the repo root:
 *   gcc -std=gnu11 -Wall -Wextra -Iawto/include -Ifacts tests/host/test_reg.c -o tmp/test_reg
 *   tmp/test_reg tests/vectors/osdgap.tsv */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "names.h"

/* recording mocks: reads and writes are separate calls so the access list keeps its kind */
#define REG8(a)       mock_rd((uint16_t)(a))
#define REG8_WR(a, v) mock_wr((uint16_t)(a), (uint8_t)(v))

struct acc {
    char op;
    uint16_t a;
    uint8_t v;
};

static uint8_t mem[65536];
static struct acc logv[4096];
static int nlog;
static struct acc expv[4096];
static int nexp;
static int armed;      /* HB_CTRL start written: busy reads apply */
static int busy_left;  /* busy checks still to report */
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
    uint8_t v = mem[a];
    if (a == HB_CTRL && armed) {
        uint8_t go = (v & HB_CTRL_CMD_GO) ? HB_CTRL_CMD_GO : HB_CTRL_DATA_GO;
        if (busy_left > 0) {
            busy_left--;
            v |= go;
        } else {
            v &= (uint8_t)~go;
        }
    }
    log_add(logv, &nlog, 'R', a, v);
    return v;
}

static void mock_wr(uint16_t a, uint8_t v)
{
    if (a == HB_CTRL && (v & (HB_CTRL_CMD_GO | HB_CTRL_DATA_GO)))
        armed = 1;
    mem[a] = v;
    log_add(logv, &nlog, 'W', a, v);
}

#include "reg.h"
#include "mode.h"
#include "../../awto/reg/reg.c"
#include "../../awto/reg/burst.c"

uint32_t mode_dclk_khz(void)
{
    return 148500;  /* 1080p60 pixel clock; osd gap rows checked in burst_case */
}

static void reset_case(void)
{
    memset(mem, 0, sizeof mem);
    nlog = 0;
    nexp = 0;
    armed = 0;
    busy_left = 0;
}

static void ex(char op, uint16_t a, uint8_t v)
{
    log_add(expv, &nexp, op, a, v);
}

static void check(const char *name)
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

static void check_u32(const char *name, uint32_t got, uint32_t want)
{
    checks++;
    if (got == want)
        return;
    fails++;
    printf("FAIL %s: got %08lX want %08lX\n", name, (unsigned long)got, (unsigned long)want);
}

static void test_multibyte(void)
{
    uint8_t src[5] = {1, 2, 3, 4, 5};
    uint8_t dst[5];
    uint16_t r16;
    uint32_t r32;
    int n;

    /* reg_rd16 / reg_wr16 */
    reset_case();
    mem[0x1234] = 0xAB;
    mem[0x1235] = 0xCD;
    r16 = reg_rd16(0x1234);
    ex('R', 0x1234, 0xAB);
    ex('R', 0x1235, 0xCD);
    check("rd16");
    check_u32("rd16 value", r16, 0xABCD);

    reset_case();
    reg_wr16(0x1234, 0xABCD);
    ex('W', 0x1234, 0xAB);
    ex('W', 0x1235, 0xCD);
    check("wr16");

    /* reg_rd32 / reg_wr32: measured 32-bit write order (high byte first) */
    reset_case();
    mem[0x8A04] = 0x00;
    mem[0x8A05] = 0x01;
    mem[0x8A06] = 0x01;
    mem[0x8A07] = 0x00;
    r32 = reg_rd32(0x8A04);
    ex('R', 0x8A04, 0x00);
    ex('R', 0x8A05, 0x01);
    ex('R', 0x8A06, 0x01);
    ex('R', 0x8A07, 0x00);
    check("rd32");
    check_u32("rd32 value", r32, 0x00010100);

    reset_case();
    reg_wr32(0x8A04, 0x00010100);
    ex('W', 0x8A04, 0x00);
    ex('W', 0x8A05, 0x01);
    ex('W', 0x8A06, 0x01);
    ex('W', 0x8A07, 0x00);
    check("wr32");

    /* reg_rmw32: new = (old & keep) | (set & ~keep) */
    reset_case();
    mem[0x8A04] = 0x11;
    mem[0x8A05] = 0x22;
    mem[0x8A06] = 0x33;
    mem[0x8A07] = 0x44;
    reg_rmw32(0x8A04, 0xFFFF0000, 0x0000ABCD);
    ex('R', 0x8A04, 0x11);
    ex('R', 0x8A05, 0x22);
    ex('R', 0x8A06, 0x33);
    ex('R', 0x8A07, 0x44);
    ex('W', 0x8A04, 0x11);
    ex('W', 0x8A05, 0x22);
    ex('W', 0x8A06, 0xAB);
    ex('W', 0x8A07, 0xCD);
    check("rmw32");
    check_u32("rmw32 value", (uint32_t)mem[0x8A04] << 24 | (uint32_t)mem[0x8A05] << 16 |
                             (uint32_t)mem[0x8A06] << 8 | mem[0x8A07], 0x1122ABCD);

    /* reg_wr_n / reg_rd_n: step 1 = consecutive, step 0 = fixed address, n = 0 = no access */
    for (n = 0; n <= 5; n++) {
        int k;
        reset_case();
        reg_wr_n(0x2000, src, n, 1);
        for (k = 0; k < n; k++)
            ex('W', 0x2000 + k, src[k]);
        check("wr_n step1");

        reset_case();
        reg_wr_n(0x2000, src, n, 0);
        for (k = 0; k < n; k++)
            ex('W', 0x2000, src[k]);
        check("wr_n step0");

        reset_case();
        mem[0x2000] = 0x10;
        mem[0x2001] = 0x20;
        mem[0x2002] = 0x30;
        mem[0x2003] = 0x40;
        mem[0x2004] = 0x50;
        reg_rd_n(0x2000, dst, n, 1);
        for (k = 0; k < n; k++) {
            ex('R', 0x2000 + k, mem[0x2000 + k]);
            checks++;
            if (dst[k] != mem[0x2000 + k]) {
                fails++;
                printf("FAIL rd_n step1 n=%d k=%d\n", n, k);
            }
        }
        check("rd_n step1");

        reset_case();
        mem[0x2000] = 0x7E;
        reg_rd_n(0x2000, dst, n, 0);
        for (k = 0; k < n; k++)
            ex('R', 0x2000, 0x7E);
        check("rd_n step0");
    }
}

/* S1..S12 of spec reg section 2, in the fixed order used by burst.c */
static void burst_case(uint8_t kind, uint8_t xram, uint8_t hd, int busy_n)
{
    const uint16_t target = 0x8B04;
    const uint32_t src = 0x0A5B6C;
    const uint16_t len = 0x1234;
    const uint8_t go = (kind == HB_CMDS) ? HB_CTRL_CMD_GO : HB_CTRL_DATA_GO;
    uint8_t ctl = 0x80;     /* HB_CTRL reset value (facts PFF_F3_RST) */
    uint8_t map = 0x08;     /* MCU_MAP reset value (facts PFF_FC_RST) */
    uint8_t start, gap, want_ret;
    uint8_t ret;
    int k;
    char name[80];

    snprintf(name, sizeof name, "burst kind=%d xram=%d hd=%d busy=%d", kind, xram, hd, busy_n);
    reset_case();
    mem[HB_CTRL] = ctl;
    mem[MCU_MAP] = map;
    mem[OSD_FRAME_0A] = hd ? OSD_HDOUBLE : 0;
    busy_left = busy_n;

    /* S1 */
    ex('W', REG_PAGE, target >> 8);
    /* S2 */
    ex('R', HB_CTRL, ctl);
    ctl &= (uint8_t)~(HB_CTRL_CMD_GO | HB_CTRL_DATA_GO);
    ex('W', HB_CTRL, ctl);
    /* S3 */
    ex('R', HB_CTRL, ctl);
    ctl |= HB_CTRL_NOINC;
    ex('W', HB_CTRL, ctl);
    /* S4 */
    if (kind != HB_CMDS)
        ex('W', HB_TARGET, target & 0xFF);
    /* S5..S7 */
    ex('W', HB_SRC_BANK, src >> 16);
    ex('W', HB_SRC_HI, (src >> 8) & 0xFF);
    ex('W', HB_SRC_LO, src & 0xFF);
    ex('W', HB_LEN_HI, len >> 8);
    ex('W', HB_LEN_LO, len & 0xFF);
    /* S8 */
    if (kind == HB_OSD) {
        gap = hd ? 0x9E : 0x4F;     /* osdgap rows at 148500 kHz */
        ex('R', OSD_FRAME_0A, hd ? OSD_HDOUBLE : 0);
    } else {
        gap = 3;
    }
    ex('W', HB_GAP, gap);
    /* S9 */
    if (xram) {
        ex('R', MCU_MAP, map);
        map |= MCU_MAP_BURST_FROM_XRAM;
        ex('W', MCU_MAP, map);
    }
    /* S10 */
    start = (kind == HB_CMDS) ? 0x10 : (kind == HB_STEP) ? 0x08 : 0x28;
    ex('W', HB_CTRL, start);
    /* S11: busy reads report go; each busy read below 100 is followed by a restart write */
    ret = 0;
    for (k = 1;; k++) {
        int busy = k <= busy_n;
        ex('R', HB_CTRL, busy ? (uint8_t)(start | go) : (uint8_t)(start & ~go));
        if (!busy) {
            ret = 0;
            break;
        }
        if (k == 100) {
            ret = 1;
            break;
        }
        ex('W', HB_CTRL, start | go);
    }
    /* S12: always */
    ex('R', MCU_MAP, map);
    map &= (uint8_t)~MCU_MAP_BURST_FROM_XRAM;
    ex('W', MCU_MAP, map);

    want_ret = (busy_n >= 100);
    ret = hb_burst(src, len, target, kind, xram);
    if (ret != want_ret) {
        fails++;
        printf("FAIL %s: return %d want %d\n", name, ret, want_ret);
    }
    checks++;
    check(name);
}

static void test_burst(void)
{
    static const int busy_n[] = {0, 1, 5, 99, 100, 200};
    uint8_t kind, xram, hd;
    size_t i;

    for (kind = HB_FIXED; kind <= HB_CMDS; kind++)
        for (xram = 0; xram <= 1; xram++)
            for (hd = 0; hd <= 1; hd++)
                for (i = 0; i < sizeof busy_n / sizeof busy_n[0]; i++)
                    burst_case(kind, xram, hd, busy_n[i]);
}

static void test_osd_gap_vectors(const char *path)
{
    FILE *f = fopen(path, "r");
    char line[256];
    int rows = 0;

    if (!f) {
        fails++;
        printf("FAIL cannot open %s\n", path);
        return;
    }
    while (fgets(line, sizeof line, f)) {
        unsigned long dclk;
        unsigned hd, want;
        uint8_t got;
        if (line[0] == '#' || line[0] == '\n')
            continue;
        if (sscanf(line, "%lu %u %x", &dclk, &hd, &want) != 3) {
            fails++;
            printf("FAIL bad row: %s", line);
            continue;
        }
        got = hb_osd_gap((uint32_t)dclk, (uint8_t)hd);
        checks++;
        rows++;
        if (got != want) {
            fails++;
            printf("FAIL osd_gap dclk=%lu hd=%u got %02X want %02X\n", dclk, hd, got, want);
        }
    }
    fclose(f);
    printf("osdgap rows: %d\n", rows);
}

int main(int argc, char **argv)
{
    const char *vec = argc > 1 ? argv[1] : "tests/vectors/osdgap.tsv";

    test_multibyte();
    test_burst();
    test_osd_gap_vectors(vec);
    printf("test_reg: %d checks, %d failures\n", checks, fails);
    return fails ? 1 : 0;
}
