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
// ID Code      : RTD2014Ddcci.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __RTD_DDCCI__

#include "UserCommonInclude.h"

#if(_OSD_TYPE == _REALTEK_2014_OSD)

//****************************************************************************
// DEFINITIONS / MACROS
//****************************************************************************

#define _DDCCI_FIRMWARE_VERSION                     0x01

#define _DDCCI_BLACKLEVEL_DEFAULT                   0x50

// RC
#define _DDCCI_CMD_GETVCP_RC_NO_ERROR               0x00
#define _DDCCI_CMD_GETVCP_RC_UNSUPPORTED            0x01

// TP
#define _DDCCI_CMD_GETVCP_TP_SET_PARAMETER          0x00
#define _DDCCI_CMD_GETVCP_TP_MOMENTARY              0x01

//--------------------------------------------------
// Definitions of Contrast Range (Real Value)
//--------------------------------------------------
#define _COLORTEMP_USER_MAX                         255
#define _COLORTEMP_USER_MIN                         0
#define _COLORTEMP_USER_CENTER                      (((_COLORTEMP_USER_MAX - _COLORTEMP_USER_MIN) / 2) + _COLORTEMP_USER_MIN)

//--------------------------------------------------
// For DDCCI Set Input Port
//--------------------------------------------------
#define _VGA_1                                      _A0_INPUT_PORT
#define _DVI_1                                      _NO_INPUT_PORT
#define _DVI_2                                      _NO_INPUT_PORT
#define _DP_1                                       _D1_INPUT_PORT
#define _DP_2                                       _NO_INPUT_PORT
#define _HDMI_1                                     _D2_INPUT_PORT
#define _HDMI_2                                     _D3_INPUT_PORT

//--------------------------------------------------
// Dell DDM Tool
//--------------------------------------------------
#define _DDCCI_OPCODE_VCP_DELL_DDM_SUPPORT          0xF1


//****************************************************************************
// STRUCT / TYPE / ENUM DEFINITTIONS
//****************************************************************************
BYTE __code tCOLORPRESET_VALUE[] = {0x08, 0x06, 0x05, 0x04, 0x01, 0x0B, 0x02};

BYTE __code tLANGUAGEDEFINE[] = {0x02, 0x01, 0x03, 0x04, 0x0A, 0x0D, 0x06};



//****************************************************************************
// VARIABLE DECLARATIONS
//****************************************************************************
BYTE g_ucDdcciRedBlackLevel   = _DDCCI_BLACKLEVEL_DEFAULT;
BYTE g_ucDdcciGreenBlackLevel = _DDCCI_BLACKLEVEL_DEFAULT;
BYTE g_ucDdcciBlueBlackLevel  = _DDCCI_BLACKLEVEL_DEFAULT;
BYTE g_ucDdcciNewControlValue = 1;
BYTE g_ucDdcciActiveValue;
BYTE g_ucColorTempUnSupport;

__xdata _Bool g_bForcePowSavStatus = _FALSE;

//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
void UserDdcciHandler(void);

//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  : DDC Handler Process
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void UserDdcciHandler(void)
{
    // DDC/CI is ours (#60): GET_OSD_DDCCI_STATUS() is _OFF (RL6449_Project.h), so the SDK VCP branch never ran (#209)
#if((_DP_SUPPORT == _ON) && (_DP_MST_SUPPORT == _ON))
    if((GET_RUN_DDCCI_COMMAND() == _SUCCESS) && (UserCommonInterfaceGetDpMstCapablePort() != _DP_MST_NO_PORT))
    {
        UserCommonDdcciInitTx();
        SET_RUN_DDCCI_COMMAND(_FAIL);
    }
#endif
}

#if(_DDCCI_CUSTOM_CAPABILITY_STR_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Get custom capability string data
// Input Value  : pucDest -> destination
//                enumPortType -> port type
//                usStartIndex -> __data offset
//                usLength -> __data length
// Output Value : None
//--------------------------------------------------
void UserInterfaceDdcciGetCpStringData(BYTE *pucDest, EnumInputPortType enumPortType, WORD usStartIndex, WORD usLength)
{
    pucDest = pucDest;
    enumPortType = enumPortType;
    usStartIndex = usStartIndex;
    usLength = usLength;
}

//--------------------------------------------------
// Description  : Get custom capability string size
// Input Value  : enumPortType -> port type
// Output Value : size
//--------------------------------------------------
WORD UserInterfaceDdcciGetCpStringSize(EnumInputPortType enumPortType)
{
    enumPortType = enumPortType;
    return 0;
}
#endif





#endif // End of #if(_OSD_TYPE == _REALTEK_2014_OSD)
