#include <stdint.h>
#include "UserCommonInclude.h"
#include "flash_screen_data.inc"

// Flash warning screen (#232): drawn by the running firmware just before the host flasher halts the MCU (DDC/CI VCP 0xEB = 5, `dev.py flash`).
// Red over the whole panel (window 0), a 72 x 72 px Pac-Man (6 x 4 tiles, mouth open / shut) and text rows; the map is 30 x 11 tiles of 12 x 18 px
// scaled 64 / 6 = 10.67 (3840 px wide). The OSD circuit keeps drawing while the MCU is held in ISP: scripts/flash_screen.py rewrites map words over ISP
// (mouth frame, progress text). Layout constants come from scripts/gen_flash_screen.py (flash_screen_data.inc); the rest is mirrored in
// scripts/flash_screen.py and checked by tests/test_flash_screen.py. Turned 180 when the display is (docs/osd-rotation.md): map cells mirrored, glyphs turned.
extern void osd_tc_show(BYTE ucOn);
extern void osd_tc_close(void);

#define AWTO_FS_ROW_B0                          0x80
#define AWTO_FS_TILE_W                          12
#define AWTO_FS_TILE_H                          18
#define AWTO_FS_CHAR_B0                         0x4C                // 1-bit char, width 12, id bit 8 = 0
#define AWTO_FS_BG                              1                   // palette indexes: red, yellow, white
#define AWTO_FS_YELLOW                          2
#define AWTO_FS_WHITE                           3
#define AWTO_FS_FG_SHIFT                        4
#define AWTO_FS_ROW_WORD                        0                   // row commands from here, one per row
#define AWTO_FS_END_WORD                        AWTO_FS_ROWS        // end of the row commands
#define AWTO_FS_CHAR_WORD                       (AWTO_FS_ROWS + 1)  // char commands, row-major
#define AWTO_FS_CELLS                           (AWTO_FS_COLS * AWTO_FS_ROWS)
#define AWTO_FS_FONT_BASE                       (AWTO_FS_CHAR_WORD + AWTO_FS_CELLS)
#define AWTO_FS_GLYPH_WORDS                     9
#define AWTO_FS_KICK_MASK                       0x3F                // watchdog kick every 64 data port bytes
#define AWTO_FS_BG_R                            200                 // warning red
#define AWTO_FS_BG_G                            0
#define AWTO_FS_BG_B                            0
#define AWTO_FS_YEL_R                           255
#define AWTO_FS_YEL_G                           220
#define AWTO_FS_YEL_B                           0
#define AWTO_FS_WHT_R                           255
#define AWTO_FS_WHT_G                           255
#define AWTO_FS_WHT_B                           255
#define AWTO_FS_SU_FACTOR                       6                   // ratio 64 / 6 = 10.67: 360 px -> 3840 px
#define AWTO_FS_PANEL_W                         3840
#define AWTO_FS_PANEL_H                         2160
#define AWTO_FS_POS_OFFSET_H                    0x3B                // as the other test screens
#define AWTO_FS_POS_OFFSET_V                    0x04
#define AWTO_FS_WIN                             0                   // full-panel red window behind everything
#define AWTO_FS_ZERO                            0x00
#define AWTO_FS_ARG_ON                          0x7E
#define AWTO_FS_ARG_OFF                         0x7F
#define AWTO_FS_CELL_CHUNK                      110                 // cells per draw step (330 cells: 3 steps); the splash draws one step per main pass
#define AWTO_FS_GLYPH_CHUNK                     30                  // glyphs per step (90: 3 steps)
#define AWTO_FS_CELL_STEPS                      ((AWTO_FS_CELLS + AWTO_FS_CELL_CHUNK - 1) / AWTO_FS_CELL_CHUNK)
#define AWTO_FS_GLYPH_STEPS                     ((AWTO_FS_GLYPHS + AWTO_FS_GLYPH_CHUNK - 1) / AWTO_FS_GLYPH_CHUNK)
#define AWTO_FS_STEP_SETUP                      0
#define AWTO_FS_STEP_GLYPH0                     (1 + AWTO_FS_CELL_STEPS)
#define AWTO_FS_STEP_LAST                       (AWTO_FS_STEP_GLYPH0 + AWTO_FS_GLYPH_STEPS)

#pragma place bank(11)                      // leaf readers in the data's bank
static BYTE FsByte(WORD usIdx)
{
    return g_aucFsGlyph[usIdx];
}

#pragma place bank(11)
static BYTE FsTitle(BYTE ucCol)
{
    return g_aucFsTitle[ucCol];
}

static BYTE FsCellId(WORD usCell, BYTE ucSplash)  // glyph id of the logical cell: Pac-Man tile (id >= AWTO_FS_PM_OPEN), title char or blank
{
    BYTE ucRow = (BYTE)(usCell / AWTO_FS_COLS);
    BYTE ucCol = (BYTE)(usCell % AWTO_FS_COLS);

    if((ucRow >= AWTO_FS_PM_ROW0) && (ucRow < AWTO_FS_PM_ROW0 + AWTO_FS_PM_ROWS) && (ucCol >= AWTO_FS_PM_COL0) && (ucCol < AWTO_FS_PM_COL0 + AWTO_FS_PM_COLS))
    {
        return (BYTE)(AWTO_FS_PM_OPEN + (ucRow - AWTO_FS_PM_ROW0) * AWTO_FS_PM_COLS + (ucCol - AWTO_FS_PM_COL0));
    }
    return (ucRow == AWTO_FS_ROW_TITLE) ? FsTitle((BYTE)(ucCol + ((ucSplash != 0) ? AWTO_FS_COLS : 0))) : 0;
}

static void FsWord(WORD usAddr, BYTE ucB0, BYTE ucB1, BYTE ucB2)
{
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usAddr, _OSD_WITHOUT_DB);
    ScalerOsdDataPort(ucB0);
    ScalerOsdDataPort(ucB1);
    ScalerOsdDataPort(ucB2);
}

// One draw step (ucSplash: second title text); 0 = more steps follow, 1 = drawn and shown. Steps: set-up, cell chunks, glyph chunks, show.
BYTE AwtoFlashDraw(BYTE ucSplash, BYTE ucStep)
{
    WORD usI;
    BYTE ucK;
    BYTE ucB;

    if(ucStep == AWTO_FS_STEP_SETUP)
    {
        osd_tc_close();
        AwtoOsdTestReset();
        g_ucAwtoOsdRot = AwtoOsdRot180();                               // latched for the steps that follow
        ScalerOsdGlobalDoubleBuffer(_DISABLE);
        ScalerOsdCircuitActivated(_ENABLE);
        ScalerOsdVerticalStartSelect(_OSD_VSYNC_SELECT_DVS);
        ScalerOsdSetColorPalette(AWTO_FS_ZERO, AWTO_FS_ZERO, AWTO_FS_ZERO, AWTO_FS_ZERO);
        ScalerOsdSetColorPalette(AWTO_FS_BG, AWTO_FS_BG_R, AWTO_FS_BG_G, AWTO_FS_BG_B);
        ScalerOsdSetColorPalette(AWTO_FS_YELLOW, AWTO_FS_YEL_R, AWTO_FS_YEL_G, AWTO_FS_YEL_B);
        ScalerOsdSetColorPalette(AWTO_FS_WHITE, AWTO_FS_WHT_R, AWTO_FS_WHT_G, AWTO_FS_WHT_B);
        ScalerOsd2FontFunction(_DISABLE);
        for(usI = 0; usI < AWTO_FS_ROWS; usI++)
        {
            FsWord(AWTO_FS_ROW_WORD + usI, AWTO_FS_ROW_B0, AWTO_FS_TILE_H - 1, AWTO_FS_COLS);
        }
        FsWord(AWTO_FS_END_WORD, AWTO_FS_ZERO, AWTO_FS_ZERO, AWTO_FS_ZERO);
        return 0;
    }
    if(ucStep < AWTO_FS_STEP_GLYPH0)
    {
        usI = (WORD)(ucStep - 1) * AWTO_FS_CELL_CHUNK;
        ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_FS_CHAR_WORD + usI, _OSD_WITHOUT_DB);
        for(; (usI < (WORD)ucStep * AWTO_FS_CELL_CHUNK) && (usI < AWTO_FS_CELLS); usI++)   // physical cell usI shows the logical cell usI, or the mirrored one when turned
        {
            AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
            ucB = FsCellId((g_ucAwtoOsdRot != 0) ? AwtoOsdRotCell(usI, AWTO_FS_CELLS) : usI, ucSplash);
            ScalerOsdDataPort(AWTO_FS_CHAR_B0);
            ScalerOsdDataPort(ucB);
            ScalerOsdDataPort((BYTE)((((ucB >= AWTO_FS_PM_OPEN) ? AWTO_FS_YELLOW : AWTO_FS_WHITE) << AWTO_FS_FG_SHIFT) | AWTO_FS_BG));
        }
        return 0;
    }
    if(ucStep < AWTO_FS_STEP_LAST)
    {
        usI = (WORD)(ucStep - AWTO_FS_STEP_GLYPH0) * AWTO_FS_GLYPH_CHUNK;
        ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_FS_FONT_BASE + usI * AWTO_FS_GLYPH_WORDS, _OSD_WITHOUT_DB);
        for(; (usI < (WORD)(ucStep - AWTO_FS_STEP_GLYPH0 + 1) * AWTO_FS_GLYPH_CHUNK) && (usI < AWTO_FS_GLYPHS); usI++)
        {
            for(ucK = 0; ucK < AWTO_FS_GLYPH_BYTES; ucK++)
            {
                AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
                if(g_ucAwtoOsdRot != 0)                                          // turned 180: words reversed, bits reversed (docs/osd-rotation.md)
                {
                    ucB = AwtoOsdRevByte(FsByte(usI * AWTO_FS_GLYPH_BYTES + AwtoOsdRotSrc(ucK, AWTO_FS_GLYPH_WORDS)));
                }
                else
                {
                    ucB = FsByte(usI * AWTO_FS_GLYPH_BYTES + ucK);
                }
                ScalerOsdDataPort(ucB);
            }
        }
        return 0;
    }
    SET_OSD_MAPA_COL_MAX(AWTO_FS_COLS);
    ScalerOsdSramBaseAddressSet(_OSD_A, AWTO_FS_ROW_WORD, AWTO_FS_CHAR_WORD, AWTO_FS_FONT_BASE);
    ScalerOsdFontWindowVericalAlignemnt(_ENABLE);
    ScalerOsdPositionOffset(_OSD_POSITION_OFFSET_GLOBAL, AWTO_FS_POS_OFFSET_H, AWTO_FS_POS_OFFSET_V);
    ScalerOsdPosition(_OSD_POSITION_GLOBAL_A, AWTO_FS_ZERO, AWTO_FS_ZERO);
    ScalerOsdReferenceDelay(_OSD_A, _OSD_FIRST_DELAY);
    ScalerOsdPosition(_OSD_POSITION_FONT_A, AWTO_FS_ZERO, AWTO_FS_ZERO);
    ScalerOsdScaleUpHorSize(AWTO_FS_ZERO, AWTO_FS_COLS * AWTO_FS_TILE_W);       // the window is in display coordinates: it starts where the OSD starts (0, 0)
    ScalerOsdScaleUpVerSize(AWTO_FS_ZERO, AWTO_FS_ROWS * AWTO_FS_TILE_H);
    ScalerOsdScaleUpVerFactor(AWTO_FS_SU_FACTOR);
    ScalerOsdScaleUpHorFactor(AWTO_FS_SU_FACTOR);
    ScalerOsdScaleUpBoundaryCodition(_OSD_SCALING_BOUNDARY_NEIGHTBOOR);
    ScalerOsdScaleUpOnOff(_ENABLE);
    memset(&g_stOsdWindow, 0, sizeof(g_stOsdWindow));
    SET_OSD_WINDOW_REFERENCE_DELAY(_OSD_FIRST_DELAY);
    SET_OSD_WINDOW_COLOR(AWTO_FS_BG);
    osd_tc_win_draw(AWTO_FS_WIN, AWTO_FS_ZERO, AWTO_FS_ZERO, AWTO_FS_PANEL_W - 1, AWTO_FS_PANEL_H - 1);
    osd_tc_show(1);
    return 1;
}

void AwtoFlashScreen(BYTE ucOn)
{
    if(ucOn == 0)
    {
        osd_tc_close();
        ScalerOsdScaleUpOnOff(_DISABLE);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_FS_ARG_OFF, 0);
        return;
    }
    ucOn = 0;                                                           // now the step counter
    while(AwtoFlashDraw(0, ucOn++) == 0)
    {
    }
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_FS_ARG_ON, 0);
}
