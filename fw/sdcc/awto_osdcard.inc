// AWTO user-facing OSD screens on the awto text layer (awto_dbgpop.inc helpers, menu font and colours), inserted into
// RTD2014OsdDisplay.c after awto_dbgpop.inc. The SDK timers and OSD states drive them as before; only the drawing is ours.
// - Message cards (#124): OsdDispOsdMessage (the SDK body is removed by keil2sdcc), incl. the ACTIVE input-info card.
// - Source selector (#134): one row per board port + Auto. Backlight bar (#132): UP / DOWN with a picture.
#if(!defined(_AWTO_NEW_SETTINGS))
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
#define AWTO_BAR_SURFACE    0                   // osd_tc_bar colours = awto-rtdfw osd.h AWTO_BAR_SURFACE / AWTO_BAR_ACCENT
#define AWTO_BAR_ACCENT     1

// Fixed texts: one table, read only by AwtoCardTxt (a constant read through a pointer sits in its reader's bank, awto-sdcc#39).
#define AWTO_CT_INPUT       0
#define AWTO_CT_AUTO        1
#define AWTO_CT_DP          2
#define AWTO_CT_HDMI        3
#define AWTO_CT_PORT        4
#define AWTO_CT_STATE       5                   // + ui_port_state: no cable, no signal, ready, ACTIVE
#define AWTO_UPS_DISABLED   4                   // ui_port_state: off by setting (awto-rtdfw ui.h UPS_DISABLED)
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
#define AWTO_CT_BACKLIGHT   58
#define AWTO_CT_DISABLED    59                  // selector state of a port off by setting (#81; ui_port_state 4)
static const __code char tAwtoCardS[] =
    "Input\0Auto select\0DP-1\0HDMI-\0Input D\0no cable\0no signal\0ready\0ACTIVE\0"
    "AWTO\0No signal\0No cable\0Not supported\0Auto adjust\0Auto colour\0DDC/CI on \0Power saving\0Panel uniformity\0On\0Off\0"
    "Information\0Resolution\0Refresh\0H frequency\0Pixel clock\0HDCP\0DP link\0Swing/pre\0Status\0"
    " Hz\0 kHz\0 MHz\0off\0 sink\0 repeater\0 lanes \0RBR\0HBR\0HBR2\0"
    "idle\0search\0scan\0stable\0measure\0timing ok\0display set\0active\0no signal\0no support\0sleep\0off\0fast path\0init\0"
    "HBR3\0Sync log\0no link\0TMDS \0Saving to memory\0Backlight\0disabled\0";

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

static BYTE AwtoSrcItemPort(BYTE ucItem)        // OSD input item -> port byte of the ring line (0xFF = Auto)
{
    return (ucItem == _OSD_INPUT_AUTO) ? 0xFF : (ucItem - _OSD_INPUT_D0 + _D0_INPUT_PORT);
}

static void AwtoSrcRing(BYTE ucEv, BYTE ucItem)  // one ring line per selector outcome (#132): AWTO_SEL_EV_*
{
    AwtoSyncPush(AWTO_SYNC_EV_SEL, ucEv, AwtoSrcItemPort(ucItem));
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

static void AwtoPortName(BYTE ucPort)          // "DP-1", "HDMI-n" (n-th HDMI port of the board), else "Input Dn" (Dan, 2026-11-12)
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
static const __code BYTE tAwtoSyncFmt[322] = {
    0x00, 0x0A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x00, 0x10, 0x0B, 0x0B, 0x0B,
    0x0B, 0x0B, 0x16, 0x16, 0x16, 0x16, 0x16, 0x00, 0x16, 0x0C, 0x0C, 0x8D, 0x0E, 0x0C, 0x0C, 0x0F,
    0x00, 0x01, 0x01, 0x01, 0x14, 0x14, 0x14, 0x14, 0x14, 0x14, 0x14, 0x14, 0x14, 0x14, 0x14, 0x0B,
    0x0B, 0x0B, 0x0B, 0x0B, 0x13, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B,
    0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x09, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x11, 0x12, 0x15, 0x15, 0x15, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x09, 0x00, 0x80,
    0x80, 0x80, 0x83, 0x87, 0x88, 0x80, 0x82, 0x85, 0x86, 0x00, 0x80, 0x80, 0x80, 0x80, 0x80, 0x83,
    0x80, 0x80, 0x80, 0x8B, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x0D, 0x01, 0x00,
    0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C,
    0x0C, 0x0C, 0x00, 0x00, 0x0C, 0x0C, 0x0C, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x00, 0x0C, 0x0C,
    0x0C, 0x0C, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00};
static const __code char tAwtoSyncTxtS[] = "boot: cold power-up (no valid canary in RAM)\0" "boot: watchdog bite, \x01" "\0" "boot: warm reset, no capture (host ISP 0xEE, or a hardware watchdog reset with interrupts off)\0" "boot: watchdog probe reset (test cmd 0x49 / 0x4F)\0" "boot: hardware watchdog reset, no capture (an early warning IRQ came)\0" "boot: main() entered\0" "boot: GPIO set up\0" "boot: MCU set up (M2PLL clock, flash clock, code banks, Timer2 tick)\0" "boot: pin functions set\0" "boot: first main-loop pass\0" "MCU init: crystal clock, watchdog N = \x01" "\0" "Timer2 1 ms tick running\0" "watchdog run-time: \x01" "\0" "NVRAM save start (since the last poke \x01" ")\0" "NVRAM save end (since the last poke \x01" ")\0" "flash erase start (since the last poke \x01" ")\0" "flash erase done (since the last poke \x01" ")\0" "NVRAM page move (since the last poke \x01" ")\0" "NVRAM flush (gate open): \x01" "\0" "NVRAM flush (forced after 30 s): \x01" "\0" "NVRAM flush (power off / saving entry): \x01" "\0" "NVRAM flush (menu / selector close): \x01" "\0" "NVRAM flush (test cmd 0x3D): \x01" "\0" "NVRAM write outside the gate: a second BriCon / ColorProc item while one waits, written at once by the SDK save\0" "NVRAM flush (DDC/CI save settings): \x01" "\0" "flash: type \x01" " found by the SDK (tFlashInformation index: 24 = MX25L8006E, 254 = none)\0" "(the 2 lines above repeated \x01" " more times)\0" "wake by the SDK source detect, not our poll (poll state \x01" ")\0" "host time \x01" "\0" "(fw +\x01" " ms, first host sync since boot)\0" "(fw +\x01" " ms, host sync after a drift)\0" "drift \x01" " (host - fw clock)\0" "power on\0" "switch to \x01" "\0" "wake on \x01" "\0" "power key on, \x01" "\0" "panel on requested by \x01" " (accepted)\0" "panel on requested by \x01" " (already on)\0" "panel off requested by \x01" " (accepted)\0" "panel off requested by \x01" " (already off)\0" "backlight on requested by \x01" " (accepted)\0" "backlight on requested by \x01" " (already on)\0" "backlight off requested by \x01" " (accepted)\0" "backlight off requested by \x01" " (already off)\0" "panel on requested by \x01" " (deferred: power off / saving takes the panel down)\0" "backlight on requested by \x01" " (deferred: power off / saving takes the panel down)\0" "backlight off requested by \x01" " (deferred: power off / saving takes the panel down)\0" "panel: OFF -> VDD (\x01" "): VDD on, T1 starts\0" "panel: VDD -> HPD (\x01" "): T1 done, power on, eDP-1 PHY on\0" "panel: VDD -> T6 (\x01" "): off before the PHY, VDD off\0" "panel: HPD -> LINK (\x01" "): eDP-1 HPD high, link training\0" "panel: HPD -> T6 (\x01" "): off, PHY and VDD off\0" "panel: LINK -> VIDEO (\x01" "): eDP-1 link trained in \x01" ", stream on\0" "panel: VIDEO -> T3 (\x01" "): backlight wanted, T3 counts from the stream start\0" "panel: VIDEO -> T4 (\x01" "): off, T4 starts\0" "panel: T3 -> VIDEO (\x01" "): backlight no longer wanted\0" "panel: T3 -> BL_PWM (\x01" "): T3 done, backlight pin on\0" "panel: BL_PWM -> BL_ON (\x01" "): PWM duty set\0" "panel: BL_PWM -> BL_OFF (\x01" "): backlight off wanted, PWM dark\0" "panel: BL_ON -> BL_OFF (\x01" "): PWM dark\0" "panel: BL_OFF -> VIDEO (\x01" "): backlight pin off, stream kept\0" "panel: BL_OFF -> T4 (\x01" "): backlight pin off, T4 starts\0" "panel: T4 -> VIDEO (\x01" "): on again, stream still on\0" "panel: T4 -> T5 (\x01" "): T4 done, stream idle\0" "panel: T5 -> VIDEO (\x01" "): on again, stream on\0" "panel: T5 -> T6 (\x01" "): T5 done, link and VDD off\0" "panel: T6 -> OFF (\x01" "): T6 done, VDD may come on again\0" "panel: OFF -> T6 (\x01" "): warm reset, VDD went off at GPIO init: T6 first\0" "panel: VIDEO -> T5 (\x01" "): off, backlight never on: no T4, stream idle\0" "panel: state change \x01" " (not a listed transition)\0" "panel: no eDP-1 HPD within T2, link training anyway\0" "eDP-1: link training FAIL\0" "panel VDD pin off, written outside the panel machine\0" "panel VDD pin on, written outside the panel machine\0" "panel VDD pin off again (already off), written outside the panel machine\0" "panel VDD pin on again (already on), written outside the panel machine\0" "backlight pin off, written outside the panel machine\0" "backlight pin on, written outside the panel machine\0" "backlight pin off again (already off), written outside the panel machine\0" "backlight pin on again (already on), written outside the panel machine\0" "backlight PWM written outside the panel machine\0" "system: \x01" "\0" "system: \x01" "\0" "LED: off (\x01" ")\0" "LED: on colour (\x01" ")\0" "LED: standby colour breathing (\x01" ")\0" "judge: source unstable\0" "judge: timing change\0" "judge: interlace change\0" "judge: memory / timing gen\0" "fast path refused: no cache\0" "fast path refused: receiver unstable\0" "fast path: SDK reset meanwhile\0" "fast path refused: timing field \x01" "\0" "hold: SDK reset\0" "HPD pulse (TMDS recover)\0" "HPD high again after 110 ms (TMDS recover)\0" "TMDS predetect on (clock not measured yet)\0" "TMDS clock \x01" " measured\0" "DP link \x01" " detected\0" "scan done: \x01" "\0" "signal lost\0" "timing \x01" "\0" "refresh \x01" "\0" "pixel clock \x01" "\0" "console opened (sync log)\0" "cable plugged in: wake\0" "EDID read by source: wake\0" "AUX command from source: wake\0" "DPCD 600h = D0 (source powers the link): wake\0" "cable unplugged: wake\0" "wake by TMDS clock, about \x01" " (IOSC reference)\0" "DDC activity in power saving: no wake (SDK DDC handshake gated, counted)\0" "DP AUX activity in power saving: no wake (SDK AUX toggle gated, counted)\0" "AUX command from source in power saving: no wake (wake: DPCD 600h = D0 or link training)\0" "TMDS clock burst \x01" " in power saving: shorter than the hold, no wake\0" "refused: no cable on \x01" "\0" "no cable on \x01" ", no signal, another port cabled: auto search\0" "input selector opened (SOURCE key) on \x01" "\0" "input selector opened (no-signal / wake card) on \x01" "\0" "input selector: \x01" " kept (no key for 2 s, the input it opened on), closed\0" "input selector: \x01" " kept (AUTO on the input it opened on), closed\0" "input selector cancelled (MENU): \x01" " kept\0" "input selector: \x01" " refused, no cable; stays open\0" "input selector: take ignored, DP version pop-up up\0" "input selector: item \x01" " is no port of this board; stays open\0" "input selector closed by a mode reset (SDK OSD reset): \x01" " kept\0" "console (opened by itself) closed by SOURCE: input selector next\0" "\x01" " disabled by setting (stored): HPD low, EDID off, receiver off, not searched\0" "\x01" " disabled by setting: HPD low, EDID off, receiver off, not searched\0" "\x01" " enabled by setting: HPD up, EDID on, receiver on, searched\0" "\x01" " enabled by the input selector: HPD up, EDID on, receiver on\0" "\x01" " enabled by input select (VCP 0x60 / menu / test cmd): HPD up, EDID on, receiver on\0" "disable \x01" " refused: the input on screen\0" "disable \x01" " refused: the last enabled input\0" "wake on \x01" " suppressed: input disabled (once per trigger per sleep)\0" "disable \x01" " requested: already disabled\0" "enable \x01" " requested: already enabled\0" "fixed search on disabled \x01" ": auto search\0" "speaker amp on (P7.4 = 1)\0" "speaker amp off (P7.4 = 0)\0" "amp aux pin low (P7.3 = 0)\0" "unmute during an audio test step without the amp: P7.4 stays 0\0" "audio test 1/6: speaker out, amp on, user volume\0" "audio test 2/6: speaker out, amp OFF (P7.4 = 0), user volume\0" "audio test 3/6: speaker out, amp on, -16.5 dB (Dahua default = volume 50)\0" "audio test 4/6: speaker out, amp on, -6 dB (= volume 100 now)\0" "audio test 5/6: speaker out, amp on, -3 dB\0" "audio test 6/6: speaker out, amp on, 0 dB (DVC maximum)\0" "audio test 1/6 done: amp and user volume back\0" "audio test 2/6 done: amp and user volume back\0" "audio test 3/6 done: amp and user volume back\0" "audio test 4/6 done: amp and user volume back\0" "audio test 5/6 done: amp and user volume back\0" "audio test 6/6 done: amp and user volume back\0" "audio test (no step): \x01" " Hz\0" "audio test 1: \x01" " Hz\0" "audio test 2: \x01" " Hz\0" "audio test 3: \x01" " Hz\0" "audio test 4: \x01" " Hz\0" "audio test 5: \x01" " Hz\0" "audio test 6: \x01" " Hz\0" "M-domain set-up: start\0" "M-domain set-up: IVS wait 1\0" "M-domain set-up: memory check (WD ctrl0 x 256 + status0 = \x01" ")\0" "M-domain set-up: memory + timing gen check OK (WD ctrl0 x 256 + status0 = \x01" ")\0" "DCLK fine tune: final offset \x01" "\0" "M-domain set-up: step lines stop after \x01" " this boot (the first set-up did not finish; later passes not logged)\0" "frame buffer forced (test cmd 0x0C): display setting re-run\0" "memory mode back to the SDK choice (test cmd 0x0D): display setting re-run\0" "frame buffer requested: already forced\0" "SDK memory choice requested: already\0" "memory force \x01" " stored (not ACTIVE): next display setting\0" "frame buffer refused: FRC not built (_AWTO_FRC off)\0" "memory select: frame-sync line buffer (force \x01" ")\0" "memory select: frame-sync frame buffer (force \x01" ")\0" "memory select: free-run frame buffer (force \x01" ")\0" "memory select: M/N frame-sync frame buffer (force \x01" ")\0" "memory select: free run, no input (force \x01" ")\0" "picture normal: display re-set\0" "picture mirrored left-right: display re-set\0" "picture mirrored top-bottom: display re-set\0" "picture rotated 180: display re-set\0" "picture normal: stored, applies at the next display setting\0" "picture mirrored left-right: stored, applies at the next display setting\0" "picture mirrored top-bottom: stored, applies at the next display setting\0" "picture rotated 180: stored, applies at the next display setting\0" "picture normal: already in effect\0" "picture mirrored left-right: already in effect\0" "picture mirrored top-bottom: already in effect\0" "picture rotated 180: already in effect\0" "picture normal: not built (no _AWTO_ROTATION): stored only\0" "picture mirrored left-right: not built (no _AWTO_ROTATION): stored only\0" "picture mirrored top-bottom: not built (no _AWTO_ROTATION): stored only\0" "picture rotated 180: not built (no _AWTO_ROTATION): stored only\0" "OSD rotated 180 with the picture\0" "OSD upright\0" "wake suppressed (cable, once per sleep): \x01" "\0" "wake suppressed (EDID read, once per sleep): \x01" "\0" "wake suppressed (AUX command, once per sleep): \x01" "\0" "wake suppressed (DPCD 600h, once per sleep): \x01" "\0" "wake suppressed (cable unplug, once per sleep): \x01" "\0" "wake suppressed (TMDS clock, once per sleep): \x01" "\0" "AC ON\0" "OFF\0" "INITIAL\0" "SEARCH\0" "DISPLAY SETTING\0" "ACTIVE\0" "FAST SWITCH\0" "HOLD L1\0" "NO SUPPORT\0" "NO SIGNAL\0" "POWER SAVING\0" "WAKE SEARCH\0" "POWER DOWN\0" "RESET\0" "POWER key\0" "front key in power saving\0" "test cmd 0x3E (POWER key)\0" "DDC/CI VCP D6 power mode\0" "input select (KVM / VCP 0x60 / menu / test cmd)\0" "input selector\0" "dead port: auto search\0" "our wake poll\0" "SDK power-saving source detect\0" "SDK cable reset (search port cable changed)\0" "no-signal cards: power-saving timer\0" "settings (aspect / overscan / DP version)\0" "SDK OSD (user adjust)\0" "hold L2 released: no-signal path (power-saving timers)\0" "hold: signal back, fast wake\0" "fast path taken (cached input)\0" "fast path: picture up\0" "fast path timeout: full path\0" "fast wake timeout: back to the hold\0" "judge timer: timing not confirmed (no signal)\0" "judge timer: no support\0" "NVRAM power status at boot\0" "SDK\0" "wake search found no source\0" "target written without a request\0" "hold: fast wakes used up\0" "hold: auto search, other cable\0" "INITIAL done\0" "timing confirmed, supported\0" "search done, no source\0" "display set, panel video ready\0" "judge: source unstable\0" "judge: timing change\0" "judge: interlace change\0" "judge: memory / timing gen\0" "judge: eDP unstable\0" "signal lost: L1 hold (backlight off, set-up kept)\0" "panel down (T4 / T5 done)\0" "power off / saving called off\0" "system machine started\0" "AUTO key: auto source select\0" "UP+DOWN in power saving: wake into the console\0" "input selector: no key for 2 s (idle commit)\0" "input selector closed by a mode reset: its highlighted input\0" "test cmd 0x0C / 0x0D (memory mode)\0" "power off\0" "power on\0" "power saving\0" "reset to search\0" "display setting again\0" "display setting again (no forced background)\0" "no support\0" "no signal\0" "power-saving reset\0" "power-off reset\0" "factory mode\0" "fast switch\0" "back to the hold\0" "fast path done\0" "accepted\0" "already\0" "replaces a pending request\0" "refused in this state\0" "kept until the state allows it\0" "dropped: the no-signal search found a timing first\0" " -> \0" " (\0" " ms): \0" " requested by \0" "; \0" "monitor off, inputs not searched\0" "monitor off, inputs not searched\0" "scaler input side reset for a new search\0" "finding a source (cable, clock / link, stable timing)\0" "scaler set-up for the timing\0" "picture on screen\0" "timing outside what scaler / panel accept\0" "search found no source\0" "no signal, low power, waiting for a wake\0" "boot (cold power-up: panel early)\0" "boot (warm reset: after T6)\0" "power switch OFF -> NORMAL\0" "power switch POWER SAVING -> NORMAL (wake)\0" "our wake poll (console + backlight)\0" "power off / saving: panel down first\0" "power off / saving called off: previous level\0" "display setting / ACTIVE gate: video wanted\0" "display setting: backlight action off\0" "display setting: DCLK change\0" "SDK OSD reset\0" "first ACTIVE pass\0" "L1 hold: signal lost\0" "hold: signal back, fast wake\0" "input selector opened\0" "SDK OSD: no-signal card\0" "SDK OSD: no-cable card\0" "SDK OSD: no-support card\0" "SDK OSD: source menu\0" "SDK OSD: power-saving card\0" "SDK OSD: DP info\0" "FreeSync OD measure\0" "SDK power switch: AC ON -> OFF\0" "SDK power switch: NORMAL -> OFF\0" "SDK power switch: NORMAL -> POWER SAVING\0" "UP+DOWN wake (console + backlight)\0" "";
static const __code WORD tAwtoSyncTxtOff[322] = {0, 45, 68, 163, 213, 283, 304, 322, 391, 415, 442, 482, 507, 528, 569, 608, 650, 691, 731, 758, 793, 835, 874, 905, 1017, 1055, 1141, 1183, 1242, 1254, 1293, 1329, 1355, 1364, 1376, 1386, 1402, 1437, 1474, 1510, 1549, 1588, 1629, 1669, 1712, 1788, 1868, 1949, 1990, 2045, 2095, 2149, 2192, 2253, 2327, 2366, 2417, 2468, 2509, 2569, 2606, 2665, 2719, 2769, 2811, 2855, 2902, 2955, 3025, 3093, 3141, 3193, 3219, 3272, 3324, 3397, 3468, 3521, 3573, 3646, 3717, 3765, 3775, 3785, 3798, 3817, 3851, 3874, 3895, 3919, 3946, 3974, 4011, 4042, 4076, 4092, 4117, 4160, 4203, 4225, 4244, 4257, 4269, 4278, 4288, 4302, 4328, 4351, 4377, 4407, 4453, 4475, 4520, 4593, 4666, 4755, 4822, 4845, 4904, 4944, 4995, 5067, 5131, 5171, 5219, 5270, 5330, 5392, 5457, 5535, 5604, 5665, 5727, 5812, 5851, 5893, 5959, 5997, 6033, 6073, 6099, 6126, 6153, 6216, 6265, 6326, 6400, 6462, 6505, 6561, 6607, 6653, 6699, 6745, 6791, 6837, 6864, 6883, 6902, 6921, 6940, 6959, 6978, 7001, 7029, 7090, 7167, 7198, 7308, 7368, 7443, 7482, 7519, 7576, 7628, 7676, 7725, 7772, 7825, 7869, 7900, 7944, 7988, 8024, 8084, 8157, 8230, 8295, 8329, 8376, 8423, 8462, 8521, 8593, 8665, 8729, 8762, 8774, 8817, 8864, 8913, 8960, 9010, 9058, 9064, 9068, 9076, 9083, 9099, 9106, 9118, 9126, 9137, 9147, 9160, 9172, 9183, 9189, 9199, 9225, 9251, 9276, 9324, 9339, 9362, 9376, 9407, 9451, 9487, 9529, 9551, 9606, 9635, 9666, 9688, 9717, 9753, 9799, 9823, 9850, 9854, 9882, 9915, 9940, 9971, 9984, 10012, 10035, 10066, 10089, 10110, 10134, 10161, 10181, 10231, 10257, 10287, 10310, 10339, 10386, 10431, 10492, 10527, 10537, 10546, 10559, 10575, 10597, 10642, 10653, 10663, 10682, 10698, 10711, 10723, 10740, 10755, 10764, 10772, 10799, 10821, 10852, 10903, 10908, 10911, 10918, 10933, 10936, 10969, 11002, 11043, 11097, 11126, 11144, 11186, 11209, 11250, 11284, 11312, 11339, 11382, 11418, 11455, 11501, 11545, 11583, 11612, 11626, 11644, 11665, 11694, 11716, 11740, 11763, 11788, 11809, 11836, 11853, 11873, 11904, 11936, 11977};
static BYTE AwtoSyncTxt(WORD usRow, BYTE ucPart)   // text after ucPart (0..2) value marks, 0xFF = none; returns the fmt
{                                                  // usRow: logged row, or AWTO_SYNC_NAME_ROW0 + name row
    const __code char *pc = &tAwtoSyncTxtS[tAwtoSyncTxtOff[usRow]];

    if(ucPart == 0xFF)
    {
        return tAwtoSyncFmt[usRow];
    }
    if(ucPart != 0)                             // at most two marks (ms2); ucPart is not written (no XDATA copy)
    {
        while((*pc != 0) && (*pc != 1))
        {
            pc++;
        }
        if(*pc == 0)
        {
            return tAwtoSyncFmt[usRow];
        }
        pc++;
        if(ucPart == 2)
        {
            while((*pc != 0) && (*pc != 1))
            {
                pc++;
            }
            if(*pc == 0)
            {
                return tAwtoSyncFmt[usRow];
            }
            pc++;
        }
    }
    while((*pc != 0) && (*pc != 1))             // AwtoPutChar inlined: no call, so the packer keeps the table in this bank
    {
        if(s_bAwtoSkip != 0)
        {
            if(--s_ucLogI == 0)                 // second pass of a wrapped console line: dropped
            {
                s_bAwtoSkip = 0;
            }
        }
        else if(s_ucAwtoLen < s_ucAwtoCols)
        {
            s_pcAwtoRow[s_ucAwtoLen++] = *pc;
        }
        else if(s_bAwtoWrap != 0)
        {
            s_bAwtoOver = 1;                    // main-page log: the line takes two rows (AwtoConWrapLine)
        }
        pc++;
    }
    return tAwtoSyncFmt[usRow];
}
#define AWTO_SYNC_NAME_FIRST 0x15
#define AWTO_SYNC_NAME_ROW0 203                 // text row of name row 0 (= the logged rows)
#define AWTO_SYNC_NAME_IDS 7
#define AWTO_SYNC_NAME_ARGS 64
static const __code BYTE tAwtoSyncNameRow[448] = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 55, 56, 57, 58,
    59, 42, 43, 0, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 60, 61, 62, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 63, 64, 65, 66, 67, 68, 69, 70, 0, 0, 0, 0, 0, 0, 0,
    71, 72, 73, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    74, 75, 76, 77, 78, 79, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    80, 0, 81, 82, 83, 84, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    85, 86, 87, 88, 89, 90, 0, 0, 91, 92, 93, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
// GENERATED-END awto_sync_text

static __xdata BYTE s_pucSrcSt[3];              // last drawn: port state, sync stage, rate checksum
static __xdata BYTE s_pucSrcStage[3];
static __xdata WORD s_pusSrcRate[3];             // rate change key (AwtoSrcRateKey)
static __xdata BYTE s_pucSrcSig[AWTO_PS_N];     // last drawn value per signal row
static __xdata BYTE s_pucSrcCnt[(AWTO_PS_CNT_N != 0) ? AWTO_PS_CNT_N : 1];   // edge counter at the last poll
static __xdata WORD s_usSrcPoll;
static __xdata BYTE s_ucSrcLogSeq;              // ring seq the log pane shows up to

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

// #162 step 3: a name from a sync.tsv table row (id 15..18): the row text, or the code in hex when there is no row
static void AwtoSyncName(BYTE ucId, BYTE ucArg)    // no locals: XDATA is full (#162 step 3)
{
    if(((BYTE)(ucId - AWTO_SYNC_NAME_FIRST) < AWTO_SYNC_NAME_IDS) && (ucArg < AWTO_SYNC_NAME_ARGS) &&
       (tAwtoSyncNameRow[(WORD)(ucId - AWTO_SYNC_NAME_FIRST) * AWTO_SYNC_NAME_ARGS + ucArg] != 0))
    {
        AwtoSyncTxt(AWTO_SYNC_NAME_ROW0 - 1 + tAwtoSyncNameRow[(WORD)(ucId - AWTO_SYNC_NAME_FIRST) * AWTO_SYNC_NAME_ARGS + ucArg], 0);
        return;
    }
    AwtoPutHex2(ucArg);
}

// One sync-ring entry as a log line: "+  260 ms D2 timing 3840x2160" (texts and formats: fw/awto/sync.tsv).
static __xdata DWORD s_ulAwtoLnV;               // #157: value + time in XDATA (DATA overlay path depth, see AwtoPutIso)
static __xdata WORD s_usAwtoLnMs;

static void AwtoPutNvFlush(void);              // #151 fmt nvw: awto_nvpop.inc (last in this file: no string renumbering)
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
    for(ucFmt = (usMs < 10) ? 4 : (usMs < 100) ? 3 : (usMs < 1000) ? 2 : (usMs < 10000) ? 1 : 0; ucFmt != 0; ucFmt--)
    {
        AwtoPutChar(' ');                       // not AwtoPutCol: a skipped pass (AwtoConWrapLine) does not move the row length
    }
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
    ucFmt = AwtoSyncTxt(ucRow - 1, 0xFF);        // 0xFF = nothing printed, the fmt only
    if((ucFmt & 0x80) != 0)
    {
        AwtoPortName(puc[1]);
        AwtoPutChar(' ');
    }
    AwtoSyncTxt(ucRow - 1, 0);
    switch(ucFmt & 0x7F)
    {
        case 1:                                 // vport
            if(puc[7] == 0xFF) AwtoPutStr("auto");
            else { AwtoPortName(puc[7]); }
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
        case 16:                                                                                   // wdt: warning ms << 16 | reset ms
            AwtoPutStr("warning "); AwtoPutNum(ulV >> 16, 1); AwtoPutStr(" ms, reset "); AwtoPutNum(ulV & 0xFFFF, 1); AwtoPutStr(" ms");
            break;
        case 17:                                                                                   // sys: old -> new (ms in old): why
            AwtoSyncName(AWTO_SYNC_EV_SYS_STATE, puc[1] >> 4); AwtoSyncName(AWTO_SYNC_EV_SYS_SEP, 0);
            AwtoSyncName(AWTO_SYNC_EV_SYS_STATE, puc[1] & 0x0F); AwtoSyncName(AWTO_SYNC_EV_SYS_SEP, 2);
            AwtoPutNum(ulV & AWTO_SYS_MS_MAX, 1); AwtoSyncName(AWTO_SYNC_EV_SYS_SEP, 3);
            AwtoSyncName(AWTO_SYNC_EV_SYS_WHY, puc[4] & AWTO_SYS_WHY_CODE);
            if((puc[4] & AWTO_SYS_WHY_MODE) != 0)                                                  // #162 s3b: the SDK mode changed
            {
                AwtoSyncName(AWTO_SYNC_EV_SYS_SEP, 5); AwtoSyncName(AWTO_SYNC_EV_SYS_MODE, puc[1] & 0x0F);
            }
            break;
        case 18:                                                                                   // sysreq: request by who (outcome)
            AwtoSyncName(AWTO_SYNC_EV_SYS_REQNAME, puc[1]); AwtoSyncName(AWTO_SYNC_EV_SYS_SEP, 4);
            AwtoSyncName(AWTO_SYNC_EV_SYS_WHY, puc[6]); AwtoSyncName(AWTO_SYNC_EV_SYS_SEP, 2);
            AwtoSyncName(AWTO_SYNC_EV_SYS_OUTCOME, puc[7]); AwtoPutChar(')');
            break;
        case 19:                                                                                   // ms2: low word ms % ... high word ms % (#162 s3b)
            AwtoPutNum(ulV & 0xFFFF, 1); AwtoPutStr(" ms"); AwtoSyncTxt(ucRow - 1, 1);
            AwtoPutNum(ulV >> 16, 1); AwtoPutStr(" ms"); AwtoSyncTxt(ucRow - 1, 2);
            return;                                 // its own tail: no fmt kept over the calls (DATA overlay path, #162 s3b)
        case 20: AwtoSyncName(AWTO_SYNC_EV_PNL_BY, puc[7]); break;                                 // pby: panel requester (#162 s3b)
        case 21: AwtoSyncName(AWTO_SYNC_EV_SYS_STATE, puc[7]); break;                              // sname: system state (#95 LED)
        case 22: AwtoPutNvFlush(); break;                                                          // nvw: NVRAM flush result (#151)
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
        if(g_stAwtoFreq.ucValid != 0)
        {
            AwtoPutMilli(g_stAwtoFreq.ulVFreqmHz);
            AwtoPutStr("Hz ");
            AwtoPutMilli(g_stAwtoFreq.ulPclkHz / 1000);
            AwtoPutStr("MHz");
            return;
        }
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
        if(g_stAwtoFreq.ucValid != 0)
        {
            return 0x8000 ^ GET_INPUT_TIMING_HWIDTH() ^ (GET_INPUT_TIMING_VHEIGHT() << 4) ^ (WORD)g_stAwtoFreq.ulVFreqmHz ^
                   (WORD)(g_stAwtoFreq.ulPclkHz >> 10);
        }
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
        AwtoCardTxt((ucV == AWTO_UPS_DISABLED) ? AWTO_CT_DISABLED : (AWTO_CT_STATE + ucV));
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
    s_usSrcPoll = ((WORD)AwtoMs());
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
    if(AwtoSourceNoPicture() == _TRUE)
    {
        ScalerTimerReactiveTimerEvent(SEC(AWTO_SRC_SLEEP_SEC), _USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
    }
    else
    {
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
    }
}

// The one way in (SOURCE, OSD event 7 = no signal / wake): preset to the current input (Auto while auto-scanning).
// Opening alone arms no idle commit: the selector stays (#139) until a step key starts the AWTO_SRC_IDLE_COMMIT_MS wait.
void AwtoSourceOpen(BYTE ucWhy)
{
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
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
    AwtoSrcRing(ucWhy, g_usBackupValue);
    AwtoCardOpenW(AWTO_SRC_COLS, AWTO_SRC_LINES, AWTO_CT_INPUT);
    AwtoSourceRows();
    AwtoCardShow();
    UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, AWTO_PNL_BY_SELECTOR));
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

// Auto source select (#132): the selector's Auto row and the AUTO key with nothing open. The SDK auto search takes the first input
// with a signal; the scan type is stored at the gate ("Saving to memory"). ucWho = AWTO_SYS_BY_* of the request line.
void AwtoSourceAuto(BYTE ucWho)
{
    SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_AUTO);
    AwtoSyncBegin(AWTO_SYNC_K_SWITCH, 0xFF);
    SysSourceSetScanType(_SOURCE_SWITCH_AUTO_IN_GROUP);
    SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_SEARCH, ucWho);
    UserCommonNVRamSetSystemData(_SOURCE_SCAN_TYPE, SysSourceGetScanType());
    AwtoNvCommitSel();                          // #151: the chosen input is stored at the gate ("Saving to memory")
}

// Take the highlighted item: AUTO key (AWTO_SYS_BY_SELECTOR) or the idle commit (AWTO_SYS_BY_SELECTOR_IDLE).
static void AwtoSourceTake(BYTE ucWho)
{
    BYTE ucItem = GET_OSD_INPUT_PORT_OSD_ITEM();
    BYTE ucPort;

    if(GET_OSD_DP_VERSION_HOTKEY_DISP() != _OFF)
    {
        AwtoSrcRing(AWTO_SEL_EV_DPVER, ucItem);
        return;
    }
    if(g_usBackupValue == ucItem)
    {
        AwtoSrcRing((ucWho == AWTO_SYS_BY_SELECTOR_IDLE) ? AWTO_SEL_EV_KEPT_IDLE : AWTO_SEL_EV_KEPT_AUTO, ucItem);
        AwtoSourceClose();
    }
    else if(ucItem == _OSD_INPUT_AUTO)
    {
        AwtoSourceAuto(ucWho);
    }
    else
    {
        ucPort = (ucItem >= _OSD_INPUT_D0) ? (ucItem - _OSD_INPUT_D0 + _D0_INPUT_PORT) : _NO_INPUT_PORT;
        if(ucPort == _NO_INPUT_PORT)
        {
            AwtoSyncPush(AWTO_SYNC_EV_SEL, AWTO_SEL_EV_NOPORT, ucItem);    // not a port of this board: the selector stays up
            return;
        }
        if(AwtoPortCable(ucPort) == _FALSE)
        {
            AwtoSwEvent(AWTO_SW_EV_DEADPORT, 1);    // #84: no cable on the chosen port: refused, the selector stays up
            AwtoSrcRing(AWTO_SEL_EV_NOCABLE, ucItem);
            return;
        }
        AwtoPortSelect(ucPort, AWTO_PORT_WHY_SELECTOR);     // #81: a disabled port is enabled (stored), then the switch
        SET_FORCE_POW_SAV_STATUS(_FALSE);
        SysSourceSwitchInputPort(ucPort);
        SysSourceSetScanType(_SOURCE_SWITCH_FIXED_PORT);
        SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_SEARCH, ucWho);
        UserCommonNVRamSetSystemData(_SEARCH_PORT, SysSourceGetInputPort());
        UserCommonNVRamSetSystemData(_SOURCE_SCAN_TYPE, SysSourceGetScanType());
        AwtoNvCommitSel();                      // #151: the chosen input is stored at the gate ("Saving to memory")
    }
    SET_OSD_STATE(_MENU_NONE);
}

void AwtoSourceIdle(void)                       // OSD_DISABLE timer, selector open: no key for AWTO_SRC_IDLE_COMMIT_MS
{
    AwtoSourceTake(AWTO_SYS_BY_SELECTOR_IDLE);
}

// SDK OSD reset (mode reset, signal back in no signal) with the selector open: a highlighted other input is taken (the
// user's choice, never dropped silently, #132); else one line says what closed it. OsdDispDisableOsd follows in the caller.
void AwtoSourceReset(void)
{
    BYTE ucItem = GET_OSD_INPUT_PORT_OSD_ITEM();

    if(GET_OSD_STATE() != _MENU_HOTKEY_SOURCE)
    {
        return;
    }
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
    if(ucItem != g_usBackupValue)
    {
        AwtoSourceTake(AWTO_SYS_BY_SELECTOR_RESET);
        if(GET_OSD_STATE() != _MENU_HOTKEY_SOURCE)
        {
            return;                             // taken: switch + request lines
        }
    }
    AwtoSrcRing(AWTO_SEL_EV_RESET, ucItem);     // nothing to take, or the take refused (its line came first)
}

// Selector open (_MENU_HOTKEY_SOURCE), key from the key router (#129). Roles as before #132: AUTO takes, MENU cancels.
// SOURCE / UP step forward, DOWN back (wrap); every step restarts the idle commit.
void AwtoSourceKey(BYTE ucKey)
{
    if((ucKey == _RIGHT_KEY_MESSAGE) || (ucKey == _LEFT_KEY_MESSAGE) || (ucKey == AWTO_KEY_MSG_SOURCE))
    {
        AwtoSourceStep(ucKey == _LEFT_KEY_MESSAGE);
        AwtoSourceRows();
        AwtoSrcSleepArm();                      // #151: a step is never stored
        ScalerTimerReactiveTimerEvent(AWTO_SRC_IDLE_COMMIT_MS, _USER_TIMER_EVENT_OSD_DISABLE);
    }
    else if(ucKey == _EXIT_KEY_MESSAGE)        // MENU: cancel, the choice goes back
    {
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
        if(g_usBackupValue != GET_OSD_INPUT_PORT_OSD_ITEM())
        {
            SET_OSD_INPUT_PORT_OSD_ITEM(g_usBackupValue);
        }
        AwtoSrcRing(AWTO_SEL_EV_CANCEL, g_usBackupValue);
        AwtoSourceClose();
    }
    else if(ucKey == _MENU_KEY_MESSAGE)        // AUTO: take the choice now
    {
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
        AwtoSourceTake(AWTO_SYS_BY_SELECTOR);
    }
}

//---- backlight bar (#132): UP / DOWN with a picture and nothing open. One card row: bar (OSD windows) + value. ----
extern void osd_tc_bar_off(BYTE ucWin);
#define AWTO_BL_ROW         AWTO_CARD_ROW0
#define AWTO_BL_BAR_COL     1                   // bar: cells 1..AWTO_BL_VAL_COL - 2, value right of it
#define AWTO_BL_VAL_COL     23
#define AWTO_BL_VAL_W       4                   // "100%"
#define AWTO_BL_MAX         100                 // registry brightness max (percent)
#define AWTO_WIN_BL_EDGE    3                   // bar outline (accent), inside (surface), fill (accent): above the card windows 0..2
#define AWTO_WIN_BL_IN      4
#define AWTO_WIN_BL_FILL    5
#define AWTO_BL_X0          ((WORD)AWTO_BL_BAR_COL * osd_cw)
#define AWTO_BL_X1          ((WORD)(AWTO_BL_VAL_COL - 1) * osd_cw - 1)
#define AWTO_BL_Y0          ((WORD)AWTO_BL_ROW * osd_rh + 3)
#define AWTO_BL_Y1          ((WORD)(AWTO_BL_ROW + 1) * osd_rh - 4)
#define AWTO_BL_INSET       3                   // fill inset from the outline, px (1 px edge, 2 px surface gap)

static void AwtoBlDraw(void)                    // fill width and value text of the stored backlight
{
    BYTE ucV = (BYTE)AWTO_SET(BRIGHTNESS);
    WORD usW = (AWTO_BL_X1 - AWTO_BL_X0 - 2 * AWTO_BL_INSET) * ucV / AWTO_BL_MAX;

    if(usW == 0)
    {
        osd_tc_bar_off(AWTO_WIN_BL_FILL);
    }
    else
    {
        osd_tc_bar(AWTO_WIN_BL_FILL, AWTO_BL_X0 + AWTO_BL_INSET, AWTO_BL_Y0 + AWTO_BL_INSET, AWTO_BL_X0 + AWTO_BL_INSET + usW - 1,
                   AWTO_BL_Y1 - AWTO_BL_INSET, AWTO_BAR_ACCENT);
    }
    AwtoFieldBegin();
    AwtoPutNum(ucV, 1);
    AwtoPutChar('%');
    AwtoPutCol(AWTO_BL_VAL_W);
    AwtoFieldEnd(AWTO_BL_ROW, AWTO_BL_VAL_COL, AWTO_T_STYLE_TEXT);
}

void AwtoBlKey(BYTE ucKey)                      // UP = brighter, DOWN = darker; the first press opens the bar
{
    extern unsigned char set_put(unsigned char ucId, int iV, unsigned char ucNow);

    if(GET_OSD_STATE() != _MENU_HOTKEY_BACKLIGHT)
    {
        AwtoCardOpen(AWTO_CARD_ROW0 + 2, AWTO_CT_BACKLIGHT);
        osd_tc_place(50, AWTO_BL_VPOS_PCT, GET_OSD_NVRAM_DOUBLE_SIZE());
        osd_tc_bar(AWTO_WIN_BL_EDGE, AWTO_BL_X0, AWTO_BL_Y0, AWTO_BL_X1, AWTO_BL_Y1, AWTO_BAR_ACCENT);
        osd_tc_bar(AWTO_WIN_BL_IN, AWTO_BL_X0 + 1, AWTO_BL_Y0 + 1, AWTO_BL_X1 - 1, AWTO_BL_Y1 - 1, AWTO_BAR_SURFACE);
        AwtoTextLine(AWTO_BL_ROW, AWTO_T_STYLE_TEXT);
        SET_OSD_STATE(_MENU_HOTKEY_BACKLIGHT);
    }
    set_put(AWTO_SET_BRIGHTNESS, AWTO_SET(BRIGHTNESS) + ((ucKey == _RIGHT_KEY_MESSAGE) ? AWTO_BL_KEY_STEP : -AWTO_BL_KEY_STEP), 1);
    AwtoBlDraw();
    AwtoCardShow();
}

void AwtoBlClose(void)                          // another key: the bar goes first (OsdDispDisableOsd commits the value)
{
    OsdDispDisableOsd();
}

// #139 console auto-open: once per episode, when the screen is ours to take (no menu / selector / logo / hold) and the
// episode has settled (ACTIVE / no signal / no support / power saving): opening it never delays the sync. Setting: registry
// sync_console (id 110); g_ucAwtoSyncCon = 0 also stops it (test harness, fw_sim osd_render.Session).
__xdata BYTE g_ucAwtoSyncCon = 1;
__xdata BYTE g_ucAwtoConAuto;                   // the console open now opened itself (not UP+DOWN / test cmd): SOURCE passes (#132)

static void AwtoSyncConPoll(void)
{
    if(g_stAwtoSync.ucOpenReq == 0)
    {
        return;
    }
    if(g_stAwtoSync.ucOpenReq == AWTO_SYNC_OPEN_KEY)    // #132 UP+DOWN wake: waits through the wake, only POWER off drops it
    {
        if(SysPowerGetPowerStatus() == _POWER_STATUS_OFF)
        {
            g_stAwtoSync.ucOpenReq = 0;
            return;
        }
    }
    else if((g_ucAwtoSyncCon == 0) || (AWTO_SET(SYNC_CONSOLE) == 0) || (GET_OSD_STATE() == _MENU_HOTKEY_SOURCE) ||
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
        BYTE ucP = s_ucConOpen;                 // open since power-on: display setting's panel cycle blanks the OSD;

        g_stAwtoSync.ucOpenReq = 0;             // redraw it as UP+DOWN opens it (re-applying the scroll alone stayed blank)
        s_ucConOpen = 0;
        AwtoDiagConsole(ucP);
        return;
    }
    if((SysPowerGetPowerStatus() != _POWER_STATUS_NORMAL) || (GET_OSD_STATE() != _MENU_NONE) || (g_ucAwtoMenuOn != 0) || AWTO_KEY_TEST_ON() ||
       (g_stAwtoDiag.ucHold != 0))
    {
        return;
    }
    g_ucAwtoConAuto = (g_stAwtoSync.ucOpenReq != AWTO_SYNC_OPEN_KEY);
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
    if((g_stAwtoSync.ucOpenReq != AWTO_SYNC_OPEN_KEY) && ((g_ucAwtoSyncCon == 0) || (AWTO_SET(SYNC_CONSOLE) == 0)))
    {
        return;
    }
    ScalerDDomainBackgroundEnable(_ENABLE);    // black frame under the OSD: also the short T3 (own pattern) at panel on
    AwtoSyncPush(AWTO_SYNC_EV_CONSOLE, 0, 0);
    s_ucConOpen = 0;                            // wake: power saving lost the OSD of a console left open; draw it anew
    AwtoDiagConsole(1);
    g_ucAwtoConAuto = (g_stAwtoSync.ucOpenReq != AWTO_SYNC_OPEN_KEY);
}
#endif

// Every main-loop pass (AwtoGpioPoll): console log lines, auto-open, selector fields every AWTO_SRC_POLL_MS.
void AwtoOsdSyncPoll(void)
{
    WORD usDt;                                  // ms since the last selector poll (XDATA local: one WORD, #157 merge)
    BYTE ucI;

    if(s_ucConOpen != 0)
    {
        if(s_ucConRedraw != 0)                  // terminal reached the roll-up limit: one full redraw, then it rolls again
        {
            s_ucConOpen = 0;
            AwtoDiagConsole(AWTO_CON_MAIN);
        }
        AwtoConLogSync();
        AwtoConTitlePoll();                     // #157 live title fields
    }
    AwtoSyncConPoll();
    if((GET_OSD_STATE() != _MENU_HOTKEY_SOURCE) || (g_ucOsdWidth != AWTO_SRC_COLS))
    {
        return;
    }
    usDt = ((WORD)AwtoMs()) - s_usSrcPoll;
    if(usDt < AWTO_SRC_POLL_MS)
    {
        return;
    }
    s_usSrcPoll += usDt;
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
        if(g_stAwtoFreq.ucValid != 0)
        {
            AwtoPutMilli(g_stAwtoFreq.ulVFreqmHz);
        }
        else
        {
            AwtoInfoTenths(GET_INPUT_TIMING_VFREQ());
        }
        AwtoCardTxt(AWTO_CT_HZ);
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
        AwtoInfoLabel(AWTO_CT_HFREQ);
        if(g_stAwtoFreq.ucValid != 0)
        {
            AwtoPutMilli(g_stAwtoFreq.ulHFreqHz);
        }
        else
        {
            AwtoInfoTenths(GET_INPUT_TIMING_HFREQ());
        }
        AwtoCardTxt(AWTO_CT_HZ + 1);
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
        AwtoInfoLabel(AWTO_CT_PCLK);
        if(g_stAwtoFreq.ucValid != 0)
        {
            AwtoPutMilli(g_stAwtoFreq.ulPclkHz / 1000);
        }
        else
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
