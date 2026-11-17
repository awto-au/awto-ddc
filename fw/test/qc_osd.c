#include <stdint.h>
#include "UserCommonInclude.h"
#include "qc_osd_data.inc"

// #227: Realtek's QC OSD test pattern on the unit (test cmds 0xB0 show, 0xB1 close), ported from RL6449_Series_QC_OSD.c
// (ScalerQC_OSDTestProc init, ScalerQC_OSDFuncApplyMap / FontLoadVLC, ScalerQC_OSDSRAMTestPattern, LoadIcon). Data: qc_osd_data.inc
// (scripts/gen_qc_osd.py): the prebuilt two-map screen (tQCDRAW_MAP, 856 words at SRAM 0), the 1 / 2 / 4-bit fonts and a 64-colour
// palette, loaded through our hardware-VLC path (osd_tc_vlc_*). Map A = 32 x 14 cells (rows from 0, chars from 23), map B = 55 x 7
// (rows from 15, chars from 471); font base 856. Shows: digits (1 bit), the Brook skull x 4 (2 bit, map A row 8), the Luffy skull x 5
// (4 bit, map B). Not rotated with the picture (unit 3 is Rotate 180): the pattern appears turned. Sync line E9 0x50 / 0x51.
// osd_tc_* prototypes: RL6449_Project.h

#define AWTO_QC_MAP_WORDS                       856                 // _OSD_MAP_FONT_BASE_ADDRESS: the map ends where the fonts begin
#define AWTO_QC_1BIT_TILES                      32                  // _1BIT_FONT_ICON_SIZE (tiles of 9 words)
#define AWTO_QC_2BIT_TILES                      120                 // _2BIT_FONT_ICON_SIZE
#define AWTO_QC_2BIT_OFFSET                     16                  // _2BIT_OFFSET: ICON_2BIT(x) = x
#define AWTO_QC_4BIT_ICON                       38                  // ICON_4BIT(0) = (32 + 120) / 4
#define AWTO_QC_ROW_B                           8                   // map A row of the first 2-bit icon row
#define AWTO_QC_MAPA_COL                        32
#define AWTO_QC_MAPB_COL                        55
#define AWTO_QC_ROWCMD_A                        0
#define AWTO_QC_CHARCMD_A                       23
#define AWTO_QC_ROWCMD_B                        15
#define AWTO_QC_CHARCMD_B                       471
#define AWTO_QC_POS_OFFSET_H                    0x3B                // _QC_OSD_POSITION_OFFSET_H / _V (their test panel)
#define AWTO_QC_POS_OFFSET_V                    0x04
#define AWTO_QC_POS_B_Y                         505
#define AWTO_QC_PAL_N                           64
#define AWTO_QC_RGB                             3                   // bytes per palette entry: R, G, B
#define AWTO_QC_R                               0
#define AWTO_QC_G                               1
#define AWTO_QC_B                               2
#define AWTO_QC_1BIT_ICON                       11                  // glyphs of tQCICON_1BIT: ids 0..10
#define AWTO_QC_2BIT_COLS                       8                   // tQCICON_2BIT: 8 x 6, ids 0..47
#define AWTO_QC_2BIT_ROWS                       6
#define AWTO_QC_4BIT_COLS                       11                  // tQCICON_4BIT: 11 x 7, ids ICON_4BIT(0..76)
#define AWTO_QC_4BIT_ROWS                       7

#pragma place bank(12)                      // reads the blobs via movc: same bank as the data above
static void AwtoQcBlob(const uint8_t __code *pucBlob, WORD usWord)     // blob = [8 B value map][2 B BE N][N stream bytes], to SRAM word usWord
{
    static __xdata BYTE s_aucBuf[32];
    WORD usN = ((WORD)pucBlob[8] << 8) | pucBlob[9];
    WORD usO = 10;
    BYTE ucK;
    BYTE ucM;

    for(ucK = 0; ucK < 8; ucK++)
    {
        ScalerSetByte(AWTO_R_FRAME_CTRL_0F + ucK, pucBlob[ucK]);
    }
    ScalerSetBit(AWTO_R_FRAME_CTRL_17, ~(AWTO_F_FRAME_CTRL_17_DECODE_NOCOM_DATA | AWTO_F_FRAME_CTRL_17_OSD_COMPRESSION_EN), AWTO_F_FRAME_CTRL_17_OSD_COMPRESSION_EN);
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usWord, _OSD_WITHOUT_DB);
    while(usN != 0)
    {
        ucM = (usN > sizeof(s_aucBuf)) ? (BYTE)sizeof(s_aucBuf) : (BYTE)usN;
        for(ucK = 0; ucK < ucM; ucK++)
        {
            s_aucBuf[ucK] = pucBlob[usO + ucK];
        }
        for(ucK = 0; ucK < ucM; ucK++)
        {
            ScalerOsdDataPort(s_aucBuf[ucK]);
        }
        usO += ucM;
        usN -= ucM;
    }
    ScalerTimerDelayXmsQuiet(2);                // the decoder flushes its last words after the final stream byte (as osd_tc_vlc_end)
    ScalerSetBit(AWTO_R_FRAME_CTRL_17, ~(AWTO_F_FRAME_CTRL_17_DECODE_NOCOM_DATA | AWTO_F_FRAME_CTRL_17_OSD_COMPRESSION_EN), 0x00);
}

static void AwtoQcIcon(BYTE ucRow, BYTE ucCol, BYTE ucFirst, BYTE ucCols, BYTE ucRows)    // ids ucFirst.. into the cell bytes B1 (the prebuilt map holds the cell types)
{
    BYTE ucR;
    BYTE ucC;
    BYTE ucId = ucFirst;

    for(ucR = 0; ucR < ucRows; ucR++)
    {
        for(ucC = 0; ucC < ucCols; ucC++)
        {
            ScalerOsdSramAddressCount(ucRow + ucR, ucCol + ucC, _OSD_BYTE1);
            ScalerOsdDataPort(ucId++);
        }
    }
}

void AwtoQcOsd(BYTE ucOn)
{
    BYTE ucI;

    osd_tc_close();                                                         // our own OSD off, windows closed
    if(ucOn == 0)
    {
        ScalerOsd2FontFunction(_DISABLE);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 0x51, 0);
        return;
    }
    AwtoOsdTestReset();
    ScalerOsdGlobalDoubleBuffer(_DISABLE);
    ScalerOsdCircuitActivated(_ENABLE);
    ScalerOsdVerticalStartSelect(_OSD_VSYNC_SELECT_DVS);
    for(ucI = 0; ucI < AWTO_QC_PAL_N; ucI++)                                // ScalerQC_OSDTablePaletteAdjust
    {
        ScalerOsdSetColorPalette(ucI, g_qcPal[AWTO_QC_RGB * ucI + AWTO_QC_R], g_qcPal[AWTO_QC_RGB * ucI + AWTO_QC_G], g_qcPal[AWTO_QC_RGB * ucI + AWTO_QC_B]);
    }
    ScalerOsd2FontFunction(_ENABLE);
    AwtoQcBlob(g_qcMap, 0);                                                 // ScalerQC_OSDFontLoadVLC: map at SRAM 0, fonts from the map end
    AwtoQcBlob(g_qcGlobal, AWTO_QC_MAP_WORDS);
    AwtoQcBlob(g_qcBrook, AWTO_QC_MAP_WORDS + 9 * AWTO_QC_1BIT_TILES);
    AwtoQcBlob(g_qcLuffy, AWTO_QC_MAP_WORDS + 9 * (AWTO_QC_1BIT_TILES + AWTO_QC_2BIT_TILES));
    SET_OSD_MAPA_COL_MAX(AWTO_QC_MAPA_COL);                                 // ScalerQC_OSDFuncApplyMap
    ScalerOsdSramBaseAddressSet(_OSD_A, AWTO_QC_ROWCMD_A, AWTO_QC_CHARCMD_A, AWTO_QC_MAP_WORDS);
    SET_OSD_MAPB_COL_MAX(AWTO_QC_MAPB_COL);
    ScalerOsdSramBaseAddressSet(_OSD_B, AWTO_QC_ROWCMD_B, AWTO_QC_CHARCMD_B, AWTO_QC_MAP_WORDS);
    ScalerOsdFontWindowVericalAlignemnt(_ENABLE);                           // positions (ScalerQC_OSDTestProc)
    ScalerOsdPositionOffset(_OSD_POSITION_OFFSET_GLOBAL, AWTO_QC_POS_OFFSET_H, AWTO_QC_POS_OFFSET_V);
    ScalerOsdPosition(_OSD_POSITION_GLOBAL_A, 0, 0);
    ScalerOsdPosition(_OSD_POSITION_GLOBAL_B, 0, AWTO_QC_POS_B_Y);
    ScalerOsdReferenceDelay(_OSD_A, _OSD_FIRST_DELAY);
    ScalerOsdReferenceDelay(_OSD_B, _OSD_SECOND_DELAY);
    ScalerOsdPosition(_OSD_POSITION_FONT_A, 0, 0);
    ScalerOsdPosition(_OSD_POSITION_FONT_B, 0, 0);
    AwtoQcIcon(1, 0, 0, AWTO_QC_1BIT_ICON, 1);                              // ScalerQC_OSDSRAMTestPattern: 1-bit digits
    AwtoQcIcon(2, 0, 0, AWTO_QC_1BIT_ICON, 1);
    AwtoQcIcon(2, 16, 0, AWTO_QC_1BIT_ICON, 1);
    ScalerOsd2BitFontOffset(AWTO_QC_2BIT_OFFSET);                           // 2-bit Brook x 4
    for(ucI = 0; ucI < 4; ucI++)
    {
        AwtoQcIcon(AWTO_QC_ROW_B, ucI * AWTO_QC_2BIT_COLS, 0, AWTO_QC_2BIT_COLS, AWTO_QC_2BIT_ROWS);
        ScalerOsdChange2BitColor(AWTO_QC_ROW_B, ucI * AWTO_QC_2BIT_COLS, AWTO_QC_2BIT_COLS, AWTO_QC_2BIT_ROWS, 0, 1, 2, 3);
    }
    for(ucI = 0; ucI < 5; ucI++)                                            // 4-bit Luffy x 5 on map B
    {
        AwtoQcIcon(ROW_MAPB(0), ucI * AWTO_QC_4BIT_COLS, AWTO_QC_4BIT_ICON, AWTO_QC_4BIT_COLS, AWTO_QC_4BIT_ROWS);
        ScalerOsdChange4BitColor(ROW_MAPB(0), ucI * AWTO_QC_4BIT_COLS, AWTO_QC_4BIT_COLS, AWTO_QC_4BIT_ROWS, 0x01,
                                 _OSD_4BIT_PALETTE_00_01_02_03 | _OSD_4BIT_PALETTE_04_05_06_07 | _OSD_4BIT_PALETTE_08_09_10_11 | _OSD_4BIT_PALETTE_12_13_14_15);
    }
    osd_tc_show(1);
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 0x50, 0);
}
