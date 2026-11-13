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
// ID Code      : SysMain.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __MAIN__

#define _AWTO_DIAG_DEFINER
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


//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
void main(void);
void SysMainSystemInitial(void);
bit SysMainSytemPowerDetect(void);

#if(_ALS_TYPE != _SENSER_NONE)
void SysMainAlsHandler(void);
#endif

#if((_BACKLIGHT_SENSOR == _ON) || (_NEW_BACKLIGHT_SENSOR_FUN_EN == _ON))
void SysMainBackLightSensorHandler(void);
#endif

#if(_FLASH_PARTITION_TYPE != _FLASH_PARTITION_NONE)
void SysMainStartUserCode(BYTE ucBankAddress);
#endif



//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  : The main function
// Input Value  : None
// Output Value : None
//--------------------------------------------------
#include "awto_sw.inc"
#include "awto_sync.inc"
#include "awto_meas4k.inc"
#include "awto_wdt.inc"
#include "awto_audio.inc"
void main(void)
{
    AwtoStackPaint();
    AwtoWdtInit();
    do
    {
        AwtoDiagInit();
        AwtoMeasInit();
        AwtoSyncInit();
        SysMainSystemInitial();

        while(SysMainSytemPowerDetect() == _TRUE)
        {
            AwtoStackCheck();
            AWTO_LP(0);
            AWTO_SW_MARK(0);
            AwtoSwPoll();
            AwtoDiagMainPass();
            AWTO_PS_POLL_SITE();
            AwtoGpioPoll();
            AWTO_PS_POLL_SITE();
            AwtoKeyPoll();
            AWTO_PS_POLL_SITE();
            AwtoDiagTestCmd();
            AWTO_LP(1);
            AWTO_SW_MARK(1);
            AWTO_PS_POLL_SITE();
            SysMachineHandler();                    // #162 step 3: power + mode transitions (was SysPowerHandler + SysJudgeHandler)
            UserCommonInterfacePanelPowerTick();    // #162 panel machine: right after the power switch (PHY needs power NORMAL)
            AWTO_SW_FAST_POLL();
            AWTO_LP(2);
            AWTO_SW_MARK(2);
            AWTO_PS_POLL_SITE();

#if(_ALS_TYPE != _SENSER_NONE)
            SysMainAlsHandler();            
#endif

#if((_BACKLIGHT_SENSOR == _ON) || (_NEW_BACKLIGHT_SENSOR_FUN_EN == _ON))
            SysMainBackLightSensorHandler();
#endif

#if(_AUDIO_SUPPORT == _ON)
            SysAudioHandler();
#endif
            AWTO_SW_POLL_MARKS();
            AWTO_LP(3);
            AWTO_SW_MARK(3);
            AWTO_PS_POLL_SITE();
            SysTimerHandler();
            AWTO_LP(4);
            AWTO_SW_MARK(4);
            AWTO_PS_POLL_SITE();
            SysSourceHandler();
            AWTO_LP(5);
            AWTO_SW_MARK(5);
            AWTO_PS_POLL_SITE();
            SysMachineWork();                       // #162 step 3: the state's scaler work (was SysModeHandler)

#if(_MHL_SUPPORT == _ON)
            SysMHLMscHandler();
#endif

#if(_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON)
            SysTypeCHandler();

#endif

#if(_DP_SUPPORT == _ON)
            AWTO_SW_POLL_MARKS();
            AWTO_LP(6);
            AWTO_SW_MARK(6);
            AWTO_PS_POLL_SITE();
            SysDpRxHandler();
#endif

#if((_DVI_SUPPORT == _ON) || (_HDMI_SUPPORT == _ON))
            AWTO_LP(7);
            AWTO_SW_MARK(7);
            AWTO_PS_POLL_SITE();
            SysTMDSRxHandler();

#if(_HDMI_CEC_SUPPORT == _ON)
            SysCecHandler();
#endif
#endif

#if(_DP_TX_SUPPORT == _ON)
            SysDpTxHandler();
#endif

#if(_EMBEDDED_DP_TX_SUPPORT == _ON)
            SysDpEmbeddedTxHandler();
#endif

#if(_DP_MST_SUPPORT == _ON)
            SysDpMstHandler();
#endif

#if(_HDMI_TX_SUPPORT == _ON)
            SysHdmiTxHandler();
#endif

#if(_HDCP_2_2_SUPPORT == _ON)
            AWTO_LP(8);
            AWTO_SW_MARK(8);
            AWTO_PS_POLL_SITE();
            ScalerHdcp2Handler();
#endif

#if(_BILLBOARD_SCALER_SUPPORT == _ON)
            ScalerBBHandler();
#endif

#if(_AUTO_TEST_SUPPORT == _ON)
            SysAutotestHandler();
#endif

            AWTO_LP(9);
            AWTO_SW_MARK(9);
            AWTO_PS_POLL_SITE();
            AWTO_SET_LOOP();
            UserCommonInterfacePanelPowerTick();    // before the OSD handler's long draws (boot console): T3 / PWM steps due now
            UserCommonInterfaceOsdHandler();

#if(_DDCCI_CODE_REDUCTION == _OFF)
            if(AWTO_DDCCI_POLL_ON()) AWTO_DDCCI_POLL();
            AWTO_NET_POLL();
            AWTO_LP(10);
            AWTO_SW_MARK(10);
            AWTO_PS_POLL_SITE();
            UserCommonDdcciHandler();
#endif
            AWTO_PS_POLL_SITE();
            SysColorHandler();
            ScalerDebug();

        }
    }
    while(_TRUE);
}

//--------------------------------------------------
// Description  : System AC on initial flow
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysMainSystemInitial(void)
{
#if((_FLASH_PARTITION_TYPE == _FLASH_PARTITION_BOOT) &&\
    (_CODE_DIGITAL_SIGNATURE_SUPPORT == _SIGNATURE_TYPE_OFF))
    ScalerMcuBootInitial();

    SysMainStartUserCode(UserInterfaceGetUserCodeLocation());
#endif

    ScalerMcuInitial();
    SysPowerMcuClock(_M2PLL_CLK);           // #162 / #144: init on M2PLL, not the 14.318 MHz crystal (crystal again around the chip reset)

    AwtoDiagStage(3);
    ScalerPinshareInitial();

#if(_CODE_DIGITAL_SIGNATURE_SUPPORT == _SIGNATURE_TYPE_EXTERNAL)

    UserCommonSignExterMoveKey();

#elif(_CODE_DIGITAL_SIGNATURE_SUPPORT == _SIGNATURE_TYPE_INTERNAL)

#if(_FLASH_PARTITION_TYPE == _FLASH_PARTITION_BOOT)
    UserCommonSignHandler();
    SysMainStartUserCode(UserCommonSignGetSwitchUserBank());
#elif(_FLASH_PARTITION_TYPE == _FLASH_PARTITION_USER)
    UserCommonSignInterMoveKey();
#endif

#endif

    AwtoDiagStage(4);
    ScalerTimerInitialTimerEvent();         // before the backlight on: the pin arms the panel-time timer event
    UserCommonInterfacePanelBoot();         // VDD on since GPIO init (default on); PHY / link once power is NORMAL
#if(_AWTO_BOOT_PANEL_EARLY == _ON)
    // #162: backlight now, on M2PLL (Dan 2026-11-13: no T3 wait), cold and warm boot
    UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, (AwtoBootReason() == AWTO_BOOT_COLD) ? AWTO_PNL_BY_BOOT_COLD : AWTO_PNL_BY_BOOT_WARM));
#endif

    AWTO_BPROF(0x30);
    UserCommonInterfaceInitial();
    UserCommonInterfacePanelBootDuty();     // settings loaded: user brightness replaces the boot 100 %

    AWTO_BPROF(0x31);
    ScalerMcuDdcRamEnable();

    AWTO_BPROF(0x32);
    SysSourceInitial();

    AWTO_BPROF(0x33);
    SysPowerInitial();

#if(_IR_SUPPORT == _IR_HW_SUPPORT)
    ScalerIRHWModeInitial();
#endif

#if(_ALS_TYPE != _SENSER_NONE)
    ALS_Initial();
#endif

#if(_BACKLIGHT_SENSOR == _ON)
    InitTsl2561();
#elif(_NEW_BACKLIGHT_SENSOR_FUN_EN == _ON)
    InitBacklightSensor();
#endif


    AWTO_BPROF(0x34);
    SysMachineInit();                       // #162 step 3: AC_ON, power target from NVRAM (a request)
}

//--------------------------------------------------
// Description  : System power detect
// Input Value  : None
// Output Value : None
//--------------------------------------------------
bit SysMainSytemPowerDetect(void)
{
    return PCB_POWER_5V_DETECT();
}

#if(_ALS_TYPE != _SENSER_NONE)
void SysMainAlsHandler(void)
{
    if(GET_MODE_STATE() == _MODE_STATUS_ACTIVE)
        ScalerTimerActiveTimerEvent(SEC(0.04), _USER_TIMER_EVENT_ALS_ADJUST);
}
#endif

#if((_BACKLIGHT_SENSOR == _ON) || (_NEW_BACKLIGHT_SENSOR_FUN_EN == _ON))
void SysMainBackLightSensorHandler(void)
{
    if(GET_MODE_STATE() == _MODE_STATUS_ACTIVE)
    {
#if(_BACKLIGHT_SENSOR == _ON)    
        ScalerTimerActiveTimerEvent(SEC(0.04), _USER_TIMER_EVENT_BACKLIGHTSENSOR_ADJUST);
#elif(_NEW_BACKLIGHT_SENSOR_FUN_EN == _ON)
        ScalerTimerActiveTimerEvent(SEC(0.2), _USER_TIMER_EVENT_BACKLIGHTSENSOR_ADJUST);
#endif
    }
}
#endif


#if(_FLASH_PARTITION_TYPE != _FLASH_PARTITION_NONE)
//--------------------------------------------------
// Description  : Switch bank and jump to user code
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysMainStartUserCode(BYTE ucBankAddress)
{
#if(_FLASH_PARTITION_RELOCATABLE_SUPPORT == _ON)
    // Set bank offset for user __code
    SET_BANK_SWITCH_OFFSET(ucBankAddress);
#endif

    // Switch current bank
    MCU_FFFF_PBANK_SWITCH = ucBankAddress;

    // The below __code is used here to ignore the pre-read __code of mcu
    _nop_();
    _nop_();
    _nop_();
    _nop_();

#if(_FLASH_PARTITION_TYPE == _FLASH_PARTITION_USER)
    // Reset FW after switched to user code
    ((void (*)(void))0x0000)();
#endif
}
#endif


