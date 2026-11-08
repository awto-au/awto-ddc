// #39 key test screen: rows of the same pop-up as the debug lines (awto_dbgpop.inc, #34); redrawn by AwtoKeyScan every
// AWTO_KEY_REFRESH_MS while open. Inserted into RTD2014OsdDisplay.c after the debug lines (uses their AwtoPut* helpers).
#if(_AWTO_DIAG == _ON)
static void AwtoPutHex2(BYTE ucV)
{
    BYTE ucH = ucV >> 4;
    BYTE ucL = ucV & 0x0F;

    AwtoPutChar((ucH < 10) ? ('0' + ucH) : ('A' + ucH - 10));
    AwtoPutChar((ucL < 10) ? ('0' + ucL) : ('A' + ucL - 10));
}

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

static void AwtoPutKeyMsg(BYTE ucMsg)
{
    AwtoPutStr((ucMsg == _MENU_KEY_MESSAGE) ? "MENU" : (ucMsg == _RIGHT_KEY_MESSAGE) ? "UP" : (ucMsg == _LEFT_KEY_MESSAGE) ? "DOWN" :
               (ucMsg == _EXIT_KEY_MESSAGE) ? "AUTO" : (ucMsg == AWTO_KEY_MSG_SOURCE) ? "SOURCE" : "NONE");
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
        ucL = (ucMsg == _MENU_KEY_MESSAGE) ? 'M' : (ucMsg == _RIGHT_KEY_MESSAGE) ? 'U' : (ucMsg == _LEFT_KEY_MESSAGE) ? 'D' :
              (ucMsg == _EXIT_KEY_MESSAGE) ? 'A' : (ucMsg == AWTO_KEY_MSG_SOURCE) ? 'S' : ' ';
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

    g_ucFontPointer0 = _OSD_PAGE_0_START;
    g_ucFontPointer1 = _OSD_PAGE_1_START;
    g_ucFontPointer2 = _OSD_PAGE_2_START;
    g_stAwtoKey.ucDrawn = 1;
    s_ucAwtoLen = 0;

    AwtoPutAdc(0, g_stAwtoKey.ucA0);
    AwtoShowLine(_OSD_MESSAGE_ROW_START, _PFONT_PAGE_0);
    AwtoPutAdc(1, g_stAwtoKey.ucA1);
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 1, _PFONT_PAGE_1);

    AwtoPutStr("P30 ");
    AwtoPutNum(g_stAwtoKey.ucP30 & AWTO_KEY_F_P30, 1);
    AwtoPutStr(" KEY ");
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
#endif
