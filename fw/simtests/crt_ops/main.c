/* % and / written as C operators (compiler-generated helper calls, not direct calls) through fw/sdcc/crt_mod0.c and
 * crt_divulong.c: checks the arg-passing convention of the crt overrides at the current AWTO_SDCCCALL level (#51.1).
 * Self-checking: any wrong result hangs before the sentinel (harness: TIMEOUT). Operands volatile: no constant folding. */
#include "sim.h"

struct vec { unsigned long a, b, q, r32; unsigned int r16; unsigned long m10, d1000; unsigned int m10_16; };
static const struct vec T[] = {
    {0xDEADBEEFUL, 0x00000007UL, 0x1FCFAD8FUL, 0x00000006UL, 0x0005, 0x00000009UL, 0x00390178UL, 0x0009},
    {0xDEADBEEFUL, 0x00010001UL, 0x0000DEACUL, 0x0000E043UL, 0x0000, 0x00000009UL, 0x00390178UL, 0x0009},
    {0xFFFFFFFFUL, 0x00000003UL, 0x55555555UL, 0x00000000UL, 0x0000, 0x00000005UL, 0x00418937UL, 0x0005},
    {0x12345678UL, 0x00001234UL, 0x00010004UL, 0x00000DA8UL, 0x0DA8, 0x00000006UL, 0x0004A90BUL, 0x0006},
    {0x000003E8UL, 0x00000000UL, 0xFFFFFFFFUL, 0x000003E8UL, 0x03E8, 0x00000000UL, 0x00000001UL, 0x0000},
    {0x0000BEEFUL, 0x00000000UL, 0xFFFFFFFFUL, 0x0000BEEFUL, 0xBEEF, 0x00000009UL, 0x00000030UL, 0x0009},
    {0x00000064UL, 0x00000007UL, 0x0000000EUL, 0x00000002UL, 0x0002, 0x00000000UL, 0x00000000UL, 0x0000},
    {0x80000000UL, 0x7FFFFFFFUL, 0x00000001UL, 0x00000001UL, 0x0000, 0x00000008UL, 0x0020C49BUL, 0x0000},
    {0x6AA79987UL, 0x00029A73UL, 0x000028F8UL, 0x0000021FUL, 0x9987, 0x00000001UL, 0x001B4DB8UL, 0x0003},
    {0xD1F6F86CUL, 0x0000DAEBUL, 0x0000F587UL, 0x00009F7FUL, 0x1D81, 0x00000006UL, 0x0035C03FUL, 0x0006},
    {0x5E503A67UL, 0x00000045UL, 0x015DEA95UL, 0x0000003EUL, 0x002F, 0x00000005UL, 0x001824ECUL, 0x0001},
    {0x90E5E945UL, 0x00002965UL, 0x0003801BUL, 0x00000B9EUL, 0x1A4C, 0x00000005UL, 0x0025180AUL, 0x0007},
    {0x5F811CB9UL, 0x000000DFUL, 0x006DA324UL, 0x0000005DUL, 0x00D9, 0x00000007UL, 0x001872F9UL, 0x0003},
    {0x6ED4E94BUL, 0x00008FE5UL, 0x0000C52DUL, 0x0000650AUL, 0x5966, 0x00000005UL, 0x001C5F77UL, 0x0003},
    {0xA091250EUL, 0x0000009DUL, 0x0105D0F3UL, 0x00000007UL, 0x0042, 0x00000006UL, 0x00291AEAUL, 0x0006},
    {0x8D9FE5B9UL, 0x0000005BUL, 0x018E6A9CUL, 0x00000045UL, 0x0017, 0x00000009UL, 0x00244182UL, 0x0009},
    {0xBCF74D7AUL, 0x00175F0DUL, 0x00000815UL, 0x00141969UL, 0x4D7A, 0x00000004UL, 0x00306013UL, 0x0004},
    {0x87F26AEEUL, 0x006980A9UL, 0x00000149UL, 0x005C11BDUL, 0x6AEE, 0x00000006UL, 0x0022CD6BUL, 0x0004},
};

volatile unsigned long va, vb;
volatile unsigned int ua, ub;

void main(void)
{
    unsigned char i, bad = 0;
    unsigned long q, r;
    unsigned int r16;
    for (i = 0; i < sizeof T / sizeof T[0]; i++) {
        va = T[i].a; vb = T[i].b; ua = (unsigned int)T[i].a; ub = (unsigned int)T[i].b;
        q = va / vb;
        r = va % vb;
        r16 = ua % ub;
        if (va % 10UL != T[i].m10 || va / 1000UL != T[i].d1000 || ua % 10U != T[i].m10_16) bad++;   /* constant divisors */
        if (q != T[i].q || r != T[i].r32 || r16 != T[i].r16) { bad++; sim_val("badrow", i); }
    }
    sim_val("bad", bad);
    if (bad) for (;;) ;
    sim_done();
}
