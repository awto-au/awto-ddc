// Watchdog panel of the diagnostic console (#131): last bite from g_stAwtoWdt; at the end of RTD2014OsdDisplay.c (after awto_dbgpop.inc).
#if((_AWTO_WDT == _ON) && (defined(_AWTO_NEW_SETTINGS)))
#define AWTO_WDT_POP_COL    79                  // #144: right of the debug panel, below the console view
#define AWTO_WDT_POP_ROW    52
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
        AwtoPutStr(((ucC & 0x3F) == AWTO_WDT_C_STALL) ? "STALL" : "?");
        AwtoPutStr(((ucC & AWTO_WDT_C_TMODE) != 0) ? " TMODE" : "");
        AwtoPutStr(((ucC & AWTO_WDT_C_TEST) != 0) ? " TEST" : "");
        AwtoPutStr("  PASS AGE ");
        AwtoPutNum(((WORD)g_stAwtoWdt.ucPassAgeHi << 8) | g_stAwtoWdt.ucPassAgeLo, 1);
        AwtoPutStr("MS");
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
    AwtoPutStr(((g_stAwtoWdt.ucBoot & AWTO_WDT_B_COLD) != 0) ? "COLD" : ((g_stAwtoWdt.ucBoot & AWTO_WDT_B_AFTER) != 0) ? "BITE" :
               ((g_stAwtoWdt.ucBoot & AWTO_WDT_B_HWWDT) != 0) ? "HW WDT" : "WARM");
    AwtoPutStr(" MAX PASS ");                   // x32 ms; poke gap x32 CNT3 = 4.58 ms (RL6449_Project.h)
    AwtoPutNum((WORD)g_stAwtoWdt.ucMaxPass << 5, 1);
    AwtoPutStr(" POKE ");
    AwtoPutNum(((WORD)g_stAwtoWdt.ucMaxPoke * 293) >> 6, 1);
    AwtoPutStr("MS AT ");
    AwtoPutNum(g_ucAwtoPokeSite, 1);            // AWTO_WDT_S_* (#150)
    AwtoTextLine(5, AWTO_T_STYLE_TEXT);
    AwtoPutStr("PROBE ");
    AwtoPutHex2(g_stAwtoWdt.ucProbe);           // AWTO_WDT_P_*: 01 timer 02 armed 04 IRQ 08 reset 10 no reset
    AwtoTextLine(6, AWTO_T_STYLE_TEXT);
}
#elif(_AWTO_WDT == _ON)
void AwtoOsdWdtLines(void)
{
}
#endif
