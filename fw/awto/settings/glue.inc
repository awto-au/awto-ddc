// #67 settings glue (integrator-owned, private): the clean settings / menu / VCP code (awto-rtdfw awto/settings,
// awto/nvram) on top of this firmware. Inserted into RTD2014Osd.c by fw/awto/settings/rules.py.
// - implements the clean interfaces: osd_tc_* (text cells on the OSD engine), fl_* (flash), set_status, set_ap_*
// - hooks: AwtoSetInit (after RTDNVRamStartup), AwtoSetLoop (main loop), AwtoMenuForget (vendor OSD closes);
//   keys reach the menu from the key router (fw/sdcc/awto_keys.inc, #129); DDC/CI hooks: glue_ddcci.inc
#ifdef _AWTO_NEW_SETTINGS
#include <stddef.h>

// clean API (awto-rtdfw awto/include: settings.h, menu.h, vcp.h); int = int16_t, WORD = uint16_t
extern void set_load(void);
extern void set_boot(void);
extern void set_service(void);
extern void set_track(BYTE ucId, int iV);
extern int set_put(BYTE ucId, int iV, BYTE ucNow);
extern int set_get(BYTE ucId);
extern BYTE set_in_boot(void);
extern void set_defaults(void);
extern void menu_open(void);
extern void menu_close(void);
extern void menu_key(BYTE ucKey);
extern void menu_service(void);
extern void menu_forget(void);
extern void menu_relayout(void);
extern BYTE menu_active(void);
extern void vcp_box_service(void);
extern __xdata struct { BYTE ucMagic, cmd; } vcp_box;   // awto-rtdfw vcp.c: first two bytes (magic, cmd)
extern void osd_font_load(BYTE ucFont);

BYTE ui_font_selected(void)
{
    return (BYTE)set_get(AWTO_SET_OSD_FONT);
}

__xdata BYTE g_ucAwtoDdcciOn;              // GET_OSD_DDCCI_STATUS (RL6449_Project.h): Debug link off and DDC/CI on
__xdata BYTE g_ucAwtoKeepIdle = 1;         // AWTO_IDLE_RX_OFF: Keep idle inputs
static __xdata BYTE s_ucAwtoSetBooted;
__xdata BYTE g_ucAwtoMenuOn;
__xdata WORD g_usAwtoSetLast;

// Power levels (#60 wake work): the firmware agent's variables are not named yet; values land here until then.
typedef struct
{
    BYTE ucL1En, ucL2En, ucL3En, ucWake;   // ucWake bit n = wake on D(n+1)
    WORD usL1Ms, usL2S, usL3S;
} StAwtoPwrCfg;
__xdata StAwtoPwrCfg g_stAwtoPwrCfg;

//---- flash (nvram.h fl_*): one entry point, so fw_sim can model it (scripts/settings_sim.py stubs AwtoFlIo) ----
typedef struct
{
    BYTE ucOp;                                  // 1 read, 2 write, 3 erase sector
    BYTE ucOk;
    BYTE ucBank;
    WORD usAddr;
    WORD usLen;
    BYTE xdata *pucBuf;
} StAwtoFl;
__xdata StAwtoFl g_stAwtoFl;

void AwtoFlIo(void)
{
    bit bOk = _FALSE;

    if(g_stAwtoFl.ucOp == 1)
    {
        bOk = UserCommonFlashRead(g_stAwtoFl.ucBank, g_stAwtoFl.usAddr, g_stAwtoFl.usLen, g_stAwtoFl.pucBuf);
    }
    else if(g_stAwtoFl.ucOp == 2)
    {
        bOk = UserCommonFlashWrite(g_stAwtoFl.ucBank, g_stAwtoFl.usAddr, g_stAwtoFl.usLen, g_stAwtoFl.pucBuf);
    }
    else if(g_stAwtoFl.ucOp == 3)
    {
        bOk = UserCommonFlashErasePage(g_stAwtoFl.ucBank, (BYTE)(g_stAwtoFl.usAddr >> 12));
    }
    g_stAwtoFl.ucOk = bOk;
}

static BYTE AwtoFl(BYTE ucOp, DWORD ulA, BYTE xdata *pucBuf, WORD usLen)
{
    g_stAwtoFl.ucOp = ucOp;
    g_stAwtoFl.ucBank = (BYTE)(ulA >> 16);
    g_stAwtoFl.usAddr = (WORD)ulA;
    g_stAwtoFl.usLen = usLen;
    g_stAwtoFl.pucBuf = pucBuf;
    g_stAwtoFl.ucOk = 0;
    AwtoFlIo();
    return g_stAwtoFl.ucOk;
}

BYTE fl_read(DWORD ulA, BYTE xdata *pucDst, WORD usN)
{
    return AwtoFl(1, ulA, pucDst, usN);
}

BYTE fl_write(DWORD ulA, BYTE xdata *pucSrc, WORD usN)
{
    return AwtoFl(2, ulA, pucSrc, usN);
}

BYTE fl_erase(DWORD ulA)
{
    return AwtoFl(3, ulA, 0, 0);
}

//---- time, keys, status ----
WORD set_now_ms(void)
{
    WORD usNow;

    do
    {
        usNow = g_usTimerCounter;
    }
    while(usNow != g_usTimerCounter);
    return usNow;
}

void set_wait_ms(WORD usMs)
{
    ScalerTimerDelayXms(usMs);
}

int set_status(BYTE ucId)
{
    switch(ucId)
    {
        case AWTO_SET_INFO_INPUT:
            return (SysSourceGetInputPort() >= _D1_INPUT_PORT) ? (SysSourceGetInputPort() - _D1_INPUT_PORT) : 0;
        case AWTO_SET_INFO_HRES:
            return GET_INPUT_TIMING_HWIDTH();
        case AWTO_SET_INFO_VRES:
            return GET_INPUT_TIMING_VHEIGHT();
        case AWTO_SET_INFO_VFREQ:
            return GET_INPUT_TIMING_VFREQ();
        case AWTO_SET_INFO_HFREQ:
            return GET_INPUT_TIMING_HFREQ();                // 0.1 kHz
        case AWTO_SET_INFO_PCLK:
            return ScalerSyncGetInputPixelClk();            // 0.1 MHz
        case AWTO_SET_INFO_HDCP:
            return (ScalerSyncHdcpCheckEnabled(SysSourceGetInputPort()) != _FALSE) ? 1 : 0;
        case AWTO_SET_INFO_MODE:
            return SysModeGetModeState();
        case AWTO_SET_INFO_LOOP:
            return g_stAwtoDiag.usLoopRate;
        case AWTO_SET_INFO_SCHEMA:
            return AWTO_SET_SCHEMA;
        default:
            return 0;
    }
}

//---- text layer on the OSD engine (osd.h osd_tc_*, awto-ddc#89): native Spleen 8 x 16 bitmap glyphs ----
// palette (index: colour): our own entries over the SDK's, restored when the Realtek SDK menu loads its palette.
// White surface + Realtek 2014 blue (0,68,166) text/accent; selected rows retain white text on blue.
static __code BYTE tAwtoPal[12][3] = {
    {0, 68, 166}, {170, 170, 170}, {255, 255, 255}, {73, 73, 73}, {110, 110, 110}, {170, 193, 225},
    {0, 45, 111}, {85, 85, 85}, {37, 37, 37}, {85, 130, 196}, {0, 23, 55}, {0, 0, 0}};
// 1 bit glyph foreground for each osd_style; background 0 is transparent and exposes the white/blue window.
static __code BYTE tAwtoStyle[5] = {1, 2, 3, 1, 4};      // style 4 = palette 4: only the diagnostic console uses it (alert)
#define AWTO_BAR_SURFACE            3
#define AWTO_BAR_ACCENT             1

static BYTE s_ucVpRows;                          // viewport rows (0 = the whole map is shown)
static BYTE s_ucVpFirst;                         // first map row shown
static BYTE s_ucVpEnd;                           // map row that currently holds the end-of-rows marker

void osd_tc_open(BYTE ucChars, BYTE ucLines)
{
    BYTE ucI;

    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
    OsdFuncDisableOsd();
    OsdFuncCloseWindow(_OSD_WINDOW_ALL);
    SET_OSD_DOUBLE_SIZE(GET_OSD_NVRAM_DOUBLE_SIZE());
    OsdFuncApplyMap(WIDTH(ucChars), HEIGHT(ucLines), COLOR(0, 0));
    ScalerSetBit(0x3A18, ~_BIT7, 0x00);             // roll-up (viewport scroll) off
    s_ucVpRows = 0;
    s_ucVpFirst = 0;
    s_ucVpEnd = ucLines;
    OsdFuncBlending(_OSD_TRANSPARENCY_ONLY_WINDOW);
    OsdFuncTransparency(GET_OSD_TRANSPARENCY_STATUS());
    OsdPaletteSelectPalette(_PALETTE_MAIN_MENU);
    for(ucI = 0; ucI < 12; ucI++)
    {
        ScalerOsdSetColorPalette(ucI + 1, tAwtoPal[ucI][0], tAwtoPal[ucI][1], tAwtoPal[ucI][2]);
    }
}

extern BYTE __xdata osd_cw;
extern BYTE __xdata osd_rh;

void osd_tc_rowh(BYTE ucRh)
{
    BYTE ucI;

    for(ucI = 0; ucI < g_ucOsdHeight; ucI++)
    {
        ScalerOsdCommandAllByte(ucI, 0x80, ucRh - 1, g_ucOsdWidth);   // row height - 1 (5 bit); the SDK map uses 17 = 18 px
    }
}

// Viewport (standard scrolling screen): the map has more rows than the window shows. Hardware roll-up moves the first displayed row
// (0x3A19 row base, 0x3A1B/0x3A1C font-select base, 12 bit) and the end-of-rows marker moves with it, so the shown height stays fixed.
// Call after osd_tc_open and the font load. Returns the first row actually shown (limited by the map end and by the 12-bit base).
BYTE osd_tc_scroll(BYTE ucFirst)
{
    WORD usFs;
    BYTE ucEnd;

    if(s_ucVpRows == 0)
    {
        return 0;
    }
    if(ucFirst > g_ucOsdHeight - s_ucVpRows)
    {
        ucFirst = g_ucOsdHeight - s_ucVpRows;
    }
    while((ucFirst != 0) && ((WORD)ucFirst * g_ucOsdWidth + g_usFontSelectStart > 4095))
    {
        ucFirst--;
    }
    ucEnd = ucFirst + s_ucVpRows;
    if(s_ucVpEnd < g_ucOsdHeight)
    {
        ScalerOsdCommandAllByte(s_ucVpEnd, 0x80, osd_rh - 1, g_ucOsdWidth);    // the old marker row is a text row again
    }
    if(ucEnd < g_ucOsdHeight)
    {
        ScalerOsdCommandByte(ucEnd, _OSD_BYTE0, 0x00);                         // end-of-rows marker: the view stops here
    }
    s_ucVpEnd = ucEnd;
    usFs = g_usFontSelectStart + (WORD)ucFirst * g_ucOsdWidth;
    ScalerSetBit(0x3A18, ~(_BIT7 | _BIT6), _BIT7);                              // special function on, 0 = roll-up
    ScalerSetByte(0x3A19, ucFirst);
    ScalerSetBit(0x3A1B, 0x0F, (BYTE)((usFs >> 8) << 4));
    ScalerSetByte(0x3A1C, (BYTE)usFs);
    s_ucVpFirst = ucFirst;
    return ucFirst;
}

void osd_tc_viewport(BYTE ucRows)
{
    s_ucVpRows = (ucRows < g_ucOsdHeight) ? ucRows : 0;
    s_ucVpFirst = 0;
    osd_tc_scroll(0);
}

void osd_tc_cells(BYTE ucRow, BYTE ucCell, BYTE __xdata *pucTiles, BYTE ucN, BYTE ucStyle)
{
    BYTE ucB0 = 0x40 | osd_cw;                   // 1 bit font, cell width = the loaded font's pixel width
    BYTE ucB2 = tAwtoStyle[ucStyle] << 4;         // foreground; transparent background

    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, g_usFontSelectStart + (WORD)ucRow * g_ucOsdWidth + ucCell, _OSD_WITHOUT_DB);
    while(ucN-- != 0)                              // one address, then B0 B1 B2 per cell (the word address increments by itself)
    {
        ScalerOsdDataPort(ucB0);
        ScalerOsdDataPort(*pucTiles++);
        ScalerOsdDataPort(ucB2);
    }
}

void osd_tc_bar(BYTE ucWin, WORD usX0, WORD usY0, WORD usX1, WORD usY1, BYTE ucColour)
{
    OsdWindowDrawing(ucWin, usX0, usY0, usX1, usY1, (ucColour == 0) ? AWTO_BAR_SURFACE : AWTO_BAR_ACCENT);
}

void osd_tc_bar_off(BYTE ucWin)
{
    ScalerOsdWindowDisable((EnumOsdWindowsType)ucWin);
}

// VLC font download, osd-font-download.md section 1: value map -> 0x3A0F..0x3A16, 0x3A17[0] = 1, destination word address,
// stream bytes to the data port (3 decoded bytes = one word per 6 symbols, END code stops), 0x3A17[1:0] = 0
void osd_tc_vlc_begin(BYTE __xdata *pucMap, WORD usTile)
{
    BYTE ucI;

    for(ucI = 0; ucI < 8; ucI++)
    {
        ScalerSetByte(0x3A0F + ucI, pucMap[ucI]);
    }
    ScalerSetBit(0x3A17, ~(_BIT1 | _BIT0), _BIT0);
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, g_usFontTableStart + usTile * 9, _OSD_WITHOUT_DB);
}

void osd_tc_vlc_put(BYTE __xdata *pucData, BYTE ucN)
{
    while(ucN-- != 0)
    {
        ScalerOsdDataPort(*pucData++);
    }
}

void osd_tc_vlc_end(void)
{
    // The RTD2795 decoder flushes its final decoded words after the last stream byte. Clearing compression
    // immediately truncates/corrupts glyph SRAM; Realtek's loader waits 2 ms here for the same reason.
    ScalerTimerDelayXms(2);
    ScalerSetBit(0x3A17, ~(_BIT1 | _BIT0), 0x00);
}

// Own placement: the SDK OsdDispSetPosition assumes 12 x 18 cells, so rows x 36 above the panel height wraps to an off-screen position.
void osd_tc_place(BYTE ucH, BYTE ucV, BYTE ucBig)
{
    DWORD ulW = (DWORD)g_ucOsdWidth * osd_cw;
    DWORD ulH = (DWORD)((s_ucVpRows != 0) ? s_ucVpRows : g_ucOsdHeight) * osd_rh;
    WORD usX = 0;
    WORD usY = 0;
    BYTE ucStep = (ScalerOsdGetHorizontalDelayStep() == _OSD_HORIZONTAL_DELAY_STEP_1_PIXEL) ? 1 : 4;

    SET_OSD_DOUBLE_SIZE(ucBig);
    ScalerOsdDoubleFunction(ucBig, ucBig);
    if(ucBig != 0)
    {
        ulW *= 2;
        ulH *= 2;
    }
    if((DWORD)_PANEL_DH_WIDTH > ulW)
    {
        usX = (WORD)((((DWORD)_PANEL_DH_WIDTH - ulW) / ucStep) * ucH / 100);
    }
    if((DWORD)_PANEL_DV_HEIGHT > ulH)
    {
        usY = (WORD)((((DWORD)_PANEL_DV_HEIGHT - ulH) * ucV) / 100);
    }
    if(ucBig != 0)
    {
        usX /= 2;
        usY /= 2;
    }
    OsdFuncSetPosition(_OSD_POSITION_GLOBAL_A, usX, usY);
}

void osd_tc_show(BYTE ucOn)
{
    g_ucAwtoMenuOn = (ucOn != 0);
    if(ucOn != 0)
    {
        OsdFuncEnableOsd();
    }
    else
    {
        OsdFuncDisableOsd();
    }
}

void osd_tc_close(void)
{
    g_ucAwtoMenuOn = 0;
    ScalerSetBit(0x3A18, ~_BIT7, 0x00);              // viewport roll-up off: the next screen starts at row 0
    s_ucVpRows = 0;
    OsdFuncDisableOsd();
    OsdFuncCloseWindow(_OSD_WINDOW_ALL);
    SET_OSD_DOUBLE_SIZE(GET_OSD_NVRAM_DOUBLE_SIZE());
    g_ucOsdWidth = 0;
    g_ucOsdHeight = 0;
    SET_OSD_STATE(_MENU_NONE);
    if(SysModeGetModeState() == _MODE_STATUS_NOSIGNAL)       // the no-signal path dropped while the menu was up
    {
        ScalerTimerActiveTimerEvent(SEC(2), _USER_TIMER_EVENT_OSD_SHOW_NO_SIGNAL);
    }
}

// status strip data (ui.h): D1..D3 state and the active input's measured timing
struct AwtoUiTiming
{
    WORD usW, usH;
    DWORD ulVmHz;
};

BYTE ui_port_state(BYTE ucI)
{
    BYTE ucP = _D1_INPUT_PORT + ucI;
    bit bCable = (ucI == 0) ? GET_D1_CABLE_STATUS() : (ucI == 1) ? GET_D2_CABLE_STATUS() : GET_D3_CABLE_STATUS();

    if((SysSourceGetInputPort() == ucP) && (SysModeGetModeState() == _MODE_STATUS_ACTIVE))
    {
        return 3;                                  // UPS_ACTIVE
    }
    if(bCable == _FALSE)
    {
        return 0;                                  // UPS_NOCABLE
    }
#if(_AWTO_FAST_SWITCH == _ON)
    if(AwtoSwCacheValid(ucP) != 0)
    {
        return 2;                                  // UPS_READY: this port has carried a picture (#60 cache)
    }
#endif
    return 1;                                      // UPS_NOSIGNAL
}

BYTE ui_timing(struct AwtoUiTiming __xdata *pst)
{
    if(SysModeGetModeState() != _MODE_STATUS_ACTIVE)
    {
        return _FALSE;
    }
    pst->usW = GET_INPUT_TIMING_HWIDTH();
    pst->usH = GET_INPUT_TIMING_VHEIGHT();
#if(_AWTO_FREQ == _ON)
    if(g_stAwtoFreq.ucValid != 0)
    {
        pst->ulVmHz = g_stAwtoFreq.ulVFreqmHz;     // exact: measured clock / (htotal x vtotal) (#34)
        return _TRUE;
    }
#endif
    pst->ulVmHz = (DWORD)GET_INPUT_TIMING_VFREQ() * 100;
    return _TRUE;
}

//---- apply functions (settings.h set_ap_*): registry value -> this firmware's variables and adjust calls ----
void set_ap_backlight(BYTE ucId, int iV)
{
    ucId = ucId;
    SET_OSD_BACKLIGHT(UserCommonAdjustPercentToRealValue((BYTE)iV, _BACKLIGHT_MAX, _BACKLIGHT_MIN, _BACKLIGHT_CENTER));
    UserAdjustBacklight(GET_OSD_BACKLIGHT());
}

void set_ap_black_level(BYTE ucId, int iV)
{
    ucId = ucId;
#if(_BRIGHTNESS_SUPPORT == _ON)
    SET_OSD_BRIGHTNESS(UserCommonAdjustPercentToRealValue((BYTE)iV, _BRIGHTNESS_MAX, _BRIGHTNESS_MIN, _BRIGHTNESS_CENTER));
    UserAdjustBrightness(GET_OSD_BRIGHTNESS());
#else
    iV = iV;
#endif
}

void set_ap_contrast(BYTE ucId, int iV)
{
    ucId = ucId;
#if(_CONTRAST_SUPPORT == _ON)
    SET_OSD_CONTRAST(UserCommonAdjustPercentToRealValue((BYTE)iV, _CONTRAST_MAX, _CONTRAST_MIN, _CONTRAST_CENTER));
    UserAdjustContrast(GET_OSD_CONTRAST());
#else
    iV = iV;
#endif
}

void set_ap_gamma(BYTE ucId, int iV)
{
    ucId = ucId;                                   // called on a change only (settings.c), or at boot
    SET_OSD_GAMMA((BYTE)iV);
#if(_GAMMA_FUNCTION == _ON)
    ScalerTimerWaitForEvent(_EVENT_DEN_STOP);
    UserCommonAdjustGammaRegionEnable(_FUNCTION_OFF);
    if(GET_OSD_GAMMA() != _GAMMA_OFF)
    {
        UserAdjustGamma(GET_OSD_GAMMA());
        ScalerTimerWaitForEvent(_EVENT_DEN_STOP);
        UserCommonAdjustGammaRegionEnable(_FUNCTION_ON);
    }
#endif
}

static void AwtoUserRgb(void)
{
    SET_COLOR_TEMP_TYPE_USER_R(set_get(AWTO_SET_USER_RED));
    SET_COLOR_TEMP_TYPE_USER_G(set_get(AWTO_SET_USER_GREEN));
    SET_COLOR_TEMP_TYPE_USER_B(set_get(AWTO_SET_USER_BLUE));
}

void set_ap_colour_temp(BYTE ucId, int iV)
{
    ucId = ucId;
    SET_COLOR_TEMP_TYPE((BYTE)iV);
    RTDNVRamLoadColorSetting((BYTE)iV);
    if(iV == _CT_USER)
    {
        AwtoUserRgb();
    }
#if(_CONTRAST_SUPPORT == _ON)
    UserAdjustContrast(GET_OSD_CONTRAST());
#endif
}

void set_ap_user_rgb(BYTE ucId, int iV)
{
    ucId = ucId;
    iV = iV;
    if(GET_COLOR_TEMP_TYPE() == _CT_USER)
    {
        AwtoUserRgb();
#if(_CONTRAST_SUPPORT == _ON)
        UserAdjustContrast(GET_OSD_CONTRAST());
#endif
    }
}

void set_ap_aspect(BYTE ucId, int iV)
{
    ucId = ucId;
    SET_OSD_ASPECT_RATIO_TYPE((BYTE)iV);
    if(SysModeGetModeState() == _MODE_STATUS_ACTIVE)
    {
        SysModeSetResetTarget(_MODE_ACTION_RESET_TO_DISPLAY_SETTING);
    }
}

void set_ap_overscan(BYTE ucId, int iV)
{
    ucId = ucId;
    SET_OSD_OVERSCAN_STATUS((BYTE)iV);
    if(SysModeGetModeState() == _MODE_STATUS_ACTIVE)
    {
        SysModeSetResetTarget(_MODE_ACTION_RESET_TO_DISPLAY_SETTING);
    }
}

void set_ap_input_mode(BYTE ucId, int iV)
{
    ucId = ucId;
    SysSourceSetScanType((iV != 0) ? _SOURCE_SWITCH_FIXED_PORT : _SOURCE_SWITCH_AUTO_IN_GROUP);
}

void set_ap_input_select(BYTE ucId, int iV)        // the KVM entry (#60 AwtoInputSelect): fixed port, fast path first
{
    ucId = ucId;
    if(set_in_boot() == _TRUE)
    {
        return;                                     // boot: the search owns the port
    }
    set_track(AWTO_SET_INPUT_MODE, 1);             // not stored: an input switch writes no flash (#151)
    AwtoInputSelect(_D1_INPUT_PORT + (BYTE)iV, 0x60);
}

void set_ap_power_mode(BYTE ucId, int iV)          // MCCS 0xD6: on, or any off state -> power saving (L1..L3 owner: #78)
{
    ucId = ucId;
    if(set_in_boot() == _TRUE)
    {
        return;
    }
    if(iV == 0)
    {
        SET_FORCE_POW_SAV_STATUS(_FALSE);
        SysPowerSetTargetPowerStatus(_POWER_STATUS_NORMAL);
    }
    else
    {
        SET_FORCE_POW_SAV_STATUS(_TRUE);
        SysPowerSetTargetPowerStatus(_POWER_STATUS_SAVING);
    }
}

void set_ap_search_time(BYTE ucId, int iV)
{
    switch(ucId)
    {
        case AWTO_SET_SEARCH_HDMI_MS:
            SysSourceSetDefaultSearchTime(_SOURCE_INPUT_TYPE_HDMI, (WORD)iV);
            break;
        case AWTO_SET_SEARCH_DP_MS:
            SysSourceSetDefaultSearchTime(_SOURCE_INPUT_TYPE_DP, (WORD)iV);
            break;
        case AWTO_SET_NOCABLE_HDMI_MS:
            SysSourceSetNoCableSearchTime(_SOURCE_INPUT_TYPE_HDMI, (WORD)iV);
            break;
        case AWTO_SET_NOCABLE_DP_MS:
            SysSourceSetNoCableSearchTime(_SOURCE_INPUT_TYPE_DP, (WORD)iV);
            break;
        default:
            break;
    }
}

void set_ap_dp_version(BYTE ucId, int iV)
{
    ucId = ucId;
    if(set_in_boot() == _TRUE)
    {
        return;                                     // the SDK store set it up at boot
    }
    SET_OSD_DP_D1_VERSION((BYTE)iV);
#if(_DP_SUPPORT == _ON)
    UserCommonInterfaceDpVersionSwitch(_D1_INPUT_PORT, UserInterfaceGetDPVersion(_D1_INPUT_PORT), UserCommonInterfaceGetDpMstCapablePort());
    if(SysSourceGetInputPort() == _D1_INPUT_PORT)
    {
        SysModeSetResetTarget(_MODE_ACTION_RESET_TO_SEARCH);
    }
#endif
}

void set_ap_dp_edid(BYTE ucId, int iV)
{
    ucId = ucId;
    if(set_in_boot() == _TRUE)
    {
        return;                                     // the SDK store set it up at boot
    }
    UserCommonNVRamSetSystemData(_EDID_D1_SELECT, (BYTE)iV);
#if((_EMBEDDED_EDID_SUPPORT == _ON) && (_DP_SUPPORT == _ON))
    UserCommonInterfaceDPSwitchEdid(_D1_INPUT_PORT);
#endif
}

void set_ap_osd_pos(BYTE ucId, int iV)
{
    if(ucId == AWTO_SET_OSD_HPOS)
    {
        SET_OSD_HPOS((BYTE)iV);
    }
    else
    {
        SET_OSD_VPOS((BYTE)iV);
    }
    menu_relayout();
}

void set_ap_osd_scale(BYTE ucId, int iV)
{
    ucId = ucId;
    SET_OSD_NVRAM_DOUBLE_SIZE((BYTE)iV);
    menu_relayout();
}

void set_ap_osd_font(BYTE ucId, int iV)
{
    ucId = ucId;
    if(g_ucAwtoMenuOn != 0)
    {
        osd_font_load((BYTE)iV);                  // same glyph IDs and 8 px geometry; redraw uses the new atlas
    }
}

void set_ap_osd_transparency(BYTE ucId, int iV)
{
    ucId = ucId;
    SET_OSD_TRANSPARENCY_STATUS((BYTE)(((WORD)iV * 255) / 100));
    OsdFuncTransparency(GET_OSD_TRANSPARENCY_STATUS());
}

void set_ap_sdk_language(BYTE ucId, int iV)
{
    ucId = ucId;
    SET_OSD_LANGUAGE((BYTE)iV);
}

void set_ap_debug_msgs(BYTE ucId, int iV)
{
    ucId = ucId;
#if(_DEBUG_MESSAGE_SUPPORT == _ON)
    g_stOSDUserData.b1AwtoMsgOn = (iV != 0);
    g_ucAwtoMsgOn = (iV != 0);
#else
    iV = iV;
#endif
}

void set_ap_msg_log(BYTE ucId, int iV)
{
    ucId = ucId;
    g_ucAwtoMsgLog = (iV != 0);
}

void set_ap_debug_popup(BYTE ucId, int iV)
{
    ucId = ucId;
    iV = iV;
    AwtoDiagConsole(1);                            // closes the menu; was the info pop-up hook (ucDbgPopup), gone with #124
}

void set_ap_key_test(BYTE ucId, int iV)
{
    ucId = ucId;
    iV = iV;
    menu_close();
    AwtoKeyTestSet(2);
}

void set_ap_gpio_test(BYTE ucId, int iV)
{
    ucId = ucId;
    iV = iV;
    menu_close();
    AwtoGpioTestSet(1);
}

void set_ap_factory_menu(BYTE ucId, int iV)
{
    ucId = ucId;
    iV = iV;
    menu_close();
#if(_AWTO_FACTORY == _ON)
    OsdDispDisableOsd();
    ScalerOsdMapRotation(0, _ENABLE, HEIGHT(_FACTORY_OSD_ROW), _DISABLE, 0, _DISABLE);
    RTDFactoryMainMenu();
#endif
}

void set_ap_power(BYTE ucId, int iV)               // placeholder store (see StAwtoPwrCfg)
{
    switch(ucId)
    {
        case AWTO_SET_PWR_L1_EN: g_stAwtoPwrCfg.ucL1En = (BYTE)iV; break;
        case AWTO_SET_PWR_L2_EN: g_stAwtoPwrCfg.ucL2En = (BYTE)iV; break;
        case AWTO_SET_PWR_L3_EN: g_stAwtoPwrCfg.ucL3En = (BYTE)iV; break;
        case AWTO_SET_PWR_L1_MS: g_stAwtoPwrCfg.usL1Ms = (WORD)iV; break;
        case AWTO_SET_PWR_L2_S: g_stAwtoPwrCfg.usL2S = (WORD)iV; break;
        case AWTO_SET_PWR_L3_S: g_stAwtoPwrCfg.usL3S = (WORD)iV; break;
        default:
            if((ucId >= AWTO_SET_WAKE_D1) && (ucId <= AWTO_SET_WAKE_D3))
            {
                BYTE ucBit = (BYTE)(1 << (ucId - AWTO_SET_WAKE_D1));

                g_stAwtoPwrCfg.ucWake = (iV != 0) ? (g_stAwtoPwrCfg.ucWake | ucBit) : (g_stAwtoPwrCfg.ucWake & ~ucBit);
            }
            break;
    }
}

#include "glue_nv.inc"

//---- hooks ----
void AwtoSetInit(void)                             // UserInterfaceInitial, after RTDNVRamStartup: values for boot readers
{
    set_load();
    AwtoNvLoad();                                  // aux rows; SDK rows are the SDK store's fields (#151)
    g_ucAwtoDdcciOn = (set_get(AWTO_SET_DDCCI) != 0);             // spare-engine DDC/CI 0x37 (#60); debug 0x35 stays
    g_ucAwtoKeepIdle = (set_get(AWTO_SET_KEEP_IDLE_RX) != 0);
}

void AwtoSetLoop(void)                             // main loop (AWTO_SET_LOOP: every pass while our menu is up, else every 20 ms)
{
    g_usAwtoSetLast = g_stAwtoDiag.usT2Isr;
    if(s_ucAwtoSetBooted == 0)
    {
        s_ucAwtoSetBooted = 1;
        set_boot();                                // recovery keys, then every apply
    }
    set_service();
    AwtoNvService();
    if((SysSourceGetInputPort() >= _D1_INPUT_PORT) && (SysSourceGetInputPort() <= _D3_INPUT_PORT))
    {
        set_track(AWTO_SET_INPUT, SysSourceGetInputPort() - _D1_INPUT_PORT);   // every switch path (key, test cmd, VCP 0x60, search), #67
    }
    if(vcp_box.cmd != 0)
    {
        g_ucAwtoNvDdc = 1;                         // the host mailbox (debug link) counts as DDC/CI for the gate
    }
    vcp_box_service();
    if((menu_active() != 0) && ((SysPowerGetPowerStatus() != _POWER_STATUS_NORMAL) || (SysModeGetModeState() == _MODE_STATUS_POWER_SAVING)))
    {
        menu_close();                              // power off / saving takes the screen: OsdDispDisableOsd is blocked while the menu is up
    }
    if(menu_active() != 0)
    {
        menu_service();
        if((GET_OSD_EVENT_MESSAGE() >= _OSDEVENT_SHOW_NOSIGNAL_MSG) && (GET_OSD_EVENT_MESSAGE() <= _OSDEVENT_ACTIVE_DO_ONE_TIME_MSG))
        {
            SET_OSD_EVENT_MESSAGE(_OSDEVENT_NONE_MSG);      // pop-ups would draw over our menu
        }
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_SIGNAL);
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_CABLE);
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_GO_TO_POWER_SAVING);
    }
}

void AwtoMenuForget(void)                          // OsdDispDisableOsd: the vendor OSD took the screen
{
    g_ucAwtoMenuOn = 0;
    menu_forget();
}

#endif
