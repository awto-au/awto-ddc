#include <stdint.h>
#include "UserCommonInclude.h"

// Full-screen OSD screens: flash warning screen, boot splash, alert tone; run from the main loop (docs/games.md: the game screensavers are gone).
// Starts: cold power-up (boot splash), DDC/CI VCP 0xEB (setting 121 screensaver_now), test cmd.
// Stops: VCP 0xEB = 0; boot splash: a key, the console / a test command taking the OSD, ACTIVE, AWTO_SPLASH_MAX_MS.
// A DDC/CI command does not end a "now" screen or the splash.

// GENERATED-BEGIN awto_savers (fw/awto/savers.tsv; edit the TSV, not this block)
#define AWTO_SAVER_OFF                  0
#define AWTO_SAVER_FLASH                5
#define AWTO_SAVER_SPLASH               6
#define AWTO_SAVER_NOW_STOP             0
#define AWTO_SAVER_NOW_FLASH            5
#define AWTO_SAVER_NOW_SPLASH           7
#define AWTO_SAVER_NOW_ALERT            6
// GENERATED-END awto_savers
#define AWTO_SAVER_WHY_NONE                     0
#define AWTO_SAVER_WHY_NOW                      3
#define AWTO_SAVER_WHY_BOOT                     4                   // boot splash (docs/flash-screen.md): the flash screen drawing, shown a step per main pass
#define AWTO_SAVER_SPLASH_DONE                  0xFF                // s_ucMid: all draw steps done
#define AWTO_SPLASH_MAX_MS                      3000UL              // hard cap: 4x the sim power-on -> ACTIVE (~0.75 s), = console hold AWTO_CON_HOLD_MS; expiry = splash closes
#define AWTO_SAVER_ARG_START                    0x79                // sync line E9: value = what (run << 4 | why)
#define AWTO_SAVER_ARG_STOP                     0x79                // same line as the start, value 0
#define AWTO_SAVER_REQ_NONE                     0xFF
#define AWTO_SAVER_SND_ALERT                    2                   // AwtoPmSound(cmd): alert (AWTO_PS_CMD_ALERT, fw/audio/audio.c)
#define AWTO_SAVER_RUN_SHIFT                    4

__xdata BYTE g_ucAwtoSaverRun;                                       // AWTO_SAVER_FLASH / SPLASH while one runs, else OFF
__xdata BYTE g_ucAwtoSaverWhy;
static __xdata BYTE s_ucReq = AWTO_SAVER_REQ_NONE;                  // set by the DDC/CI apply, served by AwtoSaverPoll: a draw on the DDC handler's stack overflows IRAM and blocks DDC for its whole length
static __xdata BYTE s_ucMid;                                        // splash: draw steps done
static __xdata unsigned long s_ulSwap;                              // first pass done / run started

void AwtoSaverKey(void)                                             // a front key ends the boot splash
{
    if(g_ucAwtoSaverWhy == AWTO_SAVER_WHY_BOOT)
    {
        AwtoSaverStop();
    }
}

static void SaverDraw(BYTE ucRun)
{
    if((g_ucAwtoSaverRun == AWTO_SAVER_FLASH) || (g_ucAwtoSaverRun == AWTO_SAVER_SPLASH))
    {
        AwtoFlashScreen(0);
    }
    g_ucAwtoSaverRun = ucRun;
    if(ucRun == AWTO_SAVER_FLASH)
    {
        AwtoFlashScreen(1);
    }
    else if(ucRun == AWTO_SAVER_SPLASH)
    {
        AwtoFlashScreen(2);
    }
    s_ulSwap = AwtoMs();
    s_ucMid = 1;
}

void AwtoSaverStart(BYTE ucWhich, BYTE ucWhy)                      // ucWhich: FLASH / SPLASH
{
    g_ucAwtoSaverWhy = ucWhy;
    SaverDraw(ucWhich);
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SAVER_ARG_START, (BYTE)((ucWhich << AWTO_SAVER_RUN_SHIFT) | ucWhy));
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
    SaverDraw(AWTO_SAVER_OFF);
    g_ucAwtoSaverWhy = AWTO_SAVER_WHY_NONE;
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SAVER_ARG_STOP, 0);
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
        if(g_ucAwtoSaverWhy != AWTO_SAVER_WHY_BOOT)                 // the settings load's stop of 0 leaves a boot splash running: this pass may draw it
        {
            return;
        }
    }
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
            isr_g_stAwtoDiag.ucHold |= AWTO_HOLD_POPUP;             // the SDK's OSD resets (display setting, mode changes) cannot wipe it; Stop / the console release it
        }
    }
}

void set_ap_screensaver_now(BYTE ucId, int iV)                      // DDC/CI VCP 0xEB: recorded, the main loop acts
{
    ucId = ucId;
    s_ucReq = (BYTE)iV;
}
