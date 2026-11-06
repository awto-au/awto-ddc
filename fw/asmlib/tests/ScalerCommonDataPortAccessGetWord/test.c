/* asm vs C-reference equivalence for ScalerCommonDataPortAccessGetWord.asm; "port" windows are xdata RAM.
   Window is plain RAM, so hi == lo == last write at a+1; the two index writes make hi/lo order testable only via
   the final a-byte; use a pre-seeded a+1 and compare return value + window. */
#include "sim.h"
typedef unsigned char BYTE;
typedef unsigned int WORD;
WORD ScalerGetDataPortWord(WORD a, BYTE v, __bit nonauto);
WORD ref_ScalerGetDataPortWord(WORD a, BYTE v, __bit nonauto);

#define WA ((volatile BYTE __xdata *)0xC000)
#define WB ((volatile BYTE __xdata *)0xC100)
static unsigned long seed = 0x1357911;
static BYTE rnd(void) { seed = seed * 1103515245UL + 12345UL; return (BYTE)(seed >> 16); }

// BENCH-NAMES: GetWord
#ifdef BENCH
void sim_halt(void);
void main(void)
{
    BYTE n;
    for (n = 0; n < BENCH_N; n++)
        ScalerGetDataPortWord(0xC000, 0x12, 0);
    sim_halt();
}
#else
void main(void)
{
    BYTE n, i, fails = 0;
    for (n = 0; n < 200; n++) {
        BYTE v = (n < 4) ? 0xFE + n : rnd(), off = rnd() & 3, nonauto = n & 1;
        WORD ra, rb;
        for (i = 0; i < 8; i++) { BYTE r = rnd(); WA[i] = r; WB[i] = r; }
        ra = ScalerGetDataPortWord(0xC000 + off, v, nonauto);
        rb = ref_ScalerGetDataPortWord(0xC100 + off, v, nonauto);
        if (ra != rb) fails++;
        for (i = 0; i < 8; i++) if (WA[i] != WB[i]) { fails++; break; }
    }
    sim_val("fails", fails);
    if (!fails) sim_puts("PASS\n");
    sim_done();
}
#endif
