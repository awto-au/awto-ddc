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
// ID Code      : RTD2014OsdFontTable.c
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __RTD_OSDFONTTABLE__

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
BYTE __code tOSD_iREALTEK[] =
{
    _iREALTEK_00, _iREALTEK_01, _iREALTEK_02, _iREALTEK_03, _iREALTEK_04, _iREALTEK_05, _iREALTEK_06, _iREALTEK_07, _iREALTEK_08, _iREALTEK_09, _iREALTEK_0A, _iREALTEK_0B, _NEXT_,
    _iREALTEK_10, _iREALTEK_11, _iREALTEK_12, _iREALTEK_13, _iREALTEK_14, _iREALTEK_15, _iREALTEK_16, _iREALTEK_17, _iREALTEK_18, _iREALTEK_19, _iREALTEK_1A, _iREALTEK_1B, _END_,
};

BYTE __code tOSD_iKEY_BACK[] =
{
    _iKEY_BACK_00, _iKEY_BACK_01, _NEXT_,
    _iKEY_BACK_10, _iKEY_BACK_11, _END_,
};

BYTE __code tOSD_iKEY_LEFT[] =
{
    _iKEY_LEFT_00, _iKEY_LEFT_01, _NEXT_,
    _iKEY_LEFT_10, _iKEY_LEFT_11, _END_,
};

BYTE __code tOSD_iKEY_RIGHT[] =
{
    _iKEY_RIGHT_00, _iKEY_RIGHT_01, _NEXT_,
    _iKEY_RIGHT_10, _iKEY_RIGHT_11, _END_,
};

BYTE __code tOSD_iKEY_ENTER[] =
{
    _iKEY_ENTER_00, _iKEY_ENTER_01, _NEXT_,
    _iKEY_ENTER_10, _iKEY_ENTER_11, _END_,
};

BYTE __code tOSD_iKEY_EXIT[] =
{
    _iKEY_EXIT_00, _iKEY_EXIT_01, _NEXT_,
    _iKEY_EXIT_10, _iKEY_EXIT_11, _END_,
};



//****************************************************************************
// VARIABLE DECLARATIONS
//****************************************************************************

//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
void OsdFontPut1Bit(BYTE ucRow, BYTE ucCol, BYTE ucIcon, BYTE ucColor);
void OsdFontPut1BitTable(BYTE ucRow, BYTE ucCol, BYTE *pucArray, BYTE ucColor);
void OsdFontPut1BitMainMenuIcon(BYTE ucRow, BYTE ucCol, BYTE ucIcon, BYTE ucForeground, BYTE ucBackground);
void OsdFontPut2Bit(BYTE ucRow, BYTE ucCol, BYTE ucIcon, BYTE ucColor0, BYTE ucColor1, BYTE ucColor2, BYTE ucColor3);
void OsdFontPut2BitTable(BYTE ucRow, BYTE ucCol, BYTE *pucArray, BYTE ucColor0, BYTE ucColor1, BYTE ucColor2, BYTE ucColor3);

//***************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFontPut1Bit(BYTE ucRow, BYTE ucCol, BYTE ucIcon, BYTE ucColor)
{
    WORD xdata usOsdAddr = (WORD)ucRow * g_ucOsdWidth + ucCol;
    BYTE xdata ucByte0 = 0x4C;

#if(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_SOFTWARE)
    if(GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_90)
    {
        usOsdAddr = (WORD)((g_ucOsdWidth - ucRow - 1) + g_ucOsdWidth * ucCol);
        ucByte0 = 0x4E;
    }
    else if(GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_270)
    {
        usOsdAddr = (WORD)(g_ucOsdHeight - 1 - ucCol) * g_ucOsdWidth + ucRow;
        ucByte0 = 0x4E;
    }
#endif

    ScalerOsdCommandAllByte(usOsdAddr + g_usFontSelectStart, ucByte0, ucIcon, ucColor);
}

//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFontPut1BitTable(BYTE ucRow, BYTE ucCol, BYTE *pucArray, BYTE ucColor)
{
    BYTE ucOsdWidth = 0;
    BYTE ucCount = 0;
    BYTE ucHTemp = ucCol;

#if(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_SOFTWARE)
    if((GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_90) ||
       (GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_270))
    {
        ucOsdWidth = g_ucOsdHeight;
    }
    else
#endif
    {
        ucOsdWidth = g_ucOsdWidth;
    }

    while(*pucArray != _END_)
    {
        if(*pucArray == _NEXT_)
        {
            ucRow++;
            ucHTemp =ucCol;
            pucArray++;
        }
        else if(*pucArray == _SPACE_)
        {
            ucHTemp++;
            pucArray++;
        }
        else if(*pucArray == _REPEAT_)
        {
            ucCount = *(pucArray + 1) - 1;

            while(ucCount > 0)
            {
                if(*(pucArray - 1) != _SPACE_)
                {
                    OsdFontPut1Bit(ucRow, ucHTemp, *(pucArray - 1), ucColor);
                }

                ucHTemp++;

                if((ucHTemp == ucOsdWidth) && (*(pucArray + 1) != _NEXT_))
                {
                    ucRow++;
                    ucHTemp =ucCol;
                }
                ucCount--;
            }
            pucArray += 2;
        }
        else
        {
            OsdFontPut1Bit(ucRow, ucHTemp, *pucArray, ucColor);
            ucHTemp++;

            if((ucHTemp == ucOsdWidth) && (*(pucArray + 1) != _NEXT_))
            {
                ucRow++;
                ucHTemp =ucCol;
            }
            pucArray++;
        }
    }
}

//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFontPut1BitMainMenuIcon(BYTE ucRow, BYTE ucCol, BYTE ucIcon, BYTE ucForeground, BYTE ucBackground)
{
    WORD usOsdAddr = (WORD)ucRow * g_ucOsdWidth + ucCol;
    BYTE ucByte0 = 0x4C;
    BYTE ucByte2 = 0;
    BYTE ucLength = 6;
    BYTE ucHeight = 4;

#if(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_SOFTWARE)
    if(GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_90)
    {
        usOsdAddr = (WORD)((g_ucOsdWidth - ucRow - 1) + g_ucOsdWidth * ucCol);
        ucByte0 = 0x4E;
    }
    else if(GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_270)
    {
        usOsdAddr = (WORD)(g_ucOsdHeight - 1 - ucCol) * g_ucOsdWidth + ucRow;
        ucByte0 = 0x4E;
    }
#endif

    ucForeground &= 0x0F;

    ucByte2 = ((ucForeground << 4) | ucBackground);

#if(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_SOFTWARE)
    if(GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_90)
    {
        for(ucHeight = 0; ucHeight < 4; ucHeight++)
        {
            for(ucLength=0; ucLength < 6; ucLength++)
            {
                usOsdAddr = (WORD)(g_ucOsdWidth - ucRow - ucHeight - 1) + g_ucOsdWidth * (ucCol + ucLength);
                ScalerOsdCommandAllByte(usOsdAddr + g_usFontSelectStart, ucByte0, ucIcon, ucByte2);
                ucIcon++;
            }
        }
    }
    else if(GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_270)
    {
        for(ucHeight = 0; ucHeight < 4; ucHeight++)
        {
            for(ucLength=0; ucLength < 6; ucLength++)
            {
                usOsdAddr = (WORD)(g_ucOsdHeight - 1 - (ucCol + ucLength)) * g_ucOsdWidth + (ucRow + ucHeight);
                ScalerOsdCommandAllByte(usOsdAddr + g_usFontSelectStart, ucByte0, ucIcon, ucByte2);
                ucIcon++;
            }
        }
    }
    else
#endif
    {
        for(ucHeight = 0; ucHeight < 4; ucHeight++)
        {
            for(ucLength=0; ucLength < 6; ucLength++)
            {
                ScalerOsdCommandAllByte(usOsdAddr + g_usFontSelectStart + ucLength, ucByte0, ucIcon, ucByte2);
                ucIcon++;
            }
            usOsdAddr += g_ucOsdWidth;
        }
    }
}

//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFontPut2Bit(BYTE ucRow, BYTE ucCol, BYTE ucIcon, BYTE ucColor0, BYTE ucColor1, BYTE ucColor2, BYTE ucColor3)
{
    WORD xdata usOsdAddr = (WORD)ucRow * g_ucOsdWidth + ucCol;
    BYTE xdata ucByte0 = 0;
    BYTE xdata ucByte2 = 0;

#if(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_SOFTWARE)
    if(GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_90)
    {
        usOsdAddr = (WORD)((g_ucOsdWidth - ucRow - 1) + g_ucOsdWidth * ucCol);
    }
    else if(GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_270)
    {
        usOsdAddr = (WORD)(g_ucOsdHeight - 1 - ucCol) * g_ucOsdWidth + ucRow;
    }
#endif

    ucColor0 &= 0x0F;
    ucByte0 = (_BIT7) | ((ucColor0 & _BIT3) << 2) | ((ucColor1 & _BIT3) << 1) | ((ucColor3 & 0x07) << 1) | ((ucColor0 & _BIT2) >> 2);
    ucByte2 = ((ucColor0 & 0x03) << 6) | ((ucColor2 & 0x07) << 3) | (ucColor1 & 0x07);

    ScalerOsdCommandAllByte(usOsdAddr + g_usFontSelectStart, ucByte0, ucIcon, ucByte2);
}

//--------------------------------------------------
// Description  :
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void OsdFontPut2BitTable(BYTE ucRow, BYTE ucCol, BYTE *pucArray, BYTE ucColor0, BYTE ucColor1, BYTE ucColor2, BYTE ucColor3)
{
    BYTE ucOsdWidth = 0;
    BYTE ucCount = 0;
    BYTE ucHTemp = ucCol;

#if(_OSD_ROTATE_FUNCTION == _OSD_ROTATE_SOFTWARE)
    if((GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_90) ||
       (GET_OSD_ROTATE_STATUS() == _OSD_ROTATE_DEGREE_270))
    {
        ucOsdWidth = g_ucOsdHeight;
    }
    else
#endif
    {
        ucOsdWidth = g_ucOsdWidth;
    }

    while(*pucArray != _END_)
    {
        if(*pucArray == _NEXT_)
        {
            ucRow++;
            ucHTemp =ucCol;
            pucArray++;
        }
        else if(*pucArray == _SPACE_)
        {
            ucHTemp++;
            pucArray++;
        }
        else if(*pucArray == _REPEAT_)
        {
            ucCount = *(pucArray + 1) - 1;

            while(ucCount > 0)
            {
                if(*(pucArray - 1) != _SPACE_)
                {
                    OsdFontPut2Bit(ucRow, ucHTemp, *(pucArray - 1), ucColor0, ucColor1, ucColor2, ucColor3);
                }

                ucHTemp++;

                if((ucHTemp == ucOsdWidth) && (*(pucArray + 1) != _NEXT_))
                {
                    ucRow++;
                    ucHTemp =ucCol;
                }
                ucCount--;
            }
            pucArray += 2;
        }
        else
        {
            OsdFontPut2Bit(ucRow, ucHTemp, *pucArray, ucColor0, ucColor1, ucColor2, ucColor3);
            ucHTemp++;

            if((ucHTemp == ucOsdWidth) && (*(pucArray + 1) != _NEXT_))
            {
                ucRow++;
                ucHTemp = ucCol;
            }
            pucArray++;
        }
    }
}

//void OsdFontPut4Bit()
//{
//}

//void OsdFontPut4BitTable()
//{
//}

#endif//#if(_OSD_TYPE == _REALTEK_2014_OSD)

