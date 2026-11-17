#include <stdint.h>
#include "UserCommonInclude.h"
#include "../../tools/osd_lines/osd_lines.h"

// Scope screensaver 2 (docs/screensaver.md, Dan's bench-scope photo): red graticule with centre ticks and 100 / 90 / 10 / 0 % marks,
// green pulse trace with two dotted cursors on its 10 % and 90 % points, readouts on top (counter, delta t from the cursors) and
// scale labels at the bottom. 28 x 9 tiles of 12 x 18 (336 x 162 px), 2-bit glyphs: plane 0 (MSB) = trace layer, plane 1 (LSB) = graticule
// layer; pixel value 1 = red, 2 and 3 = green. 252 glyph ids (the 2-bit char command has 8 id bits). Canvas = the 1-tile-wide band of
// scope_saver.c (XDATA floor), 3 tiles high, redrawn per column and band; the graticule plane is uploaded once, the trace plane per frame.
//   AwtoScopeSaver2(1) draw   (2) next frame   (0) off
extern void osd_tc_show(BYTE ucOn);
extern void osd_tc_close(void);
extern __xdata uint8_t g_aucScPix[];
extern __xdata uint8_t g_aucScDirty[];
extern __xdata osd_canvas g_scCv;

#define AWTO_S2_COLS                            28
#define AWTO_S2_ROWS                            9
#define AWTO_S2_TW                              OSD_TILE_W
#define AWTO_S2_TH                              OSD_TILE_H
#define AWTO_S2_W                               (AWTO_S2_COLS * AWTO_S2_TW)         // 336
#define AWTO_S2_H                               (AWTO_S2_ROWS * AWTO_S2_TH)         // 162
#define AWTO_S2_BAND_ROWS                       3
#define AWTO_S2_BANDS                           (AWTO_S2_ROWS / AWTO_S2_BAND_ROWS)
#define AWTO_S2_BAND_H                          (AWTO_S2_BAND_ROWS * AWTO_S2_TH)
#define AWTO_S2_CELLS                           (AWTO_S2_COLS * AWTO_S2_ROWS)
#define AWTO_S2_FS_BASE                         (AWTO_S2_ROWS + 1)
#define AWTO_S2_FONT_BASE                       (AWTO_S2_FS_BASE + AWTO_S2_CELLS)
#define AWTO_S2_GLYPH_WORDS                     9                                   // per plane
#define AWTO_S2_PLANES                          2
#define AWTO_S2_WORD_BYTES                      3
#define AWTO_S2_PX_PER_HD                       4                                   // OSD horizontal position unit: 4 panel px
#define AWTO_S2_PLANE_TRACE                     0                                   // MSB plane first
#define AWTO_S2_PLANE_GRID                      1
#define AWTO_S2_ROW_B0                          0x80
#define AWTO_S2_ZERO                            0x00
#define AWTO_S2_PAL_BG                          1                                   // palette indexes (all < 8: the 2-bit char command carries 3 bits for c2 / c3)
#define AWTO_S2_PAL_RED                         2
#define AWTO_S2_PAL_GREEN                       3
#define AWTO_S2_BG_R                            20
#define AWTO_S2_BG_G                            24
#define AWTO_S2_BG_B                            20
#define AWTO_S2_RED_R                           200
#define AWTO_S2_RED_G                           40
#define AWTO_S2_RED_B                           40
#define AWTO_S2_GRN_R                           70
#define AWTO_S2_GRN_G                           235
#define AWTO_S2_GRN_B                           170
#define AWTO_S2_SU_FACTOR                       6                                   // ratio 64 / 6 = 10.67: 336 x 162 -> 3584 x 1728 of 3840 x 2160
#define AWTO_S2_POS_OFFSET_H                    0x3B
#define AWTO_S2_POS_OFFSET_V                    0x04
#define AWTO_S2_POS_H                           32                                  // hd units of 4 panel px: (3840 - 3584) / 2 / 4
#define AWTO_S2_POS_V                           216                                 // (2160 - 1728) / 2
#define AWTO_S2_DIV_X                           42                                  // 8 divisions across
#define AWTO_S2_DIV_Y                           27                                  // 6 divisions down
#define AWTO_S2_TICK_LEN                        3                                   // minor tick half length
#define AWTO_S2_TICK_X                          8                                   // minor tick spacing on the horizontal axis
#define AWTO_S2_TICK_Y                          5                                   // on the vertical axis
#define AWTO_S2_BASE_Y                          108                                 // 0 % level (4 divisions down)
#define AWTO_S2_AMP                             81                                  // 100 % = 3 divisions above the baseline
#define AWTO_S2_P10                             8                                   // 10 % / 90 % of the amplitude
#define AWTO_S2_P90                             73
#define AWTO_S2_NS_PER_DIV                      1                                   // time base label: 1 ns / div
#define AWTO_S2_PS_PER_DIV                      1000
#define AWTO_S2_PULSE_N                         64                                  // pulse shape table length
#define AWTO_S2_PULSE_PEAK                      255
#define AWTO_S2_SPREAD_MIN                      3                                   // px per table step (slowest edge) .. + range
#define AWTO_S2_SPREAD_RANGE                    4
#define AWTO_S2_X0_MIN                          70                                  // pulse start x range
#define AWTO_S2_X0_RANGE                        90
#define AWTO_S2_FRAME_SLOW                      3                                   // frames per px of pulse drift
#define AWTO_S2_THICK                           1                                   // trace drawn twice, 1 px apart
#define AWTO_S2_FONT_W                          5
#define AWTO_S2_FONT_H                          7
#define AWTO_S2_FONT_ADV                        6
#define AWTO_S2_COUNTER0                        1129500UL                           // counter readout start (Hz-ish, shown as xxxx.xxx kHz)
#define AWTO_S2_STAGE_GRID                      0
#define AWTO_S2_STAGE_FIRST                     1
#define AWTO_S2_STAGE_RUN                       2
#define AWTO_S2_ARG_ON                          0x7B
#define AWTO_S2_ARG_FRAME                       0x7C
#define AWTO_S2_ARG_OFF                         0x7D

// pulse shape: rise then a slower fall (255 = peak), 64 entries
#pragma place bank(12)                      // data and its reader share a bank (docs/banking: movc reads the running bank)
static __code uint8_t s_tPulse[AWTO_S2_PULSE_N] = {
    0, 0, 0, 1, 2, 3, 5, 8, 12, 18, 26, 36, 49, 65, 84, 106,
    130, 154, 176, 196, 213, 227, 238, 246, 251, 254, 255, 254, 251, 246, 239, 230,
    220, 209, 198, 186, 174, 162, 150, 139, 128, 118, 108, 99, 90, 82, 75, 68,
    62, 56, 50, 45, 40, 36, 32, 28, 25, 22, 19, 16, 13, 10, 7, 4};

// 5 x 7 font, one byte per column (bit 0 = top row)
#define AWTO_S2_GL_DELTA                        'D'
#pragma place bank(12)
static __code uint8_t s_tFont[][AWTO_S2_FONT_W + 1] = {
    {'0', 0x3E, 0x51, 0x49, 0x45, 0x3E}, {'1', 0x00, 0x42, 0x7F, 0x40, 0x00}, {'2', 0x42, 0x61, 0x51, 0x49, 0x46},
    {'3', 0x21, 0x41, 0x45, 0x4B, 0x31}, {'4', 0x18, 0x14, 0x12, 0x7F, 0x10}, {'5', 0x27, 0x45, 0x45, 0x45, 0x39},
    {'6', 0x3C, 0x4A, 0x49, 0x49, 0x30}, {'7', 0x01, 0x71, 0x09, 0x05, 0x03}, {'8', 0x36, 0x49, 0x49, 0x49, 0x36},
    {'9', 0x06, 0x49, 0x49, 0x29, 0x1E}, {'.', 0x00, 0x60, 0x60, 0x00, 0x00}, {'>', 0x00, 0x41, 0x22, 0x14, 0x08},
    {'k', 0x7F, 0x10, 0x28, 0x44, 0x00}, {'H', 0x7F, 0x08, 0x08, 0x08, 0x7F}, {'z', 0x44, 0x64, 0x54, 0x4C, 0x44},
    {'n', 0x7C, 0x08, 0x04, 0x04, 0x78}, {'s', 0x48, 0x54, 0x54, 0x54, 0x20}, {'m', 0x7C, 0x04, 0x18, 0x04, 0x78},
    {'V', 0x1F, 0x20, 0x40, 0x20, 0x1F}, {'t', 0x04, 0x3F, 0x44, 0x40, 0x20}, {AWTO_S2_GL_DELTA, 0x60, 0x58, 0x46, 0x58, 0x60}};
#define AWTO_S2_FONT_N                          21                                  // glyphs in s_tFont
typedef char s_tFontCountCheck[(sizeof(s_tFont) == AWTO_S2_FONT_N * (AWTO_S2_FONT_W + 1)) ? 1 : -1];

#pragma place bank(12)
static __code char s_cS100[] = "100";
#pragma place bank(12)
static __code char s_cS90[] = "90";
#pragma place bank(12)
static __code char s_cS10[] = "10";
#pragma place bank(12)
static __code char s_cS0[] = "0";
#pragma place bank(12)
static __code char s_cSFreq[] = "1129.500 kHz";
#pragma place bank(12)
static __code char s_cSVolt[] = ">200mV";
#pragma place bank(12)
static __code char s_cSTime[] = "1ns";

static __xdata WORD s_usFrame;
static __xdata BYTE s_ucCol;
static __xdata BYTE s_ucStage;
static __xdata WORD s_usX0;                                                         // pulse start x
static __xdata BYTE s_ucSpread;                                                     // px per table step
static __xdata WORD s_usX10;                                                        // cursor x positions (10 % / 90 % points of the rising edge)
static __xdata WORD s_usX90;
static __xdata WORD s_usCell0;
static __xdata BYTE s_ucPlane;
static __xdata char s_acNum[12];

static void S2Word(WORD usAddr, BYTE ucB0, BYTE ucB1, BYTE ucB2)
{
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usAddr, _OSD_WITHOUT_DB);
    ScalerOsdDataPort(ucB0);
    ScalerOsdDataPort(ucB1);
    ScalerOsdDataPort(ucB2);
}

static void S2Upload(BYTE ucTile)
{
    BYTE ucK;
    WORD usCell = s_usCell0 + (WORD)ucTile * AWTO_S2_COLS;
    const uint8_t *pucB = g_aucScPix + (WORD)ucTile * OSD_TILE_BYTES;

    if(g_ucAwtoOsdRot != 0)                                                                // turned 180 (docs/osd-rotation.md): the glyph slot of the mirrored cell, words in reverse order, bits reversed
    {
        usCell = AwtoOsdRotCell(usCell, AWTO_S2_CELLS);
    }
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_S2_FONT_BASE + (WORD)usCell * (AWTO_S2_PLANES * AWTO_S2_GLYPH_WORDS) + (WORD)s_ucPlane * AWTO_S2_GLYPH_WORDS, _OSD_WITHOUT_DB);
    for(ucK = 0; ucK < AWTO_S2_GLYPH_WORDS; ucK++)                                  // canonical c0 c1 c2 -> stored B0 B1 B2 = c2 c1 c0
    {
        if(g_ucAwtoOsdRot != 0)
        {
            WORD usW = (WORD)(AWTO_S2_GLYPH_WORDS - 1 - ucK) * AWTO_S2_WORD_BYTES;

            ScalerOsdDataPort(AwtoOsdRevByte(pucB[usW]));
            ScalerOsdDataPort(AwtoOsdRevByte(pucB[usW + 1]));
            ScalerOsdDataPort(AwtoOsdRevByte(pucB[usW + 2]));
        }
        else
        {
            ScalerOsdDataPort(pucB[AWTO_S2_WORD_BYTES * ucK + 2]);
            ScalerOsdDataPort(pucB[AWTO_S2_WORD_BYTES * ucK + 1]);
            ScalerOsdDataPort(pucB[AWTO_S2_WORD_BYTES * ucK]);
        }
    }
}

static __xdata int16_t s_sOx;                                                       // origin of the pass being drawn
static __xdata int16_t s_sOy;

static void S2Px(int16_t sX, int16_t sY)                                            // absolute screen px -> canvas (osd_pixel clips)
{
    osd_pixel(&g_scCv, sX - s_sOx, sY - s_sOy, 1);
}

#pragma place bank(12)
static void S2Char(char cC, int16_t sX, int16_t sY, BYTE ucScale)
{
    BYTE ucI;
    BYTE ucCol;
    BYTE ucRow;
    BYTE ucBits;
    BYTE ucDx;
    BYTE ucDy;

    AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
    for(ucI = 0; ucI < AWTO_S2_FONT_N; ucI++)
    {
        if(s_tFont[ucI][0] == (BYTE)cC)
        {
            break;
        }
    }
    if(ucI == AWTO_S2_FONT_N)
    {
        return;
    }
    if(((int16_t)(sX + AWTO_S2_FONT_W * ucScale) <= s_sOx) || (sX >= s_sOx + AWTO_S2_TW) ||
       ((int16_t)(sY + AWTO_S2_FONT_H * ucScale) <= s_sOy) || (sY >= s_sOy + AWTO_S2_BAND_H))
    {
        return;                                                                     // outside this pass
    }
    for(ucCol = 0; ucCol < AWTO_S2_FONT_W; ucCol++)
    {
        ucBits = s_tFont[ucI][1 + ucCol];
        for(ucRow = 0; ucRow < AWTO_S2_FONT_H; ucRow++)
        {
            if((ucBits & (1 << ucRow)) != 0)
            {
                for(ucDy = 0; ucDy < ucScale; ucDy++)
                {
                    for(ucDx = 0; ucDx < ucScale; ucDx++)
                    {
                        S2Px(sX + (int16_t)ucCol * ucScale + ucDx, sY + (int16_t)ucRow * ucScale + ucDy);
                    }
                }
            }
        }
    }
}

#pragma place bank(12)
static void S2Text(const char *pcS, int16_t sX, int16_t sY, BYTE ucScale)
{
    while(*pcS != 0)
    {
        S2Char(*pcS, sX, sY, ucScale);
        sX += (int16_t)AWTO_S2_FONT_ADV * ucScale;
        pcS++;
    }
}

static BYTE S2Uint(unsigned long ulV, BYTE ucDigits, BYTE ucPos)                    // zero padded decimal into s_acNum from ucPos
{
    BYTE ucK;

    for(ucK = ucDigits; ucK > 0; ucK--)
    {
        s_acNum[ucPos + ucK - 1] = (char)('0' + (ulV % 10));
        ulV /= 10;
    }
    return ucPos + ucDigits;
}

#pragma place bank(12)
static BYTE S2Pulse(WORD usX)                                                       // 0..255 pulse height at screen x
{
    WORD usI;

    if(usX < s_usX0)
    {
        return 0;
    }
    usI = (usX - s_usX0) / s_ucSpread;
    return (usI < AWTO_S2_PULSE_N) ? s_tPulse[usI] : 0;
}

static int16_t S2Y(WORD usX)
{
    return AWTO_S2_BASE_Y - (int16_t)(((WORD)S2Pulse(usX) * AWTO_S2_AMP) / AWTO_S2_PULSE_PEAK);
}

static void S2Grid(BYTE ucCol, BYTE ucBand)                                         // graticule layer of one pass
{
    int16_t sX;
    int16_t sY;

    for(sX = s_sOx; sX < s_sOx + AWTO_S2_TW; sX++)
    {
        if(((sX % AWTO_S2_DIV_X) == 0) || (sX == AWTO_S2_W - 1))
        {
            osd_line(&g_scCv, sX - s_sOx, 0, sX - s_sOx, AWTO_S2_BAND_H - 1, 1);    // vertical division line
        }
    }
    for(sY = s_sOy; sY < s_sOy + AWTO_S2_BAND_H; sY++)
    {
        if(((sY % AWTO_S2_DIV_Y) == 0) || (sY == AWTO_S2_H - 1))
        {
            osd_line(&g_scCv, 0, sY - s_sOy, AWTO_S2_TW - 1, sY - s_sOy, 1);        // horizontal division line
        }
    }
    for(sX = s_sOx; sX < s_sOx + AWTO_S2_TW; sX++)                                  // minor ticks on the centre horizontal axis (y = 81)
    {
        if((sX % AWTO_S2_TICK_X) == 0)
        {
            for(sY = AWTO_S2_H / 2 - AWTO_S2_TICK_LEN; sY <= AWTO_S2_H / 2 + AWTO_S2_TICK_LEN; sY++)
            {
                S2Px(sX, sY);
            }
        }
    }
    for(sY = s_sOy; sY < s_sOy + AWTO_S2_BAND_H; sY++)                              // and on the centre vertical axis (x = 168)
    {
        if((sY % AWTO_S2_TICK_Y) == 0)
        {
            for(sX = AWTO_S2_W / 2 - AWTO_S2_TICK_LEN; sX <= AWTO_S2_W / 2 + AWTO_S2_TICK_LEN; sX++)
            {
                S2Px(sX, sY);
            }
        }
    }
    S2Text(s_cS100, 2, AWTO_S2_BASE_Y - AWTO_S2_AMP - 3, 1);                          // levels of the pulse, left edge
    S2Text(s_cS90, 2, AWTO_S2_BASE_Y - AWTO_S2_P90 - 3, 1);
    S2Text(s_cS10, 2, AWTO_S2_BASE_Y - AWTO_S2_P10 - 3, 1);
    S2Text(s_cS0, 2, AWTO_S2_BASE_Y - 3, 1);
    (void)ucCol;
    (void)ucBand;
}

static void S2Trace(void)                                                           // trace layer of one pass
{
    int16_t sX;
    int16_t sY;
    int16_t sPrev;
    int16_t sCur;
    WORD usPs;

    sPrev = S2Y((WORD)((s_sOx > 0) ? s_sOx - 1 : 0));
    for(sX = s_sOx + ((s_sOx > 0) ? 0 : 1); sX <= s_sOx + AWTO_S2_TW; sX++)         // one px past the column (the next pass clips its half)
    {
        sCur = S2Y((WORD)sX);
        osd_line(&g_scCv, sX - 1 - s_sOx, sPrev - s_sOy, sX - s_sOx, sCur - s_sOy, 1);
        osd_line(&g_scCv, sX - 1 - s_sOx, sPrev - s_sOy + AWTO_S2_THICK, sX - s_sOx, sCur - s_sOy + AWTO_S2_THICK, 1);
        sPrev = sCur;
    }
    for(sY = s_sOy; sY < s_sOy + AWTO_S2_BAND_H; sY += 2)                           // dotted cursors
    {
        S2Px(s_usX10, sY);
        S2Px(s_usX90, sY);
    }
    usPs = (WORD)(((unsigned long)(s_usX90 - s_usX10) * AWTO_S2_PS_PER_DIV) / AWTO_S2_DIV_X);   // delta t in ps from the cursors
    S2Text(s_cSFreq, 6, 4, 1);                                                // counter readout: placeholder digits, replaced per frame below
    s_acNum[0] = AWTO_S2_GL_DELTA;
    s_acNum[1] = 't';
    s_acNum[2] = 0;
    S2Text(s_acNum, 196, 4, 1);
    S2Uint(usPs / 1000, 1, 0);
    s_acNum[1] = '.';
    S2Uint(usPs % 1000 / 10, 2, 2);
    s_acNum[4] = ' ';
    s_acNum[5] = 'n';
    s_acNum[6] = 's';
    s_acNum[7] = 0;
    S2Text(s_acNum, 214, 14, 2);
    S2Text(s_cSVolt, 6, 150, 1);
    S2Text(s_cSTime, 170, 150, 1);
}

static void S2Pass(BYTE ucCol, BYTE ucBand, BYTE ucPlane)
{
    BYTE ucT;

    AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;               // a text-heavy pass is long: kick per pass
    s_sOx = (int16_t)ucCol * AWTO_S2_TW;
    s_sOy = (int16_t)ucBand * AWTO_S2_BAND_H;
    osd_clear(&g_scCv);
    osd_mark_all_dirty(&g_scCv);
    if(ucPlane == AWTO_S2_PLANE_GRID)
    {
        S2Grid(ucCol, ucBand);
    }
    else
    {
        S2Trace();
    }
    s_usCell0 = (WORD)ucBand * AWTO_S2_BAND_ROWS * AWTO_S2_COLS + ucCol;
    s_ucPlane = ucPlane;
    for(ucT = 0; ucT < AWTO_S2_BAND_ROWS; ucT++)
    {
        S2Upload(ucT);
    }
}

static void S2Params(void)                                                          // pulse position / edge speed of this frame, cursors on its 10 % / 90 % points
{
    WORD usX;

    s_usX0 = AWTO_S2_X0_MIN + (s_usFrame / AWTO_S2_FRAME_SLOW) % AWTO_S2_X0_RANGE;
    s_ucSpread = AWTO_S2_SPREAD_MIN + (BYTE)((s_usFrame / (AWTO_S2_FRAME_SLOW * AWTO_S2_X0_RANGE)) % AWTO_S2_SPREAD_RANGE);
    s_usX10 = s_usX0;
    s_usX90 = s_usX0;
    for(usX = s_usX0; usX < AWTO_S2_W; usX++)
    {
        if((WORD)((WORD)S2Pulse(usX) * AWTO_S2_AMP / AWTO_S2_PULSE_PEAK) >= AWTO_S2_P10)
        {
            s_usX10 = usX;
            break;
        }
    }
    for(usX = s_usX10; usX < AWTO_S2_W; usX++)
    {
        if((WORD)((WORD)S2Pulse(usX) * AWTO_S2_AMP / AWTO_S2_PULSE_PEAK) >= AWTO_S2_P90)
        {
            s_usX90 = usX;
            break;
        }
    }
}

BYTE AwtoScopeSaver2(BYTE ucCmd)                                        // cmd 2 draws one column (3 bands) of the current plane, returns 1 when a trace frame is complete
{
    WORD usI;
    BYTE ucB;

    if(ucCmd == 0)
    {
        osd_tc_close();
        ScalerOsdScaleUpOnOff(_DISABLE);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_S2_ARG_OFF, 0);
        return 1;
    }
    if(ucCmd == 2)
    {
        if((s_ucStage != AWTO_S2_STAGE_GRID) && (s_ucCol == 0))
        {
            s_usFrame++;
            S2Params();
        }
        for(ucB = 0; ucB < AWTO_S2_BANDS; ucB++)
        {
            S2Pass(s_ucCol, ucB, (s_ucStage == AWTO_S2_STAGE_GRID) ? AWTO_S2_PLANE_GRID : AWTO_S2_PLANE_TRACE);
        }
        s_ucCol++;
        if(s_ucCol < AWTO_S2_COLS)
        {
            return 0;
        }
        s_ucCol = 0;
        if(s_ucStage == AWTO_S2_STAGE_GRID)                             // graticule plane done (once): the first trace frame is drawn hidden
        {
            s_ucStage = AWTO_S2_STAGE_FIRST;
            return 0;
        }
        if(s_ucStage == AWTO_S2_STAGE_FIRST)
        {
            s_ucStage = AWTO_S2_STAGE_RUN;
            osd_tc_show(1);
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_S2_ARG_ON, 0);
        }
        else
        {
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_S2_ARG_FRAME, (BYTE)s_usFrame);
        }
        return 1;
    }
    osd_tc_close();
    g_ucAwtoOsdRot = AwtoOsdRot180();
    AwtoOsdTestReset();
    ScalerOsdGlobalDoubleBuffer(_DISABLE);
    ScalerOsdCircuitActivated(_ENABLE);
    ScalerOsdVerticalStartSelect(_OSD_VSYNC_SELECT_DVS);
    ScalerOsdSetColorPalette(AWTO_S2_ZERO, AWTO_S2_ZERO, AWTO_S2_ZERO, AWTO_S2_ZERO);
    ScalerOsdSetColorPalette(AWTO_S2_PAL_BG, AWTO_S2_BG_R, AWTO_S2_BG_G, AWTO_S2_BG_B);
    ScalerOsdSetColorPalette(AWTO_S2_PAL_RED, AWTO_S2_RED_R, AWTO_S2_RED_G, AWTO_S2_RED_B);
    ScalerOsdSetColorPalette(AWTO_S2_PAL_GREEN, AWTO_S2_GRN_R, AWTO_S2_GRN_G, AWTO_S2_GRN_B);
    ScalerOsd2FontFunction(_DISABLE);
    for(usI = 0; usI < AWTO_S2_ROWS; usI++)
    {
        S2Word(usI, AWTO_S2_ROW_B0, AWTO_S2_TH - 1, AWTO_S2_COLS);
    }
    S2Word(AWTO_S2_ROWS, AWTO_S2_ZERO, AWTO_S2_ZERO, AWTO_S2_ZERO);
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_S2_FS_BASE, _OSD_WITHOUT_DB);    // 2-bit char per cell, glyph id = cell index; value 0 bg, 1 red, 2 / 3 green
    for(usI = 0; usI < AWTO_S2_CELLS; usI++)
    {
        ScalerOsdDataPort((BYTE)(AWTO_S2_ROW_B0 | (((AWTO_S2_PAL_BG >> 3) & 1) << 5) | (((AWTO_S2_PAL_RED >> 3) & 1) << 4) | ((AWTO_S2_PAL_GREEN & 7) << 1) | ((AWTO_S2_PAL_BG >> 2) & 1)));
        ScalerOsdDataPort((BYTE)usI);
        ScalerOsdDataPort((BYTE)(((AWTO_S2_PAL_BG & 3) << 6) | ((AWTO_S2_PAL_GREEN & 7) << 3) | (AWTO_S2_PAL_RED & 7)));
    }
    SET_OSD_MAPA_COL_MAX(AWTO_S2_COLS);
    ScalerOsdSramBaseAddressSet(_OSD_A, AWTO_S2_ZERO, AWTO_S2_FS_BASE, AWTO_S2_FONT_BASE);
    ScalerOsd2BitFontOffset(AWTO_S2_ZERO);
    ScalerOsdFontWindowVericalAlignemnt(_ENABLE);
    ScalerOsdPositionOffset(_OSD_POSITION_OFFSET_GLOBAL, AWTO_S2_POS_OFFSET_H, AWTO_S2_POS_OFFSET_V);
    ScalerOsdPosition(_OSD_POSITION_GLOBAL_A, AWTO_S2_POS_H, AWTO_S2_POS_V);
    ScalerOsdReferenceDelay(_OSD_A, _OSD_FIRST_DELAY);
    ScalerOsdPosition(_OSD_POSITION_FONT_A, AWTO_S2_ZERO, AWTO_S2_ZERO);
    ScalerOsdScaleUpHorSize(AWTO_S2_POS_H * AWTO_S2_PX_PER_HD, AWTO_S2_W);          // the window is in display coordinates: it starts where the OSD starts
    ScalerOsdScaleUpVerSize(AWTO_S2_POS_V, AWTO_S2_H);
    ScalerOsdScaleUpVerFactor(AWTO_S2_SU_FACTOR);
    ScalerOsdScaleUpHorFactor(AWTO_S2_SU_FACTOR);
    ScalerOsdScaleUpBoundaryCodition(_OSD_SCALING_BOUNDARY_NEIGHTBOOR);
    ScalerOsdScaleUpOnOff(_ENABLE);
    osd_canvas_init(&g_scCv, 1, AWTO_S2_BAND_ROWS, g_aucScPix, AWTO_S2_BAND_ROWS * OSD_TILE_BYTES, g_aucScDirty, OSD_DIRTY_BYTES(1, AWTO_S2_BAND_ROWS));
    s_usFrame = 0;
    s_ucCol = 0;
    s_ucStage = AWTO_S2_STAGE_GRID;                                     // drawn column by column (cmd 2): graticule plane, first trace frame, then shown
    return 0;
}
