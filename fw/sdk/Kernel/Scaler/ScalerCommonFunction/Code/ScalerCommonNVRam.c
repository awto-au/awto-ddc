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
// ID Code      : ScalerCommonNVRam.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __SCLAER_COMMON_NVRAM__

#include "ScalerCommonFunctionInclude.h"


//****************************************************************************
// DEFINITIONS / MACROS
//****************************************************************************
#define _RDSR_OPCODE                                   0x05
#define _RDCR_OPCODE                                   0x15

#define _WRITE_SR_MODE_SEL                             (_FLASH_EWSR_FUNCTION_SUPPORT == _ON)

//****************************************************************************
// STRUCT / TYPE / ENUM DEFINITTIONS
//****************************************************************************

//****************************************************************************
// CODE TABLES
//****************************************************************************
#if((_FLASH_WRITE_FUNCTION_SUPPORT == _ON) || (_FLASH_WR_PROTECT == _ON))
#if(_AWTO_FLASH_ALL == _ON)
StructFlashInformation __code tFlashInformation[] =
{
    // _FLASH_W25X20A; ucUnprotectWRSR is not used here
    {0x9F, 0xEF, 0x30, 0x12, 0x90, 0xEF, 0x11, 0x00, 0x06, 0x04, 0x20, 0x28, 0xBC},
    // _FLASH_W25X21CL; ucUnprotectWRSR is not used here
    {0x9F, 0xEF, 0x30, 0x12, 0x90, 0xEF, 0x11, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_PM25LV020; ucUnprotectWRSR is not used here
    {0x9F, 0x7F, 0x9D, 0x7D, 0xAB, 0x9D, 0x7D, 0x7F, 0x26, 0x24, 0xD7, 0x00, 0x9C},
    // _FLASH_MX25L2026; ucUnprotectWRSR is not used here
    {0x9F, 0xC2, 0x20, 0x12, 0x90, 0xC2, 0x03, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_EN25F20; ucUnprotectWRSR is not used here
    {0x9F, 0x1C, 0x31, 0x12, 0x90, 0x1C, 0x11, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
    // _FLASH_PM25LD020; ucUnprotectWRSR is not used here
    {0x9F, 0x7F, 0x9D, 0x22, 0x90, 0x9D, 0x11, 0x7F, 0x26, 0x24, 0xD7, 0x00, 0x9C},
    // _FLASH_MX25L2025; ucUnprotectWRSR is not used here
    {0x9F, 0xC2, 0x20, 0x12, 0x90, 0xC2, 0x11, 0x00, 0x06, 0x04, 0x20, 0x02, 0x8C},
    // _FLASH_MX25L4006E; ucUnprotectWRSR is not used here
    {0X9F, 0xC2, 0x20, 0x13, 0x90, 0xC2, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
    // _FLASH_SST25LF020A
    {0x90, 0xBF, 0x43, 0x00, 0x90, 0xBF, 0x43, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
    // _FLASH_W25X41CL; ucUnprotectWRSR is not used here
    {0x9F, 0xEF, 0x30, 0x13, 0x90, 0xEF, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_FM25F04; ucUnprotectWRSR is not used here
    {0x9F, 0xA1, 0x31, 0x13, 0x90, 0xA1, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_N25S40; ucUnprotectWRSR is not used here
    {0x9F, 0xD5, 0x30, 0x13, 0x90, 0xD5, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_A25L040; ucUnprotectWRSR is not used here
    {0x9F, 0x37, 0x30, 0x13, 0x90, 0x37, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
    // _FLASH_W25Q80BV; ucUnprotectWRSR is not used here
    {0x9F, 0xEF, 0x40, 0x14, 0x90, 0xEF, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_PM25LQ020A; ucUnprotectWRSR is not used here
    {0x9F, 0x7F, 0x9D, 0x42, 0x90, 0x9D, 0x11, 0x7F, 0x26, 0x24, 0x20, 0x02, 0x9C},
    // _FLASH_MX25L4026D; ucUnprotectWRSR is not used here
    {0x9F, 0xC2, 0x20, 0x13, 0x90, 0xC2, 0x04, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_W25X40CL; ucUnprotectWRSR is not used here
    {0x9F, 0xEF, 0x30, 0x13, 0x90, 0xEF, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_EN25F20A; ucUnprotectWRSR is not used here
    {0x9F, 0x1C, 0x31, 0x12, 0x90, 0x1C, 0x11, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_EN25F40A; ucUnprotectWRSR is not used here
    {0x9F, 0x1C, 0x31, 0x13, 0x90, 0x1C, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_EN25Q40A; ucUnprotectWRSR is not used here
    {0x9F, 0x1C, 0x30, 0x13, 0x90, 0x1C, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_EN25Q80; ucUnprotectWRSR is not used here
    {0x9F, 0x1C, 0x30, 0x14, 0x90, 0x1C, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_GD25Q80B; ucUnprotectWRSR is not used here
    {0x9F, 0xC8, 0x40, 0x14, 0x90, 0xC8, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_GD25M21B; ucUnprotectWRSR and ucProtectWRSR is not used here
    {0x9F, 0xC8, 0x41, 0x12, 0x90, 0xC8, 0x11, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_GD25M41B; ucUnprotectWRSR and ucProtectWRSR is not used here
    {0x9F, 0xC8, 0x41, 0x13, 0x90, 0xC8, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_MX25L8006E; ucUnprotectWRSR is not used here
    {0X9F, 0xC2, 0x20, 0x14, 0x90, 0xC2, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
    // _FLASH_PM25LQ080; ucUnprotectWRSR is not used here
    {0x9F, 0x9D, 0x13, 0x44, 0x90, 0x9D, 0x13, 0x7F, 0x26, 0x24, 0x20, 0x02, 0xBC},
    // _FLASH_GD25Q40B; ucUnprotectWRSR is not used here
    {0x9F, 0xC8, 0x40, 0x13, 0x90, 0xC8, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_MX25L1606E; ucUnprotectWRSR is not used here
    {0x9F, 0xC2, 0x20, 0x15, 0x90, 0xC2, 0x14, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_MX25L3206E; ucUnprotectWRSR is not used here
    {0x9F, 0xC2, 0x20, 0x16, 0x90, 0xC2, 0x15, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_A25L016; ucUnprotectWRSR is not used here
    {0x9F, 0x37, 0x30, 0x15, 0x90, 0x37, 0x14, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
    // _FLASH_W25Q16DV; ucUnprotectWRSR is not used here
    {0x9F, 0xEF, 0x40, 0x15, 0x90, 0xEF, 0x14, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_A25L032; ucUnprotectWRSR is not used here
    {0x9F, 0x37, 0x30, 0x16, 0x90, 0x37, 0x15, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_W25Q32F; ucUnprotectWRSR is not used here
    {0x9F, 0xEF, 0x40, 0x16, 0x90, 0xEF, 0x15, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_GD25Q16; ucUnprotectWRSR is not used here
    {0x9F, 0xC8, 0x40, 0x15, 0x90, 0xC8, 0x14, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_MX25L1633E; ucUnprotectWRSR is not used here
    {0x9F, 0xC2, 0x24, 0x15, 0x90, 0xC2, 0x24, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_GD25Q16C; ucUnprotectWRSR is not used here
    {0x9F, 0xC8, 0x40, 0x15, 0x90, 0xC8, 0x14, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_MX25L3233F; ucUnprotectWRSR is not used here
    {0x9F, 0xC2, 0x20, 0x16, 0x90, 0xC2, 0x15, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_PM25LQ040; ucUnprotectWRSR is not used here
    {0x9F, 0x7F, 0x9D, 0x7E, 0x90, 0x9D, 0x7E, 0x7F, 0x26, 0x24, 0xD7, 0x00, 0x9C},
    // _FLASH_GD25Q41B; ucUnprotectWRSR is not used here
    {0x9F, 0xC8, 0x40, 0x13, 0x90, 0xC8, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_EN25QH32A; ucUnprotectWRSR is not used here
    {0x9F, 0x1C, 0x70, 0x16, 0x90, 0x1C, 0x15, 0x00, 0x06, 0x04, 0x20, 0x42, 0xBC},
    // _FLASH_MX25V1635F; ucUnprotectWRSR is not used here
    {0x9F, 0xC2, 0x23, 0x15, 0x90, 0xC2, 0x15, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_AT25SF041; ucUnprotectWRSR is not used here
    {0x9F, 0x1F, 0x84, 0x01, 0x90, 0x1F, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_MX25L6433F; ucUnprotectWRSR is not used here
    {0x9F, 0xC2, 0x20, 0x17, 0x90, 0xC2, 0x16, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_PM25LQ016; ucUnprotectWRSR is not used here
    {0x9F, 0x9D, 0x14, 0x45, 0x90, 0x9D, 0x14, 0x7F, 0x26, 0x24, 0x20, 0x02, 0xBC},
    // _FLASH_GD25Q32C; ucUnprotectWRSR is not used here
    {0x9F, 0xC8, 0x40, 0x16, 0x90, 0xC8, 0x15, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_MX25V8035F; ucUnprotectWRSR is not used here
    {0x9F, 0xC2, 0x23, 0x14, 0x90, 0xC2, 0x14, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_AT25SF321; ucUnprotectWRSR is not used here
    {0x9F, 0x1F, 0x87, 0x01, 0x90, 0x1F, 0x15, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
    // _FLASH_FM25Q08A; ucUnprotectWRSR is not used here
    {0x9F, 0xA1, 0x40, 0x14, 0x90, 0xA1, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_FM25Q04; ucUnprotectWRSR is not used here
    {0x9F, 0xA1, 0x40, 0x13, 0x90, 0xA1, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_W25Q16JVSIM; ucUnprotectWRSR is not used here
    {0x9F, 0xEF, 0x70, 0x15, 0x90, 0xEF, 0x14, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_W25Q32JVSIM; ucUnprotectWRSR is not used here
    {0x9F, 0xEF, 0x70, 0x16, 0x90, 0xEF, 0x15, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_IS25LQ040B; ucUnprotectWRSR is not used here
    {0x9F, 0x9D, 0x40, 0x13, 0x90, 0x9D, 0x12, 0x00, 0x26, 0x24, 0x20, 0x02, 0x9C},
    // _FLASH_KH25L3236F; ucUnprotectWRSR is not used here
    {0x9F, 0xC2, 0x20, 0x16, 0x90, 0xC2, 0x15, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_W25Q16JVSIQ; ucUnprotectWRSR is not used here
    {0x9F, 0xEF, 0x40, 0x15, 0x90, 0xEF, 0x14, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_MX25V4035F; ucUnprotectWRSR is not used here
    {0x9F, 0xC2, 0x23, 0x13, 0x90, 0xC2, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_P25Q40H; ucUnprotectWRSR is not used here
    {0x9F, 0x85, 0x60, 0x13, 0x90, 0x85, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xBC},
    // _FLASH_FM25Q08; ucUnprotectWRSR is not used here
    {0x9F, 0xA1, 0x40, 0x14, 0x90, 0xA1, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_P25Q80H; ucUnprotectWRSR is not used here
    {0x9F, 0x85, 0x60, 0x14, 0x90, 0x85, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_P25Q16H; ucUnprotectWRSR is not used here
    {0x9F, 0x85, 0x60, 0x15, 0x90, 0x85, 0x14, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_BY25D40C; ucUnprotectWRSR is not used here
    {0x9F, 0x68, 0x40, 0x13, 0x90, 0x68, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_GD25VQ16C; ucUnprotectWRSR is not used here
    {0x9F, 0xC8, 0x42, 0x15, 0x90, 0xC8, 0x15, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_MD25D80DT; ucUnprotectWRSR is not used here
    {0x9F, 0x51, 0x40, 0x14, 0x90, 0x51, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_MD25D40DT; ucUnprotectWRSR is not used here
    {0x9F, 0x51, 0x40, 0x13, 0x90, 0x51, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_EN25QH16B; ucUnprotectWRSR is not used here
    {0x9F, 0x1C, 0x70, 0x15, 0x1C, 0x70, 0x14, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_IS25LP080D; ucUnprotectWRSR is not used here
    {0x9F, 0x9D, 0x60, 0x14, 0x90, 0x9D, 0x13, 0x00, 0x26, 0x24, 0x20, 0x02, 0xA0},
    // _FLASH_BY25D40ASTIG; ucUnprotectWRSR is not used here
    {0x9F, 0x68, 0x40, 0x13, 0x90, 0x68, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
    // _FLASH_BY25D16ASTIG; ucUnprotectWRSR is not used here
    {0x9F, 0x68, 0x40, 0x15, 0x90, 0x68, 0x14, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
    // _FLASH_BY25D80ASTIG; ucUnprotectWRSR is not used here
    {0x9F, 0x68, 0x40, 0x14, 0x90, 0x68, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
    // _FLASH_XM25QH80B; ucUnprotectWRSR is not used here
    {0x9F, 0x20, 0x40, 0x14, 0x90, 0x20, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
    // _FLASH_XM25QH40B; ucUnprotectWRSR is not used here
    {0x9F, 0x20, 0x40, 0x13, 0x90, 0x20, 0x12, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
    // _FLASH_XT25F08B; ucUnprotectWRSR is not used here
    {0x9F, 0x0B, 0x40, 0x14, 0x90, 0x0B, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
    // _FLASH_W25Q32JVSSIQ; ucUnprotectWRSR is not used here
    {0x9F, 0xEF, 0x40, 0x16, 0x90, 0xEF, 0x15, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_P25Q32H; ucUnprotectWRSR is not used here
    {0x9F, 0x85, 0x60, 0x16, 0x90, 0x85, 0x15, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_W25Q128JVSQ; ucUnprotectWRSR is not used here
    {0x9F, 0xEF, 0x40, 0x18, 0x90, 0xEF, 0x17, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_XM25QH16C; ucUnprotectWRSR is not used here
    {0x9F, 0x20, 0x40, 0x15, 0x90, 0x20, 0x14, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_BY25Q80BSTIG; ucUnprotectWRSR is not used here
    {0x9F, 0x68, 0x40, 0x14, 0x90, 0x68, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
    // _FLASH_XM25QH32CHIGT; ucUnprotectWRSR is not used here
    {0x9F, 0x20, 0x40, 0x16, 0x90, 0x20, 0x15, 0x00, 0x06, 0x04, 0x20, 0x02, 0xFC},
};
#else
StructFlashInformation __code tFlashInformation[] =
{
    {0x9F, 0xC2, 0x20, 0x14, 0x90, 0xC2, 0x13, 0x00, 0x06, 0x04, 0x20, 0x02, 0x9C},
};
#endif

//****************************************************************************
// VARIABLE DECLARATIONS
//****************************************************************************
#if(_AWTO_FLASH_ALL == _ON)
BYTE g_ucFlashType = _FLASH_UNDETECT;
#endif

//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
void ScalerFlashDetectFlashType(void);
bit ScalerFlashReadFlashIDCode(BYTE ucRDIDOPCode, BYTE *pucIDArry);

#if(_FLASH_WRITE_FUNCTION_SUPPORT == _ON)
void ScalerFlashWREN(BYTE ucBank, BYTE ucPage);
void ScalerFlashWRDis(void);
#endif

void ScalerFlashSetWREN(BYTE ucOpCode);
void ScalerFlashSetWRSR(BYTE ucWRSR, bit bIsSST);
void ScalerFlashSet2ByteWRSR(BYTE ucWRSR1, BYTE ucWRSR2, bit bIsSST);
void ScalerFlashSet2ByteWRSRonebyone(BYTE ucWRSR1, BYTE ucWRSR2, bit bIsSST);

#if(_FLASH_WRITE_FUNCTION_SUPPORT == _ON)
void ScalerFlashSet2ndWRSR(BYTE ucWRSR, bit bIsSST);
void ScalerFlashSet3rdWRSR(BYTE ucWRSR, bit bIsSST);
void ScalerFlashSet4thWRSR(BYTE ucWRSR, bit bIsSST);
bit ScalerFlashErasePage(BYTE ucBank, BYTE ucPage);
#endif

BYTE ScalerFlashReadSR(BYTE ucOpCode);

#if(_FLASH_WR_PROTECT == _ON)
void ScalerFlashWRProtect(void);
#endif

//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  : Auto detect current flash type
// Input Value  : None
// Output Value : Detected flash type index
//--------------------------------------------------
#if(_AWTO_FLASH_ALL == _ON)
void ScalerFlashDetectFlashType(void)
{
    BYTE ucIndex = 0;
    BYTE ucIDCheck1PassFlashCount = 0;
    BYTE pucIDArry[3];
    BYTE pucFlashType[8];

    memset(pucIDArry, 0, sizeof(pucIDArry));
    memset(pucFlashType, 0, sizeof(pucFlashType));

    // ID check 1, use 0x9F/0x90/0xAB op __code base on flash spec
    for(ucIndex = 0; ucIndex < _FLASH_TOTAL_COUNT; ucIndex++)
    {
        if(ScalerFlashReadFlashIDCode(tFlashInformation[ucIndex].ucIDCheck1OpCode, pucIDArry) == _TRUE)
        {
            // ID = 0 means ignore
            if((tFlashInformation[ucIndex].ucIDCheck1_ID0 == 0x00) || (pucIDArry[0] == tFlashInformation[ucIndex].ucIDCheck1_ID0))
            {
                if((tFlashInformation[ucIndex].ucIDCheck1_ID1 == 0x00) || (pucIDArry[1] == tFlashInformation[ucIndex].ucIDCheck1_ID1))
                {
                    if((tFlashInformation[ucIndex].ucIDCheck1_ID2 == 0x00) || (pucIDArry[2] == tFlashInformation[ucIndex].ucIDCheck1_ID2))
                    {
                        // Save matched flash type index to buffer
                        pucFlashType[ucIDCheck1PassFlashCount] = ucIndex;
                        ucIDCheck1PassFlashCount++;
                    }
                }
            }
        }
        else
        {
            // Read ID __code failed
            g_ucFlashType = _FLASH_DEFAULT_TYPE;
            return;
        }
    }

    // Find only one matched flash type in ID check 1
    if(ucIDCheck1PassFlashCount == 1)
    {
        g_ucFlashType = pucFlashType[0];
        return;
    }
    // Find more than one flash type in ID check 1
    else if(ucIDCheck1PassFlashCount > 1)
    {
        // Find more than 1 types in ID check 1, use ID check 2 to choose
        for(ucIndex = 0; ucIndex < ucIDCheck1PassFlashCount; ucIndex++)
        {
            // ID check 2
            if(ScalerFlashReadFlashIDCode(tFlashInformation[pucFlashType[ucIndex]].ucIDCheck2OpCode, pucIDArry) == _TRUE)
            {
                // ID = 0 means ignore
                if((tFlashInformation[pucFlashType[ucIndex]].ucIDCheck2_ID0 != 0x00) && (pucIDArry[0] != tFlashInformation[pucFlashType[ucIndex]].ucIDCheck2_ID0))
                {
                    continue;
                }

                if((tFlashInformation[pucFlashType[ucIndex]].ucIDCheck2_ID1 != 0x00) && (pucIDArry[1] != tFlashInformation[pucFlashType[ucIndex]].ucIDCheck2_ID1))
                {
                    continue;
                }

                if((tFlashInformation[pucFlashType[ucIndex]].ucIDCheck2_ID2 != 0x00) && (pucIDArry[2] != tFlashInformation[pucFlashType[ucIndex]].ucIDCheck2_ID2))
                {
                    continue;
                }

                break;
            }
        }

        if(ucIndex >= ucIDCheck1PassFlashCount)
        {
            g_ucFlashType = pucFlashType[0];
            return;
        }
        else
        {
            g_ucFlashType = pucFlashType[ucIndex];

#if(_FLASH_TYPE_W25X20A_OR_W25X21CL == _FLASH_W25X20A)
            if(g_ucFlashType == _FLASH_W25X21CL)
            {
                g_ucFlashType = _FLASH_W25X20A;
            }
#else
            if(g_ucFlashType == _FLASH_W25X20A)
            {
                g_ucFlashType = _FLASH_W25X21CL;
            }
#endif

#if(_FLASH_TYPE_W25X40CL_OR_W25X41CL == _FLASH_W25X40CL)
            if(g_ucFlashType == _FLASH_W25X41CL)
            {
                g_ucFlashType = _FLASH_W25X40CL;
            }
#else
            if(g_ucFlashType == _FLASH_W25X40CL)
            {
                g_ucFlashType = _FLASH_W25X41CL;
            }
#endif

#if(_FLASH_TYPE_GD25Q16C_OR_GD25Q16 == _FLASH_GD25Q16C)
            if(g_ucFlashType == _FLASH_GD25Q16)
            {
                g_ucFlashType = _FLASH_GD25Q16C;
            }
#else
            if(g_ucFlashType == _FLASH_GD25Q16C)
            {
                g_ucFlashType = _FLASH_GD25Q16;
            }
#endif

#if(_FLASH_TYPE_W25Q16DV_OR_W25Q16JVSIQ == _FLASH_W25Q16JVSIQ)
            if(g_ucFlashType == _FLASH_W25Q16DV)
            {
                g_ucFlashType = _FLASH_W25Q16JVSIQ;
            }
#else
            if(g_ucFlashType == _FLASH_W25Q16JVSIQ)
            {
                g_ucFlashType = _FLASH_W25Q16DV;
            }
#endif

#if(_FLASH_TYPE_MX25L3206E_OR_MX25L3233F_OR_KH25L3236F == _FLASH_KH25L3236F)
            if(g_ucFlashType == _FLASH_MX25L3206E)
            {
                g_ucFlashType = _FLASH_KH25L3236F;
            }
            if(g_ucFlashType == _FLASH_MX25L3233F)
            {
                g_ucFlashType = _FLASH_KH25L3236F;
            }
#elif(_FLASH_TYPE_MX25L3206E_OR_MX25L3233F_OR_KH25L3236F == _FLASH_MX25L3233F)
            if(g_ucFlashType == _FLASH_MX25L3206E)
            {
                g_ucFlashType = _FLASH_MX25L3233F;
            }
            if(g_ucFlashType == _FLASH_KH25L3236F)
            {
                g_ucFlashType = _FLASH_MX25L3233F;
            }
#else
            if(g_ucFlashType == _FLASH_KH25L3236F)
            {
                g_ucFlashType = _FLASH_MX25L3206E;
            }
            if(g_ucFlashType == _FLASH_MX25L3233F)
            {
                g_ucFlashType = _FLASH_MX25L3206E;
            }
#endif

#if(_FLASH_TYPE_GD25Q40B_OR_GD25Q41B == _FLASH_GD25Q41B)
            if(g_ucFlashType == _FLASH_GD25Q40B)
            {
                g_ucFlashType = _FLASH_GD25Q41B;
            }
#else
            if(g_ucFlashType == _FLASH_GD25Q41B)
            {
                g_ucFlashType = _FLASH_GD25Q40B;
            }
#endif

#if(_FLASH_TYPE_FM25Q08_OR_FM25Q08A == _FLASH_FM25Q08)
            if(g_ucFlashType == _FLASH_FM25Q08A)
            {
                g_ucFlashType = _FLASH_FM25Q08;
            }
#else
            if(g_ucFlashType == _FLASH_FM25Q08)
            {
                g_ucFlashType = _FLASH_FM25Q08A;
            }
#endif

#if(_FLASH_TYPE_BY25D40C_OR_BY25D40ASTIG == _FLASH_BY25D40C)
            if(g_ucFlashType == _FLASH_BY25D40ASTIG)
            {
                g_ucFlashType = _FLASH_BY25D40C;
            }
#else
            if(g_ucFlashType == _FLASH_BY25D40C)
            {
                g_ucFlashType = _FLASH_BY25D40ASTIG;
            }
#endif

#if(_FLASH_TYPE_W25Q32F_OR_W25Q32JVSSIQ == _FLASH_W25Q32JVSSIQ)
            if(g_ucFlashType == _FLASH_W25Q32F)
            {
                g_ucFlashType = _FLASH_W25Q32JVSSIQ;
            }
#else
            if(g_ucFlashType == _FLASH_W25Q32JVSSIQ)
            {
                g_ucFlashType = _FLASH_W25Q32F;
            }
#endif

#if(_FLASH_TYPE_BY25D80ASTIG_OR_BY25Q80BSTIG == _FLASH_BY25Q80BSTIG)
            if(g_ucFlashType == _FLASH_BY25D80ASTIG)
            {
                g_ucFlashType = _FLASH_BY25Q80BSTIG;
            }
#else
            if(g_ucFlashType == _FLASH_BY25Q80BSTIG)
            {
                g_ucFlashType = _FLASH_BY25D80ASTIG;
            }
#endif

            return;
        }
    }
    else
    {
        // Do not find 1 type in ID check 1
        g_ucFlashType = _FLASH_DEFAULT_TYPE;
        return;
    }

    g_ucFlashType = _FLASH_DEFAULT_TYPE;
}
#endif

//--------------------------------------------------
// Description  : Read flash ID code
// Input Value  : ucRDIDOPCode: Read ID __code op code
//                pucIDArry: Saved the ID __code read from flash
// Output Value : _TRUE for read success, else return _FALSE
//--------------------------------------------------
bit ScalerFlashReadFlashIDCode(BYTE ucRDIDOPCode, BYTE *pucIDArry)
{
    BYTE ucIndex = 0;
    BYTE ucTryCount = 10;
    BYTE ucID0 = 0;
    BYTE ucID1 = 0;
    BYTE ucID2 = 0;

    switch(ucRDIDOPCode)
    {
        case 0x9F:

            //////////////////////////////////////////////////////////////////////////
            // Use JEDECID Instruction to get Flash Manufacture ID, Device ID       //
            //////////////////////////////////////////////////////////////////////////
            MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x46, _CKCON_MCU_SLOW_CYCLE);
            MCU_FF61_COMMON_OP_CODE = ucRDIDOPCode;
            MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x47, _CKCON_MCU_SLOW_CYCLE);
            pucIDArry[0] = MCU_FF67_COMMON_INST_READ_PORT0;
            pucIDArry[1] = MCU_FF68_COMMON_INST_READ_PORT1;
            pucIDArry[2] = MCU_FF69_COMMON_INST_READ_PORT2;

            // Repeatedly read flash ID __code and check flash ID __code __data between twice RDID instructions
            for(ucIndex = 0; ucIndex < ucTryCount; ucIndex++)
            {
                MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x46, _CKCON_MCU_SLOW_CYCLE);
                MCU_FF61_COMMON_OP_CODE = ucRDIDOPCode;
                MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x47, _CKCON_MCU_SLOW_CYCLE);
                ucID0 = MCU_FF67_COMMON_INST_READ_PORT0;
                ucID1 = MCU_FF68_COMMON_INST_READ_PORT1;
                ucID2 = MCU_FF69_COMMON_INST_READ_PORT2;

                if((pucIDArry[0] == ucID0) && (pucIDArry[1] == ucID1) && (pucIDArry[2] == ucID2))
                {
                    break;
                }
                else
                {
                    pucIDArry[0] = ucID0;
                    pucIDArry[1] = ucID1;
                    pucIDArry[2] = ucID2;
                }
            }

            if(ucIndex >= ucTryCount)
            {
                return _FALSE;
            }

            break;

        case 0x90:
        case 0xAB:

            //////////////////////////////////////////////////////////////////////////////////
            // Use RDID(0x90/0xAB) Instruction first to get Flash Manufacture ID, Device ID //
            //////////////////////////////////////////////////////////////////////////////////
            MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x5E, _CKCON_MCU_SLOW_CYCLE);
            MCU_FF61_COMMON_OP_CODE = ucRDIDOPCode;
            MCU_FF64_FLASH_PROG_ISP0 = 0x00;
            MCU_FF65_FLASH_PROG_ISP1 = 0x00;
            MCU_FF66_FLASH_PROG_ISP2 = 0x00;
            MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x5F, _CKCON_MCU_SLOW_CYCLE);

            pucIDArry[0] = MCU_FF67_COMMON_INST_READ_PORT0;
            pucIDArry[1] = MCU_FF68_COMMON_INST_READ_PORT1;
            pucIDArry[2] = MCU_FF69_COMMON_INST_READ_PORT2;

            for(ucIndex = 0; ucIndex < ucTryCount; ucIndex++)
            {
                MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x5E, _CKCON_MCU_SLOW_CYCLE);
                MCU_FF61_COMMON_OP_CODE = ucRDIDOPCode;
                MCU_FF64_FLASH_PROG_ISP0 = 0x00;
                MCU_FF65_FLASH_PROG_ISP1 = 0x00;
                MCU_FF66_FLASH_PROG_ISP2 = 0x00;
                MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x5F, _CKCON_MCU_SLOW_CYCLE);

                ucID0 = MCU_FF67_COMMON_INST_READ_PORT0;
                ucID1 = MCU_FF68_COMMON_INST_READ_PORT1;
                ucID2 = MCU_FF69_COMMON_INST_READ_PORT2;

                if((pucIDArry[0] == ucID0) && (pucIDArry[1] == ucID1) && (pucIDArry[2] == ucID2))
                {
                    break;
                }
                else
                {
                    pucIDArry[0] = ucID0;
                    pucIDArry[1] = ucID1;
                    pucIDArry[2] = ucID2;
                }
            }

            if(ucIndex >= ucTryCount)
            {
                return _FALSE;
            }

            break;

        default:
            break;
    }

    return _TRUE;
}


#if(_FLASH_WRITE_FUNCTION_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Write enable process for serial flash
// Input Value  : ucBank: bank index
//                ucPage: page index (0 ~ 15)
// Output Value : Return _TURE if succeed, else return _FALSE
//--------------------------------------------------
#include "ScalerCommonNVRamWren_gen.inc"

//--------------------------------------------------
// Description  : Write disable process for serial flash
// Input Value  : None
// Output Value : Return _TURE if succeed, else return _FALSE
//--------------------------------------------------
void ScalerFlashWRDis(void)
{
    // Clear watch dog
    AWTO_WDT_FEED(AWTO_WDT_S_WRDIS);

    switch(g_ucFlashType)
    {
        case _FLASH_PM25LV020:
        case _FLASH_PM25LD020:
        case _FLASH_PM25LQ020A:
        case _FLASH_PM25LQ040:
        case _FLASH_PM25LQ080:
        case _FLASH_PM25LQ016:
        case _FLASH_IS25LQ040B:
        case _FLASH_IS25LP080D:

            // Sector Unprotect Disable
            ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            break;

        case _FLASH_W25X20A:
        case _FLASH_MX25L2026:
        case _FLASH_EN25F20:
        case _FLASH_MX25L2025:
        case _FLASH_MX25L4006E:
        case _FLASH_W25X21CL:
        case _FLASH_W25X41CL:
        case _FLASH_FM25F04:
        case _FLASH_N25S40:
        case _FLASH_A25L040:
        case _FLASH_W25Q80BV:
        case _FLASH_MX25L4026D:
        case _FLASH_W25X40CL:
        case _FLASH_EN25F20A:
        case _FLASH_EN25F40A:
        case _FLASH_EN25Q40A:
        case _FLASH_EN25Q80:
        case _FLASH_GD25Q80B:
        case _FLASH_MX25L8006E:
        case _FLASH_GD25Q40B:
        case _FLASH_MX25L1606E:
        case _FLASH_MX25L3206E:
        case _FLASH_A25L016:
        case _FLASH_W25Q16DV:
        case _FLASH_A25L032:
        case _FLASH_GD25Q16:
        case _FLASH_MX25L1633E:
        case _FLASH_GD25Q16C:
        case _FLASH_MX25L3233F:
        case _FLASH_EN25QH32A:
        case _FLASH_MX25V1635F:
        case _FLASH_AT25SF041:
        case _FLASH_MX25L6433F:
        case _FLASH_MX25V8035F:
        case _FLASH_AT25SF321:
        case _FLASH_KH25L3236F:
        case _FLASH_MX25V4035F:
        case _FLASH_P25Q40H:
        case _FLASH_P25Q80H:
        case _FLASH_P25Q16H:
        case _FLASH_BY25D40C:
        case _FLASH_GD25VQ16C:
        case _FLASH_MD25D80DT:
        case _FLASH_MD25D40DT:
        case _FLASH_EN25QH16B:
        case _FLASH_BY25D40ASTIG:
        case _FLASH_BY25D16ASTIG:
        case _FLASH_BY25D80ASTIG:
        case _FLASH_XM25QH80B:
        case _FLASH_XM25QH40B:

            ScalerFlashSetWRSR(tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR, _FALSE);
            ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            break;

        case _FLASH_SST25LF020A:

            ScalerFlashSetWRSR(tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR, _TRUE);
            ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            break;

        case _FLASH_GD25M21B:
        case _FLASH_GD25M41B:

            // Sector Unlock Disable
            MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x20, _CKCON_MCU_SLOW_CYCLE);
            MCU_FF61_COMMON_OP_CODE = 0x4D;
            MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x21, _CKCON_MCU_SLOW_CYCLE);

            ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            break;

        case _FLASH_W25Q32F:
        case _FLASH_GD25Q41B:
        case _FLASH_FM25Q08A:
        case _FLASH_FM25Q08:

            ScalerFlashSet2ByteWRSR(tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR, 0x00, _FALSE);
            ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            break;

        case _FLASH_GD25Q32C:

            ScalerFlashSet2ByteWRSRonebyone(tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR, 0x00, _FALSE);
            ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            break;

        case _FLASH_XT25F08B:
        case _FLASH_XM25QH16C:
        case _FLASH_BY25Q80BSTIG:
        case _FLASH_XM25QH32CHIGT:

            ScalerFlashSet2ByteWRSR(tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR, 0x00, _WRITE_SR_MODE_SEL);
            ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            break;

        case _FLASH_FM25Q04:
            // Global Block Lock
            MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x60, _CKCON_MCU_SLOW_CYCLE);
            MCU_FF61_COMMON_OP_CODE = 0x7E;
            MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x61, _CKCON_MCU_SLOW_CYCLE);
            //// Set PTB/PD for sector protect
            ScalerFlashSet4thWRSR(0xFF, _FALSE);
            ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            break;

        case _FLASH_W25Q16JVSIM:
        case _FLASH_W25Q32JVSIM:
        case _FLASH_W25Q16JVSIQ:
        case _FLASH_W25Q32JVSSIQ:
        case _FLASH_P25Q32H:
        case _FLASH_W25Q128JVSQ:

            // Global Block Lock
            MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x60, _CKCON_MCU_SLOW_CYCLE);
            MCU_FF61_COMMON_OP_CODE = 0x7E;
            MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x61, _CKCON_MCU_SLOW_CYCLE);

            ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            break;
        default:

            ScalerFlashSetWRSR(0xFF, _FALSE);
            ScalerFlashSetWREN(0x04);
            break;
    }

    // Disable Program OP __code
    MCU_FF6D_PROGRAM_OP_CODE = 0xFF;

    // Disable Command OP __code
    MCU_FF61_COMMON_OP_CODE = 0xFF;
}
#endif // End of #if(_FLASH_WRITE_FUNCTION_SUPPORT == _ON)

//--------------------------------------------------
// Description  : WREN instructions for serial flash
// Input Value  : ucOpCode: WREN instruction op code
// Output Value : None
//--------------------------------------------------
void ScalerFlashSetWREN(BYTE ucOpCode)
{
    // WREN instructions
    MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x20, _CKCON_MCU_SLOW_CYCLE);
    MCU_FF61_COMMON_OP_CODE = ucOpCode;
    MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x21, _CKCON_MCU_SLOW_CYCLE);

    // No need to polling, 8051 will halt when common instruction executes
}

//--------------------------------------------------
// Description  : WRSR instructions for Serial Flash
// Input Value  : ucWRSR: value written to Flash Status Reg
//                ucIsSST: _TRUE for SST Flash, _FALSE for other flash
// Output Value : None
//--------------------------------------------------
void ScalerFlashSetWRSR(BYTE ucWRSR, bit bIsSST)
{
    PCB_FLASH_WRITE_PROTECT(_FLASH_WRITE_PROTECT_DISABLE);

    // WRSR
    if(bIsSST == _TRUE)
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x88, _CKCON_MCU_SLOW_CYCLE);
    }
    else
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x68, _CKCON_MCU_SLOW_CYCLE);
    }

    MCU_FF61_COMMON_OP_CODE = 0x01;
    MCU_FF64_FLASH_PROG_ISP0 = ucWRSR;
    MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, (MCU_FF60_COMMON_INST_EN | _BIT0), _CKCON_MCU_SLOW_CYCLE);

    // No need to polling, 8051 will halt when common instruction executes

    // Disable Command OP __code
    MCU_FF61_COMMON_OP_CODE = 0xFF;

    PCB_FLASH_WRITE_PROTECT(_FLASH_WRITE_PROTECT_ENABLE);
}

//--------------------------------------------------
// Description  : WRSR instructions for Serial Flash
// Input Value  : ucWRSR1: value written to Flash Status Register-1
//              : ucWRSR2: value written to Flash Status Register-2
//                ucIsSST: _TRUE for SST Flash, _FALSE for other flash
// Output Value : None
//--------------------------------------------------
void ScalerFlashSet2ByteWRSR(BYTE ucWRSR1, BYTE ucWRSR2, bit bIsSST)
{
    PCB_FLASH_WRITE_PROTECT(_FLASH_WRITE_PROTECT_DISABLE);

    // WRSR
    if(bIsSST == _TRUE)
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x90, _CKCON_MCU_SLOW_CYCLE);
    }
    else
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x70, _CKCON_MCU_SLOW_CYCLE);
    }

    MCU_FF61_COMMON_OP_CODE = 0x01;
    MCU_FF64_FLASH_PROG_ISP0 = ucWRSR1;
    MCU_FF65_FLASH_PROG_ISP1 = ucWRSR2;
    MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, (MCU_FF60_COMMON_INST_EN | _BIT0), _CKCON_MCU_SLOW_CYCLE);

    // No need to polling, 8051 will halt when common instruction executes

    // Disable Command OP __code
    MCU_FF61_COMMON_OP_CODE = 0xFF;

    PCB_FLASH_WRITE_PROTECT(_FLASH_WRITE_PROTECT_ENABLE);
}

//--------------------------------------------------
// Description  : WRSR instructions on two SR one by one for Serial Flash
// Input Value  : ucWRSR1: value written to Flash Status Register-1
//              : ucWRSR2: value written to Flash Status Register-2
//                ucIsSST: _TRUE for SST Flash, _FALSE for other flash
// Output Value : None
//--------------------------------------------------
void ScalerFlashSet2ByteWRSRonebyone(BYTE ucWRSR1, BYTE ucWRSR2, bit bIsSST)
{
    PCB_FLASH_WRITE_PROTECT(_FLASH_WRITE_PROTECT_DISABLE);

    // WRSR
    if(bIsSST == _TRUE)
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x88, _CKCON_MCU_SLOW_CYCLE);
    }
    else
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x68, _CKCON_MCU_SLOW_CYCLE);
    }

    MCU_FF61_COMMON_OP_CODE = 0x01;
    MCU_FF64_FLASH_PROG_ISP0 = ucWRSR1;
    MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, (MCU_FF60_COMMON_INST_EN | _BIT0), _CKCON_MCU_SLOW_CYCLE);

    // No need to polling, 8051 will halt when common instruction executes

    if(bIsSST == _TRUE)
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x88, _CKCON_MCU_SLOW_CYCLE);
    }
    else
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x68, _CKCON_MCU_SLOW_CYCLE);
    }

    MCU_FF61_COMMON_OP_CODE = 0x31;
    MCU_FF64_FLASH_PROG_ISP0 = ucWRSR2;
    MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, (MCU_FF60_COMMON_INST_EN | _BIT0), _CKCON_MCU_SLOW_CYCLE);

    // No need to polling, 8051 will halt when common instruction executes

    // Disable Command OP __code
    MCU_FF61_COMMON_OP_CODE = 0xFF;

    PCB_FLASH_WRITE_PROTECT(_FLASH_WRITE_PROTECT_ENABLE);
}

#if(_FLASH_WRITE_FUNCTION_SUPPORT == _ON)
//--------------------------------------------------
// Description  : WRSR instructions of Status Register-2 for Serial Flash
// Input Value  : ucWRSR: value written to Flash Status Reg
//                ucIsSST: _TRUE for SST Flash, _FALSE for other flash
// Output Value : None
//--------------------------------------------------
void ScalerFlashSet2ndWRSR(BYTE ucWRSR, bit bIsSST)
{
    PCB_FLASH_WRITE_PROTECT(_FLASH_WRITE_PROTECT_DISABLE);

    // WRSR
    if(bIsSST == _TRUE)
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x88, _CKCON_MCU_SLOW_CYCLE);
    }
    else
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x68, _CKCON_MCU_SLOW_CYCLE);
    }

    MCU_FF61_COMMON_OP_CODE = 0x31;
    MCU_FF64_FLASH_PROG_ISP0 = ucWRSR;
    MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, (MCU_FF60_COMMON_INST_EN | _BIT0), _CKCON_MCU_SLOW_CYCLE);

    // No need to polling, 8051 will halt when common instruction executes

    // Disable Command OP __code
    MCU_FF61_COMMON_OP_CODE = 0xFF;

    PCB_FLASH_WRITE_PROTECT(_FLASH_WRITE_PROTECT_ENABLE);
}

//--------------------------------------------------
// Description  : WRSR instructions of Status Register-3 for Serial Flash
// Input Value  : ucWRSR: value written to Flash Status Reg
//                ucIsSST: _TRUE for SST Flash, _FALSE for other flash
// Output Value : None
//--------------------------------------------------
void ScalerFlashSet3rdWRSR(BYTE ucWRSR, bit bIsSST)
{
    PCB_FLASH_WRITE_PROTECT(_FLASH_WRITE_PROTECT_DISABLE);

    // WRSR
    if(bIsSST == _TRUE)
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x88, _CKCON_MCU_SLOW_CYCLE);
    }
    else
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x68, _CKCON_MCU_SLOW_CYCLE);
    }

    MCU_FF61_COMMON_OP_CODE = 0x11;
    MCU_FF64_FLASH_PROG_ISP0 = ucWRSR;
    MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, (MCU_FF60_COMMON_INST_EN | _BIT0), _CKCON_MCU_SLOW_CYCLE);

    // No need to polling, 8051 will halt when common instruction executes

    // Disable Command OP __code
    MCU_FF61_COMMON_OP_CODE = 0xFF;

    PCB_FLASH_WRITE_PROTECT(_FLASH_WRITE_PROTECT_ENABLE);
}

//--------------------------------------------------
// Description  : WRSR instructions of Status Register-4 for Serial Flash
// Input Value  : ucWRSR: value written to Flash Status Reg
//                ucIsSST: _TRUE for SST Flash, _FALSE for other flash
// Output Value : None
//--------------------------------------------------
void ScalerFlashSet4thWRSR(BYTE ucWRSR, bit bIsSST)
{
    PCB_FLASH_WRITE_PROTECT(_FLASH_WRITE_PROTECT_DISABLE);

    // WRSR
    if(bIsSST == _TRUE)
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x88, _CKCON_MCU_SLOW_CYCLE);
    }
    else
    {
        MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x68, _CKCON_MCU_SLOW_CYCLE);
    }

    MCU_FF61_COMMON_OP_CODE = 0x41;
    MCU_FF64_FLASH_PROG_ISP0 = ucWRSR;
    MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, (MCU_FF60_COMMON_INST_EN | _BIT0), _CKCON_MCU_SLOW_CYCLE);

    // No need to polling, 8051 will halt when common instruction executes

    // Disable Command OP __code
    MCU_FF61_COMMON_OP_CODE = 0xFF;

    PCB_FLASH_WRITE_PROTECT(_FLASH_WRITE_PROTECT_ENABLE);
}

//--------------------------------------------------
// Description  : Erase page
// Input Value  : ucBank: bank index
//                ucPage: page index (0 ~ 15)
// Output Value : _TRUE for erase success and _FALSE for erase fail
//--------------------------------------------------
bit ScalerFlashErasePage(BYTE ucBank, BYTE ucPage)
{
    // The access bank is smaller than than the start bank
    if(ucBank < MCU_FFFD_XDATA_BANK_START)
    {
        return _FALSE;
    }

    // Flash commands (ID, WREN, WRSR, SE, WRDis) run at the in-spec flash clock
    AwtoFlashWrBegin();

    if(g_ucFlashType == _FLASH_UNDETECT)
    {
        ScalerFlashDetectFlashType();
    }

    ScalerFlashWREN(ucBank, ucPage); AWTO_NV_EV(3);

    // Sector Erase
    MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0xB8, _CKCON_MCU_SLOW_CYCLE);
    MCU_FF61_COMMON_OP_CODE = tFlashInformation[_AWTO_FLASH_IDX].ucPageEraseOpCode;
    // Set WR address
    MCU_FF64_FLASH_PROG_ISP0 = ucBank;
    MCU_FF65_FLASH_PROG_ISP1 = (BYTE)((ucPage << 4) & 0xF0);
    MCU_FF66_FLASH_PROG_ISP2 = 0x00;
    // Start Bit0
    MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0xB9, _CKCON_MCU_SLOW_CYCLE);

    // No need to polling, 8051 will halt when common instruction executes

    MCU_FF61_COMMON_OP_CODE = 0xFF; AWTO_NV_EV(4);

    ScalerFlashWRDis();

    AwtoFlashWrEnd();

    return _TRUE;
}
#endif // End of #if(_FLASH_WRITE_FUNCTION_SUPPORT ==_ON)

//--------------------------------------------------
// Description  : RDSR instructions for serial flash
// Input Value  : ucOpCode: RDSR instruction op code
// Output Value : Current SR Value
//--------------------------------------------------
BYTE ScalerFlashReadSR(BYTE ucOpCode)
{
    BYTE ucRDSR = 0;

    // Read SR
    MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x42, _CKCON_MCU_SLOW_CYCLE);
    MCU_FF61_COMMON_OP_CODE = ucOpCode;
    MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x43, _CKCON_MCU_SLOW_CYCLE);
    ucRDSR = MCU_FF67_COMMON_INST_READ_PORT0;
    return ucRDSR;
}

#if(_FLASH_WR_PROTECT == _ON)
//--------------------------------------------------
// Description  : Set SR to protect flash
// Input Value  : None
// Output Value : Return _TURE if succeed, else return _FALSE
//--------------------------------------------------
void ScalerFlashWRProtect(void)
{
    BYTE ucRDSR = 0;

    // Clear watch dog
    AWTO_WDT_FEED(AWTO_WDT_S_WRPROT);

    // Detect flash type first
    if(g_ucFlashType == _FLASH_UNDETECT)
    {
        ScalerFlashDetectFlashType();
    }

    switch(g_ucFlashType)
    {
        case _FLASH_PM25LV020:
        case _FLASH_PM25LD020:
        case _FLASH_PM25LQ020A:
        case _FLASH_PM25LQ040:
        case _FLASH_PM25LQ080:
        case _FLASH_W25X20A:
        case _FLASH_MX25L2026:
        case _FLASH_EN25F20:
        case _FLASH_MX25L2025:
        case _FLASH_MX25L4006E:
        case _FLASH_W25X21CL:
        case _FLASH_W25X41CL:
        case _FLASH_FM25F04:
        case _FLASH_N25S40:
        case _FLASH_A25L040:
        case _FLASH_W25Q80BV:
        case _FLASH_MX25L4026D:
        case _FLASH_W25X40CL:
        case _FLASH_EN25F20A:
        case _FLASH_EN25F40A:
        case _FLASH_EN25Q40A:
        case _FLASH_EN25Q80:
        case _FLASH_GD25Q80B:
        case _FLASH_MX25L8006E:
        case _FLASH_GD25Q40B:
        case _FLASH_MX25L1606E:
        case _FLASH_MX25L3206E:
        case _FLASH_A25L016:
        case _FLASH_W25Q16DV:
        case _FLASH_A25L032:
        case _FLASH_GD25Q16:
        case _FLASH_MX25L1633E:
        case _FLASH_GD25Q16C:
        case _FLASH_MX25L3233F:
        case _FLASH_EN25QH32A:
        case _FLASH_MX25V1635F:
        case _FLASH_AT25SF041:
        case _FLASH_MX25L6433F:
        case _FLASH_PM25LQ016:
        case _FLASH_MX25V8035F:
        case _FLASH_AT25SF321:
        case _FLASH_IS25LQ040B:
        case _FLASH_KH25L3236F:
        case _FLASH_MX25V4035F:
        case _FLASH_P25Q40H:
        case _FLASH_P25Q80H:
        case _FLASH_P25Q16H:
        case _FLASH_BY25D40C:
        case _FLASH_GD25VQ16C:
        case _FLASH_MD25D80DT:
        case _FLASH_MD25D40DT:
        case _FLASH_EN25QH16B:
        case _FLASH_IS25LP080D:
        case _FLASH_BY25D40ASTIG:
        case _FLASH_BY25D16ASTIG:
        case _FLASH_BY25D80ASTIG:
        case _FLASH_XM25QH80B:
        case _FLASH_XM25QH40B:

            // Read SR
            ucRDSR = ScalerFlashReadSR(_RDSR_OPCODE);

            if(ucRDSR != tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR)
            {
                ScalerFlashSetWRSR(tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR, _FALSE);
                ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            }
            break;

        case _FLASH_SST25LF020A:

            // Read SR
            ucRDSR = ScalerFlashReadSR(_RDSR_OPCODE);

            if(ucRDSR != tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR)
            {
                ScalerFlashSetWRSR(tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR, _TRUE);
                ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            }
            break;

        case _FLASH_GD25M21B:
        case _FLASH_GD25M41B:

            // Read SR
            ucRDSR = ScalerFlashReadSR(_RDSR_OPCODE);

            if(ucRDSR != tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR)
            {
                // Sector Unlock Disable
                MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x20, _CKCON_MCU_SLOW_CYCLE);
                MCU_FF61_COMMON_OP_CODE = 0x4D;
                MCU_SET_BYTE_WITH_CKCON(MCU_FF60_COMMON_INST_EN, 0x21, _CKCON_MCU_SLOW_CYCLE);
                ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            }
            break;

        case _FLASH_W25Q32F:
        case _FLASH_GD25Q41B:
        case _FLASH_FM25Q08A:
        case _FLASH_FM25Q04:
        case _FLASH_W25Q16JVSIM:
        case _FLASH_W25Q32JVSIM:
        case _FLASH_W25Q16JVSIQ:
        case _FLASH_FM25Q08:
        case _FLASH_XT25F08B:
        case _FLASH_W25Q32JVSSIQ:
        case _FLASH_P25Q32H:
        case _FLASH_BY25Q80BSTIG:

            // Read SR
            ucRDSR = ScalerFlashReadSR(_RDSR_OPCODE);

            if(ucRDSR != tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR)
            {
                ScalerFlashSet2ByteWRSR(tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR, 0x00, _FALSE);
                ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            }
            break;

        case _FLASH_GD25Q32C:

            // Read SR
            ucRDSR = ScalerFlashReadSR(_RDSR_OPCODE);

            if(ucRDSR != tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR)
            {
                ScalerFlashSet2ByteWRSRonebyone(tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR, 0x00, _FALSE);
                ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            }
            break;

        case _FLASH_W25Q128JVSQ:

            // Read SR
            ucRDSR = ScalerFlashReadSR(_RDSR_OPCODE);

            if(ucRDSR != tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR)
            {
                ScalerFlashSet2ByteWRSR(tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR, 0x00, _WRITE_SR_MODE_SEL);
                ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            }
            break;

        case _FLASH_XM25QH16C:
        case _FLASH_XM25QH32CHIGT:

            // Read SR
            ucRDSR = ScalerFlashReadSR(_RDSR_OPCODE);

            if(ucRDSR != tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR)
            {
                ScalerFlashSet2ByteWRSR(tFlashInformation[_AWTO_FLASH_IDX].ucProtectWRSR, 0x00, _WRITE_SR_MODE_SEL);
                ScalerFlashSetWREN(tFlashInformation[_AWTO_FLASH_IDX].ucWRDisOpCode);
            }
            break;

        default:
            // Read SR
            ucRDSR = ScalerFlashReadSR(_RDSR_OPCODE);

            if(ucRDSR != 0xFF)
            {
                ScalerFlashSetWRSR(0xFF, _FALSE);
                ScalerFlashSetWREN(0x04);
            }
            break;
    }

    // Disable Program OP __code
    MCU_FF6D_PROGRAM_OP_CODE = 0xFF;

    // Disable Command OP __code
    MCU_FF61_COMMON_OP_CODE = 0xFF;
}

#endif // End of #if(_FLASH_WR_PROTECT ==_ON)
#endif // End of #if((_FLASH_WRITE_FUNCTION_SUPPORT == _ON) || (_FLASH_WR_PROTECT == _ON))
