#include <stdint.h>
#include <string.h>
#include "UserCommonInclude.h"
#define OSD_NO_FLUSH
#include "../../tools/osd_lines/osd_lines.c"

// Scope screensaver (docs/screensaver.md): a 384 x 216 waveform screen drawn with the tiled line renderer tools/osd_lines (awto-ddc#226),
// 32 x 12 tiles of 12 x 18, one font glyph per cell, scaled up to the panel. XDATA is tight (floor 700 B), so the canvas is one tile
// column band (1 x 6 tiles, 162 B) redrawn 32 x 2 times per frame; every pass draws only the shapes that touch its band.
//   AwtoScopeSaver(1) draw the screen   (2) next frame   (0) off
extern void osd_tc_show(BYTE ucOn);
extern void osd_tc_close(void);

#define AWTO_SC_COLS                            32
#define AWTO_SC_ROWS                            12
#define AWTO_SC_TILE_W                          OSD_TILE_W
#define AWTO_SC_TILE_H                          OSD_TILE_H
#define AWTO_SC_W                               (AWTO_SC_COLS * AWTO_SC_TILE_W)
#define AWTO_SC_H                               (AWTO_SC_ROWS * AWTO_SC_TILE_H)
#define AWTO_SC_BANDS                           2
#define AWTO_SC_BAND_ROWS                       (AWTO_SC_ROWS / AWTO_SC_BANDS)
#define AWTO_SC_BAND_H                          (AWTO_SC_BAND_ROWS * AWTO_SC_TILE_H)
#define AWTO_SC_CELLS                           (AWTO_SC_COLS * AWTO_SC_ROWS)
#define AWTO_SC_FS_BASE                         (AWTO_SC_ROWS + 1)
#define AWTO_SC_FONT_BASE                       (AWTO_SC_FS_BASE + AWTO_SC_CELLS)
#define AWTO_SC_GLYPH_WORDS                     9
#define AWTO_SC_WORD_BYTES                      3
#define AWTO_SC_PX_PER_HD                       4                   // OSD horizontal position unit: 4 panel px
#define AWTO_SC_ROW_B0                          0x80
#define AWTO_SC_CHAR_B0                         0x40                // 1-bit char command
#define AWTO_SC_CHAR_W                          AWTO_SC_TILE_W      // B0[4:0] = glyph width
#define AWTO_SC_ID_HI_SHIFT                     5                   // B0[5] = glyph id bit 8
#define AWTO_SC_ID_LO_MASK                      0xFF
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
#define AWTO_SC_POS_OFFSET_H                    0x3B                // as the QC pattern and Pac-Man
#define AWTO_SC_POS_OFFSET_V                    0x04
#define AWTO_SC_POS_H                           41                  // hd units of 4 panel px: (3840 - 3511) / 2 / 4
#define AWTO_SC_POS_V                           92                  // (2160 - 1975) / 2
#define AWTO_SC_ZERO                            0x00
#define AWTO_SC_GRID_STEP_X                     48                  // dotted graticule: 8 x 4 divisions
#define AWTO_SC_GRID_STEP_Y                     54
#define AWTO_SC_DOT                             4                   // dot spacing of the graticule
#define AWTO_SC_MID_Y                           (AWTO_SC_H / 2)
#define AWTO_SC_AMP1                            62                  // trace: two sines, px
#define AWTO_SC_AMP2                            28
#define AWTO_SC_SINE_N                          64
#define AWTO_SC_SINE_MASK                       (AWTO_SC_SINE_N - 1)
#define AWTO_SC_SINE_AMP                        127                 // table peak
#define AWTO_SC_SINE_SHIFT                      7                   // table peak 127 -> divide by 128
#define AWTO_SC_PH_STEP                         3                   // phase advance per frame, table units
#define AWTO_SC_H2_PER_PX                       4                   // second component: table units per px
#define AWTO_SC_H2_PH                           2                   // second component phase per frame
#define AWTO_SC_ARG_ON                          0x76
#define AWTO_SC_ARG_FRAME                       0x77
#define AWTO_SC_ARG_OFF                         0x78

// 64-point sine, peak 127 (round(127 * sin(2 pi k / 64)))
static __code int8_t s_tSine[AWTO_SC_SINE_N] = {
    0, 12, 25, 37, 49, 60, 71, 81, 90, 98, 106, 112, 117, 122, 125, 126,
    127, 126, 125, 122, 117, 112, 106, 98, 90, 81, 71, 60, 49, 37, 25, 12,
    0, -12, -25, -37, -49, -60, -71, -81, -90, -98, -106, -112, -117, -122, -125, -126,
    -127, -126, -125, -122, -117, -112, -106, -98, -90, -81, -71, -60, -49, -37, -25, -12};

__xdata uint8_t g_aucScPix[OSD_BITMAP_BYTES(1, AWTO_SC_BAND_ROWS)];
__xdata uint8_t g_aucScDirty[OSD_DIRTY_BYTES(1, AWTO_SC_BAND_ROWS)];
__xdata osd_canvas g_scCv;           // shared with scope_saver2.c: one saver runs at a time, XDATA floor
static __xdata BYTE s_ucPhase;
static __xdata BYTE s_ucCol;                                            // next column of the frame being drawn
static __xdata BYTE s_ucShown;
static __xdata WORD s_usCell0;                                          // first cell (global tile index) of the band being drawn

static void ScWord(WORD usAddr, BYTE ucB0, BYTE ucB1, BYTE ucB2)
{
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usAddr, _OSD_WITHOUT_DB);
    ScalerOsdDataPort(ucB0);
    ScalerOsdDataPort(ucB1);
    ScalerOsdDataPort(ucB2);
}

static void ScUpload(BYTE ucTile)
{
    BYTE ucK;
    WORD usCell = s_usCell0 + (WORD)ucTile * AWTO_SC_COLS;
    const uint8_t *pucB = g_aucScPix + (WORD)ucTile * OSD_TILE_BYTES;

    if(g_ucAwtoOsdRot != 0)                                                    // turned 180 (docs/osd-rotation.md): the glyph slot of the mirrored cell, words in reverse order, bits reversed
    {
        usCell = AwtoOsdRotCell(usCell, AWTO_SC_CELLS);
    }
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_SC_FONT_BASE + AWTO_SC_GLYPH_WORDS * usCell, _OSD_WITHOUT_DB);
    for(ucK = 0; ucK < AWTO_SC_GLYPH_WORDS; ucK++)                      // canonical c0 c1 c2 -> stored B0 B1 B2 = c2 c1 c0 (osd_lines_view.py)
    {
        if(g_ucAwtoOsdRot != 0)
        {
            WORD usW = (WORD)(AWTO_SC_GLYPH_WORDS - 1 - ucK) * AWTO_SC_WORD_BYTES;

            ScalerOsdDataPort(AwtoOsdRevByte(pucB[usW]));
            ScalerOsdDataPort(AwtoOsdRevByte(pucB[usW + 1]));
            ScalerOsdDataPort(AwtoOsdRevByte(pucB[usW + 2]));
        }
        else
        {
            ScalerOsdDataPort(pucB[AWTO_SC_WORD_BYTES * ucK + 2]);
            ScalerOsdDataPort(pucB[AWTO_SC_WORD_BYTES * ucK + 1]);
            ScalerOsdDataPort(pucB[AWTO_SC_WORD_BYTES * ucK]);
        }
    }
}

static int16_t ScY(int16_t sX, BYTE ucPh)
{
    int16_t sV1 = ((int16_t)s_tSine[(sX + ucPh) & AWTO_SC_SINE_MASK] * AWTO_SC_AMP1) >> AWTO_SC_SINE_SHIFT;
    int16_t sV2 = ((int16_t)s_tSine[(sX * AWTO_SC_H2_PER_PX + ucPh * AWTO_SC_H2_PH) & AWTO_SC_SINE_MASK] * AWTO_SC_AMP2) >> AWTO_SC_SINE_SHIFT;

    return AWTO_SC_MID_Y - sV1 - sV2;
}

static void ScPass(BYTE ucCol, BYTE ucBand)
{
    int16_t sOx = (int16_t)ucCol * AWTO_SC_TILE_W;
    int16_t sOy = (int16_t)ucBand * AWTO_SC_BAND_H;
    int16_t sX;
    int16_t sY;
    int16_t sPrev;
    int16_t sCur;
    BYTE ucT;

    osd_clear(&g_scCv);
    osd_mark_all_dirty(&g_scCv);
    for(sY = sOy - (sOy % AWTO_SC_GRID_STEP_Y); sY < sOy + AWTO_SC_BAND_H; sY += AWTO_SC_GRID_STEP_Y)   // dotted horizontal graticule
    {
        if((sY >= sOy) && (sY < AWTO_SC_H))
        {
            for(sX = sOx - (sOx % AWTO_SC_DOT); sX < sOx + AWTO_SC_TILE_W; sX += AWTO_SC_DOT)
            {
                osd_pixel(&g_scCv, sX - sOx, sY - sOy, 1);
            }
        }
    }
    for(sX = sOx - (sOx % AWTO_SC_GRID_STEP_X); sX < sOx + AWTO_SC_TILE_W; sX += AWTO_SC_GRID_STEP_X)  // dotted vertical graticule
    {
        if(sX >= sOx)
        {
            for(sY = sOy - (sOy % AWTO_SC_DOT); sY < sOy + AWTO_SC_BAND_H; sY += AWTO_SC_DOT)
            {
                osd_pixel(&g_scCv, sX - sOx, sY - sOy, 1);
            }
        }
    }
    for(sX = 0; sX < AWTO_SC_TILE_W; sX++)                              // frame: top and bottom edges of this column
    {
        if(ucBand == 0)
        {
            osd_pixel(&g_scCv, sX, 0, 1);
        }
        if(ucBand == (AWTO_SC_BANDS - 1))
        {
            osd_pixel(&g_scCv, sX, AWTO_SC_BAND_H - 1, 1);
        }
    }
    for(sY = 0; sY < AWTO_SC_BAND_H; sY++)                              // left / right edges
    {
        if(ucCol == 0)
        {
            osd_pixel(&g_scCv, 0, sY, 1);
        }
        if(ucCol == (AWTO_SC_COLS - 1))
        {
            osd_pixel(&g_scCv, AWTO_SC_TILE_W - 1, sY, 1);
        }
    }
    sPrev = ScY(sOx - ((sOx > 0) ? 1 : 0), s_ucPhase);                  // the trace: one osd_line per px step; the loop runs one px past the column so the half of a
    for(sX = sOx + ((sOx > 0) ? 0 : 1); sX <= sOx + AWTO_SC_TILE_W; sX++)   // steep segment that lands at x = ox + 12 is drawn here too (the next pass clips its own half)
    {
        sCur = ScY(sX, s_ucPhase);
        osd_line(&g_scCv, sX - 1 - sOx, sPrev - sOy, sX - sOx, sCur - sOy, 1);
        sPrev = sCur;
    }
    s_usCell0 = (WORD)ucBand * AWTO_SC_BAND_ROWS * AWTO_SC_COLS + ucCol;
    for(ucT = 0; ucT < AWTO_SC_BAND_ROWS; ucT++)                        // every tile of the band, changed or not (the canvas is reused)
    {
        ScUpload(ucT);
    }
}

BYTE AwtoScopeSaver(BYTE ucCmd)                                         // cmd 2 draws one column (2 bands) and returns 1 when it completed a frame: the saver calls it once per main pass
{
    WORD usI;
    BYTE ucB;

    if(ucCmd == 0)
    {
        osd_tc_close();
        ScalerOsdScaleUpOnOff(_DISABLE);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SC_ARG_OFF, 0);
        return 1;
    }
    if(ucCmd == 2)                                                      // next column
    {
        if(s_ucCol == 0)
        {
            s_ucPhase += AWTO_SC_PH_STEP;
        }
        AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
        for(ucB = 0; ucB < AWTO_SC_BANDS; ucB++)
        {
            ScPass(s_ucCol, ucB);
        }
        s_ucCol++;
        if(s_ucCol < AWTO_SC_COLS)
        {
            return 0;
        }
        s_ucCol = 0;
        if(s_ucShown == 0)                                              // the first frame was drawn hidden: show the OSD now
        {
            s_ucShown = 1;
            osd_tc_show(1);
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SC_ARG_ON, 0);
        }
        else
        {
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_SC_ARG_FRAME, s_ucPhase);
        }
        return 1;
    }
    osd_tc_close();
    g_ucAwtoOsdRot = AwtoOsdRot180();
    AwtoOsdTestReset();
    ScalerOsdGlobalDoubleBuffer(_DISABLE);
    ScalerOsdCircuitActivated(_ENABLE);
    ScalerOsdVerticalStartSelect(_OSD_VSYNC_SELECT_DVS);
    ScalerOsdSetColorPalette(AWTO_SC_ZERO, AWTO_SC_ZERO, AWTO_SC_ZERO, AWTO_SC_ZERO);
    ScalerOsdSetColorPalette(AWTO_SC_BG, AWTO_SC_BG_R, AWTO_SC_BG_G, AWTO_SC_BG_B);
    ScalerOsdSetColorPalette(AWTO_SC_FG, AWTO_SC_FG_R, AWTO_SC_FG_G, AWTO_SC_FG_B);
    ScalerOsd2FontFunction(_DISABLE);
    for(usI = 0; usI < AWTO_SC_ROWS; usI++)
    {
        ScWord(usI, AWTO_SC_ROW_B0, AWTO_SC_TILE_H - 1, AWTO_SC_COLS);
    }
    ScWord(AWTO_SC_ROWS, AWTO_SC_ZERO, AWTO_SC_ZERO, AWTO_SC_ZERO);
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_SC_FS_BASE, _OSD_WITHOUT_DB);   // one char command per cell, glyph id = cell index
    for(usI = 0; usI < AWTO_SC_CELLS; usI++)
    {
        ScalerOsdDataPort(AWTO_SC_CHAR_B0 | AWTO_SC_CHAR_W | (BYTE)((usI >> 8) << AWTO_SC_ID_HI_SHIFT));
        ScalerOsdDataPort((BYTE)(usI & AWTO_SC_ID_LO_MASK));
        ScalerOsdDataPort((BYTE)((AWTO_SC_FG << AWTO_SC_FG_SHIFT) | AWTO_SC_BG));
    }
    SET_OSD_MAPA_COL_MAX(AWTO_SC_COLS);
    ScalerOsdSramBaseAddressSet(_OSD_A, AWTO_SC_ZERO, AWTO_SC_FS_BASE, AWTO_SC_FONT_BASE);
    ScalerOsdFontWindowVericalAlignemnt(_ENABLE);
    ScalerOsdPositionOffset(_OSD_POSITION_OFFSET_GLOBAL, AWTO_SC_POS_OFFSET_H, AWTO_SC_POS_OFFSET_V);
    ScalerOsdPosition(_OSD_POSITION_GLOBAL_A, AWTO_SC_POS_H, AWTO_SC_POS_V);
    ScalerOsdReferenceDelay(_OSD_A, _OSD_FIRST_DELAY);
    ScalerOsdPosition(_OSD_POSITION_FONT_A, AWTO_SC_ZERO, AWTO_SC_ZERO);
    ScalerOsdScaleUpHorSize(AWTO_SC_POS_H * AWTO_SC_PX_PER_HD, AWTO_SC_W);       // the window is in display coordinates: it starts where the OSD starts
    ScalerOsdScaleUpVerSize(AWTO_SC_POS_V, AWTO_SC_H);
    ScalerOsdScaleUpVerFactor(AWTO_SC_SU_FACTOR);
    ScalerOsdScaleUpHorFactor(AWTO_SC_SU_FACTOR);
    ScalerOsdScaleUpBoundaryCodition(_OSD_SCALING_BOUNDARY_NEIGHTBOOR);
    ScalerOsdScaleUpOnOff(_ENABLE);
    osd_canvas_init(&g_scCv, 1, AWTO_SC_BAND_ROWS, g_aucScPix, sizeof(g_aucScPix), g_aucScDirty, sizeof(g_aucScDirty));
    s_ucPhase = 0;
    s_ucCol = 0;
    s_ucShown = 0;                                                      // the first frame is drawn column by column (cmd 2), then the OSD is shown
    return 0;
}
