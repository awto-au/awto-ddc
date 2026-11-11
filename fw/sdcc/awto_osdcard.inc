// AWTO user-facing OSD cards and the source selector. Inserted into RTD2014OsdDisplay.c after awto_dbgpop.inc (its text layer).
// - Cards: AWTO mark + one line, SDK proportional font (#124 moves them to the text layer).
// - Source selector (#134): text rows on the awto text layer, one per board port + Auto, awto menu look.
#if((_AWTO_DIAG != _ON) || !defined(_AWTO_NEW_SETTINGS))
#error "awto_osdcard.inc draws on the awto text layer (awto_dbgpop.inc, _AWTO_NEW_SETTINGS)"
#endif
extern BYTE *g_pucShowNumberAddress;

static BYTE s_pucAwtoCard[28];
static BYTE s_ucAwtoCardLen;
static BYTE s_ucAwtoCardSrc;

static void AwtoCardGlyph(BYTE ucG)
{
    if(s_ucAwtoCardLen < 26)
    {
        s_pucAwtoCard[s_ucAwtoCardLen++] = ucG;
    }
}

static void AwtoCardChar(char c)
{
    BYTE ucG = _QUERY_;

    if((c >= '0') && (c <= '9'))
    {
        ucG = _0_ + (c - '0');
    }
    else if((c >= 'A') && (c <= 'Z'))
    {
        ucG = _A_ + (c - 'A') + ((c > 'W') ? 1 : 0);
    }
    else if((c >= 'a') && (c <= 'z'))
    {
        ucG = _a_ + (c - 'a') + ((c > 'w') ? 1 : 0);
    }
    else if(c == ' ')
    {
        ucG = _;
    }
    else if(c == '-')
    {
        ucG = _SLINE_;
    }
    AwtoCardGlyph(ucG);
    if((c == 'W') || (c == 'w'))
    {
        AwtoCardGlyph(ucG + 1);
    }
}

static void AwtoCardLine(BYTE ucRow, BYTE ucColour)
{
    s_pucAwtoCard[s_ucAwtoCardLen] = _END_;
    g_pucShowNumberAddress = s_pucAwtoCard;
    OsdFuncClearOsd(ROW(ucRow), COL(12), WIDTH(24), HEIGHT(1));
    OsdPropPutStringCenter(ROW(ucRow), COL(13), WIDTH(22), _PFONT_PAGE_0,
                           _STRING_SHOW_NUMBER, COLOR(ucColour, _CP_BG), _ENGLISH);
}

// Copy the code string in the function that names it. On this banked 8051, passing a code pointer to a helper that the
// linker places in another bank reads unrelated flash bytes and produces garbled text.
#define AWTO_CARD_LINE(row, text, colour) \
    do { \
        s_ucAwtoCardLen = 0; \
        s_ucAwtoCardSrc = 0; \
        while((text)[s_ucAwtoCardSrc] != 0) { \
            AwtoCardChar((text)[s_ucAwtoCardSrc++]); \
        } \
        AwtoCardLine((row), (colour)); \
    } while(0)

static void AwtoCardLogo(void)
{
    OsdFontVLCDynamicLoadIcon(_ICON_POS_UP_0, _MENU_INFORMATION);
    OsdFontPut1BitMainMenuIcon(ROW(2), COL(3),
                              (_1DYNAMIC_ICON_START + (0 * 24)), _CP_WHITE, _CP_BG);
}

static void AwtoCardPanel(void)
{
    AwtoCardLogo();
    AWTO_CARD_LINE(2, "Panel Uniformity", _CP_BLUE);
    if(GET_OSD_PANEL_UNIFORMITY() == _ON)
    {
        AWTO_CARD_LINE(4, "On", _CP_BLUE);
    }
    else
    {
        AWTO_CARD_LINE(4, "Off", _CP_BLUE);
    }
}

// Return true when this message has been fully rendered as an AWTO card.
static bit AwtoCardMessage(EnumOSDDispMsg enumMessage)
{
    switch(enumMessage)
    {
        case _OSD_DISP_NOSIGNAL_MSG:
        case _OSD_DISP_NOCABLE_MSG:
        case _OSD_DISP_NOSUPPORT_MSG:
        case _OSD_DISP_AUTO_CONFIG_MSG:
        case _OSD_DISP_AUTO_COLOR_MSG:
        case _OSD_DISP_POWER_SAVING_MSG:
            break;
        case _OSD_DISP_PANEL_UNIFORMITY_ONOFF_MSG:
            AwtoCardPanel();
            return _TRUE;
#if(_FREEZE_SUPPORT == _ON)
        case _OSD_DISP_DISABLE_FREEZE_MSG:        break;
#endif
#if(_DP_MST_SUPPORT == _ON)
        case _OSD_DISP_MST_WARNING_MSG:           break;
#endif
        default:
            return _FALSE;
    }

    AwtoCardLogo();
    // Name each literal here so its bank is the active one.
    switch(enumMessage)
    {
        case _OSD_DISP_NOSIGNAL_MSG:             AWTO_CARD_LINE(3, "No Signal", _CP_BLUE); break;
        case _OSD_DISP_NOCABLE_MSG:              AWTO_CARD_LINE(3, "No Cable", _CP_BLUE); break;
        case _OSD_DISP_NOSUPPORT_MSG:            AWTO_CARD_LINE(3, "No Support", _CP_BLUE); break;
        case _OSD_DISP_AUTO_CONFIG_MSG:           AWTO_CARD_LINE(3, "Auto Adjust", _CP_BLUE); break;
        case _OSD_DISP_AUTO_COLOR_MSG:            AWTO_CARD_LINE(3, "Auto Colour", _CP_BLUE); break;
        case _OSD_DISP_POWER_SAVING_MSG:          AWTO_CARD_LINE(3, "Power Saving", _CP_BLUE); break;
#if(_FREEZE_SUPPORT == _ON)
        case _OSD_DISP_DISABLE_FREEZE_MSG:        AWTO_CARD_LINE(3, "Freeze Disabled", _CP_BLUE); break;
#endif
#if(_DP_MST_SUPPORT == _ON)
        case _OSD_DISP_MST_WARNING_MSG:           AWTO_CARD_LINE(3, "DP MST Warning", _CP_BLUE); break;
#endif
        default: break;
    }
    return _TRUE;
}

//---- source selector (#134) ----
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
#define AWTO_SRC_STATE_COL  15                  // port state column
#define AWTO_SRC_ROW0       2                   // first item row: title, one blank row, then the items
#define AWTO_WIN_FRAME      0                   // window ids as the awto menu (awto-rtdfw ui.c)
#define AWTO_WIN_INSET      1
#define AWTO_WIN_TITLE      2
#define AWTO_WIN_HL         5
#define AWTO_T_STYLE_DIM    1

// Fixed card texts: one table, read only by AwtoCardTxt (a constant read through a pointer sits in its reader's bank, awto-sdcc#39).
#define AWTO_CT_INPUT       0
#define AWTO_CT_AUTO        1
#define AWTO_CT_DP          2
#define AWTO_CT_HDMI        3
#define AWTO_CT_PORT        4
#define AWTO_CT_STATE       5                   // + ui_port_state: no cable, no signal, ready, ACTIVE
static const __code char tAwtoCardS[] = "Input\0Auto select\0DisplayPort\0HDMI \0Input D\0no cable\0no signal\0ready\0ACTIVE\0";

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

// Card frame in the awto menu look (blue frame + title bar on white, the menu font), centred; the OSD stays off until shown.
static void AwtoCardOpen(BYTE ucLines)
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
}

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

static void AwtoSrcSet(BYTE ucI)
{
    SET_OSD_INPUT_PORT_OSD_ITEM((ucI == 0) ? _OSD_INPUT_AUTO : AwtoSrcItem(AwtoSrcPort(ucI)));
}

static void AwtoSourceRows(void)                // Auto, then each port with its state; the selection on the bar
{
    BYTE ucSel = AwtoSrcSel();
    BYTE ucI, ucSt, ucHdmi = 0;

    osd_tc_bar(AWTO_WIN_HL, 2, (WORD)(AWTO_SRC_ROW0 + ucSel) * osd_rh, (WORD)AWTO_CARD_COLS * osd_cw - 3,
               (WORD)(AWTO_SRC_ROW0 + ucSel + 1) * osd_rh - 1, 1);
    for(ucI = 0; ucI <= AWTO_SRC_PORTS; ucI++)
    {
        ucSt = 0;
        if(ucI == 0)
        {
            AwtoCardTxt(AWTO_CT_AUTO);
        }
        else if((tAwtoSrcType[ucI - 1] & 0x0F) == _PORT_DP)
        {
            AwtoCardTxt(AWTO_CT_DP);
        }
        else if((tAwtoSrcType[ucI - 1] & 0x0F) == _PORT_HDMI)
        {
            AwtoCardTxt(AWTO_CT_HDMI);
            AwtoPutNum(++ucHdmi, 1);
        }
        else
        {
            AwtoCardTxt(AWTO_CT_PORT);
            AwtoPutNum(AwtoSrcPort(ucI) - _D0_INPUT_PORT, 1);
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
    SET_OSD_STATE(_MENU_HOTKEY_SOURCE);
    OsdFuncSetOsdItemFlag();
    g_usBackupValue = GET_OSD_INPUT_PORT_OSD_ITEM();
    AwtoCardOpen(AWTO_SRC_ROW0 + AWTO_SRC_PORTS + 2);   // + Auto + pad row (the frame covers the last 2 px)
    AwtoCardTxt(AWTO_CT_INPUT);
    AwtoTextLine(0, AWTO_T_STYLE_ONACC);
    AwtoSourceRows();
    ScalerTimerWaitForEvent(_EVENT_DEN_STOP);
    OsdFuncEnableOsd();
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

static bit AwtoSourceNoPicture(void)            // power saving / no signal / no support: the SDK hands back to its pop-up timers
{
    BYTE ucMode = SysModeGetModeState();

    return ((ucMode == _MODE_STATUS_POWER_SAVING) || (ucMode == _MODE_STATUS_NOSIGNAL) || (ucMode == _MODE_STATUS_NOSUPPORT));
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
        if((SysModeGetModeState() == _MODE_STATUS_POWER_SAVING) || (SysModeGetModeState() == _MODE_STATUS_NOSIGNAL))
        {
            ScalerTimerReactiveTimerEvent(SEC(3), _USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
        }
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

// Runtime override of the SDK panel-uniformity switch (drawn as an AWTO card).
bit AwtoPanelCardOverride(void)
{
    AwtoCardPanel();
    return (g_ucOsdWidth == 36);
}
