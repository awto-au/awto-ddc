// Debug pop-up (#34): same window/font/colours as the input-info pop-up; hooked into OsdDispOsdMessage by keil2sdcc.py.
#if(_AWTO_DIAG == _ON)
extern BYTE *g_pucShowNumberAddress;
#include <stddef.h>
static BYTE s_pucAwtoDbg[28];
static BYTE s_ucAwtoLen;

void AwtoOsdOfsInit(void)
{
    g_stAwtoDiag.ucOsdOfsState = offsetof(StructOsdInfo, usOsdState);
    g_stAwtoDiag.ucOsdOfsEvent = offsetof(StructOsdInfo, ucOsdEventMsg);
    g_stAwtoDiag.ucOsdOfsKey = offsetof(StructOsdInfo, ucOsdKeyMessage);
}

static void AwtoPutGlyph(BYTE ucG)
{
    if(s_ucAwtoLen < 26)      // awto: #53.2 clamp counts glyphs, the buffer holds 28 with the terminator
    {
        s_pucAwtoDbg[s_ucAwtoLen++] = ucG;
    }
}

static void AwtoPutChar(char c)
{
    BYTE ucG = _QUERY_;

    if((c >= '0') && (c <= '9'))
    {
        ucG = _0_ + (c - '0');
    }
    else if((c >= 'A') && (c <= 'Z'))
    {
        ucG = _A_ + (c - 'A') + ((c > 'W') ? 1 : 0);      // W is two glyphs (_W_0,_W_1): X..Z shift by one
    }
    else if((c >= 'a') && (c <= 'z'))
    {
        ucG = _a_ + (c - 'a') + ((c > 'w') ? 1 : 0);
    }
    else if(c == ' ')
    {
        ucG = _;
    }
    else if(c == ':')
    {
        ucG = _COLON_;
    }
    else if(c == '.')
    {
        ucG = _DOT_;
    }
    else if(c == '-')
    {
        ucG = _SLINE_;
    }
    else if(c == '/')
    {
        ucG = _AND_;                  // U002F: the SDK font has it, the old mapping printed '?'
    }
    AwtoPutGlyph(ucG);
    if((c == 'W') || (c == 'w'))
    {
        AwtoPutGlyph(ucG + 1);      // awto: #53.2 second half (_W_1 / _w_1)
    }
}

static void AwtoPutStr(const char *s)
{
    while(*s != 0)
    {
        AwtoPutChar(*s++);
    }
}

static void AwtoPutNum(unsigned long ulV, BYTE ucMin)
{
    char pcD[10];
    BYTE ucN = 0;

    do
    {
        pcD[ucN++] = '0' + (ulV % 10);
        ulV /= 10;
    }
    while((ulV != 0) && (ucN < 10));
    while(ucN < ucMin)
    {
        pcD[ucN++] = '0';
    }
    while(ucN != 0)
    {
        AwtoPutChar(pcD[--ucN]);
    }
}

// ulV in thousandths -> "int.ddd" (#34: every frequency with 3 decimals)
static void AwtoPutMilli(unsigned long ulV)
{
    AwtoPutNum(ulV / 1000, 1);
    AwtoPutChar('.');
    AwtoPutNum(ulV % 1000, 3);
}

static void AwtoShowLine(BYTE ucRow, BYTE ucPage)
{
    s_pucAwtoDbg[s_ucAwtoLen] = _END_;
    s_ucAwtoLen = 0;
    g_pucShowNumberAddress = s_pucAwtoDbg;
    OsdFuncClearOsd(ucRow, _OSD_MESSAGE_CENTER_COL_START, _OSD_MESSAGE_CENTER_COL_END + 1, 1);     // a shorter text must not leave the old one's cells
    OsdPropPutStringCenter(ROW(ucRow), COL(_OSD_MESSAGE_CENTER_COL_START), WIDTH(_OSD_MESSAGE_CENTER_COL_END), ucPage, _STRING_SHOW_NUMBER, COLOR(_CP_WHITE, _CP_BG), _ENGLISH);
}

void AwtoOsdDebugLines(void)
{
    BYTE ucPort = SysSourceGetInputPort();
    BYTE ucMode = SysModeGetModeState();
    BYTE ucPwr = SysPowerGetPowerStatus();
    unsigned long ulDclk = GET_D_CLK_FREQ();      // kHz
    WORD usV = GET_INPUT_TIMING_VFREQ();          // 0.1 Hz

    g_stAwtoDiag.ucDbgPopup = 0;
    s_ucAwtoLen = 0;

    AwtoPutStr((ucPort >= _D0_PORT) ? "D" : "A");
    AwtoPutNum((ucPort >= _D0_PORT) ? (ucPort - _D0_PORT) : 0, 1);
    AwtoPutStr(" ");
    AwtoPutNum(GET_INPUT_TIMING_HWIDTH(), 1);
    AwtoPutStr("x");
    AwtoPutNum(GET_INPUT_TIMING_VHEIGHT(), 1);
    AwtoPutStr(" ");
#if(_AWTO_FREQ == _ON)
    if(g_stAwtoFreq.ucValid != 0)
    {
        AwtoPutMilli(g_stAwtoFreq.ulVFreqmHz);
    }
    else
#endif
    {
        AwtoPutNum(usV / 10, 1);      // SDK 0.1 Hz value: no exact count yet
        AwtoPutStr(".");
        AwtoPutNum(usV % 10, 1);
    }
    AwtoPutStr("Hz");
    AwtoShowLine(_OSD_MESSAGE_ROW_START, _PFONT_PAGE_0);

    AwtoPutStr(ucMode == _MODE_STATUS_ACTIVE ? "ACTIVE" : (ucMode == _MODE_STATUS_NOSIGNAL ? "NOSIG" : (ucMode == _MODE_STATUS_POWER_SAVING ? "PSAVE" : "MODE")));
    AwtoPutStr(" ");
    AwtoPutNum(ucMode, 1);
    AwtoPutStr("  PWR ");
    AwtoPutStr(ucPwr == _POWER_STATUS_NORMAL ? "ON" : (ucPwr == _POWER_STATUS_SAVING ? "SAVE" : (ucPwr == _POWER_STATUS_OFF ? "OFF" : "AC")));
    AwtoPutNum(ucPwr, 1);
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 1, _PFONT_PAGE_1);

#if(_AWTO_FREQ == _ON)
    if(g_stAwtoFreq.ucValid != 0)
    {
        AwtoPutStr("PCLK ");
        AwtoPutMilli(g_stAwtoFreq.ulPclkHz / 1000);
        AwtoPutStr(" ");
    }
#endif
    AwtoPutStr("DCLK ");
    AwtoPutMilli(ulDclk);
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 2, _PFONT_PAGE_2);

    AwtoPutStr("LOOP ");
    AwtoPutNum(g_stAwtoDiag.usLoopRate, 1);
    AwtoPutStr("/s");
#if(_AWTO_FREQ == _ON)
    if(g_stAwtoFreq.ucValid != 0)
    {
        AwtoPutStr("  H ");
        AwtoPutMilli(g_stAwtoFreq.ulHFreqHz);
        AwtoPutStr("kHz");
    }
#endif
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 3, _PFONT_PAGE_0);

    AwtoPutStr("FW ");
    AwtoPutStr(AWTO_FW_TAG);
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 4, _PFONT_PAGE_1);
}
#endif
