#include "UserCommonInclude.h"

// #33: 0x01..0x05 = key messages 0..4 = menu role (physical AUTO) / UP / DOWN / exit role (physical MENU) / SOURCE; logged as injected, #39), 0x41/0x42 = key test screen open/close (#39), 0x10+n = OSD event n (n<16; 0x70+n-16 above), 0x20 = debug pop-up (#34).
// 0x22/0x23: on-screen message log on/off (#56); 0x28/0x29 debug messages on/off, NVRAM (#74). #28 holds (isr_g_stAwtoDiag.ucHold):
// 0x26 debug pop-up held, 0x27 clear all holds (0x21 / 0x24 / 0x25 were the boot logo, #144). #60: 0x31..0x33 switch to D1..D3 (fixed port),
// 0x30 auto search, 0x06..0x08 / 0x09..0x0B D1..D3 off / on (#81), 0x40 settings defaults (#67), 0x3D one store write, 0x3E POWER key (#151). 0x50+n directly holds EnumOSDDispMsg n for visual review. 0x0C / 0x0D frame buffer forced / SDK memory choice (#165). 0x2A..0x2F Timer0 events (#138).
#define AWTO_TC_PORT_OFF                        0x06    // #81 test cmds: + 0..2 = D1..D3 off; AWTO_TC_PORT_ON + 0..2 = on
#define AWTO_TC_PORT_ON                         0x09

void AwtoMsgLoad(void)              // #74: after RTDNVRamStartup (keil2sdcc sub); reset value 0 = off until then
{
#if(_DEBUG_MESSAGE_SUPPORT == _ON)
    g_ucAwtoMsgOn = g_stOSDUserData.b1AwtoMsgOn;
#endif
}

// Hold guards (#28): a held visual survives the SDK's own OSD paths; each blocked path is logged (StAwtoSw, scripts/sw_timeline.py).
bit AwtoHoldBlocksDisable(void)                  // top of OsdDispDisableOsd: the SDK OSD timeout / reset paths
{
#ifdef _AWTO_NEW_SETTINGS
    if((g_ucAwtoMenuOn != 0) && (SysPowerGetPowerStatus() == _POWER_STATUS_NORMAL) && (SysModeGetModeState() != _MODE_STATUS_POWER_SAVING))
    {
        return _TRUE;                            // #67 / #88: the source search resets the SDK OSD every few seconds; the awto menu closes itself
    }
#endif
    if(isr_g_stAwtoDiag.ucHold == 0)
    {
        return _FALSE;
    }
    AwtoSwEvent(AWTO_SW_EV_HOLD_BLOCK, SysModeGetModeState());
    isr_g_stAwtoSw.ucHoldBlocks++;
    return _TRUE;
}

#ifdef _AWTO_PROBES                             // -D _AWTO_PROBES: OSD SRAM + 0xA5 probes (~280 B XDATA, #233); host: scripts/osd_sram_probe.py
// #226 OSD SRAM probe, on the MCU through the SDK write path (not over I2C): per address read M1 and M2 (0x0093[5] sram_read_select),
// write the marker <addr hi>, <addr lo>, B2 to both, read M1 / M2 again, put zeros back. An address that is not all zero before
// (live OSD data) is only read. OSD must be off (0x3A33[4] sram_read_en reads only with the OSD off; the 2nd read is the right one).
#define AWTO_OSDP_N                             13
#define AWTO_OSDP_MARK_B2                       0xA5
typedef struct
{
    BYTE ucState;                                       // 0 idle, 2 done, 3 refused (OSD on)
    BYTE ucCircuit;                                     // OSD circuit enable (0x3A02[0]) before the probe
    WORD ausAddr[AWTO_OSDP_N];
    BYTE aucOrig[AWTO_OSDP_N][6];                       // M1 B0..B2, M2 B0..B2 before
    BYTE aucMark[AWTO_OSDP_N][6];                       // the same after the marker write
    BYTE aucSkip[AWTO_OSDP_N];                          // 1 = not all zero before: read only
} StAwtoOsdProbe;
__xdata StAwtoOsdProbe g_stAwtoOsdProbe;
static const __code WORD tAwtoOsdProbeAddr[AWTO_OSDP_N] = {0x0000, 0x0800, 0x0FFF, 0x1000, 0x1FFF, 0x2000, 0x2FFF, 0x3000, 0x3FFF, 0x4000, 0x5000, 0x6000, 0x7FFF};

static void AwtoOsdProbeRead(WORD usAddr, BYTE ucSel, BYTE *pucOut)
{
    BYTE ucP;
    BYTE ucPlane;

    ScalerSetBit(AWTO_R_OSD_MISC_PORT, ~AWTO_F_OSD_MISC_PORT_SRAM_READ_SELECT, (ucSel != 0) ? AWTO_F_OSD_MISC_PORT_SRAM_READ_SELECT : 0x00);
    for(ucP = 0; ucP < 3; ucP++)
    {
        ucPlane = (ucP == 0) ? _OSD_BYTE0 : ((ucP == 1) ? _OSD_BYTE1 : _OSD_BYTE2);
        ScalerOsdAddrSet(_OSD_SRAM, ucPlane, usAddr, _OSD_WITHOUT_DB);
        ScalerGetByte(AWTO_R_OSD_DATA_PORT);                 // first read discarded
        ScalerOsdAddrSet(_OSD_SRAM, ucPlane, usAddr, _OSD_WITHOUT_DB);
        pucOut[ucP] = ScalerGetByte(AWTO_R_OSD_DATA_PORT);
    }
}

static void AwtoOsdSramProbe(void)
{
    BYTE ucI;
    BYTE ucS;
    BYTE ucK;
    BYTE ucMisc;
    BYTE ucWrote = 0;
    bit bCircuit = (ScalerGetBit(AWTO_R_FRAME_CTRL_02, AWTO_F_FRAME_CTRL_02_OSD_EN) != 0x00);
    WORD usA;

    if(ScalerOsdGetOsdEnable() == _TRUE)
    {
        g_stAwtoOsdProbe.ucState = 3;
        AwtoSyncPush(AWTO_SYNC_EV_OSDP, 3, 0);
        return;
    }
    ScalerOsdCircuitActivated(_ENABLE);                     // the SDK activates the OSD circuit before any SRAM access (waits 2 DVS); no-op when on
    ucMisc = ScalerGetByte(AWTO_R_OSD_MISC_PORT);
    ScalerSetBit(AWTO_R_OSD_MISC_PORT, ~AWTO_F_OSD_MISC_PORT_DB_ENABLE, 0x00);        // global double buffer off: writes latch at once
    ScalerSetBit(AWTO_R_FRAME_CTRL_33, ~AWTO_F_FRAME_CTRL_33_SRAM_READ_EN, AWTO_F_FRAME_CTRL_33_SRAM_READ_EN);      // sram_read_en
    for(ucI = 0; ucI < AWTO_OSDP_N; ucI++)
    {
        usA = tAwtoOsdProbeAddr[ucI];
        g_stAwtoOsdProbe.ausAddr[ucI] = usA;
        for(ucS = 0; ucS < 2; ucS++)
        {
            AwtoOsdProbeRead(usA, ucS, &g_stAwtoOsdProbe.aucOrig[ucI][ucS * 3]);
        }
        g_stAwtoOsdProbe.aucSkip[ucI] = 0;
        for(ucK = 0; ucK < 6; ucK++)
        {
            g_stAwtoOsdProbe.aucSkip[ucI] |= g_stAwtoOsdProbe.aucOrig[ucI][ucK];
        }
        if(g_stAwtoOsdProbe.aucSkip[ucI] != 0)
        {
            g_stAwtoOsdProbe.aucSkip[ucI] = 1;
            continue;
        }
        ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usA, _OSD_WITHOUT_DB);
        ScalerSetByte(AWTO_R_OSD_DATA_PORT, HIBYTE(usA));
        ScalerSetByte(AWTO_R_OSD_DATA_PORT, LOBYTE(usA));
        ScalerSetByte(AWTO_R_OSD_DATA_PORT, AWTO_OSDP_MARK_B2);
        for(ucS = 0; ucS < 2; ucS++)
        {
            AwtoOsdProbeRead(usA, ucS, &g_stAwtoOsdProbe.aucMark[ucI][ucS * 3]);
        }
        ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usA, _OSD_WITHOUT_DB);
        ScalerSetByte(AWTO_R_OSD_DATA_PORT, 0x00);           // zeros back (it was all zero)
        ScalerSetByte(AWTO_R_OSD_DATA_PORT, 0x00);
        ScalerSetByte(AWTO_R_OSD_DATA_PORT, 0x00);
        ucWrote++;
    }
    ScalerSetBit(AWTO_R_FRAME_CTRL_33, ~AWTO_F_FRAME_CTRL_33_SRAM_READ_EN, 0x00);
    ScalerSetBit(AWTO_R_OSD_WRITE_OPTION, ~(AWTO_F_OSD_WRITE_OPTION_BYTESEL | AWTO_F_OSD_WRITE_OPTION_SRAM_SEL), 0x00);   // byte select reset, address indicator = window registers
    ScalerSetByte(AWTO_R_OSD_MISC_PORT, ucMisc);
    if(bCircuit == _FALSE)
    {
        ScalerOsdCircuitActivated(_DISABLE);                // back as found
    }
    g_stAwtoOsdProbe.ucState = 2;
    g_stAwtoOsdProbe.ucCircuit = bCircuit;
    AwtoSyncPush(AWTO_SYNC_EV_OSDP, 1, ucWrote);
}
#endif

#ifdef _AWTO_OSD_HWTEST                         // -D _AWTO_OSD_HWTEST: OSD SRAM write / read-back tests on the unit (docs/osd-hw-tests.md); host: scripts/osd_hw_test.py
// The host fills g_stAwtoOsdHw over the debug link, then writes ucGo = op; the main loop runs it and clears ucGo. No test cmd number.
#include "../../tools/osd_lines/osd_lines.h"                // tile geometry only
#define AWTO_OHW_BUF                            54                  // one 2-bit glyph (18 words): the chunk a direct write streams back-to-back
#define AWTO_OHW_REGS                           9
#define AWTO_OHW_BAD                            8                   // first 4 mismatches: got, want
#define AWTO_OHW_WORD                           3
#define AWTO_OHW_OP_WRITE                       1                   // usN pattern bytes from usAddr
#define AWTO_OHW_OP_VERIFY                      2                   // read usN bytes back, compare with the pattern
#define AWTO_OHW_OP_READ                        3                   // usN words (<= 18) into aucBuf
#define AWTO_OHW_OP_CRC                         4                   // CRC-16 of usN words read back
#define AWTO_OHW_OP_WRBUF                       5                   // aucBuf (usN bytes) to usAddr
#define AWTO_OHW_OP_PLANES                      6                   // the plane / colour screen (T6)
#define AWTO_OHW_OP_S2FRAMES                    7                   // Scope 2: finish the current frame + usN more (saver poll held)
#define AWTO_OHW_OP_REGS                        8                   // register snapshot only
#define AWTO_OHW_OP_LADDER                      10                  // 2-bit glyph id ladder: ids 0..255 in a 16 x 16 grid, all plane A solid
#define AWTO_OHW_OP_SAVER                       9                   // saver request usN (as DDC/CI VCP 0xEB), served by one saver poll in the op
#define AWTO_OHW_M_SDK                          0                   // ScalerOsdDataPort per byte
#define AWTO_OHW_M_DIRECT                       1                   // AWTO_XFR stores back-to-back (loop over the chunk)
#define AWTO_OHW_M_GAP                          2                   // direct + ucGap delay-loop passes before each store
#define AWTO_OHW_M_TRIPLE                       3                   // direct, three stores per word unrolled (the map write shape)
#define AWTO_OHW_F_EA_OFF                       0x01                // interrupts off while writing
#define AWTO_OHW_F_M2                           0x02                // read M2 (else M1)
#define AWTO_OHW_F_HIDE                         0x04                // overlay off while writing
#define AWTO_OHW_F_HOLD                         0x08                // hold the saver poll (frozen screen) until cleared
#define AWTO_OHW_F_REPEAT                       0x10                // the first chunk repeated (no refill: pure port-write time); verify likewise
#define AWTO_OHW_F_RD_OVL                       0x20                // read-back: leave the overlay on (default: off for the read)
#define AWTO_OHW_F_RD_SU                        0x40                // read-back: scale-up engine off for the read
#define AWTO_OHW_ST_OK                          1
#define AWTO_OHW_ST_BAD_OP                      2
#define AWTO_OHW_ST_LIMIT                       3                   // S2FRAMES: call limit reached
#define AWTO_OHW_ST_NO_S2                       4                   // S2FRAMES: Scope 2 is not the running saver (cmd 2 without its start draws garbage)
#define AWTO_OHW_RUN_SCOPE2                     3                   // g_ucAwtoSaverRun of Scope 2 (saver.c AWTO_SAVER_SCOPE2)
#define AWTO_OHW_LFSR_POLY                      0xB400              // 16-bit Galois LFSR (x^16 + x^14 + x^13 + x^11 + 1)
#define AWTO_OHW_LFSR_LOW                       0x5A                // low byte of the start state (never all zero)
#define AWTO_OHW_LFSR_STEPS                     8                   // steps per output byte: no shifted copy between neighbours
#define AWTO_OHW_CRC_POLY                       0x1021              // CRC-16/CCITT-FALSE
#define AWTO_OHW_CRC_INIT                       0xFFFF
#define AWTO_OHW_BYTE_BITS                      8
#define AWTO_OHW_S2_CALLS                       60000               // S2FRAMES: cmd-2 calls per frame at most (one call = <= 8 ms band)
#define AWTO_OHW_S2_DRAW                        2
#define AWTO_OHW_PL_ROWS                        3                   // plane screen: 3 x 3 cells per shape, one gap column
#define AWTO_OHW_PL_COLS                        11
#define AWTO_OHW_PL_SHAPE                       4                   // shape column pitch (3 cells + gap)
#define AWTO_OHW_PL_FONT                        (AWTO_OHW_PL_ROWS + 1 + AWTO_OHW_PL_ROWS * AWTO_OHW_PL_COLS)
#define AWTO_OHW_PL_STRIDE                      18                  // words per 2-bit glyph
#define AWTO_OHW_PL_PLANE_W                     9
#define AWTO_OHW_PL_FACTOR                      16                  // scale-up 64 / 16 = 4x
#define AWTO_OHW_PL_POS_H                       200                 // x 4 px
#define AWTO_OHW_PL_POS_V                       600
#define AWTO_OHW_ROW_FULL                       0x0FFF              // 12 px row masks, bit 11 = px 0
#define AWTO_OHW_ROW_EDGE                       0x0C03
#define AWTO_OHW_ROW_MID                        0x0060
#define AWTO_OHW_ROW_NONE                       0x0000
#define AWTO_OHW_EDGE_ROWS                      2
#define AWTO_OHW_MID_ROW0                       8
#define AWTO_OHW_MID_ROW1                       9
#define AWTO_OHW_HALF                           12                  // bits per row in a word
#define AWTO_OHW_GLYPH_N                        4                   // 0 blank, 1 SOLID (plane A), 2 BOXES (plane B), 3 PLUSES (both)
#define AWTO_OHW_PAL_BG                         1
#define AWTO_OHW_PAL_C1                         2
#define AWTO_OHW_PAL_C2                         3
#define AWTO_OHW_PAL_C3                         4
#define AWTO_OHW_LD_N                           16                  // ladder: 16 x 16 cells, glyph id = row * 16 + col (as the viewer reads it)
#define AWTO_OHW_LD_IDS                         256
#define AWTO_OHW_LD_FONT                        616                 // = Scope 2 font base: the same glyph word addresses
#define AWTO_OHW_LD_POS_H                       384                 // (3840 - 16 * 12 * 4) / 2 / 4
#define AWTO_OHW_LD_POS_V                       504                 // (2160 - 16 * 18 * 4) / 2
#define AWTO_OHW_SOLID                          0xFF
#define AWTO_OHW_NO_DIGIT                       0
#define AWTO_OHW_DIGITS                         6                   // T10 variants 1..6, the digit shown in blue
#define AWTO_OHW_DG_W                           5
#define AWTO_OHW_DG_H                           7
#define AWTO_OHW_DG_ROW                         4
#define AWTO_OHW_DG_COL                         5
#define AWTO_OHW_V_STATIC                       1                   // no writes
#define AWTO_OHW_V_SDK                          2                   // glyphs rewritten (same content) through ScalerOsdDataPort, continuously
#define AWTO_OHW_V_DIRECT                       3                   // the same with direct stores
#define AWTO_OHW_V_MAP                          4                   // map words rewritten (same content)
#define AWTO_OHW_V_VBLANK                       5                   // one glyph per frame, right after DVS
#define AWTO_OHW_V_ADDR                         6                   // address sets only, no data
#define AWTO_OHW_V_SCOPE2                       7                   // Scope 2 running (one band per main pass), no digit
#define AWTO_OHW_CY_MS                          8000                // per variant
#define AWTO_OHW_CY_S2_START                    1                   // AwtoOhwCycleStep result: Scope 2 cmd 1
#define AWTO_OHW_CY_S2_STOP                     3                   // ... Scope 2 off + the ladder again
#define AWTO_OHW_CY_BAND_MS                     8                   // writes per main pass, as Scope 2 (AWTO_S2_PASS_MS)
#define AWTO_OHW_OP_CYCLE                       11                  // T10 on (usN != 0) / off
#define AWTO_OHW_LO                             40
#define AWTO_OHW_MIDC                           90
#define AWTO_OHW_HI                             230
typedef struct
{
    BYTE ucGo;                                          // host: op; fw: 0 when done
    BYTE ucSeq;                                         // fw: + 1 per finished op
    BYTE ucState;                                       // AWTO_OHW_ST_*
    BYTE ucMode;                                        // AWTO_OHW_M_*
    BYTE ucGap;
    BYTE ucFlags;                                       // AWTO_OHW_F_*
    BYTE ucSeed;
    BYTE ucOverlay;                                     // overlay enable seen at the start of the op
    WORD usAddr;
    WORD usN;
    WORD usBad;
    WORD usFirst;                                       // first bad byte index (0xFFFF none)
    WORD usCrc;
    WORD usMs;                                          // write / op time (AwtoMs)
    WORD usFrame;                                       // g_usAwtoS2Frame at the end of the op
    BYTE aucRegs[AWTO_OHW_REGS];                        // 3A02 3A0B 3A17 3A33 3A34 3A41 0093 0094 006C at the start of the op
    BYTE aucBad[AWTO_OHW_BAD];
    BYTE aucBuf[AWTO_OHW_BUF];
    BYTE ucSaverRun;                                    // g_ucAwtoSaverRun at the op
} StAwtoOsdHw;
__xdata StAwtoOsdHw g_stAwtoOsdHw;
extern __xdata WORD g_usAwtoS2Frame;
extern __xdata BYTE g_ucAwtoSaverRun;
extern void set_ap_screensaver_now(BYTE ucId, int iV);
static __xdata WORD s_usOhwLfsr;
static __xdata BYTE s_ucOhwCyOn;
static __xdata BYTE s_ucOhwCyVar;
static __xdata WORD s_usOhwCyPos;
static __xdata unsigned long s_ulOhwCyT0;
static const __code BYTE tAwtoOhwDigit[AWTO_OHW_DIGITS][AWTO_OHW_DG_H] = {        // 5 x 7, bit 4 = left column
    {0x04, 0x0C, 0x04, 0x04, 0x04, 0x04, 0x0E}, {0x0E, 0x11, 0x01, 0x02, 0x04, 0x08, 0x1F}, {0x1F, 0x02, 0x04, 0x02, 0x01, 0x11, 0x0E},
    {0x02, 0x06, 0x0A, 0x12, 0x1F, 0x02, 0x02}, {0x1F, 0x10, 0x1E, 0x01, 0x01, 0x11, 0x0E}, {0x06, 0x08, 0x10, 0x1E, 0x11, 0x11, 0x0E}};
static const __code WORD tAwtoOhwRegs[AWTO_OHW_REGS] = {AWTO_R_FRAME_CTRL_02, AWTO_R_FRAME_CTRL_0B, AWTO_R_FRAME_CTRL_17, AWTO_R_FRAME_CTRL_33,
                                                        AWTO_R_FRAME_CTRL_34, AWTO_R_FRAME_CTRL_41, AWTO_R_OSD_MISC_PORT, AWTO_R_OSD_WRITE_OPTION, AWTO_R_OVERLAY_CTRL};

static BYTE AwtoOhwNext(void)                           // pattern byte (scripts/osd_hw_test.py pattern())
{
    BYTE ucK;

    for(ucK = 0; ucK < AWTO_OHW_LFSR_STEPS; ucK++)
    {
        s_usOhwLfsr = (s_usOhwLfsr & 1) ? ((s_usOhwLfsr >> 1) ^ AWTO_OHW_LFSR_POLY) : (s_usOhwLfsr >> 1);
    }
    return LOBYTE(s_usOhwLfsr);
}

static void AwtoOhwSeed(void)
{
    s_usOhwLfsr = ((WORD)g_stAwtoOsdHw.ucSeed << AWTO_OHW_BYTE_BITS) | AWTO_OHW_LFSR_LOW;
}

static void AwtoOhwOverlay(BYTE ucOn)
{
    ScalerSetBit(AWTO_R_OVERLAY_CTRL, ~AWTO_F_OVERLAY_CTRL_OVERLAY_PORT_EN, (ucOn != 0) ? AWTO_F_OVERLAY_CTRL_OVERLAY_PORT_EN : 0x00);
}

static void AwtoOhwPut(BYTE ucN)                        // aucBuf[0..ucN) to the data port in the selected mode
{
    BYTE ucI;
    BYTE ucG;
    BYTE ucMode = g_stAwtoOsdHw.ucMode;

    if(ucMode == AWTO_OHW_M_SDK)
    {
        for(ucI = 0; ucI < ucN; ucI++)
        {
            ScalerOsdDataPort(g_stAwtoOsdHw.aucBuf[ucI]);
        }
    }
    else if(ucMode == AWTO_OHW_M_GAP)
    {
        for(ucI = 0; ucI < ucN; ucI++)
        {
            for(ucG = g_stAwtoOsdHw.ucGap; ucG != 0; ucG--)
            {
                __asm nop __endasm;
            }
            AWTO_XFR(AWTO_R_OSD_DATA_PORT) = g_stAwtoOsdHw.aucBuf[ucI];
        }
    }
    else if((ucMode == AWTO_OHW_M_TRIPLE) && ((ucN % AWTO_OHW_WORD) == 0))
    {
        for(ucI = 0; ucI < ucN; ucI += AWTO_OHW_WORD)
        {
            AWTO_XFR(AWTO_R_OSD_DATA_PORT) = g_stAwtoOsdHw.aucBuf[ucI];
            AWTO_XFR(AWTO_R_OSD_DATA_PORT) = g_stAwtoOsdHw.aucBuf[ucI + 1];
            AWTO_XFR(AWTO_R_OSD_DATA_PORT) = g_stAwtoOsdHw.aucBuf[ucI + 2];
        }
    }
    else
    {
        for(ucI = 0; ucI < ucN; ucI++)
        {
            AWTO_XFR(AWTO_R_OSD_DATA_PORT) = g_stAwtoOsdHw.aucBuf[ucI];
        }
    }
}

static __xdata BYTE s_aucOhwWord[AWTO_OHW_WORD];

static void AwtoOhwRead(WORD usWord)                   // one stored word, as ScalerOsdSramGetData (circuit off, sram_read_en): all 3 bytes read twice, the 2nd is right
{
    BYTE ucK;

    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usWord, _OSD_WITHOUT_DB);
    for(ucK = 0; ucK < AWTO_OHW_WORD; ucK++)
    {
        s_aucOhwWord[ucK] = ScalerGetByte(AWTO_R_OSD_DATA_PORT);
    }
    for(ucK = 0; ucK < AWTO_OHW_WORD; ucK++)
    {
        s_aucOhwWord[ucK] = ScalerGetByte(AWTO_R_OSD_DATA_PORT);
    }
}

static WORD AwtoOhwCrc(WORD usCrc, BYTE ucB)
{
    BYTE ucK;

    usCrc ^= (WORD)ucB << AWTO_OHW_BYTE_BITS;
    for(ucK = 0; ucK < AWTO_OHW_BYTE_BITS; ucK++)
    {
        usCrc = (usCrc & 0x8000) ? ((usCrc << 1) ^ AWTO_OHW_CRC_POLY) : (usCrc << 1);
    }
    return usCrc;
}

static void AwtoOhwWrite(void)                          // pattern in chunks of AWTO_OHW_BUF: refill, then one burst; one address set
{
    WORD usLeft = g_stAwtoOsdHw.usN;
    BYTE ucN;
    BYTE ucI;
    unsigned long ulT0;

    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, g_stAwtoOsdHw.usAddr, _OSD_WITHOUT_DB);
    ulT0 = AwtoMs();
    while(usLeft != 0)
    {
        AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
        ucN = (usLeft > AWTO_OHW_BUF) ? AWTO_OHW_BUF : (BYTE)usLeft;
        for(ucI = 0; (ucI < ucN) && ((usLeft == g_stAwtoOsdHw.usN) || ((g_stAwtoOsdHw.ucFlags & AWTO_OHW_F_REPEAT) == 0)); ucI++)
        {
            g_stAwtoOsdHw.aucBuf[ucI] = AwtoOhwNext();
        }
        if((g_stAwtoOsdHw.ucFlags & AWTO_OHW_F_EA_OFF) != 0)
        {
            EA = 0;
        }
        AwtoOhwPut(ucN);
        EA = 1;
        usLeft -= ucN;
    }
    g_stAwtoOsdHw.usMs = (WORD)(AwtoMs() - ulT0);
}

static void AwtoOhwVerify(BYTE ucOp)                    // VERIFY (pattern bytes), READ (words into aucBuf) or CRC (words)
{
    WORD usI;
    WORD usBytes = (ucOp == AWTO_OHW_OP_VERIFY) ? g_stAwtoOsdHw.usN : g_stAwtoOsdHw.usN * AWTO_OHW_WORD;
    BYTE ucGot;
    BYTE ucWant;
    BYTE ucNb = 0;
    WORD usCrc = AWTO_OHW_CRC_INIT;

    ScalerSetBit(AWTO_R_OSD_MISC_PORT, ~AWTO_F_OSD_MISC_PORT_SRAM_READ_SELECT, ((g_stAwtoOsdHw.ucFlags & AWTO_OHW_F_M2) != 0) ? AWTO_F_OSD_MISC_PORT_SRAM_READ_SELECT : 0x00);
    ScalerSetBit(AWTO_R_FRAME_CTRL_33, ~AWTO_F_FRAME_CTRL_33_SRAM_READ_EN, AWTO_F_FRAME_CTRL_33_SRAM_READ_EN);
    g_stAwtoOsdHw.usBad = 0;
    g_stAwtoOsdHw.usFirst = 0xFFFF;
    for(usI = 0; usI < usBytes; usI++)
    {
        if((usI & 0xFF) == 0)
        {
            AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
        }
        if((usI % AWTO_OHW_WORD) == 0)
        {
            AwtoOhwRead(g_stAwtoOsdHw.usAddr + usI / AWTO_OHW_WORD);
        }
        ucGot = s_aucOhwWord[usI % AWTO_OHW_WORD];
        usCrc = AwtoOhwCrc(usCrc, ucGot);
        if(ucOp == AWTO_OHW_OP_READ)
        {
            if(usI < AWTO_OHW_BUF)
            {
                g_stAwtoOsdHw.aucBuf[usI] = ucGot;
            }
            continue;
        }
        if(ucOp != AWTO_OHW_OP_VERIFY)
        {
            continue;
        }
        if(((g_stAwtoOsdHw.ucFlags & AWTO_OHW_F_REPEAT) != 0) && ((usI % AWTO_OHW_BUF) == 0))
        {
            AwtoOhwSeed();
        }
        ucWant = AwtoOhwNext();
        if(ucGot != ucWant)
        {
            if(g_stAwtoOsdHw.usBad == 0)
            {
                g_stAwtoOsdHw.usFirst = usI;
            }
            g_stAwtoOsdHw.usBad++;
            if(ucNb < AWTO_OHW_BAD)
            {
                g_stAwtoOsdHw.aucBad[ucNb] = ucGot;
                g_stAwtoOsdHw.aucBad[ucNb + 1] = ucWant;
                ucNb += 2;
            }
        }
    }
    g_stAwtoOsdHw.usCrc = usCrc;
    ScalerSetBit(AWTO_R_FRAME_CTRL_33, ~AWTO_F_FRAME_CTRL_33_SRAM_READ_EN, 0x00);
    ScalerSetBit(AWTO_R_OSD_MISC_PORT, ~AWTO_F_OSD_MISC_PORT_SRAM_READ_SELECT, 0x00);
}

static WORD AwtoOhwRow(BYTE ucGlyph, BYTE ucPlane, BYTE ucRow)   // 12 px row mask of the plane screen glyphs
{
    BYTE ucEdge = (BYTE)((ucRow < AWTO_OHW_EDGE_ROWS) || (ucRow >= OSD_TILE_H - AWTO_OHW_EDGE_ROWS));

    if((ucGlyph == 1) && (ucPlane == 0))
    {
        return AWTO_OHW_ROW_FULL;                                   // SOLID: plane A only
    }
    if((ucGlyph == 2) && (ucPlane == 1))
    {
        return (ucEdge != 0) ? AWTO_OHW_ROW_FULL : AWTO_OHW_ROW_EDGE;   // BOXES: plane B only
    }
    if(ucGlyph == 3)
    {
        return ((ucRow == AWTO_OHW_MID_ROW0) || (ucRow == AWTO_OHW_MID_ROW1)) ? AWTO_OHW_ROW_FULL : AWTO_OHW_ROW_MID;   // PLUSES: both planes
    }
    return AWTO_OHW_ROW_NONE;
}

static void AwtoOhwPlanes(void)                         // T6: SOLID = plane A (first 9 words) only, BOXES = plane B only, PLUSES = both; c1 red, c2 green, c3 blue
{
    BYTE ucG;
    BYTE ucP;
    BYTE ucW;
    BYTE ucR;
    BYTE ucC;
    WORD usRow;

    AwtoOsdScreenBegin();
    ScalerOsdSetColorPalette(AWTO_OSD_ZERO, AWTO_OSD_ZERO, AWTO_OSD_ZERO, AWTO_OSD_ZERO);
    ScalerOsdSetColorPalette(AWTO_OHW_PAL_BG, AWTO_OHW_MIDC, AWTO_OHW_MIDC, AWTO_OHW_MIDC);
    ScalerOsdSetColorPalette(AWTO_OHW_PAL_C1, AWTO_OHW_HI, AWTO_OHW_LO, AWTO_OHW_LO);
    ScalerOsdSetColorPalette(AWTO_OHW_PAL_C2, AWTO_OHW_LO, AWTO_OHW_HI, AWTO_OHW_LO);
    ScalerOsdSetColorPalette(AWTO_OHW_PAL_C3, AWTO_OHW_LO, AWTO_OHW_LO, AWTO_OHW_HI);
    ScalerOsd2FontFunction(_DISABLE);
    AwtoOsdRowCmds(AWTO_OHW_PL_ROWS, OSD_TILE_H, AWTO_OHW_PL_COLS);
    for(ucG = 0; ucG < AWTO_OHW_GLYPH_N; ucG++)
    {
        ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_OHW_PL_FONT + (WORD)ucG * AWTO_OHW_PL_STRIDE, _OSD_WITHOUT_DB);
        for(ucP = 0; ucP < 2; ucP++)
        {
            for(ucW = 0; ucW < AWTO_OHW_PL_PLANE_W; ucW++)          // word = row 2w (bits 23..12) | row 2w + 1; port order low byte first
            {
                usRow = AwtoOhwRow(ucG, ucP, (BYTE)(2 * ucW + 1));
                ScalerOsdDataPort(LOBYTE(usRow));
                ScalerOsdDataPort((BYTE)((HIBYTE(usRow)) | (BYTE)(AwtoOhwRow(ucG, ucP, (BYTE)(2 * ucW)) << (AWTO_OHW_HALF - AWTO_OHW_BYTE_BITS))));
                ScalerOsdDataPort((BYTE)(AwtoOhwRow(ucG, ucP, (BYTE)(2 * ucW)) >> (AWTO_OHW_HALF - AWTO_OHW_BYTE_BITS)));
            }
        }
    }
    for(ucR = 0; ucR < AWTO_OHW_PL_ROWS; ucR++)
    {
        for(ucC = 0; ucC < AWTO_OHW_PL_COLS; ucC++)
        {
            ucG = ((ucC % AWTO_OHW_PL_SHAPE) == (AWTO_OHW_PL_SHAPE - 1)) ? 0 : (BYTE)(ucC / AWTO_OHW_PL_SHAPE + 1);
            AwtoOsdWord(AWTO_OHW_PL_ROWS + 1 + (WORD)ucR * AWTO_OHW_PL_COLS + ucC,
                        (BYTE)(AWTO_OSD_ROW_B0 | (((AWTO_OHW_PAL_BG >> 3) & 1) << 5) | (((AWTO_OHW_PAL_C1 >> 3) & 1) << 4) | ((AWTO_OHW_PAL_C3 & 7) << 1) | ((AWTO_OHW_PAL_BG >> 2) & 1)),
                        ((WORD)ucG << AWTO_OHW_BYTE_BITS) | (BYTE)(((AWTO_OHW_PAL_BG & 3) << 6) | ((AWTO_OHW_PAL_C2 & 7) << 3) | (AWTO_OHW_PAL_C1 & 7)));
        }
    }
    SET_OSD_MAPA_COL_MAX(AWTO_OHW_PL_COLS);
    ScalerOsdSramBaseAddressSet(_OSD_A, AWTO_OSD_ZERO, AWTO_OHW_PL_ROWS + 1, AWTO_OHW_PL_FONT);
    ScalerOsd2BitFontOffset(AWTO_OSD_ZERO);
    AwtoOsdPlaceScaleUp(AWTO_OHW_PL_POS_H, AWTO_OHW_PL_POS_V, AWTO_OHW_PL_COLS, AWTO_OHW_PL_ROWS, AWTO_OHW_PL_FACTOR);
    osd_tc_show(1);
}

static void AwtoOhwLadderMap(BYTE ucDigit)              // map of the ladder: id = cell as the viewer reads it; the cells of a 5 x 7 digit 1..6 in blue
{
    WORD usI;
    WORD usCell;
    WORD usCells = (WORD)AWTO_OHW_LD_N * AWTO_OHW_LD_N;
    BYTE ucC1;
    BYTE ucR;
    BYTE ucC;

    for(usI = 0; usI < usCells; usI++)
    {
        ucR = (BYTE)(usI / AWTO_OHW_LD_N);
        ucC = (BYTE)(usI % AWTO_OHW_LD_N);
        ucC1 = AWTO_OHW_PAL_C1;
        if((ucDigit >= 1) && (ucDigit <= AWTO_OHW_DIGITS) && (ucR >= AWTO_OHW_DG_ROW) && (ucR < AWTO_OHW_DG_ROW + AWTO_OHW_DG_H) &&
           (ucC >= AWTO_OHW_DG_COL) && (ucC < AWTO_OHW_DG_COL + AWTO_OHW_DG_W) &&
           (((tAwtoOhwDigit[ucDigit - 1][ucR - AWTO_OHW_DG_ROW] >> (AWTO_OHW_DG_W - 1 - (ucC - AWTO_OHW_DG_COL))) & 1) != 0))
        {
            ucC1 = AWTO_OHW_PAL_C3;                                     // blue
        }
        usCell = (g_ucAwtoOsdRot != 0) ? AwtoOsdRotCell(usI, usCells) : usI;
        AwtoOsdWord(AWTO_OHW_LD_N + 1 + usCell,
                    (BYTE)(AWTO_OSD_ROW_B0 | (((AWTO_OHW_PAL_BG >> 3) & 1) << 5) | (((ucC1 >> 3) & 1) << 4) | ((AWTO_OHW_PAL_C3 & 7) << 1) | ((AWTO_OHW_PAL_BG >> 2) & 1)),
                    (usI << AWTO_OHW_BYTE_BITS) | (BYTE)(((AWTO_OHW_PAL_BG & 3) << 6) | ((AWTO_OHW_PAL_C2 & 7) << 3) | (ucC1 & 7)));
    }
}

static void AwtoOhwGlyphPut(BYTE ucId, BYTE ucDirect)  // one ladder glyph rewritten with the same content: plane A solid, plane B 0
{
    BYTE ucK;

    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_OHW_LD_FONT + (WORD)ucId * AWTO_OHW_PL_STRIDE, _OSD_WITHOUT_DB);
    for(ucK = 0; ucK < AWTO_OHW_PL_STRIDE * AWTO_OHW_WORD; ucK++)
    {
        if(ucDirect != 0)
        {
            AWTO_XFR(AWTO_R_OSD_DATA_PORT) = (ucK < AWTO_OHW_PL_PLANE_W * AWTO_OHW_WORD) ? AWTO_OHW_SOLID : AWTO_OSD_ZERO;
        }
        else
        {
            ScalerOsdDataPort((ucK < AWTO_OHW_PL_PLANE_W * AWTO_OHW_WORD) ? AWTO_OHW_SOLID : AWTO_OSD_ZERO);
        }
    }
}

static void AwtoOhwLadder(void);

static BYTE AwtoOhwCycleStep(void)                      // T10: one band of the variant; next every AWTO_OHW_CY_MS. Returns the Scope 2 cmd the poll must call (0 none)
{
    unsigned long ulT0 = AwtoMs();
    WORD usCells = (WORD)AWTO_OHW_LD_N * AWTO_OHW_LD_N;

    if((WORD)(ulT0 - s_ulOhwCyT0) >= AWTO_OHW_CY_MS)
    {
        s_ulOhwCyT0 = ulT0;
        s_ucOhwCyVar = (s_ucOhwCyVar >= AWTO_OHW_V_SCOPE2) ? 1 : (BYTE)(s_ucOhwCyVar + 1);
        g_stAwtoOsdHw.usFrame = s_ucOhwCyVar;                         // host sees the variant shown
        if(s_ucOhwCyVar == AWTO_OHW_V_SCOPE2)
        {
            return AWTO_OHW_CY_S2_START;                                // the real saver for one variant (no digit: the scope itself)
        }
        if(s_ucOhwCyVar == 1)
        {
            return AWTO_OHW_CY_S2_STOP;                                 // the poll stops Scope 2 and redraws the ladder
        }
        AwtoOhwLadderMap(s_ucOhwCyVar);
        return 0;
    }
    if(s_ucOhwCyVar == AWTO_OHW_V_SCOPE2)
    {
        return AWTO_OHW_S2_DRAW;                                        // one band, as the saver poll does
    }
    if(s_ucOhwCyVar == AWTO_OHW_V_STATIC)
    {
        return 0;
    }
    do
    {
        if(s_ucOhwCyVar == AWTO_OHW_V_VBLANK)                         // one glyph right after the display vsync, then back to the main loop
        {
            ScalerTimerWaitForEvent(_EVENT_DVS);
            AwtoOhwGlyphPut((BYTE)s_usOhwCyPos, 1);
            s_usOhwCyPos = (s_usOhwCyPos + 1) % AWTO_OHW_LD_IDS;
            g_stAwtoOsdHw.usBad++;
            return 0;
        }
        if(s_ucOhwCyVar == AWTO_OHW_V_MAP)
        {
            AwtoOhwLadderMap(s_ucOhwCyVar);
        }
        else if(s_ucOhwCyVar == AWTO_OHW_V_ADDR)
        {
            ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_OHW_LD_FONT + s_usOhwCyPos * AWTO_OHW_PL_STRIDE, _OSD_WITHOUT_DB);
        }
        else
        {
            AwtoOhwGlyphPut((BYTE)s_usOhwCyPos, (BYTE)(s_ucOhwCyVar == AWTO_OHW_V_DIRECT));
        }
        s_usOhwCyPos = (s_usOhwCyPos + 1) % ((s_ucOhwCyVar == AWTO_OHW_V_MAP) ? usCells : AWTO_OHW_LD_IDS);
        g_stAwtoOsdHw.usBad++;                                          // writes done (glyphs, maps or address sets)
    }
    while((WORD)(AwtoMs() - ulT0) < AWTO_OHW_CY_BAND_MS);
    return 0;
}

static void AwtoOhwLadder(void)                         // ids >= the first broken cell are fetched from elsewhere; colour = what plane A alone selects
{
    WORD usI;
    BYTE ucK;

    AwtoOsdScreenBegin();
    ScalerOsdSetColorPalette(AWTO_OSD_ZERO, AWTO_OSD_ZERO, AWTO_OSD_ZERO, AWTO_OSD_ZERO);
    ScalerOsdSetColorPalette(AWTO_OHW_PAL_BG, AWTO_OHW_MIDC, AWTO_OHW_MIDC, AWTO_OHW_MIDC);
    ScalerOsdSetColorPalette(AWTO_OHW_PAL_C1, AWTO_OHW_HI, AWTO_OHW_LO, AWTO_OHW_LO);
    ScalerOsdSetColorPalette(AWTO_OHW_PAL_C2, AWTO_OHW_LO, AWTO_OHW_HI, AWTO_OHW_LO);
    ScalerOsdSetColorPalette(AWTO_OHW_PAL_C3, AWTO_OHW_LO, AWTO_OHW_LO, AWTO_OHW_HI);
    ScalerOsd2FontFunction(_DISABLE);
    AwtoOsdRowCmds(AWTO_OHW_LD_N, OSD_TILE_H, AWTO_OHW_LD_N);
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, AWTO_OHW_LD_FONT, _OSD_WITHOUT_DB);
    for(usI = 0; usI < AWTO_OHW_LD_IDS; usI++)
    {
        AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
        for(ucK = 0; ucK < AWTO_OHW_PL_STRIDE * AWTO_OHW_WORD; ucK++)
        {
            ScalerOsdDataPort((ucK < AWTO_OHW_PL_PLANE_W * AWTO_OHW_WORD) ? AWTO_OHW_SOLID : AWTO_OSD_ZERO);
        }
    }
    AwtoOhwLadderMap(AWTO_OHW_NO_DIGIT);
    SET_OSD_MAPA_COL_MAX(AWTO_OHW_LD_N);
    ScalerOsdSramBaseAddressSet(_OSD_A, AWTO_OSD_ZERO, AWTO_OHW_LD_N + 1, AWTO_OHW_LD_FONT);
    ScalerOsd2BitFontOffset(AWTO_OSD_ZERO);
    AwtoOsdPlaceScaleUp(AWTO_OHW_LD_POS_H, AWTO_OHW_LD_POS_V, AWTO_OHW_LD_N, AWTO_OHW_LD_N, AWTO_OHW_PL_FACTOR);
    osd_tc_show(1);
}

// ---- MCU / flash clock sweep (docs/clock-sweep.md; host scripts/clk_sweep.py). MCU = M2PLL / F / M, SPI = M2PLL / F / F2 (FFED, FFEE, FFE9).
// Apply = dividers + everything derived from them as the SDK speed-up mode does, then the checks; held until revert / hold limit.
// Fallbacks: revert from the main loop at the hold limit; a stalled main loop = WDT reset (586 ms) = stock clock again.
#include "ScalerCommonFunctionInclude.h"                       // DELAY_5US / DELAY_XUS
#define AWTO_CLK_OP_APPLY                       1
#define AWTO_CLK_OP_REVERT                      2
#define AWTO_CLK_ST_IDLE                        0
#define AWTO_CLK_ST_HELD                        1
#define AWTO_CLK_ST_REVERTED                    2
#define AWTO_CLK_ST_REFUSED                     3
#define AWTO_CLK_ST_AUTO_REVERTED               4
#define AWTO_CLK_REF_NONE                       0
#define AWTO_CLK_REF_RANGE                      1                   // divider outside 1..15
#define AWTO_CLK_REF_BUSY                       2                   // a step is held: revert first
#define AWTO_CLK_REF_SPI                        3                   // SPI above the flash's fast-read rating
#define AWTO_CLK_REF_ORDER                      4                   // no write order keeps every transient inside the limits
#define AWTO_CLK_REF_RATIO                      5                   // MCU slower than the flash (cache mcu_low_speed mode not used)
#define AWTO_CLK_F_DUAL                         0x01                // READ_INSTRUCTION read_mode 10 (0x3B dual output) during the step
#define AWTO_CLK_F_CKCON                        0x02
#define AWTO_CLK_OP_DREAD                       0x3B                // MX25L8006E DREAD (datasheet): FF6B holds the fast-read opcode, also for read_mode 10
#define AWTO_CLK_F_NOWRAP                       0x04                // FF6C accessed with the default MOVX cycle (tests the SDK's 9-cycle wrapper claim)                // global MOVX stretch = ucCkcon during the step
#define AWTO_CLK_SPI_MAX_KHZ                    86000UL             // MX25L8006E fSCLK, FAST_READ (datasheet Table 13)
#define AWTO_CLK_SPI_DUAL_KHZ                   80000UL             // fTSCLK, DREAD
#define AWTO_CLK_CRC_FROM                       0x0100              // code region read with MOVC (common area, the code that runs)
#define AWTO_CLK_CRC_TO                         0x4000
#define AWTO_CLK_CRC_PASSES                     3
#define AWTO_CLK_XD_N                           AWTO_OHW_BUF        // the OSD test op's scratch buffer (idle while the clock op runs)
#define AWTO_CLK_XD_ROUNDS                      8
#define AWTO_CLK_ALU_LOOPS                      6
#define AWTO_CLK_ALU_N                          32768               // iterations per loop (WORD counter)
#define AWTO_CLK_ALU_POKE                       8192
#define AWTO_CLK_MISS_PASSES                    16                  // x 1024 line reads (stride 16 over the CRC region: every read a cache miss)
#define AWTO_CLK_MISS_READS                     1024
#define AWTO_CLK_LINE                           16
#define AWTO_CLK_WIN_TICKS                      100                 // crystal-vs-Timer2 window: < the WDT warning (200 ms without a poke)
#define AWTO_CLK_NS_PER_US                      1000UL
#define AWTO_CLK_DIV_MAX                        15
#define AWTO_CLK_DELAY5_N                       10
#define AWTO_CLK_DELAYX_US                      100
#define AWTO_CLK_DELAY_BAND                     5                   // % around AWTO_DELAY_TARGET_PCT
#define AWTO_CLK_DELAY_ITER                     8
#define AWTO_CLK_DELAY_REPS                     5
#define AWTO_CLK_PERM                           6
#define AWTO_CLK_SPI_N_MIN                      5                   // F x F2 >= 5 at 351 MHz keeps the SPI <= 86 MHz
typedef struct
{
    BYTE ucGo;                                          // host: 1 apply, 2 revert; fw clears
    BYTE ucSeq;
    BYTE ucState;                                       // AWTO_CLK_ST_*
    BYTE ucF;                                           // FFED[5:2] flash_clk_div (first stage, MCU and SPI)
    BYTE ucF2;                                          // FFE9[3:0] flash_clk_div2 (SPI second stage)
    BYTE ucM;                                           // FFEE[5:2] mcu_clk_div
    BYTE ucCkcon;
    BYTE ucFlags;                                       // AWTO_CLK_F_*
    WORD usHoldMs;                                      // revert by itself after this long
    WORD usRcap;                                        // RCAP2 now
    BYTE ucD5;                                          // DELAY_5US / DELAY_XUS counts now
    BYTE ucDX;
    WORD usD5Pct;                                       // measured / nominal, 10 x DELAY_5US
    WORD usDXPct;                                       // DELAY_XUS(100)
    WORD usTickPm;                                      // Timer2 ms per crystal ms x 1000
    BYTE aucCrc[4];                                     // CRC-32 of the code region (pass 0), big endian
    BYTE ucCrcBad;                                      // passes whose CRC differs from pass 0
    BYTE ucRes0;
    WORD usXdBad;
    WORD usAluMs;                                       // 3 x 65535 iterations
    WORD usMissMs;                                      // 16 x 1024 line reads
    WORD usCrcMs;                                       // one CRC pass
    BYTE ucFFED;
    BYTE ucFFE9;
    BYTE ucFFEE;
    BYTE ucFF6C;
    BYTE ucFDA1;
    BYTE ucCkNow;
    BYTE ucFormulaOk;                                   // the stock Timer2 reload came out of the reload formula
    BYTE ucRefuse;                                      // AWTO_CLK_REF_*
    unsigned long ulPllKhz;
    WORD usDdcDeb;
    unsigned long ulRef;                                // cache meter over the CRC pass 0: program reads, misses, memory restarts
    unsigned long ulMiss;
    unsigned long ulRestart;
    WORD usNowMs;                                       // AwtoMs low word, refreshed every main pass (host: heartbeat vs wall clock)
    BYTE ucDrive;                                       // request: SPI pad drive 0..7 (P10_C2[7:5] SCLK and [4:2] data: 2 mA + 0.5 mA x n), 0xFF = keep
    BYTE ucSlew;                                        // request: pad slew 0 fast / 1 slow (P10_81[7:6]), 0xFF = keep
    BYTE ucChip;                                        // ScalerGlobalGetIDCode (0x20 A, 0x21 B, 0x22 D, 0x23 E)
    BYTE ucDriveNow;                                    // P10_C2 / P10_81 now
    BYTE ucSlewNow;
    WORD usAstFrames;                                   // Asteroids frames drawn (g_usAwtoAstFrames, asteroids.c)
    BYTE ucRdTune;                                      // request: FF6C[5:2] (latch_so_rise, drive_si_fall, si_dly_sel) while the step is held, 0xFF = keep
    BYTE ucPasses;                                      // request: CRC passes in the checks (0 = AWTO_CLK_CRC_PASSES); more = a longer flash-read stress
    WORD usScFrames;                                    // Scope 1 frames drawn (g_usAwtoScFrames, scope_saver.c)
} StAwtoClk;
__xdata StAwtoClk g_stAwtoClk;
extern __xdata WORD g_usAwtoAstFrames;
extern __xdata WORD g_usAwtoScFrames;
static __xdata BYTE s_ucClkSaved;
static __xdata BYTE s_ucClkStock[11];                   // F, F2, M, CKCON, FF6C, D5, DX, FDA1, P10_C2, P10_81, FF6B
static __xdata WORD s_usClkStockRcap;
static __xdata WORD s_usClkStockDeb;
static __xdata unsigned long s_ulClkT0;
#define s_aucClkXd g_stAwtoOsdHw.aucBuf
static __xdata BYTE s_ucClkSink;
static const __code unsigned long tAwtoClkCrc[16] = {0x00000000UL, 0x1DB71064UL, 0x3B6E20C8UL, 0x26D930ACUL, 0x76DC4190UL, 0x6B6B51F4UL, 0x4DB26158UL, 0x5005713CUL,
                                                     0xEDB88320UL, 0xF00F9344UL, 0xD6D6A3E8UL, 0xCB61B38CUL, 0x9B64C2B0UL, 0x86D3D2D4UL, 0xA00AE278UL, 0xBDBDF21CUL};
static const __code BYTE tAwtoClkPerm[AWTO_CLK_PERM][3] = {{0, 1, 2}, {0, 2, 1}, {1, 0, 2}, {1, 2, 0}, {2, 0, 1}, {2, 1, 0}};     // 0 = FFE9, 1 = FFED, 2 = FFEE

static unsigned long AwtoClkPllKhz(void)                // M2PLL = crystal x M / (N x O) (0x01E0 = M - 2, 0x01E1[3:0] = N - 2, [5:4] = O / 2)
{
    BYTE ucN = ScalerGetByte(P1_E1_M2PLL_N);
    BYTE ucO = ((ucN >> 4) & 3) * 2;

    if(ucO == 0)
    {
        ucO = 1;
    }
    return ((unsigned long)_EXT_XTAL * ((WORD)ScalerGetByte(P1_E0_M2PLL_M) + 2)) / (((ucN & 0x0F) + 2) * ucO);
}

static WORD AwtoClkReload(BYTE ucF, BYTE ucM)           // as _TIMER2_COUNT_NUM: 1 ms of Timer2 (clk / 12)
{
    unsigned long ulT = 12UL * ucF * ucM;               // PLL kHz / ulT = Timer2 counts per ms

    return (WORD)(0xFFFF - (WORD)((g_stAwtoClk.ulPllKhz + ulT / 2) / ulT));
}

static BYTE s_ucClkWrap = _CKCON_MOVX_9_CYCLE;           // MOVX cycles for FF6C accesses (flag NOWRAP: the default)

static BYTE AwtoClkFlashRegGet(void)                    // FF6C read with the SDK's slow MOVX cycle (flash-controller registers, speed-up mode)
{
    BYTE ucV;

    CKCON = ((CKCON & ~(_BIT2 | _BIT1 | _BIT0)) | s_ucClkWrap);
    ucV = MCU_FF6C_READ_INSTRUCTION;
    CKCON = ((CKCON & ~(_BIT2 | _BIT1 | _BIT0)) | _CKCON_MOVX_DEFAULT_CYCLE);
    return ucV;
}

static void AwtoClkReadMode(BYTE ucOp, BYTE ucMode)     // FF6B opcode then FF6C: both write instructions sit in one cache line (called once warm with the old values first)
{
    CKCON = ((CKCON & ~(_BIT2 | _BIT1 | _BIT0)) | s_ucClkWrap);
    MCU_FF6B_FAST_READ_OP_CODE = ucOp;
    MCU_FF6C_READ_INSTRUCTION = ucMode;
    CKCON = ((CKCON & ~(_BIT2 | _BIT1 | _BIT0)) | _CKCON_MOVX_DEFAULT_CYCLE);
}

static void AwtoClkPoke(void)
{
    AWTO_XFR(AWTO_R_WATCHDOG_TIMER) |= AWTO_F_WATCHDOG_TIMER_CLR_WDT;
}

static void AwtoClkSetReg(BYTE ucReg, BYTE ucV)
{
    if(ucReg == 0)
    {
        MCU_FFE9_MCU_CLK_CONTROL_1 = (ucV & 0x0F) | (MCU_FFE9_MCU_CLK_CONTROL_1 & 0xF0);
    }
    else if(ucReg == 1)
    {
        MCU_FFED_MCU_CONTROL = ((ucV & 0x0F) << 2) | (MCU_FFED_MCU_CONTROL & 0xC3);
    }
    else
    {
        MCU_FFEE_MCU_CLOCK_CONTROL = ((ucV & 0x0F) << 2) | (MCU_FFEE_MCU_CLOCK_CONTROL & 0xC3);
    }
}

// Dividers -> (f2, f, m) in the first write order whose every transient has SPI <= rated and MCU not faster than the faster end; 0 = none.
static BYTE AwtoClkWrite(BYTE ucF, BYTE ucF2, BYTE ucM)
{
    BYTE ucP;
    BYTE ucS;
    BYTE aucCur[3];
    BYTE aucNew[3];
    BYTE ucOk;
    WORD usFast;
    WORD usOld = (WORD)(MCU_FFED_MCU_CONTROL >> 2 & 0x0F) * ((MCU_FFEE_MCU_CLOCK_CONTROL >> 2) & 0x0F);
    WORD usNew = (WORD)ucF * ucM;

    usFast = (usOld < usNew) ? usOld : usNew;
    aucNew[0] = ucF2;
    aucNew[1] = ucF;
    aucNew[2] = ucM;
    for(ucP = 0; ucP < AWTO_CLK_PERM; ucP++)
    {
        aucCur[0] = MCU_FFE9_MCU_CLK_CONTROL_1 & 0x0F;
        aucCur[1] = (MCU_FFED_MCU_CONTROL >> 2) & 0x0F;
        aucCur[2] = (MCU_FFEE_MCU_CLOCK_CONTROL >> 2) & 0x0F;
        ucOk = 1;
        for(ucS = 0; ucS < 3; ucS++)
        {
            aucCur[tAwtoClkPerm[ucP][ucS]] = aucNew[tAwtoClkPerm[ucP][ucS]];
            if(((WORD)aucCur[1] * aucCur[0] < AWTO_CLK_SPI_N_MIN) || ((WORD)aucCur[1] * aucCur[2] < usFast))
            {
                ucOk = 0;
            }
        }
        if(ucOk != 0)
        {
            for(ucS = 0; ucS < 3; ucS++)
            {
                AwtoClkSetReg(tAwtoClkPerm[ucP][ucS], aucNew[tAwtoClkPerm[ucP][ucS]]);
            }
            return 1;
        }
    }
    return 0;
}

static unsigned long AwtoClkT2Now(void)                 // Timer2 counter, torn-read safe, EA off by the caller
{
    BYTE ucH;
    BYTE ucL;

    do
    {
        ucH = TH2;
        ucL = TL2;
    }
    while(ucH != TH2);
    return ((unsigned long)ucH << 8) | ucL;
}

static unsigned long AwtoClkT2Diff(unsigned long ulA, unsigned long ulB)   // counts a -> b, at most one reload between
{
    WORD usRc = ((WORD)RCAP2H << 8) | RCAP2L;

    return (ulB >= ulA) ? (ulB - ulA) : ((0x10000UL - ulA) + (ulB - usRc));
}

#define AWTO_CLK_MEAS(dst, body)                                \
    do                                                          \
    {                                                           \
        (dst) = 0xFFFFFFFFUL;                                   \
        for(ucRep = 0; ucRep < AWTO_CLK_DELAY_REPS; ucRep++)    \
        {                                                       \
            EA = 0;                                             \
            body;                                               /* warm-up: the first run pays the cache misses */ \
            ulA = AwtoClkT2Now();                               \
            body;                                               \
            ulB = AwtoClkT2Now();                               \
            EA = 1;                                             \
            ulD = AwtoClkT2Diff(ulA, ulB);                      \
            ulD = (ulD > ulOvh) ? (ulD - ulOvh) : 0;            \
            (dst) = (ulD < (dst)) ? ulD : (dst);                /* the shortest of the runs: least disturbed (as the SDK-side calibration) */ \
        }                                                       \
    }                                                           \
    while(0)
#define AWTO_CLK_X10(op)    op; op; op; op; op; op; op; op; op; op

static void AwtoClkMeasDelay(void)                      // 10 x DELAY_5US and DELAY_XUS(100) against Timer2, % of nominal
{
    unsigned long ulA;
    unsigned long ulB;
    unsigned long ulOvh;
    unsigned long ulD;
    BYTE ucRep;
    unsigned long ulD5;
    unsigned long ulDX;
    unsigned long ulPer = 0x10000UL - (((WORD)RCAP2H << 8) | RCAP2L);   // counts per ms

    EA = 0;
    ulA = AwtoClkT2Now();
    ulB = AwtoClkT2Now();                               // warm-up pair, then the measured one
    ulA = AwtoClkT2Now();
    ulB = AwtoClkT2Now();
    EA = 1;
    ulOvh = AwtoClkT2Diff(ulA, ulB);
    AWTO_CLK_MEAS(ulD5, AWTO_CLK_X10(DELAY_5US()));
    AWTO_CLK_MEAS(ulDX, DELAY_XUS(AWTO_CLK_DELAYX_US));
    g_stAwtoClk.usD5Pct = (WORD)((ulD5 * 100UL * 1000UL) / (ulPer * 5UL * AWTO_CLK_DELAY5_N));
    g_stAwtoClk.usDXPct = (WORD)((ulDX * 100UL * 1000UL) / (ulPer * AWTO_CLK_DELAYX_US));
}

static BYTE AwtoClkDelayNext(BYTE ucC, BYTE ucPrevC, WORD usPct, WORD usPrevPct)   // secant step on count -> % (not proportional: fixed loop overhead)
{
    long lN;

    if((usPct == 0) || (usPrevPct == 0) || (ucC == ucPrevC) || (usPct == usPrevPct))
    {
        lN = (usPct == 0) ? ucC : ((long)ucC * AWTO_DELAY_TARGET_PCT) / usPct;
    }
    else
    {
        lN = (long)ucC + ((long)AWTO_DELAY_TARGET_PCT - usPct) * ((long)ucC - ucPrevC) / ((long)usPct - usPrevPct);
    }
    if(lN == ucC)
    {
        lN += (usPct < AWTO_DELAY_TARGET_PCT) ? 1 : -1;
    }
    return (lN < 1) ? 1 : ((lN > 255) ? 255 : (BYTE)lN);
}

static void AwtoClkDelayCal(void)                       // scaled stock counts, then secant steps until both are within AWTO_CLK_DELAY_BAND of AWTO_DELAY_TARGET_PCT
{
    BYTE ucK;
    BYTE ucP5 = d_isr_g_ucDelay5usN_Base;
    BYTE ucPX = d_isr_g_ucDelayXusN_Base;
    WORD usP5 = 0;
    WORD usPX = 0;
    BYTE ucN5;
    BYTE ucNX;

    for(ucK = 0; ucK < AWTO_CLK_DELAY_ITER; ucK++)
    {
        AwtoClkMeasDelay();
        if((g_stAwtoClk.usD5Pct + AWTO_CLK_DELAY_BAND >= AWTO_DELAY_TARGET_PCT) && (g_stAwtoClk.usD5Pct <= AWTO_DELAY_TARGET_PCT + AWTO_CLK_DELAY_BAND) &&
           (g_stAwtoClk.usDXPct + AWTO_CLK_DELAY_BAND >= AWTO_DELAY_TARGET_PCT) && (g_stAwtoClk.usDXPct <= AWTO_DELAY_TARGET_PCT + AWTO_CLK_DELAY_BAND))
        {
            break;
        }
        ucN5 = AwtoClkDelayNext(d_isr_g_ucDelay5usN_Base, ucP5, g_stAwtoClk.usD5Pct, usP5);
        ucNX = AwtoClkDelayNext(d_isr_g_ucDelayXusN_Base, ucPX, g_stAwtoClk.usDXPct, usPX);
        ucP5 = d_isr_g_ucDelay5usN_Base;
        ucPX = d_isr_g_ucDelayXusN_Base;
        usP5 = g_stAwtoClk.usD5Pct;
        usPX = g_stAwtoClk.usDXPct;
        d_isr_g_ucDelay5usN_Base = ucN5;
        d_isr_g_ucDelayXusN_Base = ucNX;
    }
    AwtoClkMeasDelay();                                 // the result of the counts that stay
    g_stAwtoClk.ucD5 = d_isr_g_ucDelay5usN_Base;
    g_stAwtoClk.ucDX = d_isr_g_ucDelayXusN_Base;
}

static void AwtoClkTickCheck(void)                      // Timer2 ms over AWTO_CLK_WIN_TICKS ticks vs the crystal-clocked WDT counter (clear = latch)
{
    WORD usT = (WORD)AwtoMs();
    WORD usN;
    unsigned long ulX;

    while((WORD)AwtoMs() == usT);                       // a tick edge
    usN = (WORD)AwtoMs();
    AwtoClkPoke();
    while((WORD)((WORD)AwtoMs() - usN) < AWTO_CLK_WIN_TICKS);
    AwtoClkPoke();
    ulX = ((unsigned long)(AWTO_XFR(AWTO_R_WATCHDOG_CNT3_VALUE) & 0x7F) << 5 | (AWTO_XFR(AWTO_R_WATCHDOG_CNT23_VALUE) >> 3)) * 2048UL
          + (((WORD)(AWTO_XFR(AWTO_R_WATCHDOG_CNT23_VALUE) & 0x07) << 8) | AWTO_XFR(AWTO_R_WATCHDOG_CNT2_VALUE));    // crystal clocks
    g_stAwtoClk.usTickPm = (WORD)(((unsigned long)AWTO_CLK_WIN_TICKS * _EXT_XTAL * 1000UL) / ulX);
}

static unsigned long AwtoClkCrcPass(void)
{
    unsigned long ulCrc = 0xFFFFFFFFUL;
    WORD usA;
    BYTE ucB;

    for(usA = AWTO_CLK_CRC_FROM; usA < AWTO_CLK_CRC_TO; usA++)
    {
        if((usA & 0xFF) == 0)
        {
            AwtoClkPoke();
        }
        ucB = *(__code BYTE *)usA;
        ulCrc = (ulCrc >> 4) ^ tAwtoClkCrc[(BYTE)(ulCrc ^ ucB) & 0x0F];
        ulCrc = (ulCrc >> 4) ^ tAwtoClkCrc[(BYTE)(ulCrc ^ (ucB >> 4)) & 0x0F];
    }
    return ~ulCrc;
}

static unsigned long AwtoClkPm32(WORD usReg)            // 4 consecutive meter bytes, MSB first
{
    unsigned long ulV = 0;
    BYTE ucK;

    for(ucK = 0; ucK < 4; ucK++)
    {
        ulV = (ulV << 8) | AWTO_XFR(usReg + ucK);
    }
    return ulV;
}

static void AwtoClkChecks(void)
{
    unsigned long ulCrc;
    unsigned long ulT0;
    WORD usI;
    BYTE ucP;
    BYTE ucR;
    BYTE ucV;
    WORD usIt;
    BYTE ucAcc = 0;
    BYTE ucJ;

    AWTO_XFR(AWTO_R_PERFORMANCE_METER_CONTROL) = AWTO_F_PERFORMANCE_METER_CONTROL_PM_RST;
    AWTO_XFR(AWTO_R_PERFORMANCE_METER_CONTROL) = AWTO_F_PERFORMANCE_METER_CONTROL_PM_MTR_EN;
    ulT0 = AwtoMs();
    ulCrc = AwtoClkCrcPass();
    AWTO_XFR(AWTO_R_PERFORMANCE_METER_CONTROL) = 0x00;
    g_stAwtoClk.ulRef = AwtoClkPm32(AWTO_R_PERFORMANCE_METER_REF_COUNT_H);
    g_stAwtoClk.ulMiss = AwtoClkPm32(AWTO_R_PERFORMANCE_METER_MISS_COUNT_H);
    g_stAwtoClk.ulRestart = AwtoClkPm32(AWTO_R_PERFORMANCE_METER_MEM_RESTART_H);
    g_stAwtoClk.usCrcMs = (WORD)(AwtoMs() - ulT0);
    g_stAwtoClk.aucCrc[0] = (BYTE)(ulCrc >> 24);
    g_stAwtoClk.aucCrc[1] = (BYTE)(ulCrc >> 16);
    g_stAwtoClk.aucCrc[2] = (BYTE)(ulCrc >> 8);
    g_stAwtoClk.aucCrc[3] = (BYTE)ulCrc;
    g_stAwtoClk.ucCrcBad = 0;
    ucP = (g_stAwtoClk.ucPasses != 0) ? g_stAwtoClk.ucPasses : AWTO_CLK_CRC_PASSES;
    while(ucP-- > 1)
    {
        g_stAwtoClk.ucCrcBad += (AwtoClkCrcPass() != ulCrc);
    }
    g_stAwtoClk.usXdBad = 0;
    for(ucR = 0; ucR < AWTO_CLK_XD_ROUNDS; ucR++)
    {
        for(ucP = 0; ucP < 4; ucP++)
        {
            for(usI = 0; usI < AWTO_CLK_XD_N; usI++)
            {
                ucV = (ucP == 0) ? 0x55 : ((ucP == 1) ? 0xAA : ((ucP == 2) ? (BYTE)(usI + ucR) : (BYTE)(~(usI * 7 + ucR))));
                s_aucClkXd[usI] = ucV;
            }
            for(usI = 0; usI < AWTO_CLK_XD_N; usI++)
            {
                ucV = (ucP == 0) ? 0x55 : ((ucP == 1) ? 0xAA : ((ucP == 2) ? (BYTE)(usI + ucR) : (BYTE)(~(usI * 7 + ucR))));
                g_stAwtoClk.usXdBad += (s_aucClkXd[usI] != ucV);
            }
        }
        AwtoClkPoke();
    }
    ulT0 = AwtoMs();
    for(ucJ = 0; ucJ < AWTO_CLK_ALU_LOOPS; ucJ++)
    {
        for(usIt = 0; usIt < AWTO_CLK_ALU_N; usIt++)
        {
            ucAcc = (BYTE)((ucAcc << 1) ^ (BYTE)usIt ^ (ucAcc >> 7));
            if((usIt & (AWTO_CLK_ALU_POKE - 1)) == 0)
            {
                AwtoClkPoke();                              // a poke gap of 8192 iterations = 40 ms at the slowest step (WDT warning 200 ms)
            }
        }
    }
    s_ucClkSink = ucAcc;
    g_stAwtoClk.usAluMs = (WORD)(AwtoMs() - ulT0);
    ulT0 = AwtoMs();
    for(ucP = 0; ucP < AWTO_CLK_MISS_PASSES; ucP++)
    {
        WORD usA = AWTO_CLK_CRC_FROM;

        for(usI = 0; usI < AWTO_CLK_MISS_READS; usI++)
        {
            ucAcc ^= *(__code BYTE *)usA;
            usA += AWTO_CLK_LINE;
        }
        AwtoClkPoke();
    }
    s_ucClkSink = ucAcc;
    g_stAwtoClk.usMissMs = (WORD)(AwtoMs() - ulT0);
    AwtoClkTickCheck();
    AwtoClkDelayCal();
}

static void AwtoClkReadback(void)
{
    g_stAwtoClk.usRcap = ((WORD)RCAP2H << 8) | RCAP2L;
    g_stAwtoClk.ucFFED = MCU_FFED_MCU_CONTROL;
    g_stAwtoClk.ucFFE9 = MCU_FFE9_MCU_CLK_CONTROL_1;
    g_stAwtoClk.ucFFEE = MCU_FFEE_MCU_CLOCK_CONTROL;
    g_stAwtoClk.ucFF6C = AwtoClkFlashRegGet();
    g_stAwtoClk.ucDriveNow = ScalerGetByte(P10_C2_PIN_DRIVING_CTRL02__TOPON);
    g_stAwtoClk.ucSlewNow = ScalerGetByte(P10_81_PIN_SLEW_RATE_CTRL1__TOPON);
    g_stAwtoClk.ucFDA1 = MCU_FDA1_CACHE_OPTION;
    g_stAwtoClk.ucCkNow = CKCON;
    g_stAwtoClk.usDdcDeb = isr_g_usDDCDebounceCnt;
}

static void AwtoClkTimers(WORD usRcap)                  // Timer2 reload as ScalerTimerSetTimerCount
{
    ET2 = 0;
    TR2 = 0;
    TF2 = 0;
    TL2 = LOBYTE(usRcap);
    TH2 = HIBYTE(usRcap);
    RCAP2L = LOBYTE(usRcap);
    RCAP2H = HIBYTE(usRcap);
    ET2 = 1;
    TR2 = 1;
}

static void AwtoClkApply(void)
{
    BYTE ucF = g_stAwtoClk.ucF;
    BYTE ucF2 = g_stAwtoClk.ucF2;
    BYTE ucM = g_stAwtoClk.ucM;
    WORD usN;
    BYTE ucMode;
    unsigned long ulPll;

    g_stAwtoClk.ucRefuse = AWTO_CLK_REF_NONE;
    ulPll = AwtoClkPllKhz();
    g_stAwtoClk.ulPllKhz = ulPll;
    if((ucF < 1) || (ucF2 < 1) || (ucM < 1) || (ucF > AWTO_CLK_DIV_MAX) || (ucF2 > AWTO_CLK_DIV_MAX) || (ucM > AWTO_CLK_DIV_MAX))
    {
        g_stAwtoClk.ucRefuse = AWTO_CLK_REF_RANGE;
    }
    else if(g_stAwtoClk.ucState == AWTO_CLK_ST_HELD)
    {
        g_stAwtoClk.ucRefuse = AWTO_CLK_REF_BUSY;
    }
    else if(ulPll / ((WORD)ucF * ucF2) > (((g_stAwtoClk.ucFlags & AWTO_CLK_F_DUAL) != 0) ? AWTO_CLK_SPI_DUAL_KHZ : AWTO_CLK_SPI_MAX_KHZ))
    {
        g_stAwtoClk.ucRefuse = AWTO_CLK_REF_SPI;
    }
    else if(ucM > ucF2)
    {
        g_stAwtoClk.ucRefuse = AWTO_CLK_REF_RATIO;                      // MCU slower than the SPI
    }
    if(g_stAwtoClk.ucRefuse != AWTO_CLK_REF_NONE)
    {
        g_stAwtoClk.ucState = AWTO_CLK_ST_REFUSED;
        return;
    }
    if(s_ucClkSaved == 0)
    {
        s_ucClkStock[0] = (MCU_FFED_MCU_CONTROL >> 2) & 0x0F;
        s_ucClkStock[1] = MCU_FFE9_MCU_CLK_CONTROL_1 & 0x0F;
        s_ucClkStock[2] = (MCU_FFEE_MCU_CLOCK_CONTROL >> 2) & 0x0F;
        s_ucClkStock[3] = CKCON;
        s_ucClkStock[4] = AwtoClkFlashRegGet();
        s_ucClkStock[10] = MCU_FF6B_FAST_READ_OP_CODE;
        s_ucClkStock[8] = ScalerGetByte(P10_C2_PIN_DRIVING_CTRL02__TOPON);
        s_ucClkStock[9] = ScalerGetByte(P10_81_PIN_SLEW_RATE_CTRL1__TOPON);
        g_stAwtoClk.ucChip = ScalerGlobalGetIDCode();
        s_ucClkStock[5] = d_isr_g_ucDelay5usN_Base;
        s_ucClkStock[6] = d_isr_g_ucDelayXusN_Base;
        s_ucClkStock[7] = MCU_FDA1_CACHE_OPTION;
        s_usClkStockRcap = ((WORD)RCAP2H << 8) | RCAP2L;
        s_usClkStockDeb = isr_g_usDDCDebounceCnt;
        g_stAwtoClk.ucFormulaOk = (AwtoClkReload(s_ucClkStock[0], s_ucClkStock[2]) == s_usClkStockRcap);
        s_ucClkSaved = 1;
    }
    usN = (WORD)ucF * ucM;
    if(g_stAwtoClk.ucDrive != 0xFF)
    {
        ScalerSetByte(P10_C2_PIN_DRIVING_CTRL02__TOPON, (BYTE)(((g_stAwtoClk.ucDrive & 7) << 5) | ((g_stAwtoClk.ucDrive & 7) << 2) | (s_ucClkStock[8] & 0x03)));
    }
    if(g_stAwtoClk.ucSlew != 0xFF)
    {
        ScalerSetByte(P10_81_PIN_SLEW_RATE_CTRL1__TOPON, (BYTE)((s_ucClkStock[9] & 0x3F) | ((g_stAwtoClk.ucSlew != 0) ? (_BIT7 | _BIT6) : 0)));
    }
    s_ucClkWrap = ((g_stAwtoClk.ucFlags & AWTO_CLK_F_NOWRAP) != 0) ? _CKCON_MOVX_DEFAULT_CYCLE : _CKCON_MOVX_9_CYCLE;
    EA = 0;
    if(AwtoClkWrite(ucF, ucF2, ucM) == 0)
    {
        EA = 1;
        g_stAwtoClk.ucRefuse = AWTO_CLK_REF_ORDER;
        g_stAwtoClk.ucState = AWTO_CLK_ST_REFUSED;
        return;
    }
    AwtoClkTimers(AwtoClkReload(ucF, ucM));
    d_isr_g_ucDelay5usN_Base = (BYTE)(((WORD)s_ucClkStock[5] * (s_ucClkStock[0] * s_ucClkStock[2]) + usN / 2) / usN);
    d_isr_g_ucDelayXusN_Base = (BYTE)(((WORD)s_ucClkStock[6] * (s_ucClkStock[0] * s_ucClkStock[2]) + usN / 2) / usN);
    isr_g_usDDCDebounceCnt = (WORD)(((unsigned long)s_usClkStockDeb * (s_ucClkStock[0] * s_ucClkStock[2]) + usN / 2) / usN);
    if(((g_stAwtoClk.ucFlags & AWTO_CLK_F_DUAL) != 0) || (g_stAwtoClk.ucRdTune != 0xFF))
    {
        AwtoClkReadMode(s_ucClkStock[10], s_ucClkStock[4]);                 // warm the cache line with the stock values
        ucMode = (s_ucClkStock[4] & 0xC3) | (((g_stAwtoClk.ucFlags & AWTO_CLK_F_DUAL) != 0) ? 0x80 : 0x00);
        if(g_stAwtoClk.ucRdTune != 0xFF)
        {
            ucMode = (ucMode & ~0x3C) | (g_stAwtoClk.ucRdTune & 0x3C);
        }
        if((ucMode & 0xC0) == 0x80)
        {
            AwtoClkReadMode(AWTO_CLK_OP_DREAD, ucMode);
        }
        else
        {
            AwtoClkReadMode(s_ucClkStock[10], ucMode);
        }
    }
    if((g_stAwtoClk.ucFlags & AWTO_CLK_F_CKCON) != 0)
    {
        CKCON = (CKCON & ~0x07) | (g_stAwtoClk.ucCkcon & 0x07);
    }
    EA = 1;
    s_ulClkT0 = AwtoMs();
    g_stAwtoClk.ucState = AWTO_CLK_ST_HELD;
    AwtoClkChecks();
    AwtoClkReadback();
}

static void AwtoClkRevert(BYTE ucState)
{
    if(s_ucClkSaved == 0)
    {
        return;
    }
    EA = 0;
    AwtoClkReadMode(s_ucClkStock[10], s_ucClkStock[4]);
    CKCON = s_ucClkStock[3];
    AwtoClkWrite(s_ucClkStock[0], s_ucClkStock[1], s_ucClkStock[2]);
    AwtoClkTimers(s_usClkStockRcap);
    d_isr_g_ucDelay5usN_Base = s_ucClkStock[5];
    d_isr_g_ucDelayXusN_Base = s_ucClkStock[6];
    isr_g_usDDCDebounceCnt = s_usClkStockDeb;
    EA = 1;
    ScalerSetByte(P10_C2_PIN_DRIVING_CTRL02__TOPON, s_ucClkStock[8]);
    ScalerSetByte(P10_81_PIN_SLEW_RATE_CTRL1__TOPON, s_ucClkStock[9]);
    g_stAwtoClk.ucState = ucState;
    AwtoClkReadback();
}

static void AwtoClkPoll(void)
{
    BYTE ucGo = g_stAwtoClk.ucGo;

    g_stAwtoClk.usNowMs = (WORD)AwtoMs();
    g_stAwtoClk.usAstFrames = g_usAwtoAstFrames;
    g_stAwtoClk.usScFrames = g_usAwtoScFrames;
    if((g_stAwtoClk.ucState == AWTO_CLK_ST_HELD) && ((ucGo == AWTO_CLK_OP_REVERT) || ((WORD)((WORD)AwtoMs() - (WORD)s_ulClkT0) >= g_stAwtoClk.usHoldMs)))
    {
        AwtoClkRevert((ucGo == AWTO_CLK_OP_REVERT) ? AWTO_CLK_ST_REVERTED : AWTO_CLK_ST_AUTO_REVERTED);
    }
    else if(ucGo == AWTO_CLK_OP_APPLY)
    {
        AwtoClkApply();
    }
    else if(ucGo == AWTO_CLK_OP_REVERT)
    {
        g_stAwtoClk.ucState = AWTO_CLK_ST_REVERTED;
        AwtoClkReadback();
    }
    if(ucGo != 0)
    {
        g_stAwtoClk.ucSeq++;
        g_stAwtoClk.ucGo = 0;
    }
}

static void AwtoOsdHwPoll(void)
{
    BYTE ucOp = g_stAwtoOsdHw.ucGo;
    BYTE ucI;
    BYTE ucSu;
    WORD usF;
    WORD usCalls;
    unsigned long ulT0;

    AwtoClkPoll();
    g_stAwtoOsdHw.ucSaverRun = g_ucAwtoSaverRun;
    if(s_ucOhwCyOn != 0)
    {
        ucI = AwtoOhwCycleStep();
        if(ucI == AWTO_OHW_CY_S2_STOP)
        {
            AwtoScopeSaver2(0);
            AwtoOhwLadder();
            AwtoOhwLadderMap(1);
        }
        else if(ucI != 0)
        {
            AwtoScopeSaver2(ucI);                                       // called here, not deeper: the saver poll's stack depth
        }
    }
    if(ucOp == 0)
    {
        return;
    }
    g_stAwtoOsdHw.ucState = AWTO_OHW_ST_OK;
    for(ucI = 0; ucI < AWTO_OHW_REGS; ucI++)
    {
        g_stAwtoOsdHw.aucRegs[ucI] = ScalerGetByte(tAwtoOhwRegs[ucI]);
    }
    g_stAwtoOsdHw.ucOverlay = ScalerGetBit(AWTO_R_OVERLAY_CTRL, AWTO_F_OVERLAY_CTRL_OVERLAY_PORT_EN);
    AwtoOhwSeed();
    ulT0 = AwtoMs();
    if((ucOp == AWTO_OHW_OP_WRITE) || (ucOp == AWTO_OHW_OP_WRBUF) || (ucOp == AWTO_OHW_OP_VERIFY) || (ucOp == AWTO_OHW_OP_READ) || (ucOp == AWTO_OHW_OP_CRC))
    {
        ScalerOsdCircuitActivated(_ENABLE);             // SRAM access needs the OSD circuit on (docs/osd/timing.md); no-op when on
        ScalerSetBit(AWTO_R_OSD_MISC_PORT, ~AWTO_F_OSD_MISC_PORT_DB_ENABLE, 0x00);
        if((ucOp != AWTO_OHW_OP_WRITE) && (ucOp != AWTO_OHW_OP_WRBUF))
        {
            ucSu = ScalerGetByte(AWTO_R_OSD_SU_CRTL);
            if((g_stAwtoOsdHw.ucFlags & AWTO_OHW_F_RD_OVL) == 0)
            {
                AwtoOhwOverlay(0);
            }
            if((g_stAwtoOsdHw.ucFlags & AWTO_OHW_F_RD_SU) != 0)
            {
                ScalerSetByte(AWTO_R_OSD_SU_CRTL, AWTO_OSD_ZERO);
            }
            ScalerOsdCircuitActivated(_DISABLE);        // as ScalerOsdSramGetData: circuit off, one DVS, then read
            ScalerTimerWaitForEvent(_EVENT_DVS);
            AwtoOhwVerify(ucOp);
            ScalerOsdCircuitActivated(_ENABLE);
            ScalerSetByte(AWTO_R_OSD_SU_CRTL, ucSu);
        }
        else
        {
            if((g_stAwtoOsdHw.ucFlags & AWTO_OHW_F_HIDE) != 0)
            {
                AwtoOhwOverlay(0);
            }
            if(ucOp == AWTO_OHW_OP_WRITE)
            {
                AwtoOhwWrite();
            }
            else
            {
                ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, g_stAwtoOsdHw.usAddr, _OSD_WITHOUT_DB);
                AwtoOhwPut((g_stAwtoOsdHw.usN > AWTO_OHW_BUF) ? AWTO_OHW_BUF : (BYTE)g_stAwtoOsdHw.usN);
            }
        }
        AwtoOhwOverlay(g_stAwtoOsdHw.ucOverlay);
        ScalerSetBit(AWTO_R_OSD_WRITE_OPTION, ~(AWTO_F_OSD_WRITE_OPTION_BYTESEL | AWTO_F_OSD_WRITE_OPTION_SRAM_SEL), 0x00);
    }
    else if(ucOp == AWTO_OHW_OP_PLANES)
    {
        AwtoOhwPlanes();
    }
    else if(ucOp == AWTO_OHW_OP_S2FRAMES)                   // finish the current Scope 2 frame + usN more (poll held); inline: the saver poll's stack depth
    {
        if(g_ucAwtoSaverRun != AWTO_OHW_RUN_SCOPE2)
        {
            g_stAwtoOsdHw.ucState = AWTO_OHW_ST_NO_S2;
        }
        for(usF = 0; (g_stAwtoOsdHw.ucState == AWTO_OHW_ST_OK) && (usF <= g_stAwtoOsdHw.usN); usF++)
        {
            for(usCalls = 0; AwtoScopeSaver2(AWTO_OHW_S2_DRAW) == 0; usCalls++)
            {
                if(usCalls >= AWTO_OHW_S2_CALLS)
                {
                    g_stAwtoOsdHw.ucState = AWTO_OHW_ST_LIMIT;
                    break;
                }
            }
        }
    }
    else if(ucOp == AWTO_OHW_OP_LADDER)
    {
        AwtoOhwLadder();
    }
    else if(ucOp == AWTO_OHW_OP_CYCLE)
    {
        s_ucOhwCyOn = (g_stAwtoOsdHw.usN != 0);
        if(s_ucOhwCyOn != 0)
        {
            AwtoOhwLadder();
            s_ucOhwCyVar = AWTO_OHW_V_SCOPE2;                           // the first step goes on to variant 1
            s_ulOhwCyT0 = AwtoMs() - AWTO_OHW_CY_MS;
            s_usOhwCyPos = 0;
            g_stAwtoOsdHw.usBad = 0;
        }
    }
    else if(ucOp == AWTO_OHW_OP_SAVER)
    {
        set_ap_screensaver_now(0, (int)g_stAwtoOsdHw.usN);    // served by the next saver poll; the host waits for ucSaverRun before a hold
    }
    else if(ucOp != AWTO_OHW_OP_REGS)
    {
        g_stAwtoOsdHw.ucState = AWTO_OHW_ST_BAD_OP;
    }
    if(ucOp != AWTO_OHW_OP_WRITE)
    {
        g_stAwtoOsdHw.usMs = (WORD)(AwtoMs() - ulT0);
    }
    g_stAwtoOsdHw.usFrame = g_usAwtoS2Frame;
    g_stAwtoOsdHw.ucSeq++;
    g_stAwtoOsdHw.ucGo = 0;
}
#endif

// #165 step 2: memory work mode for the current timing; one sync line per request (E3), one per resulting select change
static void AwtoMemForce(BYTE ucOn)
{
#if(_FRC_SUPPORT == _OFF)
    if(ucOn != 0)
    {
        AwtoSyncPush(AWTO_SYNC_EV_MEM, AWTO_MEM_LOG_NO_FRC, 0);
        return;
    }
#endif
    if(ucOn == g_ucAwtoMemForce)
    {
        AwtoSyncPush(AWTO_SYNC_EV_MEM, (ucOn != 0) ? AWTO_MEM_LOG_ALREADY_FORCED : AWTO_MEM_LOG_ALREADY_SDK, 0);
        return;
    }
    g_ucAwtoMemForce = ucOn;
    if(SysModeGetModeState() != _MODE_STATUS_ACTIVE)
    {
        AwtoSyncPush(AWTO_SYNC_EV_MEM, AWTO_MEM_LOG_STORED, ucOn);
        return;
    }
    AwtoSyncPush(AWTO_SYNC_EV_MEM, (ucOn != 0) ? AWTO_MEM_LOG_FORCE : AWTO_MEM_LOG_RELEASE, 0);
    g_ucAwtoMstepN = 0;                                 // log the M-domain steps of this set-up too
    SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_DISPLAY_SETTING, AWTO_SYS_BY_MEMTEST);
}

static __xdata unsigned int s_usAwtoHoldCancel;  // usT2Isr at the last OSD_DISABLE cancel

// test cmd 0x3A: demo log, AWTO_DEMO_LINES lines AWTO_DEMO_MS apart (Dan 2026-11-13: console scroll / wrap): "line N test 1234567890...",
// short / medium / long in turn (the long one wraps)
#define AWTO_DEMO_LINES                         100
#define AWTO_DEMO_MS                            5
static __xdata unsigned char s_ucAwtoDemoN;     // lines still to push (0 = idle: XDATA is zeroed at boot)
static __xdata unsigned int s_usAwtoDemoAt;     // AwtoMs() of the last push

// Does a direct scaler register access change MCU_FFF4_SCA_INF_ADDR (the "Burst Write Bug" backup in every ISR)?
#define AWTO_TC_FFF4_PROBE                      0x35
#define AWTO_FFF4_MARK                          0xA5    // a value no probed register's low address byte has
#define AWTO_FFF4_DONE                          0x5A    // [6]: the probe ran
__xdata BYTE g_pucAwtoFff4Probe[8];             // [0] FFF4 at entry, [1] after writing the mark, [2] after a P0_01 read,
                                                // [3] after a P0_02 read, [4] after a P3A_18 same-value write, [5] FFF3, [6] AWTO_FFF4_DONE
static void AwtoFff4Probe(void)
{
    BYTE ucSave = MCU_FFF4_SCA_INF_ADDR;
    BYTE ucV;

    EA = 0;
    g_pucAwtoFff4Probe[0] = ucSave;
    MCU_FFF4_SCA_INF_ADDR = AWTO_FFF4_MARK;
    g_pucAwtoFff4Probe[1] = MCU_FFF4_SCA_INF_ADDR;
    ucV = ScalerGetByte(AWTO_R_HOST_CTRL);
    g_pucAwtoFff4Probe[2] = MCU_FFF4_SCA_INF_ADDR;
    ucV = ScalerGetByte(AWTO_R_STATUS0);
    g_pucAwtoFff4Probe[3] = MCU_FFF4_SCA_INF_ADDR;
    ucV = ScalerGetByte(AWTO_R_FRAME_CTRL_18);
    ScalerSetByte(AWTO_R_FRAME_CTRL_18, ucV);
    g_pucAwtoFff4Probe[4] = MCU_FFF4_SCA_INF_ADDR;
    g_pucAwtoFff4Probe[5] = MCU_FFF3_SCA_INF_CONTROL;
    MCU_FFF4_SCA_INF_ADDR = ucSave;
    EA = 1;
    g_pucAwtoFff4Probe[6] = AWTO_FFF4_DONE;
}

#ifdef _AWTO_PROBES
// Reserved opcode 0xA5 on the DW8051 (fw/sdcc/a5_probe.asm): 4 cases x 20 B capture + the two bytes DPTR0 / DPTR1 point at
#define AWTO_TC_A5_PROBE                        0x21
#define AWTO_A5_MARK0                           80      // a5_probe.asm MARK0 / MARK1
#define AWTO_A5_VAL0                            0xC0
#define AWTO_A5_VAL1                            0xC1
__xdata BYTE g_pucAwtoA5Probe[AWTO_A5_MARK0 + 2];
extern void AwtoA5Run0(void);
extern void AwtoA5Run1(void);
extern void AwtoA5Run2(void);
extern void AwtoA5Run3(void);

static void AwtoA5Probe(void)
{
    BYTE ucI;

    for(ucI = 0; ucI < AWTO_A5_MARK0; ucI++)
    {
        g_pucAwtoA5Probe[ucI] = 0;
    }
    g_pucAwtoA5Probe[AWTO_A5_MARK0] = AWTO_A5_VAL0;
    g_pucAwtoA5Probe[AWTO_A5_MARK0 + 1] = AWTO_A5_VAL1;
    EA = 0;
    AwtoA5Run0();
    AwtoA5Run1();
    AwtoA5Run2();
    AwtoA5Run3();
    EA = 1;
}
#endif

static void AwtoDemoLog(void)                   // each main pass while lines are left
{
    if((s_ucAwtoDemoN == 0) || ((unsigned int)((WORD)AwtoMs() - s_usAwtoDemoAt) < AWTO_DEMO_MS))
    {
        return;
    }
    s_usAwtoDemoAt = (WORD)AwtoMs();
    s_ucAwtoDemoN--;
    AwtoSyncPush(AWTO_SYNC_EV_DEMO, 1 + (s_ucAwtoDemoN % 3), AWTO_DEMO_LINES - s_ucAwtoDemoN);     // line 1..100
}

void AwtoDiagTestCmd(void)
{
    unsigned char ucCmd = isr_g_stAwtoDiag.ucHold;

    if((ucCmd != 0) && ((unsigned int)((WORD)AwtoMs() - s_usAwtoHoldCancel) >= AWTO_KEY_REFRESH_MS))
    {
        s_usAwtoHoldCancel = (WORD)AwtoMs();                       // pending pop-up timeout (each draw re-arms it; seconds):
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);      // every 80 ms, not every pass (a cancel walks the timer table)
    }
    AwtoDemoLog();
    AwtoPmSoundPoll();
#ifdef _AWTO_OSD_HWTEST
    AwtoOsdHwPoll();
    if((g_stAwtoOsdHw.ucFlags & AWTO_OHW_F_HOLD) == 0)
#endif
    AwtoSaverPoll();
    ucCmd = isr_g_stAwtoDiag.ucTestCmd;
    if(ucCmd == 0)
    {
        return;
    }
    isr_g_stAwtoDiag.ucTestCmd = 0;
    if((ucCmd == AWTO_TC_QC_OSD) || (ucCmd == AWTO_TC_QC_OSD + 1))     // #227 Realtek QC OSD pattern (0xB0.. is the probe-columns range below)
    {
        AwtoQcOsd(ucCmd == AWTO_TC_QC_OSD);
    }
    else if((ucCmd == AWTO_TC_DPG) || (ucCmd == AWTO_TC_DPG + 1))
    {
        AwtoDpgTest(ucCmd == AWTO_TC_DPG);
    }
    else if((ucCmd >= AWTO_TC_PACMAN) && (ucCmd <= AWTO_TC_PACMAN + 2))
    {
        AwtoPacmanClassic((ucCmd == AWTO_TC_PACMAN) ? 1 : ((ucCmd == AWTO_TC_PACMAN + 1) ? 2 : 0));
    }
    else if((ucCmd >= AWTO_TC_SCOPE) && (ucCmd <= AWTO_TC_SCOPE + 2))
    {
        AwtoScopeSaver((ucCmd == AWTO_TC_SCOPE) ? 1 : ((ucCmd == AWTO_TC_SCOPE + 1) ? 2 : 0));
    }
    else if((ucCmd >= AWTO_TC_PACMAN_SND) && (ucCmd <= AWTO_TC_PACMAN_SND + 5))   // Pac-Man sound (0xB7..0xB9 are the full-screen Pac-Man)
    {
        AwtoPmSound(ucCmd - AWTO_TC_PACMAN_SND);
    }
    else if((ucCmd >= AWTO_TC_OSD_DEMO) && (ucCmd <= AWTO_TC_OSD_DEMO + 5))   // #226 OSD window demo (first: 0xC0.. is the probe-columns range below)
    {
        AwtoOsdDemo(ucCmd - AWTO_TC_OSD_DEMO);
    }
    else if(ucCmd <= 5)
    {
        AwtoKeyInject(ucCmd - 1);                       // routed by the next AwtoKeyPoll (#129)
    }
    else if((ucCmd == 0x41) || (ucCmd == 0x42))         // #39 key test screen: 41 open, 42 close
    {
        AwtoKeyTestSet(ucCmd == 0x41);
    }
    else if((ucCmd == 0x43) || (ucCmd == 0x44))         // console GPIO page: open / close the console
    {
        AwtoGpioTestSet(ucCmd == 0x43);
    }
    else if(ucCmd == 0x45)                              // limit probe: open with the stored line count (default 24) / 0x46 close
    {
        AwtoProbeSet((g_ucAwtoProbeLines != 0) ? g_ucAwtoProbeLines : 24);
    }
    else if(ucCmd == 0x46)
    {
        AwtoProbeSet(0);
    }
#if(_AWTO_WDT == _ON)
    else if((ucCmd >= 0x4C) && (ucCmd <= 0x4E))         // #131 watchdog test hangs: 4C spin, 4E spin with EA off (4D gone, #138)
    {
        AwtoWdtHang(ucCmd - 0x4C);
    }
    else if((ucCmd == 0x49) || (ucCmd == 0x4F))         // #138 WDT probe for unit 2: 49 normal mode, 4F timer mode
    {
        AwtoWdtProbe(ucCmd == 0x4F);
    }
    else if((ucCmd >= 0x2A) && (ucCmd <= 0x2F))         // #138 Timer0 events: 2A DP rebuild 30 ms, 2B/2C HDMI RR D2/D3 10 ms,
    {                                                   // 2D 2A+2B, 2E/2F = 2A/2B across a forced clock-switch reload
        AwtoT0EvTest(ucCmd - 0x2A);
    }
    else if((ucCmd >= 0x5A) && (ucCmd <= 0x5C))         // 5A/5B = 2A/2B at the PS reload, 5C three out of order + cancel
    {
        AwtoT0EvTest(ucCmd - 0x5A + 6);
    }
    else if(ucCmd == 0x24)                              // stuck Timer0 handler
    {
        AwtoT0EvTest(9);
    }
    else if((ucCmd == 0x25) || ((ucCmd >= 0x5D) && (ucCmd <= 0x5F)))   // EXINT0 hook: 25 off, 5D arm, 5E 2 ms spin, 5F stuck
    {
        isr_g_ucAwtoT0Test = (ucCmd == 0x25) ? 0 : (ucCmd - 0x5C);
    }
#endif
    else if((ucCmd >= 0x60) && (ucCmd <= 0x6F))         // diagnostic screen font: 0x60 + font index (osd_font_load)
    {
        g_ucAwtoDiagFont = ucCmd - 0x60 + 1;
    }
    else if((ucCmd == 0x4A) || (ucCmd == 0x4B))         // diagnostic screens at 1x / 2x size
    {
        g_ucAwtoDiagSmall = (ucCmd == 0x4A);
    }
    else if(ucCmd == 0x47)                              // scroll down one row (console; the limit probe steps on)
    {
        AwtoConScroll(1);
        AwtoProbeScroll(0);
    }
    else if(ucCmd == 0x48)                              // scroll up one row (console; the limit probe goes back to 0)
    {
        AwtoConScroll(-1);
        AwtoProbeScroll(1);
    }
    else if(ucCmd >= 0xC0)                              // 0xC0 + n: probe columns = 4 * n (0xE8 = 160)
    {
        g_ucAwtoProbeCols = (ucCmd - 0xC0) << 2;
    }
    else if(ucCmd >= 0x80)                              // 0x80 + n: probe with n lines (n = 1..63)
    {
        g_ucAwtoProbeLines = ucCmd - 0x80;
        AwtoProbeSet(g_ucAwtoProbeLines);
    }
    else if((ucCmd >= 0x50) && (ucCmd <= 0x59))         // every compiled user-visible OSD message, held for review
    {
        OsdDispOsdMessage((EnumOSDDispMsg)(ucCmd - 0x50));
        isr_g_stAwtoDiag.ucHold |= AWTO_HOLD_POPUP;
    }
    else if((ucCmd == 0x20) || (ucCmd == 0x26))         // debug pop-up: the diagnostic console
    {
        AwtoDiagConsole(1);
        g_ucAwtoConAuto = 0;
    }
    else if(ucCmd == 0x3A)                              // demo log on the console (AwtoDemoLog)
    {
        AwtoDiagConsole(1);
        g_ucAwtoConAuto = 0;
        s_ucAwtoDemoN = AWTO_DEMO_LINES;
        s_usAwtoDemoAt = (WORD)AwtoMs();
    }
    else if(ucCmd == 0x27)
    {
        unsigned char ucWas = isr_g_stAwtoDiag.ucHold;

        AwtoDiagConsole(0);

        isr_g_stAwtoDiag.ucHold = 0;                     // first: OsdDispDisableOsd is blocked while a hold is set
        if((ucWas & AWTO_HOLD_POPUP) != 0)
        {
            OsdDispDisableOsd();
        }
    }
    else if((ucCmd >= 0x31) && (ucCmd <= 0x33))      // #60 switch to D1/D2/D3, fixed port, as VCP 0x60 (RTD2014Ddcci.c)
    {
        AwtoInputSelect(_D0_INPUT_PORT + (ucCmd - 0x30), ucCmd);     // fw/ddcci/ddcci.c, shared with VCP 0x60
    }
    else if((ucCmd == 0x22) || (ucCmd == 0x23))      // #56: on-screen message log on / off
    {
        g_ucAwtoMsgLog = (ucCmd == 0x22);
    }
#if(_DEBUG_MESSAGE_SUPPORT == _ON)
    else if((ucCmd == 0x28) || (ucCmd == 0x29))      // #74: debug messages on / off; stored by the #151 gate
    {
#ifdef _AWTO_NEW_SETTINGS
        extern unsigned char set_put(unsigned char ucId, int iV, unsigned char ucNow);
        set_put(AWTO_SET_DEBUG_MSGS, (ucCmd == 0x28), 1);
#else
        g_stOSDUserData.b1AwtoMsgOn = (ucCmd == 0x28);
        g_ucAwtoMsgOn = (ucCmd == 0x28);
        SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
#endif
    }
#endif
#if(_AWTO_WAKE_HOLD == _ON)
    else if((ucCmd >= 0x36) && (ucCmd <= 0x39))      // #78 power levels: 36 defaults, 37 L1 off (SDK path), 38 L2 off,
    {                                                // 39 L2 after 5 s (tests); L3 folded into the no-signal timers (#162)
        g_stAwtoPower.ucL1 = (ucCmd != 0x37);
        g_stAwtoPower.ucL2 = (ucCmd != 0x38);
        g_stAwtoPower.usL2Sec = (ucCmd == 0x39) ? 5 : AWTO_L2_SEC;
    }
#endif
#ifdef _AWTO_NEW_SETTINGS
    else if((ucCmd >= AWTO_TC_PORT_OFF) && (ucCmd < AWTO_TC_PORT_ON + 3))   // #81: 06..08 disable D1..D3, 09..0B enable (registry)
    {
        extern unsigned char set_put(unsigned char ucId, int iV, unsigned char ucNow);
        set_put(AWTO_SET_D1_ENABLE + ((ucCmd - AWTO_TC_PORT_OFF) % 3), (ucCmd >= AWTO_TC_PORT_ON), 1);
    }
    else if(ucCmd == 0x40)                              // #67 every settings-registry row to its default (recovery)
    {
        extern void set_defaults(void);
        set_defaults();
    }
    else if(ucCmd == 0x3D)                              // #151 test: one real item write now (inert aux row kvm_prefill toggled)
    {
        extern void AwtoNvTestWrite(void);
        AwtoNvTestWrite();
    }
#endif
    else if(ucCmd == 0x3E)                              // #151 test: the POWER key (soft off / on; off flushes the store)
    {
        if(SysMachineOffOrGoing() == _TRUE)
        {
            SET_OSD_STATE(_MENU_NONE);
            SysMachineRequest(_POWER_STATUS_NORMAL, AWTO_SYS_BY_TESTCMD);
        }
        else
        {
            SysMachineRequest(_POWER_STATUS_OFF, AWTO_SYS_BY_TESTCMD);
        }
    }
    else if((ucCmd == AWTO_TC_MEM_FRAME) || (ucCmd == AWTO_TC_MEM_SDK))   // #165 frame buffer forced / SDK choice
    {
        AwtoMemForce(ucCmd == AWTO_TC_MEM_FRAME);
    }
    else if(ucCmd == AWTO_TC_HOST_TIME)                // #157 host time over the debug link (DDC/CI is off while it is on)
    {
        AwtoHtSync(isr_g_stAwtoHt.aucPend);
    }
    else if(ucCmd == AWTO_TC_STACK_DEEP)                // stack canary test: deep recursion; the next main pass shows the fatal box
    {
        extern void AwtoStackDeepTest(void);
        AwtoStackDeepTest();
    }
#ifdef _AWTO_PROBES
    else if(ucCmd == AWTO_TC_OSD_SRAM_PROBE)            // #226 OSD SRAM markers from the MCU
    {
        AwtoOsdSramProbe();
    }
    else if(ucCmd == AWTO_TC_A5_PROBE)                  // reserved opcode 0xA5 (a5_probe.asm)
    {
        AwtoA5Probe();
    }
#endif
    else if(ucCmd == AWTO_TC_FFF4_PROBE)                // FFF4 vs direct scaler access
    {
        AwtoFff4Probe();
    }
    else if(ucCmd == 0x34)                              // #78 arm the switch log only (wake / power-level timing)
    {
        AwtoSwArm(SysSourceGetInputPort());
    }
#if(_AWTO_DBG_SWAP == _ON)
    else if((ucCmd == 0x3B) || (ucCmd == 0x3C))         // #79 debug link: 3B back to DDC/CI now, 3C on until told back
    {
        AwtoDbgLinkStart((ucCmd == 0x3C) ? 0xFF : 0);
    }
#endif
    else if(ucCmd == 0x30)                              // #60 back to auto search in group (NVRAM default), no switch
    {
        AwtoSwEvent(AWTO_SW_EV_CMD, ucCmd);
        SysSourceSetScanType(_SOURCE_SWITCH_AUTO_IN_GROUP);
    }
    else if((ucCmd >= 0x10) && (ucCmd <= 0x1F))         // OSD events 0..15 (#53.17); 0x20..0x22 are commands
    {
        SET_OSD_EVENT_MESSAGE(ucCmd - 0x10);
    }
    else if((ucCmd >= 0x70) && (ucCmd <= (0x70 + _OSDEVENT_SAVE_NVRAM_OSDSIXCOLORDATA_MSG - 16)))   // OSD events 16..last (#113)
    {
        SET_OSD_EVENT_MESSAGE(ucCmd - 0x70 + 16);
    }
}
