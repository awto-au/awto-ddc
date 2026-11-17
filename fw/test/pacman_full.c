#include <stdint.h>
#include "UserCommonInclude.h"
#include "pacman_full_data.inc"

// Full-screen Pac-Man demo on the unit (the pacland14 image of 2026-11-09, data: scripts/gen_pacman_full.py): 80 x 60 cells of native
// 24 x 36 one-bit glyphs (36 words each), row height 36 (the whole glyph), double width only = 3840 x 2160 (round Pac-Man: 2 x 1 pixels), an autonomous demo recorded
// as cell updates (200 steps, host-paced by scripts/pacman_unit.py --full).
//   test cmd 0xB7: draw the maze   0xB8: next step (after the last one the maze is redrawn)   0xB9: off
// SRAM layout: row commands from 0, end word, char commands from AWTO_PF_FS_BASE, glyph words from AWTO_PF_FONT_BASE.
// Sync line E9 0x73 (drawn) / 0x74 (value = step) / 0x75 (off).
extern void osd_tc_show(BYTE ucOn);
extern void osd_tc_close(void);

#define AWTO_PF_CELLS                           (AWTO_PF_COLS * AWTO_PF_ROWS)
#define AWTO_PF_FS_BASE                         (AWTO_PF_ROWS + 1)
#define AWTO_PF_FONT_BASE                       (AWTO_PF_FS_BASE + AWTO_PF_CELLS)
#define AWTO_PF_WORDS_PER_GLYPH                 36                  // 24 x 36 one bit = 864 bits
#define AWTO_PF_ROW_B0                          0x80                // row command: present
#define AWTO_PF_ROW_H                           36                  // row height in OSD lines = the full 24 x 36 glyph; double WIDTH only: 2 x 1 pixels, 60 rows = 2160 lines, 80 x 48 = 3840
#define AWTO_PF_CHAR_B0                         0x58                // one-bit char, width 24 (bit 5 = glyph id bit 8: not needed below 256 glyphs)
#define AWTO_PF_BG                              0x01                // background palette index: opaque black
#define AWTO_PF_COLOUR_SHIFT                    4
#define AWTO_PF_RGB                             3
#define AWTO_PF_R                               0
#define AWTO_PF_G                               1
#define AWTO_PF_B                               2
#define AWTO_PF_DELTA_BYTES                     4                   // cell index lo, hi, glyph, colour
#define AWTO_PF_FIX_BYTES                       3                   // cell index lo, hi, colour
#define AWTO_PF_POS_OFFSET_H                    0x3B                // as the QC pattern / the small Pac-Man
#define AWTO_PF_POS_OFFSET_V                    0x04
#define AWTO_PF_ZERO                            0x00
#define AWTO_PF_KICK_MASK                       0x7F                // kick the watchdog every 128 data port bytes: the maze + glyph load is ~24 KB, well over the 586 ms bite time
#define PF_KICK(i)                              do { if(((i) & AWTO_PF_KICK_MASK) == AWTO_PF_ZERO) { AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT; } } while(0)
#define AWTO_PF_ARG_ON                          0x73
#define AWTO_PF_ARG_STEP                        0x74
#define AWTO_PF_ARG_OFF                         0x75

static __xdata BYTE s_ucStep;
__xdata BYTE g_ucAwtoPfPosH;                            // OSD position, hd units (host-settable for tuning)
__xdata BYTE g_ucAwtoPfPosV;

#define PF_STEP_BODY(IDX, DELTA)                                                                                         \
    WORD usO = ((WORD)IDX[2 * ucStep + 1] << 8) | IDX[2 * ucStep];                                                       \
    WORD usEnd = ((WORD)IDX[2 * ucStep + 3] << 8) | IDX[2 * ucStep + 2];                                                 \
    WORD usPos;                                                                                                          \
    BYTE ucGlyph;                                                                                                        \
    BYTE ucB2;                                                                                                           \
    for(; usO < usEnd; usO += AWTO_PF_DELTA_BYTES)                                                                       \
    {                                                                                                                    \
        usPos = ((WORD)DELTA[usO + 1] << 8) | DELTA[usO];                                                                \
        ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_PF_FS_BASE + usPos, _OSD_WITHOUT_DB);                             \
        ucGlyph = DELTA[usO + 2];                                                                                        \
        ucB2 = (BYTE)((DELTA[usO + 3] << AWTO_PF_COLOUR_SHIFT) | AWTO_PF_BG);                                            \
        ScalerOsdDataPort(AWTO_PF_CHAR_B0);                                                                              \
        ScalerOsdDataPort(ucGlyph);                                                                                      \
        ScalerOsdDataPort(ucB2);                                                                                         \
    }

#pragma place bank(11)                      // reads the step tables via movc: same bank (a pragma pins only the next definition)
static void PfStepB(BYTE ucStep)
{
    PF_STEP_BODY(g_pfIdxB, g_pfDeltaB)
}

#pragma place bank(11)
static void PfStepA(BYTE ucStep)
{
    PF_STEP_BODY(g_pfIdxA, g_pfDeltaA)
}

static void PfCell(WORD usPos, BYTE ucGlyph, BYTE ucColour)
{
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_PF_FS_BASE + usPos, _OSD_WITHOUT_DB);
    ScalerOsdDataPort(AWTO_PF_CHAR_B0);
    ScalerOsdDataPort(ucGlyph);
    ScalerOsdDataPort((BYTE)((ucColour << AWTO_PF_COLOUR_SHIFT) | AWTO_PF_BG));
}

#pragma place bank(12)                      // leaf reader: a const reference in a function that also calls a banked routine trips the link check (gptr_const_xbank)
static BYTE PfFg(BYTE ucGlyph)
{
    return g_pfFg[ucGlyph];
}

#pragma place bank(12)                      // the maze, glyph and palette tables are read here and in the entry function
static void PfMaze(void)
{
    WORD usI;
    WORD usPos;
    BYTE ucGlyph;
    BYTE ucB2;

    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_PF_FS_BASE, _OSD_WITHOUT_DB);        // the data port counts words: one address set for all cells
    for(usI = 0; usI < AWTO_PF_CELLS; usI++)
    {
        PF_KICK(usI);
        ucGlyph = g_pfCell[usI];                                            // table reads into locals, not inside call arguments
        ucB2 = (BYTE)((PfFg(ucGlyph) << AWTO_PF_COLOUR_SHIFT) | AWTO_PF_BG);
        ScalerOsdDataPort(AWTO_PF_CHAR_B0);
        ScalerOsdDataPort(ucGlyph);
        ScalerOsdDataPort(ucB2);
    }
    for(usI = 0; usI < sizeof(g_pfFix); usI += AWTO_PF_FIX_BYTES)               // cells whose colour is not the glyph's (the actors)
    {
        usPos = ((WORD)g_pfFix[usI + 1] << 8) | g_pfFix[usI];
        ucB2 = g_pfFix[usI + 2];
        ucGlyph = g_pfCell[usPos];
        PfCell(usPos, ucGlyph, ucB2);
    }
}

#pragma place bank(12)
void AwtoPacmanFull(BYTE ucCmd)
{
    WORD usI;
    BYTE ucB2;

    if(ucCmd == 0)
    {
        osd_tc_close();
        ScalerOsdFont24x36OnOff(_DISABLE);
        ScalerOsdDoubleFunction(_OSD_DOUBLE_WIDTH_DISABLE, _OSD_DOUBLE_HEIGHT_DISABLE);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PF_ARG_OFF, 0);
        return;
    }
    if(ucCmd == 2)                                                          // next step: its cell updates
    {
        if(s_ucStep >= AWTO_PF_STEPS)
        {
            PfMaze();                                                       // after the last step: the maze from the start
            s_ucStep = 0;
        }
        if(s_ucStep < AWTO_PF_HALF)
        {
            PfStepA(s_ucStep);
        }
        else
        {
            PfStepB(s_ucStep - AWTO_PF_HALF);
        }
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PF_ARG_STEP, s_ucStep);
        s_ucStep++;
        return;
    }
    osd_tc_close();                                                         // our own OSD off, windows closed
    AwtoOsdTestReset();
    ScalerOsdGlobalDoubleBuffer(_DISABLE);
    ScalerOsdCircuitActivated(_ENABLE);
    ScalerOsdVerticalStartSelect(_OSD_VSYNC_SELECT_DVS);
    for(usI = 0; usI < AWTO_PF_PAL_N; usI++)
    {
        ScalerOsdSetColorPalette((BYTE)usI, g_pfPal[AWTO_PF_RGB * usI + AWTO_PF_R], g_pfPal[AWTO_PF_RGB * usI + AWTO_PF_G], g_pfPal[AWTO_PF_RGB * usI + AWTO_PF_B]);
    }
    ScalerOsd2FontFunction(_DISABLE);
    for(usI = 0; usI < AWTO_PF_ROWS; usI++)                                 // row commands: present, height - 1, cells per row
    {
        ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usI, _OSD_WITHOUT_DB);
        ScalerOsdDataPort(AWTO_PF_ROW_B0);
        ScalerOsdDataPort(AWTO_PF_ROW_H - 1);
        ScalerOsdDataPort(AWTO_PF_COLS);
    }
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_PF_ROWS, _OSD_WITHOUT_DB);          // end of the row commands
    ScalerOsdDataPort(AWTO_PF_ZERO);
    ScalerOsdDataPort(AWTO_PF_ZERO);
    ScalerOsdDataPort(AWTO_PF_ZERO);
    PfMaze();
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_PF_FONT_BASE, _OSD_WITHOUT_DB);
    for(usI = 0; usI < sizeof(g_pfGlyph0); usI++)                           // the glyph stream in three arrays (bank holes are smaller than 9 KB)
    {
        PF_KICK(usI);
        ucB2 = g_pfGlyph0[usI];
        ScalerOsdDataPort(ucB2);
    }
    for(usI = 0; usI < sizeof(g_pfGlyph1); usI++)
    {
        PF_KICK(usI);
        ucB2 = g_pfGlyph1[usI];
        ScalerOsdDataPort(ucB2);
    }
    for(usI = 0; usI < sizeof(g_pfGlyph2); usI++)
    {
        PF_KICK(usI);
        ucB2 = g_pfGlyph2[usI];
        ScalerOsdDataPort(ucB2);
    }
    SET_OSD_MAPA_COL_MAX(AWTO_PF_COLS);
    ScalerOsdSramBaseAddressSet(_OSD_A, AWTO_PF_ZERO, AWTO_PF_FS_BASE, AWTO_PF_FONT_BASE);
    ScalerOsdFont24x36OnOff(_ENABLE);
    ScalerOsdDoubleFunction(_OSD_DOUBLE_WIDTH_ENABLE, _OSD_DOUBLE_HEIGHT_DISABLE);
    ScalerOsdFontWindowVericalAlignemnt(_ENABLE);
    ScalerOsdPositionOffset(_OSD_POSITION_OFFSET_GLOBAL, AWTO_PF_POS_OFFSET_H, AWTO_PF_POS_OFFSET_V);
    ScalerOsdPosition(_OSD_POSITION_GLOBAL_A, g_ucAwtoPfPosH, g_ucAwtoPfPosV);
    ScalerOsdReferenceDelay(_OSD_A, _OSD_FIRST_DELAY);
    ScalerOsdPosition(_OSD_POSITION_FONT_A, AWTO_PF_ZERO, AWTO_PF_ZERO);
    s_ucStep = 0;
    osd_tc_show(1);
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PF_ARG_ON, 0);
}
