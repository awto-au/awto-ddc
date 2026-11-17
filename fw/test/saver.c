#include <stdint.h>
#include "UserCommonInclude.h"

// Screensavers (docs/screensaver.md): Pac-Man (pacman_classic.c) and the scope (scope_saver.c), run from the main loop.
// Settings 119 screensaver (Off / Pac-Man / Scope / Scope 2 / Alternate), 120 screensaver_s (idle seconds, 0 = none), 121 screensaver_now (DDC/CI VCP 0xEB).
// Starts: no signal for AWTO_SAVER_NOSIG_MS with a mode set; idle with a picture for screensaver_s; DDC/CI / test cmd now.
// Stops: a key, a DDC/CI command (not VCP 0xEB), mode no longer the one that started it, VCP 0xEB = 0.
extern void AwtoPacmanClassic(BYTE ucCmd);
extern void AwtoScopeSaver(BYTE ucCmd);
extern void AwtoScopeSaver2(BYTE ucCmd);

#define AWTO_SAVER_OFF                          0
#define AWTO_SAVER_PACMAN                       1
#define AWTO_SAVER_SCOPE                        2
#define AWTO_SAVER_SCOPE2                       3
#define AWTO_SAVER_ALTERNATE                    4
#define AWTO_SAVER_WHY_NONE                     0
#define AWTO_SAVER_WHY_NOSIG                    1
#define AWTO_SAVER_WHY_IDLE                     2
#define AWTO_SAVER_WHY_NOW                      3
#define AWTO_SAVER_NOSIG_MS                     10000UL             // no signal this long: the source search has ended (SDK search + hold are ~4 s; start = 2.5x)
#define AWTO_SAVER_ALT_MS                       120000UL            // Alternate: one saver for 2 min, then the other
#define AWTO_SAVER_PACMAN_MS                    125UL               // Pac-Man step period (pacman_unit.py: 8 steps/s)
#define AWTO_SAVER_SCOPE2_MS                    500UL               // scope 2 frame period (84 passes of the trace plane; unit measurement pending)
#define AWTO_SAVER_SCOPE_MS                     250UL               // scope frame period (a frame is 64 passes of tile uploads; measured on the unit, awto-ddc docs/screensaver.md)
#define AWTO_SAVER_MS_PER_S                     1000UL
#define AWTO_SAVER_ARG_START                    0x79                // sync line E9: value = what (run << 4 | why)
#define AWTO_SAVER_ARG_STOP                     0x7A
#define AWTO_SAVER_NOW_STOP                     0
#define AWTO_SAVER_NOW_SELECTED                 1
#define AWTO_SAVER_RUN_SHIFT                    4

__xdata BYTE g_ucAwtoSaverMode;
__xdata WORD g_usAwtoSaverIdleS;
__xdata BYTE g_ucAwtoSaverRun;                                       // AWTO_SAVER_PACMAN / SCOPE while one runs, else OFF
__xdata BYTE g_ucAwtoSaverWhy;
#define AWTO_SAVER_REQ_NONE                     0xFF
static __xdata BYTE s_ucReq = AWTO_SAVER_REQ_NONE;                  // set by the DDC/CI apply, served by AwtoSaverPoll: a draw on the DDC handler's stack overflows IRAM and blocks DDC for its whole length
static __xdata unsigned long s_ulAct;                               // last key / DDC activity
static __xdata unsigned long s_ulTick;                              // last frame
static __xdata unsigned long s_ulSwap;                              // run started / last swap (Alternate)
static __xdata unsigned long s_ulNoSig;                             // no-signal since (0 = not in no-signal)

void AwtoSaverActivity(void)
{
    s_ulAct = AwtoMs();
    if((g_ucAwtoSaverRun != AWTO_SAVER_OFF) && (g_ucAwtoSaverWhy != AWTO_SAVER_WHY_NOW))
    {
        AwtoSaverStop();
    }
}

static void SaverDraw(BYTE ucRun)
{
    if(g_ucAwtoSaverRun == AWTO_SAVER_PACMAN)
    {
        AwtoPacmanClassic(0);
    }
    else if(g_ucAwtoSaverRun == AWTO_SAVER_SCOPE)
    {
        AwtoScopeSaver(0);
    }
    else if(g_ucAwtoSaverRun == AWTO_SAVER_SCOPE2)
    {
        AwtoScopeSaver2(0);
    }
    g_ucAwtoSaverRun = ucRun;
    if(ucRun == AWTO_SAVER_PACMAN)
    {
        AwtoPacmanClassic(1);
    }
    else if(ucRun == AWTO_SAVER_SCOPE)
    {
        AwtoScopeSaver(1);
    }
    else if(ucRun == AWTO_SAVER_SCOPE2)
    {
        AwtoScopeSaver2(1);
    }
    s_ulTick = AwtoMs();
    s_ulSwap = s_ulTick;
}

void AwtoSaverStart(BYTE ucWhich, BYTE ucWhy)                      // ucWhich: PACMAN / SCOPE / ALTERNATE
{
    BYTE ucRun = ((ucWhich == AWTO_SAVER_SCOPE) || (ucWhich == AWTO_SAVER_SCOPE2)) ? ucWhich : AWTO_SAVER_PACMAN;

    g_ucAwtoSaverWhy = ucWhy;
    SaverDraw(ucRun);
    s_ulAct = AwtoMs();
    if(ucWhich == AWTO_SAVER_ALTERNATE)
    {
        g_ucAwtoSaverWhy |= 0x80;                                            // alternate flag, cleared in AwtoSaverStop
    }
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SAVER_ARG_START, (BYTE)((ucRun << AWTO_SAVER_RUN_SHIFT) | ucWhy));
}

void AwtoSaverStop(void)
{
    if(g_ucAwtoSaverRun == AWTO_SAVER_OFF)
    {
        return;
    }
    SaverDraw(AWTO_SAVER_OFF);
    g_ucAwtoSaverWhy = AWTO_SAVER_WHY_NONE;
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SAVER_ARG_STOP, 0);
}

void AwtoSaverPoll(void)                                            // main loop, once per pass
{
    unsigned long ulNow = AwtoMs();
    BYTE ucMode = SysModeGetModeState();

    if(s_ucReq != AWTO_SAVER_REQ_NONE)
    {
        BYTE ucReq = s_ucReq;

        s_ucReq = AWTO_SAVER_REQ_NONE;
        if(ucReq == AWTO_SAVER_NOW_STOP)
        {
            AwtoSaverStop();
        }
        else
        {
            AwtoSaverStart((ucReq == AWTO_SAVER_NOW_SELECTED) ? ((g_ucAwtoSaverMode == AWTO_SAVER_OFF) ? AWTO_SAVER_ALTERNATE : g_ucAwtoSaverMode) : (BYTE)(ucReq - 1), AWTO_SAVER_WHY_NOW);
        }
        return;
    }
    if(g_ucAwtoSaverRun != AWTO_SAVER_OFF)
    {
        if(((g_ucAwtoSaverWhy & 0x7F) == AWTO_SAVER_WHY_NOSIG) && (ucMode != _MODE_STATUS_NOSIGNAL))
        {
            AwtoSaverStop();                                        // a source locked
            return;
        }
        if((g_ucAwtoSaverWhy & 0x80) && ((ulNow - s_ulSwap) >= AWTO_SAVER_ALT_MS))
        {
            SaverDraw((g_ucAwtoSaverRun == AWTO_SAVER_PACMAN) ? AWTO_SAVER_SCOPE : ((g_ucAwtoSaverRun == AWTO_SAVER_SCOPE) ? AWTO_SAVER_SCOPE2 : AWTO_SAVER_PACMAN));
            return;
        }
        if((ulNow - s_ulTick) >= ((g_ucAwtoSaverRun == AWTO_SAVER_PACMAN) ? AWTO_SAVER_PACMAN_MS : ((g_ucAwtoSaverRun == AWTO_SAVER_SCOPE) ? AWTO_SAVER_SCOPE_MS : AWTO_SAVER_SCOPE2_MS)))
        {
            s_ulTick = ulNow;
            if(g_ucAwtoSaverRun == AWTO_SAVER_PACMAN)
            {
                AwtoPacmanClassic(2);
            }
            else if(g_ucAwtoSaverRun == AWTO_SAVER_SCOPE)
            {
                AwtoScopeSaver(2);
            }
            else
            {
                AwtoScopeSaver2(2);
            }
        }
        return;
    }
    if(g_ucAwtoSaverMode == AWTO_SAVER_OFF)
    {
        s_ulNoSig = 0;
        return;
    }
    if(ucMode == _MODE_STATUS_NOSIGNAL)
    {
        if(s_ulNoSig == 0)
        {
            s_ulNoSig = ulNow;
        }
        else if((ulNow - s_ulNoSig) >= AWTO_SAVER_NOSIG_MS)
        {
            AwtoSaverStart(g_ucAwtoSaverMode, AWTO_SAVER_WHY_NOSIG);
        }
        return;
    }
    s_ulNoSig = 0;
    if((ucMode == _MODE_STATUS_ACTIVE) && (g_usAwtoSaverIdleS != 0) && ((ulNow - s_ulAct) >= ((unsigned long)g_usAwtoSaverIdleS * AWTO_SAVER_MS_PER_S)))
    {
        AwtoSaverStart(g_ucAwtoSaverMode, AWTO_SAVER_WHY_IDLE);
    }
}

void set_ap_screensaver(BYTE ucId, int iV)
{
    ucId = ucId;
    g_ucAwtoSaverMode = (BYTE)iV;
}

void set_ap_screensaver_s(BYTE ucId, int iV)
{
    ucId = ucId;
    g_usAwtoSaverIdleS = (WORD)iV;
}

void set_ap_screensaver_now(BYTE ucId, int iV)                      // DDC/CI VCP 0xEB: recorded, the main loop acts
{
    ucId = ucId;
    s_ucReq = (BYTE)iV;
}
