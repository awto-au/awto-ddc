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
// ID Code      : SysCec.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __SYSTEM_CEC__

#include "SysInclude.h"

#if(_HDMI_CEC_SUPPORT == _ON)
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
void SysCecHandler(void);
__xdata BYTE g_ucAwtoCecPass;                   // pass counter of AWTO_CEC_DUE (ScalerCecInterface.h)
static __bit d_s_bCecInit;                        // ScalerCecInitial done since the last power-off
static __bit d_s_bCecOn;                          // registry cec_en as applied to the block

//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  : System Cec Handler
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysCecHandler(void)
{
    // awto (docs/cec.md): called when AWTO_CEC_DUE (ScalerCecInterface.h): a frame / reply / analysis is pending, else every 32nd pass.
    // Init after the display path is up (power NORMAL, mode settled), never in the power-on path; registry cec_en live
    if(GET_POWER_STATUS() == _POWER_STATUS_OFF)
    {
        d_s_bCecInit = 0;
    }
    if(d_s_bCecInit == 0)
    {
        if((GET_POWER_STATUS() != _POWER_STATUS_NORMAL) ||
           ((GET_MODE_STATE() != _MODE_STATUS_ACTIVE) && (GET_MODE_STATE() != _MODE_STATUS_NOSIGNAL) && (GET_MODE_STATE() != _MODE_STATUS_NOSUPPORT)))
        {
            return;
        }
        ScalerCecInitial();
        d_s_bCecOn = UserInterfaceCecGetCecActive();
        ScalerCecFunctionEnable(d_s_bCecOn);
        ScalerCecBlockEnable(d_s_bCecOn);
        d_s_bCecInit = 1;
        AwtoSyncPush(AWTO_SYNC_EV_CEC, AWTO_CEC_K_STATE, d_s_bCecOn);
    }
    else if(d_s_bCecOn != UserInterfaceCecGetCecActive())
    {
        d_s_bCecOn = UserInterfaceCecGetCecActive();
        ScalerCecFunctionEnable(d_s_bCecOn);
        ScalerCecBlockEnable(d_s_bCecOn);
        AwtoSyncPush(AWTO_SYNC_EV_CEC, AWTO_CEC_K_STATE, d_s_bCecOn);
    }

    // Receive part
    ScalerCecRxProcess();
    UserCommonCecReceiveNotify();

    // Transmit part
    ScalerCecTxProcess();
    UserInterfaceCecHighLevelFlow();            // result of the last reply, release the RX path (was called from the OSD handler)
}

#endif
