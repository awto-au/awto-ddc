#include "UserCommonInclude.h"
#include "../../tools/osd_lines/osd_lines.h"

// Shared helpers of the full-screen OSD users that draw their own map + glyphs (scope savers, QC pattern): docs/osd/rotation.md.

#define AWTO_OSDS_WORD_BYTES                    3
#define AWTO_OSDS_GLYPH_WORDS                   (OSD_TILE_BYTES / AWTO_OSDS_WORD_BYTES)
#define AWTO_OSDS_CHAR1_B0                      0x40                // 1-bit char command; B0[4:0] = glyph width
#define AWTO_OSDS_ID_HI_SHIFT                   5                   // B0[5] = glyph id bit 8
#define AWTO_OSDS_ID_LO_MASK                    0xFF

static __xdata WORD s_usOsdsCells;                                  // geometry latched by AwtoOsdMap1 for AwtoOsdTile (one screen at a time)
static __xdata WORD s_usOsdsFontBase;

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
    for(ucK = 0; ucK < ucWords; ucK++)                  // canonical c0 c1 c2 -> stored B0 B1 B2 = c2 c1 c0 (osd_lines_view.py)
    {
        if(g_ucAwtoOsdRot != 0)                         // words in reverse order, bits reversed
        {
            BYTE ucW = (BYTE)((ucWords - 1 - ucK) * AWTO_OSDS_WORD_BYTES);

            ScalerOsdDataPort(AwtoOsdRevByte(pucB[ucW]));
            ScalerOsdDataPort(AwtoOsdRevByte(pucB[ucW + 1]));
            ScalerOsdDataPort(AwtoOsdRevByte(pucB[ucW + 2]));
        }
        else
        {
            ScalerOsdDataPort(pucB[AWTO_OSDS_WORD_BYTES * ucK + 2]);
            ScalerOsdDataPort(pucB[AWTO_OSDS_WORD_BYTES * ucK + 1]);
            ScalerOsdDataPort(pucB[AWTO_OSDS_WORD_BYTES * ucK]);
        }
    }
}

void AwtoOsdMap1(BYTE ucCols, BYTE ucRows, BYTE ucAttr)
{
    WORD usI;

    s_usOsdsCells = (WORD)ucCols * ucRows;
    s_usOsdsFontBase = ucRows + 1 + s_usOsdsCells;                      // row commands + end word, then one char command per cell
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, ucRows + 1, _OSD_WITHOUT_DB);
    for(usI = 0; usI < s_usOsdsCells; usI++)
    {
        ScalerOsdDataPort(AWTO_OSDS_CHAR1_B0 | OSD_TILE_W | (BYTE)((usI >> 8) << AWTO_OSDS_ID_HI_SHIFT));
        ScalerOsdDataPort((BYTE)(usI & AWTO_OSDS_ID_LO_MASK));
        ScalerOsdDataPort(ucAttr);
    }
    SET_OSD_MAPA_COL_MAX(ucCols);
    ScalerOsdSramBaseAddressSet(_OSD_A, AWTO_OSD_ZERO, ucRows + 1, s_usOsdsFontBase);
}

void AwtoOsdTile(WORD usCell, const BYTE __xdata *pucB)
{
    if(g_ucAwtoOsdRot != 0)                                             // turned 180 (docs/osd/rotation.md): the glyph slot of the mirrored cell
    {
        usCell = AwtoOsdRotCell(usCell, s_usOsdsCells);
    }
    AwtoOsdGlyph(s_usOsdsFontBase + AWTO_OSDS_GLYPH_WORDS * usCell, pucB, AWTO_OSDS_GLYPH_WORDS);
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
