#include <stdint.h>
#include "UserCommonInclude.h"
#include "flash_screen_data.inc"

// Flash warning screen (#232): a huge Pac-Man on red, drawn by the running firmware just before the host flasher halts the MCU (DDC/CI VCP 0xEB = 5,
// `dev.py flash`). The OSD circuit keeps drawing from its SRAM while the MCU is held in ISP, so the flasher (scripts/flash_screen.py) only swaps the
// glyph id of the one map cell between sectors (mouth open / shut) and turns the OSD off before the reset. One 12 x 12 tile scaled up 64 : 1.
// SRAM: row command word 0, end word 1, char command word 2, glyph 0 from word 3 (9 words), glyph 1 from word 12. Values below are mirrored in scripts/flash_screen.py
// (tests/test_flash_screen.py checks they agree).
extern void osd_tc_show(BYTE ucOn);
extern void osd_tc_close(void);

#define AWTO_FS_ROW_B0                          0x80
#define AWTO_FS_ROW_H                           12                  // visible rows of the glyph
#define AWTO_FS_TILE_W                          12
#define AWTO_FS_CHAR_B0                         0x4C                // 1-bit char, width 12
#define AWTO_FS_BG                              1                   // palette indexes
#define AWTO_FS_FG                              2
#define AWTO_FS_FG_SHIFT                        4
#define AWTO_FS_CHAR_B2                         ((AWTO_FS_FG << AWTO_FS_FG_SHIFT) | AWTO_FS_BG)
#define AWTO_FS_ROW_WORD                        0
#define AWTO_FS_END_WORD                        1
#define AWTO_FS_CHAR_WORD                       2                   // the one cell
#define AWTO_FS_FONT_BASE                       3
#define AWTO_FS_GLYPH_WORDS                     9
#define AWTO_FS_ROT_BYTES                       18                  // the 12 visible rows (6 words) are turned for Rotate 180
#define AWTO_FS_ROT_WORDS                       6
#define AWTO_FS_BG_R                            200                 // warning red
#define AWTO_FS_BG_G                            0
#define AWTO_FS_BG_B                            0
#define AWTO_FS_FG_R                            255                 // Pac-Man yellow
#define AWTO_FS_FG_G                            220
#define AWTO_FS_FG_B                            0
#define AWTO_FS_SU_FACTOR                       1                   // ratio 64 / 1: 12 px -> 768 px (the largest the engine does)
#define AWTO_FS_SU_PX                           (AWTO_FS_TILE_W * 64 / AWTO_FS_SU_FACTOR)
#define AWTO_FS_PANEL_W                         3840
#define AWTO_FS_PANEL_H                         2160
#define AWTO_FS_POS_OFFSET_H                    0x3B                // as the other test screens
#define AWTO_FS_POS_OFFSET_V                    0x04
#define AWTO_FS_PX_PER_HD                       4                   // OSD horizontal position unit: 4 panel px
#define AWTO_FS_POS_H                           ((AWTO_FS_PANEL_W - AWTO_FS_SU_PX) / 2 / AWTO_FS_PX_PER_HD)
#define AWTO_FS_POS_V                           ((AWTO_FS_PANEL_H - AWTO_FS_SU_PX) / 2)
#define AWTO_FS_ZERO                            0x00
#define AWTO_FS_ARG_ON                          0x7E
#define AWTO_FS_ARG_OFF                         0x7F

#pragma place bank(11)                      // leaf reader in the data's bank
static BYTE FsByte(BYTE ucIdx)
{
    return g_aucFsGlyph[ucIdx];
}

static void FsWord(WORD usAddr, BYTE ucB0, BYTE ucB1, BYTE ucB2)
{
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usAddr, _OSD_WITHOUT_DB);
    ScalerOsdDataPort(ucB0);
    ScalerOsdDataPort(ucB1);
    ScalerOsdDataPort(ucB2);
}

void AwtoFlashScreen(BYTE ucOn)
{
    BYTE ucG;
    BYTE ucK;
    BYTE ucB;
    BYTE ucRot;

    osd_tc_close();
    if(ucOn == 0)
    {
        ScalerOsdScaleUpOnOff(_DISABLE);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_FS_ARG_OFF, 0);
        return;
    }
    ucRot = AwtoOsdRot180();
    AwtoOsdTestReset();
    ScalerOsdGlobalDoubleBuffer(_DISABLE);
    ScalerOsdCircuitActivated(_ENABLE);
    ScalerOsdVerticalStartSelect(_OSD_VSYNC_SELECT_DVS);
    ScalerOsdSetColorPalette(AWTO_FS_ZERO, AWTO_FS_ZERO, AWTO_FS_ZERO, AWTO_FS_ZERO);
    ScalerOsdSetColorPalette(AWTO_FS_BG, AWTO_FS_BG_R, AWTO_FS_BG_G, AWTO_FS_BG_B);
    ScalerOsdSetColorPalette(AWTO_FS_FG, AWTO_FS_FG_R, AWTO_FS_FG_G, AWTO_FS_FG_B);
    ScalerOsd2FontFunction(_DISABLE);
    FsWord(AWTO_FS_ROW_WORD, AWTO_FS_ROW_B0, AWTO_FS_ROW_H - 1, 1);
    FsWord(AWTO_FS_END_WORD, AWTO_FS_ZERO, AWTO_FS_ZERO, AWTO_FS_ZERO);
    FsWord(AWTO_FS_CHAR_WORD, AWTO_FS_CHAR_B0, AWTO_FS_ZERO, AWTO_FS_CHAR_B2);
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_FS_FONT_BASE, _OSD_WITHOUT_DB);
    for(ucG = 0; ucG < 2; ucG++)
    {
        for(ucK = 0; ucK < AWTO_FS_GLYPH_BYTES; ucK++)
        {
            if((ucRot != 0) && (ucK < AWTO_FS_ROT_BYTES))              // turned 180 (docs/osd-rotation.md)
            {
                ucB = AwtoOsdRevByte(FsByte(ucG * AWTO_FS_GLYPH_BYTES + AwtoOsdRotSrc(ucK, AWTO_FS_ROT_WORDS)));
            }
            else
            {
                ucB = FsByte(ucG * AWTO_FS_GLYPH_BYTES + ucK);
            }
            ScalerOsdDataPort(ucB);
        }
    }
    SET_OSD_MAPA_COL_MAX(1);
    ScalerOsdSramBaseAddressSet(_OSD_A, AWTO_FS_ROW_WORD, AWTO_FS_CHAR_WORD, AWTO_FS_FONT_BASE);
    ScalerOsdFontWindowVericalAlignemnt(_ENABLE);
    ScalerOsdPositionOffset(_OSD_POSITION_OFFSET_GLOBAL, AWTO_FS_POS_OFFSET_H, AWTO_FS_POS_OFFSET_V);
    ScalerOsdPosition(_OSD_POSITION_GLOBAL_A, AWTO_FS_POS_H, AWTO_FS_POS_V);
    ScalerOsdReferenceDelay(_OSD_A, _OSD_FIRST_DELAY);
    ScalerOsdPosition(_OSD_POSITION_FONT_A, AWTO_FS_ZERO, AWTO_FS_ZERO);
    ScalerOsdScaleUpHorSize(AWTO_FS_POS_H * AWTO_FS_PX_PER_HD, AWTO_FS_TILE_W);        // the window is in display coordinates: it starts where the OSD starts
    ScalerOsdScaleUpVerSize(AWTO_FS_POS_V, AWTO_FS_ROW_H);
    ScalerOsdScaleUpVerFactor(AWTO_FS_SU_FACTOR);
    ScalerOsdScaleUpHorFactor(AWTO_FS_SU_FACTOR);
    ScalerOsdScaleUpBoundaryCodition(_OSD_SCALING_BOUNDARY_NEIGHTBOOR);
    ScalerOsdScaleUpOnOff(_ENABLE);
    osd_tc_show(1);
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_FS_ARG_ON, 0);
}
