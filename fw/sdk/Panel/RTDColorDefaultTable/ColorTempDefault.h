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
// ID Code      : ColorTempDefaultNo.0000
// Update Note  :
//
//----------------------------------------------------------------------------------------------------

//****************************************************************************
// COLOR TEMP DEFAULT DATA
//****************************************************************************
#if(_CTS_TYPE == _CTS_GEN_1_12BIT)
// Per-preset gains: scripts/colour_temp_gains.py
#include "ColorTempGains.h"
#define _CTUSER_RED                                (_CT_GAIN_UNITY)
#define _CTUSER_GREEN                              (_CT_GAIN_UNITY)
#define _CTUSER_BLUE                               (_CT_GAIN_UNITY)
#else
#define _CT9300_RED                                 0x7e
#define _CT9300_GREEN                               0x7e
#define _CT9300_BLUE                                0x7e
#define _CT7500_RED                                 0x7e
#define _CT7500_GREEN                               0x7e
#define _CT7500_BLUE                                0x7e
#define _CT6500_RED                                 0x7e
#define _CT6500_GREEN                               0x7e
#define _CT6500_BLUE                                0x7e
#define _CT5800_RED                                 0x7e
#define _CT5800_GREEN                               0x7e
#define _CT5800_BLUE                                0x7e
#define _CTSRGB_RED                                 0x7e
#define _CTSRGB_GREEN                               0x7e
#define _CTSRGB_BLUE                                0x7e
#define _CTUSER_RED                                 0x7e
#define _CTUSER_GREEN                               0x7e
#define _CTUSER_BLUE                                0x7e
#endif

