#include "UserCommonInclude.h"

#if(_OSD_TYPE == _REALTEK_2014_OSD)
#ifdef _AWTO_NEW_SETTINGS
//---- flash (nvram.h fl_*): one entry point, so fw_sim can model it (scripts/settings_sim.py stubs AwtoFlIo) ----
typedef struct
{
    BYTE ucOp;                                  // 1 read, 2 write, 3 erase sector
    BYTE ucOk;
    BYTE ucBank;
    WORD usAddr;
    WORD usLen;
    BYTE xdata *pucBuf;
} StAwtoFl;
__xdata StAwtoFl g_stAwtoFl;

void AwtoFlIo(void)
{
    bit bOk = _FALSE;

    if(g_stAwtoFl.ucOp == 1)
    {
        bOk = UserCommonFlashRead(g_stAwtoFl.ucBank, g_stAwtoFl.usAddr, g_stAwtoFl.usLen, g_stAwtoFl.pucBuf);
    }
    else if(g_stAwtoFl.ucOp == 2)
    {
        bOk = UserCommonFlashWrite(g_stAwtoFl.ucBank, g_stAwtoFl.usAddr, g_stAwtoFl.usLen, g_stAwtoFl.pucBuf);
    }
    else if(g_stAwtoFl.ucOp == 3)
    {
        bOk = UserCommonFlashErasePage(g_stAwtoFl.ucBank, (BYTE)(g_stAwtoFl.usAddr >> 12));
    }
    g_stAwtoFl.ucOk = bOk;
}

static BYTE AwtoFl(BYTE ucOp, DWORD ulA, BYTE xdata *pucBuf, WORD usLen)
{
    g_stAwtoFl.ucOp = ucOp;
    g_stAwtoFl.ucBank = (BYTE)(ulA >> 16);
    g_stAwtoFl.usAddr = (WORD)ulA;
    g_stAwtoFl.usLen = usLen;
    g_stAwtoFl.pucBuf = pucBuf;
    g_stAwtoFl.ucOk = 0;
    AwtoFlIo();
    return g_stAwtoFl.ucOk;
}

BYTE fl_read(DWORD ulA, BYTE xdata *pucDst, WORD usN)
{
    return AwtoFl(1, ulA, pucDst, usN);
}

BYTE fl_write(DWORD ulA, BYTE xdata *pucSrc, WORD usN)
{
    return AwtoFl(2, ulA, pucSrc, usN);
}

BYTE fl_erase(DWORD ulA)
{
    return AwtoFl(3, ulA, 0, 0);
}
#endif
#endif//#if(_OSD_TYPE == _REALTEK_2014_OSD)
