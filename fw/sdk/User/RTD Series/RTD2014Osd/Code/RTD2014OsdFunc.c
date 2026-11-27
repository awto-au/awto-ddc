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
// ID Code      : RTD2014OsdFunc.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __RTD_OSDFUNC__

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
WORD g_usFontSelectStart;
WORD g_usFontTableStart;
BYTE g_ucOsdWidth;
BYTE g_ucOsdHeight;
BYTE g_ucOsdWidthB;
BYTE g_ucOsdHeightB;
BYTE g_ucFontPointer0 = _OSD_PAGE_0_START;
BYTE g_ucFontPointer1 = _OSD_PAGE_1_START;
BYTE g_ucFontPointer2 = _OSD_PAGE_2_START;
//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
void OsdFuncApplyMap(BYTE ucWidth, BYTE ucHeight, BYTE ucColor, BYTE ucCellW);
void OsdFuncSetPosition(EnumOsdPositionType enumOsdPositionType, WORD usX, WORD usY);
void OsdFuncTransparency(BYTE ucTrans);
void OsdFuncBlending(BYTE ucType);



void OsdFuncCloseWindow(EnumOsdWindowsType enumWinIndex);
void OsdFuncDisableOsd(void);
void OsdFuncEnableOsd(void);
#if(_SIX_COLOR_SUPPORT == _ON)
void OsdFuncSixColorAdjust(void);
#endif
void OsdFuncSetOsdItemFlag(void);

#if(_FREEZE_SUPPORT == _ON)
bit OsdFuncCheckFreezeDisable(void);
void OsdFuncShowOSDAfterClosedFreezeMsg(void);
#endif

#if(_HDMI_MULTI_EDID_SUPPORT == _ON)
BYTE OsdFuncGetHdmiPortVersion(EnumSourceSearchPort enumSearchPort);
void OsdFuncSetHdmiPortVersion(EnumSourceSearchPort enumSearchPort,BYTE ucValue);
#endif

//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFuncApplyMap(BYTE ucWidth, BYTE ucHeight, BYTE ucColor, BYTE ucCellW)   // ucCellW: blank cells match the font loaded next
{
    BYTE ucI = 0;
    BYTE ucTmp = 17; // Row Height = 18

#if(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_SOFTWARE)
    if((GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_90) ||
       (GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_270))
    {
        ucI = ucWidth;
        ucWidth = ucHeight;
        ucHeight = ucI;
        ucTmp = 11;  // Row Height = 12
    }
#endif

    // Row Command
    for(ucI = 0; ucI < ucHeight; ucI++)
    {
        ScalerOsdCommandAllByte(ucI, 0x80, ucTmp, ucWidth);
    }

    // Row Command end
    ScalerOsdCommandByte(ucHeight, _OSD_BYTE0, 0x00);

    // Frame Control (set font start address)
    g_ucAwtoMapBHas = g_ucAwtoMapBAsk;          // awto: map B room after the row end word, asked by the console (#357)
    g_ucAwtoMapBAsk = 0;
    g_ucAwtoMapBRow = ucHeight + 1;
    g_usFontSelectStart = ucHeight + 1 + ((g_ucAwtoMapBHas != 0) ? AWTO_MAPB_WORDS : 0);
    g_usFontTableStart = g_usFontSelectStart + (WORD)(ucWidth * ucHeight);
    ScalerOsdSramBaseAddressSet(_OSD_A, 0, g_usFontSelectStart, g_usFontTableStart);

    // Character Command initial
#if(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_SOFTWARE)
    if((GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_90) ||
       (GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_270))
    {
        ucTmp = AWTO_OSD_CHAR_1BIT_W(AWTO_OSD_SDK_CELL_W_ROT90);
    }
    else
#endif
    {
        ucTmp = AWTO_OSD_CHAR_1BIT_W(ucCellW);
    }

    ScalerOsdCharCommandAllByteSeries(g_usFontSelectStart, ucTmp, 0, ucColor, (WORD)ucWidth * ucHeight);

    g_ucOsdWidth = ucWidth; // for calculation (unit: word count)
    g_ucOsdHeight = ucHeight;
    SET_OSD_MAPA_COL_MAX(WIDTH(g_ucOsdWidth));

    ScalerOsdVerticalStartSelect(_OSD_VSYNC_SELECT_DVS);
    ScalerOsdDoubleFunction(GET_OSD_DOUBLE_SIZE(), GET_OSD_DOUBLE_SIZE());
}

//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFuncSetPosition(EnumOsdPositionType enumOsdPositionType, WORD usX, WORD usY)
{
#if(_D_DOMAIN_PATH == _D_DOMAIN_4_PATH)
    WORD usShiftValue = 0;
    BYTE ucXdouble = 1;
    WORD usTemp = 0;

    if(GET_OSD_DOUBLE_SIZE() == _ON)
    {
        ucXdouble = 2;
    }

    if(ScalerOsdGetHorizontalDelayStep() == _OSD_HORIZONTAL_DELAY_STEP_4_PIXEL)
    {
        // change horizontal delay step to 1 pixel for FB shift
        ScalerOsdHorizontalDelayStep(_OSD_HORIZONTAL_DELAY_STEP_1_PIXEL);
        usX *= 4;
    }

#if(_OSD_POSITION_OFFSET_CORRECTION == _ON)
    usY = (usY >= GET_OSD_POSITION_V_OFFSET_CORRECT_COMPENSATION()) ? (usY - GET_OSD_POSITION_V_OFFSET_CORRECT_COMPENSATION()) : (usY);
#endif

    if(enumOsdPositionType == _OSD_POSITION_GLOBAL_A)
    {
        if((usX * ucXdouble) <= 100)
        {
//            ScalerOsdPosition(enumOsdPositionType, (usX * ucXdouble), usY);
            ScalerOsdPosition(enumOsdPositionType, (usX), usY);
            ScalerOsdFBShiftValue(_OSD_FRONT_BACK_SHIFT_OUTSIDE, 0);
        }
        else if((usX * ucXdouble) <= (4094 + 100))
        {
            ScalerOsdPosition(enumOsdPositionType, 100 / ucXdouble, usY);
            ScalerOsdFBShiftValue(_OSD_FRONT_BACK_SHIFT_OUTSIDE, (usX * ucXdouble) - 100);
        }
        else // > 4095+100
        {
            ScalerOsdPosition(enumOsdPositionType, ((usX * ucXdouble) - 4094) / ucXdouble, usY);
            ScalerOsdFBShiftValue(_OSD_FRONT_BACK_SHIFT_OUTSIDE, 4094);
        }

        ScalerOsdFBShiftValue(_OSD_FRONT_BACK_SHIFT_INSIDE, 0x00);
        ScalerOsdFBShiftBoundarySize(0x00, 0x00);
        ScalerOsdFBShiftEn(_ENABLE);
    }
    else if(enumOsdPositionType == _OSD_POSITION_GLOBAL_B)
    {
        usShiftValue = ScalerOsdGetFBShiftValue(_OSD_FRONT_BACK_SHIFT_OUTSIDE);

        if((GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_0) ||
           (GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_180))
        {
            usTemp = g_ucOsdWidthB * 12;
        }
        else
        {
            usTemp = g_ucOsdHeightB * 18;
        }

        // if HPOS over halt of Panel width + shift value, adjust to adaptable HPOS
        if((usX * ucXdouble) > ((_PANEL_DH_WIDTH / 2 + usShiftValue) - (usTemp * ucXdouble)))
        {
            ScalerOsdPosition(enumOsdPositionType, (((_PANEL_DH_WIDTH / 2 + usShiftValue) - (usTemp * ucXdouble)) / ucXdouble), usY);
        }
        else
        {
            ScalerOsdPosition(enumOsdPositionType, ((usX * ucXdouble) - usShiftValue) / ucXdouble, usY);
        }
    }
#else

#if(_OSD_POSITION_OFFSET_CORRECTION == _ON)
    usY = (usY >= GET_OSD_POSITION_V_OFFSET_CORRECT_COMPENSATION()) ? (usY - GET_OSD_POSITION_V_OFFSET_CORRECT_COMPENSATION()) : (usY);
#endif

    ScalerOsdPosition(enumOsdPositionType, usX, usY);
#endif

    ScalerTimerWaitForEvent(_EVENT_DVS);
}

//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFuncTransparency(BYTE ucTrans)
{
    ScalerOsdSetTransparency(ucTrans);
}

//--------------------------------------------------
// Description  :
// Input Value  : Blending type1:Only windows blending.
//                Blending type2:All blending.
//                Blending type3:Windows & Character background blending.
// Output Value : None
//--------------------------------------------------
void OsdFuncBlending(BYTE ucType)
{
    ScalerOsdVerticalStartSelect(_OSD_VSYNC_SELECT_DVS);
    ScalerOsdWindow7SpecialFunction(_OSD_WINDOW_7_FUNCTION_MASK_REGION_TRANSPARENT_ALL);
    ScalerOsdSetTransparencyType(ucType);
}

//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFuncCloseWindow(EnumOsdWindowsType enumWinIndex)
{
    ScalerOsdWindowDisable(enumWinIndex);
}

//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFuncDisableOsd(void)
{
    ScalerOsdDisableOsd();
#if(_INTERNAL_AUDIO_TEST_SUPPORT == _ON)
    if(ScalerAudioGetInternalAudioGenEnable(SysSourceGetInputPort()) == _ENABLE)
        SysAudioInternalGenTestProc(_OFF);
#endif
}

//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFuncEnableOsd(void)
{
    ScalerOsdEnableOsd();
}





#if(_SIX_COLOR_SUPPORT == _ON)
//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFuncSixColorAdjust(void)
{
    ScalerColorSixColorAdjust(GET_OSD_SIX_COLOR(), GET_OSD_SIX_COLOR_HUE(), GET_OSD_SIX_COLOR_SATURATION());
}
#endif



//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFuncSetOsdItemFlag(void)
{
    // input port
    if(SysSourceGetScanType() == _SOURCE_SWITCH_AUTO_IN_GROUP)
    {
        SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_AUTO);
    }
    else
    {
        switch(SysSourceGetInputPort())
        {
            case _A0_INPUT_PORT:
                SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_A0);
                break;

            case _D0_INPUT_PORT:
                SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_D0);
                break;

            case _D1_INPUT_PORT:
                SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_D1);
                break;

            case _D2_INPUT_PORT:
                SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_D2);
                break;

            case _D3_INPUT_PORT:
                SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_D3);
                break;

            case _D4_INPUT_PORT:
                SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_D4);
                break;

            case _D5_INPUT_PORT:
                SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_D5);
                break;

            case _D6_INPUT_PORT:
                SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_D6);
                break;

            default:
                break;
        }
    }
}

#if(_FREEZE_SUPPORT == _ON)
//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : _TRUE / _FALSE
//--------------------------------------------------
bit OsdFuncCheckFreezeDisable(void)
{
    if(((((GET_OSD_STATE() >= _MENU_DISPLAY_AUTO) &&
          (GET_OSD_STATE() <= _MENU_DISPLAY_PHASE)) ||
         (GET_OSD_STATE() == _MENU_COLOR_FORMAT) ||
         (GET_OSD_STATE() == _MENU_ADVANCE_ITEM) ||
         (GET_OSD_STATE() == _MENU_OTHER_RESET) ||
         (GET_OSD_STATE() == _MENU_DISPLAY_LATENCY)) &&
        (GET_KEYMESSAGE() == _MENU_KEY_MESSAGE)) ||
       ((GET_OSD_STATE() == _MENU_ADVANCE_ULTRA_VIVID_ADJUST) && (GET_OSD_ULTRA_VIVID_STATUS() == _ULTRA_VIVID_OFF) && (GET_KEYMESSAGE() == _RIGHT_KEY_MESSAGE)) ||
       ((GET_OSD_STATE() == _MENU_ADVANCE_ULTRA_VIVID_ADJUST) && (GET_OSD_ULTRA_VIVID_STATUS() == _ULTRA_VIVID_L) && (GET_KEYMESSAGE() == _LEFT_KEY_MESSAGE)))
    {
        OsdDispOsdMessage(_OSD_DISP_DISABLE_FREEZE_MSG);
        ScalerTimerActiveTimerEvent(SEC(1), _USER_TIMER_EVENT_OSD_DISABLE_FREEZE_MSG);
        SET_OSD_STATE(GET_OSD_STATE_PREVIOUS());
        SET_OSD_FREEZE_STATUS(_OFF);
        UserCommonAdjustDisplayFreeze(_OFF);
#if(_URGENT_EVENT_CHECK_MODE == _OFF)
        SET_FREEZE_DISABLE_MSG_STATE(_ON);
#endif
        return _TRUE;
    }
    return _FALSE;
}

//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFuncShowOSDAfterClosedFreezeMsg(void)
{
    AWTO_REALTEK_MENU_OPEN();
    // the SDK menu pages are not ours: the state is _MENU_NONE above, nothing to redraw (#255)
}
#endif

#if(_HDMI_MULTI_EDID_SUPPORT == _ON)
//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
BYTE OsdFuncGetHdmiPortVersion(EnumSourceSearchPort enumSearchPort)
{
    switch(enumSearchPort)
    {
#if(_D0_HDMI_MULTI_EDID_SUPPORT == _ON)
        case _D0_INPUT_PORT:
            return (GET_OSD_D0_HDMI_VER());
#endif

#if(_D1_HDMI_MULTI_EDID_SUPPORT == _ON)
        case _D1_INPUT_PORT:
            return (GET_OSD_D1_HDMI_VER());
#endif

#if(_D2_HDMI_MULTI_EDID_SUPPORT == _ON)
        case _D2_INPUT_PORT:
            return (GET_OSD_D2_HDMI_VER());
#endif

#if(_D3_HDMI_MULTI_EDID_SUPPORT == _ON)
        case _D3_INPUT_PORT:
            return (GET_OSD_D3_HDMI_VER());
#endif

#if(_D4_HDMI_MULTI_EDID_SUPPORT == _ON)
        case _D4_INPUT_PORT:
            return (GET_OSD_D4_HDMI_VER());
#endif

#if(_D5_HDMI_MULTI_EDID_SUPPORT == _ON)
        case _D5_INPUT_PORT:
            return (GET_OSD_D5_HDMI_VER());
#endif

        default:
            return 0;
    }
}
//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFuncSetHdmiPortVersion(EnumSourceSearchPort enumSearchPort,BYTE ucValue)
{
    ucValue = ucValue;

    switch(enumSearchPort)
    {
#if(_D0_HDMI_MULTI_EDID_SUPPORT == _ON)
        case _D0_INPUT_PORT:
            SET_OSD_D0_HDMI_VER(ucValue);
            break;
#endif

#if(_D1_HDMI_MULTI_EDID_SUPPORT == _ON)
        case _D1_INPUT_PORT:
            SET_OSD_D1_HDMI_VER(ucValue);
            break;
#endif

#if(_D2_HDMI_MULTI_EDID_SUPPORT == _ON)
        case _D2_INPUT_PORT:
            SET_OSD_D2_HDMI_VER(ucValue);
            break;
#endif

#if(_D3_HDMI_MULTI_EDID_SUPPORT == _ON)
        case _D3_INPUT_PORT:
            SET_OSD_D3_HDMI_VER(ucValue);
            break;
#endif

#if(_D4_HDMI_MULTI_EDID_SUPPORT == _ON)
        case _D4_INPUT_PORT:
            SET_OSD_D4_HDMI_VER(ucValue);
            break;
#endif

#if(_D5_HDMI_MULTI_EDID_SUPPORT == _ON)
        case _D5_INPUT_PORT:
            SET_OSD_D5_HDMI_VER(ucValue);
            break;
#endif
        default:
            break;
    }
}
#endif

#endif // End of #if(_OSD_TYPE == _REALTEK_2014_OSD)

