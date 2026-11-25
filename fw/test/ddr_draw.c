#ifndef AWTO_DRW_HOST
#include "UserCommonInclude.h"
#endif

// #267 DDR draw ops (freeze build only): draw into the frame buffer through MCU_DC port A in the monitor, not burst by burst from the host.
// Host: scripts/ddr_draw.py fills g_stAwtoDraw, then ucGo = op; AwtoDrwPoll (main pass) runs it and clears ucGo. No test cmd number.
// ONE place owns the layout (#255 measurements, docs/data-channels.md): 8 B per address unit, 3 B per pixel (B, G, R), burst = 16 B = 2 units,
// the two 8 B halves of the write buffer are swapped, line pitch 1440 units, block 1 = chip A = even screen rows (screen row = 2 x memory line; odd rows chip B, docs/ddr-map.md).
#if(_AWTO_FREEZE == _ON)

#define AWTO_DRW_SCREEN_W                       3840
#define AWTO_DRW_SCREEN_H                       2160
#define AWTO_DRW_LINE_DOUBLE                    2                           // block 1: every memory line is shown on 2 screen rows
#define AWTO_DRW_LINES                          (AWTO_DRW_SCREEN_H / AWTO_DRW_LINE_DOUBLE)
#define AWTO_DRW_BPP                            3
#define AWTO_DRW_UNIT_BYTES                     8
#define AWTO_DRW_BURST_BYTES                    16
#define AWTO_DRW_HALF                           (AWTO_DRW_BURST_BYTES / 2)  // buffer halves swapped: buffer[0..7] -> unit a + 1, [8..15] -> unit a
#define AWTO_DRW_BURST_UNITS                    (AWTO_DRW_BURST_BYTES / AWTO_DRW_UNIT_BYTES)
#define AWTO_DRW_LINE_UNITS                     (AWTO_DRW_SCREEN_W * AWTO_DRW_BPP / AWTO_DRW_UNIT_BYTES)    // 1440, CAP_M1_LINE_STEP
#define AWTO_DRW_LINE_BURSTS                    (AWTO_DRW_LINE_UNITS / AWTO_DRW_BURST_UNITS)
#define AWTO_DRW_FRAME_BASE                     0UL                         // CAP_M1_MEM_ADDR in frame mode
#define AWTO_DRW_PHASES                         AWTO_DRW_BPP                // burst byte phase = burst index mod 3 (16 = 1 mod 3)
#define AWTO_DRW_LINE_BYTES                     (AWTO_DRW_SCREEN_W * AWTO_DRW_BPP)
#define AWTO_DRW_ALL_MASKED                     0xFFFF                      // WMASK: 1 = byte NOT written
#define AWTO_DRW_MASK_LANE_BUFFER               1                           // 1 = mask bit n = write BUFFER byte n (halves swapped like the data); op MASKTEST decides
#define AWTO_DRW_OPC_WRITE                      4                           // MCU_DC_CMD [7:5] 100 = write
#define AWTO_DRW_CMD_SHIFT                      5
#define AWTO_DRW_CMD_WRITE                      (AWTO_DRW_OPC_WRITE << AWTO_DRW_CMD_SHIFT)
#define AWTO_DRW_LEN_UNITS                      2                           // MCU_DC_LEN reset value; other values hang port A (#255)
#define AWTO_DRW_SPIN_FAST                      255                         // CMD poll before the ms limit: ~8 cycles each, DDR write ~0.4 us (estimate, #255)
#define AWTO_DRW_STALL_MS                       50                          // CMD -> NOP stall limit = 3 frames of DDR arbitration (as ddr_frame_test.py); expiry = op aborted, STALL
#define AWTO_DRW_GREY_NONE                      0xFFFF
#define AWTO_DRW_ISQRT_TOP_BIT                  (1UL << 30)
#define AWTO_DRW_GRAD_BAND_PX                   16                          // 16 px = 48 B = 3 bursts: a band starts on burst phase 0
#define AWTO_DRW_GRAD_BANDS                     (AWTO_DRW_SCREEN_W / AWTO_DRW_GRAD_BAND_PX)
#define AWTO_DRW_LEVEL_MAX                      255
#define AWTO_DRW_BARS                           8
#define AWTO_DRW_PAL_N                          10
#define AWTO_DRW_GRID_STEP_MAX                  AWTO_DRW_SCREEN_W
#define AWTO_DRW_FIG_SIDE                       100                         // grid100 figure (scripts/ddr_grid100.py): 100 px square, 10 x 10 cells, white circle
#define AWTO_DRW_FIG_N                          10
#define AWTO_DRW_MASKTEST_BURSTS                16
#define AWTO_DRW_BLOCK1_UNITS                   ((unsigned long)AWTO_DRW_LINE_UNITS * AWTO_DRW_LINES)      // 1 555 200 units = 12 441 600 B
#define AWTO_DRW_ADDR_BURSTS                    (AWTO_DRW_BLOCK1_UNITS / AWTO_DRW_BURST_UNITS)             // 777 600
#define AWTO_DRW_ADDR_BLOCK_BURSTS              128                         // 128 bursts = 256 units: the low address byte wraps, mid / high index bytes change
#define AWTO_DRW_ADDR_BLOCKS                    ((unsigned long)AWTO_DRW_ADDR_BURSTS / AWTO_DRW_ADDR_BLOCK_BURSTS)        // 6075
#define AWTO_DRW_IDX_BYTES                      4                           // unit index ^ seed, memory bytes 0..3 of each 8 B unit, low first
#define AWTO_DRW_LANE_BYTES                     (AWTO_DRW_UNIT_BYTES - AWTO_DRW_IDX_BYTES)
#define AWTO_DRW_IDX_BITS                       28                          // MCU_DC address: ADDR_H 4 bits + 3 bytes = 2 GB of 8 B units
#define AWTO_DRW_ODD_BUF                        0                           // buffer byte of memory byte 0 of the ODD unit (halves swapped)
#define AWTO_DRW_EVEN_BUF                       AWTO_DRW_HALF               // ... of the EVEN unit
#define AWTO_DRW_OPC_READ                       5                           // MCU_DC_CMD [7:5] 101 = read
#define AWTO_DRW_CMD_READ                       (AWTO_DRW_OPC_READ << AWTO_DRW_CMD_SHIFT)
#define AWTO_DRW_READ_FLAG_BIT                  0x01                        // MCU_DC_READ_FLAG [0]
#define AWTO_DRW_WATCH_N                        8
#define AWTO_DRW_ADDR_TMO_MAX                   4096                        // read-flag timeouts (50 ms each) before the op aborts: 4096 x 50 ms = 205 s backstop
#define AWTO_DRW_REC_N                          4                           // first mismatches kept
#define AWTO_DRW_INV                            0xFF

#define AWTO_DRW_OP_FILL_RECT                   1       // x y w h rgb
#define AWTO_DRW_OP_HLINE                       2       // x y w(length) rgb: 1 screen row = 1 memory line (2 rows shown)
#define AWTO_DRW_OP_VLINE                       3       // x y h(length) rgb
#define AWTO_DRW_OP_GRID                        4       // x y w(side) n(cells per side), line colours = palette
#define AWTO_DRW_OP_CIRCLE                      5       // x y w(diameter, box top-left) rgb, 1 px ring in screen geometry
#define AWTO_DRW_OP_FIGURE                      6       // x y: grid100 = GRID(100, 10) + white CIRCLE(100) in ONE command
#define AWTO_DRW_OP_BARS                        7       // x y w h: 8 colour bars
#define AWTO_DRW_OP_FILL_FRAME                  8       // rgb: whole block 1
#define AWTO_DRW_OP_GRAD_H                      9       // grey ramp across the frame (240 bands of 16 px)
#define AWTO_DRW_OP_GRAD_V                      10      // grey ramp down the frame (one level per memory line)
#define AWTO_DRW_OP_MASKTEST                    11      // x y: 16 bursts at (x px, y row), burst j writes ONLY memory byte j (0xFF)
#define AWTO_DRW_OP_ADDR_FILL                   12      // params in g_stAwtoAddr (blk0, blocks, seed, inv): address-in-data fill, default = the shown block
#define AWTO_DRW_OP_ADDR_VERIFY                 13      // read back blocks (stride, swap, retry), results in g_stAwtoAddr
#define AWTO_DRW_OP_ADDR_WATCH                  14      // fill, then verify ucSamples times usStepMs apart (0 = back to back): bad bursts per sample (does the live capture overwrite it)

#define AWTO_DRW_ST_IDLE                        0
#define AWTO_DRW_ST_OK                          2
#define AWTO_DRW_ST_REFUSED                     3       // op unknown or the rectangle is empty / off screen
#define AWTO_DRW_ST_STALL                       4       // CMD stayed busy past AWTO_DRW_STALL_MS: op aborted

typedef struct
{
    BYTE ucGo;                                  // 0 = idle; host writes the op last
    BYTE ucSeq;                                 // +1 per finished op
    BYTE ucState;
    BYTE ucFrozen;                              // GET_OSD_FREEZE_STATUS at op start (a live capture overwrites the drawing)
    WORD usX;
    WORD usY;
    WORD usW;
    WORD usH;
    BYTE ucR;
    BYTE ucG;
    BYTE ucB;
    BYTE ucN;
    WORD usMs;                                  // AwtoMs delta of the last op
    unsigned long ulBursts;                     // bursts issued by the last op
    BYTE ucSlow;                                // CMD polls that outlasted AWTO_DRW_SPIN_FAST
} StAwtoDraw;

#ifndef AWTO_DRW_HOST
__xdata StAwtoDraw g_stAwtoDraw;
#define DRW_RD(reg)                             AWTO_XB(reg)
#define DRW_WR(reg, val)                        (AWTO_XB(reg) = (val))
#define DRW_FEED()                              AWTO_WDT_FEED(AWTO_WDT_S_POLL)
#else
extern StAwtoDraw g_stAwtoDraw;                 // host build (tests/ddr_draw_host.c): the harness supplies DRW_*, AwtoMs, GET_OSD_FREEZE_STATUS
#endif
#define DRW_IDLE()                              do { if((DRW_RD(AWTO_R_MCU_DC_CMD_A) & AWTO_F_MCU_DC_CMD_A_DDR_A_CMD) != 0) { DrwIdleSlow(0); } } while(0)

static const __code BYTE tcDrwPal[AWTO_DRW_PAL_N][AWTO_DRW_BPP] =       // R, G, B (scripts/ddr_grid100.py PAL)
{
    {255, 0, 0}, {255, 128, 0}, {255, 255, 0}, {0, 255, 0}, {0, 255, 255},
    {0, 0, 255}, {128, 0, 255}, {255, 0, 255}, {160, 82, 45}, {128, 128, 128}
};
static const __code BYTE tcDrwBars[AWTO_DRW_BARS][AWTO_DRW_BPP] =       // R, G, B: white yellow cyan green magenta red blue black
{
    {255, 255, 255}, {255, 255, 0}, {0, 255, 255}, {0, 255, 0}, {255, 0, 255}, {255, 0, 0}, {0, 0, 255}, {0, 0, 0}
};

static BYTE s_aucDrwC[AWTO_DRW_BPP];            // current colour in memory byte order B, G, R
static WORD s_usDrwColGrey;                     // grey level of the current colour, AWTO_DRW_GREY_NONE = not grey
static WORD s_usDrwBufGrey;                     // grey level the write buffer holds (any phase), NONE = unknown / colour
static WORD s_usDrwMask;                        // WMASK shadow, memory byte order (bit n = memory byte n not written)
static BYTE s_ucDrwErr;                         // AWTO_DRW_ST_* of the first failure, 0 = none
static BYTE s_ucDrwSlow;
static unsigned long s_ulDrwBursts;

static void DrwIdleSlow(BYTE ucPort)           // CMD busy after the first read: spin, then the ms limit; ucPort = register offset of the port
{
    BYTE ucN;
    unsigned long ulT;

    if(s_ucDrwErr != 0)
    {
        return;
    }
    for(ucN = AWTO_DRW_SPIN_FAST; ucN != 0; ucN--)
    {
        if((DRW_RD(AWTO_R_MCU_DC_CMD_A + ucPort) & AWTO_F_MCU_DC_CMD_A_DDR_A_CMD) == 0)
        {
            return;
        }
    }
    s_ucDrwSlow++;
    ulT = AwtoMs();
    while((DRW_RD(AWTO_R_MCU_DC_CMD_A + ucPort) & AWTO_F_MCU_DC_CMD_A_DDR_A_CMD) != 0)
    {
        if((AwtoMs() - ulT) >= AWTO_DRW_STALL_MS)
        {
            s_ucDrwErr = AWTO_DRW_ST_STALL;
            return;
        }
    }
}

static void DrwColour(BYTE ucR, BYTE ucG, BYTE ucB)
{
    s_aucDrwC[0] = ucB;
    s_aucDrwC[1] = ucG;
    s_aucDrwC[2] = ucR;
    s_usDrwColGrey = ((ucR == ucG) && (ucG == ucB)) ? ucR : AWTO_DRW_GREY_NONE;
}

static void DrwLoad(BYTE ucPh)                  // buffer byte j holds memory byte (j + HALF) mod 16 = colour (ph + k) mod 3
{
    BYTE ucJ;
    BYTE ucI;

    if((s_usDrwColGrey != AWTO_DRW_GREY_NONE) && (s_usDrwBufGrey == s_usDrwColGrey))
    {
        return;
    }
    DRW_IDLE();
    ucI = (ucPh + AWTO_DRW_HALF) % AWTO_DRW_PHASES;
    for(ucJ = 0; ucJ < AWTO_DRW_HALF; ucJ++)
    {
        DRW_WR(AWTO_R_MCU_DC_DATABUF_W_00_A + ucJ, s_aucDrwC[ucI]);
        ucI = (ucI == (AWTO_DRW_PHASES - 1)) ? 0 : (ucI + 1);
    }
    ucI = ucPh;
    for(ucJ = AWTO_DRW_HALF; ucJ < AWTO_DRW_BURST_BYTES; ucJ++)
    {
        DRW_WR(AWTO_R_MCU_DC_DATABUF_W_00_A + ucJ, s_aucDrwC[ucI]);
        ucI = (ucI == (AWTO_DRW_PHASES - 1)) ? 0 : (ucI + 1);
    }
    s_usDrwBufGrey = s_usDrwColGrey;
}

static void DrwMaskSet(WORD usMem)              // caller: CMD idle. usMem in memory byte order -> WMASK in write-buffer order
{
    if(usMem == s_usDrwMask)
    {
        return;
    }
#if(AWTO_DRW_MASK_LANE_BUFFER == 1)
    DRW_WR(AWTO_R_MCU_DC_WMASK_H_A, (BYTE)usMem);               // buffer bytes 8..15 = memory bytes 0..7
    DRW_WR(AWTO_R_MCU_DC_WMASK_L_A, (BYTE)(usMem >> AWTO_DRW_HALF));
#else
    DRW_WR(AWTO_R_MCU_DC_WMASK_H_A, (BYTE)(usMem >> AWTO_DRW_HALF));
    DRW_WR(AWTO_R_MCU_DC_WMASK_L_A, (BYTE)usMem);
#endif
    s_usDrwMask = usMem;
}

static unsigned long DrwBurstUnit(WORD usLine, WORD usBurst)
{
    return AWTO_DRW_FRAME_BASE + (unsigned long)AWTO_DRW_LINE_UNITS * usLine + (unsigned long)AWTO_DRW_BURST_UNITS * usBurst;
}

static void DrwEdge(WORD usLine, WORD usBurst, WORD usMask)     // one burst, some bytes masked
{
    unsigned long ulA = DrwBurstUnit(usLine, usBurst);

    DRW_IDLE();
    DrwLoad((BYTE)(usBurst % AWTO_DRW_PHASES));
    DrwMaskSet(usMask);
    DRW_WR(AWTO_R_MCU_DC_ADDR_H_A, (BYTE)(ulA >> 24));
    DRW_WR(AWTO_R_MCU_DC_ADDR_M_A, (BYTE)(ulA >> 16));
    DRW_WR(AWTO_R_MCU_DC_ADDR_L_A, (BYTE)(ulA >> 8));
    DRW_WR(AWTO_R_MCU_DC_ADDR_A, (BYTE)ulA);
    DRW_WR(AWTO_R_MCU_DC_CMD_A, AWTO_DRW_CMD_WRITE);
    s_ulDrwBursts++;
    DRW_IDLE();
    DrwMaskSet(0);
}

// Whole bursts usB0..usB1 of a line: one buffer load per phase, then ~4 register writes per burst (the hot loop).
static void DrwFull(WORD usLine, WORD usB0, WORD usB1)
{
    BYTE ucPh;
    BYTE ucN;
    BYTE ucMid;
    BYTE ucTop;
    WORD usB;
    WORD usLo;
    unsigned long ulA;

    for(ucPh = 0; ucPh < AWTO_DRW_PHASES; ucPh++)
    {
        usB = usB0 + ((ucPh + AWTO_DRW_PHASES - (usB0 % AWTO_DRW_PHASES)) % AWTO_DRW_PHASES);
        if(usB > usB1)
        {
            continue;
        }
        ucN = (BYTE)((usB1 - usB) / AWTO_DRW_PHASES + 1);       // <= 240 per line
        DrwLoad(ucPh);
        ulA = DrwBurstUnit(usLine, usB);
        usLo = (WORD)ulA;
        ucMid = (BYTE)(ulA >> 16);
        ucTop = (BYTE)(ulA >> 24);
        DRW_IDLE();
        DRW_WR(AWTO_R_MCU_DC_ADDR_H_A, ucTop);
        DRW_WR(AWTO_R_MCU_DC_ADDR_M_A, ucMid);
        s_ulDrwBursts += ucN;
        do
        {
            DRW_IDLE();
            DRW_WR(AWTO_R_MCU_DC_ADDR_L_A, (BYTE)(usLo >> 8));
            DRW_WR(AWTO_R_MCU_DC_ADDR_A, (BYTE)usLo);
            DRW_WR(AWTO_R_MCU_DC_CMD_A, AWTO_DRW_CMD_WRITE);
            usLo += AWTO_DRW_PHASES * AWTO_DRW_BURST_UNITS;
            if(usLo < (AWTO_DRW_PHASES * AWTO_DRW_BURST_UNITS))     // carry into bit 16
            {
                DRW_IDLE();
                ucMid++;
                if(ucMid == 0)
                {
                    ucTop++;
                    DRW_WR(AWTO_R_MCU_DC_ADDR_H_A, ucTop);
                }
                DRW_WR(AWTO_R_MCU_DC_ADDR_M_A, ucMid);
            }
        }
        while(--ucN != 0);
    }
}

// Pixels usX0..usX1 (inclusive) of one memory line in the current colour: edge bursts masked, the rest whole.
static void DrwSpan(WORD usX0, WORD usX1, WORD usLine)
{
    WORD usB0 = usX0 * AWTO_DRW_BPP;                            // byte range [usB0, usE) of the line
    WORD usE = (usX1 + 1) * AWTO_DRW_BPP;
    WORD usFirst = usB0 / AWTO_DRW_BURST_BYTES;
    WORD usLast = (usE - 1) / AWTO_DRW_BURST_BYTES;
    BYTE ucHead = (BYTE)(usB0 % AWTO_DRW_BURST_BYTES);          // bytes 0..ucHead-1 of the first burst are not ours
    BYTE ucTail = (BYTE)((usE - 1) % AWTO_DRW_BURST_BYTES + 1); // bytes 0..ucTail-1 of the last burst are ours
    WORD usMHead = (WORD)(((unsigned long)1 << ucHead) - 1);
    WORD usMTail = (WORD)(AWTO_DRW_ALL_MASKED & ~(((unsigned long)1 << ucTail) - 1));

    if(usFirst == usLast)
    {
        DrwEdge(usLine, usFirst, usMHead | usMTail);
        return;
    }
    if(usMHead != 0)
    {
        DrwEdge(usLine, usFirst, usMHead);
        usFirst++;
    }
    if(usMTail != 0)
    {
        DrwEdge(usLine, usLast, usMTail);
        usLast--;
    }
    if(usFirst <= usLast)
    {
        DrwFull(usLine, usFirst, usLast);
    }
}

static BYTE DrwRect(WORD usX, WORD usY, WORD usW, WORD usH)     // SCREEN pixels; odd rows round outward to the doubled memory line
{
    WORD usM;
    WORD usM1;

    if((usW == 0) || (usH == 0) || (usX >= AWTO_DRW_SCREEN_W) || (usY >= AWTO_DRW_SCREEN_H))
    {
        return 0;
    }
    if(usW > (AWTO_DRW_SCREEN_W - usX))
    {
        usW = AWTO_DRW_SCREEN_W - usX;
    }
    if(usH > (AWTO_DRW_SCREEN_H - usY))
    {
        usH = AWTO_DRW_SCREEN_H - usY;
    }
    usM1 = (usY + usH - 1) / AWTO_DRW_LINE_DOUBLE;
    for(usM = usY / AWTO_DRW_LINE_DOUBLE; (usM <= usM1) && (s_ucDrwErr == 0); usM++)
    {
        DRW_FEED();
        DrwSpan(usX, usX + usW - 1, usM);
    }
    return 1;
}

static WORD DrwIsqrt(unsigned long ulV)
{
    unsigned long ulR = 0;
    unsigned long ulBit = AWTO_DRW_ISQRT_TOP_BIT;

    while(ulBit > ulV)
    {
        ulBit >>= 2;
    }
    while(ulBit != 0)
    {
        if(ulV >= (ulR + ulBit))
        {
            ulV -= ulR + ulBit;
            ulR = (ulR >> 1) + ulBit;
        }
        else
        {
            ulR >>= 1;
        }
        ulBit >>= 2;
    }
    return (WORD)ulR;
}

// 1 px ring in the box (usX, usY, usD): pixel (i, j) is on it when (d - 2)^2 < u^2 + v^2 <= d^2, u = 2i - (d - 1), v = 2j - (d - 1).
static BYTE DrwCircle(WORD usX, WORD usY, WORD usD)
{
    WORD usJ;
    WORD usOut;
    WORD usIn;
    WORD usOLo;
    WORD usOHi;
    WORD usILo;
    WORD usIHi;
    WORD usLine;
    long lV;
    unsigned long ulV2;
    unsigned long ulIn2 = (unsigned long)(usD - 2) * (usD - 2);

    if((usD < 3) || ((usX + usD) > AWTO_DRW_SCREEN_W) || ((usY + usD) > AWTO_DRW_SCREEN_H))
    {
        return 0;
    }
    for(usJ = 0; (usJ < usD) && (s_ucDrwErr == 0); usJ++)
    {
        DRW_FEED();
        lV = (long)2 * usJ - (usD - 1);
        ulV2 = (unsigned long)(lV * lV);
        usOut = DrwIsqrt((unsigned long)usD * usD - ulV2);
        usOLo = (usD - usOut) / 2;
        usOHi = (usOut + usD - 1) / 2;
        usLine = (usY + usJ) / AWTO_DRW_LINE_DOUBLE;
        if(ulV2 > ulIn2)
        {
            DrwSpan(usX + usOLo, usX + usOHi, usLine);
            continue;
        }
        usIn = DrwIsqrt(ulIn2 - ulV2);
        usILo = (usD - usIn) / 2;
        usIHi = (usIn + usD - 1) / 2;
        if(usILo > usIHi)
        {
            DrwSpan(usX + usOLo, usX + usOHi, usLine);
            continue;
        }
        if(usOLo < usILo)
        {
            DrwSpan(usX + usOLo, usX + usILo - 1, usLine);
        }
        if(usIHi < usOHi)
        {
            DrwSpan(usX + usIHi + 1, usX + usOHi, usLine);
        }
    }
    return 1;
}

static void DrwPal(BYTE ucIdx)
{
    DrwColour(tcDrwPal[ucIdx][0], tcDrwPal[ucIdx][1], tcDrwPal[ucIdx][2]);
}

// n x n cells in a square of usSide px: n vertical + n horizontal lines (first at the origin, one every side / n) + a closing one at side - 1.
static BYTE DrwGrid(WORD usX, WORD usY, WORD usSide, BYTE ucN)
{
    BYTE ucK;
    WORD usStep;
    WORD usAt;

    if((ucN == 0) || (usSide == 0) || ((usSide / ucN) == 0))
    {
        return 0;
    }
    usStep = usSide / ucN;
    for(ucK = 0; (ucK <= ucN) && (s_ucDrwErr == 0); ucK++)     // vertical lines
    {
        DrwPal((ucK < ucN) ? (ucK % AWTO_DRW_PAL_N) : (AWTO_DRW_PAL_N - 1));
        usAt = (ucK < ucN) ? (usX + (WORD)ucK * usStep) : (usX + usSide - 1);
        DrwRect(usAt, usY, 1, usSide);
    }
    for(ucK = 0; (ucK <= ucN) && (s_ucDrwErr == 0); ucK++)     // horizontal lines, 1 screen row = 1 memory line
    {
        DrwPal((ucK < ucN) ? (ucK % AWTO_DRW_PAL_N) : (AWTO_DRW_PAL_N - 1));
        usAt = (ucK < ucN) ? (usY + (WORD)ucK * usStep) : (usY + usSide - 1);
        DrwRect(usX, usAt, usSide, 1);
    }
    return 1;
}

static BYTE DrwBars(WORD usX, WORD usY, WORD usW, WORD usH)
{
    BYTE ucI;
    WORD usX0;
    WORD usX1;

    if(usW < AWTO_DRW_BARS)
    {
        return 0;
    }
    for(ucI = 0; ucI < AWTO_DRW_BARS; ucI++)
    {
        usX0 = usX + (WORD)((unsigned long)usW * ucI / AWTO_DRW_BARS);
        usX1 = usX + (WORD)((unsigned long)usW * (ucI + 1) / AWTO_DRW_BARS);
        DrwColour(tcDrwBars[ucI][0], tcDrwBars[ucI][1], tcDrwBars[ucI][2]);
        DrwRect(usX0, usY, usX1 - usX0, usH);
    }
    return 1;
}

static void DrwGradH(void)                      // band-outer: the colour (and the buffer) changes 240 times, not 259 000
{
    WORD usBand;
    WORD usM;
    BYTE ucL;

    for(usBand = 0; (usBand < AWTO_DRW_GRAD_BANDS) && (s_ucDrwErr == 0); usBand++)
    {
        ucL = (BYTE)((unsigned long)usBand * AWTO_DRW_LEVEL_MAX / (AWTO_DRW_GRAD_BANDS - 1));
        DrwColour(ucL, ucL, ucL);
        for(usM = 0; usM < AWTO_DRW_LINES; usM++)
        {
            DRW_FEED();
            DrwSpan(usBand * AWTO_DRW_GRAD_BAND_PX, usBand * AWTO_DRW_GRAD_BAND_PX + AWTO_DRW_GRAD_BAND_PX - 1, usM);
        }
    }
}

static void DrwGradV(void)
{
    WORD usM;
    BYTE ucL;

    for(usM = 0; (usM < AWTO_DRW_LINES) && (s_ucDrwErr == 0); usM++)
    {
        ucL = (BYTE)((unsigned long)usM * AWTO_DRW_LEVEL_MAX / (AWTO_DRW_LINES - 1));
        DrwColour(ucL, ucL, ucL);
        DRW_FEED();
        DrwSpan(0, AWTO_DRW_SCREEN_W - 1, usM);
    }
}

static BYTE DrwMaskTest(WORD usX, WORD usY)     // burst j writes only memory byte j: per-channel counts tell the mask lane order
{
    BYTE ucJ;
    WORD usB0 = (usX / AWTO_DRW_GRAD_BAND_PX) * AWTO_DRW_PHASES;

    if((usX >= AWTO_DRW_SCREEN_W) || (usY >= AWTO_DRW_SCREEN_H) || ((usB0 + AWTO_DRW_MASKTEST_BURSTS) > AWTO_DRW_LINE_BURSTS))
    {
        return 0;
    }
    DrwColour(AWTO_DRW_LEVEL_MAX, AWTO_DRW_LEVEL_MAX, AWTO_DRW_LEVEL_MAX);
    for(ucJ = 0; ucJ < AWTO_DRW_MASKTEST_BURSTS; ucJ++)
    {
        DrwEdge(usY / AWTO_DRW_LINE_DOUBLE, usB0 + ucJ, (WORD)(AWTO_DRW_ALL_MASKED & ~((unsigned long)1 << ucJ)));
    }
    return 1;
}

typedef struct
{
    unsigned long ulBlk0;                       // params (host writes, then g_stAwtoDraw.ucGo): first block of 128 bursts
    unsigned long ulBlocks;                     // blocks to fill / read, 0 = the shown block (AWTO_DRW_ADDR_BLOCKS)
    unsigned long ulSeed;                       // XORed into every unit index
    WORD usStride;                              // verify: blocks between reads (0 = 1)
    WORD usStepMs;                              // watch: ms between samples
    BYTE ucInv;                                 // 1 = every byte inverted
    BYTE ucSwap;                                // verify: read lane swap (0 / 1)
    BYTE ucRetry;                               // verify: extra reads of a bad burst, 0 = single read
    BYTE ucSamples;                             // watch: samples
    BYTE ucPort;                                // 0 = MCU_DC port A (chip A), 1 = port B (chip B, #348)
    unsigned long ulChecked;                    // results: bursts read back
    unsigned long ulBad;                        // still wrong after the extra reads
    unsigned long ulStale;                      // first read wrong, a retry right (only with ucRetry)
    unsigned long ulShift;                      // bad bursts whose index is the neighbour unit (+-1)
    unsigned long ulData;                       // bad bursts with the right index (data lane fault)
    unsigned long ulTmo;                        // read flag never set
    unsigned long ulSpin;                       // flag polls summed over all reads (first-poll hits count 0)
    unsigned long ulSlow;                       // reads that needed more than AWTO_DRW_SPIN_FAST polls
    unsigned long aulBit[AWTO_DRW_IDX_BITS];    // bad bursts per unit-index bit that differs (expected ^ got)
    WORD ausWatch[AWTO_DRW_WATCH_N];            // watch: bad bursts per sample
    BYTE ucRecN;
    unsigned long aulRecIdx[AWTO_DRW_REC_N];    // burst index of the first bad bursts
    BYTE aucRec[AWTO_DRW_REC_N][AWTO_DRW_BURST_BYTES];      // what was read (memory order after the lane swap)
} StAwtoAddr;

#ifndef AWTO_DRW_HOST
__xdata StAwtoAddr g_stAwtoAddr;
#else
extern StAwtoAddr g_stAwtoAddr;
#endif

static const __code BYTE tcDrwLane[AWTO_DRW_LANE_BYTES] = {0x5A, 0xA5, 0x3C, 0xC3};
static BYTE s_aucAdExp[AWTO_DRW_BURST_BYTES];   // expected burst, memory order
static BYTE s_aucAdGot[AWTO_DRW_BURST_BYTES];
static BYTE s_aucAdSeed[AWTO_DRW_IDX_BYTES];    // seed bytes, low first
static BYTE s_ucAdInv;
static BYTE s_ucAdSwap;
static BYTE s_ucAdPort;                         // register offset of the selected MCU_DC port (0 = A)

#define AWTO_DRW_PORT_B_OFF                     (AWTO_R_MCU_DC_CMD_B - AWTO_R_MCU_DC_CMD_A)    // port B registers = port A + this
#define AD_RD(reg)                              DRW_RD((reg) + s_ucAdPort)
#define AD_WR(reg, val)                         DRW_WR((reg) + s_ucAdPort, (val))
#define AD_IDLE()                               do { if((AD_RD(AWTO_R_MCU_DC_CMD_A) & AWTO_F_MCU_DC_CMD_A_DDR_A_CMD) != 0) { DrwIdleSlow(s_ucAdPort); } } while(0)

static void AdSet(BYTE ucPos, BYTE ucVal)       // one expected byte in both units
{
    s_aucAdExp[ucPos] = ucVal;
    s_aucAdExp[AWTO_DRW_UNIT_BYTES + ucPos] = ucVal;
}

static void AdBlockSet(unsigned long ulBlk)     // address upper bytes of the block + its index bytes 1..3 into the expected burst
{
    unsigned long ulU = ulBlk * (AWTO_DRW_ADDR_BLOCK_BURSTS * AWTO_DRW_BURST_UNITS);
    BYTE ucK;

    for(ucK = 1; ucK < AWTO_DRW_IDX_BYTES; ucK++)
    {
        AdSet(ucK, (BYTE)(ulU >> (8 * ucK)) ^ s_aucAdSeed[ucK] ^ s_ucAdInv);
    }
    AD_IDLE();
    AD_WR(AWTO_R_MCU_DC_ADDR_H_A, (BYTE)(ulU >> 24));
    AD_WR(AWTO_R_MCU_DC_ADDR_M_A, (BYTE)(ulU >> 16));
    AD_WR(AWTO_R_MCU_DC_ADDR_L_A, (BYTE)(ulU >> 8));
}

static unsigned long AdParams(void)             // returns the block count
{
    BYTE ucK;

    for(ucK = 0; ucK < AWTO_DRW_IDX_BYTES; ucK++)
    {
        s_aucAdSeed[ucK] = (BYTE)(g_stAwtoAddr.ulSeed >> (8 * ucK));
    }
    s_ucAdInv = (g_stAwtoAddr.ucInv != 0) ? AWTO_DRW_INV : 0;
    s_ucAdPort = (g_stAwtoAddr.ucPort != 0) ? AWTO_DRW_PORT_B_OFF : 0;
    AD_IDLE();
    AD_WR(AWTO_R_MCU_DC_LEN_A, AWTO_DRW_LEN_UNITS);             // port B: regdb reset 0x02, read 0x02 on unit 3 (#348); only 2 is ever written
    AD_WR(AWTO_R_MCU_DC_WMASK_H_A, 0);                          // every byte written
    AD_WR(AWTO_R_MCU_DC_WMASK_L_A, 0);
    for(ucK = 0; ucK < AWTO_DRW_LANE_BYTES; ucK++)
    {
        AdSet(AWTO_DRW_IDX_BYTES + ucK, tcDrwLane[ucK] ^ s_ucAdInv);
    }
    return (g_stAwtoAddr.ulBlocks == 0) ? AWTO_DRW_ADDR_BLOCKS : g_stAwtoAddr.ulBlocks;
}

static BYTE DrwAddrFill(void)
{
    unsigned long ulBlk;
    unsigned long ulN = AdParams();
    BYTE ucJ;
    BYTE ucK;
    BYTE ucLo;

    for(ucK = AWTO_DRW_IDX_BYTES; ucK < AWTO_DRW_UNIT_BYTES; ucK++)     // the lane bytes never change: loaded once
    {
        AD_IDLE();
        AD_WR(AWTO_R_MCU_DC_DATABUF_W_00_A + AWTO_DRW_EVEN_BUF + ucK, s_aucAdExp[ucK]);
        AD_WR(AWTO_R_MCU_DC_DATABUF_W_00_A + AWTO_DRW_ODD_BUF + ucK, s_aucAdExp[ucK]);
    }
    for(ulBlk = g_stAwtoAddr.ulBlk0; (ulBlk < (g_stAwtoAddr.ulBlk0 + ulN)) && (s_ucDrwErr == 0); ulBlk++)
    {
        DRW_FEED();
        AdBlockSet(ulBlk);
        for(ucK = 1; ucK < AWTO_DRW_IDX_BYTES; ucK++)
        {
            AD_WR(AWTO_R_MCU_DC_DATABUF_W_00_A + AWTO_DRW_EVEN_BUF + ucK, s_aucAdExp[ucK]);
            AD_WR(AWTO_R_MCU_DC_DATABUF_W_00_A + AWTO_DRW_ODD_BUF + ucK, s_aucAdExp[ucK]);
        }
        for(ucJ = 0; ucJ < AWTO_DRW_ADDR_BLOCK_BURSTS; ucJ++)
        {
            ucLo = (BYTE)(ucJ * AWTO_DRW_BURST_UNITS);
            AD_IDLE();
            AD_WR(AWTO_R_MCU_DC_ADDR_A, ucLo);
            ucLo ^= s_aucAdSeed[0] ^ s_ucAdInv;
            AD_WR(AWTO_R_MCU_DC_DATABUF_W_00_A + AWTO_DRW_EVEN_BUF, ucLo);
            AD_WR(AWTO_R_MCU_DC_DATABUF_W_00_A + AWTO_DRW_ODD_BUF, ucLo ^ 1);
            AD_WR(AWTO_R_MCU_DC_CMD_A, AWTO_DRW_CMD_WRITE);
        }
        s_ulDrwBursts += AWTO_DRW_ADDR_BLOCK_BURSTS;
    }
    return 1;
}

static BYTE AdRead(BYTE ucLo)                   // 0 = flag timeout
{
    BYTE ucN;
    BYTE ucJ;
    unsigned long ulT;

    AD_IDLE();
    AD_WR(AWTO_R_MCU_DC_ADDR_A, ucLo);
    AD_WR(AWTO_R_MCU_DC_CMD_A, AWTO_DRW_CMD_READ);
    for(ucN = AWTO_DRW_SPIN_FAST; (ucN != 0) && ((AD_RD(AWTO_R_MCU_DC_READ_FLAG_A) & AWTO_DRW_READ_FLAG_BIT) == 0); ucN--)
    {
    }
    g_stAwtoAddr.ulSpin += (BYTE)(AWTO_DRW_SPIN_FAST - ucN);
    if(ucN == 0)
    {
        g_stAwtoAddr.ulSlow++;
        ulT = AwtoMs();
        while((AD_RD(AWTO_R_MCU_DC_READ_FLAG_A) & AWTO_DRW_READ_FLAG_BIT) == 0)
        {
            if((AwtoMs() - ulT) >= AWTO_DRW_STALL_MS)
            {
                return 0;
            }
        }
    }
    for(ucJ = 0; ucJ < AWTO_DRW_BURST_BYTES; ucJ++)
    {
        s_aucAdGot[ucJ] = AD_RD(AWTO_R_MCU_DC_DATABUF_R_00_A + ((ucJ + s_ucAdSwap * AWTO_DRW_HALF) % AWTO_DRW_BURST_BYTES));
    }
    return 1;
}

static BYTE AdMatch(void)
{
    BYTE ucJ;

    for(ucJ = 0; ucJ < AWTO_DRW_BURST_BYTES; ucJ++)
    {
        if(s_aucAdGot[ucJ] != s_aucAdExp[ucJ])
        {
            return 0;
        }
    }
    return 1;
}

static void AdBad(unsigned long ulBurst)
{
    BYTE ucK;
    unsigned long ulGot = 0;
    unsigned long ulDiff;
    unsigned long ulExp = ulBurst * AWTO_DRW_BURST_UNITS;

    for(ucK = 0; ucK < AWTO_DRW_IDX_BYTES; ucK++)
    {
        ulGot |= (unsigned long)(BYTE)(s_aucAdGot[ucK] ^ s_ucAdInv ^ s_aucAdSeed[ucK]) << (8 * ucK);
    }
    ulDiff = ulGot ^ ulExp;
    g_stAwtoAddr.ulBad++;
    if(ulDiff == 0)
    {
        g_stAwtoAddr.ulData++;
    }
    else if(((ulGot + 1) == ulExp) || (ulGot == (ulExp + 1)))
    {
        g_stAwtoAddr.ulShift++;
    }
    for(ucK = 0; ucK < AWTO_DRW_IDX_BITS; ucK++)
    {
        if(((ulDiff >> ucK) & 1) != 0)
        {
            g_stAwtoAddr.aulBit[ucK]++;
        }
    }
    if(g_stAwtoAddr.ucRecN < AWTO_DRW_REC_N)
    {
        g_stAwtoAddr.aulRecIdx[g_stAwtoAddr.ucRecN] = ulBurst;
        for(ucK = 0; ucK < AWTO_DRW_BURST_BYTES; ucK++)
        {
            g_stAwtoAddr.aucRec[g_stAwtoAddr.ucRecN][ucK] = s_aucAdGot[ucK];
        }
        g_stAwtoAddr.ucRecN++;
    }
}

static void AdVerifyBlocks(unsigned long ulBlk0, unsigned long ulN, WORD usStride)
{
    unsigned long ulI;
    unsigned long ulBlk;
    BYTE ucJ;
    BYTE ucTry;
    BYTE ucLo;
    BYTE ucOk;
    BYTE ucGot;

    for(ulI = 0; (ulI < ulN) && (s_ucDrwErr == 0); ulI++)
    {
        ulBlk = ulBlk0 + ulI * usStride;
        DRW_FEED();
        AdBlockSet(ulBlk);
        for(ucJ = 0; ucJ < AWTO_DRW_ADDR_BLOCK_BURSTS; ucJ++)
        {
            ucLo = (BYTE)(ucJ * AWTO_DRW_BURST_UNITS);
            s_aucAdExp[0] = ucLo ^ s_aucAdSeed[0] ^ s_ucAdInv;
            s_aucAdExp[AWTO_DRW_UNIT_BYTES] = s_aucAdExp[0] ^ 1;
            g_stAwtoAddr.ulChecked++;
            ucOk = 0;
            ucGot = 0;
            for(ucTry = 0; ucTry <= g_stAwtoAddr.ucRetry; ucTry++)
            {
                if(AdRead(ucLo) == 0)
                {
                    g_stAwtoAddr.ulTmo++;
                    if(g_stAwtoAddr.ulTmo >= AWTO_DRW_ADDR_TMO_MAX)
                    {
                        s_ucDrwErr = AWTO_DRW_ST_STALL;
                        return;
                    }
                    continue;
                }
                ucGot = 1;
                if(AdMatch() != 0)
                {
                    ucOk = 1;
                    if(ucTry != 0)
                    {
                        g_stAwtoAddr.ulStale++;
                    }
                    break;
                }
            }
            if((ucOk == 0) && (ucGot != 0))             // a burst whose reads all timed out is counted in ulTmo only
            {
                AdBad((ulBlk * AWTO_DRW_ADDR_BLOCK_BURSTS) + ucJ);
            }
        }
        s_ulDrwBursts += AWTO_DRW_ADDR_BLOCK_BURSTS;
    }
}

static void AdClearResults(void)
{
    BYTE *pucC = (BYTE *)&g_stAwtoAddr.ulChecked;
    WORD usI;

    for(usI = 0; usI < (WORD)(sizeof(g_stAwtoAddr) - (WORD)((BYTE *)&g_stAwtoAddr.ulChecked - (BYTE *)&g_stAwtoAddr)); usI++)
    {
        pucC[usI] = 0;
    }
}

static BYTE DrwAddrVerify(void)
{
    unsigned long ulN;

    AdClearResults();
    ulN = AdParams();
    s_ucAdSwap = (g_stAwtoAddr.ucSwap != 0) ? 1 : 0;
    AdVerifyBlocks(g_stAwtoAddr.ulBlk0, ulN, (g_stAwtoAddr.usStride == 0) ? 1 : g_stAwtoAddr.usStride);
    return 1;
}

static BYTE DrwAddrWatch(void)
{
    BYTE ucS;
    unsigned long ulT0;
    unsigned long ulBad0;
    unsigned long ulN;

    if((g_stAwtoAddr.ucSamples == 0) || (g_stAwtoAddr.ucSamples > AWTO_DRW_WATCH_N))
    {
        return 0;
    }
    AdClearResults();
    ulN = AdParams();
    s_ucAdSwap = g_stAwtoAddr.ucSwap;
    DrwAddrFill();
    ulT0 = AwtoMs();
    for(ucS = 0; (ucS < g_stAwtoAddr.ucSamples) && (s_ucDrwErr == 0); ucS++)
    {
        while((AwtoMs() - ulT0) < ((unsigned long)(ucS + 1) * g_stAwtoAddr.usStepMs))
        {
            DRW_FEED();
        }
        ulBad0 = g_stAwtoAddr.ulBad;
        AdVerifyBlocks(g_stAwtoAddr.ulBlk0, ulN, 1);
        g_stAwtoAddr.ausWatch[ucS] = (WORD)(g_stAwtoAddr.ulBad - ulBad0);
    }
    return 1;
}

static BYTE DrwRun(BYTE ucOp)                   // 0 = refused
{
    WORD usX = g_stAwtoDraw.usX;
    WORD usY = g_stAwtoDraw.usY;
    WORD usW = g_stAwtoDraw.usW;
    WORD usH = g_stAwtoDraw.usH;

    DrwColour(g_stAwtoDraw.ucR, g_stAwtoDraw.ucG, g_stAwtoDraw.ucB);
    switch(ucOp)
    {
        case AWTO_DRW_OP_FILL_RECT:
            return DrwRect(usX, usY, usW, usH);
        case AWTO_DRW_OP_HLINE:
            return DrwRect(usX, usY, usW, 1);
        case AWTO_DRW_OP_VLINE:
            return DrwRect(usX, usY, 1, usH);
        case AWTO_DRW_OP_GRID:
            return DrwGrid(usX, usY, usW, g_stAwtoDraw.ucN);
        case AWTO_DRW_OP_CIRCLE:
            return DrwCircle(usX, usY, usW);
        case AWTO_DRW_OP_FIGURE:
            if(DrwGrid(usX, usY, AWTO_DRW_FIG_SIDE, AWTO_DRW_FIG_N) == 0)
            {
                return 0;
            }
            DrwColour(AWTO_DRW_LEVEL_MAX, AWTO_DRW_LEVEL_MAX, AWTO_DRW_LEVEL_MAX);
            return DrwCircle(usX, usY, AWTO_DRW_FIG_SIDE);
        case AWTO_DRW_OP_BARS:
            return DrwBars(usX, usY, usW, usH);
        case AWTO_DRW_OP_FILL_FRAME:
            return DrwRect(0, 0, AWTO_DRW_SCREEN_W, AWTO_DRW_SCREEN_H);
        case AWTO_DRW_OP_GRAD_H:
            DrwGradH();
            return 1;
        case AWTO_DRW_OP_GRAD_V:
            DrwGradV();
            return 1;
        case AWTO_DRW_OP_MASKTEST:
            return DrwMaskTest(usX, usY);
        case AWTO_DRW_OP_ADDR_FILL:
            return DrwAddrFill();
        case AWTO_DRW_OP_ADDR_VERIFY:
            return DrwAddrVerify();
        case AWTO_DRW_OP_ADDR_WATCH:
            return DrwAddrWatch();
        default:
            return 0;
    }
}

void AwtoDrwPoll(void)                          // main pass: one op at a time, runs to the end (WDT fed per line)
{
    BYTE ucOp = g_stAwtoDraw.ucGo;
    BYTE ucOk;
    unsigned long ulT0;

    if(ucOp == 0)
    {
        return;
    }
    g_stAwtoDraw.ucFrozen = GET_OSD_FREEZE_STATUS();
    s_ucDrwErr = 0;
    s_ucDrwSlow = 0;
    s_ulDrwBursts = 0;
    s_usDrwMask = AWTO_DRW_ALL_MASKED;                          // shadow unknown: the first DrwMaskSet(0) writes WMASK
    s_usDrwBufGrey = AWTO_DRW_GREY_NONE;
    ulT0 = AwtoMs();
    DRW_WR(AWTO_R_MCU_DC_LEN_A, AWTO_DRW_LEN_UNITS);
    DRW_IDLE();
    DrwMaskSet(0);
    s_ucAdPort = 0;
    ucOk = DrwRun(ucOp);
    DRW_IDLE();
    AD_IDLE();                                                  // addr ops on port B: its last write done too
    g_stAwtoDraw.usMs = (WORD)(AwtoMs() - ulT0);
    g_stAwtoDraw.ulBursts = s_ulDrwBursts;
    g_stAwtoDraw.ucSlow = s_ucDrwSlow;
    g_stAwtoDraw.ucState = (s_ucDrwErr != 0) ? s_ucDrwErr : ((ucOk != 0) ? AWTO_DRW_ST_OK : AWTO_DRW_ST_REFUSED);
    g_stAwtoDraw.ucSeq++;
    g_stAwtoDraw.ucGo = 0;
}

#endif
