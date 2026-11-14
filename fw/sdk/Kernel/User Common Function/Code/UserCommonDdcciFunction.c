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
// ID Code      : UserCommonDdcciFunction.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __USER_COMMON_DDCCI_FUNCTION__

#include "UserCommonInclude.h"

#if(_DDCCI_CODE_REDUCTION == _OFF)
//****************************************************************************
// DEFINITIONS / MACROS
//****************************************************************************
//--------------------------------------------------
// Definitions of DDCCI Capabilities Request
//--------------------------------------------------
#if(_DDCCI_AUTO_SWITCH_SUPPORT == _ON)
// I2C Speed = 20k, DDCCI Buffer = _DDCCI_RXBUF_LENGTH
// (1/20K)*_DDCCI_RXBUF_LENGTH*8
#define _CLR_DDCCI_CMD_RECEIVE_NOT_FINISH_TIMEOUT       (((_DDCCI_RXBUF_LENGTH * 9) / 20) + 1)
#endif

//****************************************************************************
// STRUCT / TYPE / ENUM DEFINITTIONS
//****************************************************************************


//****************************************************************************
// CODE TABLES
//****************************************************************************
#if(_DDCCI_CUSTOM_CAPABILITY_STR_SUPPORT == _OFF)
#if(_VGA_PORT_EXIST == _ON)
BYTE __code tCP_STRING_DSUB[] =
{
    _CAPABILITIES_STRING_VGA
};
#endif

#if(_DVI_PORT_EXIST == _ON)
BYTE __code tCP_STRING_DVI[] =
{
    _CAPABILITIES_STRING_DVI
};
#endif

#if(_HDMI_PORT_EXIST == _ON)
BYTE __code tCP_STRING_HDMI[] =
{
    _CAPABILITIES_STRING_HDMI
};
#endif

#if(_DP_PORT_EXIST == _ON)
BYTE __code tCP_STRING_DP[] =
{
    _CAPABILITIES_STRING_DP
};
#endif
#endif

//****************************************************************************
// VARIABLE DECLARATIONS
//****************************************************************************

#if(_SUPPORT_GET_LUT == _ON)
WORD g_ucLUTCheckSum = 0;
BYTE g_ucLUTReadyFlag = 0;
#endif

//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
void UserCommonDdcciHandler(void);

//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  : User Common DDC Handler Process
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void UserCommonDdcciHandler(void)
{
#if(_DDCCI_AUTO_SWITCH_SUPPORT == _ON)
    if(GET_RUN_DDCCI_COMMAND() == _FAIL)
    {
        if(GET_RECEIVE_DDCCI_CMD_NOT_FINISH() == _SUCCESS)
        {
            // Polling User Ddcci Cmd Finished
            ScalerTimerActiveTimerEvent(_CLR_DDCCI_CMD_RECEIVE_NOT_FINISH_TIMEOUT, _SYSTEM_TIMER_EVENT_CLR_DDCCI_RECEIVE_COMMAND_NOT_FINISH);
        }
        else
        {
            if(GET_DDCCI_AUTO_SWITCH() == _FALSE)
            {
                // Enable DDCCI Channel Auto Switch
                SET_DDCCI_AUTO_SWITCH();

                // Set Other DDC Enable
                ScalerMcuDdcciAutoSwitchInactiveChannel(_ENABLE);
            }
        }
    }
#endif

    UserDdcciHandler();
}



#if((_GAMMA_IN_FLASH_BANK == _ON) && (BEACON_GAMMA_TYPE != Gamma_default))    
//--------------------------------------------------
// Description  : Caculate checksum
// Input Value  : None
// Output Value : ucSum --> Checksum value
//--------------------------------------------------
BYTE UserCommonDdcciCalRxCheckSum(void)
{
    BYTE ucCount = 0;
    BYTE ucCheckLen = 0;
    BYTE ucSum = _DDCCI_DEST_ADDRESS;

    ucCheckLen = (g_pucDdcciRxBuf[_DDCCI_LENGTH] & 0x7F) + 2;

    for(ucCount = 0; ucCount < ucCheckLen; ucCount++)
    {
        ucSum = ucSum ^ g_pucDdcciRxBuf[ucCount];
    }

    return ucSum;
}
#endif






#endif  // #if(_DDCCI_CODE_REDUCTION == _OFF)
