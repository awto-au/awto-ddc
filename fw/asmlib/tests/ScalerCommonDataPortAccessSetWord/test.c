/* asm vs C-reference equivalence for ScalerCommonDataPortAccessSetWord.asm; "port" windows are xdata RAM. */
#include "sim.h"
typedef unsigned char BYTE;
typedef unsigned int WORD;
void ScalerSetDataPortWord(WORD a, BYTE v1, WORD v2);
void ref_ScalerSetDataPortWord(WORD a, BYTE v1, WORD v2);

#define WA ((volatile BYTE __xdata *)0xC000)
#define WB ((volatile BYTE __xdata *)0xC100)
static unsigned long seed = 0x1357911;
static BYTE rnd(void) { seed = seed * 1103515245UL + 12345UL; return (BYTE)(seed >> 16); }

// BENCH-NAMES: SetWord
#ifdef BENCH
void sim_halt(void);
void main(void)
{
    BYTE n;
    for (n = 0; n < BENCH_N; n++)
        ScalerSetDataPortWord(0xC000, 0x12, 0x3456);
    sim_halt();
}
#else
void main(void)
{
    BYTE n, i, fails = 0;
    for (n = 0; n < 200; n++) {
        BYTE v = (n < 4) ? 0xFE + n : rnd(), off = rnd() & 3;      /* includes v1+1 wrap */
        WORD w = ((WORD)rnd() << 8) | rnd();
        for (i = 0; i < 8; i++) { BYTE r = rnd(); WA[i] = r; WB[i] = r; }
        ScalerSetDataPortWord(0xC000 + off, v, w);
        ref_ScalerSetDataPortWord(0xC100 + off, v, w);
        for (i = 0; i < 8; i++) if (WA[i] != WB[i]) { fails++; break; }
    }
    sim_val("fails", fails);
    if (!fails) sim_puts("PASS\n");
    sim_done();
}
#endif
