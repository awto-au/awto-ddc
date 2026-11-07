/* test_gamma.c: host test for awto/gamma/gamma.c against spec gamma sections 2, 5, 6.
 * Includes the implementation: the REG8 mock must be defined before reg.h is first included.
 * Build and run from the repo root:
 *   gcc -std=gnu11 -Wall -Wextra -Iawto/include -Ifacts tests/host/test_gamma.c -lm -o tmp/test_gamma
 *   tmp/test_gamma tests/vectors/gamma.tsv */
#include <math.h>
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

enum { EV_RD, EV_WR, EV_EDGE };
struct ev { uint8_t op; uint16_t addr; uint8_t val; };

#define MAXEV   16384
#define CTRL    0x0067u                    /* P00_67 */
#define PORT    0x0066u                    /* P00_66 */
#define ANY     0xFFFFu                    /* expected value not checked (table data) */
#define NCH_BYTES 2052u

static struct ev tr[MAXEV];
static unsigned ntr;
static uint8_t regs[0x10000];
static uint8_t edge_ret[4];                /* return values of successive tmr_wait_edge calls */
static unsigned nedge_calls;

static void ev_push(uint8_t op, uint16_t a, uint8_t v)
{
    if (ntr < MAXEV) {
        tr[ntr].op = op;
        tr[ntr].addr = a;
        tr[ntr].val = v;
    }
    ntr++;
}

static uint8_t mock_rd(uint16_t a)
{
    ev_push(EV_RD, a, 0);
    return regs[a];
}

static void mock_wr(uint16_t a, uint8_t v)
{
    ev_push(EV_WR, a, v);
    regs[a] = v;
}

#define REG8_RD(a)    mock_rd(a)
#define REG8_WR(a, v) mock_wr((a), (v))

uint8_t tmr_wait_edge(uint8_t edge)
{
    uint8_t r = nedge_calls < 4 ? edge_ret[nedge_calls] : 1;

    ev_push(EV_EDGE, edge, 0);
    nedge_calls++;
    return r;
}

#include "../../awto/gamma/gamma.c"

struct exp { uint8_t op; uint16_t addr; uint16_t val; };
static struct exp ex[MAXEV];
static unsigned nex;
static long fails;
static uint8_t kdata[4][3 * NCH_BYTES];    /* data bytes of the last load per kind (R, G, B) */
static const unsigned kind_gx10[4] = { 18, 20, 22, 24 };

static void x(uint8_t op, uint16_t a, uint16_t v)
{
    ex[nex].op = op;
    ex[nex].addr = a;
    ex[nex].val = v;
    nex++;
}

static void xrmw(uint8_t ctrl_val)         /* RMW of CTRL: one read, one write */
{
    x(EV_RD, CTRL, ANY);
    x(EV_WR, CTRL, ctrl_val);
}

/* spec gamma section 2: C1..C4 and T for R, G, B, then L4 (ACCESS cleared) */
static void exp_body(void)
{
    static const uint8_t c1[3] = { 0x00, 0x10, 0x20 };
    static const uint8_t c2[3] = { 0x08, 0x18, 0x28 };
    static const uint8_t c4[3] = { 0x80, 0x90, 0xA0 };
    unsigned ch, i;

    for (ch = 0; ch < 3; ch++) {
        xrmw(c1[ch]);
        xrmw(c2[ch]);
        x(EV_WR, PORT, 0x00);              /* C3: offset 0, high byte first */
        x(EV_WR, PORT, 0x00);
        xrmw(c4[ch]);
        for (i = 0; i < NCH_BYTES; i++)
            x(EV_WR, PORT, ANY);
    }
    xrmw(0x20);                            /* L4 */
}

static void reset_mock(uint8_t start_ctrl, const uint8_t *edges, unsigned ne)
{
    memset(regs, 0, sizeof regs);
    memset(tr, 0, sizeof tr);
    memset(edge_ret, 1, sizeof edge_ret);
    if (edges)
        memcpy(edge_ret, edges, ne);
    ntr = 0;
    nex = 0;
    nedge_calls = 0;
    regs[CTRL] = start_ctrl;
}

/* compares trace with expectation; copies the ANY-PORT bytes (table data, in order) to data */
static int compare_trace(const char *name, uint8_t *data, unsigned cap, unsigned *ndata)
{
    unsigned i, nd = 0;
    int bad = 0;

    if (ntr != nex) {
        printf("FAIL %s: %u events, expected %u\n", name, ntr, nex);
        bad = 1;
    }
    for (i = 0; i < ntr && i < nex; i++) {
        if (tr[i].op != ex[i].op || tr[i].addr != ex[i].addr ||
            (ex[i].val != ANY && tr[i].val != ex[i].val)) {
            printf("FAIL %s: event %u op %u addr %04X val %02X, expected op %u addr %04X val %04X\n",
                   name, i, tr[i].op, tr[i].addr, tr[i].val, ex[i].op, ex[i].addr, ex[i].val);
            bad = 1;
            break;
        }
        if (ex[i].val == ANY && ex[i].op == EV_WR && ex[i].addr == PORT) {
            if (data && nd < cap)
                data[nd] = tr[i].val;
            nd++;
        }
    }
    if (ndata)
        *ndata = nd;
    return bad;
}

/* reference curve, spec gamma section 5: 16368 * (i/1023)^(g/2.2), round half up; 1024, 1025 fixed */
static uint16_t ref_entry(unsigned gx10, unsigned i)
{
    double v;

    if (i == 1024)
        return 0x3FF0;
    if (i == 1025)
        return 0x0000;
    v = 16368.0 * pow((double)i / 1023.0, (double)gx10 / 22.0);
    return (uint16_t)(v + 0.5);
}

static uint16_t entry(const uint8_t *pd, unsigned i)
{
    return (uint16_t)((pd[2 * i] << 8) | pd[2 * i + 1]);
}

/* 1026 entries of R; G and B equal R; formula within +-1; monotonic 0..1023 */
static int check_curve(unsigned kind, const uint8_t *pd)
{
    unsigned i;
    long maxdev = 0;
    int bad = 0;

    if (memcmp(pd, pd + NCH_BYTES, NCH_BYTES) != 0 || memcmp(pd, pd + 2 * NCH_BYTES, NCH_BYTES) != 0) {
        printf("FAIL kind %u: channels differ\n", kind);
        bad = 1;
    }
    for (i = 0; i < 1026; i++) {
        long dev = (long)entry(pd, i) - (long)ref_entry(kind_gx10[kind], i);
        if (labs(dev) > maxdev)
            maxdev = labs(dev);
        if (labs(dev) > 1) {
            printf("FAIL kind %u entry %u: got %04X, formula %04X\n", kind, i, entry(pd, i),
                   ref_entry(kind_gx10[kind], i));
            bad = 1;
            break;
        }
    }
    for (i = 1; i < 1024 && !bad; i++) {
        if (entry(pd, i) < entry(pd, i - 1)) {
            printf("FAIL kind %u: entries %u..%u decrease\n", kind, i - 1, i);
            bad = 1;
        }
    }
    if (entry(pd, 1024) != 0x3FF0 || entry(pd, 1025) != 0) {
        printf("FAIL kind %u: entries 1024/1025 are %04X/%04X\n", kind, entry(pd, 1024), entry(pd, 1025));
        bad = 1;
    }
    printf("kind %u (gamma %u.%u): max |dev| vs formula = %ld\n", kind, kind_gx10[kind] / 10,
           kind_gx10[kind] % 10, maxdev);
    return bad;
}

/* L1 .. L4 for a stage that is off (start 0x00), or on (start 0x40: L2/L3 and L5/L6 added) */
static int test_load(unsigned kind, uint8_t start_ctrl)
{
    static uint8_t pd[3 * NCH_BYTES];
    char name[64];
    unsigned nd = 0;
    int bad;

    reset_mock(start_ctrl, NULL, 0);
    nex = 0;
    x(EV_RD, CTRL, ANY);                   /* L1 */
    if (start_ctrl & P00_67_B6) {
        x(EV_EDGE, TE_OUT_VEND, 0);        /* L2 */
        xrmw(0x00);                        /* L3 */
    }
    exp_body();
    if (start_ctrl & P00_67_B6) {
        x(EV_EDGE, TE_OUT_VEND, 0);        /* L5 */
        xrmw(0x60);                        /* L6: ON set */
    }
    gamma_load((uint8_t)kind);
    sprintf(name, "load kind %u start %02X", kind, start_ctrl);
    bad = compare_trace(name, pd, sizeof pd, &nd);
    if (nd != 3 * NCH_BYTES) {
        printf("FAIL %s: %u data bytes\n", name, nd);
        bad = 1;
    }
    bad |= check_curve(kind, pd);
    memcpy(kdata[kind], pd, sizeof pd);
    if (bad)
        fails++;
    return bad;
}

/* spec gamma section 6: vectors gamma_x10 index expected, +-1 */
static void check_vectors(const char *path)
{
    FILE *f = fopen(path, "r");
    char line[256];
    long rows = 0, bad = 0;

    if (!f) {
        printf("cannot open %s\n", path);
        fails++;
        return;
    }
    while (fgets(line, sizeof line, f)) {
        unsigned gx10, idx, want, k, got;
        long dev;

        if (line[0] == '#' || line[0] == '\n')
            continue;
        if (sscanf(line, "%u %u %x", &gx10, &idx, &want) != 3 || idx >= 1026) {
            printf("bad row: %s", line);
            bad++;
            continue;
        }
        for (k = 0; k < 4 && kind_gx10[k] != gx10; k++)
            ;
        if (k == 4) {
            printf("bad gamma in row: %s", line);
            bad++;
            continue;
        }
        got = entry(kdata[k], idx);
        dev = (long)got - (long)want;
        rows++;
        if (labs(dev) > 1) {
            printf("FAIL vector gamma %u index %u: got %04X want %04X\n", gx10, idx, got, want);
            bad++;
        }
    }
    fclose(f);
    printf("vectors: %ld rows, %ld failures\n", rows, bad);
    fails += bad > 0;
}

static int test_enable(void)
{
    int bad = 0;

    reset_mock(0x00, NULL, 0);
    nex = 0;
    x(EV_RD, CTRL, ANY);
    x(EV_WR, CTRL, 0x40);
    gamma_enable(1);
    bad |= compare_trace("enable 1", NULL, 0, NULL);

    reset_mock(0x40, NULL, 0);
    nex = 0;
    x(EV_RD, CTRL, ANY);
    x(EV_WR, CTRL, 0x00);
    gamma_enable(0);
    bad |= compare_trace("enable 0", NULL, 0, NULL);
    printf("enable: %s\n", bad ? "FAIL" : "ok");
    fails += bad;
    return bad;
}

/* timeouts: L2 expiry returns before any write; L5 expiry leaves the stage off */
static int test_timeouts(void)
{
    static const uint8_t l2[1] = { 0 };
    static const uint8_t l5[2] = { 1, 0 };
    int bad = 0;

    reset_mock(0x40, l2, 1);
    nex = 0;
    x(EV_RD, CTRL, ANY);
    x(EV_EDGE, TE_OUT_VEND, 0);
    gamma_load(2);
    bad |= compare_trace("timeout L2", NULL, 0, NULL);

    reset_mock(0x40, l5, 2);
    nex = 0;
    x(EV_RD, CTRL, ANY);
    x(EV_EDGE, TE_OUT_VEND, 0);
    xrmw(0x00);
    exp_body();
    x(EV_EDGE, TE_OUT_VEND, 0);
    gamma_load(2);
    bad |= compare_trace("timeout L5", NULL, 0, NULL);
    printf("timeouts: %s\n", bad ? "FAIL" : "ok");
    fails += bad;
    return bad;
}

int main(int argc, char **argv)
{
    const char *vec = argc > 1 ? argv[1] : "tests/vectors/gamma.tsv";
    unsigned k;

    for (k = 0; k < 4; k++)
        fails += test_load(k, 0x00);
    fails += test_load(2, 0x40);           /* stage on */
    test_enable();
    test_timeouts();
    check_vectors(vec);

    reset_mock(0x00, NULL, 0);             /* kind out of range: no bus traffic */
    gamma_load(4);
    if (ntr != 0) {
        printf("FAIL kind 4: %u events\n", ntr);
        fails++;
    }
    printf("test_gamma: %s (%ld failing groups)\n", fails ? "FAIL" : "PASS", fails);
    return fails ? 1 : 0;
}
