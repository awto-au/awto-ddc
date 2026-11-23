#include <stdint.h>
#include "UserCommonInclude.h"
#if(_AWTO_SAVER_PACMAN == _ON)                                        // saver not in the image when _OFF (RL6449_Project.h)
#include "pacman_classic_data.inc"

// Classic-layout Pac-Man demo on the unit (data: scripts/gen_pacman_classic.py): the arcade's 28 x 36 tile grid, 12 x 12 visible tiles
// (12 x 18 glyphs, row height 12), outline walls, 1-bit Pac-Man / dots / text, 2-bit ghosts (body, white eye, blue pupil), scaled up by
// the OSD scale-up engine to the panel height (ratio 64 / AWTO_PC_SU_FACTOR); recorded demo (game steps of 2^AWTO_PC_SUB_SHIFT sub-steps: sprites move 12 / that px per call), host-paced by scripts/pacman_unit.py.
//   test cmd 0xB7: draw the maze   0xB8: next step (after the last one the maze is redrawn)   0xB9: off
// SRAM layout: row commands from 0, end word, char commands from AWTO_PC_FS_BASE, glyph words from AWTO_PC_FONT_BASE (1-bit glyphs, then the
// 2-bit glyphs at 18 words * the 2-bit offset). Sync line E9 0x73 (drawn) / 0x74 (value = step) / 0x75 (off).
extern void osd_tc_show(BYTE ucOn);
extern void osd_tc_close(void);

#define AWTO_PC_CELLS                           (AWTO_PC_COLS * AWTO_PC_ROWS)
#define AWTO_PC_FS_BASE                         (AWTO_PC_ROWS + 1)
#define AWTO_PC_FONT_BASE                       (AWTO_PC_FS_BASE + AWTO_PC_CELLS)
#define AWTO_PC_ROW_H                           12                  // visible tile height (the glyphs are 18 rows, the rest is cut)
#define AWTO_PC_TILE_W                          12
#define AWTO_PC_RGB                             3
#define AWTO_PC_R                               0
#define AWTO_PC_G                               1
#define AWTO_PC_B                               2
#define AWTO_PC_DELTA_BYTES                     3                   // cell lo | hi(1:0), kind(2) glyph id bit 8(3) colour(7:4), glyph id lo (gen_pacman_classic.py delta_rec)
#define AWTO_PC_POS_HI_MASK                     0x03
#define AWTO_PC_KIND2_BIT                       0x04                // 2-bit glyph: colour = style index
#define AWTO_PC_ID8_BIT                         0x08
#define AWTO_PC_COL_SHIFT                       4
#define AWTO_PC_ID8_SHIFT                       3
#define AWTO_PC_CHAR1_B0                        0x4C                // 1-bit char command B0 (id bit 8 goes to bit 5)
#define AWTO_PC_CHAR1_ID8_SHIFT                 5
#define AWTO_PC_BG                              1                   // palette index of the cell background (K_BG)
#define AWTO_PC_STYLE_BYTES                     2                   // per style: B0, B2 of the 2-bit char command
#define AWTO_PC_SUB_MASK                        ((1 << AWTO_PC_SUB_SHIFT) - 1)
#define AWTO_PC_SU_FACTOR                       13                  // scale-up ratio = 64 / 13 = 4.9: 432 lines -> 2126 of the 2160 panel lines
#define AWTO_PC_POS_OFFSET_H                    0x3B                // as the QC pattern
#define AWTO_PC_POS_OFFSET_V                    0x04
#define AWTO_PC_POS_H                           274                 // hd units of 4 panel px: (3840 - 1646) / 2 centres the maze
#define AWTO_PC_ZERO                            0x00
#define AWTO_PC_KICK_MASK                       0x7F                // kick the watchdog every 128 data port bytes: the load is ~14 KB, near the 586 ms bite time
#define PC_KICK(i)                              do { if(((i) & AWTO_PC_KICK_MASK) == AWTO_PC_ZERO) { AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT; } } while(0)
#define AWTO_PC_SND_INTRO                       0                   // AwtoPmSound(cmd - AWTO_TC_PACMAN_SND): 0 intro, 1 waka (loops), 2 death, 3 calibration, 4 stop
#define AWTO_PC_SND_WAKA                        1
#define AWTO_PC_SND_DEATH                       2
#define AWTO_PC_SND_STOP                        4
#define AWTO_PC_SND_GHOST                       6                   // 5 = alert (saver.c)
#define AWTO_PC_SND_FRUIT                       7
#define AWTO_PC_SND_WAKA_OFF                    8
#define AWTO_PC_BLOCK_BYTES                     27                  // one glyph plane: 9 words x 3 bytes (1-bit glyph = 1 block, 2-bit glyph = 2 blocks, low bit plane first)
#define AWTO_PC_BLOCK_ROT_BYTES                 18                  // the visible 12 of its 18 rows (6 words); the rest is padding
#define AWTO_PC_BLOCK_ROT_WORDS                 6
#define AWTO_PC_PX_PER_HD                       4                   // OSD horizontal position unit: 4 panel px
#define AWTO_PC_ARG_ON                          0x73
#define AWTO_PC_ARG_STEP                        0x74
#define AWTO_PC_ARG_OFF                         0x75

static __xdata WORD s_usStep;
__xdata BYTE g_ucAwtoPcFactor = AWTO_PC_SU_FACTOR;      // scale-up factor (0 = off), host-settable for tuning
__xdata WORD g_usAwtoPcPosH = AWTO_PC_POS_H;            // WORD: the centred position is above 255
__xdata WORD g_usAwtoPcPosV;

#pragma place group(pacman_12)                      // each reader sits in the bank of the table it reads (a pragma pins only the next definition)
static BYTE PcPal(BYTE ucK)
{
    return g_pcPal[ucK];
}

#pragma place group(pacman_12)
static BYTE PcGlyph(WORD usK)
{
    return g_pcGlyph[usK];
}

#pragma place group(pacman_12)
static BYTE PcStyle(BYTE ucK)
{
    return g_pcStyle[ucK];
}

#pragma place group(pacman_13)
static BYTE PcCell(WORD usK)
{
    return g_pcCell[usK];
}

#pragma place group(pacman_12)
static BYTE PcIdx(WORD usK)
{
    return g_pcIdx[usK];
}

#pragma place group(pacman_12)
static BYTE PcDeltaA(WORD usK)
{
    return g_pcDeltaA[usK];
}

#pragma place group(pacman_12)
static BYTE PcEvt(WORD usStep)
{
    return g_pcEvt[usStep];
}

#pragma place group(pacman_11)
static BYTE PcDeltaB(WORD usK)
{
    return g_pcDeltaB[usK];
}

static BYTE PcDelta(WORD usK)
{
    return (usK < AWTO_PC_HALF_BYTES) ? PcDeltaA(usK) : PcDeltaB(usK - AWTO_PC_HALF_BYTES);
}

static void PcWord(WORD usAddr, BYTE ucB0, BYTE ucB1, BYTE ucB2)
{
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usAddr, _OSD_WITHOUT_DB);
    AWTO_OSD_PORT(ucB0);
    AWTO_OSD_PORT(ucB1);
    AWTO_OSD_PORT(ucB2);
}

static void PcCellSet(WORD usPos, BYTE ucB0, BYTE ucB1, BYTE ucB2)
{
    if(g_ucAwtoOsdRot != 0)
    {
        usPos = AwtoOsdRotCell(usPos, AWTO_PC_CELLS);
    }
    PcWord(AWTO_PC_FS_BASE + usPos, ucB0, ucB1, ucB2);
}

static void PcMaze(void)
{
    WORD usC;
    WORD usSrc;
    BYTE ucB;

    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_PC_FS_BASE, _OSD_WITHOUT_DB);        // the data port counts words: one address set for all cells
    for(usC = 0; usC < AWTO_PC_CELLS; usC++)
    {
        PC_KICK(usC);
        usSrc = (g_ucAwtoOsdRot != 0) ? AwtoOsdRotCell(usC, AWTO_PC_CELLS) : usC;            // turned map: the cell at the mirrored place
        for(ucB = 0; ucB < AWTO_PC_RGB; ucB++)
        {
            AWTO_OSD_PORT(PcCell((WORD)AWTO_PC_RGB * usSrc + ucB));
        }
    }
}

static void PcStep(WORD usStep)
{
    WORD usO = ((WORD)PcIdx(2 * usStep + 1) << 8) | PcIdx(2 * usStep);
    WORD usEnd = ((WORD)PcIdx(2 * usStep + 3) << 8) | PcIdx(2 * usStep + 2);
    WORD usPos;
    BYTE ucB0;
    BYTE ucB1;
    BYTE ucB2;

    for(; usO < usEnd; usO += AWTO_PC_DELTA_BYTES)
    {
        ucB1 = PcDelta(usO + 1);
        usPos = ((WORD)(ucB1 & AWTO_PC_POS_HI_MASK) << 8) | PcDelta(usO);
        ucB2 = PcDelta(usO + 2);                                            // glyph id lo
        if((ucB1 & AWTO_PC_KIND2_BIT) != 0)
        {
            ucB0 = PcStyle((BYTE)((ucB1 >> AWTO_PC_COL_SHIFT) * AWTO_PC_STYLE_BYTES));
            ucB1 = PcStyle((BYTE)((ucB1 >> AWTO_PC_COL_SHIFT) * AWTO_PC_STYLE_BYTES + 1));
            PcCellSet(usPos, ucB0, ucB2, ucB1);
        }
        else
        {
            PcCellSet(usPos, AWTO_PC_CHAR1_B0 | (((ucB1 & AWTO_PC_ID8_BIT) >> AWTO_PC_ID8_SHIFT) << AWTO_PC_CHAR1_ID8_SHIFT), ucB2,
                      ((ucB1 >> AWTO_PC_COL_SHIFT) << AWTO_PC_COL_SHIFT) | AWTO_PC_BG);
        }
    }
}

void AwtoPacmanClassic(BYTE ucCmd)
{
    WORD usI;
    BYTE ucB;
    BYTE ucK;
    BYTE ucEv;

    if(ucCmd == 0)
    {
        osd_tc_close();
        ScalerOsdScaleUpOnOff(_DISABLE);
        AwtoPmSound(AWTO_PC_SND_STOP);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PC_ARG_OFF, 0);
        return;
    }
    if(ucCmd == 2)                                                          // next step: its cell updates
    {
        if(s_usStep >= AWTO_PC_STEPS)
        {
            PcMaze();                                                       // after the last step: the maze from the start
            s_usStep = 0;
        }
        PcStep(s_usStep);
        ucEv = PcEvt(s_usStep >> AWTO_PC_SUB_SHIFT);                        // per game step: low nibble = sound event (first sub-step only), high nibble = background state (gen_pacman_classic.py)
        ucB = ucEv >> AWTO_PC_EV_BG_SHIFT;
        ucEv = ((s_usStep & AWTO_PC_SUB_MASK) == 0) ? (ucEv & AWTO_PC_EV_EV_MASK) : AWTO_PC_EV_NONE;
        if(ucEv == AWTO_PC_EV_INTRO)
        {
            AwtoPmSound(AWTO_PC_SND_INTRO);
        }
        else if(ucEv == AWTO_PC_EV_WAKA_ON)
        {
            AwtoPmSound(AWTO_PC_SND_WAKA);
        }
        else if(ucEv == AWTO_PC_EV_DEATH)
        {
            AwtoPmSound(AWTO_PC_SND_DEATH);
        }
        else if(ucEv == AWTO_PC_EV_GHOST)
        {
            AwtoPmSound(AWTO_PC_SND_GHOST);
        }
        else if(ucEv == AWTO_PC_EV_FRUIT)
        {
            AwtoPmSound(AWTO_PC_SND_FRUIT);
        }
        else if(ucEv == AWTO_PC_EV_WAKA_OFF)
        {
            AwtoPmSound(AWTO_PC_SND_WAKA_OFF);
        }
        else if(ucEv == AWTO_PC_EV_STOP)
        {
            AwtoPmSound(AWTO_PC_SND_STOP);
        }
        AwtoPmSoundBg(ucB);                                                 // siren / frightened state; the player acts on a change
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PC_ARG_STEP, (BYTE)s_usStep);
        s_usStep++;
        return;
    }
    AwtoOsdScreenBegin();                                                   // our own OSD off, windows closed, rotation latched, state reset
    for(usI = 0; usI < AWTO_PC_PAL_N; usI++)
    {
        ScalerOsdSetColorPalette((BYTE)usI, PcPal((BYTE)(AWTO_PC_RGB * usI + AWTO_PC_R)), PcPal((BYTE)(AWTO_PC_RGB * usI + AWTO_PC_G)), PcPal((BYTE)(AWTO_PC_RGB * usI + AWTO_PC_B)));
    }
    ScalerOsd2FontFunction(_DISABLE);
    AwtoOsdRowCmds(AWTO_PC_ROWS, AWTO_PC_ROW_H, AWTO_PC_COLS);
    PcMaze();
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_PC_FONT_BASE, _OSD_WITHOUT_DB);
    for(usI = 0; usI < AWTO_PC_GLYPH_BYTES; usI += AWTO_PC_BLOCK_BYTES)             // per glyph plane block
    {
        for(ucK = 0; ucK < AWTO_PC_BLOCK_BYTES; ucK++)
        {
            PC_KICK(usI + ucK);
            if((g_ucAwtoOsdRot != 0) && (ucK < AWTO_PC_BLOCK_ROT_BYTES))                // turned: the 12 visible rows turned 180 inside the glyph
            {
                ucB = AwtoOsdRevByte(PcGlyph(usI + AwtoOsdRotSrc(ucK, AWTO_PC_BLOCK_ROT_WORDS)));
            }
            else
            {
                ucB = PcGlyph(usI + ucK);
            }
            AWTO_OSD_PORT(ucB);
        }
    }
    SET_OSD_MAPA_COL_MAX(AWTO_PC_COLS);
    ScalerOsdSramBaseAddressSet(_OSD_A, AWTO_PC_ZERO, AWTO_PC_FS_BASE, AWTO_PC_FONT_BASE);
    ScalerOsd2BitFontOffset(AWTO_PC_OFF2);
    ScalerOsdFontWindowVericalAlignemnt(_ENABLE);
    ScalerOsdPositionOffset(_OSD_POSITION_OFFSET_GLOBAL, AWTO_PC_POS_OFFSET_H, AWTO_PC_POS_OFFSET_V);
    ScalerOsdPosition(_OSD_POSITION_GLOBAL_A, g_usAwtoPcPosH, g_usAwtoPcPosV);
    ScalerOsdReferenceDelay(_OSD_A, _OSD_FIRST_DELAY);
    ScalerOsdPosition(_OSD_POSITION_FONT_A, AWTO_PC_ZERO, AWTO_PC_ZERO);
    if(g_ucAwtoPcFactor != AWTO_PC_ZERO)                                    // scale-up engine over the whole map (ScalerQC_OSDScaleUp sequence)
    {
        ScalerOsdScaleUpHorSize(g_usAwtoPcPosH * AWTO_PC_PX_PER_HD, (WORD)AWTO_PC_COLS * AWTO_PC_TILE_W);     // the window is in display coordinates: it starts where the OSD starts
        ScalerOsdScaleUpVerSize(g_usAwtoPcPosV, (WORD)AWTO_PC_ROWS * AWTO_PC_ROW_H);
        ScalerOsdScaleUpVerFactor(g_ucAwtoPcFactor);
        ScalerOsdScaleUpHorFactor(g_ucAwtoPcFactor);
        ScalerOsdScaleUpBoundaryCodition(_OSD_SCALING_BOUNDARY_NEIGHTBOOR);
        ScalerOsdScaleUpOnOff(_ENABLE);
    }
    s_usStep = 0;
    osd_tc_show(1);
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PC_ARG_ON, 0);
}
#endif                                                         // _AWTO_SAVER_PACMAN
