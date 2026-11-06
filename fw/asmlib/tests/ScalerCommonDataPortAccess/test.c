/* asm vs C-reference equivalence for ScalerCommonDataPortAccess.asm; "port" windows are plain xdata RAM. */
#include "sim.h"
typedef unsigned char BYTE;
typedef unsigned int WORD;

void ScalerSetDataPortByte(WORD a, BYTE v1, BYTE v2);
void ScalerGetDataPortByte(WORD a, BYTE v, WORD len, BYTE *p, __bit nonauto);
void ScalerSetDataPortBit(WORD a, BYTE v, BYTE and, BYTE or);
BYTE ScalerGetDataPortBit(WORD a, BYTE v, BYTE and);
BYTE ScalerEnableAccessPort(WORD a, BYTE v);
void ref_ScalerSetDataPortByte(WORD a, BYTE v1, BYTE v2);
void ref_ScalerGetDataPortByte(WORD a, BYTE v, WORD len, BYTE *p, __bit nonauto);
void ref_ScalerSetDataPortBit(WORD a, BYTE v, BYTE and, BYTE or);
BYTE ref_ScalerGetDataPortBit(WORD a, BYTE v, BYTE and);

#define WA ((volatile BYTE __xdata *)0xC000)   /* asm window */
#define WB ((volatile BYTE __xdata *)0xC100)   /* ref window */
static BYTE __xdata bufA[300], bufB[300];
static BYTE __idata ibufA[20], ibufB[20];
static unsigned long seed = 0x1234567;
static BYTE rnd(void) { seed = seed * 1103515245UL + 12345UL; return (BYTE)(seed >> 16); }
static unsigned char fails, checks;

static void fail(const char *n) { if (fails < 8) { sim_puts("FAIL "); sim_puts(n); sim_putc('\n'); } fails++; }

static void seedwin(void)
{
    BYTE i;
    for (i = 0; i < 8; i++) { BYTE r = rnd(); WA[i] = r; WB[i] = r; }
}
static BYTE winsame(void)
{
    BYTE i;
    for (i = 0; i < 8; i++) if (WA[i] != WB[i]) return 0;
    return 1;
}

// BENCH-NAMES: SetByte,SetBit,GetBit,GetByte16,GetByte256
#ifdef BENCH
void sim_halt(void);
void main(void)
{
    BYTE n;
    for (n = 0; n < BENCH_N; n++) {
#if BENCH == 1
        ScalerSetDataPortByte(0xC000, 0x12, 0x34);
#elif BENCH == 2
        ScalerSetDataPortBit(0xC000, 0x12, 0xF0, 0x05);
#elif BENCH == 3
        ScalerGetDataPortBit(0xC000, 0x12, 0x0F);
#elif BENCH == 4
        ScalerGetDataPortByte(0xC000, 0x12, 16, bufA, 0);
#elif BENCH == 5
        ScalerGetDataPortByte(0xC000, 0x12, 256, bufA, 1);
#endif
    }
    sim_halt();
}
#else
void main(void)
{
    BYTE n, i;
    for (n = 0; n < 200; n++) {
        BYTE v = rnd(), v2 = rnd(), a1 = rnd(), o1 = rnd(), off = rnd() & 3;
        seedwin(); checks++;
        ScalerSetDataPortByte(0xC000 + off, v, v2); ref_ScalerSetDataPortByte(0xC100 + off, v, v2);
        if (!winsame()) fail("SetByte");
        seedwin(); checks++;
        ScalerSetDataPortBit(0xC000 + off, v, a1, o1); ref_ScalerSetDataPortBit(0xC100 + off, v, a1, o1);
        if (!winsame()) fail("SetBit");
        seedwin(); checks++;
        if (ScalerGetDataPortBit(0xC000 + off, v, a1) != ref_ScalerGetDataPortBit(0xC100 + off, v, a1) || !winsame()) fail("GetBit");
        if (ScalerEnableAccessPort(0xC000, v) != v) fail("Enable");
    }
    /* GetDataPortByte: xdata dest (fast path), lengths incl. 0, 1, 255, 256, 257; guard bytes around dest */
    {
        static const WORD lens[] = {0, 1, 2, 3, 127, 255, 256, 257, 290};
        BYTE k, nonauto;
        for (k = 0; k < sizeof(lens) / sizeof(lens[0]); k++) {
            for (nonauto = 0; nonauto < 2; nonauto++) {
                BYTE v = rnd();
                WORD j;
                for (j = 0; j < 300; j++) { bufA[j] = 0xA5; bufB[j] = 0xA5; }
                seedwin(); checks++;
                ScalerGetDataPortByte(0xC000, v, lens[k], bufA + 2, nonauto);
                ref_ScalerGetDataPortByte(0xC100, v, lens[k], bufB + 2, nonauto);
                if (!winsame()) fail("GetByte win");
                for (j = 0; j < 300; j++) if (bufA[j] != bufB[j]) { fail("GetByte buf"); break; }
            }
        }
    }
    /* generic (idata) destination: slow path through __gptrput */
    for (n = 0; n < 2; n++) {
        BYTE v = rnd(), len = 1 + (rnd() & 7);
        for (i = 0; i < 20; i++) { ibufA[i] = 0x5A; ibufB[i] = 0x5A; }
        seedwin(); checks++;
        ScalerGetDataPortByte(0xC000, v, len, (BYTE *)ibufA + 1, n);
        ref_ScalerGetDataPortByte(0xC100, v, len, (BYTE *)ibufB + 1, n);
        if (!winsame()) fail("GetByte idata win");
        for (i = 0; i < 20; i++) if (ibufA[i] != ibufB[i]) { fail("GetByte idata buf"); break; }
    }
    sim_val("checks", checks);
    sim_val("fails", fails);
    if (!fails) sim_puts("PASS\n");
    sim_done();
}
#endif
