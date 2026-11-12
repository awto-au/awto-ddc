// AWTO user-facing OSD screens on the awto text layer (awto_dbgpop.inc helpers, menu font and colours), inserted into
// RTD2014OsdDisplay.c after awto_dbgpop.inc. The SDK timers and OSD states drive them as before; only the drawing is ours.
// - Message cards (#124): OsdDispOsdMessage (the SDK body is removed by keil2sdcc), incl. the DOWN / ACTIVE input-info card.
// - Source selector (#134): one row per board port + Auto.
#if((_AWTO_DIAG != _ON) || !defined(_AWTO_NEW_SETTINGS))
#error "awto_osdcard.inc draws on the awto text layer (awto_dbgpop.inc, _AWTO_NEW_SETTINGS)"
#endif
#if((_FREEZE_SUPPORT == _ON) || (_DP_MST_SUPPORT == _ON))
#error "awto_osdcard.inc: no card text for the freeze / DP MST messages"
#endif

// Board ports from the PCB config (type = port << 4 | kind). ui_port_state (glue.inc) knows D1..D3 only.
#if((_D0_INPUT_PORT_TYPE != _D0_NO_PORT) || (_D4_INPUT_PORT_TYPE != _D4_NO_PORT) || (_D5_INPUT_PORT_TYPE != _D5_NO_PORT) || (_D6_INPUT_PORT_TYPE != _D6_NO_PORT))
#error "source selector: ui_port_state (glue.inc) covers D1..D3 only"
#endif
extern BYTE ui_port_state(BYTE ucI);
static const __code BYTE tAwtoSrcType[] = {
#if(_D1_INPUT_PORT_TYPE != _D1_NO_PORT)
    _D1_INPUT_PORT_TYPE,
#endif
#if(_D2_INPUT_PORT_TYPE != _D2_NO_PORT)
    _D2_INPUT_PORT_TYPE,
#endif
#if(_D3_INPUT_PORT_TYPE != _D3_NO_PORT)
    _D3_INPUT_PORT_TYPE,
#endif
};
#define AWTO_SRC_PORTS      ((BYTE)sizeof(tAwtoSrcType))
#define AWTO_CARD_COLS      28                  // text cells per card row
#define AWTO_CARD_ROW0      2                   // first body row: title, one blank row, then the body
#define AWTO_SRC_STATE_COL  15                  // selector: port state column
#define AWTO_SRC_ROW0       AWTO_CARD_ROW0
#define AWTO_INFO_VAL_COL   13                  // info card: value column
#define AWTO_WIN_FRAME      0                   // window ids as the awto menu (awto-rtdfw ui.c)
#define AWTO_WIN_INSET      1
#define AWTO_WIN_TITLE      2
#define AWTO_WIN_HL         5
#define AWTO_T_STYLE_DIM    1

// Fixed texts: one table, read only by AwtoCardTxt (a constant read through a pointer sits in its reader's bank, awto-sdcc#39).
#define AWTO_CT_INPUT       0
#define AWTO_CT_AUTO        1
#define AWTO_CT_DP          2
#define AWTO_CT_HDMI        3
#define AWTO_CT_PORT        4
#define AWTO_CT_STATE       5                   // + ui_port_state: no cable, no signal, ready, ACTIVE
#define AWTO_CT_AWTO        9
#define AWTO_CT_NOSIGNAL    10
#define AWTO_CT_NOCABLE     11
#define AWTO_CT_NOSUPPORT   12
#define AWTO_CT_AUTOADJ     13
#define AWTO_CT_AUTOCOL     14
#define AWTO_CT_DDCCI       15
#define AWTO_CT_PSAVE       16
#define AWTO_CT_PANEL       17
#define AWTO_CT_ON          18                  // + 1 = Off
#define AWTO_CT_INFO        20
#define AWTO_CT_RES         21
#define AWTO_CT_REFRESH     22
#define AWTO_CT_HFREQ       23
#define AWTO_CT_PCLK        24
#define AWTO_CT_HDCP        25
#define AWTO_CT_DPLINK      26
#define AWTO_CT_SWING       27
#define AWTO_CT_STATUS      28
#define AWTO_CT_HZ          29                  // + 1 kHz, + 2 MHz
#define AWTO_CT_OFF         32
#define AWTO_CT_SINK        33                  // + 1 = repeater
#define AWTO_CT_LANES       35
#define AWTO_CT_RBR         36                  // + 1 HBR, + 2 HBR2
#define AWTO_CT_STAGE       39                  // + AWTO_SYNC_ST_* (#139)
#define AWTO_CT_HBR3        53
#define AWTO_CT_SYNCLOG     54
#define AWTO_CT_NOLINK      55
#define AWTO_CT_TMDS        56
#define AWTO_CT_SAVING      57
static const __code char tAwtoCardS[] =
    "Input\0Auto select\0DisplayPort\0HDMI \0Input D\0no cable\0no signal\0ready\0ACTIVE\0"
    "AWTO\0No signal\0No cable\0Not supported\0Auto adjust\0Auto colour\0DDC/CI on \0Power saving\0Panel uniformity\0On\0Off\0"
    "Information\0Resolution\0Refresh\0H frequency\0Pixel clock\0HDCP\0DP link\0Swing/pre\0Status\0"
    " Hz\0 kHz\0 MHz\0off\0 sink\0 repeater\0 lanes \0RBR\0HBR\0HBR2\0"
    "idle\0search\0scan\0stable\0measure\0timing ok\0display set\0active\0no signal\0no support\0sleep\0off\0fast path\0init\0"
    "HBR3\0Sync log\0no link\0TMDS \0Saving to memory\0";

static void AwtoCardTxt(BYTE ucI)               // appends text ucI to the composed row (AwtoPut*)
{
    const __code char *pc = tAwtoCardS;

    while(ucI != 0)
    {
        if(*pc++ == 0)
        {
            ucI--;
        }
    }
    while(*pc != 0)
    {
        AwtoPutChar(*pc++);
    }
}

// Card frame in the awto menu look (blue frame + title bar on white, the menu font), centred, title drawn; the OSD stays off.
static void AwtoCardOpenW(BYTE ucCols, BYTE ucLines, BYTE ucTitle)
{
    WORD usW, usH;

    osd_tc_open(ucCols, ucLines);
    osd_font_load(ui_font_selected());
    usW = (WORD)ucCols * osd_cw;
    usH = (WORD)ucLines * osd_rh;
    osd_tc_bar(AWTO_WIN_FRAME, 0, 0, usW - 1, usH - 1, 1);
    osd_tc_bar(AWTO_WIN_INSET, 2, 2, usW - 3, usH - 3, 0);
    osd_tc_bar(AWTO_WIN_TITLE, 2, 2, usW - 3, osd_rh - 1, 1);
    osd_tc_place(50, 50, GET_OSD_NVRAM_DOUBLE_SIZE());
    s_ucPanelRow = 0;
    s_ucPanelCol = 0;
    s_ucAwtoCols = ucCols;
    s_pcAwtoRow[0] = ' ';
    s_ucAwtoLen = 1;
    AwtoCardTxt(ucTitle);
    AwtoTextLine(0, AWTO_T_STYLE_ONACC);
}

static void AwtoCardOpen(BYTE ucLines, BYTE ucTitle)
{
    AwtoCardOpenW(AWTO_CARD_COLS, ucLines, ucTitle);
}

static void AwtoCardShow(void)
{
    ScalerTimerWaitForEvent(_EVENT_DEN_STOP);
    OsdFuncEnableOsd();                         // not osd_tc_show: that would flag the awto menu as open
}

static void AwtoCardCentre(BYTE ucLine, BYTE ucStyle)   // the composed text, centred on the row
{
    BYTE ucN = s_ucAwtoLen - 1;
    BYTE ucShift = (ucN < AWTO_CARD_COLS - 1) ? ((AWTO_CARD_COLS - ucN) / 2 - 1) : 0;
    BYTE ucI;

    for(ucI = ucN; ucI != 0; ucI--)
    {
        s_pcAwtoRow[ucI + ucShift] = s_pcAwtoRow[ucI];
    }
    for(ucI = 1; ucI <= ucShift; ucI++)
    {
        s_pcAwtoRow[ucI] = ' ';
    }
    s_ucAwtoLen = ucN + 1 + ucShift;
    AwtoTextLine(ucLine, ucStyle);
}

//---- source selector (#134) ----
static BYTE AwtoSrcPort(BYTE ucI)               // selector row 1..n -> input port
{
    return tAwtoSrcType[ucI - 1] >> 4;
}

static BYTE AwtoSrcItem(BYTE ucPort)            // input port -> OSD input item (_OSD_INPUT_D*)
{
    return ucPort - _D0_INPUT_PORT + _OSD_INPUT_D0;
}

static BYTE AwtoSrcSel(void)                    // OSD input item -> selector row (0 = Auto)
{
    BYTE ucI;

    for(ucI = 1; ucI <= AWTO_SRC_PORTS; ucI++)
    {
        if(AwtoSrcItem(AwtoSrcPort(ucI)) == GET_OSD_INPUT_PORT_OSD_ITEM())
        {
            return ucI;
        }
    }
    return 0;
}

static void AwtoPortName(BYTE ucPort)          // "DisplayPort", "HDMI n" (n-th HDMI port of the board), else "Input Dn"
{
    BYTE ucI, ucHdmi = 0;

    for(ucI = 1; ucI <= AWTO_SRC_PORTS; ucI++)
    {
        if((tAwtoSrcType[ucI - 1] & 0x0F) == _PORT_HDMI)
        {
            ucHdmi++;
        }
        if(AwtoSrcPort(ucI) == ucPort)
        {
            if((tAwtoSrcType[ucI - 1] & 0x0F) == _PORT_DP)
            {
                AwtoCardTxt(AWTO_CT_DP);
                return;
            }
            if((tAwtoSrcType[ucI - 1] & 0x0F) == _PORT_HDMI)
            {
                AwtoCardTxt(AWTO_CT_HDMI);
                AwtoPutNum(ucHdmi, 1);
                return;
            }
            break;
        }
    }
    AwtoCardTxt(AWTO_CT_PORT);
    AwtoPutNum(ucPort - _D0_INPUT_PORT, 1);
}

static bit AwtoPortIsDp(BYTE ucPort)
{
    BYTE ucI;

    for(ucI = 1; ucI <= AWTO_SRC_PORTS; ucI++)
    {
        if(AwtoSrcPort(ucI) == ucPort)
        {
            return ((tAwtoSrcType[ucI - 1] & 0x0F) == _PORT_DP);
        }
    }
    return 0;
}

static void AwtoSrcSet(BYTE ucI)
{
    SET_OSD_INPUT_PORT_OSD_ITEM((ucI == 0) ? _OSD_INPUT_AUTO : AwtoSrcItem(AwtoSrcPort(ucI)));
}

//---- #139 per-port live status + sync log pane ----
// Layout (AWTO_SRC_COLS wide): Auto; per port 3 lines: name + state, signals (fw/awto/portsig.tsv), stage + rate; the log.
#define AWTO_SRC_COLS       46
#define AWTO_SRC_STAGE_COL  3                   // line 3: sync stage
#define AWTO_SRC_RATE_COL   15                  // line 3: rate (timing / TMDS clock / DP link)
#define AWTO_SRC_RATE_W     (AWTO_SRC_COLS - AWTO_SRC_RATE_COL - 1)
#define AWTO_SRC_LOGN       8                   // log pane lines
#define AWTO_SRC_PROW(i)    (AWTO_SRC_ROW0 + 1 + ((i) - 1) * 3)   // port item i (1..n): first line
#define AWTO_SRC_LOGHDR     (AWTO_SRC_PROW(AWTO_SRC_PORTS) + 4)
#define AWTO_SRC_LINES      (AWTO_SRC_LOGHDR + 1 + AWTO_SRC_LOGN + 1)     // + pad row (the frame covers the last 2 px)
#define AWTO_PS_SRC_IN      0
#define AWTO_PS_SRC_CNT     1
#define AWTO_PS_SRC_XREG    2
#define AWTO_PS_SRC_CABLE   3
#define AWTO_PS_SRC_DDC     4
#define AWTO_PS_SRC_TMDS    5

// GENERATED-BEGIN awto_port_sigs
#define AWTO_PS_N 16
static const __code BYTE tAwtoPsPort[16] = {
    0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2};
static const __code BYTE tAwtoPsSrc[16] = {
    3, 0, 0, 0, 1, 4, 3, 0, 0, 5, 4, 3, 0, 0, 5, 4};
static const __code WORD tAwtoPsA[16] = {0x0000, 0x0019, 0x001D, 0x001E, 0x0000, 0x0000, 0x0000, 0x001B, 0x0018, 0x0071, 0x0000, 0x0000, 0x001A, 0x0017, 0x0072, 0x0000};
static const __code BYTE tAwtoPsB[16] = {
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00};
static const __code BYTE tAwtoPsCol[16] = {
    6, 11, 16, 21, 27, 36, 6, 10, 15, 21, 26, 6, 10, 15, 21, 26};
static const __code BYTE tAwtoPsLblCol[16] = {
    3, 8, 13, 18, 23, 33, 3, 8, 12, 17, 23, 3, 8, 12, 17, 23};
static const __code char tAwtoPsLblS[] = "cbl\0" "hpd\0" "p15\0" "p16\0" "p17\0" "ddc\0" "cbl\0" "5V\0" "hpd\0" "tmds\0" "ddc\0" "cbl\0" "5V\0" "hpd\0" "tmds\0" "ddc\0" "";
static const __code BYTE tAwtoPsLblOff[16] = {
    0, 4, 8, 12, 16, 20, 24, 28, 31, 35, 40, 44, 48, 51, 55, 60};
static void AwtoPsLbl(BYTE ucRow)                  // signal label (one table + its reader, awto-sdcc#39)
{
    const __code char *pc = &tAwtoPsLblS[tAwtoPsLblOff[ucRow]];

    while(*pc != 0)
    {
        AwtoPutChar(*pc++);
    }
}
// GENERATED-END awto_port_sigs

// GENERATED-BEGIN awto_sync_text
static const __code BYTE tAwtoSyncFmt[101] = {
    0x00, 0x0A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0C, 0x8D, 0x0E, 0x0C, 0x0C,
    0x0F, 0x00, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x09, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x80, 0x83, 0x87, 0x88, 0x80, 0x82,
    0x85, 0x86, 0x00, 0x00, 0x00, 0x80, 0x80, 0x80, 0x80, 0x80, 0x83, 0x80, 0x80, 0x80, 0x8B, 0x01,
    0x01, 0x01, 0x01, 0x01, 0x01};
static const __code char tAwtoSyncTxtS[] = "boot: cold power-up (no valid canary in RAM)\0" "boot: watchdog bite, \x01" "\0" "boot: warm reset, no capture (host ISP 0xEE, or a hardware watchdog reset with interrupts off)\0" "boot: watchdog probe reset (test cmd 0x49 / 0x4F)\0" "boot: hardware watchdog reset, no capture (an early warning IRQ came)\0" "stage 1: main\0" "stage 2: GPIO init done\0" "stage 3: MCU init done (M2PLL, flash clock, banks, Timer2)\0" "stage 4: pin-share done\0" "stage 5: panel VDD on\0" "stage 6: first main-loop pass\0" "stage 7: DPTx link\0" "stage 8: DPTx video stream\0" "MCU init: crystal clock, watchdog N = 8\0" "Timer2 1 ms tick running\0" "watchdog run-time: warning 1025 ms, reset 1172 ms\0" "NVRAM save start (since the last poke \x01" ")\0" "NVRAM save end (since the last poke \x01" ")\0" "flash erase start (since the last poke \x01" ")\0" "flash erase done (since the last poke \x01" ")\0" "NVRAM page move (since the last poke \x01" ")\0" "NVRAM flush: gate open (since the last poke \x01" ")\0" "NVRAM flush: forced after 30 s (since the last poke \x01" ")\0" "NVRAM flush: power off / saving entry (since the last poke \x01" ")\0" "NVRAM flush: menu / selector close (since the last poke \x01" ")\0" "NVRAM flush: test cmd 0x3D (since the last poke \x01" ")\0" "NVRAM flush: second BriCon / ColorProc item (since the last poke \x01" ")\0" "(the 2 lines above repeated \x01" " more times)\0" "wake by the SDK source detect, not our poll (poll state \x01" ")\0" "host time \x01" "\0" "(fw +\x01" " ms, first host sync since boot)\0" "(fw +\x01" " ms, host sync after a drift)\0" "drift \x01" " (host - fw clock)\0" "power on\0" "switch to \x01" "\0" "wake on \x01" "\0" "power key on, \x01" "\0" "mode INITIAL\0" "mode SEARCH\0" "mode DISPLAY SETTING\0" "mode ACTIVE\0" "mode NO SUPPORT\0" "mode NO SIGNAL\0" "mode POWER SAVING\0" "mode POWER OFF\0" "panel on\0" "panel off\0" "backlight on\0" "backlight off\0" "panel VDD on (early)\0" "reset to search\0" "display setting\0" "judge: source unstable\0" "judge: timing change\0" "judge: interlace change\0" "judge: memory / timing gen\0" "eDP: panel HPD high\0" "eDP: link trained\0" "eDP: link training FAIL\0" "fast path taken\0" "fast path refused: no cache\0" "fast path refused: receiver unstable\0" "fast path: SDK reset meanwhile\0" "fast path timeout: full path\0" "fast path refused: timing field \x01" "\0" "hold L1: backlight off\0" "hold L2: eDP link off\0" "hold L3: SDK power saving\0" "hold: fast wakes used up\0" "hold: signal back\0" "hold: backlight on\0" "hold: fast wake retry\0" "hold: auto search, other cable\0" "hold: SDK reset\0" "HPD pulse (TMDS recover)\0" "TMDS clock \x01" " detected\0" "DP link \x01" " detected\0" "scan done: \x01" "\0" "signal lost\0" "timing \x01" "\0" "refresh \x01" "\0" "pixel clock \x01" "\0" "power off\0" "power saving\0" "console opened (sync log)\0" "cable plugged in: wake\0" "EDID read by source: wake\0" "AUX command from source: wake\0" "DPCD 600h = D0 (source powers the link): wake\0" "cable unplugged: wake\0" "wake by TMDS clock, about \x01" " (IOSC reference)\0" "DDC activity in power saving: no wake (SDK DDC handshake gated, counted)\0" "DP AUX activity in power saving: no wake (SDK AUX toggle gated, counted)\0" "AUX command from source in power saving: no wake (AUX wake off, #144 test)\0" "TMDS clock burst \x01" " in power saving: shorter than the hold, no wake\0" "wake suppressed (cable, once per sleep): \x01" "\0" "wake suppressed (EDID read, once per sleep): \x01" "\0" "wake suppressed (AUX command, once per sleep): \x01" "\0" "wake suppressed (DPCD 600h, once per sleep): \x01" "\0" "wake suppressed (cable unplug, once per sleep): \x01" "\0" "wake suppressed (TMDS clock, once per sleep): \x01" "\0" "";
static const __code WORD tAwtoSyncTxtOff[101] = {0, 45, 68, 163, 213, 283, 297, 321, 380, 404, 426, 456, 475, 502, 542, 567, 617, 658, 697, 739, 780, 820, 867, 922, 984, 1043, 1094, 1162, 1204, 1263, 1275, 1314, 1350, 1376, 1385, 1397, 1407, 1423, 1436, 1448, 1469, 1481, 1497, 1512, 1530, 1545, 1554, 1564, 1577, 1591, 1612, 1628, 1644, 1667, 1688, 1712, 1739, 1759, 1777, 1801, 1817, 1845, 1882, 1913, 1942, 1976, 1999, 2021, 2047, 2072, 2090, 2109, 2131, 2162, 2178, 2203, 2225, 2244, 2257, 2269, 2278, 2288, 2302, 2312, 2325, 2351, 2374, 2400, 2430, 2476, 2498, 2543, 2616, 2689, 2764, 2831, 2874, 2921, 2970, 3017, 3067};
static BYTE AwtoSyncTxt(BYTE ucRow, BYTE ucPart)   // text before (0) / after (1) the value mark, 2 = none; returns the fmt
{
    const __code char *pc = &tAwtoSyncTxtS[tAwtoSyncTxtOff[ucRow]];

    if(ucPart == 2)
    {
        return tAwtoSyncFmt[ucRow];
    }
    if(ucPart != 0)
    {
        while((*pc != 0) && (*pc != 1))
        {
            pc++;
        }
        if(*pc == 0)
        {
            return tAwtoSyncFmt[ucRow];
        }
        pc++;
    }
    while((*pc != 0) && (*pc != 1))             // AwtoPutChar inlined: no call, so the packer keeps the table in this bank
    {
        if(s_ucAwtoLen < s_ucAwtoCols)
        {
            s_pcAwtoRow[s_ucAwtoLen++] = *pc;
        }
        pc++;
    }
    return tAwtoSyncFmt[ucRow];
}
// GENERATED-END awto_sync_text

static __xdata BYTE s_pucSrcSt[3];              // last drawn: port state, sync stage, rate checksum
static __xdata BYTE s_pucSrcStage[3];
static __xdata WORD s_pusSrcRate[3];             // rate change key (AwtoSrcRateKey)
static __xdata BYTE s_pucSrcSig[AWTO_PS_N];     // last drawn value per signal row
static __xdata BYTE s_pucSrcCnt[(AWTO_PS_CNT_N != 0) ? AWTO_PS_CNT_N : 1];   // edge counter at the last poll
static __xdata WORD s_usSrcPoll;
static __xdata BYTE s_ucSrcLogSeq;              // ring seq the log pane shows up to

static WORD AwtoSrcNow(void)
{
    WORD usNow;

    do
    {
        usNow = g_stAwtoDiag.usT2Isr;
    }
    while(usNow != g_stAwtoDiag.usT2Isr);
    return usNow;
}

static void AwtoPutTenths(DWORD ulV)
{
    AwtoPutNum(ulV / 10, 1);
    AwtoPutChar('.');
    AwtoPutNum(ulV % 10, 1);
}

static void AwtoPutDpRate(BYTE ucRate, BYTE ucLanes)
{
    if(ucRate == _DP_LINK_RBR) AwtoCardTxt(AWTO_CT_RBR);
    else if(ucRate == _DP_LINK_HBR) AwtoCardTxt(AWTO_CT_RBR + 1);
    else if(ucRate == _DP_LINK_HBR2) AwtoCardTxt(AWTO_CT_RBR + 2);
    else if(ucRate == _DP_LINK_HBR3) AwtoCardTxt(AWTO_CT_HBR3);
    else AwtoPutHex2(ucRate);
    AwtoPutStr(" x");
    AwtoPutNum(ucLanes, 1);
}

// #157 unix s + UTC offset (15 min) -> "2026-11-12T08:45:10+11:00" (days -> civil date: H. Hinnant's civil_from_days).
// No parameters or locals in DATA: it sits on the deepest overlay path (flash save -> sync push -> console line).
static __xdata DWORD s_ulAwtoD;                 // days, then day of the era, then day of the year
static __xdata WORD s_usAwtoIsoY;
static __xdata BYTE s_ucAwtoIsoMp;              // March-based month 0..11
static __xdata signed char s_cAwtoIsoOfs;       // input: UTC offset, 15 min units

static void AwtoPutIso(void)                    // input s_ulAwtoT = unix s, s_cAwtoIsoOfs
{
    s_ulAwtoT += (long)s_cAwtoIsoOfs * 900;     // local s
    s_ulAwtoD = s_ulAwtoT / 86400 + 719468;     // days since 0000-03-01
    s_usAwtoIsoY = (WORD)(s_ulAwtoD / 146097) * 400;
    s_ulAwtoD %= 146097;
    s_usAwtoIsoY += (WORD)((s_ulAwtoD - s_ulAwtoD / 1460 + s_ulAwtoD / 36524 - s_ulAwtoD / 146096) / 365);
    s_ulAwtoD -= 365UL * (s_usAwtoIsoY % 400) + (s_usAwtoIsoY % 400) / 4 - (s_usAwtoIsoY % 400) / 100;
    s_ucAwtoIsoMp = (BYTE)((5 * (WORD)s_ulAwtoD + 2) / 153);
    AwtoPutNum(s_usAwtoIsoY + ((s_ucAwtoIsoMp >= 10) ? 1 : 0), 4);
    AwtoPutChar('-');
    AwtoPutNum((s_ucAwtoIsoMp < 10) ? (s_ucAwtoIsoMp + 3) : (s_ucAwtoIsoMp - 9), 2);
    AwtoPutChar('-');
    AwtoPutNum((WORD)s_ulAwtoD - (153 * (WORD)s_ucAwtoIsoMp + 2) / 5 + 1, 2);
    AwtoPutChar('T');
    s_ulAwtoT %= 86400;
    AwtoPutClock();
    AwtoPutChar((s_cAwtoIsoOfs < 0) ? '-' : '+');
    s_ucAwtoIsoMp = (s_cAwtoIsoOfs < 0) ? (BYTE)(0 - s_cAwtoIsoOfs) : (BYTE)s_cAwtoIsoOfs;
    AwtoPutNum(s_ucAwtoIsoMp / 4, 2);
    AwtoPutChar(':');
    AwtoPutNum((s_ucAwtoIsoMp % 4) * 15, 2);
}

// One sync-ring entry as a log line: "+  260 ms D2 timing 3840x2160" (texts and formats: fw/awto/sync.tsv).
static __xdata DWORD s_ulAwtoLnV;               // #157: value + time in XDATA (DATA overlay path depth, see AwtoPutIso)
static __xdata WORD s_usAwtoLnMs;
#define ulV s_ulAwtoLnV
#define usMs s_usAwtoLnMs
static void AwtoSyncLine(BYTE ucSeq)
{
    BYTE __xdata *puc = (BYTE __xdata *)&g_stAwtoSync.stEv[AWTO_SYNC_IDX(ucSeq)];
    BYTE ucRow = AwtoSyncRow(puc[0], puc[1]);
    BYTE ucFmt;

    ulV = ((DWORD)puc[4] << 24) | ((DWORD)puc[5] << 16) | ((WORD)puc[6] << 8) | puc[7];
    usMs = (((WORD)puc[2] << 8) | puc[3]) - (((WORD)g_stAwtoSync.ucT0Hi << 8) | g_stAwtoSync.ucT0Lo);

    AwtoPutChar('+');
    AwtoPutCol(s_ucAwtoLen + ((usMs < 10) ? 4 : (usMs < 100) ? 3 : (usMs < 1000) ? 2 : (usMs < 10000) ? 1 : 0));
    AwtoPutNum(usMs, 1);
    AwtoPutStr(" ms ");
    if(ucRow == 0)
    {
        AwtoPutStr("event ");
        AwtoPutHex2(puc[0]);
        AwtoPutChar(' ');
        AwtoPutHex2(puc[1]);
        return;
    }
    ucFmt = AwtoSyncTxt(ucRow - 1, 2);           // part 2 = nothing printed, the fmt only
    if((ucFmt & 0x80) != 0)
    {
        AwtoPutChar('D');
        AwtoPutNum(puc[1] - _D0_INPUT_PORT, 1);
        AwtoPutChar(' ');
    }
    AwtoSyncTxt(ucRow - 1, 0);
    switch(ucFmt & 0x7F)
    {
        case 1:                                 // vport
            if(puc[7] == 0xFF) AwtoPutStr("auto");
            else { AwtoPutChar('D'); AwtoPutNum(puc[7] - _D0_INPUT_PORT, 1); }
            break;
        case 2: AwtoPutNum(ulV >> 16, 1); AwtoPutChar('x'); AwtoPutNum(ulV & 0xFFFF, 1); break;    // res
        case 3: AwtoPutTenths(ulV); AwtoCardTxt(AWTO_CT_HZ + 2); break;                            // mhz1
        case 4: AwtoPutTenths(ulV); AwtoCardTxt(AWTO_CT_HZ); break;                                // hz1
        case 5: AwtoPutMilli(ulV); AwtoCardTxt(AWTO_CT_HZ); break;                                 // hz3
        case 6: AwtoPutMilli(ulV); AwtoCardTxt(AWTO_CT_HZ + 2); break;                             // mhz3
        case 7: AwtoPutDpRate(puc[6], puc[7]); break;                                              // dp
        case 8:                                                                                    // src
            if(ulV == _SOURCE_HDMI) AwtoPutStr("HDMI");
            else if(ulV == _SOURCE_DP) AwtoPutStr("DP");
            else if(ulV == _SOURCE_DVI) AwtoPutStr("DVI");
            else AwtoPutNum(ulV, 1);
            break;
        case 9: AwtoPutHex2(puc[1]); break;                                                        // harg
        case 10:                                                                                   // pc (#29)
            AwtoPutStr(((puc[4] & 0x80) != 0) ? "STALL TEST, PC " : "STALL, PC ");
            if(puc[6] >= 0x50) AwtoPutHex2(puc[5]); else AwtoPutChar('C');
            AwtoPutChar(':');
            AwtoPutHex2(puc[6]);
            AwtoPutHex2(puc[7]);
            break;
        case 11: AwtoPutNum(ulV, 1); AwtoPutStr(" ms"); break;                                     // ms (#150)
        case 12: AwtoPutNum(ulV, 1); break;                                                        // n (#150)
        case 13: AwtoPutHex2(puc[5]); AwtoPutHex2(puc[6]); AwtoPutHex2(puc[7]); break;             // x (#150)
        case 14: s_ulAwtoT = ulV; s_cAwtoIsoOfs = (signed char)puc[1]; AwtoPutIso(); break;                                     // htime (#157)
        case 15:                                                                                   // sms (#157)
            AwtoPutChar(((long)ulV < 0) ? '-' : '+');
            AwtoPutNum(((long)ulV < 0) ? (0 - ulV) : ulV, 1);
            AwtoPutStr(" ms");
            break;
        default: break;
    }
    AwtoSyncTxt(ucRow - 1, 1);
}
#undef ulV
#undef usMs

static BYTE AwtoSrcStyle(BYTE ucI)
{
    return (ucI == AwtoSrcSel()) ? AWTO_T_STYLE_ONACC : AWTO_T_STYLE_TEXT;
}

static BYTE AwtoPsValue(BYTE ucR, WORD usDt)    // current value of signal row ucR; usDt = ms since the last poll (cnt rows)
{
    BYTE ucPort = _D1_INPUT_PORT + tAwtoPsPort[ucR];
    WORD usA = tAwtoPsA[ucR];
    BYTE ucV;

    switch(tAwtoPsSrc[ucR])
    {
        case AWTO_PS_SRC_IN:
            ucV = g_stAwtoGpio.ucIn[usA];
            return (tAwtoPsB[ucR] != 0) ? (ucV == 0) : (ucV != 0);
        case AWTO_PS_SRC_CNT:
            ucV = g_pucAwtoInCnt[usA] - s_pucSrcCnt[usA];
            s_pucSrcCnt[usA] = g_pucAwtoInCnt[usA];
            return (usDt == 0) ? 0 : (BYTE)(((DWORD)ucV * 1000 + usDt / 2) / usDt);
        case AWTO_PS_SRC_XREG:
            return ((ScalerGetByte(usA) & tAwtoPsB[ucR]) != 0);
        case AWTO_PS_SRC_CABLE:
            return SysSourceGetCableDetect(ucPort);
        case AWTO_PS_SRC_DDC:
            return AwtoDdcLive(tAwtoPsPort[ucR]);
        default:
            return (AwtoTmdsIdleKhz((BYTE)usA) != 0);
    }
}

static void AwtoPsField(BYTE ucR, BYTE ucV, BYTE ucStyle)    // value of signal row ucR at its column
{
    AwtoFieldBegin();
    if(tAwtoPsSrc[ucR] == AWTO_PS_SRC_CNT)
    {
        AwtoPutNum(ucV, 1);
        AwtoPutStr("/s");
        AwtoPutCol(5);
    }
    else
    {
        AwtoPutChar((ucV != 0) ? '+' : '-');
    }
    AwtoFieldEnd(AWTO_SRC_PROW(tAwtoPsPort[ucR] + 1) + 1, tAwtoPsCol[ucR], ucStyle);
}

// Rate of a port: the active port's timing, the measured timing while syncing, else what its receiver has without a switch.
static void AwtoSrcRate(BYTE ucPort)
{
    DWORD ulK;

    if((ucPort == SysSourceGetInputPort()) && (SysModeGetModeState() == _MODE_STATUS_ACTIVE))
    {
        AwtoPutNum(GET_INPUT_TIMING_HWIDTH(), 1);
        AwtoPutChar('x');
        AwtoPutNum(GET_INPUT_TIMING_VHEIGHT(), 1);
        AwtoPutChar(' ');
#if(_AWTO_FREQ == _ON)
        if(g_stAwtoFreq.ucValid != 0)
        {
            AwtoPutMilli(g_stAwtoFreq.ulVFreqmHz);
            AwtoPutStr("Hz ");
            AwtoPutMilli(g_stAwtoFreq.ulPclkHz / 1000);
            AwtoPutStr("MHz");
            return;
        }
#endif
        AwtoPutTenths(GET_INPUT_TIMING_VFREQ());
        AwtoPutStr("Hz ");
        AwtoPutTenths(ScalerSyncGetInputPixelClk());
        AwtoPutStr("MHz");
        return;
    }
#if(_DP_SUPPORT == _ON)
    if(AwtoPortIsDp(ucPort) != 0)
    {
        ulK = ScalerDpGetLaneCount(ucPort);
        if((ulK == 0) || (SysSourceGetCableDetect(ucPort) == _FALSE))
        {
            AwtoCardTxt(AWTO_CT_NOLINK);
            return;
        }
        AwtoCardTxt(AWTO_CT_DPLINK);
        AwtoPutChar(' ');
        AwtoPutDpRate(ScalerDpGetLinkRate(ucPort), (BYTE)ulK);       // DPCD 100h / 101h: the last training
        return;
    }
#endif
    ulK = AwtoTmdsIdleKhz((ucPort == _D2_INPUT_PORT) ? 0x71 : 0x72);
    if(ulK == 0)
    {
        AwtoPutChar('-');
        return;
    }
    AwtoCardTxt(AWTO_CT_TMDS);
    AwtoPutTenths((ulK + 50) / 100);
    AwtoCardTxt(AWTO_CT_HZ + 2);
}

static WORD AwtoSrcRateKey(BYTE ucPort)         // cheap change key of what AwtoSrcRate prints (no text, no division)
{
    if((ucPort == SysSourceGetInputPort()) && (SysModeGetModeState() == _MODE_STATUS_ACTIVE))
    {
#if(_AWTO_FREQ == _ON)
        if(g_stAwtoFreq.ucValid != 0)
        {
            return 0x8000 ^ GET_INPUT_TIMING_HWIDTH() ^ (GET_INPUT_TIMING_VHEIGHT() << 4) ^ (WORD)g_stAwtoFreq.ulVFreqmHz ^
                   (WORD)(g_stAwtoFreq.ulPclkHz >> 10);
        }
#endif
        return 0x8001 ^ GET_INPUT_TIMING_HWIDTH() ^ (GET_INPUT_TIMING_VHEIGHT() << 4) ^ GET_INPUT_TIMING_VFREQ();
    }
#if(_DP_SUPPORT == _ON)
    if(AwtoPortIsDp(ucPort) != 0)
    {
        return 0x4000 | ((WORD)SysSourceGetCableDetect(ucPort) << 13) | ((WORD)ScalerDpGetLaneCount(ucPort) << 8) |
               ScalerDpGetLinkRate(ucPort);
    }
#endif
    return (WORD)(AwtoTmdsIdleKhz((ucPort == _D2_INPUT_PORT) ? 0x71 : 0x72) >> 6);    // 64 kHz steps: count noise is no change
}

// Port item i: state, stage, rate fields; bAll = draw even if unchanged (full draw).
static void AwtoSrcPortFields(BYTE ucI, bit bAll)
{
    BYTE ucPort = AwtoSrcPort(ucI);
    BYTE ucK = ucPort - _D1_INPUT_PORT;
    BYTE ucStyle = AwtoSrcStyle(ucI);
    BYTE ucV;
    WORD usKey;

    ucV = ui_port_state(ucK);
    if((bAll != 0) || (ucV != s_pucSrcSt[ucK]))
    {
        s_pucSrcSt[ucK] = ucV;
        AwtoFieldBegin();
        AwtoCardTxt(AWTO_CT_STATE + ucV);
        AwtoPutCol(10);
        AwtoFieldEnd(AWTO_SRC_PROW(ucI), AWTO_SRC_STATE_COL, (ucStyle == AWTO_T_STYLE_ONACC) ? ucStyle : ((ucV == 3) ? AWTO_T_STYLE_TEXT : AWTO_T_STYLE_DIM));
    }
    ucV = AwtoSyncStage(ucPort);
    if((bAll != 0) || (ucV != s_pucSrcStage[ucK]))
    {
        s_pucSrcStage[ucK] = ucV;
        AwtoFieldBegin();
        AwtoCardTxt(AWTO_CT_STAGE + ucV);
        AwtoPutCol(AWTO_SRC_RATE_COL - AWTO_SRC_STAGE_COL);
        AwtoFieldEnd(AWTO_SRC_PROW(ucI) + 2, AWTO_SRC_STAGE_COL, ucStyle);
    }
    usKey = AwtoSrcRateKey(ucPort);
    if((bAll != 0) || (usKey != s_pusSrcRate[ucK]))
    {
        s_pusSrcRate[ucK] = usKey;
        AwtoFieldBegin();
        AwtoSrcRate(ucPort);
        AwtoPutCol(AWTO_SRC_RATE_W);
        AwtoFieldEnd(AWTO_SRC_PROW(ucI) + 2, AWTO_SRC_RATE_COL, ucStyle);
    }
}

static void AwtoSrcSigs(bit bAll, WORD usDt)
{
    BYTE ucR, ucV;

    for(ucR = 0; ucR < AWTO_PS_N; ucR++)
    {
        ucV = AwtoPsValue(ucR, usDt);
        if((bAll != 0) || (ucV != s_pucSrcSig[ucR]))
        {
            s_pucSrcSig[ucR] = ucV;
            AwtoPsField(ucR, ucV, AwtoSrcStyle(tAwtoPsPort[ucR] + 1));
        }
    }
}

static void AwtoSrcLog(void)                    // the last AWTO_SRC_LOGN lines of the current episode
{
    BYTE ucSeq = g_stAwtoSync.ucSeq;
    BYTE ucN = AWTO_SYNC_BACK(ucSeq, g_stAwtoSync.ucEpSeq);
    BYTE ucL;

    s_ucSrcLogSeq = ucSeq;
    if(ucN > AWTO_SRC_LOGN)
    {
        ucN = AWTO_SRC_LOGN;
    }
    for(ucL = 0; ucL < AWTO_SRC_LOGN; ucL++)
    {
        if(ucL < ucN)
        {
            AwtoSyncLine(AWTO_SYNC_BACK(ucSeq, ucN - ucL));
        }
        AwtoTextLine(AWTO_SRC_LOGHDR + 1 + ucL, AWTO_T_STYLE_DIM);
    }
}

static void AwtoSourceRows(void)                // Auto, then each port with its state, signals, stage and rate; the log
{
    BYTE ucSel = AwtoSrcSel();
    BYTE ucI, ucR;

    ucR = (ucSel == 0) ? AWTO_SRC_ROW0 : AWTO_SRC_PROW(ucSel);
    osd_tc_bar(AWTO_WIN_HL, 2, (WORD)ucR * osd_rh, (WORD)AWTO_SRC_COLS * osd_cw - 3,
               (WORD)(ucR + ((ucSel == 0) ? 1 : 3)) * osd_rh - 1, 1);
    for(ucI = 0; ucI <= AWTO_SRC_PORTS; ucI++)
    {
        if(ucI == 0)
        {
            AwtoCardTxt(AWTO_CT_AUTO);
            AwtoTextLine(AWTO_SRC_ROW0, AwtoSrcStyle(0));
            continue;
        }
        AwtoPortName(AwtoSrcPort(ucI));
        AwtoTextLine(AWTO_SRC_PROW(ucI), AwtoSrcStyle(ucI));
        for(ucR = 0; ucR < AWTO_PS_N; ucR++)          // signal labels; values follow
        {
            if(tAwtoPsPort[ucR] + 1 == ucI)
            {
                AwtoPutCol(tAwtoPsLblCol[ucR]);
                AwtoPsLbl(ucR);
            }
        }
        AwtoTextLine(AWTO_SRC_PROW(ucI) + 1, AwtoSrcStyle(ucI));
        AwtoTextLine(AWTO_SRC_PROW(ucI) + 2, AwtoSrcStyle(ucI));
        AwtoSrcPortFields(ucI, 1);
    }
    AwtoSrcSigs(1, 0);
    AwtoCardTxt(AWTO_CT_SYNCLOG);
    AwtoTextLine(AWTO_SRC_LOGHDR, AWTO_T_STYLE_TEXT);
    AwtoSrcLog();
    s_usSrcPoll = AwtoSrcNow();
}

static bit AwtoSourceNoPicture(void)            // power saving / no signal / no support: the SDK hands back to its pop-up timers
{
    BYTE ucMode = SysModeGetModeState();

    return ((ucMode == _MODE_STATUS_POWER_SAVING) || (ucMode == _MODE_STATUS_NOSIGNAL) || (ucMode == _MODE_STATUS_NOSUPPORT));
}

// #139 the selector stays open until a choice or a cancel. With no picture the monitor must still sleep: after
// AWTO_SRC_SLEEP_SEC without a key, the SDK power-saving card (2 s) and power saving. With a picture: no timer.
static void AwtoSrcSleepArm(void)
{
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
    if(AwtoSourceNoPicture() == _TRUE)
    {
        ScalerTimerReactiveTimerEvent(SEC(AWTO_SRC_SLEEP_SEC), _USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
    }
    else
    {
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
    }
}

// The one way in (SOURCE, UP with a picture, OSD event 7 = no signal / wake): preset to the current input (Auto while auto-scanning).
void AwtoSourceOpen(void)
{
    if(SysSourceGetScanType() == _SOURCE_SWITCH_AUTO_IN_GROUP)
    {
        SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_AUTO);
    }
    else
    {
        SET_OSD_INPUT_PORT_OSD_ITEM(AwtoSrcItem(SysSourceGetInputPort()));
    }
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_GO_TO_POWER_SAVING);
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_CABLE);
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_SIGNAL);
    AwtoSrcSleepArm();
    SET_OSD_STATE(_MENU_HOTKEY_SOURCE);
    OsdFuncSetOsdItemFlag();
    g_usBackupValue = GET_OSD_INPUT_PORT_OSD_ITEM();
    AwtoCardOpenW(AWTO_SRC_COLS, AWTO_SRC_LINES, AWTO_CT_INPUT);
    AwtoSourceRows();
    AwtoCardShow();
    UserCommonInterfacePanelPowerAction(_BACKLIGHT_ON);
}

static void AwtoSourceStep(bit bBack)
{
    BYTE ucSel = AwtoSrcSel();

    if(bBack != 0)
    {
        ucSel = (ucSel == 0) ? AWTO_SRC_PORTS : (ucSel - 1);
    }
    else
    {
        ucSel = (ucSel == AWTO_SRC_PORTS) ? 0 : (ucSel + 1);
    }
    AwtoSrcSet(ucSel);
}

static void AwtoSourceClose(void)
{
    if(AwtoSourceNoPicture() == _TRUE)
    {
        ScalerTimerReactiveTimerEvent(SEC(0), _USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
    }
    else
    {
        OsdDispDisableOsd();
    }
}

// Selector open (_MENU_HOTKEY_SOURCE), key from the key router (#129).
void AwtoSourceKey(BYTE ucKey)
{
    BYTE ucItem = GET_OSD_INPUT_PORT_OSD_ITEM();
    BYTE ucPort;

    if((ucKey == _RIGHT_KEY_MESSAGE) || (ucKey == _LEFT_KEY_MESSAGE))  // UP / DOWN: step
    {
        AwtoSourceStep(ucKey == _LEFT_KEY_MESSAGE);
        AwtoSourceRows();
        AwtoSrcSleepArm();                      // #151: a step is never stored
    }
    else if(ucKey == _EXIT_KEY_MESSAGE)        // MENU: cancel, the choice goes back
    {
        if(g_usBackupValue != ucItem)
        {
            SET_OSD_INPUT_PORT_OSD_ITEM(g_usBackupValue);
        }
        AwtoSourceClose();
    }
    else if((ucKey == _MENU_KEY_MESSAGE) && (GET_OSD_DP_VERSION_HOTKEY_DISP() == _OFF))     // AUTO: take the choice
    {
        if(g_usBackupValue == ucItem)
        {
            AwtoSourceClose();
        }
        else if(ucItem == _OSD_INPUT_AUTO)
        {
            AwtoSyncBegin(AWTO_SYNC_K_SWITCH, 0xFF);
            SysSourceSetScanType(_SOURCE_SWITCH_AUTO_IN_GROUP);
            SysModeSetResetTarget(_MODE_ACTION_RESET_TO_SEARCH);
            UserCommonNVRamSetSystemData(_SOURCE_SCAN_TYPE, SysSourceGetScanType());
#ifdef _AWTO_NEW_SETTINGS
            AwtoNvCommitSel();                  // #151: the chosen input is stored at the gate ("Saving to memory")
#endif
        }
        else
        {
            ucPort = (ucItem >= _OSD_INPUT_D0) ? (ucItem - _OSD_INPUT_D0 + _D0_INPUT_PORT) : _NO_INPUT_PORT;
            if(ucPort == _NO_INPUT_PORT)
            {
                return;                         // not a port of this board: the selector stays up
            }
            SET_FORCE_POW_SAV_STATUS(_FALSE);
            SysSourceSwitchInputPort(ucPort);
            SysSourceSetScanType(_SOURCE_SWITCH_FIXED_PORT);
            SysModeSetResetTarget(_MODE_ACTION_RESET_TO_SEARCH);
            UserCommonNVRamSetSystemData(_SEARCH_PORT, SysSourceGetInputPort());
            UserCommonNVRamSetSystemData(_SOURCE_SCAN_TYPE, SysSourceGetScanType());
#ifdef _AWTO_NEW_SETTINGS
            AwtoNvCommitSel();                  // #151: the chosen input is stored at the gate ("Saving to memory")
#endif
        }
#if(_DP_MST_SUPPORT == _ON)
        if(g_usBackupValue != ucItem)
        {
            UserCommonInterfaceMstRx0Rx1switch(UserCommonInterfaceGetDpMstCapablePort());
            RTDNVRamSaveOSDData();
        }
#endif
        SET_OSD_STATE(_MENU_NONE);
    }
}

// #139 console auto-open: once per episode, when the screen is ours to take (no menu / selector / logo / hold) and the
// episode has settled (ACTIVE / no signal / no support / power saving): opening it never delays the sync. Setting: registry
// sync_console (id 110); g_ucAwtoSyncCon = 0 also stops it (test harness, fw_sim osd_render.Session).
__xdata BYTE g_ucAwtoSyncCon = 1;

static void AwtoSyncConPoll(void)
{
    if(g_stAwtoSync.ucOpenReq == 0)
    {
        return;
    }
    if((g_ucAwtoSyncCon == 0) || (AWTO_SET(SYNC_CONSOLE) == 0) || (GET_OSD_STATE() == _MENU_HOTKEY_SOURCE) ||
       (SysPowerGetPowerStatus() == _POWER_STATUS_OFF) || (SysPowerGetPowerStatus() == _POWER_STATUS_SAVING))
    {
        g_stAwtoSync.ucOpenReq = 0;             // off, the selector's log pane shows it, or no screen
        return;
    }
    if(g_stAwtoSync.ucDone == 0)
    {
        return;                                 // every episode ends in one of the settled modes (search time-outs)
    }
    if((s_ucConOpen != 0) && (AwtoConLost() == 0))
    {
        g_stAwtoSync.ucOpenReq = 0;             // already open (the power-on console survived display setting)
        return;
    }
    if((SysPowerGetPowerStatus() != _POWER_STATUS_NORMAL) || (GET_OSD_STATE() != _MENU_NONE) || (g_ucAwtoMenuOn != 0) || AWTO_KEY_TEST_ON() ||
       (g_stAwtoDiag.ucHold != 0))
    {
        return;
    }
    g_stAwtoSync.ucOpenReq = 0;
    AwtoSyncPush(AWTO_SYNC_EV_CONSOLE, 0, 0);
    AwtoDiagConsole(1);                         // its log backfills the episode (AwtoConLogInit)
}

#if(_AWTO_BOOT_PANEL_EARLY == _ON)
// #144 power-on, mode INITIAL (RTD2014Osd.c, before the panel comes on), and a source-event wake (awto_sync.inc): the
// console with the live log, no logo.
// The auto-open request stays: at the settled mode AwtoSyncConPoll reopens it if display setting took the OSD.
void AwtoBootConsole(void)
{
    if((g_ucAwtoSyncCon == 0) || (AWTO_SET(SYNC_CONSOLE) == 0))
    {
        return;
    }
    ScalerDDomainBackgroundEnable(_ENABLE);    // black frame under the OSD: also the short T3 (own pattern) at panel on
    AwtoSyncPush(AWTO_SYNC_EV_CONSOLE, 0, 0);
    s_ucConOpen = 0;                            // wake: power saving lost the OSD of a console left open; draw it anew
    AwtoDiagConsole(1);
}
#endif

// Every main-loop pass (AwtoGpioPoll): console log lines, auto-open, selector fields every AWTO_SRC_POLL_MS.
void AwtoOsdSyncPoll(void)
{
    WORD usNow, usDt;
    BYTE ucI;

    if(s_ucConOpen != 0)
    {
        AwtoConLogSync();
#if(_AWTO_SYNC_LOG == _ON)
        AwtoConTitlePoll();                     // #157 live title fields
#endif
    }
    AwtoSyncConPoll();
    if((GET_OSD_STATE() != _MENU_HOTKEY_SOURCE) || (g_ucOsdWidth != AWTO_SRC_COLS))
    {
        return;
    }
    usNow = AwtoSrcNow();
    usDt = usNow - s_usSrcPoll;
    if(usDt < AWTO_SRC_POLL_MS)
    {
        return;
    }
    s_usSrcPoll = usNow;
    for(ucI = 1; ucI <= AWTO_SRC_PORTS; ucI++)
    {
        AwtoSrcPortFields(ucI, 0);
    }
    AwtoSrcSigs(0, usDt);
    if(s_ucSrcLogSeq != g_stAwtoSync.ucSeq)
    {
        AwtoSrcLog();
    }
}

//---- message cards (#124) ----
static void AwtoInfoLabel(BYTE ucT)
{
    AwtoCardTxt(ucT);
    AwtoPutCol(AWTO_INFO_VAL_COL);
}

static void AwtoInfoTenths(WORD usV)            // SDK 0.1-unit value (no exact measurement yet), as the awto menu shows it
{
    AwtoPutNum(usV / 10, 1);
    AwtoPutChar('.');
    AwtoPutNum(usV % 10, 1);
}

// Input information (DOWN, mode ACTIVE): what the SDK pop-up showed, exact frequencies from awto_freq (#34) when measured.
static void AwtoInfoCard(void)
{
    BYTE ucPort = SysSourceGetInputPort();
    BYTE ucRow = AWTO_CARD_ROW0;
    BYTE ucV;
    bit bActive = (SysModeGetModeState() == _MODE_STATUS_ACTIVE);
    bit bDp = AwtoPortIsDp(ucPort);

    AwtoCardOpen(AWTO_CARD_ROW0 + (bActive ? 6 : 2) + (bDp ? 2 : 0) + 1, AWTO_CT_INFO);
    AwtoInfoLabel(AWTO_CT_INPUT);
    AwtoPortName(ucPort);
    AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
    if(bActive == 0)
    {
        AwtoInfoLabel(AWTO_CT_STATUS);
        AwtoCardTxt(AWTO_CT_STATE + ui_port_state(ucPort - _D1_INPUT_PORT));
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
    }
    else
    {
        AwtoInfoLabel(AWTO_CT_RES);
        AwtoPutNum(GET_INPUT_TIMING_HWIDTH(), 1);
        AwtoPutChar('x');
        AwtoPutNum(GET_INPUT_TIMING_VHEIGHT(), 1);
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
        AwtoInfoLabel(AWTO_CT_REFRESH);
#if(_AWTO_FREQ == _ON)
        if(g_stAwtoFreq.ucValid != 0)
        {
            AwtoPutMilli(g_stAwtoFreq.ulVFreqmHz);
        }
        else
#endif
        {
            AwtoInfoTenths(GET_INPUT_TIMING_VFREQ());
        }
        AwtoCardTxt(AWTO_CT_HZ);
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
        AwtoInfoLabel(AWTO_CT_HFREQ);
#if(_AWTO_FREQ == _ON)
        if(g_stAwtoFreq.ucValid != 0)
        {
            AwtoPutMilli(g_stAwtoFreq.ulHFreqHz);
        }
        else
#endif
        {
            AwtoInfoTenths(GET_INPUT_TIMING_HFREQ());
        }
        AwtoCardTxt(AWTO_CT_HZ + 1);
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
        AwtoInfoLabel(AWTO_CT_PCLK);
#if(_AWTO_FREQ == _ON)
        if(g_stAwtoFreq.ucValid != 0)
        {
            AwtoPutMilli(g_stAwtoFreq.ulPclkHz / 1000);
        }
        else
#endif
        {
            AwtoInfoTenths(ScalerSyncGetInputPixelClk());
        }
        AwtoCardTxt(AWTO_CT_HZ + 2);
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
        AwtoInfoLabel(AWTO_CT_HDCP);
        ucV = ScalerSyncHdcpCheckEnabled(ucPort);          // 0 = off, else version 0x14 / 0x22 | 0x80 = repeater
        if(ucV == 0)
        {
            AwtoCardTxt(AWTO_CT_OFF);
        }
        else
        {
            AwtoPutNum((ucV & 0x7F) >> 4, 1);
            AwtoPutChar('.');
            AwtoPutNum(ucV & 0x0F, 1);
            AwtoCardTxt(AWTO_CT_SINK + (((ucV & 0x80) != 0) ? 1 : 0));
        }
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
    }
#if(_DP_SUPPORT == _ON)
    if(bDp != 0)
    {
        AwtoInfoLabel(AWTO_CT_DPLINK);
        AwtoPutNum(ScalerDpGetLaneCount(ucPort), 1);
        AwtoCardTxt(AWTO_CT_LANES);
        ucV = ScalerDpGetLinkRate(ucPort);
        if(ucV == _DP_LINK_RBR)
        {
            AwtoCardTxt(AWTO_CT_RBR);
        }
        else if(ucV == _DP_LINK_HBR)
        {
            AwtoCardTxt(AWTO_CT_RBR + 1);
        }
        else if(ucV == _DP_LINK_HBR2)
        {
            AwtoCardTxt(AWTO_CT_RBR + 2);
        }
        else
        {
            AwtoPutHex2(ucV);
        }
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
        AwtoInfoLabel(AWTO_CT_SWING);
        for(ucV = _DP_LANE_0; ucV <= _DP_LANE_3; ucV++)  // voltage swing / pre-emphasis level per lane
        {
            if(ucV != _DP_LANE_0)
            {
                AwtoPutChar(' ');
            }
            AwtoPutNum(ScalerDpGetLaneVoltageSwingLv(ucPort, ucV), 1);
            AwtoPutChar('/');
            AwtoPutNum(ScalerDpGetLanePreEmpLv(ucPort, ucV), 1);
        }
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
    }
#endif
    AwtoCardShow();
}

#ifdef _AWTO_NEW_SETTINGS
// #151 "Saving to memory": up while the flush gate writes after a menu / selector close; off after AWTO_SAVE_CARD_MS
void AwtoSaveCard(void)
{
    AwtoCardOpen(AWTO_CARD_ROW0 + 2, AWTO_CT_AWTO);
    AwtoCardTxt(AWTO_CT_SAVING);
    AwtoCardCentre(AWTO_CARD_ROW0, AWTO_T_STYLE_TEXT);
    AwtoCardShow();
    ScalerTimerReactiveTimerEvent(AWTO_SAVE_CARD_MS, _USER_TIMER_EVENT_OSD_DISABLE);
}
#endif

// Every SDK message card: our text card. Fail-safe = No Support (one warning card); switch DDC/CI port names the input (#114).
void OsdDispOsdMessage(EnumOSDDispMsg enumMessage)  // replaces the SDK body (keil2sdcc _K124)
{
    BYTE ucT;

    if((GET_OSD_STATE() == _MENU_HOTKEY_SOURCE) && ((enumMessage == _OSD_DISP_NOSIGNAL_MSG) || (enumMessage == _OSD_DISP_NOCABLE_MSG)))
    {
        AwtoSrcSleepArm();                      // #139: the open selector stays (its rows show the state); the SDK's 3 s is not restarted
        return;
    }
    if((enumMessage == _OSD_DISP_INPUT_SIGNAL_MSG) && (s_ucConOpen != 0) && (AwtoConLost() == 0))
    {
        return;                                 // #144: the open console keeps the screen; its log has the timing lines
    }
    OsdDispDisableOsd();
    if(enumMessage == _OSD_DISP_INPUT_SIGNAL_MSG)
    {
        AwtoInfoCard();
        return;
    }
    switch(enumMessage)
    {
        case _OSD_DISP_NOSIGNAL_MSG:            ucT = AWTO_CT_NOSIGNAL; break;
        case _OSD_DISP_NOCABLE_MSG:             ucT = AWTO_CT_NOCABLE; break;
        case _OSD_DISP_AUTO_CONFIG_MSG:         ucT = AWTO_CT_AUTOADJ; break;
        case _OSD_DISP_AUTO_COLOR_MSG:          ucT = AWTO_CT_AUTOCOL; break;
        case _OSD_DISP_SWITCH_DDCCI_PORT_MSG:   ucT = AWTO_CT_DDCCI; break;
        case _OSD_DISP_POWER_SAVING_MSG:        ucT = AWTO_CT_PSAVE; break;
        case _OSD_DISP_PANEL_UNIFORMITY_ONOFF_MSG: ucT = AWTO_CT_PANEL; break;
        default:                                ucT = AWTO_CT_NOSUPPORT; break;     // no support, fail-safe
    }
    AwtoCardOpen(AWTO_CARD_ROW0 + 3, AWTO_CT_AWTO);     // message, second line, pad row
    AwtoCardTxt(ucT);
    if(ucT == AWTO_CT_DDCCI)
    {
        AwtoPortName(SysSourceGetInputPort());
    }
    AwtoCardCentre(AWTO_CARD_ROW0, AWTO_T_STYLE_TEXT);
    if(ucT == AWTO_CT_PANEL)
    {
        AwtoCardTxt(AWTO_CT_ON + ((GET_OSD_PANEL_UNIFORMITY() == _ON) ? 0 : 1));
        AwtoCardCentre(AWTO_CARD_ROW0 + 1, AWTO_T_STYLE_TEXT);
    }
    else if((ucT == AWTO_CT_NOSIGNAL) || (ucT == AWTO_CT_NOCABLE) || (ucT == AWTO_CT_NOSUPPORT))
    {
        AwtoPortName(SysSourceGetInputPort());
        AwtoCardCentre(AWTO_CARD_ROW0 + 1, AWTO_T_STYLE_DIM);
    }
    AwtoCardShow();
}
