/* asm vs C-reference equivalence for ScalerCommonComputeDwordMulDiv.asm (MulDiv + PowDiv). */
#include "sim.h"
typedef unsigned char BYTE;
typedef unsigned int WORD;
typedef unsigned long DWORD;
DWORD ScalerComputeDwordMulDiv(DWORD a, DWORD b, DWORD c);
DWORD ScalerComputeDwordPowDiv(DWORD a, BYTE pow, DWORD b);
DWORD ref_ScalerComputeDwordMulDiv(DWORD a, DWORD b, DWORD c);
DWORD ref_ScalerComputeDwordPowDiv(DWORD a, BYTE pow, DWORD b);

static DWORD seed = 0x13579BDF;
static DWORD rnd32(void)
{
    seed = seed * 1103515245UL + 12345UL;
    return (seed & 0xFFFF0000UL) | ((seed = seed * 1103515245UL + 12345UL) >> 16);
}
/* values of mixed magnitude: 0..32 bits */
static DWORD rmag(void)
{
    DWORD v = rnd32();
    BYTE sh = (BYTE)(rnd32() % 33);
    return sh >= 32 ? v : (v >> sh);
}

// BENCH-NAMES: MulDivSmall,MulDivBig,PowDiv
#ifdef BENCH
void sim_halt(void);
void main(void)
{
    BYTE n;
    for (n = 0; n < BENCH_N; n++) {
#if BENCH == 1
        ScalerComputeDwordMulDiv(1000000UL, 3000UL, 77UL);
#elif BENCH == 2
        ScalerComputeDwordMulDiv(0xF0000000UL, 0xE0000000UL, 0x12345678UL);
#elif BENCH == 3
        ScalerComputeDwordPowDiv(0x12345678UL, 32, 0x2345678UL);
#endif
    }
    sim_halt();
}
#else
static BYTE fails, checks;
static void check(const char *tag, DWORD got, DWORD want)
{
    checks++;
    if (got != want) {
        if (fails < 4) { sim_puts("FAIL "); sim_val(tag, got); sim_val("want", want); }
        fails++;
    }
}
void main(void)
{
    BYTE i;
    static const DWORD edge[] = {0, 1, 0xFFFF, 0x10000, 0x80000000UL, 0xFFFFFFFFUL};
    BYTE j, k;
    for (i = 0; i < 6; i++)
        for (j = 0; j < 6; j++)
            for (k = 1; k < 6; k++)
                check("edge", ScalerComputeDwordMulDiv(edge[i], edge[j], edge[k]),
                      ref_ScalerComputeDwordMulDiv(edge[i], edge[j], edge[k]));
    for (i = 0; i < 40; i++) {
        DWORD a = rmag(), b = rmag(), c = rmag() | 1;
        check("muldiv", ScalerComputeDwordMulDiv(a, b, c), ref_ScalerComputeDwordMulDiv(a, b, c));
    }
    for (i = 0; i < 40; i++) {
        DWORD a = rnd32(), b = rnd32() | 1;       /* force overflow path */
        DWORD c = rmag() | 1;
        check("ovf", ScalerComputeDwordMulDiv(a | 0x80000000UL, b | 0x80000000UL, c),
              ref_ScalerComputeDwordMulDiv(a | 0x80000000UL, b | 0x80000000UL, c));
    }
    for (i = 0; i < 30; i++) {
        DWORD a = rmag(), b = rmag() | 1;
        BYTE p = (i < 4) ? (i == 0 ? 0 : i == 1 ? 1 : i == 2 ? 32 : 255) : (BYTE)(rnd32() % 40);
        check("pow", ScalerComputeDwordPowDiv(a, p, b), ref_ScalerComputeDwordPowDiv(a, p, b));
    }
#ifdef VARIANT_A
    /* divisor 0 (stock lib hangs, so asm only): x/0 = 0xFFFFFFFF, PowDiv(,pow,0) = 2 - 2^(pow+1) mod 2^32 */
    check("div0", ScalerComputeDwordMulDiv(5, 7, 0), 0xFFFFFFFFUL);
    check("div0z", ScalerComputeDwordMulDiv(0, 7, 0), 0xFFFFFFFFUL);
    check("pow0", ScalerComputeDwordPowDiv(0x1234, 0, 0), 0xFFFFFFFFUL + 1);        /* res=-1, +1 */
    check("pow3", ScalerComputeDwordPowDiv(0x1234, 3, 0), 2UL - 16UL);
    check("pow32", ScalerComputeDwordPowDiv(0x1234, 32, 0), 2UL);
#endif
    sim_val("checks", checks);
    sim_val("fails", fails);
    if (!fails) sim_puts("PASS\n");
    sim_done();
}
#endif
