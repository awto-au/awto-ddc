// AwtoApps.h: the API of extra apps (code from an extra source root, ./dev.py build --extra-fw DIR; docs/extra-apps.md).
// Include after UserCommonInclude.h. Compiled only when _AWTO_EXTRA_APPS == _ON (the build sets it); nothing of this is in the default image.
#ifndef AWTO_APPS_H
#define AWTO_APPS_H

#include "keys.h"                                                  // AWTO_K_* key ids, AWTO_KEV_* key events

// ---- registration: one line per app at file scope, scanned by scripts/gen_awto_apps.py (no runtime registration) ----
// Hooks are functions with external linkage (not static), or AWTO_APP_NONE:
//   void init(void)                       start: draw the first frame (AwtoAppScreenBegin ...)
//   void step(void)                       once per main-loop pass while the app runs; bounded, see AwtoAppFeed
//   void key(BYTE ucKey, BYTE ucEv)       every key but POWER: ucKey AWTO_K_*, ucEv AWTO_KEV_PRESS / REPEAT / RELEASE / COMBO; without a hook a key press stops the app
//   void stop(void)                       the app ends (VCP 0xEB = 0, AwtoAppStop, POWER, a mode change, power state not NORMAL)
#define AWTO_APP_NONE                           0
#define AWTO_APP(name, init, step, key, stop)   extern char g_cAwtoApp_##name

// ---- start / stop ----
// VCP 0xEB = AWTO_APPS_VCP_BASE + index starts app `index` (order of apps_gen.tsv), 0 stops it; max 15 apps.
// Debug start: write index + 1 (AWTO_APPS_REQ_STOP = stop) to the XDATA byte g_ucAwtoAppReq (map symbol) over the debug link.
#define AWTO_APPS_VCP_BASE                      0x20
#define AWTO_APPS_REQ_STOP                      0xFF
#define AWTO_APPS_WORD_BYTES                    3                  // one OSD SRAM word
extern __xdata BYTE g_ucAwtoAppReq;
extern __xdata BYTE g_ucAwtoAppRun;                                // 0 = none, else running app index + 1
extern void AwtoAppStop(void);                                     // the app ends itself (calls its stop hook)

// ---- pacing and watchdog ----
// AWTO_WDT_PASS is fed once per pass (AwtoDiagMainPass): step must finish well inside the bite time (warn 200 ms, reset 586 ms; docs/watchdog.md).
// A bounded loop that can run longer calls AwtoAppFeed() in each iteration. The main loop runs free while an app is up (AwtoLoopBusy):
// pace frames with AwtoAppMs() compares, never with a delay loop.
#define AwtoAppFeed()                           AWTO_WDT_FEED(AWTO_WDT_S_APP)
#define AwtoAppMs()                             AwtoMs()           // unsigned long, ms since boot
extern WORD AwtoAppRandom(void);                                   // 16 bit xorshift, seeded from the start time

// ---- canvas: the full-screen OSD map the removed screensavers drew into (12 x 18 px glyph cells, docs/osd/api.md, docs/osd/rotation.md) ----
// Order: AwtoAppScreenBegin(); AwtoOsdRowCmds(rows, rowH, cols); cell commands + glyph words; AwtoOsdPlaceScaleUp(...) (or the SDK calls of
// fw/test/qc_osd.c); then per frame AwtoAppCell / AwtoAppCells / AwtoAppGlyph for the changed cells only (the OSD reads SRAM live: the
// double buffer is off, there is no flip). The helpers take display Rotate 180 into account where they say so (g_ucAwtoOsdRot, latched at ScreenBegin).
extern void AwtoAppScreenBegin(void);                              // OSD reset, rotation latched, popup hold (SDK OSD resets cannot wipe it)
extern void AwtoAppScreenEnd(void);                                // scale-up off, console / test OSD closed, hold released (the stop path does it too)
extern WORD AwtoAppCellAddr(WORD usBase, WORD usCell, WORD usCells);   // SRAM word of cell usCell of a map of usCells at usBase (mirrored when turned)
#define AwtoAppCell(usAddr, ucB0, usB12)        AwtoOsdWord((usAddr), (ucB0), (usB12))   // one 3-byte OSD SRAM word: char command / glyph word (B1 = high byte of usB12)
extern void AwtoAppCells(WORD usAddr, const BYTE __xdata *pucB, WORD usWords);   // usWords consecutive words from XDATA in data port order, one address set
extern void AwtoAppGlyph(WORD usAddr, BYTE __xdata *pucB, BYTE ucBytes);   // glyph bytes (multiple of 3, low byte of each word first) to SRAM; turned in place when Rotate 180
extern void AwtoAppTurn(BYTE __xdata *pucB, BYTE ucBytes);         // reverse a glyph buffer 180 degrees in place (byte order + bit order)

// ---- sound (the audio player that remains: key click / alert / calibration tone; game tracks are not in the player) ----
#define AWTO_APP_SND_STOP                       1                  // AwtoPmSound cmd = fw/audio/audio.c AWTO_PS_CMD_STOP
#define AWTO_APP_SND_ALERT                      2                  // AWTO_PS_CMD_ALERT
#define AwtoAppSoundTone(ucSc, usMs)            AwtoPmSoundTone((ucSc), (usMs))   // AWTO_TONE_PLAYED / AWTO_TONE_BUSY; S code = pitch (fw/audio/audio.c)
#define AwtoAppSoundAlert()                     AwtoPmSound(AWTO_APP_SND_ALERT)
#define AwtoAppSoundStop()                      AwtoPmSound(AWTO_APP_SND_STOP)

#endif
