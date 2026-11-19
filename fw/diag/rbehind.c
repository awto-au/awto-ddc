// Read-behind helper: first read of a new aligned dword on the PHY pages returns the old dword's lane (re/regmap/README.md "Read-behind")
#include "SysInclude.h"

#define AWTO_RB_NO_DWORD 0xFFFF // no listed page has this dword index (FFFC..FFFF is the MCU page)
#define AWTO_RB_S(pg) [(pg) - AWTO_RB_FIRST_PAGE] = 1 // 1 = read-behind page

// pages = re/regmap/read_behind.tsv "live" yes / yes+other
static const __code BYTE tAwtoRbPage[AWTO_RB_LAST_PAGE - AWTO_RB_FIRST_PAGE + 1] = {
    AWTO_RB_S(0x88), AWTO_RB_S(0x8A), AWTO_RB_S(0x8B), AWTO_RB_S(0x8E), AWTO_RB_S(0x8F), AWTO_RB_S(0x90),
    AWTO_RB_S(0xA0), AWTO_RB_S(0xA3), AWTO_RB_S(0xA4), AWTO_RB_S(0xA6), AWTO_RB_S(0xA7), AWTO_RB_S(0xA8),
    AWTO_RB_S(0xAB), AWTO_RB_S(0xAC), AWTO_RB_S(0xAE), AWTO_RB_S(0xAF),
    AWTO_RB_S(0xC8), AWTO_RB_S(0xCA), AWTO_RB_S(0xCB), AWTO_RB_S(0xCE), AWTO_RB_S(0xCF), AWTO_RB_S(0xD0),
};

static __xdata WORD s_usAwtoRbLast; // last dword index (addr >> 2) read on any listed page: a page switch costs one extra dummy read, never a missed one
__xdata BYTE g_aucAwtoRbCount[2];                   // [0] dummy reads done, [1] dummy != re-read (the artifact seen from the firmware; dbg-read g_aucAwtoRbCount)
__xdata BYTE g_ucAwtoRbOff;                         // dbg-write 1: no dummy reads (raw reads, hardware A/B on a running unit)
volatile __xdata BYTE isr_g_ucAwtoRbDirty = 1;          // set by the debug slave ISR: its reads move the page cache

void AwtoRbPrime(WORD usAddr)
{
    BYTE ucStale;

    if((g_ucAwtoRbOff != 0) || (AWTO_RB_IN(usAddr, AWTO_RB_FIRST_PAGE, AWTO_RB_LAST_PAGE) == 0))
    {
        return;
    }
    if(isr_g_ucAwtoRbDirty != 0)
    {
        s_usAwtoRbLast = AWTO_RB_NO_DWORD;
        isr_g_ucAwtoRbDirty = 0;
    }
    if((tAwtoRbPage[(BYTE)(usAddr >> 8) - AWTO_RB_FIRST_PAGE] != 0) && (s_usAwtoRbLast != (usAddr >> 2)))
    {
        s_usAwtoRbLast = usAddr >> 2;
        ucStale = AWTO_XFR(usAddr); // dummy read: returns the old dword's lane, loads this dword
        g_aucAwtoRbCount[0]++;
        g_aucAwtoRbCount[1] += (ucStale != AWTO_XFR(usAddr));
    }
}

BYTE AwtoRbGetByte(WORD usAddr)
{
    AwtoRbPrime(usAddr);
    return AWTO_XFR(usAddr);
}

BYTE AwtoRbGetBit(WORD usAddr, BYTE ucAnd)
{
    AwtoRbPrime(usAddr);
    return AWTO_XFR(usAddr) & ucAnd;
}

WORD AwtoRbGetWord(WORD usAddr)
{
    AwtoRbPrime(usAddr);
    return *(volatile __xdata WORD *)usAddr;
}

DWORD AwtoRbGetDWord(WORD usAddr)
{
    AwtoRbPrime(usAddr);
    return *(volatile __xdata DWORD *)usAddr;
}
