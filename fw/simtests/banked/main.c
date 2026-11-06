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
