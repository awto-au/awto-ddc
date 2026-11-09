// AWTO user-facing OSD cards. Inserted into RTD2014OsdDisplay.c by keil2sdcc.py.
// Every transient message uses the same AWTO monitor mark, blue-on-white surface,
// and the source selector lists only this board's four meaningful choices.
extern BYTE *g_pucShowNumberAddress;

static BYTE s_pucAwtoCard[28];
static BYTE s_ucAwtoCardLen;

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

static void AwtoCardLine(BYTE ucRow, const char *pText, BYTE ucColour)
{
    s_ucAwtoCardLen = 0;
    while(*pText != 0)
    {
        AwtoCardChar(*pText++);
    }
    s_pucAwtoCard[s_ucAwtoCardLen] = _END_;
    g_pucShowNumberAddress = s_pucAwtoCard;
    OsdFuncClearOsd(ROW(ucRow), COL(12), WIDTH(24), HEIGHT(1));
    OsdPropPutStringCenter(ROW(ucRow), COL(13), WIDTH(22), _PFONT_PAGE_0,
                           _STRING_SHOW_NUMBER, COLOR(ucColour, _CP_BG), _ENGLISH);
}

static void AwtoCardLogo(void)
{
    OsdFontVLCDynamicLoadIcon(_ICON_POS_UP_0, _MENU_INFORMATION);
    OsdFontPut1BitMainMenuIcon(ROW(2), COL(3),
                              (_1DYNAMIC_ICON_START + (0 * 24)), _CP_WHITE, _CP_BG);
}

static void AwtoCardPanel(void)
{
    AwtoCardLogo();
    AwtoCardLine(2, "Panel Uniformity", _CP_BLUE);
    AwtoCardLine(4, (GET_OSD_PANEL_UNIFORMITY() == _ON) ? "On" : "Off", _CP_BLUE);
}

// Return true when this message has been fully rendered as an AWTO card.
static bit AwtoCardMessage(EnumOSDDispMsg enumMessage)
{
    const char *pText = 0;

    switch(enumMessage)
    {
        case _OSD_DISP_NOSIGNAL_MSG:             pText = "No Signal"; break;
        case _OSD_DISP_NOCABLE_MSG:              pText = "No Cable"; break;
        case _OSD_DISP_NOSUPPORT_MSG:            pText = "No Support"; break;
        case _OSD_DISP_AUTO_CONFIG_MSG:           pText = "Auto Adjust"; break;
        case _OSD_DISP_AUTO_COLOR_MSG:            pText = "Auto Colour"; break;
        case _OSD_DISP_POWER_SAVING_MSG:          pText = "Power Saving"; break;
        case _OSD_DISP_PANEL_UNIFORMITY_ONOFF_MSG:
            AwtoCardPanel();
            return _TRUE;
#if(_FREEZE_SUPPORT == _ON)
        case _OSD_DISP_DISABLE_FREEZE_MSG:        pText = "Freeze Disabled"; break;
#endif
#if(_DP_MST_SUPPORT == _ON)
        case _OSD_DISP_MST_WARNING_MSG:           pText = "DP MST Warning"; break;
#endif
        default:
            return _FALSE;
    }

    AwtoCardLogo();
    AwtoCardLine(3, pText, _CP_BLUE);
    return _TRUE;
}

static BYTE AwtoSourceSelection(void)
{
    BYTE ucItem = GET_OSD_INPUT_PORT_OSD_ITEM();

    return (ucItem == _OSD_INPUT_D1) ? 1 :
           (ucItem == _OSD_INPUT_D2) ? 2 :
           (ucItem == _OSD_INPUT_D3) ? 3 : 0;
}

static void AwtoSourceRows(void)
{
    BYTE ucSel = AwtoSourceSelection();

    OsdFuncClearOsd(ROW(0), COL(12), WIDTH(24), HEIGHT(8));
    OsdWindowDrawingByFont(_OSD_WINDOW_4_1, ROW(1 + ucSel), COL(12), WIDTH(24), HEIGHT(1), _CP_BLUE);
    AwtoCardLine(1, "Auto",        (ucSel == 0) ? _CP_WHITE : _CP_BLUE);
    AwtoCardLine(2, "DisplayPort", (ucSel == 1) ? _CP_WHITE : _CP_BLUE);
    AwtoCardLine(3, "HDMI 1",      (ucSel == 2) ? _CP_WHITE : _CP_BLUE);
    AwtoCardLine(4, "HDMI 2",      (ucSel == 3) ? _CP_WHITE : _CP_BLUE);
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
                                (ucSel == 1) ? _OSD_INPUT_D1 :
                                (ucSel == 2) ? _OSD_INPUT_D2 : _OSD_INPUT_D3);
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
