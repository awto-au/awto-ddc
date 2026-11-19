/********************************************************************************/
/*   The  Software  is  proprietary,  confidential,  and  valuable to Realtek   */
/*   Semiconductor  Corporation  ("Realtek").  All  rights, including but not   */
/*   limited  to  copyrights,  patents,  trademarks, trade secrets, mask work   */
/*   rights, and other similar rights and interests, are reserved to Realtek.   */
/*   Without  prior  written  consent  from  Realtek,  copying, reproduction,   */
/*   modification,  distribution,  or  otherwise  is strictly prohibited. The   */
/*   Software  shall  be  kept  strictly  in  confidence,  and  shall  not be   */
/*   disclosed to or otherwise accessed by any third party.                     */
/*   c<2003> - <2011>                                                           */
/*   The Software is provided "AS IS" without any warranty of any kind,         */
/*   express, implied, statutory or otherwise.                                  */
/********************************************************************************/

//----------------------------------------------------------------------------------------------------
// ID Code      : ScalerCommonRegInterface.h No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

//****************************************************************************
// INTERFACE DEFINITIONS / MACROS
//****************************************************************************
#if((_DEBUG_MESSAGE_SUPPORT == _ON) || (_FACTORY_DEBUG_SUPPORT == _ON))
#define AWTO_RB_FIRST_PAGE                          0x88
#define AWTO_RB_LAST_PAGE                           0xD0
#define AWTO_RB_PAGE(usAddr)                        ((BYTE)((WORD)(usAddr) >> 8))
#define AWTO_RB_IN(usAddr, ucFirst, ucLast)         (((BYTE)(AWTO_RB_PAGE(usAddr) - (ucFirst))) <= ((ucLast) - (ucFirst)))
#define AWTO_RB_LISTED(usAddr)                      (AWTO_RB_IN(usAddr, 0x88, 0x90) || AWTO_RB_IN(usAddr, 0xA0, 0xAF) || AWTO_RB_IN(usAddr, 0xC8, 0xD0)) // page clusters, exact list in AwtoRbPrime
#ifndef AWTO_RB_RAW
#define AWTO_RB_RAW 0 // -D AWTO_RB_RAW=1: reads stay raw (hardware A/B image)
#endif
#if(AWTO_RB_RAW != 0)
#define AWTO_RB_PRIME(usAddr)                       ((void)0)
#else
#define AWTO_RB_PRIME(usAddr)                       (AWTO_RB_LISTED(usAddr) ? AwtoRbPrime((WORD)(usAddr)) : (void)0)
#endif
extern void AwtoRbPrime(WORD usAddr);
extern volatile BYTE xdata isr_g_ucAwtoRbDirty;
#define ScalerSetBit(usAddr, ucAnd, ucOr)           (*((volatile BYTE xdata *)(usAddr)) = (*((volatile BYTE xdata *)(usAddr)) & (ucAnd)) | (ucOr))
#define ScalerGetBit(usAddr, ucAnd)                 (AWTO_RB_PRIME(usAddr), (*((volatile BYTE xdata *)(usAddr)) & (ucAnd)))
#define ScalerGetByte(usAddr)                       (AWTO_RB_PRIME(usAddr), (*((volatile BYTE xdata *)(usAddr))))
#define ScalerSetByte(usAddr, ucValue)              (*((volatile BYTE xdata *)(usAddr)) = (ucValue))
#endif

//****************************************************************************
// INTERFACE VARIABLE DECLARATIONS
//****************************************************************************


//****************************************************************************
// INTERFACE FUNCTIONS
//****************************************************************************

