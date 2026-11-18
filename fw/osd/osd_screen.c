#include "UserCommonInclude.h"
#include "../../tools/osd_lines/osd_lines.h"

// Shared helpers of the full-screen OSD users that draw their own map + glyphs (scope savers, QC pattern): docs/osd-rotation.md.

#define AWTO_OSDS_WORD_BYTES                    3

void AwtoOsdWord(WORD usAddr, BYTE ucB0, WORD usB12)
{
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usAddr, _OSD_WITHOUT_DB);
    ScalerOsdDataPort(ucB0);
    ScalerOsdDataPort((BYTE)(usB12 >> 8));
    ScalerOsdDataPort((BYTE)usB12);
}

void AwtoOsdRowCmds(BYTE ucRows, BYTE ucRowH, BYTE ucCols)
{
    BYTE ucI;

    for(ucI = 0; ucI < ucRows; ucI++)
    {
        AwtoOsdWord(ucI, AWTO_OSD_ROW_B0, ((WORD)(ucRowH - 1) << 8) | ucCols);
    }
    AwtoOsdWord(ucRows, AWTO_OSD_ZERO, AWTO_OSD_ZERO);
}

void AwtoOsdGlyph(WORD usAddr, const BYTE __xdata *pucB, BYTE ucWords)
{
    BYTE ucK;

    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usAddr, _OSD_WITHOUT_DB);
    for(ucK = 0; ucK < ucWords; ucK++)                  // canonical c0 c1 c2 -> stored B0 B1 B2 = c2 c1 c0 (osd_lines_view.py); port written directly (ScalerOsdDataPort = a banked call per byte)
    {
        if(g_ucAwtoOsdRot != 0)                         // words in reverse order, bits reversed
        {
            BYTE ucW = (BYTE)((ucWords - 1 - ucK) * AWTO_OSDS_WORD_BYTES);

            AWTO_XFR(AWTO_R_OSD_DATA_PORT) = AwtoOsdRevByte(pucB[ucW]);
            AWTO_XFR(AWTO_R_OSD_DATA_PORT) = AwtoOsdRevByte(pucB[ucW + 1]);
            AWTO_XFR(AWTO_R_OSD_DATA_PORT) = AwtoOsdRevByte(pucB[ucW + 2]);
        }
        else
        {
            AWTO_XFR(AWTO_R_OSD_DATA_PORT) = pucB[AWTO_OSDS_WORD_BYTES * ucK + 2];
            AWTO_XFR(AWTO_R_OSD_DATA_PORT) = pucB[AWTO_OSDS_WORD_BYTES * ucK + 1];
            AWTO_XFR(AWTO_R_OSD_DATA_PORT) = pucB[AWTO_OSDS_WORD_BYTES * ucK];
        }
    }
}

void AwtoOsdPlaceScaleUp(BYTE ucPosH, BYTE ucPosV, BYTE ucCols, BYTE ucRows, BYTE ucFactor)
{
    ScalerOsdFontWindowVericalAlignemnt(_ENABLE);
    ScalerOsdPositionOffset(_OSD_POSITION_OFFSET_GLOBAL, AWTO_OSD_POS_OFFSET_H, AWTO_OSD_POS_OFFSET_V);
    ScalerOsdPosition(_OSD_POSITION_GLOBAL_A, ucPosH, ucPosV);
    ScalerOsdReferenceDelay(_OSD_A, _OSD_FIRST_DELAY);
    ScalerOsdPosition(_OSD_POSITION_FONT_A, AWTO_OSD_ZERO, AWTO_OSD_ZERO);
    ScalerOsdScaleUpHorSize((WORD)ucPosH * AWTO_OSD_PX_PER_HD, (WORD)ucCols * OSD_TILE_W);      // the window is in display coordinates: it starts where the OSD starts
    ScalerOsdScaleUpVerSize(ucPosV, (WORD)ucRows * OSD_TILE_H);
    ScalerOsdScaleUpVerFactor(ucFactor);
    ScalerOsdScaleUpHorFactor(ucFactor);
    ScalerOsdScaleUpBoundaryCodition(_OSD_SCALING_BOUNDARY_NEIGHTBOOR);
    ScalerOsdScaleUpOnOff(_ENABLE);
}

void AwtoOsdScreenBegin(void)
{
    osd_tc_close();
    g_ucAwtoOsdRot = AwtoOsdRot180();
    AwtoOsdTestReset();
    ScalerOsdGlobalDoubleBuffer(_DISABLE);
    ScalerOsdCircuitActivated(_ENABLE);
    ScalerOsdVerticalStartSelect(_OSD_VSYNC_SELECT_DVS);
}

void AwtoOsdScreenOff(void)
{
    osd_tc_close();
    ScalerOsdScaleUpOnOff(_DISABLE);
}
