#include <stdint.h>
#include "UserCommonInclude.h"
#include "pacman_osd_data.inc"

// Pac-Man OSD graphics prototype on the unit (tools/pacman_osd, generated data: scripts/gen_pacman_osd.py): a 28 x 36 cell maze of
// 12 x 12 visible cells (row height 12), 343 one-bit 12 x 18 glyphs uploaded as plain words, scripted 96 frame demo as cell updates.
//   test cmd 0xB4: draw the initial maze (and clear the OSD state an earlier image left)
//   test cmd 0xB5: apply the next frame (host paces it: scripts/pacman_unit.py); after frame 95 the maze is redrawn
//   test cmd 0xB6: off
// SRAM layout (the prototype's): row commands from 0, end word, char commands from AWTO_PM_FS_BASE, glyph words from AWTO_PM_FONT_BASE.
// The prototype was only emulator-tested; this is its first run on the chip. Sync line E9 0x70 / 0x71 (value = frame) / 0x72.
extern void osd_tc_show(BYTE ucOn);
extern void osd_tc_close(void);

#define AWTO_PM_ROW_B0                          0x80                // row command: present
#define AWTO_PM_CELL_H                          12                  // visible cell height (the glyphs are 18 rows high, the rest is cut)
#define AWTO_PM_WORDS_PER_GLYPH                 9
#define AWTO_PM_CELLS                           (AWTO_PM_COLS * AWTO_PM_ROWS)
#define AWTO_PM_RGB                             3                   // bytes per palette entry
#define AWTO_PM_R                               0
#define AWTO_PM_G                               1
#define AWTO_PM_B                               2
#define AWTO_PM_DELTA_BYTES                     5                   // cell index lo, hi, B0, B1, B2
#define AWTO_PM_POS_OFFSET_H                    0x3B                // as the QC pattern (qc_osd.c)
#define AWTO_PM_POS_OFFSET_V                    0x04
#define AWTO_PM_ZERO                            0x00
#define AWTO_PM_ARG_ON                          0x70
#define AWTO_PM_ARG_FRAME                       0x71
#define AWTO_PM_ARG_OFF                         0x72

static __xdata BYTE s_ucFrame;

#pragma place bank(11)                      // reads the tables via movc: same bank as the data above
static void PmWord(WORD usAddr, BYTE ucB0, BYTE ucB1, BYTE ucB2)
{
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usAddr, _OSD_WITHOUT_DB);
    ScalerOsdDataPort(ucB0);
    ScalerOsdDataPort(ucB1);
    ScalerOsdDataPort(ucB2);
}

static void PmCells(void)
{
    WORD usI;

    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_PM_FS_BASE, _OSD_WITHOUT_DB);       // the data port counts words: one address set, 3 bytes per cell
    for(usI = 0; usI < AWTO_PM_CELLS * AWTO_PM_RGB; usI++)
    {
        ScalerOsdDataPort(g_pmCell[usI]);
    }
}

void AwtoPacman(BYTE ucCmd)
{
    WORD usI;
    WORD usO;
    WORD usEnd;
    WORD usPos;

    if(ucCmd == 0)
    {
        osd_tc_close();
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PM_ARG_OFF, 0);
        return;
    }
    if(ucCmd == 2)                                                          // next frame: its cell updates
    {
        if(s_ucFrame >= AWTO_PM_FRAMES)
        {
            PmCells();                                                      // after the last frame: the initial maze again
            s_ucFrame = 0;
        }
        usO = ((WORD)g_pmFrameIdx[2 * s_ucFrame + 1] << 8) | g_pmFrameIdx[2 * s_ucFrame];
        usEnd = ((WORD)g_pmFrameIdx[2 * s_ucFrame + 3] << 8) | g_pmFrameIdx[2 * s_ucFrame + 2];
        for(; usO < usEnd; usO += AWTO_PM_DELTA_BYTES)
        {
            usPos = ((WORD)g_pmDelta[usO + 1] << 8) | g_pmDelta[usO];
            PmWord(AWTO_PM_FS_BASE + usPos, g_pmDelta[usO + 2], g_pmDelta[usO + 3], g_pmDelta[usO + 4]);
        }
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PM_ARG_FRAME, s_ucFrame);
        s_ucFrame++;
        return;
    }
    osd_tc_close();                                                         // our own OSD off, windows closed
    AwtoOsdTestReset();
    ScalerOsdGlobalDoubleBuffer(_DISABLE);
    ScalerOsdCircuitActivated(_ENABLE);
    ScalerOsdVerticalStartSelect(_OSD_VSYNC_SELECT_DVS);
    for(usI = 0; usI < AWTO_PM_PAL_N; usI++)
    {
        ScalerOsdSetColorPalette((BYTE)usI, g_pmPal[AWTO_PM_RGB * usI + AWTO_PM_R], g_pmPal[AWTO_PM_RGB * usI + AWTO_PM_G], g_pmPal[AWTO_PM_RGB * usI + AWTO_PM_B]);
    }
    ScalerOsd2FontFunction(_DISABLE);
    for(usI = 0; usI < AWTO_PM_ROWS; usI++)                                 // row commands: present, height - 1, cells per row
    {
        PmWord(usI, AWTO_PM_ROW_B0, AWTO_PM_CELL_H - 1, AWTO_PM_COLS);
    }
    PmWord(AWTO_PM_ROWS, AWTO_PM_ZERO, AWTO_PM_ZERO, AWTO_PM_ZERO);        // end of the row commands
    PmCells();
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_PM_FONT_BASE, _OSD_WITHOUT_DB);
    for(usI = 0; usI < (WORD)AWTO_PM_GLYPHS * AWTO_PM_WORDS_PER_GLYPH * AWTO_PM_RGB; usI++)
    {
        ScalerOsdDataPort(g_pmGlyph[usI]);
    }
    SET_OSD_MAPA_COL_MAX(AWTO_PM_COLS);
    ScalerOsdSramBaseAddressSet(_OSD_A, AWTO_PM_ZERO, AWTO_PM_FS_BASE, AWTO_PM_FONT_BASE);
    ScalerOsdFontWindowVericalAlignemnt(_ENABLE);
    ScalerOsdPositionOffset(_OSD_POSITION_OFFSET_GLOBAL, AWTO_PM_POS_OFFSET_H, AWTO_PM_POS_OFFSET_V);
    ScalerOsdPosition(_OSD_POSITION_GLOBAL_A, AWTO_PM_ZERO, AWTO_PM_ZERO);
    ScalerOsdReferenceDelay(_OSD_A, _OSD_FIRST_DELAY);
    ScalerOsdPosition(_OSD_POSITION_FONT_A, AWTO_PM_ZERO, AWTO_PM_ZERO);
    s_ucFrame = 0;
    osd_tc_show(1);
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PM_ARG_ON, 0);
}
