// #39 key test screen: rows of the same pop-up as the debug lines (awto_dbgpop.inc, #34); redrawn by AwtoKeyScan every
// AWTO_KEY_REFRESH_MS while open. Inserted into RTD2014OsdDisplay.c after the debug lines (uses their AwtoPut* helpers).
#ifdef _AWTO_NEW_SETTINGS
static void AwtoPutKeys(BYTE ucMask)            // front keys left to right, space separated
{
    if(ucMask == 0)
    {
        AwtoPutStr("NONE");
        return;
    }
    if((ucMask & AWTO_KM_SOURCE) != 0)
    {
        AwtoPutStr("SOURCE ");
    }
    if((ucMask & AWTO_KM_MENU) != 0)
    {
        AwtoPutStr("MENU ");
    }
    if((ucMask & AWTO_KM_DOWN) != 0)
    {
        AwtoPutStr("DOWN ");
    }
    if((ucMask & AWTO_KM_UP) != 0)
    {
        AwtoPutStr("UP ");
    }
    if((ucMask & AWTO_KM_AUTO) != 0)
    {
        AwtoPutStr("AUTO ");
    }
    if((ucMask & AWTO_KM_POWER) != 0)
    {
        AwtoPutStr("POWER");
    }
}

static void AwtoPutKeyMsg(BYTE ucMsg)            // one call per literal: a ?: chain of string literals printed garbage (keys2 render)
{
    if(ucMsg == _EXIT_KEY_MESSAGE)
    {
        AwtoPutStr("MENU");
    }
    else if(ucMsg == _RIGHT_KEY_MESSAGE)
    {
        AwtoPutStr("UP");
    }
    else if(ucMsg == _LEFT_KEY_MESSAGE)
    {
        AwtoPutStr("DOWN");
    }
    else if(ucMsg == _MENU_KEY_MESSAGE)
    {
        AwtoPutStr("AUTO");
    }
    else if(ucMsg == AWTO_KEY_MSG_SOURCE)
    {
        AwtoPutStr("SOURCE");
    }
    else
    {
        AwtoPutStr("NONE");
    }
}

static void AwtoPutAdc(BYTE ucCh, BYTE ucRaw)   // "A0 7C 15 0.484FS": raw hex, 5-bit code, fraction of full scale (reference not in the regdb)
{
    AwtoPutChar('A');
    AwtoPutNum(ucCh, 1);
    AwtoPutStr(" ");
    AwtoPutHex2(ucRaw);
    AwtoPutStr(" ");
    AwtoPutNum(ucRaw >> 3, 2);
    AwtoPutStr(" ");
    AwtoPutMilli((WORD)ucRaw * 125 / 32);       // R / 256 in thousandths
    AwtoPutStr("FS");
}

static BYTE AwtoKeyLetter(BYTE ucI)             // press log entry -> S M D U A P (lower case = injected), '-' = combo, ' ' = empty
{
    BYTE ucMask = g_stAwtoKey.pstLog[ucI].ucMask;
    BYTE ucMsg = g_stAwtoKey.pstLog[ucI].ucMsg;
    BYTE ucL = ' ';

    if(ucMask == 0)
    {
        ucL = (ucMsg == _EXIT_KEY_MESSAGE) ? 'M' : (ucMsg == _RIGHT_KEY_MESSAGE) ? 'U' : (ucMsg == _LEFT_KEY_MESSAGE) ? 'D' :
              (ucMsg == _MENU_KEY_MESSAGE) ? 'A' : (ucMsg == AWTO_KEY_MSG_SOURCE) ? 'S' : ' ';
    }
    else
    {
        ucL = (ucMask == AWTO_KM_SOURCE) ? 'S' : (ucMask == AWTO_KM_MENU) ? 'M' : (ucMask == AWTO_KM_DOWN) ? 'D' :
              (ucMask == AWTO_KM_UP) ? 'U' : (ucMask == AWTO_KM_AUTO) ? 'A' : (ucMask == AWTO_KM_POWER) ? 'P' : '-';
    }
    if(((g_stAwtoKey.pstLog[ucI].ucFlags & AWTO_KEY_F_INJ) != 0) && (ucL >= 'A') && (ucL <= 'Z'))
    {
        ucL += 'a' - 'A';
    }
    return ucL;
}

void AwtoOsdKeyLines(void)
{
    BYTE ucK;

    bit d_bFirst = (g_stAwtoKey.ucDrawn == 0);

    g_stAwtoKey.ucDrawn = 1;
    g_stAwtoKey.ucRedraws++;
    if(AwtoConLost() != 0) return;
    AwtoPanel(1);
    if(d_bFirst != 0)
    {
        AwtoPutCol(1);
        AwtoPutStr("KEY TEST");
        AwtoTextLine(0, AWTO_T_STYLE_ACCENT);
    }

    AwtoPutAdc(0, g_stAwtoKey.ucA0);
    AwtoShowLine(_OSD_MESSAGE_ROW_START, _PFONT_PAGE_0);
    AwtoPutAdc(1, g_stAwtoKey.ucA1);
    AwtoPutStr(" P30 ");                         // the POWER pin: 1 idle, 0 = pressed
    AwtoPutNum(g_stAwtoKey.ucP30 & AWTO_KEY_F_P30, 1);
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 1, _PFONT_PAGE_1);

    AwtoPutStr("KEY ");
    AwtoPutKeys(g_stAwtoKey.ucMask);
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 2, _PFONT_PAGE_2);

    AwtoPutStr("MSG ");
    AwtoPutKeyMsg(g_stAwtoKey.ucMsg);
    AwtoPutStr(" R");
    AwtoPutNum(g_stAwtoKey.ucFlags & 0x01, 1);
    AwtoPutNum((g_stAwtoKey.ucFlags >> 1) & 0x01, 1);
    AwtoPutStr(" H");
    AwtoPutNum((g_stAwtoKey.ucFlags >> 2) & 0x01, 1);
    if((g_stAwtoKey.ucFlags & AWTO_KEY_F_INJ) != 0)
    {
        AwtoPutStr(" INJ");
    }
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 3, _PFONT_PAGE_0);

    AwtoPutStr("LAST");
    for(ucK = AWTO_KEY_LAST_N; ucK != 0; ucK--)      // oldest left, newest right
    {
        AwtoPutStr(" ");
        AwtoPutChar(AwtoKeyLetter((g_stAwtoKey.ucCount - ucK) & (AWTO_KEY_LOG_N - 1)));
    }
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 4, _PFONT_PAGE_1);

    AwtoPutStr("N ");
    AwtoPutNum(g_stAwtoKey.ucCount, 1);
    AwtoPutStr(" CLOSE UP DOWN");
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 5, _PFONT_PAGE_2);
}
#else
void AwtoOsdKeyLines(void)
{
}
#endif
