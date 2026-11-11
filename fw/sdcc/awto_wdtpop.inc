// Watchdog panel of the diagnostic console (#131): last bite from g_stAwtoWdt; at the end of RTD2014OsdDisplay.c (after awto_dbgpop.inc).
#if((_AWTO_DIAG == _ON) && (_AWTO_WDT == _ON) && defined(_AWTO_NEW_SETTINGS))
#define AWTO_WDT_POP_COL    62
#define AWTO_WDT_POP_ROW    19                  // below the debug panel (rows 12..17)
#define AWTO_WDT_POP_W      36

static void AwtoWdtPutWord(BYTE ucHi, BYTE ucLo)
{
    AwtoPutHex2(ucHi);
    AwtoPutHex2(ucLo);
}

void AwtoOsdWdtLines(void)
{
    BYTE ucOk = AwtoWdtValid();
    BYTE ucC = g_stAwtoWdt.ucCause;

    s_ucPanelCol = AWTO_WDT_POP_COL;
    s_ucPanelRow = AWTO_WDT_POP_ROW;
    s_ucAwtoCols = AWTO_WDT_POP_W;
    s_ucAwtoLen = 1;
    AwtoPutStr("WATCHDOG");
    if(ucOk != 0)
    {
        AwtoPutStr("  BITES ");
        AwtoPutNum(g_stAwtoWdt.ucBites, 1);
        AwtoPutStr(" WARM ");
        AwtoPutNum(g_stAwtoWdt.ucWarm, 1);
    }
    AwtoTextLine(0, ((g_stAwtoWdt.ucBoot & AWTO_WDT_B_NEW) != 0) ? AWTO_T_STYLE_ALERT : AWTO_T_STYLE_ACCENT);
    g_stAwtoWdt.ucBoot &= ~AWTO_WDT_B_NEW;      // shown
    if((ucOk == 0) || (g_stAwtoWdt.ucBites == 0))
    {
        AwtoPutStr("NO BITE RECORDED");
        AwtoTextLine(1, AWTO_T_STYLE_TEXT);
    }
    else
    {
        AwtoPutStr(((ucC & 0x7F) == AWTO_WDT_C_STALL) ? "STALL" : (((ucC & 0x7F) == AWTO_WDT_C_PASS) ? "PASS" : "?"));
        AwtoPutStr(((ucC & AWTO_WDT_C_TEST) != 0) ? " TEST" : "");
        AwtoPutStr("  AGE FEED ");          // ages in checks of AWTO_WDT_CHECK_MS
        AwtoPutNum(g_stAwtoWdt.ucFeedAge, 1);
        AwtoPutStr(" PASS ");
        AwtoPutNum(g_stAwtoWdt.ucPassAge, 1);
        AwtoTextLine(1, AWTO_T_STYLE_TEXT);
        AwtoPutStr("PC ");
        if(g_stAwtoWdt.ucPcHi >= 0x50)
        {
            AwtoPutHex2(g_stAwtoWdt.ucBank);
        }
        else
        {
            AwtoPutStr("C");
        }
        AwtoPutChar(':');
        AwtoWdtPutWord(g_stAwtoWdt.ucPcHi, g_stAwtoWdt.ucPcLo);
        AwtoPutStr(" TOP ");
        AwtoWdtPutWord(g_stAwtoWdt.ucRetHi, g_stAwtoWdt.ucRetLo);
        AwtoPutStr(" SP ");
        AwtoPutHex2(g_stAwtoWdt.ucSp);
        AwtoTextLine(2, AWTO_T_STYLE_TEXT);
        AwtoPutStr("A ");
        AwtoPutHex2(g_stAwtoWdt.ucAcc);
        AwtoPutStr(" B ");
        AwtoPutHex2(g_stAwtoWdt.ucB);
        AwtoPutStr(" PSW ");
        AwtoPutHex2(g_stAwtoWdt.ucPsw);
        AwtoPutStr(" DPTR ");
        AwtoWdtPutWord(g_stAwtoWdt.ucDph, g_stAwtoWdt.ucDpl);
        AwtoTextLine(3, AWTO_T_STYLE_TEXT);
        AwtoPutStr("HB ");
        AwtoPutNum(((WORD)g_stAwtoWdt.ucHbHi << 8) | g_stAwtoWdt.ucHbLo, 1);
        AwtoPutStr(" UP ");
        AwtoPutNum(((WORD)g_stAwtoWdt.ucUpHi << 8) | g_stAwtoWdt.ucUpLo, 1);
        AwtoPutStr("MS ST ");
        AwtoPutNum(g_stAwtoWdt.ucStage, 1);
        AwtoPutStr(" MODE ");
        AwtoPutNum(g_stAwtoWdt.ucMode, 1);
        AwtoTextLine(4, AWTO_T_STYLE_TEXT);
    }
    AwtoPutStr("THIS BOOT ");
    AwtoPutStr(((g_stAwtoWdt.ucBoot & AWTO_WDT_B_LVR) != 0) ? "COLD" : (((g_stAwtoWdt.ucBoot & AWTO_WDT_B_WARM) != 0) ? "WARM" : "BITE"));
    AwtoPutStr(" MAX FEED ");
    AwtoPutNum(g_stAwtoWdt.ucMaxFeed, 1);
    AwtoPutStr(" PASS ");
    AwtoPutNum(g_stAwtoWdt.ucMaxPass, 1);
    AwtoTextLine(5, AWTO_T_STYLE_TEXT);
}
#elif(_AWTO_WDT == _ON)
void AwtoOsdWdtLines(void)
{
}
#endif
