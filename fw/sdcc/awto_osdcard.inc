// AWTO user-facing OSD cards. Inserted into RTD2014OsdDisplay.c by keil2sdcc.py.
// Every transient message uses the same AWTO monitor mark, blue-on-white surface,
// and the source selector lists only this board's four meaningful choices.
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

static BYTE AwtoSourceSelection(void)
{
    BYTE ucItem = GET_OSD_INPUT_PORT_OSD_ITEM();

    return (ucItem == _OSD_INPUT_D2) ? 1 :
           (ucItem == _OSD_INPUT_D3) ? 2 :
           (ucItem == _OSD_INPUT_D1) ? 3 : 0;
}

static BYTE AwtoSourceState(BYTE ucPort)
{
    bit bCable = (ucPort == _D1_INPUT_PORT) ? GET_D1_CABLE_STATUS() :
                 (ucPort == _D2_INPUT_PORT) ? GET_D2_CABLE_STATUS() : GET_D3_CABLE_STATUS();

    if((SysSourceGetInputPort() == ucPort) && (SysModeGetModeState() == _MODE_STATUS_ACTIVE))
    {
        return 3;                               // active picture now
    }
    if(bCable == _FALSE)
    {
        return 0;                               // no cable / no source power
    }
#if(_AWTO_FAST_SWITCH == _ON)
    if(AwtoSwCacheValid(ucPort) != 0)
    {
        return 2;                               // scaler has previously locked this source
    }
#endif
    return 1;                                   // cable present, no usable signal detected
}

static void AwtoSourceRows(void)
{
    BYTE ucSel = AwtoSourceSelection();
    BYTE ucState;

    OsdFuncClearOsd(ROW(0), COL(12), WIDTH(24), HEIGHT(8));
    OsdWindowDrawingByFont(_OSD_WINDOW_4_1, ROW(1 + ucSel), COL(12), WIDTH(24), HEIGHT(1), _CP_BLUE);
    AWTO_CARD_LINE(1, "Auto Select", (ucSel == 0) ? _CP_WHITE : _CP_BLUE);

    ucState = AwtoSourceState(_D2_INPUT_PORT);
    if(ucState == 0)      { AWTO_CARD_LINE(2, "HDMI 1  No Cable",  (ucSel == 1) ? _CP_WHITE : _CP_BLUE); }
    else if(ucState == 1) { AWTO_CARD_LINE(2, "HDMI 1  No Signal", (ucSel == 1) ? _CP_WHITE : _CP_BLUE); }
    else if(ucState == 2) { AWTO_CARD_LINE(2, "HDMI 1  Ready",     (ucSel == 1) ? _CP_WHITE : _CP_BLUE); }
    else                  { AWTO_CARD_LINE(2, "HDMI 1  Active",    (ucSel == 1) ? _CP_WHITE : _CP_BLUE); }

    ucState = AwtoSourceState(_D3_INPUT_PORT);
    if(ucState == 0)      { AWTO_CARD_LINE(3, "HDMI 2  No Cable",  (ucSel == 2) ? _CP_WHITE : _CP_BLUE); }
    else if(ucState == 1) { AWTO_CARD_LINE(3, "HDMI 2  No Signal", (ucSel == 2) ? _CP_WHITE : _CP_BLUE); }
    else if(ucState == 2) { AWTO_CARD_LINE(3, "HDMI 2  Ready",     (ucSel == 2) ? _CP_WHITE : _CP_BLUE); }
    else                  { AWTO_CARD_LINE(3, "HDMI 2  Active",    (ucSel == 2) ? _CP_WHITE : _CP_BLUE); }

    ucState = AwtoSourceState(_D1_INPUT_PORT);
    if(ucState == 0)      { AWTO_CARD_LINE(4, "DP  No Cable",      (ucSel == 3) ? _CP_WHITE : _CP_BLUE); }
    else if(ucState == 1) { AWTO_CARD_LINE(4, "DP  No Signal",     (ucSel == 3) ? _CP_WHITE : _CP_BLUE); }
    else if(ucState == 2) { AWTO_CARD_LINE(4, "DP  Ready",         (ucSel == 3) ? _CP_WHITE : _CP_BLUE); }
    else                  { AWTO_CARD_LINE(4, "DP  Active",        (ucSel == 3) ? _CP_WHITE : _CP_BLUE); }
}

static void AwtoSourceOpen(void)
{
    OsdFuncDisableOsd();
    OsdFuncApplyMap(WIDTH(36), HEIGHT(8), COLOR(_CP_WHITE, _CP_BG));
#if(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_HARDWARE)
    ScalerOsdMapRotation(GET_OSD_ROTATE_STATUS(), _ENABLE, HEIGHT(8), _DISABLE, 0, _ENABLE);
#endif
    OsdFuncBlending(_OSD_TRANSPARENCY_ONLY_WINDOW);
    OsdFuncTransparency(GET_OSD_TRANSPARENCY_STATUS());
    OsdPaletteSelectPalette(_PALETTE_MAIN_MENU);
    OsdFuncSet2BitIconOffset(_2BIT_ICON_OFFSET);
    OsdFontVLCLoadFont(_FONT1_GLOBAL);
    OsdWindowDrawingByFont(_OSD_WINDOW_1, ROW(0), COL(0), WIDTH(12), HEIGHT(8), _CP_BLUE);
    OsdWindowDrawingByFont(_OSD_WINDOW_0, ROW(0), COL(12), WIDTH(24), HEIGHT(8), _CP_WHITE);
    AwtoCardLogo();
    AwtoSourceRows();
    OsdDispSetPosition(_POS_PERCENT, _OSD_POSITION_GLOBAL_A, 50, 50);
    ScalerTimerWaitForEvent(_EVENT_DEN_STOP);
    OsdFuncEnableOsd();
}

void AwtoSourceStep(void)
{
    BYTE ucSel = AwtoSourceSelection();

    if(GET_KEYMESSAGE() == _LEFT_KEY_MESSAGE)
    {
        ucSel = (ucSel == 0) ? 3 : (ucSel - 1);
    }
    else
    {
        ucSel = (ucSel == 3) ? 0 : (ucSel + 1);
    }
    SET_OSD_INPUT_PORT_OSD_ITEM((ucSel == 0) ? _OSD_INPUT_AUTO :
                                (ucSel == 1) ? _OSD_INPUT_D2 :
                                (ucSel == 2) ? _OSD_INPUT_D3 : _OSD_INPUT_D1);
}

void AwtoSourceKeyOpen(void)
{
    if(SysSourceGetScanType() == _SOURCE_SWITCH_AUTO_IN_GROUP)
    {
        SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_AUTO);
    }
    else
    {
        SET_OSD_INPUT_PORT_OSD_ITEM((SysSourceGetInputPort() == _D2_INPUT_PORT) ? _OSD_INPUT_D2 :
                                    (SysSourceGetInputPort() == _D3_INPUT_PORT) ? _OSD_INPUT_D3 : _OSD_INPUT_D1);
    }
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_GO_TO_POWER_SAVING);
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_CABLE);
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_SIGNAL);
    SET_OSD_STATE(_MENU_HOTKEY_SOURCE);
    OsdFuncSetOsdItemFlag();
    g_usBackupValue = GET_OSD_INPUT_PORT_OSD_ITEM();
    OsdDispHotKeySourceMenu();
    UserCommonInterfacePanelPowerAction(_BACKLIGHT_ON);
}

// Runtime-selected wrappers retain the SDK implementation as a real fallback.
// This also lets the warning gate distinguish our override from dead source.
bit AwtoSourceRowsOverride(void)
{
    AwtoSourceRows();
    return (g_ucOsdWidth == 36);
}

bit AwtoSourceOpenOverride(void)
{
    AwtoSourceOpen();
    return (g_ucOsdWidth == 36);
}

bit AwtoPanelCardOverride(void)
{
    AwtoCardPanel();
    return (g_ucOsdWidth == 36);
}
