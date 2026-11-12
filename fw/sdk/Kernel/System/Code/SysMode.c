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
// ID Code      : SysMode.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __SYSTEM_MODE__

#include "SysInclude.h"

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
StructModeInfoType g_stModeInfo;
// ModeInfo bit[0:4] -- Mode State
// ModeInfo bit[5] -- Display Ready
// ModeInfo bit[6] -- Timing Confirm
// ModeInfo bit[7] -- ModeStateChanged

//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
BYTE SysModeGetModeState(void);
bit SysModeGetDisplaySettingReady(void);
bit SysModeGetTimingConfirm(void);
bit SysModeGetActiveReady(void);
bit SysModeDisplaySetting(void);
void SysModeSetUpDisplayInitialization(void);
void SysModeSetUpInputCapture(void);
void SysModeSetUpDisplayCapture(void);
bit SysModeSetUpMDomain(void);
void SysModeResetState(BYTE ucResetTarget);
void SysModeSetFreeRun(void);
bit SysModeGetModeStateChange(void);
void SysModeClrModeStateChange(void);
void SysModeSetResetTarget(EnumModeAction enumResetTarget);
void SysModeColorSpaceConvert(EnumColorSpace enumColorFormat, EnumDBApply enumDBApply);
void SysModeDisplayTimingInitial(void);
bit SysModeCheckToDisableGlobalDoubleBuffer(void);
void SysModeSetupIDomainIniValue(void);

#if(_FREESYNC_SUPPORT == _ON)
void SysModeDrrSetMdomainInfo(void);
WORD SysModeDrrGetIVFreq(EnumSourceSearchPort enumSearchPort);

#if(_DP_SUPPORT == _ON)
#if(_DP_FREESYNC_SUPPORT == _ON)
WORD SysModeFreeSyncDpGetDDCRamAddress(EnumSourceSearchPort enumSearchPort);
#endif
#endif
#endif


//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  : Return Mode State for other Group
// Input Value  : None
// Output Value : Mode State
//--------------------------------------------------
BYTE SysModeGetModeState(void)
{
    return GET_MODE_STATE();
}

//--------------------------------------------------
// Description  : Return Mode Display Setting Ready
// Input Value  : None
// Output Value : Mode State
//--------------------------------------------------
bit SysModeGetDisplaySettingReady(void)
{
    return GET_MODE_DISPLAY_SETTING_READY();
}

//--------------------------------------------------
// Description  : Return Mode Timing Confirm
// Input Value  : None
// Output Value : Mode State
//--------------------------------------------------
bit SysModeGetTimingConfirm(void)
{
    return GET_MODE_TIMING_CONFIRM();
}

//--------------------------------------------------
// Description  : Return Mode Active Ready
// Input Value  : None
// Output Value : Mode State
//--------------------------------------------------
bit SysModeGetActiveReady(void)
{
    return GET_MODE_ACTIVE_READY();
}

//--------------------------------------------------
// Description  : Include all required settings for Display
// Input Value  : Input Source Type
// Output Value : None
//--------------------------------------------------
bit SysModeDisplaySetting(void)
{
    bit bMdomainsetup = _FALSE;

#if(_CUSTOMER == _CUS_TOSHIBA)
#if(TOSHIBA_DC_POWER == _OFF)
    if((GET_INPUT_TIMING_HWIDTH() == 1920) && (GET_INPUT_TIMING_VHEIGHT() == 1280))
    { 
        if(UserInterfaceGetAspectRatioType() != _ASPECT_RATIO_VMAXIMAGE)
        {
#if((_ASPECT_RATIO_LIST_SELECT != _ASPECT_RATIO_LIST_TOSHIBA_1) && \
    (_ASPECT_RATIO_LIST_SELECT != _ASPECT_RATIO_LIST_TOSHIBA_2))          
            SET_OSD_ASPECT_RATIO_TYPE(_OSD_ASPECT_RATIO_4);
            RTDFlashSaveOSDData();
#endif
        }       
    }
#endif
#endif

    // Set up testing flow
    DISPLAY_SETTING_TEST_INIT();

    // Set up variables for dispaly setting
    SysModeSetUpDisplayInitialization();

    // Set Up Input Timing to I Domain
    SysModeSetUpInputCapture();

    // Set D Domain Functions
    SysModeSetUpDisplayCapture();

#if(_URGENT_EVENT_CHECK_MODE == _ON)
    if((ScalerSyncCheckUrgentEvent() == _TRUE))
    {
        return _FALSE;
    }
#endif

    // Set M Domain Functions
    bMdomainsetup = SysModeSetUpMDomain();

    // Start testing
    DISPLAY_SETTING_TEST_UPDATE();

    return bMdomainsetup;
}

//--------------------------------------------------
// Description  : Set Up variables for display setting
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysModeSetUpDisplayInitialization(void)
{
    UserInterfaceDisplayInitialization();

#if(_ULTRA_HDR_SUPPORT == _ON)
    ScalerSyncGetColorInfoFrame(SysSourceGetInputPort(), _DP_GET_RSV0_INFO_INITIAL);
#endif

    // Check Panel Backlight Action
    if(UserCommonInterfaceGetDisplaySettingBacklightAction() == _DISABLE)
    {
#if(_PANEL_POW_SEQ_FAST_MODE == _ON)
        // Turn off backlight to prevent garbage
        AWTO_BLANK(1);
#else
        // Turn off backlight to prevent garbage
        UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_PANEL_OFF, AWTO_PNL_BY_DS_BL_OFF));
#endif
    }

    SysModeSetupIDomainIniValue();

#if(_FRC_SUPPORT == _ON)
    // Set custom DVF freq.
    UserCommonInterfaceGetDVMaxMinFreq(&g_stDVCustomizedFreq);
#endif

#if(_RTK_ADVANCED_MOTION_BLUR_REDUCTION_SUPPORT == _ON)
    UserCommonInterfaceAdjustRtkAdvMbr();
#endif

    // Check Case to Disable Global Double Buffer
    if(SysModeCheckToDisableGlobalDoubleBuffer() == _TRUE)
    {
        ScalerGlobalDoubleBufferEnable(_DISABLE);
    }

#if(_DISPLAY_ROTATION_SUPPORT == _ON)
    // Set rotation
    SET_ROT_TYPE(UserInterfaceGetRotationDegree());
    SET_ROT_DISP_SIZE(UserInterfaceGetRotationDisplayType());
#endif

#if(_DISP_LATENCY_ADJUST_SUPPORT == _ON)
    // Set display latency ratio; 0 if rotation is enabled
#if(_DISPLAY_ROTATION_SUPPORT == _ON)
    if(GET_ROT_TYPE() != _ROT_DISABLE)
    {
        SET_DISP_LATENCY_RATIO(0);
    }
    else
#endif
    {
        SET_DISP_LATENCY_RATIO(UserInterfaceGetDisplayLatencyRatio());
    }
#endif

#if(_FRC_SUPPORT == _ON)
    // Disable FRC in change timing / m-domain check fail
    if(ScalerGlobalGetDBStatus() == _FALSE)
    {
        // FRC Disable M1/M2 Capture/Display
        ScalerFRCEn(_FRC_CAP_DISP_ALL, _DISABLE);

        // Set Frame sync with line buffer mode
        ScalerFRCSetDDomainSourceSelect(_DDOMAIN_SRC_FRAM_FRAME_SYNC_MODE);
    }


#if(_DISPLAY_ROTATION_SUPPORT == _ON)

#if((_MEMORY_TYPE_CONFIG == _MEMORY_DDR2) && (_MEMORY_SIZE_CONFIG == _16M_16BIT_DDR2_2PCS))
    // switch DDR2 mux
    ScalerDDR2RotationSetClientMux();
#endif

#if(_DISPLAY_ROTATION_TYPE == _DISPLAY_ROTATION_GEN_I)
    // Disable FRC
    ScalerRotationSetFRCEn(_FRC_ALL_ONOFF, _DISABLE);

    // Use information form Frame-Sync Mode
    ScalerRotationSetDDomainSourceSelect(_DDOMAIN_SRC_FRAM_FRAME_SYNC_MODE);
#endif
#endif
#endif  // End of #if(_FRC_SUPPORT == _ON)
}

//--------------------------------------------------
// Description  : Set Up stuffs into I-Domain
// Input Value  : Timing Info Into VGIP
// Output Value : None
//--------------------------------------------------
void SysModeSetUpInputCapture(void)
{
    UserCommonInterfaceAdjustInputTiming();

    ScalerIDomainVgipSetInputCapture();
}

//--------------------------------------------------
// Description  : Set Up I-Domain
// Input Value  : Timing Info Into D Domain
// Output Value : None
//--------------------------------------------------
void SysModeSetUpDisplayCapture(void)
{
    // Initialize Display Timing
    SysModeDisplayTimingInitial();

    UserCommonInterfaceAdjustDisplayTiming();

    // Check Display Timing
    ScalerMDomainCheckDisplayFormat();
}

//--------------------------------------------------
// Description  : Set Up M-Domain
// Input Value  : Timing Info Into M Domain
// Output Value : None
//--------------------------------------------------
bit SysModeSetUpMDomain(void)
{
    if(ScalerMDomainControl() == _FALSE)
    {
        return _FALSE;
    }

    return _TRUE;
}

//--------------------------------------------------
// Description  : Mode Reset
// Input Value  : Reset Target
// Output Value : None
//--------------------------------------------------
void SysModeResetState(BYTE ucResetTarget)
{
    DebugMessageSystem("SysModeResetState!!", ucResetTarget);

    switch(ucResetTarget)
    {
        case _MODE_ACTION_RESET_TO_SEARCH:

            // User Reset Process
            UserCommonInterfaceOsdResetProc();

            // Clear Source Ready Flag
            AwtoSwEvent(AWTO_SW_EV_PROBE, 4);
            SysSourceInfoReset();

            // Clear Measure Ready Flag
            CLR_MODE_TIMING_CONFIRM();

            // Clear M Domain Ready Flag
            CLR_MODE_DISPLAY_SETTING_READY();

            // Clear No Wait For Active Flag
            CLR_MODE_NO_WAIT_FOR_ACTIVE();

            // Clear Mode Active Ready Flag
            CLR_MODE_ACTIVE_READY();

            SysModeSetFreeRun();

            AwtoSwEvent(AWTO_SW_EV_PROBE, 5);
            ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_ACTIVE_STATE);
            ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_NOSIGNAL_STATE);
            ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_NOSUPPORT_STATE);

            break;

        case _MODE_ACTION_RESET_TO_DISPLAY_SETTING_WITHOUT_FORCETOBG:
        case _MODE_ACTION_RESET_TO_DISPLAY_SETTING:

            if(GET_MODE_STATE() != _MODE_STATUS_ACTIVE)
            {
                // User Reset Process
                UserCommonInterfaceOsdResetProc();
            }

            // Clear M Domain Ready Flag
            CLR_MODE_DISPLAY_SETTING_READY();

            // Set No Wait For Active Flag
            SET_MODE_NO_WAIT_FOR_ACTIVE();

            // Clear Mode Active Ready Flag
            CLR_MODE_ACTIVE_READY();

            break;

        case _MODE_ACTION_RESET_TO_NOSUPPORT:

            if(GET_MODE_STATE() == _MODE_STATUS_DISPLAY_SETTING)
            {
                // Clear M Domain Ready Flag
                CLR_MODE_DISPLAY_SETTING_READY();

                SysModeSetFreeRun();
            }

            break;

        case _MODE_ACTION_RESET_TO_POWER_SAVING:

            // User Reset Process
            UserCommonInterfaceOsdResetProc();

            // Clear Source Ready Flag
            SET_SOURCE_TYPE(g_ucSearchIndex, _SOURCE_NONE);

            // Clear Source Judge
            CLR_SOURCE_JUDGE(g_ucSearchIndex);

#if(_SOURCE_BACKGROUND_DETECT_SUPPORT == _ON)
            CLR_SOURCE_BG_JUDGE(g_ucBgDetectIndex);
#endif

            // Clear Measure Ready Flag
            CLR_MODE_TIMING_CONFIRM();

            // Clear M Domain Ready Flag
            CLR_MODE_DISPLAY_SETTING_READY();

            // Clear No Wait For Active Flag
            CLR_MODE_NO_WAIT_FOR_ACTIVE();

            // Clear Mode Active Ready Flag
            CLR_MODE_ACTIVE_READY();

            ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_ACTIVE_STATE);
            ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_NOSIGNAL_STATE);
            ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_NOSUPPORT_STATE);

            break;

        case _MODE_ACTION_RESET_TO_POWER_OFF:

            // User Reset Process
            UserCommonInterfaceOsdResetProc();

            // Clear Source Ready Flag
            SysSourceInfoReset();

            CLR_SOURCE_HP_SOURCE_JUDGE();

            // Clear Measure Ready Flag
            CLR_MODE_TIMING_CONFIRM();

            // Clear M Domain Ready Flag
            CLR_MODE_DISPLAY_SETTING_READY();

            // Clear No Wait For Active Flag
            CLR_MODE_NO_WAIT_FOR_ACTIVE();

            // Clear Mode Active Ready Flag
            CLR_MODE_ACTIVE_READY();

            // Judge Reset Process
            ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_ACTIVE_STATE);

            break;

        default:
            break;
    }

    ScalerGlobalResetProc(ucResetTarget, SysSourceGetInputPort());
}

//--------------------------------------------------
// Description  : Set Free Run Mode
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysModeSetFreeRun(void)
{
    DWORD ulDclk = GET_D_CLK_FREQ();

    // Set D Domain Timing
    SysModeDisplayTimingInitial();

    // Disable Global Double Buffer
    ScalerGlobalDoubleBufferEnable(_DISABLE);

    ScalerMDomainSetDisplayFormat(_FREE_RUN_NO_INPUT);

    // Enable Spread Spectrum
    //ScalerPLLSetDPLLSSC(_DCLK_SPREAD_SPEED, _DCLK_SPREAD_RANGE);
    ScalerPLLSetDPLLSSC(GET_DCLK_SPREAD_SPEED_VALUE(), GET_DCLK_SPREAD_RANGE_VALUE());

    if(ulDclk != GET_D_CLK_FREQ())
    {
#if(_PANEL_STYLE == _PANEL_VBO)
        // Turn off backlight to prevent garbage
        UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_PANEL_OFF, AWTO_PNL_BY_DS_DCLK));
#elif(_PANEL_STYLE == _PANEL_DPTX)
        // Turn off backlight to prevent garbage
        AWTO_BLANK(1);
#endif
    }
}

//--------------------------------------------------
// Description  : Mode State Change Flag for OSD
// Input Value  : None
// Output Value : None
//--------------------------------------------------
bit SysModeGetModeStateChange(void)
{
    return GET_MODE_STATE_CHANGE_OSD();
}

//--------------------------------------------------
// Description  : Clr Mode State Change Flag for OSD
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysModeClrModeStateChange(void)
{
    CLR_MODE_STATE_CHANGE_OSD();
}


//--------------------------------------------------
// Description  : Set Reset Status for User
// Input Value  : Target Reset State
// Output Value : None
//--------------------------------------------------
void SysModeSetResetTarget(EnumModeAction enumResetTarget)
{
    if(enumResetTarget != _MODE_ACTION_NONE)
    {
        SysMachineRequest(AWTO_SYS_REQ_MODE | enumResetTarget, AWTO_SYS_BY_SDK_OSD);    // #162 step 3: a request
    }
}

//--------------------------------------------------
// Description  : Let User Specify Which Color Space is used
// Input Value  : Target Color Space, enumDBApply
// Output Value : None
//--------------------------------------------------
void SysModeColorSpaceConvert(EnumColorSpace enumColorFormat, EnumDBApply enumDBApply)
{
    enumDBApply = enumDBApply;
    enumColorFormat = enumColorFormat;

#if(_VGA_SUPPORT == _ON)
    if(GET_SOURCE_TYPE(g_ucSearchIndex) == _SOURCE_VGA)
    {
        ScalerADCClampMode(enumColorFormat);

        // Download adc __data from NVRam
        UserCommonNVRamLoadADCSetting(enumColorFormat);

        // Gain Offset Adjust.
        UserCommonInterfaceAdjustADCData();
    }
#endif

#if((_DVI_SUPPORT == _ON) && (_UNDERSCAN_SUPPORT == _ON))
    if(GET_SOURCE_TYPE(g_ucSearchIndex) == _SOURCE_DVI)
    {
        // Adjust porch color for DVI
        ScalerTMDSSetPorchColor(SysSourceGetInputPort(), enumColorFormat);
    }
#endif

#if(_COLOR_IP_COLOR_CONVERT == _ON)
    // Wait for D-domain DB apply ready
    ScalerColorWaitDDomainDBApply();

#if(_M_DOMAIN_FORCE_YUV_FORMAT == _ON)
    ScalerColorMdomainForceYUV(enumColorFormat, enumDBApply);
#elif(_ULTRA_VIVID_SUPPORT == _ON)
    ScalerColorSpaceConvertUltraVividSupport(enumColorFormat, enumDBApply);
#else
    ScalerColorSpaceConvert(enumColorFormat, enumDBApply);
#endif
#endif // End of #if(_COLOR_IP_COLOR_CONVERT == _ON)
}

//--------------------------------------------------
// Description  : Give Display Timing Initial Value
// Input Value  : None
// Output Value : None
//--------------------------------------------------
#if(_USER_BEACON_FACTORY_OSD == _ON)
extern bit g_ucBeaconFacOsdShowFlag;//Kernel_updata_160115
#endif

void SysModeDisplayTimingInitial(void)
{
#if(_USER_BEACON_FACTORY_OSD == _ON)
#if(_CUSTOMER != _CUS_TOSHIBA)
    if(g_ucBeaconFacOsdShowFlag)
        return;
#endif
#endif

    // Set Up Display Timing According to Panel Spec
    SET_MDOMAIN_OUTPUT_HWIDTH(_PANEL_DH_WIDTH);
    SET_MDOMAIN_OUTPUT_HBWIDTH(_PANEL_DH_WIDTH);
    SET_MDOMAIN_OUTPUT_HTOTAL((_PANEL_DH_TOTAL - (_PANEL_DH_TOTAL % _DHTOTAL_MULTIPLE)));
    SET_MDOMAIN_OUTPUT_HSTART(_PANEL_DH_START);
    SET_MDOMAIN_OUTPUT_HBSTART(_PANEL_DH_START);

    SET_MDOMAIN_OUTPUT_VHEIGHT(_PANEL_DV_HEIGHT);
    SET_MDOMAIN_OUTPUT_VBHEIGHT(_PANEL_DV_HEIGHT);
    SET_MDOMAIN_OUTPUT_VTOTAL(_PANEL_DV_TOTAL);
    SET_MDOMAIN_OUTPUT_VSTART(_PANEL_DV_START);
    SET_MDOMAIN_OUTPUT_VBSTART(_PANEL_DV_START);

    SET_OUTPUT_VFREQ(_PANEL_TYP_FRAME_RATE);
}

//--------------------------------------------------
// Description  : Check To Disable Global Double Buffer
// Input Value  : None
// Output Value : _TRUE: Disale Global Global Double Buffer
//--------------------------------------------------
bit SysModeCheckToDisableGlobalDoubleBuffer(void)
{
    if(ScalerGlobalGetDBStatus() == _TRUE)
    {
#if(_DISPLAY_ROTATION_SUPPORT == _ON)
        if(GET_ROT_TYPE() != UserInterfaceGetRotationDegree())
        {
            return _TRUE;
        }
#endif
        if(GET_MEMORY_DVF_SELECT() != ScalerDisplaySelectDVFMode())
        {
            return _TRUE;
        }
    }
    return _FALSE;
}

//--------------------------------------------------
// Description  : Set I domain initial value and check
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysModeSetupIDomainIniValue(void)
{
    // Copy Input Timing to I Domain Timing as initial value
    SET_MDOMAIN_INPUT_STRUCTURE(g_stInputTimingData);

#if((_MEASURE_ADJUSTED_IHF_SUPPORT == _ON) || (_MEASURE_ADJUSTED_IVF_SUPPORT == _ON))
    ScalerMDomainUpdateInputInfo();
#endif

#if(_FORMAT_CONVERSION_SUPPORT == _ON)
    if(ScalerFmtCnvFtoPGetStatus() == _TRUE)
    {
        SET_MDOMAIN_INPUT_VSTART(GET_MDOMAIN_INPUT_VSTART() - (GET_MDOMAIN_INPUT_VSTART() % 2));
    }
#endif

#if(_FREESYNC_SUPPORT == _ON)
    SysModeDrrSetMdomainInfo();
#endif

    // Add Required Functions to Modify Input Timing
    if(GET_MDOMAIN_INPUT_VSTART() > (GET_MDOMAIN_INPUT_VTOTAL() - GET_MDOMAIN_INPUT_VHEIGHT()))
    {
        SET_MDOMAIN_INPUT_VSTART((GET_MDOMAIN_INPUT_VTOTAL() - GET_MDOMAIN_INPUT_VHEIGHT()));
    }

    if((GET_MDOMAIN_INPUT_HWIDTH() % 2) != 0x00)
    {
        // We should let H-width is even integer in case of the width of memory FIFO read width must even integer.
        SET_MDOMAIN_INPUT_HWIDTH(GET_MDOMAIN_INPUT_HWIDTH() + 1);
    }
}

#if(_FREESYNC_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Set Drr Mdomain Info
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysModeDrrSetMdomainInfo(void)
{
    EnumSourceSearchPort enumSearchPort = SysSourceGetInputPort();

#if(_FREESYNC_SUPPORT == _ON)
    ScalerFreeSyncSPDInfoReceive(enumSearchPort);
#endif

    if(GET_FREESYNC_ENABLED() == _TRUE)
    {
        WORD usIVfreq = SysModeDrrGetIVFreq(enumSearchPort);

        if(usIVfreq != 0)
        {
            SET_FREESYNC_IVF_INFO(_TRUE);
            SET_MDOMAIN_INPUT_VTOTAL((DWORD)GET_MDOMAIN_INPUT_HFREQ() * 1000 / usIVfreq);
        }
        else
        {
            SET_FREESYNC_IVF_INFO(_FALSE);
            SET_MDOMAIN_INPUT_VTOTAL((DWORD)GET_MDOMAIN_INPUT_VHEIGHT() * 105 / 100);

            usIVfreq = ((DWORD)GET_MDOMAIN_INPUT_HFREQ() * 1000 / GET_MDOMAIN_INPUT_VHEIGHT());

            if(usIVfreq > _PANEL_FREESYNC_MAX_FRAME_RATE)
            {
                usIVfreq = _PANEL_FREESYNC_MAX_FRAME_RATE;
            }
        }

        DebugMessageScaler("DRR new Vfreq max", usIVfreq);
        SET_MDOMAIN_INPUT_VFREQ(usIVfreq);
    }
}

//--------------------------------------------------
// Description  : Get DRR IVF
// Input Value  : Input port
// Output Value : IVF in DRR; 0 if not available
//--------------------------------------------------
WORD SysModeDrrGetIVFreq(EnumSourceSearchPort enumSearchPort)
{
    enumSearchPort = enumSearchPort;

    if(GET_FREESYNC_VFREQ_MAX() == 590)
    {
        SET_FREESYNC_VFREQ_MAX(600);
    }

    if(GET_FREESYNC_SPD_INFO_FRAME_RECEIVED() == _TRUE)
    {
        DebugMessageScaler("DRR Get IVF from SPD info", GET_FREESYNC_VFREQ_MAX());
        return GET_FREESYNC_VFREQ_MAX();
    }

#if(_DP_SUPPORT == _ON)
#if(_DP_FREESYNC_SUPPORT == _ON)
    if(GET_DP_FREESYNC_ENABLED() == _TRUE)
    {
        WORD usDDCRamAddress = SysModeFreeSyncDpGetDDCRamAddress(enumSearchPort);
        WORD usIVfreq = 0;

        StructDpFreeSyncSourceInfo stSourceInfo;
        memset(&stSourceInfo, 0, sizeof(stSourceInfo));

        ScalerFreeSyncDpGetSourceInfo(enumSearchPort, &stSourceInfo);

        // Get IVF from EDID info, if any
        if((usDDCRamAddress != 0) &&
           (ScalerFreeSyncDpEdidAnalysisGetVfreqMax((BYTE xdata *)usDDCRamAddress, ScalerSyncGetInputPixelClk(), &stSourceInfo, &usIVfreq) == _DP_FREESYNC_WITH_IVF_MAX))
        {
            DebugMessageScaler("DRR Get IVF from EDID analysis", usIVfreq);
            return usIVfreq;
        }

        // Get IVF from user info, if any
        if(UserCommonInterfaceDPFreeSyncGetIVFmax(&usIVfreq) == _DP_FREESYNC_WITH_IVF_MAX)
        {
            DebugMessageScaler("DRR Get IVF from user define", usIVfreq);
            return usIVfreq;
        }
    }
#endif
#endif

    DebugMessageScaler("DRR not Get IVF", 0);
    return 0;
}

#if(_DP_SUPPORT == _ON)
#if(_DP_FREESYNC_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Get EDID DDC Ram Address
// Input Value  : None
// Output Value : _TRUE: Disale Global Global Double Buffer
//--------------------------------------------------
WORD SysModeFreeSyncDpGetDDCRamAddress(EnumSourceSearchPort enumSearchPort)
{
    switch(enumSearchPort)
    {
#if(_D0_EMBEDDED_DDCRAM_MAX_SIZE != _EDID_SIZE_NONE)
#if(_D0_DDC_CHANNEL_SEL == _DDC0)
        case _D0_INPUT_PORT:

            return (WORD)&MCU_DDCRAM_D0;
#endif
#endif

#if(_D1_EMBEDDED_DDCRAM_MAX_SIZE != _EDID_SIZE_NONE)
#if(_D1_DDC_CHANNEL_SEL == _DDC1)
        case _D1_INPUT_PORT:
            return (WORD)&MCU_DDCRAM_D1;
#endif
#endif

#if(_D2_EMBEDDED_DDCRAM_MAX_SIZE != _EDID_SIZE_NONE)
#if(_D2_DDC_CHANNEL_SEL == _DDC2)
        case _D2_INPUT_PORT:
            return (WORD)&MCU_DDCRAM_D2;
#endif
#endif
        default:
            return 0;
    }

    return 0;
}
#endif
#endif
#endif


