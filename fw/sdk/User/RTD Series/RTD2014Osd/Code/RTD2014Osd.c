/********************************************************************************/
/*   The  Software  is  proprietary,  confidential,  and  valuable to Realtek   */
/*   Semiconductor  Corporation  ("Realtek").  All  rights, including but not   */
/*   limited  to  copyrights,  patents,  trademarks, trade secrets, mask work   */
/*   rights, and other similar rights and interests, are reserved to Realtek.   */
/*   Without  prior  written  consent  from  Realtek,  copying, reproduction,   */
/*   modification,  distribution,  or  otherwise  is strictly prohibited. The   */
/*   Software  shall  be  kept  strictly  in  confidence,  and  shall  not be   */
/*   disclosed to or otherwise accessed by any third party.                     */
/*   c<2003> - <2012>                                                           */
/*   The Software is provided "AS IS" without any warranty of any kind,         */
/*   express, implied, statutory or otherwise.                                  */
/********************************************************************************/

//----------------------------------------------------------------------------------------------------
// ID Code      : RTD2014Osd.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __RTD_OSD__

#include "UserCommonInclude.h"

#if(_OSD_TYPE == _REALTEK_2014_OSD)

//****************************************************************************
// DEFINITIONS / MACROS
//****************************************************************************


//****************************************************************************
// STRUCT / TYPE / ENUM DEFINITTIONS
//****************************************************************************


//****************************************************************************
// CODE TABLES
//****************************************************************************


//****************************************************************************
// VARIABLE DECLARATIONS
//****************************************************************************
StructOsdInfo g_stOsdInfo;

WORD g_usAdjustValue;
WORD g_usBackupValue;

//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
void UserOsdHandler(void);
void RTDOsdSystemFlowProc(void);
void RTDOsdEventMsgProc(void);

//***************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  : OSD Handler, executed in the main loop
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void UserOsdHandler(void)
{
    RTDOsdSystemFlowProc();
    RTDOsdEventMsgProc();
}

//--------------------------------------------------
// Description  : OSD system flow
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void RTDOsdSystemFlowProc(void)
{
    switch(SysModeGetModeState())
    {
        case _MODE_STATUS_POWER_OFF:

            if(SysModeGetModeStateChange() == _TRUE)
            {
                SET_FORCE_POW_SAV_STATUS(_FALSE);
            }

            break;

        case _MODE_STATUS_INITIAL:

            if(SysModeGetModeStateChange() == _TRUE)
            {
#if(_FREESYNC_OD_MEASURE == _ON)
                UserAdjustFREESYNCODMeasure();
#endif

                AWTO_BPROF(0x3B);
                AwtoBootConsole();      // #162: the panel is the panel machine's, requested at the power switch
            }

            break;

        case _MODE_STATUS_SEARCH:

#if(_FREEZE_SUPPORT == _ON)
            if((SysModeGetModeStateChange() == _TRUE) && (GET_OSD_FREEZE_STATUS() == _ON))
            {
                SET_OSD_FREEZE_STATUS(_OFF);
            }
#endif
            break;

        case _MODE_STATUS_DISPLAY_SETTING:

            break;

        case _MODE_STATUS_ACTIVE:

            break;

        case _MODE_STATUS_NOSUPPORT:

            if(SysModeGetModeStateChange() == _TRUE)
            {
                if(SysPowerGetPowerStatus() == _POWER_STATUS_NORMAL)
                {
                    SET_OSD_EVENT_MESSAGE(_OSDEVENT_SHOW_NOSUPPORT_MSG);
                }
            }

            break;

        case _MODE_STATUS_NOSIGNAL:

            if(SysModeGetModeStateChange() == _TRUE)
            {
                if(SysSourceGetCableDetect(UserCommonNVRamGetSystemData(_SEARCH_PORT)) == _TRUE)
                {
                    ScalerTimerActiveTimerEvent(SEC(2), _USER_TIMER_EVENT_OSD_SHOW_NO_SIGNAL);
                }
                else
                {
                    ScalerTimerActiveTimerEvent(SEC(2), _USER_TIMER_EVENT_OSD_SHOW_NO_CABLE);
                }
            }

            break;

        case _MODE_STATUS_POWER_SAVING:

            if(SysSourceGetCableDetect(SysSourceGetInputPort()) == _FALSE)
            {
                SET_FORCE_POW_SAV_STATUS(_FALSE);
            }

            if(SysPowerGetPowerStatus() == _POWER_STATUS_NORMAL)
            {
                if(GET_OSD_POWER_SAVING_SHOW_SOURCE() == _TRUE)
                {
                    SET_OSD_POWER_SAVING_SHOW_SOURCE(_FALSE);

                    SET_OSD_EVENT_MESSAGE(_OSDEVENT_SHOW_CHANGE_SOURCE_MENU_MSG);
                }
#if(_DP_DEBUG_MSG == _ON)
                else if(GET_OSD_POWER_SAVING_SHOW_DP_INFO() == _TRUE)
                {
                    SET_OSD_POWER_SAVING_SHOW_DP_INFO(_FALSE);

                    OsdDispOsdMessage(_OSD_DISP_INPUT_SIGNAL_MSG);
                    UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, AWTO_PNL_BY_OSD_DPINFO));
                }
#endif
            }

            break;

        case _MODE_STATUS_FACTORY:

            break;

        default:

            break;
    }

#if(_DP_EMBEDDED_SWITCH_SUPPORT_TYPE == _DP_EMBEDDED_SWITCH_2_DP)
    // Check embedded DP switch status
    UserCommonAdjustEmbeddedDpSwitch();
#endif

}

//--------------------------------------------------
// Description  : OSD event message processing function
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void RTDOsdEventMsgProc(void)
{
    switch(GET_OSD_EVENT_MESSAGE())
    {
        case _OSDEVENT_SHOW_NOSIGNAL_MSG:
            OsdDispOsdMessage(_OSD_DISP_NOSIGNAL_MSG);
            UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, AWTO_PNL_BY_OSD_NOSIGNAL));
            ScalerTimerActiveTimerEvent(SEC(3), _USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
            break;

        case _OSDEVENT_SHOW_NOCABLE_MSG:
            OsdDispOsdMessage(_OSD_DISP_NOCABLE_MSG);
            UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, AWTO_PNL_BY_OSD_NOCABLE));
            ScalerTimerActiveTimerEvent(SEC(3), _USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
            break;

        case _OSDEVENT_SHOW_NOSUPPORT_MSG:

            ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_CABLE);
            ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_SIGNAL);

            OsdDispOsdMessage(_OSD_DISP_NOSUPPORT_MSG);
            UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, AWTO_PNL_BY_OSD_NOSUPPORT));
            ScalerTimerReactiveTimerEvent(SEC(3), _USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
            break;

        case _OSDEVENT_SHOW_FAIL_SAFE_MODE_MSG:
            OsdDispOsdMessage(_OSD_DISP_FAIL_SAFE_MODE_MSG);
            break;

        case _OSDEVENT_SHOW_CHANGE_SOURCE_MENU_MSG:
            ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_GO_TO_POWER_SAVING);
            ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_CABLE);
            ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_SIGNAL);
            SET_OSD_STATE(_MENU_HOTKEY_SOURCE);
            OsdFuncSetOsdItemFlag();
            g_usBackupValue = GET_OSD_INPUT_PORT_OSD_ITEM();
            AwtoSourceOpen(AWTO_SEL_EV_OPEN_CARD);

            UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, AWTO_PNL_BY_OSD_SOURCE));
            break;

        case _OSDEVENT_SHOW_POWER_SAVING_EVENT_MSG:
            OsdDispDisableOsd();
            OsdDispOsdMessage(_OSD_DISP_POWER_SAVING_MSG);
            UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, AWTO_PNL_BY_OSD_PS));
            ScalerTimerActiveTimerEvent(SEC(2), _USER_TIMER_EVENT_GO_TO_POWER_SAVING);
            break;

        case _OSDEVENT_GO_TO_POWER_SAVING_EVENT_MSG:

            OsdDispDisableOsd();
            SysMachineRequest(_POWER_STATUS_SAVING, AWTO_SYS_BY_OSD_PS);
            break;

#if(_VGA_SUPPORT == _ON)
        case _OSDEVENT_DO_AUTO_CONFIG_MSG:
#if(_FREEZE_SUPPORT == _ON)
            ScalerTimerWaitForActiveTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE_FREEZE_MSG);
#endif
            OsdDispAutoConfigProc();
            break;
#endif

        case _OSDEVENT_ACTIVE_DO_ONE_TIME_MSG:

#if(_FREEZE_SUPPORT == _ON)
            ScalerTimerWaitForActiveTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE_FREEZE_MSG);
#endif

#if(_VGA_SUPPORT == _ON)
            if(SysSourceGetSourceType() == _SOURCE_VGA)
            {
                if(UserInterfaceGetFirstAutoConfigStatus() == _TRUE)
                {
                    OsdDispAutoConfigProc();
                }
            }
#endif

            if(GET_OSD_STATE() == _MENU_NONE)
            {
                AwtoSwEvent(AWTO_SW_EV_PROBE, 9);
                OsdDispOsdMessage(_OSD_DISP_INPUT_SIGNAL_MSG);
                AwtoSwEvent(AWTO_SW_EV_PROBE, 10);
                ScalerTimerActiveTimerEvent(SEC(_AWTO_INFO_POPUP_SEC), _USER_TIMER_EVENT_OSD_DISABLE); /* awto: info pop-up time _AWTO_INFO_POPUP_SEC */
            }
            break;

        case _OSDEVENT_SAVE_NVRAM_SYSTEMDATA_MSG:
            UserCommonNVRamSaveSystemData();
            break;

#if(_VGA_SUPPORT == _ON)
        case _OSDEVENT_SAVE_NVRAM_MODEUSERDATA_MSG:
            UserCommonNVRamSaveModeUserData();
            break;
#endif
        case _OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG:
            RTDNVRamSaveOSDData();
            break;

#if(_VGA_SUPPORT == _ON)
        case _OSDEVENT_SAVE_NVRAM_ADCDATA_MSG:
            if(ScalerColorGetColorSpaceRGB(UserCommonInterfaceGetColorFormat()) == _TRUE)
            {
                UserCommonNVRamSaveADCSetting(_COLOR_SPACE_RGB);
            }
            else
            {
                UserCommonNVRamSaveADCSetting(_COLOR_SPACE_YPBPR);
            }
            break;
#endif

        case _OSDEVENT_SAVE_NVRAM_COLORPROC_MSG:
            RTDNVRamSaveColorSetting(GET_COLOR_TEMP_TYPE());
            break;

        case _OSDEVENT_SAVE_NVRAM_BRICON_MSG:
            RTDNVRamSaveBriCon(SysSourceGetSourceType());
            break;

        case _OSDEVENT_SAVE_NVRAM_OSDSIXCOLORDATA_MSG:
            RTDNVRamSaveSixColorData();
            break;

        default:
            break;
    }

    SET_OSD_EVENT_MESSAGE(_OSDEVENT_NONE_MSG);
}

























































#if(_INTERNAL_AUDIO_TEST_SUPPORT == _ON)
#endif












































#if(_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
void MenuAdvanceTypeCModeD0(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:

#if(_D0_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            g_usBackupValue = GET_OSD_D0_TYPE_C_U3_MODE();
            SET_OSD_STATE(_MENU_ADVANCE_D0_TYPE_C_MODE_ADJUST);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _SELECT, g_usBackupValue);
#endif
            break;

        case _RIGHT_KEY_MESSAGE:
#if(_D1_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            SET_OSD_STATE(_MENU_ADVANCE_TYPE_C_MODE_D1);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, GET_OSD_D1_TYPE_C_U3_MODE());
#elif(_D6_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            SET_OSD_STATE(_MENU_ADVANCE_TYPE_C_MODE_D6);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, GET_OSD_D6_TYPE_C_U3_MODE());
#endif
            break;

        case _LEFT_KEY_MESSAGE:

            break;

        case _EXIT_KEY_MESSAGE:

            OsdDispMainMenuIconPage(_UP, _ICON_PAGE_CLEAR);

            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
}

void MenuAdvanceTypeCModeD1(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:

#if(_D1_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            g_usBackupValue = GET_OSD_D1_TYPE_C_U3_MODE();

            SET_OSD_STATE(_MENU_ADVANCE_D1_TYPE_C_MODE_ADJUST);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _SELECT, g_usBackupValue);
#endif

            break;

        case _RIGHT_KEY_MESSAGE:
#if(_D6_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            SET_OSD_STATE(_MENU_ADVANCE_TYPE_C_MODE_D6);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, GET_OSD_D6_TYPE_C_U3_MODE());
#endif
            break;

        case _LEFT_KEY_MESSAGE:
#if(_D0_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            SET_OSD_STATE(_MENU_ADVANCE_TYPE_C_MODE_D0);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, GET_OSD_D0_TYPE_C_U3_MODE());
#endif
            break;

        case _EXIT_KEY_MESSAGE:
            OsdDispMainMenuIconPage(_UP, _ICON_PAGE_CLEAR);
            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
}

void MenuAdvanceTypeCModeD2(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:

            break;

        case _RIGHT_KEY_MESSAGE:
#if(_D6_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            SET_OSD_STATE(_MENU_ADVANCE_DP_OPTION_D6);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, GET_OSD_D6_TYPE_C_U3_MODE());
#endif
            break;

        case _LEFT_KEY_MESSAGE:
#if(_D1_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            SET_OSD_STATE(_MENU_ADVANCE_DP_OPTION_D1);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, GET_OSD_D1_TYPE_C_U3_MODE());
#elif(_D0_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            SET_OSD_STATE(_MENU_ADVANCE_DP_OPTION_D0);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, GET_OSD_D0_TYPE_C_U3_MODE());
#endif
            break;

        case _EXIT_KEY_MESSAGE:
            OsdDispMainMenuIconPage(_UP, _ICON_PAGE_CLEAR);

            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
}

void MenuAdvanceTypeCModeD6(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
#if(_D6_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            g_usBackupValue = GET_OSD_D6_TYPE_C_U3_MODE();
            SET_OSD_STATE(_MENU_ADVANCE_D6_TYPE_C_MODE_ADJUST);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _SELECT, g_usBackupValue);
#endif

            break;

        case _RIGHT_KEY_MESSAGE:
            break;

        case _LEFT_KEY_MESSAGE:
#if(_D1_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            SET_OSD_STATE(_MENU_ADVANCE_DP_OPTION_D1);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, GET_OSD_D1_TYPE_C_U3_MODE());
#elif(_D0_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            SET_OSD_STATE(_MENU_ADVANCE_DP_OPTION_D0);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, GET_OSD_D0_TYPE_C_U3_MODE());
#endif
            break;

        case _EXIT_KEY_MESSAGE:
            OsdDispMainMenuIconPage(_UP, _ICON_PAGE_CLEAR);

            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
}
#endif

#if(_HDR10_SUPPORT == _ON)
void MenuAdvanceHdrMode(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            g_usBackupValue = GET_OSD_HDR_MODE();

            SET_OSD_STATE(_MENU_ADVANCE_HDR_MODE_ADJUST);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_HDR_MODE_SELECT, _SELECT, GET_OSD_HDR_MODE());
            break;

        case _RIGHT_KEY_MESSAGE:

            if(UserCommonHDRGetHDR10Status() == _HDR10_OFF)
                return;

            SET_OSD_STATE(_MENU_ADVANCE_HDR_DARK_ENHANCE_ONOFF);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _UNSELECT, GET_OSD_DARK_ENHANCE_STATUS());
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_ON_OFF);
            break;

        case _LEFT_KEY_MESSAGE:
            break;

        case _EXIT_KEY_MESSAGE:

            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
}

void MenuAdvanceHdrDarkEnhanceOnOff(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            g_usBackupValue = GET_OSD_DARK_ENHANCE_STATUS();
            SET_OSD_STATE(_MENU_ADVANCE_HDR_DARK_ENHANCE_ONOFF_ADJUST);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _SELECT, GET_OSD_DARK_ENHANCE_STATUS());
            break;

        case _RIGHT_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_HDR_SHARPNESS_ONOFF);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _UNSELECT, GET_OSD_HDR_SHARPNESS());
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_ON_OFF);
            break;

        case _LEFT_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_HDR_MODE);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispMainMenuOptionSetting(_OPTION_HDR_MODE_SELECT, _UNSELECT, GET_OSD_HDR_MODE());
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_HDR_MODE);
            break;

        case _EXIT_KEY_MESSAGE:

            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
}
void MenuAdvanceHdrSharpnessOnOff(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            g_usBackupValue = GET_OSD_HDR_SHARPNESS();
            SET_OSD_STATE(_MENU_ADVANCE_HDR_SHARPNESS_ONOFF_ADJUST);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _SELECT, GET_OSD_HDR_SHARPNESS());
            break;

        case _RIGHT_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_HDR_CONTRAST);
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispClearSelectColor(_DOWN);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispSliderAndNumber(_MENU_ADVANCE_HDR_CONTRAST, GET_OSD_HDR_CONTRAST());
            break;

        case _LEFT_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_HDR_DARK_ENHANCE_ONOFF);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _UNSELECT, GET_OSD_DARK_ENHANCE_STATUS());
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_ON_OFF);
            break;

        case _EXIT_KEY_MESSAGE:

            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
}
void MenuAdvanceHdrContrast(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            g_usBackupValue = GET_OSD_HDR_CONTRAST();
            SET_OSD_STATE(_MENU_ADVANCE_HDR_CONTRAST_ADJUST);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), GET_OSD_HDR_CONTRAST(), _SLIDER_0, _SELECT);
            break;

        case _RIGHT_KEY_MESSAGE:
#if((_HDR10_COLOR_ENHANCE_SUPPORT == _ON)||(_HDR10_LIGHT_ENHANCE_SUPPORT == _ON))
#if(_HDR10_COLOR_ENHANCE_SUPPORT == _ON)
            SET_OSD_STATE(_MENU_ADVANCE_HDR_COLOR_ENHANCE);
            OsdDispMainMenuIconPage(_UP, _ICON_PAGE_CLEAR);
            OsdDispMainMenuIconPage(_UP, _ICON_PAGE_HDR_ADJUST_1);
            OsdDispClearSliderAndNumber();
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispClearSelectColor(_DOWN);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispSliderAndNumber(_MENU_ADVANCE_HDR_COLOR_ENHANCE, GET_OSD_HDR_COLOR_ENHANCE());
#elif(_HDR10_LIGHT_ENHANCE_SUPPORT == _ON)
            SET_OSD_STATE(_MENU_ADVANCE_HDR_LIGHT_ENHANCE);
            OsdDispMainMenuIconPage(_UP, _ICON_PAGE_CLEAR);
            OsdDispMainMenuIconPage(_UP, _ICON_PAGE_HDR_ADJUST_1);
            OsdDispClearSliderAndNumber();
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispClearSelectColor(_DOWN);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispSliderAndNumber(_MENU_ADVANCE_HDR_LIGHT_ENHANCE, GET_OSD_HDR_LIGHT_ENHANCE());
#endif
#endif
            break;

        case _LEFT_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_HDR_SHARPNESS_ONOFF);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispClearSliderAndNumber();
            OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _UNSELECT, GET_OSD_HDR_SHARPNESS());
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_ON_OFF);
            break;

        case _EXIT_KEY_MESSAGE:

            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
}
void MenuAdvanceHdrColorEnhance(void)
{
#if(_HDR10_COLOR_ENHANCE_SUPPORT == _ON)
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            g_usBackupValue = GET_OSD_HDR_COLOR_ENHANCE();

            SET_OSD_STATE(_MENU_ADVANCE_HDR_COLOR_ENHANCE_ADJUST);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), ((WORD)GET_OSD_HDR_COLOR_ENHANCE()*100/_LEVEL_H), _SLIDER_0, _SELECT);

            break;

        case _RIGHT_KEY_MESSAGE:
#if(_HDR10_LIGHT_ENHANCE_SUPPORT == _ON)
            SET_OSD_STATE(_MENU_ADVANCE_HDR_LIGHT_ENHANCE);
            OsdDispClearSliderAndNumber();
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispClearSelectColor(_DOWN);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispSliderAndNumber(_MENU_ADVANCE_HDR_LIGHT_ENHANCE, GET_OSD_HDR_LIGHT_ENHANCE());
#endif
            break;

        case _LEFT_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_HDR_CONTRAST);
            OsdDispMainMenuIconPage(_UP, _ICON_PAGE_HDR_ADJUST);
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispClearSelectColor(_DOWN);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispSliderAndNumber(_MENU_ADVANCE_HDR_CONTRAST, GET_OSD_HDR_CONTRAST());
            break;

        case _EXIT_KEY_MESSAGE:

            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
#endif
}
void MenuAdvanceHdrLightEnhance(void)
{
#if(_HDR10_LIGHT_ENHANCE_SUPPORT == _ON)
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            g_usBackupValue = GET_OSD_HDR_LIGHT_ENHANCE();

            SET_OSD_STATE(_MENU_ADVANCE_HDR_LIGHT_ENHANCE_ADJUST);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), ((WORD)GET_OSD_HDR_LIGHT_ENHANCE()*100/_LEVEL_H), _SLIDER_0, _SELECT);
            break;

        case _RIGHT_KEY_MESSAGE:
            break;

        case _LEFT_KEY_MESSAGE:
#if(_HDR10_COLOR_ENHANCE_SUPPORT == _ON)
            SET_OSD_STATE(_MENU_ADVANCE_HDR_COLOR_ENHANCE);
            OsdDispClearSliderAndNumber();
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispClearSelectColor(_DOWN);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispSliderAndNumber(_MENU_ADVANCE_HDR_COLOR_ENHANCE, GET_OSD_HDR_COLOR_ENHANCE());
#else
            SET_OSD_STATE(_MENU_ADVANCE_HDR_CONTRAST);
            OsdDispMainMenuIconPage(_UP, _ICON_PAGE_HDR_ADJUST);
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispClearSelectColor(_DOWN);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispSliderAndNumber(_MENU_ADVANCE_HDR_CONTRAST, GET_OSD_HDR_CONTRAST());
#endif
            break;

        case _EXIT_KEY_MESSAGE:

            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
#endif
}



#endif


#if(_HDMI_MULTI_EDID_SUPPORT == _ON)
void MenuAdvanceHDMIVersionAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            switch(GET_PORT_TYPE(SysSourceGetInputPortType(_D0_INPUT_PORT + g_usAdjustValue)))
            {
                case _PORT_HDMI20:
                case _PORT_HDMI:
                case _PORT_MHL:

#if(_D0_HDMI_MULTI_EDID_SUPPORT == _OFF)
                    if(g_usAdjustValue == 0)
                    {
                        break;
                    }
#endif
#if(_D1_HDMI_MULTI_EDID_SUPPORT == _OFF)
                    if(g_usAdjustValue == 1)
                    {
                        break;
                    }
#endif
#if(_D2_HDMI_MULTI_EDID_SUPPORT == _OFF)
                    if(g_usAdjustValue == 2)
                    {
                        break;
                    }
#endif
#if(_D3_HDMI_MULTI_EDID_SUPPORT == _OFF)
                    if(g_usAdjustValue == 3)
                    {
                        break;
                    }
#endif
#if(_D4_HDMI_MULTI_EDID_SUPPORT == _OFF)
                    if(g_usAdjustValue == 4)
                    {
                        break;
                    }
#endif
#if(_D5_HDMI_MULTI_EDID_SUPPORT == _OFF)
                    if(g_usAdjustValue == 5)
                    {
                        break;
                    }
#endif

                    SET_OSD_STATE(_MENU_ADVANCE_DX_HDMI_VERSION_ADJUST);
                    OsdDispMainMenuItemSelection((g_usAdjustValue % 4), _OSD_PRE_SELECT);
                    g_usBackupValue = OsdFuncGetHdmiPortVersion(_D0_INPUT_PORT + g_usAdjustValue);// UserCommonNVRamGetSystemData(_EDID_D0_SELECT + );
                    OsdDispMainMenuOptionSetting(_OPTION_HDMI_VERSIONS_TYPE, _SELECT, g_usBackupValue);
                    break;

                default:
                    break;
            }

            break;

        case _RIGHT_KEY_MESSAGE:
            if(g_usAdjustValue == 3)
            {
                OsdDispMainMenuIconPage(_UP, _ICON_PAGE_EDID_PORT_1);
            }

            if(g_usAdjustValue < 5) // D0-D5
            {
                g_usAdjustValue++;
                OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
                OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
                switch(GET_PORT_TYPE(SysSourceGetInputPortType(_D0_INPUT_PORT + g_usAdjustValue)))
                {
                    case _PORT_HDMI20:
                    case _PORT_HDMI:
                    case _PORT_MHL:
#if(_D0_HDMI_MULTI_EDID_SUPPORT == _OFF)
                        if(g_usAdjustValue == 0)
                        {
                            break;
                        }
#endif
#if(_D1_HDMI_MULTI_EDID_SUPPORT == _OFF)
                        if(g_usAdjustValue == 1)
                        {
                            break;
                        }
#endif
#if(_D2_HDMI_MULTI_EDID_SUPPORT == _OFF)
                        if(g_usAdjustValue == 2)
                        {
                            break;
                        }
#endif
#if(_D3_HDMI_MULTI_EDID_SUPPORT == _OFF)
                        if(g_usAdjustValue == 3)
                        {
                            break;
                        }
#endif
#if(_D4_HDMI_MULTI_EDID_SUPPORT == _OFF)
                        if(g_usAdjustValue == 4)
                        {
                            break;
                        }
#endif
#if(_D5_HDMI_MULTI_EDID_SUPPORT == _OFF)
                        if(g_usAdjustValue == 5)
                        {
                            break;
                        }
#endif
                        OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_HDMI_VERSIONS );
                        OsdDispMainMenuOptionSetting(_OPTION_HDMI_VERSIONS_TYPE, _UNSELECT, OsdFuncGetHdmiPortVersion(_D0_INPUT_PORT + g_usAdjustValue));
                        break;
                    default:
                        break;
                }
            }

            break;

        case _LEFT_KEY_MESSAGE:
            if(g_usAdjustValue == 4)
            {
                OsdDispMainMenuIconPage(_UP, _ICON_PAGE_EDID_PORT_0);
            }
            if(g_usAdjustValue > 0) // D0-D6
            {
                g_usAdjustValue--;
                OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
                OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
                switch(GET_PORT_TYPE(SysSourceGetInputPortType(_D0_INPUT_PORT + g_usAdjustValue)))
                {
                    case _PORT_HDMI20:
                    case _PORT_HDMI:
                    case _PORT_MHL:
#if(_D0_HDMI_MULTI_EDID_SUPPORT == _OFF)
                        if(g_usAdjustValue == 0)
                        {
                            break;
                        }
#endif
#if(_D1_HDMI_MULTI_EDID_SUPPORT == _OFF)
                        if(g_usAdjustValue == 1)
                        {
                            break;
                        }
#endif
#if(_D2_HDMI_MULTI_EDID_SUPPORT == _OFF)
                        if(g_usAdjustValue == 2)
                        {
                            break;
                        }
#endif
#if(_D3_HDMI_MULTI_EDID_SUPPORT == _OFF)
                        if(g_usAdjustValue == 3)
                        {
                            break;
                        }
#endif
#if(_D4_HDMI_MULTI_EDID_SUPPORT == _OFF)
                        if(g_usAdjustValue == 4)
                        {
                            break;
                        }
#endif
#if(_D5_HDMI_MULTI_EDID_SUPPORT == _OFF)
                        if(g_usAdjustValue == 5)
                        {
                            break;
                        }
#endif
                        OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_HDMI_VERSIONS );
                        OsdDispMainMenuOptionSetting(_OPTION_HDMI_VERSIONS_TYPE, _UNSELECT, OsdFuncGetHdmiPortVersion(_D0_INPUT_PORT + g_usAdjustValue));
                        break;
                    default:
                        break;
                }
            }
            break;

        case _EXIT_KEY_MESSAGE:
            OsdDispAdvanceMenuReDraw(_HIGH);
            break;

        default:
            break;
    }
}

void MenuAdvanceDxHDMIVersionAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_HDMI_VERSION_ADJUST);
            OsdDispMainMenuItemSelection((g_usAdjustValue % 4), _OSD_SELECT);
            switch(GET_PORT_TYPE(SysSourceGetInputPortType(_D0_INPUT_PORT + g_usAdjustValue)))
            {
                case _PORT_HDMI20:
                case _PORT_HDMI:
                case _PORT_MHL:
                    OsdDispMainMenuOptionSetting(_OPTION_HDMI_VERSIONS_TYPE, _UNSELECT, g_usBackupValue);
                    if(g_usBackupValue != OsdFuncGetHdmiPortVersion(_D0_INPUT_PORT + g_usAdjustValue))
                    {
                        //UserCommonNVRamSetSystemData(_EDID_D0_SELECT + g_usAdjustValue, g_usBackupValue);
                        OsdFuncSetHdmiPortVersion(_D0_INPUT_PORT + g_usAdjustValue, g_usBackupValue);
                        SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);

                        // Add EDID DDCRAM Switch & HPD event
                        UserCommonInterfaceHDMISwitchEdid(_D0_INPUT_PORT + g_usAdjustValue, UserInterfaceGetMultiHdmiEdidIndex(_D0_INPUT_PORT + g_usAdjustValue));
                    }
                    break;
                default:
                    break;
            }

            break;

        case _RIGHT_KEY_MESSAGE:
            switch(GET_PORT_TYPE(SysSourceGetInputPortType(_D0_INPUT_PORT + g_usAdjustValue)))
            {
                case _PORT_HDMI20:
                case _PORT_HDMI:
                case _PORT_MHL:
                    if(g_usBackupValue < _EDID_INDEX_2)
                    {
                        g_usBackupValue++;
                    }
                    OsdDispMainMenuOptionSetting(_OPTION_HDMI_VERSIONS_TYPE, _SELECT, g_usBackupValue);
                    break;
                default:
                    break;
            }


            break;

        case _LEFT_KEY_MESSAGE:
            switch(GET_PORT_TYPE(SysSourceGetInputPortType(_D0_INPUT_PORT + g_usAdjustValue)))
            {
                case _PORT_HDMI20:
                case _PORT_HDMI:
                case _PORT_MHL:
                    if(g_usBackupValue > _EDID_INDEX_0)
                    {
                        g_usBackupValue--;
                    }
                    OsdDispMainMenuOptionSetting(_OPTION_HDMI_VERSIONS_TYPE, _SELECT, g_usBackupValue);
                    break;
                default:
                    break;
            }

            break;

        case _EXIT_KEY_MESSAGE:

            SET_OSD_STATE(_MENU_ADVANCE_HDMI_VERSION_ADJUST);
            OsdDispMainMenuItemSelection((g_usAdjustValue % 4), _OSD_SELECT);
            switch(GET_PORT_TYPE(SysSourceGetInputPortType(_D0_INPUT_PORT + g_usAdjustValue)))
            {
                case _PORT_HDMI20:
                case _PORT_HDMI:
                case _PORT_MHL:
                    OsdDispMainMenuOptionSetting(_OPTION_HDMI_VERSIONS_TYPE, _UNSELECT, OsdFuncGetHdmiPortVersion(_D0_INPUT_PORT + g_usAdjustValue));
                    break;
                default:
                    break;
            }
            break;

        default:
            break;
    }
}
#endif
#if(_PIXEL_SHIFT_SUPPORT == _ON)
void MenuAdvancePixelShifAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            OsdDispAdvanceMenuReDraw(_LOW);
            break;

        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:

            OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _SELECT, _ON);
            UserAdjustPixelShifting();
            OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _SELECT, _OFF);
            break;

        case _EXIT_KEY_MESSAGE:
            OsdDispAdvanceMenuReDraw(_LOW);
            break;

        default:
            break;
    }
}

#endif
#if (_SDR_TO_HDR_SUPPORT == _ON)
void MenuAdvanceSdrToHdrAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_SDR_TO_HDR())
            {
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }
            OsdDispAdvanceMenuReDraw(_LOW);

            break;

        case _RIGHT_KEY_MESSAGE:
            if(GET_OSD_SDR_TO_HDR() != _OFF)
            {
                SET_OSD_SDR_TO_HDR(_OFF);
                OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _SELECT, GET_OSD_SDR_TO_HDR());
                UserAdjustSDRToHDR(_OFF);
            }

            break;
        case _LEFT_KEY_MESSAGE:
            if(GET_OSD_SDR_TO_HDR() != _ON)
            {
                SET_OSD_SDR_TO_HDR(_ON);
                OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _SELECT, GET_OSD_SDR_TO_HDR());
                UserAdjustSDRToHDR(_ON);
            }
            break;

        case _EXIT_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_SDR_TO_HDR())
            {
                g_usAdjustValue = g_usBackupValue;
                SET_OSD_SDR_TO_HDR(g_usAdjustValue);
            }

            OsdDispAdvanceMenuReDraw(_LOW);

            break;

        default:
            break;
    }
}
#endif

#if(_MOTION_BLUR_REDUCTION_SUPPORT == _ON)
void MenuAdvanceMBRMode(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            g_usBackupValue = GET_OSD_MBR_STATUS();
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            SET_OSD_STATE(_MENU_ADVANCE_MBR_MODE_ADJUST);
            OsdDispMainMenuOptionSetting(_OPTION_MBR_MODE, _SELECT, GET_OSD_MBR_STATUS());
            break;

        case _RIGHT_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_MBR_DUTY);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispClearSelectColor(_DOWN);
            g_usAdjustValue = UserCommonAdjustRealValueToPercent(GET_OSD_MBR_DUTY(), 100, 0, 50);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _UNSELECT);
            OsdPropShowNumber(ROW(_OSD_NUMBER_1_ROW), COL(_OSD_NUMBER_1_COL), g_usAdjustValue, (_ALIGN_LEFT | _FORCE_SHOW_NUMBER_OFF | _SHOW_3), _PFONT_PAGE_ITEM_1, _OSD_NUMBER_UNSTLECT_COLOR);
            break;

        case _LEFT_KEY_MESSAGE:
            break;

        case _EXIT_KEY_MESSAGE:

            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
}


void MenuAdvanceMBRDuty(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            g_usBackupValue = GET_OSD_MBR_DUTY();
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            SET_OSD_STATE(_MENU_ADVANCE_MBR_DUTY_ADJUST);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _SELECT);
            break;

        case _RIGHT_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_MBR_POSITION);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispClearSelectColor(_DOWN);
            g_usAdjustValue = UserCommonAdjustRealValueToPercent(GET_OSD_MBR_POSITION(), 100, 0, 50);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _UNSELECT);
            OsdPropShowNumber(ROW(_OSD_NUMBER_1_ROW), COL(_OSD_NUMBER_1_COL), g_usAdjustValue, (_ALIGN_LEFT | _FORCE_SHOW_NUMBER_OFF | _SHOW_3), _PFONT_PAGE_ITEM_1, _OSD_NUMBER_UNSTLECT_COLOR);
            break;

        case _LEFT_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_MBR_MODE);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispClearSliderAndNumber();
            OsdDispMainMenuOptionSetting(_OPTION_MBR_MODE, _UNSELECT, GET_OSD_MBR_STATUS());
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_MBR_MODE);
            break;

        case _EXIT_KEY_MESSAGE:

            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
}
void MenuAdvanceMBRPosition(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            g_usBackupValue = GET_OSD_MBR_POSITION();
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            SET_OSD_STATE(_MENU_ADVANCE_MBR_POSITION_ADJUST);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _SELECT);
            break;

        case _RIGHT_KEY_MESSAGE:
            break;
        case _LEFT_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_MBR_DUTY);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispClearSelectColor(_DOWN);
            g_usAdjustValue = UserCommonAdjustRealValueToPercent(GET_OSD_MBR_DUTY(), 100, 0, 50);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _UNSELECT);
            OsdPropShowNumber(ROW(_OSD_NUMBER_1_ROW), COL(_OSD_NUMBER_1_COL), g_usAdjustValue, (_ALIGN_LEFT | _FORCE_SHOW_NUMBER_OFF | _SHOW_3), _PFONT_PAGE_ITEM_1, _OSD_NUMBER_UNSTLECT_COLOR);
            break;

        case _EXIT_KEY_MESSAGE:
            OsdDispAdvanceMenuReDraw(_HIGH);
            break;

        default:
            break;
    }
}
void MenuAdvanceMBRModeAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_MBR_STATUS())
            {
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }
            SET_OSD_STATE(_MENU_ADVANCE_MBR_MODE);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_MBR_MODE, _UNSELECT, GET_OSD_MBR_STATUS());

            break;

        case _RIGHT_KEY_MESSAGE:
            if(GET_OSD_MBR_STATUS() == _OSD_MBR_USER_DISABLE)
            {
                SET_OSD_MBR_STATUS(_OSD_MBR_USER_ENABLE);
                OsdDispMainMenuOptionSetting(_OPTION_MBR_MODE, _SELECT, GET_OSD_MBR_STATUS());
                //switch
            }
#if((_DRR_MOTION_BLUR_REDUCTION_SUPPORT == _ON) ||(_RTK_ADVANCED_MOTION_BLUR_REDUCTION_SUPPORT == _ON))
            else if(GET_OSD_MBR_STATUS() == _OSD_MBR_USER_ENABLE)
            {
                SET_OSD_MBR_STATUS(_OSD_RTK_ADV_MBR_USER_ENABLE);
                OsdDispMainMenuOptionSetting(_OPTION_MBR_MODE, _SELECT, GET_OSD_MBR_STATUS());
                //switch
            }
#endif
            else
            {
                SET_OSD_MBR_STATUS(_OSD_MBR_USER_DISABLE);
                OsdDispMainMenuOptionSetting(_OPTION_MBR_MODE, _SELECT, GET_OSD_MBR_STATUS());
                //switch

            }
            // Reset to display setting to re-set backlight parameters
            // Caustion!! RTK_Adv_MBR requires "reset to display setting to be effective
#if(_MOTION_BLUR_REDUCTION_MODE_SWITCH_NO_MUTE_SUPPORT == _ON)
            UserCommonInterfaceMbrStrobeBacklightCtrl(_LIGHT_CONTROL_ON);
#else
            SysModeSetResetTarget(_MODE_ACTION_RESET_TO_DISPLAY_SETTING);
#endif
            break;
        case _LEFT_KEY_MESSAGE:
            if(GET_OSD_MBR_STATUS() == _OSD_MBR_USER_ENABLE)
            {
                SET_OSD_MBR_STATUS(_OSD_MBR_USER_DISABLE);
                OsdDispMainMenuOptionSetting(_OPTION_MBR_MODE, _SELECT, GET_OSD_MBR_STATUS());
                //switch
            }
#if(_RTK_ADVANCED_MOTION_BLUR_REDUCTION_SUPPORT == _ON)
            else if(GET_OSD_MBR_STATUS() == _OSD_MBR_USER_DISABLE)
            {
                SET_OSD_MBR_STATUS(_OSD_RTK_ADV_MBR_USER_ENABLE);
                OsdDispMainMenuOptionSetting(_OPTION_MBR_MODE, _SELECT, GET_OSD_MBR_STATUS());
                //switch
            }
#endif
            else
            {
                SET_OSD_MBR_STATUS(_OSD_MBR_USER_ENABLE);
                OsdDispMainMenuOptionSetting(_OPTION_MBR_MODE, _SELECT, GET_OSD_MBR_STATUS());
                //switch

            }

            // Reset to display setting to re-set backlight parameters
            // Caustion!! RTK_Adv_MBR requires "reset to display setting to be effective
#if(_MOTION_BLUR_REDUCTION_MODE_SWITCH_NO_MUTE_SUPPORT == _ON)
            UserCommonInterfaceMbrStrobeBacklightCtrl(_LIGHT_CONTROL_ON);
#else
            SysModeSetResetTarget(_MODE_ACTION_RESET_TO_DISPLAY_SETTING);
#endif

            break;

        case _EXIT_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_MBR_STATUS())
            {
                g_usAdjustValue = g_usBackupValue;
                SET_OSD_MBR_STATUS(g_usAdjustValue);
                //switch

                // Reset to display setting to re-set backlight parameters
                // Caustion!! RTK_Adv_MBR requires "reset to display setting to be effective
#if(_MOTION_BLUR_REDUCTION_MODE_SWITCH_NO_MUTE_SUPPORT == _ON)
                UserCommonInterfaceMbrStrobeBacklightCtrl(_LIGHT_CONTROL_ON);
#else
                SysModeSetResetTarget(_MODE_ACTION_RESET_TO_DISPLAY_SETTING);
#endif
            }
            SET_OSD_STATE(_MENU_ADVANCE_MBR_MODE);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_MBR_MODE, _UNSELECT, GET_OSD_MBR_STATUS());

            break;

        default:
            break;
    }
}
void MenuAdvanceMBRDutyAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_MBR_DUTY())
            {
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }
            SET_OSD_STATE(_MENU_ADVANCE_MBR_DUTY);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            g_usAdjustValue = UserCommonAdjustRealValueToPercent(GET_OSD_MBR_DUTY(), _OSD_MBR_DUTY_MAX, _OSD_MBR_DUTY_MIN, _OSD_MBR_DUTY_CENTER);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _UNSELECT);
            OsdPropShowNumber(ROW(_OSD_NUMBER_1_ROW), COL(_OSD_NUMBER_1_COL), g_usAdjustValue, (_ALIGN_LEFT | _FORCE_SHOW_NUMBER_OFF | _SHOW_3), _PFONT_PAGE_ITEM_1, _OSD_NUMBER_UNSTLECT_COLOR);

            break;

        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:
            OsdDispSliderAndNumber(_MENU_ADVANCE_MBR_DUTY_ADJUST, GET_OSD_MBR_DUTY());
            //insert Function call
            if(GET_OSD_MBR_STATUS() == _OSD_MBR_USER_ENABLE)
            {
                UserInterfaceMbrBacklightAdjust(_BACKLIGHT_MODE_STROBE_USER_CUSTOMIZE_MBR, _LIGHT_CONTROL_ON, GET_MBR_DVTOTAL());
            }
            else if(GET_OSD_MBR_STATUS() == _OSD_RTK_ADV_MBR_USER_ENABLE)
            {
#if((_DRR_MOTION_BLUR_REDUCTION_SUPPORT == _ON) || (_RTK_ADVANCED_MOTION_BLUR_REDUCTION_SUPPORT == _ON))
                UserCommonInterfaceMbrAdvAdjust(GET_OSD_MBR_DUTY(), GET_OSD_MBR_POSITION(), _LIGHT_CONTROL_ON);
#endif
            }
            break;

        case _EXIT_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_MBR_DUTY())
            {
                g_usAdjustValue = g_usBackupValue;
                SET_OSD_MBR_DUTY(g_usAdjustValue);
                //insert Function call
                if(GET_OSD_MBR_STATUS() == _OSD_MBR_USER_ENABLE)
                {
                    UserInterfaceMbrBacklightAdjust(_BACKLIGHT_MODE_STROBE_USER_CUSTOMIZE_MBR, _LIGHT_CONTROL_ON, GET_MBR_DVTOTAL());
                }
                else if(GET_OSD_MBR_STATUS() == _OSD_RTK_ADV_MBR_USER_ENABLE)
                {
#if((_DRR_MOTION_BLUR_REDUCTION_SUPPORT == _ON) || (_RTK_ADVANCED_MOTION_BLUR_REDUCTION_SUPPORT == _ON))
                    UserCommonInterfaceMbrAdvAdjust(GET_OSD_MBR_DUTY(), GET_OSD_MBR_POSITION(), _LIGHT_CONTROL_ON);
#endif
                }
            }
            SET_OSD_STATE(_MENU_ADVANCE_MBR_DUTY);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            g_usAdjustValue = UserCommonAdjustRealValueToPercent(GET_OSD_MBR_DUTY(), _OSD_MBR_DUTY_MAX, _OSD_MBR_DUTY_MIN, _OSD_MBR_DUTY_CENTER);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _UNSELECT);
            OsdPropShowNumber(ROW(_OSD_NUMBER_1_ROW), COL(_OSD_NUMBER_1_COL), g_usAdjustValue, (_ALIGN_LEFT | _FORCE_SHOW_NUMBER_OFF | _SHOW_3), _PFONT_PAGE_ITEM_1, _OSD_NUMBER_UNSTLECT_COLOR);
            break;

        default:
            break;
    }
}
void MenuAdvanceMBRPositionAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_MBR_POSITION())
            {
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }
            SET_OSD_STATE(_MENU_ADVANCE_MBR_POSITION);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            g_usAdjustValue = UserCommonAdjustRealValueToPercent(GET_OSD_MBR_POSITION(), _OSD_MBR_POS_MAX, _OSD_MBR_POS_MIN, _OSD_MBR_POS_CENTER);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _UNSELECT);
            OsdPropShowNumber(ROW(_OSD_NUMBER_1_ROW), COL(_OSD_NUMBER_1_COL), g_usAdjustValue, (_ALIGN_LEFT | _FORCE_SHOW_NUMBER_OFF | _SHOW_3), _PFONT_PAGE_ITEM_1, _OSD_NUMBER_UNSTLECT_COLOR);

            break;

        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:
            OsdDispSliderAndNumber(_MENU_ADVANCE_MBR_POSITION_ADJUST, GET_OSD_MBR_POSITION());
            //insert Function call
            if(GET_OSD_MBR_STATUS() == _OSD_MBR_USER_ENABLE)
            {
                UserInterfaceMbrBacklightAdjust(_BACKLIGHT_MODE_STROBE_USER_CUSTOMIZE_MBR, _LIGHT_CONTROL_ON, GET_MBR_DVTOTAL());
            }
            else if(GET_OSD_MBR_STATUS() == _OSD_RTK_ADV_MBR_USER_ENABLE)
            {
#if((_DRR_MOTION_BLUR_REDUCTION_SUPPORT == _ON) || (_RTK_ADVANCED_MOTION_BLUR_REDUCTION_SUPPORT == _ON))
                UserCommonInterfaceMbrAdvAdjust(GET_OSD_MBR_DUTY(), GET_OSD_MBR_POSITION(), _LIGHT_CONTROL_ON);
#endif
            }
            break;

        case _EXIT_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_MBR_POSITION())
            {
                g_usAdjustValue = g_usBackupValue;
                SET_OSD_MBR_POSITION(g_usAdjustValue);
                //insert Function call
                if(GET_OSD_MBR_STATUS() == _OSD_MBR_USER_ENABLE)
                {
                    UserInterfaceMbrBacklightAdjust(_BACKLIGHT_MODE_STROBE_USER_CUSTOMIZE_MBR, _LIGHT_CONTROL_ON, GET_MBR_DVTOTAL());
                }
                else if(GET_OSD_MBR_STATUS() == _OSD_RTK_ADV_MBR_USER_ENABLE)
                {
#if((_DRR_MOTION_BLUR_REDUCTION_SUPPORT == _ON) || (_RTK_ADVANCED_MOTION_BLUR_REDUCTION_SUPPORT == _ON))
                    UserCommonInterfaceMbrAdvAdjust(GET_OSD_MBR_DUTY(), GET_OSD_MBR_POSITION(), _LIGHT_CONTROL_ON);
#endif
                }
            }
            SET_OSD_STATE(_MENU_ADVANCE_MBR_POSITION);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            g_usAdjustValue = UserCommonAdjustRealValueToPercent(GET_OSD_MBR_POSITION(), _OSD_MBR_POS_MAX, _OSD_MBR_POS_MIN, _OSD_MBR_POS_CENTER);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _UNSELECT);
            OsdPropShowNumber(ROW(_OSD_NUMBER_1_ROW), COL(_OSD_NUMBER_1_COL), g_usAdjustValue, (_ALIGN_LEFT | _FORCE_SHOW_NUMBER_OFF | _SHOW_3), _PFONT_PAGE_ITEM_1, _OSD_NUMBER_UNSTLECT_COLOR);
            break;

        default:
            break;
    }
}

#endif




#if(_INTERNAL_AUDIO_TEST_SUPPORT == _ON)
#endif




























































#if(_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
void MenuAdvanceD0TypeCModeAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:

#if(_D0_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            if(g_usBackupValue != GET_OSD_D0_TYPE_C_U3_MODE())
            {
                if(g_usBackupValue == _TYPE_C_U3_ON)
                {
                    SET_OSD_D0_TYPE_C_U3_MODE(_TYPE_C_U3_ON);
                }
                else if(g_usBackupValue == _TYPE_C_U3_OFF)
                {
                    SET_OSD_D0_TYPE_C_U3_MODE(_TYPE_C_U3_OFF);
                }

                UserCommonInterfaceTypeCU3ModeSwitch(_D0_INPUT_PORT);
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }
            SET_OSD_STATE(_MENU_ADVANCE_TYPE_C_MODE_D0);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, g_usBackupValue);
#endif

            break;

        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:

            if(g_usBackupValue == _TYPE_C_U3_ON)
            {
                g_usBackupValue = _TYPE_C_U3_OFF;
            }
            else
            {
                g_usBackupValue = _TYPE_C_U3_ON;
            }

            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _SELECT, g_usBackupValue);
            break;

        case _EXIT_KEY_MESSAGE:

            SET_OSD_STATE(_MENU_ADVANCE_TYPE_C_MODE_D0);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);

#if(_D0_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, GET_OSD_D0_TYPE_C_U3_MODE());
#endif
            break;

        default:
            break;
    }
}

void MenuAdvanceD1TypeCModeAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:

#if(_D1_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            if(g_usBackupValue != GET_OSD_D1_TYPE_C_U3_MODE())
            {
                if(g_usBackupValue == _TYPE_C_U3_ON)
                {
                    SET_OSD_D1_TYPE_C_U3_MODE(_TYPE_C_U3_ON);
                }
                else
                {
                    SET_OSD_D1_TYPE_C_U3_MODE(_TYPE_C_U3_OFF);
                }


                UserCommonInterfaceTypeCU3ModeSwitch(_D1_INPUT_PORT);
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }

            SET_OSD_STATE(_MENU_ADVANCE_TYPE_C_MODE_D1);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, g_usBackupValue);
#endif

            break;

        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:
            if(g_usBackupValue == _TYPE_C_U3_ON)
            {
                g_usBackupValue = _TYPE_C_U3_OFF;
            }
            else
            {
                g_usBackupValue = _TYPE_C_U3_ON;
            }

            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _SELECT, g_usBackupValue);
            break;

        case _EXIT_KEY_MESSAGE:

            SET_OSD_STATE(_MENU_ADVANCE_TYPE_C_MODE_D1);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);

#if(_D1_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, GET_OSD_D1_TYPE_C_U3_MODE());
#endif

            break;

        default:
            break;
    }
}

void MenuAdvanceD2TypeCModeAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:

            break;


        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:
            if(g_usBackupValue == _TYPE_C_U3_ON)
            {
                g_usBackupValue = _TYPE_C_U3_OFF;
            }
            else
            {
                g_usBackupValue = _TYPE_C_U3_ON;
            }
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _SELECT, g_usBackupValue);
            break;

        case _EXIT_KEY_MESSAGE:

            SET_OSD_STATE(_MENU_ADVANCE_TYPE_C_MODE_D2);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);

            break;

        default:
            break;
    }
}

void MenuAdvanceD6TypeCModeAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:

#if(_D6_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            if(g_usBackupValue != GET_OSD_D6_TYPE_C_U3_MODE())
            {
                if(g_usBackupValue == _TYPE_C_U3_ON)
                {
                    SET_OSD_D6_TYPE_C_U3_MODE(_TYPE_C_U3_ON);
                }
                else
                {
                    SET_OSD_D6_TYPE_C_U3_MODE(_TYPE_C_U3_OFF);
                }

                UserCommonInterfaceTypeCU3ModeSwitch(_D6_INPUT_PORT);
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }
            SET_OSD_STATE(_MENU_ADVANCE_TYPE_C_MODE_D6);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, g_usBackupValue);
#endif

            break;

        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:
            if(g_usBackupValue == _TYPE_C_U3_ON)
            {
                g_usBackupValue = _TYPE_C_U3_OFF;
            }
            else
            {
                g_usBackupValue = _TYPE_C_U3_ON;
            }
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _SELECT, g_usBackupValue);
            break;

        case _EXIT_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_TYPE_C_MODE_D6);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);

#if(_D6_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
            OsdDispMainMenuOptionSetting(_OPTION_TYPE_C_MODE_SELECT, _UNSELECT, GET_OSD_D6_TYPE_C_U3_MODE());
#endif
            break;

        default:
            break;
    }
}
#endif // End of #if(_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)

#if(_HDR10_SUPPORT == _ON)
void MenuAdvanceHdrModeAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_HDR_MODE())
            {
                if(((g_usBackupValue == _HDR10_MODE_OFF) && (GET_OSD_HDR_MODE() != _HDR10_MODE_OFF)) ||
                   ((g_usBackupValue != _HDR10_MODE_OFF) && (GET_OSD_HDR_MODE() == _HDR10_MODE_OFF)))
                {
#if(_EDID_HDR10_AUTO_SWITCH == _ON)

#if((_HDMI_MULTI_EDID_SUPPORT == _ON) && (_HDMI_HDR10_SUPPORT == _ON))
                    // Switch All HDMI Port Edid
                    UserCommonInterfaceHDMISwitchAllPortEdid();
#endif

#if((_EMBEDDED_EDID_SUPPORT == _ON) && (_DP_HDR10_SUPPORT == _ON) && (_DP_SUPPORT == _ON))
                    // Switch Dp Version to 1.3, if HDR On
                    UserAdjustHdrCheckDpVersion(GET_OSD_HDR_MODE());

                    // Switch All DP Port Edid
                    UserCommonInterfaceDPSwitchAllPortEdid();
#endif

#if(_HDR10_SUPPORT == _ON)
                    UserCommonHDR10SupportSwitch();
#endif

#endif
                }
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }

            SET_OSD_STATE(_MENU_ADVANCE_HDR_MODE);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_HDR_MODE_SELECT, _UNSELECT, GET_OSD_HDR_MODE());
            OsdDispMainMenuIconPage(_UP, _ICON_PAGE_HDR_ADJUST);

            break;

        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:
            if(((GET_OSD_HDR_MODE() == _HDR10_MODE_FORCE_2084) && (GET_KEYMESSAGE() == _RIGHT_KEY_MESSAGE)) ||
               ((GET_OSD_HDR_MODE() == _HDR10_MODE_OFF) && (GET_KEYMESSAGE() == _LEFT_KEY_MESSAGE)))
            {
            }
            else
            {
                OsdDispSliderAndNumber(_MENU_ADVANCE_HDR_MODE_ADJUST, GET_OSD_HDR_MODE());

                UserCommonHDRAdjust(_HDR_FLOW_OSD_MODE_CHANGE);
            }

            break;

        case _EXIT_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_HDR_MODE())
            {
                g_usAdjustValue = g_usBackupValue;
                SET_OSD_HDR_MODE(g_usAdjustValue);

                UserCommonHDRAdjust(_HDR_FLOW_OSD_MODE_CHANGE);
            }
            SET_OSD_STATE(_MENU_ADVANCE_HDR_MODE);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_HDR_MODE_SELECT, _UNSELECT, GET_OSD_HDR_MODE());

            break;

        default:
            break;
    }
}


void MenuAdvanceHdrDarkEnhanceOnOffAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_DARK_ENHANCE_STATUS())
            {
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }
            SET_OSD_STATE(_MENU_ADVANCE_HDR_DARK_ENHANCE_ONOFF);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _UNSELECT, GET_OSD_DARK_ENHANCE_STATUS());

            break;

        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:
            if(GET_KEYMESSAGE() == _RIGHT_KEY_MESSAGE)
            {
                if(GET_OSD_DARK_ENHANCE_STATUS() != _OFF)
                {
                    SET_OSD_DARK_ENHANCE_STATUS(_OFF);
                    OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _SELECT, GET_OSD_DARK_ENHANCE_STATUS());
                }
            }
            else
            {
                if(GET_OSD_DARK_ENHANCE_STATUS() != _ON)
                {
                    SET_OSD_DARK_ENHANCE_STATUS(_ON);
                    OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _SELECT, GET_OSD_DARK_ENHANCE_STATUS());
                }
            }

            UserCommonHDRAdjust(_HDR_FLOW_OSD_DARK_ENHANCE);

            break;

        case _EXIT_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_DARK_ENHANCE_STATUS())
            {
                g_usAdjustValue = g_usBackupValue;
                SET_OSD_DARK_ENHANCE_STATUS(g_usAdjustValue);

                UserCommonHDRAdjust(_HDR_FLOW_OSD_DARK_ENHANCE);
            }
            SET_OSD_STATE(_MENU_ADVANCE_HDR_DARK_ENHANCE_ONOFF);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _UNSELECT, GET_OSD_DARK_ENHANCE_STATUS());

            break;

        default:
            break;
    }
}
void MenuAdvanceHdrSharpnessOnOffAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_HDR_SHARPNESS())
            {
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }
            SET_OSD_STATE(_MENU_ADVANCE_HDR_SHARPNESS_ONOFF);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _UNSELECT, GET_OSD_HDR_SHARPNESS());

            break;

        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:
            if(GET_KEYMESSAGE() == _RIGHT_KEY_MESSAGE)
            {
                if(GET_OSD_HDR_SHARPNESS() != _OFF)
                {
                    SET_OSD_HDR_SHARPNESS(_OFF);
                    OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _SELECT, GET_OSD_HDR_SHARPNESS());
                }
            }
            else
            {
                if(GET_OSD_HDR_SHARPNESS() != _ON)
                {
                    SET_OSD_HDR_SHARPNESS(_ON);
                    OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _SELECT, GET_OSD_HDR_SHARPNESS());
                }
            }

#if(_ULTRA_VIVID_SUPPORT == _ON)
            UserCommonAdjustUltraVivid(_FUNCTION_ON, UserCommonInterfaceGetColorFormat(), _DB_APPLY_NO_POLLING);
#endif
            break;

        case _EXIT_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_HDR_SHARPNESS())
            {
                g_usAdjustValue = g_usBackupValue;
                SET_OSD_HDR_SHARPNESS(g_usAdjustValue);

#if(_ULTRA_VIVID_SUPPORT == _ON)
                UserCommonAdjustUltraVivid(_FUNCTION_ON, UserCommonInterfaceGetColorFormat(), _DB_APPLY_NO_POLLING);
#endif
            }
            SET_OSD_STATE(_MENU_ADVANCE_HDR_SHARPNESS_ONOFF);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_ON_OFF, _UNSELECT, GET_OSD_HDR_SHARPNESS());

            break;

        default:
            break;
    }
}

void MenuAdvanceHdrContrastAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_HDR_CONTRAST())
            {
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }

            SET_OSD_STATE(_MENU_ADVANCE_HDR_CONTRAST);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _UNSELECT);
            break;

        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:
            OsdDispSliderAndNumber(_MENU_ADVANCE_HDR_CONTRAST_ADJUST, GET_OSD_HDR_CONTRAST());

#if((_CONTRAST_SUPPORT == _ON) && (_HDR10_SUPPORT == _ON))
            UserCommonHDRAdjustHDR10Contrast(GET_OSD_HDR_CONTRAST());
#endif
            break;

        case _EXIT_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_HDR_CONTRAST())
            {
                g_usAdjustValue = g_usBackupValue;
                SET_OSD_HDR_CONTRAST(g_usAdjustValue);

#if((_CONTRAST_SUPPORT == _ON) && (_HDR10_SUPPORT == _ON))
                UserCommonHDRAdjustHDR10Contrast(GET_OSD_HDR_CONTRAST());
#endif
            }
            SET_OSD_STATE(_MENU_ADVANCE_HDR_CONTRAST);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _UNSELECT);
            OsdPropShowNumber(ROW(_OSD_NUMBER_1_ROW), COL(_OSD_NUMBER_1_COL), g_usAdjustValue, (_ALIGN_LEFT | _FORCE_SHOW_NUMBER_OFF | _SHOW_3), _PFONT_PAGE_ITEM_1, _OSD_NUMBER_UNSTLECT_COLOR);

            break;

        default:
            break;
    }
}
void MenuAdvanceHdrColorEnhanceAdjust(void)
{
#if(_HDR10_COLOR_ENHANCE_SUPPORT == _ON)
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_HDR_COLOR_ENHANCE())
            {
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }

            SET_OSD_STATE(_MENU_ADVANCE_HDR_COLOR_ENHANCE);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), ((WORD)GET_OSD_HDR_COLOR_ENHANCE()*100/_LEVEL_H), _SLIDER_0, _UNSELECT);

            break;

        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:
            OsdDispSliderAndNumber(_MENU_ADVANCE_HDR_COLOR_ENHANCE_ADJUST, GET_OSD_HDR_COLOR_ENHANCE());

#if(_HDR10_COLOR_ENHANCE_SUPPORT == _ON)
            UserCommonHDRAdjustHDR10ColorEffect();
#endif

            break;

        case _EXIT_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_HDR_COLOR_ENHANCE())
            {
                g_usAdjustValue = g_usBackupValue;
                SET_OSD_HDR_COLOR_ENHANCE(g_usAdjustValue);
            }

#if(_HDR10_COLOR_ENHANCE_SUPPORT == _ON)
            UserCommonHDRAdjustHDR10ColorEffect();
#endif
            SET_OSD_STATE(_MENU_ADVANCE_HDR_COLOR_ENHANCE);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), ((WORD)GET_OSD_HDR_COLOR_ENHANCE()*100/_LEVEL_H), _SLIDER_0, _UNSELECT);
            OsdPropShowNumber(ROW(_OSD_NUMBER_1_ROW), COL(_OSD_NUMBER_1_COL), GET_OSD_HDR_COLOR_ENHANCE(), (_ALIGN_LEFT | _FORCE_SHOW_NUMBER_OFF | _SHOW_3), _PFONT_PAGE_ITEM_1, _OSD_NUMBER_UNSTLECT_COLOR);
            break;

        default:
            break;
    }
#endif
}
void MenuAdvanceHdrLightEnhanceAdjust(void)
{
#if(_HDR10_LIGHT_ENHANCE_SUPPORT == _ON)
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_HDR_LIGHT_ENHANCE())
            {
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }

            SET_OSD_STATE(_MENU_ADVANCE_HDR_LIGHT_ENHANCE);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), ((WORD)GET_OSD_HDR_LIGHT_ENHANCE()*100/_LEVEL_H), _SLIDER_0, _UNSELECT);

            break;

        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:
            OsdDispSliderAndNumber(_MENU_ADVANCE_HDR_LIGHT_ENHANCE_ADJUST, GET_OSD_HDR_LIGHT_ENHANCE());

#if(_HDR10_LIGHT_ENHANCE_SUPPORT == _ON)
            UserCommonHDRAdjustHDR10ColorEffect();
#endif
            break;

        case _EXIT_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_HDR_LIGHT_ENHANCE())
            {
                g_usAdjustValue = g_usBackupValue;
                SET_OSD_HDR_LIGHT_ENHANCE(g_usAdjustValue);
            }

#if(_HDR10_LIGHT_ENHANCE_SUPPORT == _ON)
            UserCommonHDRAdjustHDR10ColorEffect();
#endif
            SET_OSD_STATE(_MENU_ADVANCE_HDR_LIGHT_ENHANCE);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), ((WORD)GET_OSD_HDR_LIGHT_ENHANCE()*100/_LEVEL_H), _SLIDER_0, _UNSELECT);
            OsdPropShowNumber(ROW(_OSD_NUMBER_1_ROW), COL(_OSD_NUMBER_1_COL), GET_OSD_HDR_LIGHT_ENHANCE(), (_ALIGN_LEFT | _FORCE_SHOW_NUMBER_OFF | _SHOW_3), _PFONT_PAGE_ITEM_1, _OSD_NUMBER_UNSTLECT_COLOR);
            break;

        default:
            break;
    }
#endif
}


#endif

#if(_OSD_LOCAL_DIMMING_SUPPORT == _ON)
void MenuAdvanceHdrLDOnOff(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            g_usBackupValue = GET_OSD_LOCAL_DIMMING();
            SET_OSD_STATE(_MENU_ADVANCE_HDR_LD_ONOFF_ADJUST);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_OVERDRIVE_ONOFF, _SELECT, GET_OSD_LOCAL_DIMMING());
            break;

        case _RIGHT_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_HDR_LD_SMOOTH_ADJ);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_CLEAR);
            OsdDispClearSelectColor(_DOWN);
            g_usAdjustValue = UserCommonAdjustRealValueToPercent(GET_OSD_LD_ADJ(), 100, 0, 50);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _UNSELECT);
            OsdPropShowNumber(ROW(_OSD_NUMBER_1_ROW), COL(_OSD_NUMBER_1_COL), g_usAdjustValue, (_ALIGN_LEFT | _FORCE_SHOW_NUMBER_OFF | _SHOW_3), _PFONT_PAGE_ITEM_1, _OSD_NUMBER_UNSTLECT_COLOR);
            break;

        case _LEFT_KEY_MESSAGE:
            break;

        case _EXIT_KEY_MESSAGE:
            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
}


void MenuAdvanceHdrLDSmoothAdj(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            g_usBackupValue = GET_OSD_OD_GAIN();
            SET_OSD_STATE(_MENU_ADVANCE_HDR_LD_SMOOTH_ADJ_ADJUST);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _INSUBSET);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _SELECT);
            break;

        case _RIGHT_KEY_MESSAGE:

            break;

        case _LEFT_KEY_MESSAGE:
            SET_OSD_STATE(_MENU_ADVANCE_HDR_LD_ONOFF);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispClearSliderAndNumber();
            OsdDispMainMenuOptionSetting(_OPTION_OVERDRIVE_ONOFF, _UNSELECT, GET_OSD_LOCAL_DIMMING());
            OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_ON_OFF);
            break;

        case _EXIT_KEY_MESSAGE:

            OsdDispAdvanceMenuReDraw(_HIGH);

            break;

        default:
            break;
    }
}

void MenuAdvanceHdrLDOnOffAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_LOCAL_DIMMING())
            {
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }
            SET_OSD_STATE(_MENU_ADVANCE_HDR_LD_ONOFF);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_OVERDRIVE_ONOFF, _UNSELECT, GET_OSD_LOCAL_DIMMING());
            break;

        case _RIGHT_KEY_MESSAGE:
            if(GET_OSD_LOCAL_DIMMING() != _OFF)
            {
                SET_OSD_LOCAL_DIMMING(_OFF);
                OsdDispMainMenuOptionSetting(_OPTION_OVERDRIVE_ONOFF, _SELECT, GET_OSD_LOCAL_DIMMING());
#if(_LOCAL_DIMMING_SUPPORT == _ON)
                UserCommonLocalDimmingEnable(_DISABLE);
                UserAdjustBacklight(GET_OSD_BACKLIGHT());
#endif
            }

            break;
        case _LEFT_KEY_MESSAGE:
            if(GET_OSD_LOCAL_DIMMING() != _ON)
            {
                SET_OSD_LOCAL_DIMMING(_ON);
                OsdDispMainMenuOptionSetting(_OPTION_OVERDRIVE_ONOFF, _SELECT, GET_OSD_LOCAL_DIMMING());
#if(_LOCAL_DIMMING_SUPPORT == _ON)
                UserCommonLocalDimmingEnable(_ENABLE);
#endif
            }

            break;

        case _EXIT_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_LOCAL_DIMMING())
            {
                g_usAdjustValue = g_usBackupValue;
                SET_OSD_LOCAL_DIMMING(g_usAdjustValue);
            }
            SET_OSD_STATE(_MENU_ADVANCE_HDR_LD_ONOFF);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            OsdDispMainMenuOptionSetting(_OPTION_OVERDRIVE_ONOFF, _UNSELECT, GET_OSD_LOCAL_DIMMING());

            break;

        default:
            break;
    }
}


void MenuAdvanceHdrLDSmoothAdjAdjust(void)
{
    switch(GET_KEYMESSAGE())
    {
        case _MENU_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_LD_ADJ())
            {
                SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
            }
            SET_OSD_STATE(_MENU_ADVANCE_HDR_LD_SMOOTH_ADJ);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            g_usAdjustValue = UserCommonAdjustRealValueToPercent(GET_OSD_LD_ADJ(), 100, 0, 50);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _UNSELECT);
            OsdPropShowNumber(ROW(_OSD_NUMBER_1_ROW), COL(_OSD_NUMBER_1_COL), g_usAdjustValue, (_ALIGN_LEFT | _FORCE_SHOW_NUMBER_OFF | _SHOW_3), _PFONT_PAGE_ITEM_1, _OSD_NUMBER_UNSTLECT_COLOR);

            break;

        case _RIGHT_KEY_MESSAGE:
        case _LEFT_KEY_MESSAGE:
            OsdDispSliderAndNumber(_MENU_ADVANCE_HDR_LD_SMOOTH_ADJ_ADJUST, GET_OSD_LD_ADJ());

            break;

        case _EXIT_KEY_MESSAGE:
            if(g_usBackupValue != GET_OSD_LD_ADJ())
            {
                g_usAdjustValue = g_usBackupValue;
                SET_OSD_LD_ADJ(g_usAdjustValue);
            }
            SET_OSD_STATE(_MENU_ADVANCE_HDR_LD_SMOOTH_ADJ);
            OsdDispMainMenuCursor(GET_OSD_STATE(), GET_OSD_STATE_PREVIOUS(), _OUTSUBSET);
            g_usAdjustValue = UserCommonAdjustRealValueToPercent(GET_OSD_LD_ADJ(), 100, 0, 50);
            OsdWindowSlider(ROW(_SLIDER_0_ROW), COL(_SLIDER_0_COL), g_usAdjustValue, _SLIDER_0, _UNSELECT);
            OsdPropShowNumber(ROW(_OSD_NUMBER_1_ROW), COL(_OSD_NUMBER_1_COL), g_usAdjustValue, (_ALIGN_LEFT | _FORCE_SHOW_NUMBER_OFF | _SHOW_3), _PFONT_PAGE_ITEM_1, _OSD_NUMBER_UNSTLECT_COLOR);
            break;

        default:
            break;
    }
}
#endif



#endif//#if(_OSD_TYPE == _REALTEK_2014_OSD)
