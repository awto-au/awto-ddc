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
// ID Code      : RTD2014OsdWindow.c
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __RTD_OSDWINDOW__

#include "UserCommonInclude.h"

#if(_OSD_TYPE == _REALTEK_2014_OSD)

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
void OsdWindowDrawing(BYTE ucWindow, WORD usXStart, WORD usYStart, WORD usXEnd, WORD usYEnd, BYTE ucColor);

//***************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  :
// Input Value  :
// Output Value :
//--------------------------------------------------
void OsdWindowDrawing(BYTE ucWindow, WORD usXStart, WORD usYStart, WORD usXEnd, WORD usYEnd, BYTE ucColor)
{
#if(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_SOFTWARE)
    WORD xdata usTemp = 0;
    WORD xdata usTemp1 = 0;
    WORD xdata usTemp2 = 0;
    usTemp  = usXEnd - usXStart;
    usTemp1 = usYEnd - usYStart;
    usTemp2 = usXStart;

    if(GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_90)
    {
        usXEnd = (g_ucOsdWidth * 18 - usYStart);
        usXStart = usXEnd - usTemp1;
        usYStart = usTemp2;
        usYEnd = usYStart + usTemp;
    }
    else if(GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_270)
    {
        usXStart = usYStart;
        usYStart = (g_ucOsdHeight * 12) - usXEnd;
        usXEnd = usXStart + usTemp1;
        usYEnd = usYStart + usTemp;
    }
    else
    {
    }

#elif(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_HARDWARE)
    WORD xdata usTemp = 0;
    WORD xdata usTemp1 = 0;
    WORD xdata usTemp2 = 0;
    usTemp  = usXEnd - usXStart;
    usTemp1 = usYEnd - usYStart;
    usTemp2 = usXStart;

    if(GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_90)
    {
        usXEnd = (g_ucOsdHeight * 18 - usYStart);
        usXStart = usXEnd - usTemp1;
        usYStart = usTemp2;
        usYEnd = usYStart + usTemp;
    }
    else if(GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_270)
    {
        usXStart = usYStart;
        usYStart = (g_ucOsdWidth * 12) - usXEnd;
        usXEnd = usXStart + usTemp1;
        usYEnd = usYStart + usTemp;
    }
    else if(GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_180)
    {
        usXStart = (g_ucOsdWidth * 12) - usTemp - usXStart;
        usXEnd = usXStart + usTemp;
        usYStart = (g_ucOsdHeight * 18) - usTemp1 - usYStart;
        usYEnd = usYStart + usTemp1;
    }
    else
    {
    }

#else // #if(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_SOFTWARE)


#endif

    SET_OSD_WINDOW_NUMBER(ucWindow);
    SET_OSD_WINDOW_COLOR(ucColor);

    SET_OSD_WINDOW_BLEND_ENABLE(_ENABLE);
    SET_OSD_WINDOW_ENABLE(_ENABLE);
    ScalerTimerWaitForEvent(_EVENT_DVS);
    ScalerOsdDrawWindow(usXStart, usYStart, usXEnd, usYEnd);
}





#endif//#if(_OSD_TYPE == _REALTEK_2014_OSD)

