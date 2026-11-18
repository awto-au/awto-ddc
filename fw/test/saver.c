#include <stdint.h>
#include "UserCommonInclude.h"

// Screensavers (docs/screensaver.md): Pac-Man (pacman_classic.c), the scopes (scope_saver.c, scope_saver2.c) and Asteroids (asteroids.c), run from the main loop.
// Settings 119 screensaver (Off / Pac-Man / Scope / Scope 2 / Alternate / Asteroids), 120 screensaver_s (idle seconds, 0 = none), 121 screensaver_now (DDC/CI VCP 0xEB).
// Starts: no signal for AWTO_SAVER_NOSIG_MS with a mode set; idle with a picture for screensaver_s; DDC/CI / test cmd now.
// Stops: a key, a DDC/CI command (ends no-signal / idle, not a "now" or boot saver: D4), mode no longer the one that started it (no signal: NOSIGNAL, idle: ACTIVE), VCP 0xEB = 0.
// No-signal saver (docs/saver-mode.md D1): replaces the SDK no-signal card, drops SDK pop-ups, runs pwr_l3_s s, then the SDK chain (card, power saving) resumes.
extern void AwtoPacmanClassic(BYTE ucCmd);
extern BYTE AwtoScopeSaver(BYTE ucCmd);
extern BYTE AwtoScopeSaver2(BYTE ucCmd);
extern BYTE AwtoAsteroids(BYTE ucCmd);

#define AWTO_SAVER_OFF                          0
#define AWTO_SAVER_PACMAN                       1
#define AWTO_SAVER_SCOPE                        2
#define AWTO_SAVER_SCOPE2                       3
#define AWTO_SAVER_ALTERNATE                    4
#define AWTO_SAVER_FLASH                        5                   // flash warning screen (VCP 0xEB = 5 only, never selected / alternated)
#define AWTO_SAVER_SPLASH                       6                   // boot splash screen (flash drawing, splash title): preview by VCP 0xEB = 7, and the power-on run (why = boot)
#define AWTO_SAVER_ASTEROIDS                    7                   // run id; the setting 119 choice is AWTO_SAVER_SET_ASTEROIDS
#define AWTO_SAVER_SET_ASTEROIDS                5                   // setting 119 value (5 is the flash run id: mapped by SAVER_MODE_RUN)
#define AWTO_SAVER_WHY_NONE                     0
#define AWTO_SAVER_WHY_NOSIG                    1
#define AWTO_SAVER_WHY_IDLE                     2
#define AWTO_SAVER_WHY_NOW                      3
#define AWTO_SAVER_WHY_BOOT                     4                   // boot splash (docs/flash-screen.md): the flash screen drawing, shown a step per main pass
#define AWTO_SAVER_SPLASH_DONE                  0xFF                // s_ucMid: all draw steps done
#define AWTO_SPLASH_MAX_MS                      3000UL              // hard cap: 4x the sim power-on -> ACTIVE (~0.75 s), = console hold AWTO_CON_HOLD_MS; expiry = splash closes
#define AWTO_SAVER_NOSIG_MS                     1800UL              // no signal this long (mode NOSIGNAL): 90 % of the SDK card timer SEC(2), so the saver is up before the card event
#define AWTO_SAVER_WHY_MASK                     0x7F                // bit 7 of the why = Alternate
#define AWTO_SAVER_ALT_MS                       120000UL            // Alternate: one saver for 2 min, then the other
#define AWTO_SAVER_PACMAN_MS                    31UL                // Pac-Man sub-step period
#define AWTO_SAVER_PACMAN_SUBS                  4                   // sub-steps per game step
#define AWTO_SAVER_PACMAN_STEP_MS               125UL               // game step = 8 steps/s as pacman_unit.py: sub-steps 31, 31, 31, 32 ms
#define AWTO_SAVER_SCOPE2_MS                    1UL                 // pause between scope 2 frames (columns are drawn per main pass within a time budget: scope_saver2.c)
#define AWTO_SAVER_SCOPE_MS                     100UL               // pause between scope frames
#define AWTO_SAVER_MS_PER_S                     1000UL
#define AWTO_SAVER_ARG_START                    0x79                // sync line E9: value = what (run << 4 | why)
#define AWTO_SAVER_ARG_STOP                     0x79                // same line as the start, value 0
#define AWTO_SAVER_NOW_STOP                     0
#define AWTO_SAVER_NOW_SELECTED                 1
#define AWTO_SAVER_NOW_FLASH                    5
#define AWTO_SAVER_NOW_ALERT                    6                   // 1 s alert tone on the speaker (no screen)
#define AWTO_SAVER_NOW_SPLASH                   7                   // preview of the boot splash
#define AWTO_SAVER_NOW_ASTEROIDS                8
#define AWTO_SAVER_SND_ALERT                    5                   // AwtoPmSound(cmd): alert
#define AWTO_SAVER_RUN_SHIFT                    4

__xdata BYTE g_ucAwtoSaverMode;
__xdata WORD g_usAwtoSaverIdleS;
__xdata BYTE g_ucAwtoSaverRun;                                       // AWTO_SAVER_PACMAN / SCOPE while one runs, else OFF
__xdata BYTE g_ucAwtoSaverWhy;
__xdata WORD g_usAwtoSaverNosigS;                                    // settings row 80 pwr_l3_s: seconds the no-signal saver runs before power saving (0 = no no-signal saver)
#define AWTO_SAVER_REQ_NONE                     0xFF
static __xdata BYTE s_ucReq = AWTO_SAVER_REQ_NONE;                  // set by the DDC/CI apply, served by AwtoSaverPoll: a draw on the DDC handler's stack overflows IRAM and blocks DDC for its whole length
static __xdata BYTE s_ucMid;                                        // a scope frame is part drawn
static __xdata unsigned long s_ulAct;                               // last key / DDC activity
static __xdata WORD s_usTick;                                       // last frame (ms, low word: the periods are <= 125 ms)
static __xdata unsigned long s_ulSwap;                              // run started / last swap (Alternate)
static __xdata unsigned long s_ulNoSig;                             // no-signal since (0 = not in no-signal)
static __xdata BYTE s_ucSub;                                        // Pac-Man sub-step 0..AWTO_SAVER_PACMAN_SUBS-1
static __xdata BYTE s_ucNoSigDone;                                  // the no-signal saver ended in this no-signal episode: it does not restart (no saver -> card -> saver loop)

void AwtoSaverActivity(void)                                        // a DDC/CI command does not end a "now" saver (host tools talk to it) or the boot splash; a key does: AwtoSaverKey
{
    s_ulAct = AwtoMs();
    if((g_ucAwtoSaverRun != AWTO_SAVER_OFF) && ((g_ucAwtoSaverWhy & AWTO_SAVER_WHY_MASK) != AWTO_SAVER_WHY_NOW) && ((g_ucAwtoSaverWhy & AWTO_SAVER_WHY_MASK) != AWTO_SAVER_WHY_BOOT))
    {
        AwtoSaverStop();
    }
}

void AwtoSaverKey(void)                                             // a front key: also ends the boot splash
{
    AwtoSaverActivity();
    if(g_ucAwtoSaverWhy == AWTO_SAVER_WHY_BOOT)
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
    else if(g_ucAwtoSaverRun == AWTO_SAVER_ASTEROIDS)
    {
        AwtoAsteroids(0);
    }
    else if((g_ucAwtoSaverRun == AWTO_SAVER_FLASH) || (g_ucAwtoSaverRun == AWTO_SAVER_SPLASH))
    {
        AwtoFlashScreen(0);
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
    else if(ucRun == AWTO_SAVER_ASTEROIDS)
    {
        AwtoAsteroids(1);
    }
    else if(ucRun == AWTO_SAVER_FLASH)
    {
        AwtoFlashScreen(1);
    }
    else if(ucRun == AWTO_SAVER_SPLASH)
    {
        AwtoFlashScreen(2);
    }
    s_ulSwap = AwtoMs();
    s_usTick = (WORD)s_ulSwap;
    s_ucSub = 0;
    s_ucMid = 1;                                                    // a scope starts with its first frame, drawn hidden
}

#define SAVER_MODE_RUN(m)                      (((m) == AWTO_SAVER_SET_ASTEROIDS) ? AWTO_SAVER_ASTEROIDS : (m))

void AwtoSaverStart(BYTE ucWhich, BYTE ucWhy)                      // ucWhich: PACMAN / SCOPE / SCOPE2 / ASTEROIDS / ALTERNATE / FLASH
{
    BYTE ucRun = ((ucWhich == AWTO_SAVER_SCOPE) || (ucWhich == AWTO_SAVER_SCOPE2) || (ucWhich == AWTO_SAVER_ASTEROIDS) || (ucWhich == AWTO_SAVER_FLASH) || (ucWhich == AWTO_SAVER_SPLASH)) ? ucWhich : AWTO_SAVER_PACMAN;

    g_ucAwtoSaverWhy = ucWhy;
    SaverDraw(ucRun);
    s_ulAct = AwtoMs();
    if(ucWhich == AWTO_SAVER_ALTERNATE)
    {
        g_ucAwtoSaverWhy |= 0x80;                                            // alternate flag, cleared in AwtoSaverStop
    }
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SAVER_ARG_START, (BYTE)((ucRun << AWTO_SAVER_RUN_SHIFT) | ucWhy));
}

static void SplashEnd(void)                                         // the OSD belongs to someone else: no redraw, no close
{
    g_ucAwtoSaverRun = AWTO_SAVER_OFF;
    g_ucAwtoSaverWhy = AWTO_SAVER_WHY_NONE;
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SAVER_ARG_STOP, 0);
}

void AwtoSaverTaken(void)                                           // OsdDispDisableOsd got past the hold: the console / a test command took the OSD
{
    if(g_ucAwtoSaverWhy == AWTO_SAVER_WHY_BOOT)
    {
        SplashEnd();
    }
}

void AwtoSaverStop(void)
{
    if(g_ucAwtoSaverRun == AWTO_SAVER_OFF)
    {
        return;
    }
    if(g_ucAwtoSaverWhy == AWTO_SAVER_WHY_BOOT)
    {
        isr_g_stAwtoDiag.ucHold &= ~AWTO_HOLD_POPUP;
    }
    if((g_ucAwtoSaverWhy & AWTO_SAVER_WHY_MASK) == AWTO_SAVER_WHY_NOSIG)
    {
        s_ucNoSigDone = 1;                                          // until the no-signal state ends
    }
    SaverDraw(AWTO_SAVER_OFF);
    g_ucAwtoSaverWhy = AWTO_SAVER_WHY_NONE;
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SAVER_ARG_STOP, 0);
}

static void SaverNoPopups(void)                                     // the SDK no-signal / power-saving chain is not to run under the no-signal saver
{
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_SIGNAL);
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_CABLE);
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_GO_TO_POWER_SAVING);
}

BYTE AwtoSaverGuard(void)                                           // RTDOsdEventMsgProc pop-up cases: 1 = the no-signal saver owns the OSD, drop the pop-up
{
    if((g_ucAwtoSaverRun == AWTO_SAVER_OFF) || ((g_ucAwtoSaverWhy & AWTO_SAVER_WHY_MASK) != AWTO_SAVER_WHY_NOSIG) || (SysModeGetModeState() != _MODE_STATUS_NOSIGNAL))
    {
        return 0;
    }
    SaverNoPopups();
    return 1;
}

void AwtoSaverPoll(void)                                            // main loop, once per pass
{
    unsigned long ulNow = AwtoMs();
    BYTE ucMode = SysModeGetModeState();

    if((s_ulSwap == 0) && (g_ucAwtoSaverRun == AWTO_SAVER_OFF) && (s_ucReq == AWTO_SAVER_REQ_NONE))   // first pass after power-on
    {
        s_ulSwap = ulNow;
        if((AWTO_SET(BOOT_SPLASH) != 0) && (AwtoBootReason() == AWTO_BOOT_COLD))     // cold power-up only: a warm reset (ISP, watchdog) shows nothing
        {
            g_ucAwtoSaverRun = AWTO_SAVER_SPLASH;
            g_ucAwtoSaverWhy = AWTO_SAVER_WHY_BOOT;
            s_ucMid = 0;                                            // drawn at the first pass in mode INITIAL: before it, the SDK's power-on OSD init would wipe it
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SAVER_ARG_START, (BYTE)((AWTO_SAVER_SPLASH << AWTO_SAVER_RUN_SHIFT) | AWTO_SAVER_WHY_BOOT));
        }
        return;
    }
    if(s_ucReq != AWTO_SAVER_REQ_NONE)
    {
        BYTE ucReq = s_ucReq;

        s_ucReq = AWTO_SAVER_REQ_NONE;
        if(ucReq == AWTO_SAVER_NOW_STOP)
        {
            if(g_ucAwtoSaverWhy != AWTO_SAVER_WHY_BOOT)             // the settings load applies 0 once: the splash has its own end
            {
                AwtoSaverStop();
            }
        }
        else if(ucReq == AWTO_SAVER_NOW_ALERT)
        {
            AwtoPmSound(AWTO_SAVER_SND_ALERT);
        }
        else if(ucReq == AWTO_SAVER_NOW_SPLASH)
        {
            AwtoSaverStart(AWTO_SAVER_SPLASH, AWTO_SAVER_WHY_NOW);
        }
        else if(ucReq == AWTO_SAVER_NOW_FLASH)
        {
            AwtoSaverStart(AWTO_SAVER_FLASH, AWTO_SAVER_WHY_NOW);
        }
        else if(ucReq == AWTO_SAVER_NOW_ASTEROIDS)
        {
            AwtoSaverStart(AWTO_SAVER_ASTEROIDS, AWTO_SAVER_WHY_NOW);
        }
        else if(ucReq > AWTO_SAVER_NOW_ALERT)
        {
            return;                                                 // unused values (7): ignored
        }
        else
        {
            AwtoSaverStart((ucReq == AWTO_SAVER_NOW_SELECTED) ? ((g_ucAwtoSaverMode == AWTO_SAVER_OFF) ? AWTO_SAVER_ALTERNATE : SAVER_MODE_RUN(g_ucAwtoSaverMode)) : (BYTE)(ucReq - 1), AWTO_SAVER_WHY_NOW);
        }
        if(g_ucAwtoSaverWhy != AWTO_SAVER_WHY_BOOT)                 // the settings load's stop of 0 leaves a boot splash running: this pass may draw it
        {
            return;
        }
    }
    if(g_ucAwtoSaverRun != AWTO_SAVER_OFF)
    {
        if(g_ucAwtoSaverWhy == AWTO_SAVER_WHY_BOOT)
        {
            if(((ulNow - s_ulSwap) >= AWTO_SPLASH_MAX_MS) || (ucMode == _MODE_STATUS_ACTIVE))      // the picture is on: it takes over
            {
                AwtoSaverStop();
            }
            else if((s_ucMid != AWTO_SAVER_SPLASH_DONE) && (ucMode == _MODE_STATUS_INITIAL))
            {
                for(s_ucMid = 0; AwtoFlashDraw(1, s_ucMid) == 0; s_ucMid++)     // all steps in one pass (Dan 2026-11-18: ACTIVE +54 ms accepted)
                {
                }
                s_ucMid = AWTO_SAVER_SPLASH_DONE;
                isr_g_stAwtoDiag.ucHold |= AWTO_HOLD_POPUP;         // the SDK's OSD resets (display setting, mode changes) cannot wipe it; Stop / the console release it
            }
            return;
        }
        if((((g_ucAwtoSaverWhy & 0x7F) == AWTO_SAVER_WHY_NOSIG) && (ucMode != _MODE_STATUS_NOSIGNAL)) ||
           (((g_ucAwtoSaverWhy & 0x7F) == AWTO_SAVER_WHY_IDLE) && (ucMode != _MODE_STATUS_ACTIVE)))
        {
            AwtoSaverStop();                                        // the state that started it is gone: a source locked / the picture was lost
            s_ulAct = ulNow;                                        // idle time from here: a new picture is not idle (docs/saver-mode.md)
            return;
        }
        if(((g_ucAwtoSaverWhy & AWTO_SAVER_WHY_MASK) == AWTO_SAVER_WHY_NOSIG) && ((ulNow - s_ulNoSig) >= (AWTO_SAVER_NOSIG_MS + (unsigned long)g_usAwtoSaverNosigS * AWTO_SAVER_MS_PER_S)))
        {
            AwtoSaverStop();                                        // run time over: the SDK chain resumes (card 2 s, power-saving card 3 s, power saving 2 s)
            return;
        }
        if((g_ucAwtoSaverWhy & 0x80) && ((ulNow - s_ulSwap) >= AWTO_SAVER_ALT_MS))
        {
            SaverDraw((g_ucAwtoSaverRun == AWTO_SAVER_PACMAN) ? AWTO_SAVER_SCOPE : ((g_ucAwtoSaverRun == AWTO_SAVER_SCOPE) ? AWTO_SAVER_SCOPE2 :
                      ((g_ucAwtoSaverRun == AWTO_SAVER_SCOPE2) ? AWTO_SAVER_ASTEROIDS : AWTO_SAVER_PACMAN)));
            return;
        }
        if((g_ucAwtoSaverRun == AWTO_SAVER_FLASH) || (g_ucAwtoSaverRun == AWTO_SAVER_SPLASH))
        {
            return;                                                 // static: the host flasher swaps the glyph over ISP
        }
        if(g_ucAwtoSaverRun != AWTO_SAVER_PACMAN)                   // scopes, Asteroids: one column per pass until the frame is complete, then a pause (none for Asteroids: frames follow at once)
        {
            if((s_ucMid == 0) && (g_ucAwtoSaverRun != AWTO_SAVER_ASTEROIDS) && ((WORD)(ulNow - s_usTick) < ((g_ucAwtoSaverRun == AWTO_SAVER_SCOPE) ? AWTO_SAVER_SCOPE_MS : AWTO_SAVER_SCOPE2_MS)))
            {
                return;
            }
            s_ucMid = (BYTE)(((g_ucAwtoSaverRun == AWTO_SAVER_SCOPE) ? AwtoScopeSaver(2) : ((g_ucAwtoSaverRun == AWTO_SAVER_ASTEROIDS) ? AwtoAsteroids(2) : AwtoScopeSaver2(2))) == 0);
            if(s_ucMid == 0)
            {
                s_usTick = (WORD)ulNow;
            }
            return;
        }
        {
            WORD usPeriod = (s_ucSub == (AWTO_SAVER_PACMAN_SUBS - 1)) ? (WORD)(AWTO_SAVER_PACMAN_STEP_MS - (AWTO_SAVER_PACMAN_SUBS - 1) * AWTO_SAVER_PACMAN_MS) : (WORD)AWTO_SAVER_PACMAN_MS;
            WORD usLate = (WORD)ulNow - s_usTick;                   // s_usTick = last step's scheduled time; it advances by the period, not from now

            if(usLate >= usPeriod)
            {
                s_usTick += usPeriod;
                s_ucSub = (s_ucSub + 1) % AWTO_SAVER_PACMAN_SUBS;
                if((WORD)((WORD)ulNow - s_usTick) >= AWTO_SAVER_PACMAN_STEP_MS)
                {
                    s_usTick = (WORD)ulNow;                         // far behind (a long pass): resync, no burst of catch-up steps
                }
                AwtoPacmanClassic(2);
            }
        }
        return;
    }
    if(g_ucAwtoSaverMode == AWTO_SAVER_OFF)
    {
        s_ulNoSig = 0;
        s_ucNoSigDone = 0;
        return;
    }
    if(ucMode == _MODE_STATUS_NOSIGNAL)
    {
        if(s_ulNoSig == 0)
        {
            s_ulNoSig = ulNow;
        }
        else if((s_ucNoSigDone == 0) && (g_usAwtoSaverNosigS != 0) && ((ulNow - s_ulNoSig) >= AWTO_SAVER_NOSIG_MS))
        {
            UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, AWTO_PNL_BY_OSD_NOSIGNAL));      // the no-signal card it replaces would have lit the backlight
            AwtoSaverStart(SAVER_MODE_RUN(g_ucAwtoSaverMode), AWTO_SAVER_WHY_NOSIG);
            SaverNoPopups();                                        // the start's OSD close re-armed the card timer
        }
        return;
    }
    s_ulNoSig = 0;
    s_ucNoSigDone = 0;
    if((ucMode == _MODE_STATUS_ACTIVE) && (g_usAwtoSaverIdleS != 0) && ((ulNow - s_ulAct) >= ((unsigned long)g_usAwtoSaverIdleS * AWTO_SAVER_MS_PER_S)))
    {
        AwtoSaverStart(SAVER_MODE_RUN(g_ucAwtoSaverMode), AWTO_SAVER_WHY_IDLE);
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
