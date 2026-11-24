#include "UserCommonInclude.h"
#include "AwtoApps.h"
#if(_AWTO_EXTRA_APPS == _ON)
#include "apps_gen.inc"                                             // AWTO_APP_COUNT + dispatchers of the AWTO_APP table (scripts/gen_awto_apps.py)

// Hooks of extra apps (docs/extra-apps.md): VCP 0xEB 0x20.., debug byte g_ucAwtoAppReq, key forward, main-loop step.
// The DDC/CI handler only records the request: a draw on its stack overflows IRAM (as the saver did); the main loop serves it.

#define AWTO_APPS_ARG                           0x79                // sync line E9 (as the saver start / stop): value = AWTO_APPS_RUN | index
#define AWTO_APPS_RUN                           0xF0                // run nibble of that value: an extra app
#define AWTO_APPS_REQ_NONE                      0
#define AWTO_APPS_VCP_STOP                      0
#define AWTO_APPS_KEV_MASK                      0x7F                // key event without the AWTO_KEV_INJ flag
#define AWTO_APPS_RND_SEED_OR                   1                   // xorshift state must not be 0
#define AWTO_APPS_RND_A                         7                   // xorshift16 shifts 7, 9, 8 (full period)
#define AWTO_APPS_RND_B                         9
#define AWTO_APPS_RND_C                         8
#define AWTO_APPS_HOLD_MASK                     AWTO_HOLD_POPUP     // isr_g_stAwtoDiag.ucHold bit that keeps SDK OSD resets off a drawn screen

__xdata BYTE g_ucAwtoAppRun;                                        // 0 = none, else index + 1
__xdata BYTE g_ucAwtoAppReq;                                        // debug / VCP request: index + 1 start, AWTO_APPS_REQ_STOP stop
static __xdata BYTE s_ucStartMode;                                  // SysModeGetModeState at the start: another mode = the SDK redraws the OSD, the app ends
static __xdata BYTE s_ucDrew;                                       // AwtoAppScreenBegin ran: stop closes the screen
static __xdata WORD s_usRnd;

BYTE AwtoAppsVcp(BYTE ucCode, WORD usV)                             // vcp_set (fw/rtdfw/awto/settings/vcp.c): 1 = taken
{
    if(ucCode != AWTO_SAVER_VCP)
    {
        return 0;
    }
    if(usV == AWTO_APPS_VCP_STOP)
    {
        g_ucAwtoAppReq = AWTO_APPS_REQ_STOP;                        // the saver path stops its own screens as before
        return 0;
    }
    if(usV >= AWTO_APPS_VCP_BASE)                                   // out of range is dropped here: the registry would clamp it to a saver value
    {
        if((usV - AWTO_APPS_VCP_BASE) < AWTO_APP_COUNT)
        {
            g_ucAwtoAppReq = (BYTE)(usV - AWTO_APPS_VCP_BASE + 1);
        }
        return 1;
    }
    return 0;
}

void AwtoAppScreenEnd(void)
{
    s_ucDrew = 0;
    isr_g_stAwtoDiag.ucHold &= ~AWTO_APPS_HOLD_MASK;
    AwtoOsdScreenOff();
}

void AwtoAppStop(void)
{
    BYTE ucI = g_ucAwtoAppRun;

    if(ucI == 0)
    {
        return;
    }
    g_ucAwtoAppRun = 0;
    AwtoAppDoStop(ucI - 1);
    if(s_ucDrew != 0)
    {
        AwtoAppScreenEnd();
    }
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_APPS_ARG, 0);
}

static void AppStart(BYTE ucI)
{
    AwtoAppStop();
    s_ucStartMode = SysModeGetModeState();
    s_ucDrew = 0;
    s_usRnd = (WORD)AwtoMs() | AWTO_APPS_RND_SEED_OR;
    g_ucAwtoAppRun = ucI + 1;
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_APPS_ARG, (BYTE)(AWTO_APPS_RUN | ucI));
    AwtoAppDoInit(ucI);
}

void AwtoAppsPoll(void)                                             // main loop, once per pass
{
    BYTE ucReq = g_ucAwtoAppReq;

    if(ucReq != AWTO_APPS_REQ_NONE)
    {
        g_ucAwtoAppReq = AWTO_APPS_REQ_NONE;
        if(ucReq == AWTO_APPS_REQ_STOP)
        {
            AwtoAppStop();
        }
        else if((ucReq <= AWTO_APP_COUNT) && (SysPowerGetPowerStatus() == _POWER_STATUS_NORMAL))
        {
            AppStart(ucReq - 1);
        }
    }
    if(g_ucAwtoAppRun == 0)
    {
        return;
    }
    if((SysPowerGetPowerStatus() != _POWER_STATUS_NORMAL) || (SysModeGetModeState() != s_ucStartMode))
    {
        AwtoAppStop();                                              // power saving / off: drawing resets the chip; another mode: the SDK reset the OSD
        return;
    }
    AwtoAppDoStep(g_ucAwtoAppRun - 1);
}

BYTE AwtoAppsKey(BYTE ucKey, BYTE ucEv)                             // keys.c AwtoKeyRouteDo: 1 = the running app took the key
{
    if(g_ucAwtoAppRun == 0)
    {
        return 0;
    }
    if(ucKey == AWTO_K_POWER)
    {
        AwtoAppStop();                                              // POWER keeps its normal action
        return 0;
    }
    if(AwtoAppHasKey(g_ucAwtoAppRun - 1) != 0)
    {
        AwtoAppDoKey(g_ucAwtoAppRun - 1, ucKey, ucEv & AWTO_APPS_KEV_MASK);     // injected keys look like front keys
    }
    else if((ucEv & AWTO_APPS_KEV_MASK) == AWTO_KEV_PRESS)
    {
        AwtoAppStop();
    }
    return 1;
}

WORD AwtoAppRandom(void)
{
    s_usRnd ^= s_usRnd << AWTO_APPS_RND_A;
    s_usRnd ^= s_usRnd >> AWTO_APPS_RND_B;
    s_usRnd ^= s_usRnd << AWTO_APPS_RND_C;
    return s_usRnd;
}

void AwtoAppScreenBegin(void)
{
    s_ucDrew = 1;
    AwtoOsdScreenBegin();
    isr_g_stAwtoDiag.ucHold |= AWTO_APPS_HOLD_MASK;
}

WORD AwtoAppCellAddr(WORD usBase, WORD usCell, WORD usCells)
{
    return usBase + ((g_ucAwtoOsdRot != 0) ? AwtoOsdRotCell(usCell, usCells) : usCell);
}

void AwtoAppCells(WORD usAddr, const BYTE __xdata *pucB, WORD usWords)
{
    WORD usI;

    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usAddr, _OSD_WITHOUT_DB);
    for(usI = 0; usI < usWords * AWTO_APPS_WORD_BYTES; usI++)
    {
        AWTO_OSD_PORT(pucB[usI]);
    }
}

void AwtoAppTurn(BYTE __xdata *pucB, BYTE ucBytes)
{
    BYTE ucLo = 0;
    BYTE ucHi = ucBytes - 1;
    BYTE ucT;

    while(ucLo < ucHi)
    {
        ucT = AwtoOsdRevByte(pucB[ucLo]);
        pucB[ucLo++] = AwtoOsdRevByte(pucB[ucHi]);
        pucB[ucHi--] = ucT;
    }
    if(ucLo == ucHi)
    {
        pucB[ucLo] = AwtoOsdRevByte(pucB[ucLo]);
    }
}

void AwtoAppGlyph(WORD usAddr, BYTE __xdata *pucB, BYTE ucBytes)
{
    BYTE ucK;

    if(g_ucAwtoOsdRot != 0)
    {
        AwtoAppTurn(pucB, ucBytes);
    }
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usAddr, _OSD_WITHOUT_DB);
    for(ucK = 0; ucK < ucBytes; ucK += AWTO_APPS_WORD_BYTES)
    {
        AWTO_OSD_PORT(pucB[ucK + 2]);
        AWTO_OSD_PORT(pucB[ucK + 1]);
        AWTO_OSD_PORT(pucB[ucK]);
    }
}
#endif
