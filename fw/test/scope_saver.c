#include <stdint.h>
#include <string.h>
#include "UserCommonInclude.h"
#define OSD_NO_FLUSH
#include "../../tools/osd_lines/osd_lines.c"

// Scope screensaver (docs/screensaver.md): a 384 x 216 waveform screen, 32 x 12 tiles of 12 x 18, one 1-bit glyph per cell (identity map), scaled up.
// 25 frames/s plan (docs/saver-fps-plan.md): per column only the tiles the trace touches now or touched last frame are redrawn (graticule
// computed per tile + one vertical run per px column = the pixels of osd_line per px step); columns within AWTO_SC_PASS_MS per call.
//   AwtoScopeSaver(1) draw the screen   (2) next columns, returns 1 when a frame is complete or not yet due   (0) off

#define AWTO_SC_COLS                            32
#define AWTO_SC_ROWS                            12
#define AWTO_SC_TILE_W                          OSD_TILE_W
#define AWTO_SC_TILE_H                          OSD_TILE_H
#define AWTO_SC_W                               (AWTO_SC_COLS * AWTO_SC_TILE_W)
#define AWTO_SC_H                               (AWTO_SC_ROWS * AWTO_SC_TILE_H)
#define AWTO_SC_BANDS                           2                   // size of the shared band canvas (Asteroids draws into it)
#define AWTO_SC_BAND_ROWS                       (AWTO_SC_ROWS / AWTO_SC_BANDS)
#define AWTO_SC_BAND_H                          (AWTO_SC_BAND_ROWS * AWTO_SC_TILE_H)
#define AWTO_SC_BG                              1                   // palette indexes
#define AWTO_SC_FG                              2
#define AWTO_SC_FG_SHIFT                        4
#define AWTO_SC_BG_R                            0                   // dark green phosphor background
#define AWTO_SC_BG_G                            24
#define AWTO_SC_BG_B                            0
#define AWTO_SC_FG_R                            96                  // trace and graticule
#define AWTO_SC_FG_G                            255
#define AWTO_SC_FG_B                            96
#define AWTO_SC_SU_FACTOR                       7                   // scale-up ratio 64 / 7 = 9.14: 384 x 216 -> 3511 x 1975 of the 3840 x 2160 panel
#define AWTO_SC_POS_H                           41                  // hd units of 4 panel px: (3840 - 3511) / 2 / 4
#define AWTO_SC_POS_V                           92                  // (2160 - 1975) / 2
#define AWTO_SC_GRID_STEP_X                     48                  // dotted graticule: 8 x 4 divisions
#define AWTO_SC_GRID_STEP_Y                     54
#define AWTO_SC_DOT                             4                   // dot spacing of the graticule
#define AWTO_SC_MID_Y                           (AWTO_SC_H / 2)
#define AWTO_SC_AMP1                            62                  // trace: two sines, px
#define AWTO_SC_AMP2                            28
#define AWTO_SC_SINE_N                          64
#define AWTO_SC_SINE_MASK                       (AWTO_SC_SINE_N - 1)
#define AWTO_SC_PH_STEP                         3                   // phase advance per frame, table units
#define AWTO_SC_H2_PER_PX                       4                   // second component: table units per px
#define AWTO_SC_H2_PH                           2                   // second component phase per frame
#define AWTO_SC_PASS_MS                         8                   // saver work per call (+ one column, <= 12 tiles): the main loop (DDC/CI, keys) runs between calls
#ifdef _AWTO_OSD_HWTEST
__xdata WORD g_usAwtoScFrames;
#endif
#define AWTO_SC_FRAME_MS                        40                  // frame schedule: 25 frames/s (docs/saver-fps-plan.md)
#define AWTO_SC_HALF_MS                         0x8000              // WORD ms difference below this = the time has passed
#define AWTO_SC_BYTE_BITS                       3                   // bit index -> byte: >> 3
#define AWTO_SC_BIT_MASK                        7
#define AWTO_SC_ROWS_ALL                        ((WORD)((1UL << AWTO_SC_ROWS) - 1))
#define AWTO_SC_H2_PX_SHIFT                     2                   // x * AWTO_SC_H2_PER_PX, ph * AWTO_SC_H2_PH, row * tile height, row * cols as shifts (checked below)
#define AWTO_SC_H2_PH_SHIFT                     1
#define AWTO_SC_TH_SHIFT_A                      4
#define AWTO_SC_TH_SHIFT_B                      1
#define AWTO_SC_COLS_SHIFT                      5
#define AWTO_SC_MUL_TW(v)                       (((v) << 3) + ((v) << 2))           // v * 12
typedef char s_tScShiftCheck[((AWTO_SC_H2_PER_PX == (1 << AWTO_SC_H2_PX_SHIFT)) && (AWTO_SC_H2_PH == (1 << AWTO_SC_H2_PH_SHIFT)) && (AWTO_SC_TILE_W == 12) &&
                              (AWTO_SC_TILE_H == (1 << AWTO_SC_TH_SHIFT_A) + (1 << AWTO_SC_TH_SHIFT_B)) && (AWTO_SC_COLS == (1 << AWTO_SC_COLS_SHIFT))) ? 1 : -1];
#define AWTO_SC_FONT_BASE                       (AWTO_SC_ROWS + 1 + AWTO_SC_COLS * AWTO_SC_ROWS)   // AwtoOsdMap1 layout: row commands, end word, one char command per cell
#define AWTO_SC_GLYPH_WORDS                     (OSD_TILE_BYTES / 3)
#define AWTO_SC_TILE(c, p)                      AwtoScTile(AWTO_SC_FONT_BASE + AWTO_SC_GLYPH_WORDS * ((g_ucAwtoOsdRot != 0) ? AwtoOsdRotCell((c), AWTO_SC_COLS * AWTO_SC_ROWS) : (c)), (p))
#define AWTO_SC_ARG_ON                          0x76
#define AWTO_SC_ARG_FRAME                       0x77
#define AWTO_SC_ARG_OFF                         0x78

// trace components as drawn: (round(127 sin(2 pi k / 64)) * amplitude) >> 7 for AWTO_SC_AMP1 (62) and AWTO_SC_AMP2 (28): no multiply per px
#pragma place bank(11)                      // tables and the draw path share a bank (movc reads the running bank; no trampoline per call)
static __code int8_t s_tScA1[AWTO_SC_SINE_N] = {
    0, 5, 12, 17, 23, 29, 34, 39, 43, 47, 51, 54, 56, 59, 60, 61,
    61, 61, 60, 59, 56, 54, 51, 47, 43, 39, 34, 29, 23, 17, 12, 5,
    0, -6, -13, -18, -24, -30, -35, -40, -44, -48, -52, -55, -57, -60, -61, -62,
    -62, -62, -61, -60, -57, -55, -52, -48, -44, -40, -35, -30, -24, -18, -13, -6};
#pragma place bank(11)
static __code int8_t s_tScA2[AWTO_SC_SINE_N] = {
    0, 2, 5, 8, 10, 13, 15, 17, 19, 21, 23, 24, 25, 26, 27, 27,
    27, 27, 27, 26, 25, 24, 23, 21, 19, 17, 15, 13, 10, 8, 5, 2,
    0, -3, -6, -9, -11, -14, -16, -18, -20, -22, -24, -25, -26, -27, -28, -28,
    -28, -28, -28, -27, -26, -25, -24, -22, -20, -18, -16, -14, -11, -9, -6, -3};
#pragma place bank(11)
static __code uint8_t s_tScBit[AWTO_SC_BIT_MASK + 1] = {0x80, 0x40, 0x20, 0x10, 0x08, 0x04, 0x02, 0x01};   // bit index in a byte -> mask (MSB first, osd_lines order)

__xdata uint8_t g_aucScPix[OSD_BITMAP_BYTES(1, AWTO_SC_BAND_ROWS)];
__xdata uint8_t g_aucScDirty[OSD_DIRTY_BYTES(1, AWTO_SC_BAND_ROWS)];
__xdata osd_canvas g_scCv;           // shared with scope_saver2.c: one saver runs at a time, XDATA is scarce
#define AWTO_SC_RUN_LO                          (g_aucScPix + OSD_TILE_BYTES)                       // Scope 1 uses the shared canvas: tile buffer, then the column's runs
#define AWTO_SC_RUN_HI                          (g_aucScPix + OSD_TILE_BYTES + AWTO_SC_TILE_W)
static __xdata BYTE s_ucPhase;
static __xdata BYTE s_ucCol;                                            // next column of the frame being drawn
static __xdata BYTE s_ucShown;
static __xdata WORD s_usFrameAt;                                        // scheduled start of the next frame (AwtoMs low word); advances by the period

void AwtoScTile(WORD usAddr, BYTE __xdata *pucB)                    // a 1-bit tile (canonical bytes; turned in place for Rotate 180) by direct port stores: Scope 1, Asteroids
{
    BYTE ucK;

    if(g_ucAwtoOsdRot != 0)
    {
        AwtoOsdTurn(pucB, OSD_TILE_BYTES);                              // then the upright word order = the turned word order
    }
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usAddr, _OSD_WITHOUT_DB);
    for(ucK = 0; ucK < OSD_TILE_BYTES; ucK += 3)
    {
        AWTO_OSD_PORT(pucB[ucK + 2]);
        AWTO_OSD_PORT(pucB[ucK + 1]);
        AWTO_OSD_PORT(pucB[ucK]);
    }
}

#pragma place bank(11)
static BYTE ScY(int16_t sX, BYTE ucPh)                                  // trace y at raster x (20..196: a byte)
{
    return (BYTE)(AWTO_SC_MID_Y - s_tScA1[(BYTE)(sX + ucPh) & AWTO_SC_SINE_MASK] - s_tScA2[(BYTE)(((BYTE)sX << AWTO_SC_H2_PX_SHIFT) + (BYTE)(ucPh << AWTO_SC_H2_PH_SHIFT)) & AWTO_SC_SINE_MASK]);
}

#pragma place bank(11)
static WORD ScRuns(BYTE ucCol, BYTE ucPh)                               // the column's 12 vertical runs (osd_line per px step: x - 1 keeps the first half + 1) -> rows mask
{
    __data int16_t sX = (int16_t)AWTO_SC_MUL_TW((WORD)ucCol);
    __data BYTE ucJ;
    __data BYTE ucPrev = ScY(sX - 1, ucPh);
    __data BYTE ucCur = ScY(sX, ucPh);
    __data BYTE ucNext;
    __data BYTE ucNext2;                                                       // end of the previous segment's second half
    __data BYTE ucLo;
    __data BYTE ucHi;
    __data BYTE ucMin = AWTO_SC_H - 1;
    __data BYTE ucMax = 0;
    __data WORD usMask = 0;

    for(ucJ = 0; ucJ < AWTO_SC_TILE_W; ucJ++, sX++)
    {
        ucNext = ScY(sX + 1, ucPh);
        ucLo = ucCur;
        ucHi = ucCur;
        if(ucNext > ucCur)                                              // segment to x + 1: its first half (d / 2 px past y) stays in this column
        {
            ucHi = ucCur + (BYTE)((ucNext - ucCur) >> 1);
        }
        else
        {
            ucLo = ucCur - (BYTE)((ucCur - ucNext) >> 1);
        }
        if(sX > 0)                                                      // segment from x - 1: the px after its first half land here (no segment ends at x = 0)
        {
            if(ucPrev < ucCur)
            {
                ucNext2 = (BYTE)(ucPrev + ((ucCur - ucPrev) >> 1) + 1);
                ucLo = (ucNext2 < ucLo) ? ucNext2 : ucLo;
            }
            else if(ucPrev > ucCur)
            {
                ucNext2 = (BYTE)(ucPrev - ((ucPrev - ucCur) >> 1) - 1);
                ucHi = (ucNext2 > ucHi) ? ucNext2 : ucHi;
            }
        }
        AWTO_SC_RUN_LO[ucJ] = ucLo;
        AWTO_SC_RUN_HI[ucJ] = ucHi;
        ucMin = (ucLo < ucMin) ? ucLo : ucMin;
        ucMax = (ucHi > ucMax) ? ucHi : ucMax;
        ucPrev = ucCur;
        ucCur = ucNext;
    }
    for(ucJ = ucMin / (BYTE)AWTO_SC_TILE_H; ucJ <= ucMax / (BYTE)AWTO_SC_TILE_H; ucJ++)
    {
        usMask |= (WORD)1 << ucJ;
    }
    return usMask;
}

#pragma place bank(11)
static void ScRun(BYTE ucX, BYTE ucLo, BYTE ucHi)                      // vertical run in the tile buffer, tile coords, ucLo <= ucHi < tile height
{
    __data BYTE ucP = (BYTE)(AWTO_SC_MUL_TW(ucLo) + ucX);

    for(; ucLo <= ucHi; ucLo++, ucP += AWTO_SC_TILE_W)
    {
        g_aucScPix[ucP >> AWTO_SC_BYTE_BITS] |= s_tScBit[ucP & AWTO_SC_BIT_MASK];
    }
}

#pragma place bank(11)
static void ScTile(BYTE ucCol, BYTE ucRow)                              // graticule + trace of one tile (runs of the column already in AWTO_SC_RUN_*) -> its glyph
{
    __data BYTE ucY0 = (BYTE)(((BYTE)(ucRow << AWTO_SC_TH_SHIFT_A)) + (BYTE)(ucRow << AWTO_SC_TH_SHIFT_B));   // ucRow * 18
    __data BYTE ucJ;
    __data BYTE ucLo;
    __data BYTE ucHi;

    memset(g_aucScPix, 0, OSD_TILE_BYTES);
    ucJ = (BYTE)((AWTO_SC_GRID_STEP_Y - ucY0 % AWTO_SC_GRID_STEP_Y) % AWTO_SC_GRID_STEP_Y);   // dotted horizontal graticule (y = 0, 54, 108, 162)
    if(ucJ < AWTO_SC_TILE_H)
    {
        for(ucLo = 0; ucLo < AWTO_SC_TILE_W; ucLo += AWTO_SC_DOT)
        {
            ScRun(ucLo, ucJ, ucJ);
        }
    }
    if((ucCol % (AWTO_SC_GRID_STEP_X / AWTO_SC_TILE_W)) == 0)          // dotted vertical graticule at the column's left px
    {
        for(ucJ = (BYTE)((AWTO_SC_DOT - ucY0 % AWTO_SC_DOT) % AWTO_SC_DOT); ucJ < AWTO_SC_TILE_H; ucJ += AWTO_SC_DOT)
        {
            ScRun(0, ucJ, ucJ);
        }
    }
    for(ucJ = 0; ucJ < AWTO_SC_TILE_W; ucJ++)                           // frame: top / bottom edge rows, then the trace
    {
        if(ucRow == 0)
        {
            ScRun(ucJ, 0, 0);
        }
        if(ucRow == (AWTO_SC_ROWS - 1))
        {
            ScRun(ucJ, AWTO_SC_TILE_H - 1, AWTO_SC_TILE_H - 1);
        }
        ucLo = AWTO_SC_RUN_LO[ucJ];
        ucHi = AWTO_SC_RUN_HI[ucJ];
        if((ucHi >= ucY0) && (ucLo < (BYTE)(ucY0 + AWTO_SC_TILE_H)))
        {
            ScRun(ucJ, (ucLo > ucY0) ? (BYTE)(ucLo - ucY0) : 0, (ucHi < (BYTE)(ucY0 + AWTO_SC_TILE_H - 1)) ? (BYTE)(ucHi - ucY0) : AWTO_SC_TILE_H - 1);
        }
    }
    if(ucCol == 0)                                                      // left / right edges
    {
        ScRun(0, 0, AWTO_SC_TILE_H - 1);
    }
    if(ucCol == (AWTO_SC_COLS - 1))
    {
        ScRun(AWTO_SC_TILE_W - 1, 0, AWTO_SC_TILE_H - 1);
    }
    AWTO_SC_TILE(((WORD)ucRow << AWTO_SC_COLS_SHIFT) + ucCol, g_aucScPix);
}

#pragma place bank(11)
static void ScColumn(BYTE ucCol)                                        // tiles of the trace now or last frame (all on the hidden first frame)
{
    WORD usMask = (s_ucShown != 0) ? ScRuns(ucCol, (BYTE)(s_ucPhase - AWTO_SC_PH_STEP)) : AWTO_SC_ROWS_ALL;
    BYTE ucR;

    usMask |= ScRuns(ucCol, s_ucPhase);
    for(ucR = 0; ucR < AWTO_SC_ROWS; ucR++)
    {
        if((usMask & ((WORD)1 << ucR)) != 0)
        {
            ScTile(ucCol, ucR);
        }
    }
}

BYTE AwtoScopeSaver(BYTE ucCmd)
{
    WORD usStart;

    if(ucCmd == 0)
    {
        AwtoOsdScreenOff();
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SC_ARG_OFF, 0);
        return 1;
    }
    if(ucCmd == 2)                                                      // next columns
    {
        usStart = (WORD)AwtoMs();
        if(s_ucCol == 0)
        {
            if(s_ucShown != 0)                                          // fixed-rate frames (the first one starts at once)
            {
                if((WORD)(usStart - s_usFrameAt) >= AWTO_SC_HALF_MS)
                {
                    return 1;                                           // not due yet
                }
                s_usFrameAt += AWTO_SC_FRAME_MS;
                if((WORD)(usStart - s_usFrameAt) < AWTO_SC_HALF_MS)
                {
                    s_usFrameAt = usStart + AWTO_SC_FRAME_MS;           // a frame or more behind: resync, no burst
                }
            }
            s_ucPhase += AWTO_SC_PH_STEP;
        }
        AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
        do
        {
            ScColumn(s_ucCol);
            s_ucCol++;
        }
        while((s_ucCol < AWTO_SC_COLS) && ((WORD)((WORD)AwtoMs() - usStart) < AWTO_SC_PASS_MS));
        if(s_ucCol < AWTO_SC_COLS)
        {
            return 0;
        }
        s_ucCol = 0;
#ifdef _AWTO_OSD_HWTEST
        g_usAwtoScFrames++;                                             // clock sweep (docs/clock-sweep.md): frames drawn
#endif
        if(s_ucShown == 0)                                              // the first frame was drawn hidden: show the OSD now
        {
            s_ucShown = 1;
            s_usFrameAt = usStart + AWTO_SC_FRAME_MS;
            osd_tc_show(1);
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SC_ARG_ON, 0);
        }
        else
        {
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SC_ARG_FRAME, s_ucPhase);
        }
        return 1;
    }
    AwtoOsdScreenBegin();
    ScalerOsdSetColorPalette(AWTO_OSD_ZERO, AWTO_OSD_ZERO, AWTO_OSD_ZERO, AWTO_OSD_ZERO);
    ScalerOsdSetColorPalette(AWTO_SC_BG, AWTO_SC_BG_R, AWTO_SC_BG_G, AWTO_SC_BG_B);
    ScalerOsdSetColorPalette(AWTO_SC_FG, AWTO_SC_FG_R, AWTO_SC_FG_G, AWTO_SC_FG_B);
    ScalerOsd2FontFunction(_DISABLE);
    AwtoOsdRowCmds(AWTO_SC_ROWS, AWTO_SC_TILE_H, AWTO_SC_COLS);
    AwtoOsdMap1(AWTO_SC_COLS, AWTO_SC_ROWS, (AWTO_SC_FG << AWTO_SC_FG_SHIFT) | AWTO_SC_BG);   // one char command per cell, glyph id = cell index
    AwtoOsdPlaceScaleUp(AWTO_SC_POS_H, AWTO_SC_POS_V, AWTO_SC_COLS, AWTO_SC_ROWS, AWTO_SC_SU_FACTOR);
    osd_canvas_init(&g_scCv, 1, AWTO_SC_BAND_ROWS, g_aucScPix, sizeof(g_aucScPix), g_aucScDirty, sizeof(g_aucScDirty));
    s_ucPhase = 0;
    s_ucCol = 0;
    s_ucShown = 0;                                                      // the first frame is drawn column by column (cmd 2), then the OSD is shown
    return 0;
}
