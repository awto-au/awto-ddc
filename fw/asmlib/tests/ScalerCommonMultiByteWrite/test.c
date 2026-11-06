/* asm vs C-reference equivalence for ScalerCommonMultiByteWrite.asm (ScalerWrite); "registers" are xdata RAM. */
#include "sim.h"
typedef unsigned char BYTE;
typedef unsigned int WORD;
void ScalerWrite(WORD a, WORD len, BYTE *p, __bit nonauto);
void ref_ScalerWrite(WORD a, WORD len, BYTE *p, __bit nonauto);

static BYTE __xdata srcx[300], dstA[300], dstB[300];
static BYTE __idata srci[20];
static unsigned long seed = 0x2468ACE;
static BYTE rnd(void) { seed = seed * 1103515245UL + 12345UL; return (BYTE)(seed >> 16); }

// BENCH-NAMES: Write16,Write16fixed,Write256
#ifdef BENCH
void sim_halt(void);
void main(void)
{
    BYTE n;
    for (n = 0; n < BENCH_N; n++) {
#if BENCH == 1
        ScalerWrite((WORD)dstA, 16, srcx, 0);
#elif BENCH == 2
        ScalerWrite((WORD)dstA, 16, srcx, 1);
#elif BENCH == 3
        ScalerWrite((WORD)dstA, 256, srcx, 0);
#endif
    }
    sim_halt();
}
#else
void main(void)
{
    static const WORD lens[] = {0, 1, 2, 3, 17, 127, 255, 256, 257, 290};
    BYTE k, nonauto, fails = 0, checks = 0, i;
    WORD j;
    for (j = 0; j < 300; j++) srcx[j] = rnd();
    for (k = 0; k < sizeof(lens) / sizeof(lens[0]); k++)
        for (nonauto = 0; nonauto < 2; nonauto++) {
            for (j = 0; j < 300; j++) { dstA[j] = 0xA5; dstB[j] = 0xA5; }
            checks++;
            ScalerWrite((WORD)dstA + 2, lens[k], srcx + 3, nonauto);
            ref_ScalerWrite((WORD)dstB + 2, lens[k], srcx + 3, nonauto);
            for (j = 0; j < 300; j++) if (dstA[j] != dstB[j]) { fails++; sim_puts("FAIL xdata\n"); break; }
        }
    for (i = 0; i < 20; i++) srci[i] = rnd();
    for (nonauto = 0; nonauto < 2; nonauto++) {            /* generic (idata) source */
        BYTE len = 1 + (rnd() & 7);
        for (j = 0; j < 20; j++) { dstA[j] = 0x5A; dstB[j] = 0x5A; }
        checks++;
        ScalerWrite((WORD)dstA + 1, len, (BYTE *)srci + 1, nonauto);
        ref_ScalerWrite((WORD)dstB + 1, len, (BYTE *)srci + 1, nonauto);
        for (j = 0; j < 20; j++) if (dstA[j] != dstB[j]) { fails++; sim_puts("FAIL idata\n"); break; }
    }
    sim_val("checks", checks);
    sim_val("fails", fails);
    if (!fails) sim_puts("PASS\n");
    sim_done();
}
#endif
