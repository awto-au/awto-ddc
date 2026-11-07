// Info pop-up frequency strings with 3 decimals from g_stAwtoFreq (#34), inserted into RTD2014OsdFontProp.c by keil2sdcc.py.
// Each SDK OsdPropGetShow*StringAddress calls AwtoFreqModeStr() first; _FALSE (no exact value) = the SDK's 0.1 string.
#if(_AWTO_FREQ == _ON)
#define AWTO_STR_RES                                            0
#define AWTO_STR_VFREQ                                          1
#define AWTO_STR_HFREQ_PCLK                                     2

static BYTE AwtoModePut(BYTE ucI, BYTE ucG)
{
    if(ucI < (sizeof(g_pucModeInfoData) - 1))
    {
        g_pucModeInfoData[ucI++] = ucG;
    }
    return ucI;
}

// ulV in thousandths -> "int.ddd" (ucDec = 3) or plain "int" (ucDec = 0)
static BYTE AwtoModePutFix(BYTE ucI, DWORD ulV, BYTE ucDec)
{
    BYTE pucD[10];
    BYTE ucN = 0;

    do
    {
        pucD[ucN++] = (BYTE)(ulV % 10);
        ulV /= 10;
    }
    while(((ulV != 0) || (ucN <= ucDec)) && (ucN < sizeof(pucD)));
    while(ucN != 0)
    {
        if(ucN == ucDec)
        {
            ucI = AwtoModePut(ucI, _DOT_);
        }
        ucI = AwtoModePut(ucI, _0_ + pucD[--ucN]);
    }
    return ucI;
}

static BYTE AwtoModePutHz(BYTE ucI, DWORD ulMilli, BYTE ucPrefix)
{
    ucI = AwtoModePutFix(ucI, ulMilli, 3);
    if(ucPrefix != 0)
    {
        ucI = AwtoModePut(ucI, ucPrefix);
    }
    ucI = AwtoModePut(ucI, _H_);
    return AwtoModePut(ucI, _z_);
}

bit AwtoFreqModeStr(BYTE ucWhich)
{
    BYTE ucI = 0;
    BYTE ucR;

    if(g_stAwtoFreq.ucValid == 0)
    {
        return _FALSE;
    }
    if(ucWhich == AWTO_STR_RES)
    {
        ucR = OsdPropVideoResolution();
        if(ucR != 0)
        {
            for(ucI = 0; ucI < 5; ucI++)
            {
                g_pucModeInfoData[ucI] = tSTRING_RESOLUTION_TABLE[ucR][ucI + 1];
            }
        }
        else
        {
            ucI = AwtoModePutFix(ucI, GET_INPUT_TIMING_HWIDTH(), 0);
            ucI = AwtoModePut(ucI, _x_);
            ucI = AwtoModePutFix(ucI, GET_INPUT_TIMING_VHEIGHT(), 0);
        }
        ucI = AwtoModePut(ucI, _AT_0_);
        ucI = AwtoModePut(ucI, _AT_1_);
        ucI = AwtoModePutHz(ucI, g_stAwtoFreq.ulVFreqmHz, 0);
    }
    else if(ucWhich == AWTO_STR_VFREQ)
    {
        ucI = AwtoModePut(ucI, _V_);
        ucI = AwtoModePut(ucI, _COLON_);
        ucI = AwtoModePut(ucI, _);
        ucI = AwtoModePutHz(ucI, g_stAwtoFreq.ulVFreqmHz, 0);
    }
    else
    {
        // "H:134.865KHz P:593.407MHz": 25 glyphs, the SDK's 28-byte buffer has no room for "PCLK" at 3 decimals
        ucI = AwtoModePut(ucI, _H_);
        ucI = AwtoModePut(ucI, _COLON_);
        ucI = AwtoModePutHz(ucI, g_stAwtoFreq.ulHFreqHz, _K_);
        ucI = AwtoModePut(ucI, _);
        ucI = AwtoModePut(ucI, _P_);
        ucI = AwtoModePut(ucI, _COLON_);
        ucI = AwtoModePutHz(ucI, g_stAwtoFreq.ulPclkHz / 1000, _M_);
    }
    g_pucModeInfoData[ucI] = _END_;
    return _TRUE;
}
#endif
