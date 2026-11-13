#include "UserCommonInclude.h"
#include <stddef.h>

// #67 settings glue: the clean settings / menu / VCP code (awto-rtdfw awto/settings, awto/nvram) on this firmware.
// - implements set_status, set_ap_*, ui_*; text layer: fw/osd/text_layer.c; fl_*: fw/nvram/flash_io.c; NVRAM gate: fw/nvram/nv_gate.c
// - hooks: AwtoSetInit (after RTDNVRamStartup), AwtoSetLoop (main loop), AwtoMenuForget (vendor OSD closes)
#if(_OSD_TYPE == _REALTEK_2014_OSD)
#ifdef _AWTO_NEW_SETTINGS

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


//---- time, keys, status ----
WORD set_now_ms(void)                          // monotonic: d_isr_g_usTimerCounter is rebased to 0 by ScalerTimerCheckTimerEvent (#132)
{
    return (WORD)AwtoMs();
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
            return isr_g_stAwtoDiag.usLoopRate;
        case AWTO_SET_INFO_SCHEMA:
            return AWTO_SET_SCHEMA;
        default:
            return 0;
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

    if(AWTO_PORT_OFF(ucP))
    {
        return 4;                                  // UPS_DISABLED (#81)
    }
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
    if(g_stAwtoFreq.ucValid != 0)
    {
        pst->ulVmHz = g_stAwtoFreq.ulVFreqmHz;     // exact: measured clock / (htotal x vtotal) (#34)
        return _TRUE;
    }
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

//---- audio (docs/audio.md): DVC digital gain, mute; the SDK SysAudio state machine does the unmute/mute sequencing ----
#if(_AUDIO_SUPPORT == _ON)
// volume % -> DVC_GAIN (linear, 0x3FFF = 0 dB), Dahua-like (#94): 50 % = AWTO_AUDIO_GAIN_DAHUA_50 (-16.5 dB), 100 % = AWTO_AUDIO_GAIN_MAX;
// dB-even per 10 %: 10..50 % from -40 dB (5.9 dB / step), 50..100 % 2.1 dB / step; 0 % = silence, linear between the points
static __code unsigned int tAwtoVolGain[11] = {0, 164, 322, 633, 1244, AWTO_AUDIO_GAIN_DAHUA_50, 3113, 3965, 5049, 6431, AWTO_AUDIO_GAIN_MAX};

unsigned int AwtoAudioGain(unsigned char ucV)
{
    unsigned int usA;

    usA = AwtoAudioTestGain();                  // ear-test step held (dev.py sound-test): its level
    if(usA != 0)
    {
        return usA;
    }
    if(ucV >= 100)
    {
        return AWTO_AUDIO_GAIN_MAX;
    }
    usA = tAwtoVolGain[ucV / 10];
    return usA + (unsigned int)(((unsigned long)(tAwtoVolGain[ucV / 10 + 1] - usA) * (ucV % 10)) / 10);
}
#endif

void set_ap_volume(BYTE ucId, int iV)
{
    ucId = ucId;
    SET_OSD_VOLUME((BYTE)iV);
#if(_AUDIO_SUPPORT == _ON)
    if((set_in_boot() == _FALSE) && (UserInterfaceGetAudioReadyToPlayStatus() == _TRUE))
    {
        UserAdjustAudioVolume(GET_OSD_VOLUME());
    }
#endif
}

void set_ap_mute(BYTE ucId, int iV)
{
    ucId = ucId;
    SET_OSD_VOLUME_MUTE(iV == 1);                   // option 1 = On (VCP 0x8D value 1 = muted)
#if(_AUDIO_SUPPORT == _ON)
    if((set_in_boot() == _FALSE) && ((iV == 1) || (UserInterfaceGetAudioReadyToPlayStatus() == _TRUE)))
    {
        UserAdjustAudioMuteSwitch();
    }
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
        SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_DISPLAY_SETTING, AWTO_SYS_BY_SETTINGS);
    }
}

// #165 Rotate (disp_rotate 0 / 180) + Mirror (mirror Off / Horizontal / Vertical): one owner. Flip bits H = 1, V = 2 (= mirror
// option index); effective = (Rotate 180 ? H | V : 0) XOR mirror -> SDK b3OsdDispRotate, read at the next display setting. One E4 line.
void set_ap_rotate(BYTE ucId, int iV)
{
    BYTE ucRot = (BYTE)((ucId == AWTO_SET_DISP_ROTATE) ? iV : set_get(AWTO_SET_DISP_ROTATE));
    BYTE ucMir = (BYTE)((ucId == AWTO_SET_MIRROR) ? iV : set_get(AWTO_SET_MIRROR)) & AWTO_FLIP_HV;
    BYTE ucFlip = ((ucRot != 0) ? AWTO_FLIP_HV : 0) ^ ucMir;
    BYTE ucWhat = AWTO_ROT_NOT_BUILT;
#if(_DISPLAY_ROTATION_SUPPORT == _ON)
    static __code BYTE tFlipToSdk[4] = {_DISP_ROTATE_0, _DISP_ROTATE_HOR_MIRROR, _DISP_ROTATE_VER_MIRROR, _DISP_ROTATE_180};

    if(GET_OSD_DISP_ROTATE() == tFlipToSdk[ucFlip])
    {
        ucWhat = AWTO_ROT_ALREADY;
    }
    else
    {
        SET_OSD_DISP_ROTATE(tFlipToSdk[ucFlip]);
        ucWhat = AWTO_ROT_STORED;
        if((set_in_boot() == _FALSE) && (SysModeGetModeState() == _MODE_STATUS_ACTIVE))
        {
            ucWhat = AWTO_ROT_APPLIED;
            SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_DISPLAY_SETTING, AWTO_SYS_BY_SETTINGS);
        }
    }
#endif
    AwtoSyncPush(AWTO_SYNC_EV_ROT, (ucWhat << 2) | ucFlip, ((DWORD)ucRot << 8) | ucMir);
}

void set_ap_overscan(BYTE ucId, int iV)
{
    ucId = ucId;
    SET_OSD_OVERSCAN_STATUS((BYTE)iV);
    if(SysModeGetModeState() == _MODE_STATUS_ACTIVE)
    {
        SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_DISPLAY_SETTING, AWTO_SYS_BY_SETTINGS);
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
        SysMachineRequest(_POWER_STATUS_NORMAL, AWTO_SYS_BY_VCP);
    }
    else
    {
        SET_FORCE_POW_SAV_STATUS(_TRUE);
        SysMachineRequest(_POWER_STATUS_SAVING, AWTO_SYS_BY_VCP);
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
        SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_SEARCH, AWTO_SYS_BY_SETTINGS);
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
    iV = iV;                                    // stored by set_sdk_put (glue_nv) before the apply
    OsdFuncTransparency(GET_OSD_TRANSPARENCY_STATUS());     // live: the screen open now (type from AwtoOsdBlend) blends at it
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


//---- hooks ----
void AwtoSetInit(void)                             // UserInterfaceInitial, after RTDNVRamStartup: values for boot readers
{
    set_load();
    AwtoNvLoad();                                  // aux rows; SDK rows are the SDK store's fields (#151)
    AwtoPortBoot();                                // #81: disabled ports before the first HPD high / DDC enable / search
    g_ucAwtoDdcciOn = (set_get(AWTO_SET_DDCCI) != 0);             // spare-engine DDC/CI 0x37 (#60); debug 0x35 stays
    g_ucAwtoKeepIdle = (set_get(AWTO_SET_KEEP_IDLE_RX) != 0);
}

void AwtoSetLoop(void)                             // main loop (AWTO_SET_LOOP: every pass while our menu is up, else every 20 ms)
{
    g_usAwtoSetLast = isr_g_stAwtoDiag.usT2Isr;
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
#endif//#if(_OSD_TYPE == _REALTEK_2014_OSD)
