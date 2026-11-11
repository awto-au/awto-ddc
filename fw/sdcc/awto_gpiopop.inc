// Diagnostic input table on the console (panel 0): one row per input in fw/awto/inputs.tsv, drawn with the Spleen text layer.
// The whole row is drawn once (console open); after that only the changed field of a changed input is written, at its exact column.
#if(_AWTO_DIAG == _ON)
#ifdef _AWTO_NEW_SETTINGS
#define AWTO_G_ROWS         AWTO_IN_ROWS
#define AWTO_G_LINES        (AWTO_G_ROWS + 3)           // title, header, rows, footer: 42 lines in the 5x8 font
#define AWTO_G_L_FIRST      2
#define AWTO_TCOL_NAME      1
#define AWTO_TCOL_PIN       8
#define AWTO_TCOL_STATE     12
#define AWTO_TCOL_RAW       15
#define AWTO_TCOL_VALUE     20
#define AWTO_TCOL_DESC      28

// GENERATED-BEGIN awto_inputs
// kind 0 bit, 1 analog (deadband), 2 byte; src: see awto_gpio.inc AwtoInRead; flags bit0 = screen row, bit1 = logged in the ring
static const __code BYTE tAwtoInKindS[AWTO_IN_N] = {
    0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0,
    2, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0};
static const __code BYTE tAwtoInPinS[AWTO_IN_N] = {
    65, 66, 67, 68, 69, 70, 74, 75, 94, 95, 96, 71,
    55, 56, 57, 58, 59, 60, 61, 62, 63, 194, 113, 1,
    14, 97, 198, 204, 206, 207, 208, 196, 159, 161, 184, 185,
    201, 202, 190, 0, 0, 0, 0, 0};
static const __code BYTE tAwtoInFlagsS[AWTO_IN_N] = {
    3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 3, 3, 3,
    3, 3, 3, 3, 1, 1, 1, 3, 3, 3, 3, 3,
    3, 3, 3, 2, 2, 2, 2, 2};

static void AwtoInName(BYTE ucI)
{
    switch(ucI)
    {
        case 0:
        case 1:
        case 2:
        case 3:
        case 4:
        case 5:
        case 6:
        case 7:
            AwtoPutStr("GPIO"); break;
        case 8:
            AwtoPutStr("ADC0"); break;
        case 9:
            AwtoPutStr("ADC1"); break;
        case 10:
            AwtoPutStr("ADC2"); break;
        case 11:
            AwtoPutStr("POWER"); break;
        case 12:
            AwtoPutStr("AVS"); break;
        case 13:
            AwtoPutStr("AHS"); break;
        case 14:
            AwtoPutStr("BM"); break;
        case 15:
            AwtoPutStr("BP"); break;
        case 16:
            AwtoPutStr("GM"); break;
        case 17:
            AwtoPutStr("GP"); break;
        case 18:
            AwtoPutStr("SOG"); break;
        case 19:
            AwtoPutStr("RM"); break;
        case 20:
            AwtoPutStr("RP"); break;
        case 21:
            AwtoPutStr("IR"); break;
        case 22:
            AwtoPutStr("HPSEL"); break;
        case 23:
            AwtoPutStr("H2HPD"); break;
        case 24:
            AwtoPutStr("H1HPD"); break;
        case 25:
            AwtoPutStr("DPHPD"); break;
        case 26:
            AwtoPutStr("H2CBL"); break;
        case 27:
            AwtoPutStr("H1CBL"); break;
        case 28:
            AwtoPutStr("DPS17"); break;
        case 29:
            AwtoPutStr("DPS15"); break;
        case 30:
            AwtoPutStr("DPS16"); break;
        case 31:
            AwtoPutStr("BLEN"); break;
        case 32:
            AwtoPutStr("PNLPW"); break;
        case 33:
            AwtoPutStr("MUTE"); break;
        case 34:
            AwtoPutStr("PWR1"); break;
        case 35:
            AwtoPutStr("PWR2"); break;
        case 36:
            AwtoPutStr("PWR3"); break;
        case 37:
            AwtoPutStr("PWR4"); break;
        case 38:
            AwtoPutStr("FLWP"); break;
        case 39:
            AwtoPutStr("SOURCE"); break;
        case 40:
            AwtoPutStr("MENU"); break;
        case 41:
            AwtoPutStr("DOWN"); break;
        case 42:
            AwtoPutStr("UP"); break;
        case 43:
            AwtoPutStr("AUTO"); break;
        default: break;
    }
}

static void AwtoInText(BYTE ucI)
{
    switch(ucI)
    {
        case 0:
        case 1:
        case 2:
        case 3:
        case 4:
        case 5:
        case 6:
        case 7:
        case 11:
            AwtoPutStr("DIGITAL"); break;
        case 8:
        case 9:
        case 10:
            AwtoPutStr("VOLT"); break;
        case 12:
        case 13:
        case 18:
            AwtoPutStr("SYNC"); break;
        case 14:
        case 15:
        case 16:
        case 17:
        case 19:
        case 20:
            AwtoPutStr("CMP"); break;
        case 21:
        case 22:
        case 23:
        case 24:
        case 25:
        case 26:
        case 27:
        case 28:
        case 29:
        case 30:
            AwtoPutStr("IN"); break;
        case 31:
        case 32:
        case 33:
        case 34:
        case 35:
        case 36:
        case 37:
        case 38:
            AwtoPutStr("OUT"); break;
        default: break;
    }
}

#define AWTO_TXT_DESCHDR       44
#define AWTO_TXT_LOGHDR        45
#define AWTO_TXT_MS            46
#define AWTO_TXT_MARK          47
static const __code char tAwtoTxtS[] = "spare pad, high-Z input\0key ladder A0: MENU UP AUTO\0key ladder A1: SOURCE DOWN\0spare ADC, 3.3 V full scale\0front POWER key, 1 = pressed\0analog VGA vertical sync\0analog VGA horizontal sync\0VGA blue- compare flag\0VGA blue+ compare flag\0VGA green- compare flag\0VGA green+ compare flag\0VGA sync on green\0VGA red- compare flag\0VGA red+ compare flag\0IR receiver, idle high\0speaker / headphone select\0HDMI-2 hot-plug output\0HDMI-1 hot-plug output\0DisplayPort hot-plug output\0HDMI-2 cable detect, 0 = cable\0HDMI-1 cable detect, 0 = cable\0DP connector pin 17 (AUX-)\0DP connector pin 15 (AUX+)\0DP connector pin 16 (GND)\0backlight enable, 0 = on\0panel power enable, 1 = on\0speaker amp, 1 = enabled\0power-state output P8.4\0power-state output P8.5\0power-state open drain P9.7\0power-state open drain PA.0\0SPI flash write protect\0\0DESCRIPTION\0EVENT LOG - UP / DOWN SCROLLS THE SCREEN\0 MS  \0-----\0";
static const __code WORD tAwtoTxtOffS[48] = {0, 0, 0, 0, 0, 0, 0, 0, 24, 52, 79, 107, 136, 161, 188, 211, 234, 258, 282, 300, 322, 344, 367, 394, 417, 440, 468, 499, 530, 557, 584, 610, 635, 662, 687, 711, 735, 763, 791, 815, 815, 815, 815, 815, 816, 828, 869, 875};
static void AwtoTxt(BYTE ucI)                  // input description (0..AWTO_IN_N-1) or AWTO_TXT_*
{
    const __code char *pc = &tAwtoTxtS[tAwtoTxtOffS[ucI]];

    while(*pc != 0)
    {
        AwtoPutChar(*pc);
        pc++;
    }
}
// GENERATED-END awto_inputs

static BYTE AwtoInStyle(BYTE ucI)               // red = not in the I2C ring (inputs.tsv log = n)
{
    return ((tAwtoInFlagsS[ucI] & 2) != 0) ? AWTO_T_STYLE_TEXT : AWTO_T_STYLE_ALERT;
}

static void AwtoInRowFull(BYTE ucI)
{
    BYTE ucV = g_stAwtoGpio.ucIn[ucI];
    BYTE ucK = tAwtoInKindS[ucI];

    AwtoPutCol(AWTO_TCOL_NAME); AwtoInName(ucI);
    AwtoPutCol(AWTO_TCOL_PIN); AwtoPutNum(tAwtoInPinS[ucI], 1);
    AwtoPutCol(AWTO_TCOL_STATE);
    if(ucK == 0) AwtoPutNum(ucV, 1); else AwtoPutChar('-');
    AwtoPutCol(AWTO_TCOL_RAW);
    if(ucK == 1) AwtoPutNum(ucV, 3); else if(ucK == 2) AwtoPutHex2(ucV); else AwtoPutChar('-');
    AwtoPutCol(AWTO_TCOL_VALUE);
    if(ucK == 1) AwtoPutVolt(ucV); else AwtoInText(ucI);
    AwtoPutCol(AWTO_TCOL_DESC); AwtoTxt(ucI);
    AwtoTextLine(AWTO_G_L_FIRST + ucI, AwtoInStyle(ucI));
}

static void AwtoInRowField(BYTE ucI)
{
    BYTE ucV = g_stAwtoGpio.ucIn[ucI];
    BYTE ucK = tAwtoInKindS[ucI];

    AwtoFieldBegin();
    if(ucK == 0)
    {
        AwtoPutNum(ucV, 1);
        AwtoFieldEnd(AWTO_G_L_FIRST + ucI, AWTO_TCOL_STATE, AwtoInStyle(ucI));
    }
    else if(ucK == 1)
    {
        AwtoPutNum(ucV, 3);
        AwtoFieldEnd(AWTO_G_L_FIRST + ucI, AWTO_TCOL_RAW, AwtoInStyle(ucI));
        AwtoFieldBegin();
        AwtoPutVolt(ucV);
        AwtoFieldEnd(AWTO_G_L_FIRST + ucI, AWTO_TCOL_VALUE, AwtoInStyle(ucI));
    }
    else
    {
        AwtoPutHex2(ucV);
        AwtoFieldEnd(AWTO_G_L_FIRST + ucI, AWTO_TCOL_RAW, AwtoInStyle(ucI));
    }
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
    AwtoPutCol(AWTO_TCOL_DESC); AwtoTxt(AWTO_TXT_DESCHDR);
    AwtoTextLine(1, AWTO_T_STYLE_ACCENT);
    AwtoPutCol(1); AwtoPutStr("I2C 44 CLOSE");
    AwtoTextLine(AWTO_G_L_FIRST + AWTO_G_ROWS, AWTO_T_STYLE_ACCENT);
    AwtoPutCol(1); AwtoPutStr("RED = NOT IN THE I2C CHANGE LOG");
    AwtoTextLine(AWTO_G_L_FIRST + AWTO_G_ROWS + 1, AWTO_T_STYLE_ALERT);
}

void AwtoOsdGpioLines(void)
{
    bit bAll = (g_stAwtoGpio.ucDrawn == 0);
    BYTE ucI;

    if(AwtoConLost() != 0) return;
    AwtoPanel(0);
    if(bAll != 0)
    {
        AwtoTableStatic();
    }
    for(ucI = 0; ucI < AWTO_G_ROWS; ucI++)
    {
        if(bAll != 0)
        {
            AwtoInRowFull(ucI);
        }
        else if((g_stAwtoGpio.ucDirty[ucI >> 3] & ((BYTE)1 << (ucI & 7))) != 0)
        {
            AwtoInRowField(ucI);
        }
    }
    for(ucI = 0; ucI < (AWTO_IN_N + 7) / 8; ucI++)
    {
        g_stAwtoGpio.ucDirty[ucI] = 0;
    }
    g_stAwtoGpio.ucAny = 0;
    g_stAwtoGpio.ucDrawn = 1;
    g_stAwtoGpio.ucRedraws++;
}

// Event log (right of the inputs panel, #144): one line per input change / sync line, newest above the "-----" marker.
static __xdata BYTE s_ucLogHead;

static __xdata BYTE s_ucConSyncSeq;             // #139: sync ring seq the log has shown up to

void AwtoConLogInit(void)
{
    s_ucLogHead = 0;
    s_ucPanelCol = AWTO_LOG_COL;
    s_ucAwtoCols = AWTO_LOG_W;
    s_ucPanelRow = AWTO_LOG_HDR;
    s_pcAwtoRow[0] = ' ';
    s_ucAwtoLen = 1;
    AwtoTxt(AWTO_TXT_LOGHDR);
    AwtoTextLine(0, AWTO_T_STYLE_ACCENT);
    s_ucConSyncSeq = (AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, g_stAwtoSync.ucEpSeq) <= AWTO_SYNC_N) ? g_stAwtoSync.ucEpSeq :
                     AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, AWTO_SYNC_N);   // backfill the current episode (what the ring still has)
    AwtoConLogSync();
}

static void AwtoConLogStart(void)               // next log row: compose with AwtoPut*, then AwtoConLogEnd
{
    s_ucPanelCol = AWTO_LOG_COL;
    s_ucAwtoCols = AWTO_LOG_W;
    s_ucPanelRow = AWTO_LOG_ROW0 + s_ucLogHead;
    s_pcAwtoRow[0] = ' ';
    s_ucAwtoLen = 1;
}

static void AwtoConLogEnd(void)
{
    AwtoTextLine(0, AWTO_T_STYLE_TEXT);
    s_ucLogHead = (s_ucLogHead + 1 >= AWTO_LOG_LINES) ? 0 : (s_ucLogHead + 1);
    s_ucPanelRow = AWTO_LOG_ROW0 + s_ucLogHead;      // marker on the next row: also blanks the oldest line
    s_pcAwtoRow[0] = ' ';
    s_ucAwtoLen = 1;
    AwtoTxt(AWTO_TXT_MARK);
    AwtoTextLine(0, AWTO_T_STYLE_ACCENT);
}

void AwtoConLogEvent(BYTE ucId, BYTE ucVal, WORD usTick)
{
    if((s_ucConOpen == 0) || (AwtoConLost() != 0))
    {
        return;
    }
    AwtoConLogStart();
    AwtoPutNum(usTick, 5); AwtoTxt(AWTO_TXT_MS); AwtoInName(ucId); AwtoPutChar(' '); AwtoPutChar(' '); AwtoPutNum(ucVal, 1);
    AwtoConLogEnd();
}

void AwtoConLogSync(void)                       // #139: new sync ring lines, one log row each (same decoder as the selector)
{
    while(s_ucConSyncSeq != g_stAwtoSync.ucSeq)
    {
        if((s_ucConOpen == 0) || (AwtoConLost() != 0))
        {
            return;
        }
        AwtoConLogStart();
        AwtoSyncLine(s_ucConSyncSeq);
        s_ucConSyncSeq = AWTO_SYNC_NEXT(s_ucConSyncSeq);
        AwtoConLogEnd();
    }
}
#else
void AwtoOsdGpioLines(void)
{
}

void AwtoConLogInit(void)
{
}

void AwtoConLogEvent(BYTE ucId, BYTE ucVal, WORD usTick)
{
    (void)ucId; (void)ucVal; (void)usTick;
}

void AwtoConLogSync(void)
{
}
#endif
#endif
