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
// ID Code      : RTD2014OsdDisplay.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __RTD_OSDDISPLAY__

#include "UserCommonInclude.h"

#if(_OSD_TYPE == _REALTEK_2014_OSD)

//****************************************************************************
// DEFINITIONS / MACROS
//****************************************************************************


//****************************************************************************
// STRUCT / TYPE / ENUM DEFINITTIONS
//****************************************************************************
typedef enum
{
    _VGA_A0 = 0x01,
} EnumOsdSourceTypeVga;

typedef enum
{
    _DVI = 0x02,
#if(_D0_INPUT_PORT_TYPE == _D0_DVI_PORT)
    _DVI_D0,
#endif
#if(_D1_INPUT_PORT_TYPE == _D1_DVI_PORT)
    _DVI_D1,
#endif
#if((_D2_INPUT_PORT_TYPE == _D2_DVI_PORT) || (_D2_INPUT_PORT_TYPE == _D2_DUAL_DVI_PORT))
    _DVI_D2,
#endif
#if((_D3_INPUT_PORT_TYPE == _D3_DVI_PORT) || (_D3_INPUT_PORT_TYPE == _D3_DUAL_DVI_PORT))
    _DVI_D3,
#endif
#if((_D4_INPUT_PORT_TYPE == _D4_DVI_PORT) || (_D4_INPUT_PORT_TYPE == _D4_DUAL_DVI_PORT))
    _DVI_D4,
#endif
#if(_D5_INPUT_PORT_TYPE == _D5_DVI_PORT)
    _DVI_D5,
#endif

    _HDMI = 0x10,
#if((_D0_INPUT_PORT_TYPE == _D0_HDMI_PORT) || (_D0_INPUT_PORT_TYPE == _D0_MHL_PORT))
    _HDMI_D0,
#endif
#if((_D1_INPUT_PORT_TYPE == _D1_HDMI_PORT) || (_D1_INPUT_PORT_TYPE == _D1_MHL_PORT))
    _HDMI_D1,
#endif
#if((_D2_INPUT_PORT_TYPE == _D2_HDMI_PORT) || (_D2_INPUT_PORT_TYPE == _D2_MHL_PORT))
    _HDMI_D2,
#endif
#if((_D3_INPUT_PORT_TYPE == _D3_HDMI_PORT) || (_D3_INPUT_PORT_TYPE == _D3_MHL_PORT))
    _HDMI_D3,
#endif
#if((_D4_INPUT_PORT_TYPE == _D4_HDMI_PORT) || (_D4_INPUT_PORT_TYPE == _D4_MHL_PORT))
    _HDMI_D4,
#endif
#if((_D5_INPUT_PORT_TYPE == _D5_HDMI_PORT) || (_D5_INPUT_PORT_TYPE == _D5_MHL_PORT))
    _HDMI_D5,
#endif
}EnumOsdSourceTypeTMDS;

typedef enum
{
    _DP = 0x0E,
#if(_D0_INPUT_PORT_TYPE == _D0_DP_PORT)
    _DP_D0,
#endif
#if(_D1_INPUT_PORT_TYPE == _D1_DP_PORT)
    _DP_D1,
#endif
#if(_D2_INPUT_PORT_TYPE == _D2_DP_PORT)
    _DP_D2,
#endif
#if(_D6_INPUT_PORT_TYPE == _D6_DP_PORT)
    _DP_D6,
#endif
} EnumOsdSourceTypeDP;

//****************************************************************************
// CODE TABLES
//****************************************************************************


//--------------------------------------------------
// Definitions of Advance OSD ITEM
//--------------------------------------------------

typedef enum
{
    _OSD_ADVANCE_ASPECT,
    _OSD_ADVANCE_OVERSCAN,
    _OSD_ADVANCE_OVERDRIVE,
    _OSD_ADVANCE_DDCCI,
    _OSD_ADVANCE_ULTRAVIVID,
    _OSD_ADVANCE_DCR,
    _OSD_ADVANCE_DPOPTION,
    _OSD_ADVANCE_DPMST,
    _OSD_ADVANCE_DP_RESOLUTION,
    _OSD_ADVANCE_CLONE,
    _OSD_ADVANCE_HDMI_VERSIONS,
    _OSD_ADVANCE_FREESYNC,
    _OSD_ADVANCE_TYPE_C_MODE,
    _OSD_ADVANCE_HDR,
    _OSD_ADVANCE_LOCALDIMMING,
    _OSD_ADVANCE_PIXELSHIFT,
    _OSD_ADVANCE_SDR_TO_HDR,
    _OSD_ADVANCE_MBR,
    _OSD_ADVANCE_NONE,

}EnumOsdAdvanceItem;

//following order could modify by User
BYTE __code OSD_ADVANCE_ITEM_PRI[]=
{
#if(_ASPECT_RATIO_SUPPORT == _ON)
    _OSD_ADVANCE_ASPECT,
#endif

#if(_OVERSCAN_SUPPORT == _ON)
    _OSD_ADVANCE_OVERSCAN,
#endif

#if(_OD_SUPPORT == _ON)
    _OSD_ADVANCE_OVERDRIVE,
#endif
    _OSD_ADVANCE_DDCCI,

#if(_ULTRA_VIVID_SUPPORT == _ON)
    _OSD_ADVANCE_ULTRAVIVID,
#endif

#if(_DCR_SUPPORT == _ON)
    _OSD_ADVANCE_DCR,
#endif

#if(_DP_SUPPORT == _ON)
    _OSD_ADVANCE_DPOPTION,
#if(_DP_MST_SUPPORT == _ON)
    _OSD_ADVANCE_DPMST,
#endif
    _OSD_ADVANCE_DP_RESOLUTION,
    _OSD_ADVANCE_CLONE,
#endif

#if (_HDMI_MULTI_EDID_SUPPORT == _ON)
    _OSD_ADVANCE_HDMI_VERSIONS,
#endif

#if((_FREESYNC_II_SUPPORT == _ON)||(_FREESYNC_SUPPORT == _ON))
    _OSD_ADVANCE_FREESYNC,
#endif

#if(_DP_TYPE_C_CONNECTOR_SUPPORT == _ON)
    _OSD_ADVANCE_TYPE_C_MODE,
#endif

#if(_HDR10_SUPPORT == _ON)
    _OSD_ADVANCE_HDR,
#endif

#if(_OSD_LOCAL_DIMMING_SUPPORT == _ON)
    _OSD_ADVANCE_LOCALDIMMING,
#endif

#if (_SDR_TO_HDR_SUPPORT == _ON)
    _OSD_ADVANCE_SDR_TO_HDR,
#endif

#if(_PIXEL_SHIFT_SUPPORT == _ON)
    _OSD_ADVANCE_PIXELSHIFT,
#endif

#if(_MOTION_BLUR_REDUCTION_SUPPORT == _ON)
    _OSD_ADVANCE_MBR,
#endif

    _OSD_ADVANCE_NONE,
};
#define _OSD_ADVANCE_ITEM_AMOUNT    (sizeof(OSD_ADVANCE_ITEM_PRI)-1)


//****************************************************************************
// VARIABLE DECLARATIONS
//****************************************************************************

//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************

#if(_VGA_SUPPORT == _ON)
BYTE OsdDisplayGetVGAModeString(bit bUserMode);
#endif

void OsdDispDisableOsd(void);

void OsdDispOsdMessage(EnumOSDDispMsg enumMessage);

#if(_VGA_SUPPORT == _ON)
void OsdDispAutoConfigProc(void);
void OsdDisplayAutoBalanceProc(void);
#endif


#if(_DP_SUPPORT == _ON)
#endif


#if((_OSD_ROTATE_FUNCTION == _OSD_ROTATE_SOFTWARE) || (_OSD_ROTATE_FUNCTION == _OSD_ROTATE_HARDWARE))
void OsdDispOsdRotateSwitch(void);
#endif


#if(_VGA_SUPPORT == _ON)
//--------------------------------------------------
// Description :
// Input Value :
// Output Value :
//--------------------------------------------------
BYTE OsdDisplayGetVGAModeString(bit bUserMode)
{
    if(bUserMode == _USER_MODE_TYPE)
    {
        return _STRING_VGA_USER_MODE;
    }
    else
    {
        return _STRING_VGA_PRESET_MODE;
    }
}
#endif



//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdDispDisableOsd(void)
{
    if(AwtoHoldBlocksDisable() == _TRUE)
    {
        return;
    }
#ifdef _AWTO_NEW_SETTINGS
    if(GET_OSD_STATE() == _MENU_HOTKEY_BACKLIGHT)
    {
        set_nv_commit(1);                       // #132: backlight bar closed: the value is stored at the gate ("Saving to memory")
    }
#endif
    SET_OSD_STATE(_MENU_NONE);
    AwtoMenuForget();
    SET_OSD_IN_FACTORY_MENU_STATUS(_FALSE);
    ScalerTimerWaitForEvent(_EVENT_DEN_STOP);
    OsdFuncDisableOsd();
    OsdFuncCloseWindow(_OSD_WINDOW_ALL);
    g_ucOsdWidth = 0;
    g_ucOsdHeight = 0;
    g_ucOsdWidthB = 0;
    g_ucOsdHeightB = 0;
}















// VLC
// font put 1 bit
// font put 1 bit table
// font put 2 bit
// font put 2 bit table
// font put 4 bit
// font put 4 bit color

// Prop
// font put prop string

// window
// draw window






//--------------------------------------------------
// Description  :
// Input Value  :
// Output Value :
//--------------------------------------------------

//--------------------------------------------------
// Description  :
// Input Value  :
// Output Value :
//--------------------------------------------------

//--------------------------------------------------
// Description  :
// Input Value  :
// Output Value :
//--------------------------------------------------


//--------------------------------------------------
// Description  :
// Input Value  :
// Output Value :
//--------------------------------------------------

#if(_VGA_SUPPORT == _ON)
//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdDispAutoConfigProc(void)
{
    OsdDispOsdMessage(_OSD_DISP_AUTO_CONFIG_MSG);
    UserCommonAutoConfig();
    OsdDispDisableOsd();
}
//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdDisplayAutoBalanceProc(void)
{
    OsdDispDisableOsd();
    OsdDispOsdMessage(_OSD_DISP_AUTO_COLOR_MSG);

    if(SysSourceGetSourceType() == _SOURCE_VGA)
    {
        if(GET_OSD_COLOR_FORMAT() == _COLOR_SPACE_RGB)
        {
            // Perform auto-color for RGB
            if(ScalerAutoDoWhiteBalance(_AUTO_TUNE_RGB) == _AUTO_SUCCESS)
            {
                ScalerAutoGetAutoColorResult(&g_stAdcData);
                UserCommonNVRamSaveADCSetting(_COLOR_SPACE_RGB);

#if((_YPBPR_SUPPORT == _ON) && (_YPBPR_AUTO_METHOD == _YPBPR_AUTO_BY_FORMULA))
                // Calculate YPbPr gain/offset using formula
                g_stAdcData = ScalerAutoBalanceYPbPrFromFormula(&g_stAdcData);
                UserCommonNVRamSaveADCSetting(_COLOR_SPACE_YPBPR);

                // Restore RGB gain/offset
                ScalerAutoGetAutoColorResult(&g_stAdcData);
#endif
            }
            else
            {
                UserCommonNVRamRestoreADCSetting();
            }
        }
#if((_YPBPR_SUPPORT == _ON) && (_YPBPR_AUTO_METHOD == _YPBPR_AUTO_BY_SOURCE))
        else
        {
            // Perform auto-color for YPbPr
            if(ScalerAutoDoWhiteBalance(_AUTO_TUNE_YPBPR) == _AUTO_SUCCESS)
            {
                ScalerAutoGetAutoColorResult(&g_stAdcData);
                UserCommonNVRamSaveADCSetting(_COLOR_SPACE_YPBPR);
            }
            else
            {
                UserCommonNVRamRestoreADCSetting();
            }
        }
#endif
    }

    OsdDispDisableOsd();
    // SET_KEYMESSAGE(_HOLD_KEY_MESSAGE);
}
#endif // End of #if(_VGA_SUPPORT == _ON)



#if(_DP_SUPPORT == _ON)
#endif



#if((_OSD_ROTATE_FUNCTION == _OSD_ROTATE_SOFTWARE) || (_OSD_ROTATE_FUNCTION == _OSD_ROTATE_HARDWARE))
//--------------------------------------------------
// Description  : OSD information function
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdDispOsdRotateSwitch(void)
{
    OsdFuncDisableOsd();

    OsdFuncApplyMap(WIDTH(44), HEIGHT(22), COLOR(_CP_WHITE, _CP_BG), AWTO_OSD_SDK_CELL_W);

//20140304 Abel
#if(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_HARDWARE)
    ScalerOsdMapRotation(GET_OSD_ROTATE_STATUS(), _ENABLE, HEIGHT(_OSD_MAIN_MENU_HEIGHT), _DISABLE, 0, _ENABLE);
#endif

    OsdFuncBlending(_OSD_TRANSPARENCY_ONLY_WINDOW);
    OsdFuncTransparency(GET_OSD_TRANSPARENCY_STATUS());

    // Adjust Color Palette
    OsdPaletteSelectPalette(_PALETTE_MAIN_MENU);

    // Load Font & Icon
    OsdFuncSet2BitIconOffset(_2BIT_ICON_OFFSET);

    OsdFontVLCLoadFont(_FONT1_GLOBAL);
    // OsdFontVLCLoadFont(_FONT2_ICON_MENU);

    // Background window
#if(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_SOFTWARE)
    if((GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_90) ||
       (GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_270))
    {
        OsdWindowDrawingByFont(_OSD_WINDOW_0, ROW(0), COL(0), WIDTH(g_ucOsdHeight), HEIGHT(g_ucOsdWidth / 2), _CP_BLUE);
        OsdWindowDrawingByFont(_OSD_WINDOW_1, ROW(g_ucOsdWidth / 2), COL(0), WIDTH(g_ucOsdHeight), HEIGHT(g_ucOsdWidth / 2), _CP_LIGHTBLUE);
    }
    else
#endif
    {
        OsdWindowDrawingByFont(_OSD_WINDOW_0, ROW(0), COL(0), WIDTH(g_ucOsdWidth), HEIGHT(g_ucOsdHeight / 2), _CP_BLUE);
        OsdWindowDrawingByFont(_OSD_WINDOW_1, ROW(g_ucOsdHeight / 2), COL(0), WIDTH(g_ucOsdWidth), HEIGHT(g_ucOsdHeight / 2), _CP_LIGHTBLUE);
    }


    // Realtek Mark
    OsdFontPut1BitTable(ROW(0), COL(32), tOSD_iREALTEK, COLOR(_CP_WHITE, _CP_BG));

    // Main Menu Icon & String
    OsdDispMainMenuIconPage(_UP, _ICON_PAGE_OTHER_1);
    OsdDispMainMenuIconPage(_DOWN, _ICON_PAGE_OSD_ROTATE);

    OsdDispClearSelectColor(_DOWN);
    OsdDispMainMenuItemSelection(_ITEM_2, _OSD_PRE_SELECT);
    OsdDispMainMenuItemIndication(_ITEM_6, 7, _OSD_SELECT);

    OsdDispMainMenuOptionSetting(_MENU_OTHER_ROTATE_ADJUST, _SELECT, GET_OSD_ROTATE_STATUS());

    // key info
    OsdDispMainMenuKeyInfo(_KEY_INFO_ALL, _OSD_UNSELECT);

    OsdDispSetPosition(_POS_PERCENT, _OSD_POSITION_GLOBAL_A, GET_OSD_HPOS(), GET_OSD_VPOS());

    // Osd Enable
    ScalerTimerWaitForEvent(_EVENT_DEN_STOP);
    OsdFuncEnableOsd();
}
#endif


#endif//#if(_OSD_TYPE == _REALTEK_2014_OSD)
