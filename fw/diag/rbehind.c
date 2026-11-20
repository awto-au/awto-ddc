// Read-behind helper: first read of a new aligned dword on the PHY pages returns the old dword's lane (re/regmap/README.md "Read-behind")
#include "SysInclude.h"

#define AWTO_RB_S(pg) [(pg) - AWTO_RB_FIRST_PAGE] = 1 // 1 = read-behind page

// pages = re/regmap/read_behind.tsv "live" yes / yes+other
static const __code BYTE tAwtoRbPage[AWTO_RB_LAST_PAGE - AWTO_RB_FIRST_PAGE + 1] = {
    AWTO_RB_S(0x88), AWTO_RB_S(0x8A), AWTO_RB_S(0x8B), AWTO_RB_S(0x8E), AWTO_RB_S(0x8F), AWTO_RB_S(0x90),
    AWTO_RB_S(0xA0), AWTO_RB_S(0xA3), AWTO_RB_S(0xA4), AWTO_RB_S(0xA6), AWTO_RB_S(0xA7), AWTO_RB_S(0xA8),
    AWTO_RB_S(0xAB), AWTO_RB_S(0xAC), AWTO_RB_S(0xAE), AWTO_RB_S(0xAF),
    AWTO_RB_S(0xC8), AWTO_RB_S(0xCA), AWTO_RB_S(0xCB), AWTO_RB_S(0xCE), AWTO_RB_S(0xCF), AWTO_RB_S(0xD0),
};

volatile __xdata WORD isr_g_usAwtoRbLast = AWTO_RB_NO_DWORD; // last dword (addr >> 2) read on a listed page; the debug-slave ISR resets it (its reads move the page cache)

void AwtoRbPrime(WORD usAddr)
{
    if(AWTO_RB_IN(usAddr, AWTO_RB_FIRST_PAGE, AWTO_RB_LAST_PAGE) == 0)
    {
        return;
    }
    if((tAwtoRbPage[(BYTE)(usAddr >> 8) - AWTO_RB_FIRST_PAGE] != 0) && (isr_g_usAwtoRbLast != (usAddr >> 2)))
    {
        isr_g_usAwtoRbLast = usAddr >> 2;
        AWTO_XFR(usAddr); // dummy read: returns the old dword's lane, loads this dword
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
