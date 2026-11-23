#include <stdint.h>
#include "UserCommonInclude.h"
#if(_AWTO_SAVER_SCOPE2 == _ON)                                        // saver not in the image when _OFF (RL6449_Project.h)
#include "../../tools/osd_lines/osd_lines.h"                                // tile geometry only

// Scope screensaver 2 (docs/screensaver.md): red graticule with minor ticks, green pulse trace, two dotted cursors on its 10 % / 90 % points,
// level marks, readouts. The whole panel is one raster (scope2_data.inc: 480 x 270 = 40 x 15 tiles of 12 x 18, 2-bit glyphs) scaled up by the OSD engine.
// Static tiles (graticule, labels) are generated (scripts/gen_scope2.py) and uploaded once; per frame only the tiles the trace, the cursors
// and the delta t number touch are drawn, one column per call, into slots of a ring above the static ids.
//   AwtoScopeSaver2(1) draw   (2) next column (returns 1 at the end of a frame)   (0) off
extern __xdata uint8_t g_aucScPix[];                                                // tile buffer shared with Asteroids, saver_canvas.c (one saver at a time): green plane, red plane

#include "scope2_data.inc"

#define AWTO_S2_TW                              OSD_TILE_W
#define AWTO_S2_TH                              OSD_TILE_H
#define AWTO_S2_CELLS                           (AWTO_S2_COLS * AWTO_S2_ROWS)
#define AWTO_S2_FS_BASE                         (AWTO_S2_ROWS + 1)
#define AWTO_S2_FONT_BASE                       (AWTO_S2_FS_BASE + AWTO_S2_CELLS)
#define AWTO_S2_GLYPH_WORDS                     9                                   // per plane
#define AWTO_S2_PLANES                          2
#define AWTO_S2_GLYPH_STRIDE                    (AWTO_S2_PLANES * AWTO_S2_GLYPH_WORDS)
#define AWTO_S2_PLANE_BYTES                     OSD_TILE_BYTES
#define AWTO_S2_BASE_BYTES                      (AWTO_S2_PLANES * AWTO_S2_PLANE_BYTES)
#define AWTO_S2_ID_LAST                         255
#define AWTO_S2_NUM_W                           (AWTO_S2_NUM_COL1 - AWTO_S2_NUM_COL0 + 1)
#define AWTO_S2_NUM_N                           (AWTO_S2_NUM_W * (AWTO_S2_NUM_ROW1 - AWTO_S2_NUM_ROW0 + 1))
#define AWTO_S2_RING0                           (AWTO_S2_STATIC_N + AWTO_S2_NUM_N)    // first dynamic slot
#define AWTO_S2_WDT_EVERY                       64                                  // cells between watchdog kicks in the map loop (power of 2)
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
#define AWTO_S2_SCALE_64                        64                                  // scale-up factor unit: ratio = 64 / factor
#define AWTO_S2_SCALED_W                        (AWTO_S2_SCALE_64 * (long)AWTO_S2_W)  // long: 64 x 960 overflows a 16-bit int
#define AWTO_S2_SCALED_H                        (AWTO_S2_SCALE_64 * (long)AWTO_S2_H)
#define AWTO_S2_SU_FACTOR                       ((BYTE)(AWTO_S2_SCALED_W / _PANEL_DH_WIDTH))
#define AWTO_S2_POS_H                           ((BYTE)((_PANEL_DH_WIDTH - AWTO_S2_SCALED_W / AWTO_S2_SU_FACTOR) / 2 / AWTO_OSD_PX_PER_HD))
#define AWTO_S2_POS_V                           ((BYTE)((_PANEL_DV_HEIGHT - AWTO_S2_SCALED_H / AWTO_S2_SU_FACTOR) / 2))
typedef char s_tS2PanelCheck[((AWTO_S2_SU_FACTOR * (long)_PANEL_DH_WIDTH == AWTO_S2_SCALED_W) && (AWTO_S2_SU_FACTOR * (long)_PANEL_DV_HEIGHT == AWTO_S2_SCALED_H)) ? 1 : -1];   // the raster must fill the panel exactly
#define AWTO_S2_CURSOR_STEP                     2                                   // cursor dots: every 2nd row
#define AWTO_S2_FONT_W                          5
#define AWTO_S2_FONT_H                          7
#define AWTO_S2_FONT_ADV                        6
#define AWTO_S2_TRACE_PTS                       14                                  // columns x = ox - 1 .. ox + 12 of a tile column
#define AWTO_S2_CACHE_N                         8                                   // cursor-only tiles per column pass: distinct static bases
#define AWTO_S2_BIT_SHIFT                       3                                   // bits per byte = 1 << 3
#define AWTO_S2_BIT_MASK                        7
#define AWTO_S2_WORD_BITS                       24
#define AWTO_S2_WORD_BYTES                      3
#define AWTO_S2_PASS_MS                         8                                   // time budget of one call (+ at most one tile, ~3 ms): the main loop (DDC/CI, keys) runs between calls
#define AWTO_S2_FRAME_MS                        40                                  // frame schedule: 25 fps cap (Dan 2026-11-19); a frame that needs longer runs back to back
#define AWTO_S2_HALF_MS                         0x8000                              // WORD ms difference below this = the time has passed
#define AWTO_S2_NUM_CHARS                       8
#define AWTO_S2_ARG_ON                          0x7B
#define AWTO_S2_ARG_FRAME                       0x7C
#define AWTO_S2_ARG_OFF                         0x7D

__xdata WORD g_usAwtoS2Frame;                                                       // frame counter (scripts/scope2_sim.py)
static __xdata BYTE s_ucCol;
static __xdata BYTE s_ucShown;
static __xdata WORD s_usFrameAt;                                                    // scheduled start of the next frame (AwtoMs low word); advances by the period
static __xdata BYTE s_ucNext;                                                       // next dynamic slot id (ring STATIC_N .. 255)
static __xdata BYTE s_ucSpread;                                                     // px per pulse table step
static __xdata WORD s_usDrift;                                                      // pulse start offset
static __xdata WORD s_usX0;
static __xdata WORD s_usX10;                                                        // cursor x positions (10 % / 90 % points of the rising edge)
static __xdata WORD s_usX90;
static __xdata BYTE s_ucCur10;                                                      // their tile columns
static __xdata BYTE s_ucCur90;
static __xdata BYTE s_ucR0;                                                         // trace rows of the column being drawn
static __xdata BYTE s_ucR1;
static __xdata int16_t s_sOy;                                                       // tile origin y of the tile being drawn
static __xdata int16_t s_asYs[AWTO_S2_TRACE_PTS];                                   // trace y at x = ox - 1 + j
static __xdata AWTO_S2_MASK_T s_aMask[AWTO_S2_COLS];                                // rows drawn dynamically per column, last frame
static __xdata BYTE s_aucCacheBase[AWTO_S2_CACHE_N];
static __xdata BYTE s_aucCacheSlot[AWTO_S2_CACHE_N];
static __xdata BYTE s_ucCacheN;
static __xdata AWTO_S2_MASK_T s_tNew;                                               // rows of the column in progress: to draw now / drawn last frame
static __xdata AWTO_S2_MASK_T s_tOld;
static __xdata BYTE s_ucRow;                                                        // next row of the column in progress
static __xdata BYTE s_ucFrameOn;                                                    // the frame's parameters are set
static __xdata BYTE s_ucInCol;                                                      // 1 = a column is part drawn
static __xdata BYTE s_ucNumLeft;                                                    // readout tiles still to redraw
static __xdata BYTE s_ucYsCol;                                                      // column s_asYs belongs to
static __xdata BYTE s_ucNumDirty;                                                   // readout tiles need a redraw
static __xdata char s_acNum[AWTO_S2_NUM_CHARS];

static void S2Run(BYTE ucX, BYTE ucLo, BYTE ucHi)                                   // vertical run (tile coords, both ends inside the tile) in the green plane
{
    BYTE ucY;
    BYTE ucQ;
    BYTE ucTmp;
    BYTE ucOffE;
    BYTE ucMaskE;
    BYTE ucOffO;
    BYTE ucMaskO;

    if(g_ucAwtoOsdRot != 0)                                                         // the tile is drawn turned 180 (docs/osd/rotation.md)
    {
        ucX = AWTO_S2_TW - 1 - ucX;
        ucTmp = AWTO_S2_TH - 1 - ucHi;
        ucHi = AWTO_S2_TH - 1 - ucLo;
        ucLo = ucTmp;
    }
    ucQ = AWTO_S2_WORD_BITS - 1 - ucX;                                              // pixel p of a word (two rows, row-major) = bit 23 - p of its 24 bits, bytes low first
    ucOffE = ucQ >> AWTO_S2_BIT_SHIFT;                                              // even row: p = x
    ucMaskE = (BYTE)(1 << (ucQ & AWTO_S2_BIT_MASK));
    ucQ = AWTO_S2_WORD_BITS - 1 - (AWTO_S2_TW + ucX);                               // odd row: p = 12 + x
    ucOffO = ucQ >> AWTO_S2_BIT_SHIFT;
    ucMaskO = (BYTE)(1 << (ucQ & AWTO_S2_BIT_MASK));
    for(ucY = ucLo; ucY <= ucHi; ucY++)
    {
        if(ucY & 1)
        {
            g_aucScPix[(ucY >> 1) * AWTO_S2_WORD_BYTES + ucOffO] |= ucMaskO;
        }
        else
        {
            g_aucScPix[(ucY >> 1) * AWTO_S2_WORD_BYTES + ucOffE] |= ucMaskE;
        }
    }
}

#pragma place group(scope2_12)                      // data and its reader share a bank (docs/banking: movc reads the running bank)
static BYTE S2CellId(WORD usCell)
{
    return s_tS2Cell[usCell];
}

#pragma place group(scope2_12)
static void S2BaseCopy(BYTE ucId)
{
    BYTE ucI;
    const __code uint8_t *pcS = s_tS2Base[ucId];

    for(ucI = 0; ucI < AWTO_S2_BASE_BYTES; ucI++)
    {
        g_aucScPix[ucI] = pcS[ucI];
    }
}

static void S2Base(BYTE ucId)                                                       // both planes of a static tile -> g_aucScPix (green, then red); Rotate 180: each plane turned in place
{
    S2BaseCopy(ucId);
    if(g_ucAwtoOsdRot != 0)
    {
        AwtoOsdTurn(g_aucScPix, AWTO_S2_PLANE_BYTES);
        AwtoOsdTurn(&g_aucScPix[AWTO_S2_PLANE_BYTES], AWTO_S2_PLANE_BYTES);
    }
}

#pragma place group(scope2_12)
static BYTE S2Pulse(WORD usX)                                                       // 0..255 pulse height at raster x, linear between table steps
{
    WORD usD;
    WORD usI;
    BYTE ucA;
    BYTE ucB;
    BYTE ucR;

    if(usX < s_usX0)
    {
        return 0;
    }
    usD = usX - s_usX0;
    usI = usD / s_ucSpread;
    if(usI >= AWTO_S2_PULSE_N)
    {
        return 0;
    }
    ucR = (BYTE)(usD - usI * s_ucSpread);
    ucA = s_tS2Pulse[usI];
    ucB = (usI + 1 < AWTO_S2_PULSE_N) ? s_tS2Pulse[usI + 1] : 0;
    return (BYTE)((int16_t)ucA + ((int16_t)ucB - (int16_t)ucA) * ucR / s_ucSpread);
}

#pragma place group(scope2_11)
static void S2Char(char cC, int16_t sX, int16_t sY, BYTE ucScale)                   // into the tile buffer, clipped to the tile
{
    BYTE ucI;
    BYTE ucCol;
    BYTE ucRow;
    BYTE ucBits;
    BYTE ucDx;
    BYTE ucStart;
    int16_t sXs;
    int16_t sLo;
    int16_t sHi;

    for(ucI = 0; ucI < AWTO_S2_FONT_N; ucI++)
    {
        if(s_tS2Font[ucI][0] == (BYTE)cC)
        {
            break;
        }
    }
    if((ucI == AWTO_S2_FONT_N) || ((int16_t)(sX + AWTO_S2_FONT_W * ucScale) <= 0) || (sX >= AWTO_S2_TW) ||
       ((int16_t)(sY + AWTO_S2_FONT_H * ucScale) <= 0) || (sY >= AWTO_S2_TH))
    {
        return;                                                                     // not a glyph of the number, or outside this tile
    }
    for(ucCol = 0; ucCol < AWTO_S2_FONT_W; ucCol++)
    {
        ucBits = s_tS2Font[ucI][1 + ucCol];
        ucStart = 0;
        for(ucRow = 0; ucRow <= AWTO_S2_FONT_H; ucRow++)                            // one run per stretch of set rows (the row after the last is clear)
        {
            if((ucRow < AWTO_S2_FONT_H) && ((ucBits >> ucRow) & 1))
            {
                if((ucRow == 0) || !((ucBits >> (ucRow - 1)) & 1))
                {
                    ucStart = ucRow;
                }
                continue;
            }
            if((ucRow == 0) || !((ucBits >> (ucRow - 1)) & 1))
            {
                continue;
            }
            sLo = sY + (int16_t)ucStart * ucScale;
            sHi = sY + (int16_t)ucRow * ucScale - 1;
            sLo = (sLo < 0) ? 0 : sLo;
            sHi = (sHi >= AWTO_S2_TH) ? AWTO_S2_TH - 1 : sHi;
            for(ucDx = 0; (sLo <= sHi) && (ucDx < ucScale); ucDx++)
            {
                sXs = sX + (int16_t)ucCol * ucScale + ucDx;
                if((sXs >= 0) && (sXs < AWTO_S2_TW))
                {
                    S2Run((BYTE)sXs, (BYTE)sLo, (BYTE)sHi);
                }
            }
        }
    }
}

#pragma place group(scope2_11)
static void S2Text(const __xdata char *pcS, int16_t sX, int16_t sY, BYTE ucScale)
{
    while(*pcS != 0)
    {
        S2Char(*pcS, sX, sY, ucScale);
        sX += (int16_t)AWTO_S2_FONT_ADV * ucScale;
        pcS++;
    }
}

#pragma place group(scope2_12)
static int16_t S2Y(WORD usX)
{
    return AWTO_S2_BASE_Y - (int16_t)(((WORD)S2Pulse(usX) * AWTO_S2_AMP) / AWTO_S2_PULSE_PEAK);
}

static void S2Uint(unsigned long ulV, BYTE ucDigits, BYTE ucPos)                    // zero padded decimal into s_acNum from ucPos
{
    BYTE ucK;

    for(ucK = ucDigits; ucK > 0; ucK--)
    {
        s_acNum[ucPos + ucK - 1] = (char)('0' + (ulV % 10));
        ulV /= 10;
    }
}

static void S2MapWord(WORD usCell, BYTE ucId)                                       // char command: glyph id, colours c0 bg, c1 green (plane A = low bit, docs/osd-hw-tests.md T9), c2 red, c3 green
{
    if(g_ucAwtoOsdRot != 0)                                                         // turned 180 (docs/osd/rotation.md): the mirrored cell
    {
        usCell = AwtoOsdRotCell(usCell, AWTO_S2_CELLS);
    }
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_S2_FS_BASE + usCell, _OSD_WITHOUT_DB);
    AWTO_OSD_PORT((BYTE)(AWTO_OSD_ROW_B0 | (((AWTO_S2_PAL_BG >> 3) & 1) << 5) | (((AWTO_S2_PAL_GREEN >> 3) & 1) << 4) | ((AWTO_S2_PAL_GREEN & 7) << 1) | ((AWTO_S2_PAL_BG >> 2) & 1)));
    AWTO_OSD_PORT(ucId);
    AWTO_OSD_PORT((BYTE)(((AWTO_S2_PAL_BG & 3) << 6) | ((AWTO_S2_PAL_RED & 7) << 3) | (AWTO_S2_PAL_GREEN & 7)));
}

static void S2Glyph(BYTE ucId)                                                      // g_aucScPix (green plane, red plane; data port order, already turned) -> glyph slot
{
    BYTE ucI;

    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_S2_FONT_BASE + (WORD)ucId * AWTO_S2_GLYPH_STRIDE, _OSD_WITHOUT_DB);
    for(ucI = 0; ucI < AWTO_S2_BASE_BYTES; ucI++)                                   // SDK call like every other saver: direct back-to-back port writes are the suspect of the unit photo 2026-11-18
    {
        AWTO_OSD_PORT(g_aucScPix[ucI]);
    }
}

static BYTE S2Alloc(void)
{
    BYTE ucId = s_ucNext;

    s_ucNext = (ucId == AWTO_S2_ID_LAST) ? AWTO_S2_RING0 : (BYTE)(ucId + 1);
    return ucId;
}

static void S2Trace(void)                                                           // the trace of the column into the tile (green plane): per pixel column the run from y(x - 1) to y(x), plus THICK
{
    __data BYTE ucX;
    __data int16_t sA;
    __data int16_t sB;
    __data int16_t sLo;
    __data int16_t sHi;

    for(ucX = 0; ucX < AWTO_S2_TW; ucX++)
    {
        sA = s_asYs[ucX] - s_sOy;
        sB = s_asYs[ucX + 1] - s_sOy;
        sLo = (sA < sB) ? sA : sB;
        sHi = ((sA > sB) ? sA : sB) + AWTO_S2_THICK;
        if((sHi < 0) || (sLo >= AWTO_S2_TH))
        {
            continue;
        }
        sLo = (sLo < 0) ? 0 : sLo;
        sHi = (sHi >= AWTO_S2_TH) ? AWTO_S2_TH - 1 : sHi;
        S2Run(ucX, (BYTE)sLo, (BYTE)sHi);
    }
}

static BYTE S2IsNum(BYTE ucCol, BYTE ucRow)
{
    return (BYTE)((ucCol >= AWTO_S2_NUM_COL0) && (ucCol <= AWTO_S2_NUM_COL1) && (ucRow >= AWTO_S2_NUM_ROW0) && (ucRow <= AWTO_S2_NUM_ROW1));
}

static BYTE S2Home(BYTE ucCol, BYTE ucRow, WORD usCell)                             // glyph id of a cell at rest: its readout slot, else its static tile
{
    if(S2IsNum(ucCol, ucRow))
    {
        return (BYTE)(AWTO_S2_STATIC_N + (ucRow - AWTO_S2_NUM_ROW0) * AWTO_S2_NUM_W + (ucCol - AWTO_S2_NUM_COL0));
    }
    return S2CellId(usCell);
}

static void S2Fill(BYTE ucCol, BYTE ucRow, BYTE ucBase, BYTE ucId)                  // draw one dynamic tile on its static base and upload it
{
    BYTE ucY;
    BYTE ucXo;

    S2Base(ucBase);
    s_sOy = (int16_t)ucRow * AWTO_S2_TH;
    if((ucRow >= s_ucR0) && (ucRow <= s_ucR1))
    {
        S2Trace();
    }
    if((ucCol == s_ucCur10) || (ucCol == s_ucCur90))                                // dotted cursor
    {
        ucXo = (BYTE)(((ucCol == s_ucCur10) ? s_usX10 : s_usX90) - (WORD)ucCol * AWTO_S2_TW);
        for(ucY = 0; ucY < AWTO_S2_TH; ucY += AWTO_S2_CURSOR_STEP)
        {
            S2Run(ucXo, ucY, ucY);
        }
    }
    if(S2IsNum(ucCol, ucRow))
    {
        S2Text(s_acNum, (int16_t)AWTO_S2_NUM_X - (int16_t)ucCol * AWTO_S2_TW, (int16_t)AWTO_S2_NUM_Y - s_sOy, AWTO_S2_TS_NUM);
    }
    S2Glyph(ucId);
}

static void S2NumDraw(void)                                                         // one readout tile (own slot), the next of s_ucNumLeft: redrawn when the number changes
{
    BYTE ucC10 = s_ucCur10;
    BYTE ucC90 = s_ucCur90;
    BYTE ucK = AWTO_S2_NUM_N - s_ucNumLeft;
    BYTE ucC = AWTO_S2_NUM_COL0 + ucK % AWTO_S2_NUM_W;
    BYTE ucR = AWTO_S2_NUM_ROW0 + ucK / AWTO_S2_NUM_W;

    s_ucNumLeft--;
    s_ucCur10 = AWTO_S2_COLS;                                                       // no cursor in these tiles (a cursor column composes its own)
    s_ucCur90 = AWTO_S2_COLS;
    s_ucR0 = AWTO_S2_ROWS;
    s_ucR1 = 0;
    S2Fill(ucC, ucR, S2CellId((WORD)ucR * AWTO_S2_COLS + ucC), S2Home(ucC, ucR, 0));
    s_ucCur10 = ucC10;
    s_ucCur90 = ucC90;
}

static void S2ColBegin(BYTE ucCol)                                                  // trace points and dynamic rows of a column; the rows follow in S2ColRows
{
    __data WORD usOx = (WORD)ucCol * AWTO_S2_TW;
    __data int16_t sMin;
    __data int16_t sMax;
    __data AWTO_S2_MASK_T tNew = 0;
    __data AWTO_S2_MASK_T tBit;
    __data BYTE ucJ;
    __data BYTE ucR;

    if((ucCol > 0) && (s_ucYsCol == ucCol - 1))                                     // the two points the previous column ended with
    {
        s_asYs[0] = s_asYs[AWTO_S2_TRACE_PTS - 2];
        s_asYs[1] = s_asYs[AWTO_S2_TRACE_PTS - 1];
        ucJ = 2;
    }
    else
    {
        s_asYs[0] = S2Y((usOx > 0) ? usOx - 1 : 0);
        ucJ = 1;
    }
    s_ucYsCol = ucCol;
    for(; ucJ < AWTO_S2_TRACE_PTS; ucJ++)
    {
        s_asYs[ucJ] = S2Y(usOx - 1 + ucJ);
    }
    sMin = s_asYs[0];
    sMax = sMin;
    for(ucJ = 1; ucJ < AWTO_S2_TRACE_PTS; ucJ++)
    {
        sMin = (s_asYs[ucJ] < sMin) ? s_asYs[ucJ] : sMin;
        sMax = (s_asYs[ucJ] > sMax) ? s_asYs[ucJ] : sMax;
    }
    s_ucR0 = (BYTE)(sMin / AWTO_S2_TH);
    s_ucR1 = (BYTE)((sMax + AWTO_S2_THICK) / AWTO_S2_TH);
    s_ucR1 = (s_ucR1 >= AWTO_S2_ROWS) ? AWTO_S2_ROWS - 1 : s_ucR1;
    for(ucR = s_ucR0, tBit = (AWTO_S2_MASK_T)1 << s_ucR0; ucR <= s_ucR1; ucR++, tBit <<= 1)
    {
        tNew |= tBit;
    }
    if((ucCol == s_ucCur10) || (ucCol == s_ucCur90))
    {
        tNew = ~(AWTO_S2_MASK_T)0;
    }
    s_ucCacheN = 0;
    s_tNew = tNew;
    s_tOld = s_aMask[ucCol];
    s_ucRow = 0;
}

static BYTE S2ColRows(BYTE ucCol, unsigned long ulStart)                           // rows from s_ucRow on until the time budget is used; 1 = column done
{
    __data BYTE ucR;
    __data BYTE ucK;
    __data BYTE ucBase;
    __data BYTE ucId;
    __data BYTE ucBusy;
    __data BYTE ucDrew;
    __data WORD usCell;
    __data AWTO_S2_MASK_T tBit;

    for(ucR = s_ucRow, tBit = (AWTO_S2_MASK_T)1 << ucR, usCell = (WORD)ucR * AWTO_S2_COLS + ucCol; ucR < AWTO_S2_ROWS; ucR++, tBit <<= 1, usCell += AWTO_S2_COLS)
    {
        ucDrew = 0;
        if(s_tNew & tBit)
        {
            ucBase = S2CellId(usCell);
            ucBusy = (BYTE)(((ucR >= s_ucR0) && (ucR <= s_ucR1)) || S2IsNum(ucCol, ucR));
            ucId = 0;
            if(!ucBusy)                                                             // cursor only: one slot per static base within the column
            {
                for(ucK = 0; ucK < s_ucCacheN; ucK++)
                {
                    if(s_aucCacheBase[ucK] == ucBase)
                    {
                        ucId = s_aucCacheSlot[ucK];
                        break;
                    }
                }
            }
            if(ucId == 0)                                                           // dynamic ids start at STATIC_N > 0
            {
                ucId = S2Alloc();
                S2Fill(ucCol, ucR, ucBase, ucId);
                ucDrew = 1;
                if(!ucBusy)
                {
                    s_aucCacheBase[s_ucCacheN] = ucBase;
                    s_aucCacheSlot[s_ucCacheN] = ucId;
                    s_ucCacheN++;
                }
            }
            S2MapWord(usCell, ucId);
        }
        else if(s_tOld & tBit)                                                      // drawn last frame, not now: back to the static tile
        {
            S2MapWord(usCell, S2Home(ucCol, ucR, usCell));
        }
        if((ucDrew != 0) && ((WORD)(AwtoMs() - ulStart) >= AWTO_S2_PASS_MS))
        {
            s_ucRow = ucR + 1;                                                      // band full: the next call goes on with the next row
            if(s_ucRow < AWTO_S2_ROWS)
            {
                return 0;
            }
            break;
        }
    }
    s_aMask[ucCol] = s_tNew;
    return 1;
}

static void S2Params(void)                                                          // pulse position / edge speed of this frame, cursors on its 10 % / 90 % points, delta t text
{
    unsigned long ulPs;

    s_usDrift += AWTO_S2_X0_STEP;
    if(s_usDrift >= AWTO_S2_X0_RANGE)
    {
        s_usDrift -= AWTO_S2_X0_RANGE;
        s_ucSpread++;
        if(s_ucSpread >= AWTO_S2_SPREAD_MIN + AWTO_S2_SPREAD_RANGE)
        {
            s_ucSpread = AWTO_S2_SPREAD_MIN;
        }
        s_ucNumDirty = 1;                                                           // the delta t number changed
    }
    s_usX0 = AWTO_S2_X0_MIN + s_usDrift;
    s_usX10 = s_usX0 + (WORD)AWTO_S2_I10 * s_ucSpread;
    s_usX90 = s_usX0 + (WORD)AWTO_S2_I90 * s_ucSpread;
    s_ucCur10 = (BYTE)(s_usX10 / AWTO_S2_TW);
    s_ucCur90 = (BYTE)(s_usX90 / AWTO_S2_TW);
    ulPs = ((unsigned long)(s_usX90 - s_usX10) * AWTO_S2_PS_PER_DIV) / AWTO_S2_DIV_X;   // delta t in ps from the cursors
    S2Uint(ulPs / 1000, 1, 0);
    s_acNum[1] = '.';
    S2Uint(ulPs % 1000 / 10, 2, 2);
    s_acNum[4] = ' ';
    s_acNum[5] = 'n';
    s_acNum[6] = 's';
    s_acNum[7] = 0;
    if(s_ucNumDirty != 0)
    {
        s_ucNumDirty = 0;
        s_ucNumLeft = AWTO_S2_NUM_N;                                                // drawn one tile per step before the columns go on
    }
}

BYTE AwtoScopeSaver2(BYTE ucCmd)
{
    WORD usI;
    BYTE ucI;
    unsigned long ulStart;

    if(ucCmd == 0)
    {
        AwtoOsdScreenOff();
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_S2_ARG_OFF, 0);
        return 1;
    }
    if(ucCmd == 2)
    {
        ulStart = AwtoMs();
        AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
        do                                                              // bands: up to the budget per call, then back to the main loop (DDC/CI, keys, watchdog)
        {
            if(s_ucFrameOn == 0)
            {
                if(s_ucShown != 0)                                              // fixed-rate frames (the hidden first one starts at once)
                {
                    if((WORD)((WORD)ulStart - s_usFrameAt) >= AWTO_S2_HALF_MS)
                    {
                        return 1;                                               // not due yet
                    }
                    s_usFrameAt += AWTO_S2_FRAME_MS;
                    if((WORD)((WORD)ulStart - s_usFrameAt) < AWTO_S2_HALF_MS)
                    {
                        s_usFrameAt = (WORD)ulStart + AWTO_S2_FRAME_MS;         // a frame or more behind: resync, no burst
                    }
                }
                s_ucFrameOn = 1;
                g_usAwtoS2Frame++;
                S2Params();
            }
            if(s_ucNumLeft != 0)
            {
                S2NumDraw();
                continue;
            }
            if(s_ucInCol == 0)
            {
                S2ColBegin(s_ucCol);
                s_ucInCol = 1;
            }
            if(S2ColRows(s_ucCol, ulStart) != 0)
            {
                s_ucInCol = 0;
                s_ucCol++;
            }
        }
        while((s_ucCol < AWTO_S2_COLS) && ((WORD)(AwtoMs() - ulStart) < AWTO_S2_PASS_MS));
        if(s_ucCol < AWTO_S2_COLS)
        {
            return 0;
        }
        s_ucCol = 0;
        s_ucFrameOn = 0;
        if(s_ucShown == 0)                                              // the first frame was drawn hidden
        {
            s_ucShown = 1;
            s_usFrameAt = (WORD)ulStart + AWTO_S2_FRAME_MS;
            osd_tc_show(1);
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_S2_ARG_ON, 0);
        }
        else
        {
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_S2_ARG_FRAME, (BYTE)g_usAwtoS2Frame);
        }
        return 1;
    }
    AwtoOsdScreenBegin();
    ScalerOsdSetColorPalette(AWTO_OSD_ZERO, AWTO_OSD_ZERO, AWTO_OSD_ZERO, AWTO_OSD_ZERO);
    ScalerOsdSetColorPalette(AWTO_S2_PAL_BG, AWTO_S2_BG_R, AWTO_S2_BG_G, AWTO_S2_BG_B);
    ScalerOsdSetColorPalette(AWTO_S2_PAL_RED, AWTO_S2_RED_R, AWTO_S2_RED_G, AWTO_S2_RED_B);
    ScalerOsdSetColorPalette(AWTO_S2_PAL_GREEN, AWTO_S2_GRN_R, AWTO_S2_GRN_G, AWTO_S2_GRN_B);
    ScalerOsd2FontFunction(_DISABLE);
    AwtoOsdRowCmds(AWTO_S2_ROWS, AWTO_S2_TH, AWTO_S2_COLS);
    for(ucI = 0; ucI < AWTO_S2_STATIC_N; ucI++)                         // static tiles: both planes
    {
        AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
        S2Base(ucI);
        S2Glyph(ucI);
    }
    for(usI = 0; usI < AWTO_S2_CELLS; usI++)                            // the map: every cell its static tile
    {
        if((usI & (AWTO_S2_WDT_EVERY - 1)) == 0)
        {
            AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
        }
        S2MapWord(usI, S2Home((BYTE)(usI % AWTO_S2_COLS), (BYTE)(usI / AWTO_S2_COLS), usI));
    }
    SET_OSD_MAPA_COL_MAX(AWTO_S2_COLS);
    ScalerOsdSramBaseAddressSet(_OSD_A, AWTO_OSD_ZERO, AWTO_S2_FS_BASE, AWTO_S2_FONT_BASE);
    ScalerOsd2BitFontOffset(AWTO_OSD_ZERO);
    AwtoOsdPlaceScaleUp(AWTO_S2_POS_H, AWTO_S2_POS_V, AWTO_S2_COLS, AWTO_S2_ROWS, AWTO_S2_SU_FACTOR);
    for(ucI = 0; ucI < AWTO_S2_COLS; ucI++)
    {
        s_aMask[ucI] = 0;
    }
    g_usAwtoS2Frame = 0;
    s_ucCol = 0;
    s_ucShown = 0;                                                      // the first frame is drawn hidden, column by column (cmd 2), then shown
    s_ucNext = AWTO_S2_RING0;
    s_ucYsCol = AWTO_S2_COLS;                                           // no previous column
    s_ucNumDirty = 1;                                                   // the first S2Params draws the readout tiles
    s_ucNumLeft = 0;
    s_ucFrameOn = 0;
    s_ucInCol = 0;
    s_ucRow = 0;
    s_ucSpread = AWTO_S2_SPREAD_MIN;
    s_usDrift = 0;
    return 0;
}
#endif                                                         // _AWTO_SAVER_SCOPE2
