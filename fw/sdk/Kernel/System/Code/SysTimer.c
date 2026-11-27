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
// ID Code      : SysTimer.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __SYSTEM_TIMER__

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
void SysTimerHandler(void);
void SysTimerEventProc(EnumScalerTimerEventID enumEventID);
void SysTimerIntProc0(void) __interrupt(1);
void SysTimerIntProc2(void) __interrupt(5);
void SysTimerWDIntProc(void) __interrupt(8);

//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  : Timer Handler
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysTimerHandler(void)
{
    BYTE ucTimerEventIndex = 0;
    BYTE ucTimerEventID = 0;

    for(ucTimerEventIndex = 0; ucTimerEventIndex < _TIMER_EVENT_COUNT; ucTimerEventIndex++)
    {
        if((ScalerTimerCheckEventValid(ucTimerEventIndex) == _TRUE) &&
           (ScalerTimerGetTimerCounter() > ScalerTimerGetEventTime(ucTimerEventIndex)))
        {
            ucTimerEventID = ScalerTimerGetEventID(ucTimerEventIndex);
            ScalerTimerClrEventValid(ucTimerEventIndex);

            if(ucTimerEventID < _USER_TIMER_EVENT_END)
            {
                UserCommonInterfaceTimerEventProc(ucTimerEventID);
            }
            else if(ucTimerEventID < _SYSTEM_TIMER_EVENT_END)
            {
                SysTimerEventProc(ucTimerEventID);
            }
            else
            {
                ScalerTimerEventProc(ucTimerEventID);
            }
        }
    }
}

#if(AWTO_LOOP_PACING > 0)
//--------------------------------------------------
// Description  : ms until the earliest valid timer event fires (SysTimerHandler fires at counter > time); 0xFFFF = none
//--------------------------------------------------
unsigned int SysTimerNextEventMs(void)
{
    BYTE ucI;
    WORD usNow = ScalerTimerGetTimerCounter();
    WORD usBest = 0xFFFF;
    WORD usD;

    for(ucI = 0; ucI < _TIMER_EVENT_COUNT; ucI++)
    {
        if(ScalerTimerCheckEventValid(ucI) == _TRUE)
        {
            usD = ScalerTimerGetEventTime(ucI);
            usD = (usD >= usNow) ? (usD - usNow + 1) : 0;
            if(usD < usBest)
            {
                usBest = usD;
            }
        }
    }
    return usBest;
}
#endif

//--------------------------------------------------
// Description  : Timer Event Process
// Input Value  : enumEventID --> Event to be processed
// Output Value : None
//--------------------------------------------------
void SysTimerEventProc(EnumScalerTimerEventID enumEventID)
{
    switch(enumEventID)
    {
        case _SYSTEM_TIMER_EVENT_SOURCE_CLEAR_DETECTING:
            SysSourceClearDetectingEvent();
            break;

        case _SYSTEM_TIMER_EVENT_JUDGE_ACTIVE_STATE:
            SET_MODE_ACTIVE_READY();
            AwtoSyncTail(1);
            break;

        case _SYSTEM_TIMER_EVENT_JUDGE_NOSUPPORT_STATE:
            SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_NOSUPPORT, AWTO_SYS_BY_TIMER_NOSUPPORT);
            break;

        case _SYSTEM_TIMER_EVENT_JUDGE_NOSIGNAL_STATE:
            SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_NOSIGNAL, AWTO_SYS_BY_TIMER_NOSIGNAL);
            break;

        case _SYSTEM_TIMER_EVENT_POWER_FAKE_OFF_TO_OFF:

#if(_DP_MST_SUPPORT == _ON)
            ScalerDpMstFakeOffDoneProc();
#endif
            SysMachineRequest(_POWER_STATUS_OFF, AWTO_SYS_BY_SDK);
            break;

#if(_EMBEDDED_DAC_SUPPORT == _ON)
        case _SYSTEM_TIMER_EVENT_AUDIO_DAC_WAIT_VCM_INITIAL:
            ScalerAudioDACSetState(_AUDIO_DAC_CHARGE);
            break;

        case _SYSTEM_TIMER_EVENT_AUDIO_DAC_WAIT_VCM_CHARGE:
            ScalerAudioDACSetState(_AUDIO_DAC_DEPOP);
            break;

        case _SYSTEM_TIMER_EVENT_AUDIO_DAC_WAIT_DEPOP_TO_NORMAL:
            ScalerAudioDACDepopToNormal();
            break;
#endif // End of #if(_EMBEDDED_DAC_SUPPORT == _ON)

#if(_HP_SOURCE_SCAN_SUPPORT == _ON)
        case _SYSTEM_TIMER_EVENT_SOURCE_HP_CANCEL_MANUAL_SWITCH_PORT:
            SET_SOURCE_HP_PORT_SWITCH_TARGET((_INPUT_PORT_VALID + 1));
            break;
#endif

#if(_SOURCE_AUTO_SEARCH_STYLE == _SOURCE_POLLING_ASUS_STYLE)
        case _SYSTEM_TIMER_EVENT_SOURCE_ASUS_START_AUTO:
            SET_SOURCE_ASUS_START_AUTO();
            SET_SOURCE_ASUS_FIRST_START_AUTO();
            break;
#endif

#if(_SOURCE_AUTO_SEARCH_STYLE == _SOURCE_POLLING_EIZO_STYLE)
        case _SYSTEM_TIMER_EVENT_SOURCE_EIZO_SEARCH_FINISH:
            if(UserInterfaceAdjustOsdCheckTotalSearchFinish() == _TRUE)
            {
                SET_SOURCE_SWITCH_FINISH();
                CLR_SOURCE_DETECTING();
                ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_SOURCE_CLEAR_DETECTING);
            }
            break;
#endif

#if(((_D6_INPUT_PORT_TYPE != _D6_NO_PORT) && (_D6_INPUT_PORT_SWITCH_FROM == _SWITCH_FROM_D0)) || (_DP_EMBEDDED_SWITCH_SUPPORT_TYPE == _DP_EMBEDDED_SWITCH_2_DP))
        case _SYSTEM_TIMER_EVENT_SOURCE_DP_SWITCH_TIMEOUT:
            SET_SOURCE_DP_SWITCH_TIMEOUT();
            break;
#endif

#if(_D0_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON)
#if(_D0_DP_TYPE_C_DISCRETE_PORT_CTRL_LINK == _DISCRETE_PORT_CTRL_USE_SMBUS)
        case _SYSTEM_TIMER_EVENT_D0_TYPE_C_CABLE_DETECT:

            UserCommonPortControllerSetD0I2CDetection();

            break;
#else
        case _SYSTEM_TIMER_EVENT_D0_TYPE_C_UNATTACH:

            SysTypeCSwitchToUnattachState(_D0_INPUT_PORT);

            break;
#endif

#if((_TYPE_C_PORT_CTRL_MODAL_OPERATION_SUPPORT == _ON) && (_TYPE_C_VENDOR_ALT_MODE == _TYPE_C_LENOVO_ALT_MODE))
        case _SYSTEM_TIMER_EVENT_D0_TYPE_C_LENOVO_RCV_DEVICE_TYPE_TIMEOUT:

            SysTypeCSetLenovoRcvDeviceTypeTimeout(_D0_INPUT_PORT);

            break;

#if(_D0_DP_TYPE_C_PORT_CTRL_TYPE == _PORT_CONTROLLER_RTS5400_SERIES)
        case _SYSTEM_TIMER_EVENT_D0_TYPE_C_LENOVO_ALT_MODE_DETECT:

            UserCommonPortControllerSet5400LenovoAltModeDetection(_D0_INPUT_PORT);

            break;

        case _SYSTEM_TIMER_EVENT_D0_TYPE_C_LENOVO_DEVICE_TYPE_DETECT:

            UserCommonPortControllerSet5400LenovoDeviceTypeDetection(_D0_INPUT_PORT);

            break;
#endif
#endif

#if(_D0_DP_TYPE_C_HUB_COMMUNICATION_SUPPORT == _ON)
        case _SYSTEM_TIMER_EVENT_D0_USBHUB_DETECT:
            SET_D0_USB_HUB_SS_DEVICE_DETECT_FLG();
            break;
#endif

#if(_D0_BILLBOARD_SUPPORT == _ON)
        case _SYSTEM_TIMER_EVENT_D0_ENABLE_BILLBOARD:
            SysTypeCBillboardControl(_D0_INPUT_PORT, _TYPE_C_BB_ENABLE);
            break;
#endif
#endif // End of #if(_D0_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON)

#if(_D1_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON)
#if(_D1_DP_TYPE_C_DISCRETE_PORT_CTRL_LINK == _DISCRETE_PORT_CTRL_USE_SMBUS)
        case _SYSTEM_TIMER_EVENT_D1_TYPE_C_CABLE_DETECT:

            UserCommonPortControllerSetD1I2CDetection();

            break;
#else
        case _SYSTEM_TIMER_EVENT_D1_TYPE_C_UNATTACH:

            SysTypeCSwitchToUnattachState(_D1_INPUT_PORT);

            break;
#endif

#if((_TYPE_C_PORT_CTRL_MODAL_OPERATION_SUPPORT == _ON) && (_TYPE_C_VENDOR_ALT_MODE == _TYPE_C_LENOVO_ALT_MODE))
        case _SYSTEM_TIMER_EVENT_D1_TYPE_C_LENOVO_RCV_DEVICE_TYPE_TIMEOUT:

            SysTypeCSetLenovoRcvDeviceTypeTimeout(_D1_INPUT_PORT);

            break;

#if(_D1_DP_TYPE_C_PORT_CTRL_TYPE == _PORT_CONTROLLER_RTS5400_SERIES)
        case _SYSTEM_TIMER_EVENT_D1_TYPE_C_LENOVO_ALT_MODE_DETECT:

            UserCommonPortControllerSet5400LenovoAltModeDetection(_D1_INPUT_PORT);

            break;

        case _SYSTEM_TIMER_EVENT_D1_TYPE_C_LENOVO_DEVICE_TYPE_DETECT:

            UserCommonPortControllerSet5400LenovoDeviceTypeDetection(_D1_INPUT_PORT);

            break;
#endif
#endif

#if(_D1_DP_TYPE_C_HUB_COMMUNICATION_SUPPORT == _ON)
        case _SYSTEM_TIMER_EVENT_D1_USBHUB_DETECT:
            SET_D1_USB_HUB_SS_DEVICE_DETECT_FLG();
            break;
#endif

#if(_D1_BILLBOARD_SUPPORT == _ON)
        case _SYSTEM_TIMER_EVENT_D1_ENABLE_BILLBOARD:
            SysTypeCBillboardControl(_D1_INPUT_PORT, _TYPE_C_BB_ENABLE);
            break;
#endif
#endif // End of #if(_D1_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON)

#if(_D6_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON)
#if(_D6_DP_TYPE_C_DISCRETE_PORT_CTRL_LINK == _DISCRETE_PORT_CTRL_USE_SMBUS)
        case _SYSTEM_TIMER_EVENT_D6_TYPE_C_CABLE_DETECT:

            UserCommonPortControllerSetD6I2CDetection();

            break;
#else
        case _SYSTEM_TIMER_EVENT_D6_TYPE_C_UNATTACH:

            SysTypeCSwitchToUnattachState(_D6_INPUT_PORT);

            break;
#endif

#if((_TYPE_C_PORT_CTRL_MODAL_OPERATION_SUPPORT == _ON) && (_TYPE_C_VENDOR_ALT_MODE == _TYPE_C_LENOVO_ALT_MODE))
        case _SYSTEM_TIMER_EVENT_D6_TYPE_C_LENOVO_RCV_DEVICE_TYPE_TIMEOUT:

            SysTypeCSetLenovoRcvDeviceTypeTimeout(_D6_INPUT_PORT);

            break;

#if(_D6_DP_TYPE_C_PORT_CTRL_TYPE == _PORT_CONTROLLER_RTS5400_SERIES)
        case _SYSTEM_TIMER_EVENT_D6_TYPE_C_LENOVO_ALT_MODE_DETECT:

            UserCommonPortControllerSet5400LenovoAltModeDetection(_D6_INPUT_PORT);

            break;

        case _SYSTEM_TIMER_EVENT_D6_TYPE_C_LENOVO_DEVICE_TYPE_DETECT:

            UserCommonPortControllerSet5400LenovoDeviceTypeDetection(_D6_INPUT_PORT);

            break;
#endif
#endif

#if(_D6_DP_TYPE_C_HUB_COMMUNICATION_SUPPORT == _ON)
        case _SYSTEM_TIMER_EVENT_D6_USBHUB_DETECT:
            SET_D6_USB_HUB_SS_DEVICE_DETECT_FLG();
            break;
#endif

#if(_D6_BILLBOARD_SUPPORT == _ON)
        case _SYSTEM_TIMER_EVENT_D6_ENABLE_BILLBOARD:
            SysTypeCBillboardControl(_D6_INPUT_PORT, _TYPE_C_BB_ENABLE);
            break;
#endif
#endif // End of #if(_D6_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON)

#if(_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON)
#if(_PORT_CONTROLLER_RTS5400_SERIES_SUPPORT == _ON)
#if((_TYPE_C_PORT_CTRL_MODAL_OPERATION_SUPPORT == _ON) && (_TYPE_C_VENDOR_ALT_MODE == _TYPE_C_LENOVO_ALT_MODE))
        case _SYSTEM_TIMER_EVENT_TYPE_C_LENOVO_ALT_MODE_URGENT_EVENT_TIMEOUT:
            CLR_TYPE_C_5400_LENOVO_ALT_MODE_URGENT_EVENT();
            break;
#endif
#endif
#endif

#if(_AUTO_TEST_SUPPORT == _ON)
        case _SYSTEM_TIMER_EVENT_AUTO_TEST_OSD_SWITCH_CTRL:
            SysAutotestOSDSwitchCtrl();
            break;
#endif

#if(_AIO_MODERN_STANDBY_SUPPORT == _ON)
        case _SYSTEM_TIMER_EVENT_AIO_MODERN_STANDBY_MODE_TIMEOUT:
            CLR_AIO_MODERN_STANDBY_MODE();
            break;
#endif

#if(_DDCCI_AUTO_SWITCH_SUPPORT == _ON)
        case _SYSTEM_TIMER_EVENT_CLR_DDCCI_RECEIVE_COMMAND_NOT_FINISH:
            CLR_RECEIVE_DDCCI_CMD_NOT_FINISH();
            break;
#endif
        default:
            break;
    }
}

//--------------------------------------------------
// Description  : Timer0 Int Function
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysTimerIntProc0(void) __interrupt(1)
{
    static BYTE ucFff4;   // private to this ISR: burst-write backup, own storage (an overlaid local broke the stall test)

    // Backup for Burst Write Bug
    ucFff4 = MCU_FFF4_SCA_INF_ADDR; AwtoT0EvIsr(); AWTO_ISR_WAKE(T0);

    // Reload Backup for Burst Write Bug
    MCU_FFF4_SCA_INF_ADDR = ucFff4;
}

//--------------------------------------------------
// Description  : Timer2 Int Function
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysTimerIntProc2(void) __interrupt(5)
{
    static BYTE ucFff4;   // private to this ISR: burst-write backup, own storage (an overlaid local broke the stall test)

    // Backup for Burst Write Bug
    ucFff4 = MCU_FFF4_SCA_INF_ADDR;

    // Clear Timer2 flag
    AWTO_DIAG_T2ISR();
    TF2 = 0;

    d_isr_g_bNotifyTimer2Int = _TRUE;

    // Timer Counter
    d_isr_g_usTimerCounter += 1;

#if((_DP_SUPPORT == _ON) && (_DP_IRQ_HPD_MODE == _DP_IRQ_HPD_T2_MODE))
    ScalerSyncDpHpdIrqAssertTimer2EventProc_EXINT();
#endif

    AWTO_MEAS_T2ISR();
    // Reload Backup for Burst Write Bug
    MCU_FFF4_SCA_INF_ADDR = ucFff4;
}

//--------------------------------------------------
// Description  : WD Timer Int Function
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysTimerWDIntProc(void) __interrupt(8)
{
    static BYTE ucFff4;   // private to this ISR: burst-write backup, own storage (an overlaid local broke the stall test)

    // Backup for Burst Write Bug
    ucFff4 = MCU_FFF4_SCA_INF_ADDR;

    // Clear Flag
    EXIF &= ~_BIT4;

#if(_WD_TIMER_INT_SUPPORT == _ON)
    AWTO_WDT_IRQ();
#endif

    if(((MCU_FFEB_WDT_TEST & _BIT7) == _BIT7) && ((EXIF & _BIT4) == 0x00))
    {
        EXIF = (EXIF & (~_BIT4)) | _BIT4;
    }

    // Reload Backup for Burst Write Bug
    MCU_FFF4_SCA_INF_ADDR = ucFff4;
}
