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
// ID Code      : UserCommonCec.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __USER_COMMON_CEC__

#include "UserCommonInclude.h"

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
void UserCommonCecReceiveNotify(void);


//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  : Received CEC RX INFO bypass to User
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void UserCommonCecReceiveNotify(void)
{
    if(GET_CEC_RX_READ_DONE() == _TRUE)
    {
        DebugMessageCEC("CEC RX Read: HB ", isr_g_stCecRxReceivedInfo.ucReceivedHb);

        // awto: analysing flag first (the interrupt then fills the backup FIFO, not this struct); the frame is handled in place,
        // no local copy (XDATA floor, docs/cec.md); the reply goes straight into g_stCecTxTransmitInfo
        SET_CEC_RX_MSG_ANALYZING();
        CLR_CEC_RX_READ_DONE();
        UserInterfaceCecReceivedNotify((StructCecRxReceivedInfo *)&isr_g_stCecRxReceivedInfo);

        // reset Cec rx struct
        memset(&isr_g_stCecRxReceivedInfo, 0, sizeof(isr_g_stCecRxReceivedInfo));
    }
}

#endif
