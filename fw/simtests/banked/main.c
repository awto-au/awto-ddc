#include "bk.h"
#include "sim.h"

volatile WORD __xdata xa = 0x1111, xb = 0x2222, xc = 0x3333;
volatile BYTE __xdata ba = 1, bb = 2, bc = 3;
volatile DWORD __xdata xl = 0x01020304UL;
static BYTE bad;

/* no string literals: sdcc_bank keys CONST chunks by name and every module's first literal is ___str_0 */
static const char __code s_fail[] = "FAIL ";
static const char __code s_ok[] = "ALL-OK\n";
static void chkf(const char __code *n, BYTE ok)
{
    if (!ok) { bad = 1; sim_puts(s_fail); sim_puts(n); sim_putc('\n'); }
}
#define chk(n, ok) do { static const char __code nm[] = n; chkf(nm, ok); } while (0)

#define W3(a, b, c) ((WORD)((WORD)(a) * 3 + (WORD)(b) * 5 + (WORD)(c) * 7))
#define V3(a, b, c) ((WORD)((WORD)(a) * 11 + (WORD)(b) * 13 + (WORD)(c) * 17))
static WORD r_back(WORD a, WORD b, WORD c) { return W3(c, b, a) + (WORD)(a * 3 + c); }

#if __SDCCCALL >= 1
WORD (*const tab2[2])(WORD, WORD) = {f2, g2};     /* pointers to banked fns = stub addresses */
#endif
#if __SDCCCALL >= 2
WORD (*const tab3[2])(WORD, WORD, WORD) = {f3, g3};
#endif

void main(void)
{
    WORD a = xa, b = xb, c = xc, i, ra = xa;
    BYTE p = ba, q = bb, r = bc;
    chk("f2", f2(a, b) == (WORD)(a * 3 + b) && f2(b, a) == (WORD)(b * 3 + a) && f2(xc, xa) == (WORD)(c * 3 + a));
    chk("g2", g2(a, b) == (WORD)(a * 5 + b) && g2(b, a) == (WORD)(b * 5 + a));
    chk("f3", f3(a, b, c) == W3(a, b, c) && f3(c, a, b) == W3(c, a, b) && f3(b, c, a) == W3(b, c, a));
    chk("g3", g3(a, b, c) == V3(a, b, c) && g3(c, b, a) == V3(c, b, a));
    chk("fb", fb(p, q, r) == 18 && fb(r, p, q) == 32);
    chk("fl", fl(xl, b) == 0x01020304UL + 0x2222 && fl(xl, 7) == 0x0102030BUL);
    chk("fbit", fbit(b, a) && !fbit(a, b) && fbit(c, 1) && !fbit(1, c));
    chk("chain1", chain1(a, b, c) == (WORD)(V3(c, a, b) + r_back(b, c, a) + W3(a, b, c)));
    chk("chain1 swap", chain1(c, b, a) == (WORD)(V3(a, c, b) + r_back(b, a, c) + W3(c, b, a)));
    chk("nest", f2(g2(a, b), g2(b, c)) == (WORD)((WORD)(a * 5 + b) * 3 + (WORD)(b * 5 + c)));
    chk("nest3", f3(f2(a, b), g2(b, c), f2(c, a)) == W3((WORD)(a * 3 + b), (WORD)(b * 5 + c), (WORD)(c * 3 + a)));
    for (i = 0; i < 40; i++)                                   /* many crossings, loop-carried values in regs */
    {
        a = f2(a, i) ^ g2(i, b);
        ra = (WORD)((WORD)(ra * 3 + i) ^ (WORD)(i * 5 + b));
    }
    chk("loop", a == ra);
    {   /* Keil ABI across stubs: generic pointers (xdata/code/data tags), long, float, every return type */
        static BYTE __xdata xb4[4] = {5, 6, 7, 8};
        static const BYTE __code cb4[4] = {1, 2, 3, 4};
        BYTE __data db4[4];
        const BYTE *gp;
        db4[0] = 9; db4[1] = 8; db4[2] = 7; db4[3] = 6;
        chk("gsum x", gsum(xb4, 4) == 26 && gsum(xb4 + 1, 2) == 13);
        chk("gsum c", gsum(cb4, 4) == 10 && gsum(cb4 + 2, 2) == 7);
        chk("gsum d", gsum(db4, 4) == 30);
        chk("gpick", gpick(2, 0x1203, xb4) == 7 + 3 && gpick(1, 1, cb4) == 3 && gpick(3, 0x0100, db4) == 6);
        chk("gp2", gp2(1, xb4, 3) == 15 && gp2(2, cb4, 4) == 10 && gp2(0, db4, 1) == 19);
        chk("lmix", lmix(0x01020304UL, 5, 6) == 0x01020304UL * 3 + 11 && lmix(0xFFFFUL, 0xFF, 1) == 0xFFFFUL * 3 + 256);
        chk("lsum3", lsum3(0x1234, 5, 6) == 0x1234000BUL);
        gp = gret(0); chk("gret c", gp[2] == 30 && gsum(gp, 4) == 100);
        gp = gret(1); chk("gret x", gp[3] == 4 && gsum(gp, 4) == 10);
        vset(0x5A); gp = gret(2); chk("gret d", gp[0] == 0x5A && vget() == 0x5A);
        chk("xret", xret()[2] == 3 && *dret() == 0x5A);
        *dret() = 0x33; chk("dret", vget() == 0x33);
        chk("fret", fret(3) == 1.5f && fret(10) == 5.0f);
        chk("fmul", fmul(1.5f, 4) == 6.0f && fmul(fret(3), 2) == 3.0f);
        chk("cret", cret(0xFE) == 0xFF && cret(9) == 10);
        chk("scr", scr(3, 5) == -2);
        chk("gnest", gnest(xb4, 4, 1) == 27 && gnest(cb4, 4, 2) == 12 && gnest(db4, 2, 3) == 20);
    }
#if __SDCCCALL >= 1
    chk("fp2", tab2[0](a, b) == f2(a, b) && tab2[1](b, c) == g2(b, c));
#endif
#if __SDCCCALL >= 2
    chk("fp3", tab3[0](a, b, c) == W3(a, b, c) && tab3[1](c, a, b) == V3(c, a, b));
#endif
    if (!bad)
        sim_puts(s_ok);
    else if (bad > 1)
        sim_puts(s_fail);               /* reference from common main keeps s_fail in common (see sdcc_bank #16) */
    sim_done();
}
