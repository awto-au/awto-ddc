// Read-behind helper: first read of a new aligned dword on the PHY pages returns the old dword's lane (re/regmap/README.md "Read-behind")
#include "SysInclude.h"

#define AWTO_RB_SLOTS 22
#define AWTO_RB_NO_DWORD 0xFFFF // no listed page has this dword index (FFFC..FFFF is the MCU page)
#define AWTO_RB_S(pg, n) [(pg) - AWTO_RB_FIRST_PAGE] = (n) // slot n + 1: 0 = page is not read-behind

// pages = re/regmap/read_behind.tsv "live" yes / yes+other
static const __code BYTE tAwtoRbSlot[AWTO_RB_LAST_PAGE - AWTO_RB_FIRST_PAGE + 1] = {
    AWTO_RB_S(0x88, 1), AWTO_RB_S(0x8A, 2), AWTO_RB_S(0x8B, 3), AWTO_RB_S(0x8E, 4), AWTO_RB_S(0x8F, 5), AWTO_RB_S(0x90, 6),
    AWTO_RB_S(0xA0, 7), AWTO_RB_S(0xA3, 8), AWTO_RB_S(0xA4, 9), AWTO_RB_S(0xA6, 10), AWTO_RB_S(0xA7, 11), AWTO_RB_S(0xA8, 12),
    AWTO_RB_S(0xAB, 13), AWTO_RB_S(0xAC, 14), AWTO_RB_S(0xAE, 15), AWTO_RB_S(0xAF, 16),
    AWTO_RB_S(0xC8, 17), AWTO_RB_S(0xCA, 18), AWTO_RB_S(0xCB, 19), AWTO_RB_S(0xCE, 20), AWTO_RB_S(0xCF, 21), AWTO_RB_S(0xD0, 22),
};

static __xdata WORD s_ausAwtoRbLast[AWTO_RB_SLOTS]; // last dword index (addr >> 2) read per page
__xdata BYTE g_aucAwtoRbCount[2];                   // [0] dummy reads done, [1] dummy != re-read (the artifact seen from the firmware; dbg-read g_aucAwtoRbCount)
volatile __xdata BYTE isr_g_ucAwtoRbDirty = 1;          // set by the debug slave ISR: its reads move the page cache

void AwtoRbPrime(WORD usAddr)
{
    BYTE ucStale;
    BYTE ucSlot = tAwtoRbSlot[(BYTE)(usAddr >> 8) - AWTO_RB_FIRST_PAGE];

    if(isr_g_ucAwtoRbDirty != 0)
    {
        BYTE ucI;

        for(ucI = 0; ucI < AWTO_RB_SLOTS; ucI++)
        {
            s_ausAwtoRbLast[ucI] = AWTO_RB_NO_DWORD;
        }
        isr_g_ucAwtoRbDirty = 0;
    }
    if(ucSlot != 0)
    {
        ucSlot--;
        if(s_ausAwtoRbLast[ucSlot] != (usAddr >> 2))
        {
            s_ausAwtoRbLast[ucSlot] = usAddr >> 2;
            ucStale = AWTO_XFR(usAddr); // dummy read: returns the old dword's lane, loads this dword
            g_aucAwtoRbCount[0]++;
            g_aucAwtoRbCount[1] += (ucStale != AWTO_XFR(usAddr));
        }
    }
}
