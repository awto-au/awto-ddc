/* asm vs C-reference equivalence for ScalerCommonMultiByteRead.asm (ScalerRead); "registers" are xdata RAM. */
#include "sim.h"
typedef unsigned char BYTE;
typedef unsigned int WORD;
void ScalerRead(WORD a, WORD len, BYTE *p, __bit nonauto);
void ref_ScalerRead(WORD a, WORD len, BYTE *p, __bit nonauto);

static BYTE __xdata src[300], bufA[300], bufB[300];
static BYTE __idata ibufA[20], ibufB[20];
static unsigned long seed = 0x7654321;
static BYTE rnd(void) { seed = seed * 1103515245UL + 12345UL; return (BYTE)(seed >> 16); }

// BENCH-NAMES: Read16,Read16fixed,Read256
#ifdef BENCH
void sim_halt(void);
void main(void)
{
    BYTE n;
    for (n = 0; n < BENCH_N; n++) {
#if BENCH == 1
        ScalerRead((WORD)src, 16, bufA, 0);
#elif BENCH == 2
        ScalerRead((WORD)src, 16, bufA, 1);
#elif BENCH == 3
        ScalerRead((WORD)src, 256, bufA, 0);
#endif
    }
    sim_halt();
}
#else
void main(void)
{
    static const WORD lens[] = {0, 1, 2, 3, 17, 127, 255, 256, 257, 290};
    BYTE k, nonauto, fails = 0, checks = 0;
    WORD j;
    for (j = 0; j < 300; j++) src[j] = rnd();
    for (k = 0; k < sizeof(lens) / sizeof(lens[0]); k++)
        for (nonauto = 0; nonauto < 2; nonauto++) {
            for (j = 0; j < 300; j++) { bufA[j] = 0xA5; bufB[j] = 0xA5; }
            checks++;
            ScalerRead((WORD)src + 3, lens[k], bufA + 2, nonauto);
            ref_ScalerRead((WORD)src + 3, lens[k], bufB + 2, nonauto);
            for (j = 0; j < 300; j++) if (bufA[j] != bufB[j]) { fails++; sim_puts("FAIL xdata\n"); break; }
        }
    for (nonauto = 0; nonauto < 2; nonauto++) {            /* generic (idata) destination */
        BYTE i, len = 1 + (rnd() & 7);
        for (i = 0; i < 20; i++) { ibufA[i] = 0x5A; ibufB[i] = 0x5A; }
        checks++;
        ScalerRead((WORD)src + 1, len, (BYTE *)ibufA + 1, nonauto);
        ref_ScalerRead((WORD)src + 1, len, (BYTE *)ibufB + 1, nonauto);
        for (i = 0; i < 20; i++) if (ibufA[i] != ibufB[i]) { fails++; sim_puts("FAIL idata\n"); break; }
    }
    sim_val("checks", checks);
    sim_val("fails", fails);
    if (!fails) sim_puts("PASS\n");
    sim_done();
}
#endif
