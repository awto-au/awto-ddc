// #67 settings glue (integrator-owned, private): the clean settings / menu / VCP code (awto-rtdfw awto/settings,
// awto/nvram) on top of this firmware. Inserted into RTD2014Osd.c by fw/awto/settings/rules.py.
// - implements the clean interfaces: osd_tc_* (text cells on the OSD engine), fl_* (flash), set_status, set_ap_*
// - hooks: AwtoSetInit (after RTDNVRamStartup), AwtoSetLoop (main loop), AwtoMenuKeyHook (OSD key flow),
//   AwtoMenuForget (vendor OSD closes); DDC/CI hooks: glue_ddcci.inc
#ifdef _AWTO_NEW_SETTINGS
#include <stddef.h>

// clean API (awto-rtdfw awto/include: settings.h, menu.h, vcp.h); int = int16_t, WORD = uint16_t
extern void set_load(void);
extern void set_boot(void);
extern void set_service(void);
extern void set_track(BYTE ucId, int iV);
extern int set_put(BYTE ucId, int iV, BYTE ucNow);
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

//---- text layer on the OSD engine (osd.h osd_tc_*, awto-ddc#89): 24 x 36 px characters = 2 x 2 hardware cells of 12 x 18, 2 bpp ----
// palette (index: colour): our own entries over the SDK's, restored when the Realtek SDK menu loads its palette
// 1 red, 2 / 8 grey 66 % / 33 %, 3 white, 4 / 9 / 5 dim 66 % / 33 % / 100 %, 6 / 10 red-white 66 % / 33 %, 7 / 11 dark red 66 % / 33 %, 12 black
static __code BYTE tAwtoPal[12][3] = {
    {255, 0, 0}, {170, 170, 170}, {255, 255, 255}, {73, 73, 73}, {110, 110, 110}, {255, 170, 170},
    {170, 0, 0}, {85, 85, 85}, {37, 37, 37}, {255, 85, 85}, {85, 0, 0}, {0, 0, 0}};
// the 2 bit char word holds the 4 colours c0..c3 of pixel levels 0..3 (c0 = 0: transparent); styles: osd_style
static __code BYTE tAwtoStyle[4][4] = {{0, 8, 2, 3}, {0, 9, 4, 5}, {0, 10, 6, 3}, {0, 11, 7, 1}};
#define AWTO_BAR_BLACK              12
#define AWTO_BAR_RED                1

void osd_tc_open(BYTE ucChars, BYTE ucLines)
{
    BYTE ucI;

    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
    OsdFuncDisableOsd();
    OsdFuncCloseWindow(_OSD_WINDOW_ALL);
    SET_OSD_DOUBLE_SIZE(GET_OSD_NVRAM_DOUBLE_SIZE());
    OsdFuncApplyMap(WIDTH(2 * ucChars), HEIGHT(2 * ucLines), COLOR(0, 0));
    OsdFuncBlending(_OSD_TRANSPARENCY_ONLY_WINDOW);
    OsdFuncTransparency(GET_OSD_TRANSPARENCY_STATUS());
    OsdPaletteSelectPalette(_PALETTE_MAIN_MENU);
    for(ucI = 0; ucI < 12; ucI++)
    {
        ScalerOsdSetColorPalette(ucI + 1, tAwtoPal[ucI][0], tAwtoPal[ucI][1], tAwtoPal[ucI][2]);
    }
    ScalerOsd2BitFontOffset(0);                    // 2 bit glyph i at font base + 18 * i
}

void osd_tc_cells(BYTE ucRow, BYTE ucCell, BYTE __xdata *pucTiles, BYTE ucN, BYTE ucStyle)
{
    BYTE ucC0 = tAwtoStyle[ucStyle][0];
    BYTE ucC1 = tAwtoStyle[ucStyle][1];
    BYTE ucB0 = 0x80 | ((ucC0 & 8) << 2) | ((ucC1 & 8) << 1) | ((tAwtoStyle[ucStyle][3] & 7) << 1) | ((ucC0 & 4) >> 2);
    BYTE ucB2 = ((ucC0 & 3) << 6) | ((tAwtoStyle[ucStyle][2] & 7) << 3) | (ucC1 & 7);

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
    OsdWindowDrawing(ucWin, usX0, usY0, usX1, usY1, (ucColour == 0) ? AWTO_BAR_BLACK : AWTO_BAR_RED);
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
    ScalerSetBit(0x3A17, ~_BIT0, _BIT0);
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, g_usFontTableStart + usTile * 18, _OSD_WITHOUT_DB);
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
    ScalerSetBit(0x3A17, ~(_BIT1 | _BIT0), 0x00);
}

void osd_tc_place(BYTE ucH, BYTE ucV, BYTE ucBig)
{
    SET_OSD_DOUBLE_SIZE(ucBig);
    ScalerOsdDoubleFunction(ucBig, ucBig);
    OsdDispSetPosition(_POS_PERCENT, _OSD_POSITION_GLOBAL_A, ucH, ucV);
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
    ucId = ucId;
    if((GET_OSD_GAMMA() == (BYTE)iV) && (set_in_boot() == _FALSE))
    {
        return;
    }
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
    if(GET_OSD_ASPECT_RATIO_TYPE() == (BYTE)iV)
    {
        return;
    }
    SET_OSD_ASPECT_RATIO_TYPE((BYTE)iV);
    if(SysModeGetModeState() == _MODE_STATUS_ACTIVE)
    {
        SysModeSetResetTarget(_MODE_ACTION_RESET_TO_DISPLAY_SETTING);
    }
}

void set_ap_overscan(BYTE ucId, int iV)
{
    ucId = ucId;
    if(GET_OSD_OVERSCAN_STATUS() == (BYTE)iV)
    {
        return;
    }
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
    set_put(AWTO_SET_INPUT_MODE, 1, 0);
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
    if(GET_OSD_DP_D1_VERSION() == (BYTE)iV)
    {
        return;
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
    if(UserCommonNVRamGetSystemData(_EDID_D1_SELECT) == (BYTE)iV)
    {
        return;
    }
    UserCommonNVRamSetSystemData(_EDID_D1_SELECT, (BYTE)iV);
    SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_SYSTEMDATA_MSG);
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
    menu_close();
    g_stAwtoDiag.ucDbgPopup = 1;
    SET_OSD_EVENT_MESSAGE(_OSDEVENT_ACTIVE_DO_ONE_TIME_MSG);
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

void set_ap_vendor_menu(BYTE ucId, int iV)
{
    ucId = ucId;
    iV = iV;
    menu_close();
    if(SysModeGetModeState() == _MODE_STATUS_ACTIVE)
    {
        SET_OSD_STATE(_MENU_PICTURE);
        OsdFuncSetOsdItemFlag();
        OsdDispMainMenu();
    }
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

//---- hooks ----
void AwtoSetInit(void)                             // UserInterfaceInitial, after RTDNVRamStartup: values for boot readers
{
    set_load();
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
    if((SysSourceGetInputPort() >= _D1_INPUT_PORT) && (SysSourceGetInputPort() <= _D3_INPUT_PORT))
    {
        set_track(AWTO_SET_INPUT, SysSourceGetInputPort() - _D1_INPUT_PORT);   // every switch path (key, test cmd, VCP 0x60, search), #67
    }
    vcp_box_service();
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

bit AwtoMenuKeyHook(void)                          // RTDOsdSystemFlowProc, key present: _TRUE = consumed
{
    BYTE ucKey = GET_KEYMESSAGE();
    BYTE ucMode = SysModeGetModeState();

    if(menu_active() != 0)
    {
        if((ucKey == _LEFT_KEY_MESSAGE) || (ucKey == _RIGHT_KEY_MESSAGE))
        {
            SET_KEYREPEATENABLE();
        }
        menu_key(ucKey);                           // menu.h MK_* = the key message numbers
        return _TRUE;
    }
    if((ucKey == _MENU_KEY_MESSAGE) && (GET_OSD_STATE() == _MENU_NONE) && (GET_OSD_IN_FACTORY_MENU_STATUS() == _FALSE) &&
       (set_get(AWTO_SET_MENU_SELECT) == 0) &&
       ((ucMode == _MODE_STATUS_ACTIVE) || (ucMode == _MODE_STATUS_NOSIGNAL) || (ucMode == _MODE_STATUS_NOSUPPORT)))
    {
        menu_open();
        return _TRUE;
    }
    return _FALSE;
}

void AwtoMenuForget(void)                          // OsdDispDisableOsd: the vendor OSD took the screen
{
    g_ucAwtoMenuOn = 0;
    menu_forget();
}

#endif
