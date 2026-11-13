#include "ScalerFunctionInclude.h"

// Exact input frequencies (#34, #26). Layout: RL6449_Project.h StAwtoFreq.
// Called after each M-domain count (line-buffer fine-tune / frame-buffer path); host twin: scripts/rtd_proto.py exact_timing.
__xdata StAwtoFreq g_stAwtoFreq;

void AwtoFreqUpdate(void)
{
    DWORD ulPix;
    DWORD ulMeas = AWTO_XTAL_HZ;
    BYTE ucDiv;

    g_stAwtoFreq.ucValid = 0;
    g_stAwtoFreq.ulCount = g_ulInputActiveRegionBackUp;
    g_stAwtoFreq.usIHTotal = g_stMDomainInputData.usHTotal;
    g_stAwtoFreq.usIVTotal = g_stMDomainInputData.usVTotal;
    g_stAwtoFreq.usIHWidth = g_stMDomainInputData.usHWidth;
    g_stAwtoFreq.usIVHeight = g_stMDomainInputData.usVHeight;
    g_stAwtoFreq.ucExtraLines = 0;
    if(ScalerGetBit(P0_23_SCALE_DOWN_CTRL_M1, _BIT0) == _BIT0)      // as ScalerDPLLFineTuneFrameSyncLineBuffer
    {
        g_stAwtoFreq.ucExtraLines = 1;
#if(_FORMAT_CONVERSION_SUPPORT == _ON)
        if(ScalerFmtCnvFtoPGetStatus() == _TRUE)
        {
            g_stAwtoFreq.ucExtraLines = 2;
        }
#endif
    }
    if((GET_M2PLL_POWER_STATUS() == _TRUE) && (_MEASURE_USE_M2PLL_CLK == _TRUE))      // _MEASURE_CLK, in Hz
    {
        ucDiv = _MEASURE_CLK_DIV;
        if(ucDiv == 0)
        {
            return;
        }
        ulMeas = AWTO_XTAL_HZ / (_M2PLL_PLL_N * _M2PLL_PLL_O) * _M2PLL_PLL_M / ucDiv;
    }
    g_stAwtoFreq.ulMeasHz = ulMeas;
    if((g_stAwtoFreq.ulCount == 0) || (g_stAwtoFreq.usIHTotal == 0) || (g_stAwtoFreq.usIVTotal == 0) || (g_stAwtoFreq.usIVHeight == 0))
    {
        return;
    }
    ulPix = (DWORD)g_stAwtoFreq.usIHTotal * (g_stAwtoFreq.usIVHeight - 1 + g_stAwtoFreq.ucExtraLines) + g_stAwtoFreq.usIHWidth;
    g_stAwtoFreq.ulPclkHz = GET_DWORD_MUL_DIV(ulMeas, ulPix, g_stAwtoFreq.ulCount);
    g_stAwtoFreq.ulHFreqHz = (g_stAwtoFreq.ulPclkHz + (g_stAwtoFreq.usIHTotal >> 1)) / g_stAwtoFreq.usIHTotal;
    g_stAwtoFreq.ulVFreqmHz = GET_DWORD_MUL_DIV(g_stAwtoFreq.ulPclkHz, 1000, (DWORD)g_stAwtoFreq.usIHTotal * g_stAwtoFreq.usIVTotal);
    g_stAwtoFreq.ucValid = 1;
}
