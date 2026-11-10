// Tall input diagnostic: one row per input, drawn with the awto menu's Spleen text layer (osd_tc_*, ui_text), not the SDK proportional font.
#if(_AWTO_DIAG == _ON)
#ifdef _AWTO_NEW_SETTINGS
#define AWTO_G_ROW_ADC      8                           // rows: 8 digital, ADC0..2, POWER, 9 VGA
#define AWTO_G_ROW_POWER    11
#define AWTO_G_ROW_VGA      12                          // rows: 8 digital, ADC0..2, POWER, 9 VGA, then the board IO rows
#define AWTO_G_ROW_IO       21
#define AWTO_G_ROWS         (AWTO_G_ROW_IO + AWTO_IO_N)
#define AWTO_G_LINES        (AWTO_G_ROWS + 3)           // title, header, rows, footer: 42 lines in the 5x8 font
#define AWTO_G_L_FIRST      2
#define AWTO_TCOL_NAME      1
#define AWTO_TCOL_PIN       8
#define AWTO_TCOL_STATE     12
#define AWTO_TCOL_RAW       15
#define AWTO_TCOL_VALUE     20

static WORD AwtoGpioOsdValue(void)
{
    return (WORD)g_stAwtoGpio.ucLevelsLo | (WORD)g_stAwtoGpio.ucLevelsHi << 8;
}

static bit AwtoGpioOsdDirty(BYTE ucI, bit bAll)
{
    if(bAll != 0) return 1;
    if(ucI < 8) return (g_stAwtoGpio.ucDirtyLo & ((BYTE)1 << ucI)) != 0;
    return (g_stAwtoGpio.ucDirtyHi & ((BYTE)1 << (ucI - 8))) != 0;
}

static void AwtoTableName(BYTE ucName)
{
    switch(ucName)
    {
        case 0: AwtoPutStr("GPIO"); break;
        case 7: AwtoPutStr("POWER"); break;
        case 8: AwtoPutStr("AVS"); break;
        case 9: AwtoPutStr("AHS"); break;
        case 10: AwtoPutStr("BM"); break;
        case 11: AwtoPutStr("BP"); break;
        case 12: AwtoPutStr("GM"); break;
        case 13: AwtoPutStr("GP"); break;
        case 14: AwtoPutStr("SOG"); break;
        case 15: AwtoPutStr("RM"); break;
        default: AwtoPutStr("RP"); break;
    }
}

static void AwtoInputDigital(BYTE ucI, BYTE ucPin)
{
    AwtoPutCol(AWTO_TCOL_NAME); AwtoTableName(0);
    AwtoPutCol(AWTO_TCOL_PIN); AwtoPutNum(ucPin, 2);
    AwtoPutCol(AWTO_TCOL_STATE); AwtoPutNum((AwtoGpioOsdValue() >> ucI) & 1, 1);
    AwtoPutCol(AWTO_TCOL_RAW); AwtoPutChar('-');
    AwtoPutCol(AWTO_TCOL_VALUE); AwtoPutStr("DIGITAL");
    AwtoTextLine(AWTO_G_L_FIRST + ucI, AWTO_T_STYLE_TEXT);
}

// One line per ADC converter: raw and volts.
static void AwtoInputAdc(BYTE ucCh, BYTE ucRaw)
{
    AwtoPutCol(AWTO_TCOL_NAME); AwtoPutStr("ADC"); AwtoPutNum(ucCh, 1);
    AwtoPutCol(AWTO_TCOL_PIN);
    if(ucCh < 2) { AwtoPutChar('A'); AwtoPutNum(ucCh, 1); } else AwtoPutNum(96, 2);
    AwtoPutCol(AWTO_TCOL_STATE); AwtoPutChar('-');
    AwtoPutCol(AWTO_TCOL_RAW); AwtoPutNum(ucRaw, 3);
    AwtoPutCol(AWTO_TCOL_VALUE); AwtoPutVolt(ucRaw);
    AwtoTextLine(AWTO_G_L_FIRST + AWTO_G_ROW_ADC + ucCh, AWTO_T_STYLE_TEXT);
}

static void AwtoInputPower(void)
{
    AwtoPutCol(AWTO_TCOL_NAME); AwtoTableName(7);
    AwtoPutCol(AWTO_TCOL_PIN); AwtoPutStr("P30");
    AwtoPutCol(AWTO_TCOL_STATE); AwtoPutNum((AwtoGpioOsdValue() >> 14) & 1, 1);
    AwtoPutCol(AWTO_TCOL_RAW); AwtoPutChar('-');
    AwtoPutCol(AWTO_TCOL_VALUE); AwtoPutStr("DIGITAL");
    AwtoTextLine(AWTO_G_L_FIRST + AWTO_G_ROW_POWER, AWTO_T_STYLE_TEXT);
}

static void AwtoIoName(BYTE ucI)
{
    switch(ucI)
    {
        case 0: AwtoPutStr("IR"); break;
        case 1: AwtoPutStr("HPSEL"); break;
        case 2: AwtoPutStr("H2HPD"); break;
        case 3: AwtoPutStr("H1HPD"); break;
        case 4: AwtoPutStr("DPHPD"); break;
        case 5: AwtoPutStr("H2CBL"); break;
        case 6: AwtoPutStr("H1CBL"); break;
        case 7: AwtoPutStr("DPS17"); break;
        case 8: AwtoPutStr("DPS15"); break;
        case 9: AwtoPutStr("DPS16"); break;
        case 10: AwtoPutStr("BLEN"); break;
        case 11: AwtoPutStr("PNLPW"); break;
        case 12: AwtoPutStr("MUTE"); break;
        case 13: AwtoPutStr("PWR1"); break;
        case 14: AwtoPutStr("PWR2"); break;
        case 15: AwtoPutStr("PWR3"); break;
        case 16: AwtoPutStr("PWR4"); break;
        default: AwtoPutStr("FLWP"); break;
    }
}

static void AwtoInputIo(BYTE ucI)
{
    AwtoPutCol(AWTO_TCOL_NAME); AwtoIoName(ucI);
    AwtoPutCol(AWTO_TCOL_PIN); AwtoPutNum(tAwtoIoPin[ucI], 1);
    AwtoPutCol(AWTO_TCOL_STATE); AwtoPutNum((g_ucAwtoIoLv[ucI >> 3] >> (ucI & 7)) & 1, 1);
    AwtoPutCol(AWTO_TCOL_RAW); AwtoPutChar('-');
    AwtoPutCol(AWTO_TCOL_VALUE); AwtoPutStr((ucI < 10) ? "IN" : "OUT");
    AwtoTextLine(AWTO_G_L_FIRST + AWTO_G_ROW_IO + ucI, AWTO_T_STYLE_TEXT);
}

static void AwtoInputVga(BYTE ucI, BYTE ucPin, BYTE ucName, BYTE ucRaw, bit bSync)
{
    AwtoPutCol(AWTO_TCOL_NAME); AwtoTableName(ucName);
    AwtoPutCol(AWTO_TCOL_PIN); AwtoPutNum(ucPin, 2);
    AwtoPutCol(AWTO_TCOL_STATE); AwtoPutChar('-');
    AwtoPutCol(AWTO_TCOL_RAW); AwtoPutHex2(ucRaw);
    AwtoPutCol(AWTO_TCOL_VALUE); AwtoPutStr((bSync != 0) ? "SYNC" : "CMP");
    AwtoTextLine(AWTO_G_L_FIRST + AWTO_G_ROW_VGA + ucI, AWTO_T_STYLE_TEXT);
}

static void AwtoTableStatic(void)
{
    AwtoPutCol(1); AwtoPutStr("GPIO INPUT DIAGNOSTICS");
    AwtoTextLine(0, AWTO_T_STYLE_ACCENT);
    AwtoPutCol(AWTO_TCOL_NAME); AwtoPutStr("INPUT");
    AwtoPutCol(AWTO_TCOL_PIN); AwtoPutStr("PIN");
    AwtoPutCol(AWTO_TCOL_STATE); AwtoPutStr("S");
    AwtoPutCol(AWTO_TCOL_RAW); AwtoPutStr("RAW");
    AwtoPutCol(AWTO_TCOL_VALUE); AwtoPutStr("VALUE");
    AwtoTextLine(1, AWTO_T_STYLE_ACCENT);
}

static void AwtoTableFooter(void)
{
    AwtoPutCol(1); AwtoPutStr("I2C 44 CLOSE");
    AwtoTextLine(AWTO_G_L_FIRST + AWTO_G_ROWS, AWTO_T_STYLE_ACCENT);
}

void AwtoOsdGpioLines(void)
{
    bit bAll = (g_stAwtoGpio.ucDrawn == 0);
    BYTE ucI;

    AwtoPanel(0);
    if(bAll != 0)
    {
        AwtoTableStatic();
    }
    {
        if(AwtoGpioOsdDirty(0, bAll)) AwtoInputDigital(0, 65);
        if(AwtoGpioOsdDirty(1, bAll)) AwtoInputDigital(1, 66);
        if(AwtoGpioOsdDirty(2, bAll)) AwtoInputDigital(2, 67);
        if(AwtoGpioOsdDirty(3, bAll)) AwtoInputDigital(3, 68);
        if(AwtoGpioOsdDirty(4, bAll)) AwtoInputDigital(4, 69);
        if(AwtoGpioOsdDirty(5, bAll)) AwtoInputDigital(5, 70);
        if(AwtoGpioOsdDirty(6, bAll)) AwtoInputDigital(6, 74);
        if(AwtoGpioOsdDirty(7, bAll)) AwtoInputDigital(7, 75);
        if((bAll != 0) || ((g_stAwtoGpio.ucDirtyHi & 0x34) != 0)) AwtoInputAdc(0, g_stAwtoGpio.ucAdc0);
        if((bAll != 0) || ((g_stAwtoGpio.ucDirtyHi & 0x0A) != 0)) AwtoInputAdc(1, g_stAwtoGpio.ucAdc1);
        if(AwtoGpioOsdDirty(8, bAll)) AwtoInputAdc(2, g_stAwtoGpio.ucAdc2);
        if(AwtoGpioOsdDirty(14, bAll)) AwtoInputPower();

        if((bAll != 0) || (g_stAwtoGpio.ucVgaDirty != 0))
        {
            AwtoInputVga(0, 55, 8, g_stAwtoGpio.ucVgaSync, 1);
            AwtoInputVga(1, 56, 9, g_stAwtoGpio.ucVgaSync, 1);
            AwtoInputVga(2, 57, 10, g_stAwtoGpio.ucVgaCompare, 0);
            AwtoInputVga(3, 58, 11, g_stAwtoGpio.ucVgaCompare, 0);
            AwtoInputVga(4, 59, 12, g_stAwtoGpio.ucVgaCompare, 0);
            AwtoInputVga(5, 60, 13, g_stAwtoGpio.ucVgaCompare, 0);
            AwtoInputVga(6, 61, 14, g_stAwtoGpio.ucVgaSync, 1);
            AwtoInputVga(7, 62, 15, g_stAwtoGpio.ucVgaCompare, 0);
            AwtoInputVga(8, 63, 16, g_stAwtoGpio.ucVgaCompare, 0);
        }
    }
    {
        for(ucI = 0; ucI < AWTO_IO_N; ucI++)
        {
            if((bAll != 0) || ((g_ucAwtoIoDirty[ucI >> 3] & ((BYTE)1 << (ucI & 7))) != 0)) AwtoInputIo(ucI);
        }
    }
    g_ucAwtoIoDirty[0] = 0; g_ucAwtoIoDirty[1] = 0; g_ucAwtoIoDirty[2] = 0; g_ucAwtoIoAny = 0;

    AwtoTableFooter();
    g_stAwtoGpio.ucDirtyLo = 0;
    g_stAwtoGpio.ucDirtyHi = 0;
    g_stAwtoGpio.ucVgaDirty = 0;
    g_stAwtoGpio.ucDrawn = 1;
    g_stAwtoGpio.ucRedraws++;
}
#else
void AwtoOsdGpioLines(void)
{
}
#endif
#endif
