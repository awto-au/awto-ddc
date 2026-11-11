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
static const __code char tAwtoCardS[] =
    "Input\0Auto select\0DisplayPort\0HDMI \0Input D\0no cable\0no signal\0ready\0ACTIVE\0"
    "AWTO\0No signal\0No cable\0Not supported\0Auto adjust\0Auto colour\0DDC/CI on \0Power saving\0Panel uniformity\0On\0Off\0"
    "Information\0Resolution\0Refresh\0H frequency\0Pixel clock\0HDCP\0DP link\0Swing/pre\0Status\0"
    " Hz\0 kHz\0 MHz\0off\0 sink\0 repeater\0 lanes \0RBR\0HBR\0HBR2\0";

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
static void AwtoCardOpen(BYTE ucLines, BYTE ucTitle)
{
    WORD usW, usH;

    osd_tc_open(AWTO_CARD_COLS, ucLines);
    osd_font_load(ui_font_selected());
    usW = (WORD)AWTO_CARD_COLS * osd_cw;
    usH = (WORD)ucLines * osd_rh;
    osd_tc_bar(AWTO_WIN_FRAME, 0, 0, usW - 1, usH - 1, 1);
    osd_tc_bar(AWTO_WIN_INSET, 2, 2, usW - 3, usH - 3, 0);
    osd_tc_bar(AWTO_WIN_TITLE, 2, 2, usW - 3, osd_rh - 1, 1);
    osd_tc_place(50, 50, GET_OSD_NVRAM_DOUBLE_SIZE());
    s_ucPanelRow = 0;
    s_ucPanelCol = 0;
    s_ucAwtoCols = AWTO_CARD_COLS;
    s_pcAwtoRow[0] = ' ';
    s_ucAwtoLen = 1;
    AwtoCardTxt(ucTitle);
    AwtoTextLine(0, AWTO_T_STYLE_ONACC);
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

static void AwtoSourceRows(void)                // Auto, then each port with its state; the selection on the bar
{
    BYTE ucSel = AwtoSrcSel();
    BYTE ucI, ucSt;

    osd_tc_bar(AWTO_WIN_HL, 2, (WORD)(AWTO_SRC_ROW0 + ucSel) * osd_rh, (WORD)AWTO_CARD_COLS * osd_cw - 3,
               (WORD)(AWTO_SRC_ROW0 + ucSel + 1) * osd_rh - 1, 1);
    for(ucI = 0; ucI <= AWTO_SRC_PORTS; ucI++)
    {
        if(ucI == 0)
        {
            AwtoCardTxt(AWTO_CT_AUTO);
        }
        else
        {
            AwtoPortName(AwtoSrcPort(ucI));
        }
        AwtoTextLine(AWTO_SRC_ROW0 + ucI, (ucI == ucSel) ? AWTO_T_STYLE_ONACC : AWTO_T_STYLE_TEXT);
        if(ucI != 0)
        {
            ucSt = ui_port_state(AwtoSrcPort(ucI) - _D1_INPUT_PORT);
            AwtoFieldBegin();
            AwtoCardTxt(AWTO_CT_STATE + ucSt);
            AwtoFieldEnd(AWTO_SRC_ROW0 + ucI, AWTO_SRC_STATE_COL, (ucI == ucSel) ? AWTO_T_STYLE_ONACC : ((ucSt == 3) ? AWTO_T_STYLE_TEXT : AWTO_T_STYLE_DIM));
        }
    }
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
    AwtoCardOpen(AWTO_SRC_ROW0 + AWTO_SRC_PORTS + 2, AWTO_CT_INPUT);   // + Auto + pad row (the frame covers the last 2 px)
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
        AwtoSrcSleepArm();
        SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
    }
    else if(ucKey == _EXIT_KEY_MESSAGE)        // MENU: cancel, the choice goes back
    {
        if(g_usBackupValue != ucItem)
        {
            SET_OSD_INPUT_PORT_OSD_ITEM(g_usBackupValue);
            SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
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
            SysSourceSetScanType(_SOURCE_SWITCH_AUTO_IN_GROUP);
            SysModeSetResetTarget(_MODE_ACTION_RESET_TO_SEARCH);
            if(UserCommonNVRamGetSystemData(_SOURCE_SCAN_TYPE) != SysSourceGetScanType())
            {
                UserCommonNVRamSetSystemData(_SOURCE_SCAN_TYPE, SysSourceGetScanType());
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_SYSTEMDATA_MSG);
            }
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
            if((UserCommonNVRamGetSystemData(_SEARCH_PORT) != SysSourceGetInputPort()) ||
               (UserCommonNVRamGetSystemData(_SOURCE_SCAN_TYPE) != SysSourceGetScanType()))
            {
                UserCommonNVRamSetSystemData(_SEARCH_PORT, SysSourceGetInputPort());
                UserCommonNVRamSetSystemData(_SOURCE_SCAN_TYPE, SysSourceGetScanType());
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_SYSTEMDATA_MSG);
            }
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

// Every SDK message card: our text card. Fail-safe = No Support (one warning card); switch DDC/CI port names the input (#114).
void OsdDispOsdMessage(EnumOSDDispMsg enumMessage)  // replaces the SDK body (keil2sdcc _K124)
{
    BYTE ucT;

    if((GET_OSD_STATE() == _MENU_HOTKEY_SOURCE) && ((enumMessage == _OSD_DISP_NOSIGNAL_MSG) || (enumMessage == _OSD_DISP_NOCABLE_MSG)))
    {
        AwtoSrcSleepArm();                      // #139: the open selector stays (its rows show the state); the SDK's 3 s is not restarted
        return;
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
