// Debug pop-up (#34): same window/font/colours as the input-info pop-up; hooked into OsdDispOsdMessage by keil2sdcc.py.
#if(_AWTO_DIAG == _ON)
extern BYTE *g_pucShowNumberAddress;
static BYTE s_pucAwtoDbg[28];
static BYTE s_ucAwtoLen;

static void AwtoPutChar(char c)
{
    BYTE ucG = _QUERY_;

    if((c >= '0') && (c <= '9'))
    {
        ucG = _0_ + (c - '0');
    }
    else if((c >= 'A') && (c <= 'Z'))
    {
        ucG = _A_ + (c - 'A') + ((c > 'W') ? 1 : 0);      // W is two glyphs: skipped, X..Z shift by one
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
    if(s_ucAwtoLen < 26)
    {
        s_pucAwtoDbg[s_ucAwtoLen++] = ucG;
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

static void AwtoShowLine(BYTE ucRow, BYTE ucPage)
{
    s_pucAwtoDbg[s_ucAwtoLen] = _END_;
    s_ucAwtoLen = 0;
    g_pucShowNumberAddress = s_pucAwtoDbg;
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
    AwtoPutNum(usV / 10, 1);
    AwtoPutStr(".");
    AwtoPutNum(usV % 10, 1);
    AwtoPutStr("Hz");
    AwtoShowLine(_OSD_MESSAGE_ROW_START, _PFONT_PAGE_0);

    AwtoPutStr(ucMode == _MODE_STATUS_ACTIVE ? "ACTIVE" : (ucMode == _MODE_STATUS_NOSIGNAL ? "NOSIG" : (ucMode == _MODE_STATUS_POWER_SAVING ? "PSAVE" : "MODE")));
    AwtoPutStr(" ");
    AwtoPutNum(ucMode, 1);
    AwtoPutStr("  PWR ");
    AwtoPutStr(ucPwr == _POWER_STATUS_NORMAL ? "ON" : (ucPwr == _POWER_STATUS_SAVING ? "SAVE" : (ucPwr == _POWER_STATUS_OFF ? "OFF" : "AC")));
    AwtoPutNum(ucPwr, 1);
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 1, _PFONT_PAGE_1);

    AwtoPutStr("DCLK ");
    AwtoPutNum(ulDclk / 1000, 1);
    AwtoPutStr(".");
    AwtoPutNum((ulDclk % 1000) / 100, 1);
    AwtoPutStr("MHz");
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 2, _PFONT_PAGE_2);

    AwtoPutStr("LOOP ");
    AwtoPutNum(g_stAwtoDiag.usLoopRate, 1);
    AwtoPutStr("/s");
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 3, _PFONT_PAGE_0);

    AwtoPutStr("FW ");
    AwtoPutStr(AWTO_FW_TAG);
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 4, _PFONT_PAGE_1);
}
#endif
