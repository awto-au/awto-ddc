// Live monitor for board pads proven unused plus the six physical keys.  The five non-power keys are decoded directly
// from the two ADC ladders; POWER is P3.0.  Sampling runs every main pass; the OSD is change-only and rate-limited,
// while the I2C-visible ring retains every transition observed by the sampler.
#if(_AWTO_DIAG == _ON)
#define AWTO_VGA_SYNC_REG          0x004E
#define AWTO_VGA_POWER_REG         0x00C6
#define AWTO_VGA_COMPARE_REG       0x00CD
#define AWTO_VGA_SOG_CTRL_REG      0x00D4
#define AWTO_VGA_ADC_REG2          0x00DA
__xdata StAwtoGpio g_stAwtoGpio;
static __xdata WORD s_usAwtoGpioDraw;
static __xdata WORD s_usAwtoGpioShown;
static __xdata WORD s_usAwtoDbgDraw;
#define AWTO_DBG_REFRESH_MS    500             // debug panel values (loop rate, clocks) change slowly: twice a second
extern void osd_tc_close(void);

__xdata BYTE g_ucAwtoIoLv[3];
__xdata BYTE g_ucAwtoIoDirty[3];
__xdata BYTE g_ucAwtoIoAny;
// Board IO from the pin ledger (docs/monitors/rtd2795t-216-pin-ledger.tsv): page FE PORTxy_PIN_REG bit 0 (bus value, SDK sets FE60 = 0xFF); P1.x via FFE2.
const __code BYTE tAwtoIoPin[AWTO_IO_N] = {194, 113, 1, 14, 97, 198, 204, 206, 207, 208, 196, 159, 161, 184, 185, 201, 202, 190};
static const __code WORD tAwtoIoAddr[AWTO_IO_N] = {0xFE28, 0xFE05, 0xFFE2, 0xFFE2, 0xFE02, 0xFE2C, 0xFE32, 0xFE33, 0xFE34, 0xFE35,
                                                   0xFE2A, 0xFE1A, 0xFE1C, 0xFE24, 0xFE25, 0xFE2F, 0xFE30, 0xFE26};
static const __code BYTE tAwtoIoMask[AWTO_IO_N] = {1, 1, 1, 2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1};

static void AwtoVgaDiagPower(bit bOn)
{
    if(bOn != 0)
    {
        ScalerSetBit(AWTO_VGA_POWER_REG, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0),
                     (_BIT7 | _BIT6 | _BIT5 | _BIT3 | _BIT2 | _BIT1 | _BIT0));
        ScalerSetBit(AWTO_VGA_SOG_CTRL_REG, ~(_BIT3 | _BIT1), _BIT3);
        ScalerSetBit(AWTO_VGA_ADC_REG2, ~(_BIT1 | _BIT0), _BIT0);
    }
    else
    {
        ScalerSetBit(AWTO_VGA_SOG_CTRL_REG, ~(_BIT3 | _BIT1), _BIT1);
        ScalerSetBit(AWTO_VGA_POWER_REG, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _BIT4);
    }
}

static WORD AwtoGpioNow(void)
{
    WORD usNow;
    do { usNow = g_stAwtoDiag.usT2Isr; } while(usNow != g_stAwtoDiag.usT2Isr);
    return usNow;
}

static WORD AwtoGpioRead(void)
{
    BYTE ucP1 = MCU_FFE2_PORT1_PIN_REG;
    BYTE ucP3 = MCU_FFE3_PORT3_PIN_REG;
    BYTE ucA0 = PCB_ADKEY1();
    BYTE ucA1 = PCB_ADKEY2();
    WORD usV = (WORD)((ucP1 >> 2) & 0x3F);       // bits 0..5 = package pins 65..70 / P1.2..P1.7

    usV |= (WORD)((ucP3 >> 1) & 0x03) << 6;     // bits 6..7 = package pins 74..75 / P3.1..P3.2
    if(MCU_FF0B_ADC_A2_CONVERT_RESULT >= 0x80) usV |= (WORD)1 << 8; // bit 8 = ADC2 above nominal half scale
    if(AWTO_KEY_BAND(ucA1, 0x68, 0x88)) usV |= (WORD)1 << 9;   // SOURCE
    if(AWTO_KEY_BAND(ucA0, 0xC0, 0xE0)) usV |= (WORD)1 << 10;  // MENU
    if(AWTO_KEY_BAND(ucA1, 0x28, 0x48)) usV |= (WORD)1 << 11;  // DOWN
    if(AWTO_KEY_BAND(ucA0, 0x28, 0x48)) usV |= (WORD)1 << 12;  // UP
    if(AWTO_KEY_BAND(ucA0, 0x70, 0x90)) usV |= (WORD)1 << 13;  // AUTO
    if(P3_0 == 0) usV |= (WORD)1 << 14;                         // POWER
    return usV;
}

static void AwtoIoSample(BYTE ucMode);

static void AwtoGpioEnsure(void)
{
    BYTE __xdata *puc = (BYTE __xdata *)&g_stAwtoGpio;
    WORD usI, usV;

    if((g_stAwtoGpio.ucMagic0 == 'G') && (g_stAwtoGpio.ucMagic1 == 'P') &&
       (g_stAwtoGpio.ucVersion == 3)) return;
    for(usI = 0; usI < sizeof(StAwtoGpio); usI++) puc[usI] = 0;
    usV = AwtoGpioRead();
    g_stAwtoGpio.ucMagic0 = 'G';
    g_stAwtoGpio.ucMagic1 = 'P';
    g_stAwtoGpio.ucVersion = 3;
    g_stAwtoGpio.ucLevelsLo = (BYTE)usV;
    g_stAwtoGpio.ucLevelsHi = (BYTE)(usV >> 8);
    g_stAwtoGpio.ucDirtyLo = 0xFF;
    g_stAwtoGpio.ucDirtyHi = 0x7F;
    g_stAwtoGpio.ucAdc0 = PCB_ADKEY1();
    g_stAwtoGpio.ucAdc1 = PCB_ADKEY2();
    g_stAwtoGpio.ucAdc2 = MCU_FF0B_ADC_A2_CONVERT_RESULT;
    g_stAwtoGpio.ucVgaSync = ScalerGetByte(AWTO_VGA_SYNC_REG);
    g_stAwtoGpio.ucVgaCompare = ScalerGetByte(AWTO_VGA_COMPARE_REG);
    g_stAwtoGpio.ucVgaPower = ScalerGetByte(AWTO_VGA_POWER_REG);
    g_stAwtoGpio.ucVgaDirty = 1;
    s_usAwtoGpioShown = usV;
    AwtoIoSample(2);
}

static void AwtoGpioLog(BYTE ucPin, BYTE ucState, WORD usNow)
{
    BYTE ucI = g_stAwtoGpio.ucSeq & (AWTO_GPIO_LOG_N - 1);
    g_stAwtoGpio.pstLog[ucI].ucSeq = g_stAwtoGpio.ucSeq;
    g_stAwtoGpio.pstLog[ucI].ucTickHi = (BYTE)(usNow >> 8);
    g_stAwtoGpio.pstLog[ucI].ucTickLo = (BYTE)usNow;
    g_stAwtoGpio.pstLog[ucI].ucPinState = (BYTE)(ucPin << 1) | (ucState & 1);
    g_stAwtoGpio.ucSeq++;
}

// ucMode 0: log changes into the transition ring (index 16 + row), 1: mark every row dirty (screen open), 2: take levels quietly.
static void AwtoIoSample(BYTE ucMode)
{
    BYTE ucI, ucV, ucB, ucX;
    WORD usNow = 0;

    for(ucI = 0; ucI < AWTO_IO_N; ucI++)
    {
        ucV = ((*(__xdata volatile BYTE *)tAwtoIoAddr[ucI]) & tAwtoIoMask[ucI]) != 0;
        ucB = (BYTE)1 << (ucI & 7);
        ucX = ucI >> 3;
        if((ucMode != 0) || ((((g_ucAwtoIoLv[ucX] & ucB) != 0) ? 1 : 0) != ucV))
        {
            if((ucMode == 0) && (usNow == 0)) usNow = AwtoGpioNow();
            if(ucMode == 0) AwtoGpioLog(AWTO_GPIO_IO_BASE + ucI, ucV, usNow);
            if(ucV != 0) g_ucAwtoIoLv[ucX] |= ucB; else g_ucAwtoIoLv[ucX] &= ~ucB;
            g_ucAwtoIoDirty[ucX] |= ucB;
            g_ucAwtoIoAny = 1;
        }
    }
}

void AwtoGpioPoll(void)
{
    WORD usOld, usNew, usDiff, usNow;
    BYTE ucI, ucA0, ucA1, ucA2, ucVgaSync, ucVgaCompare, ucVgaPower;

    AwtoGpioEnsure();
    usOld = (WORD)g_stAwtoGpio.ucLevelsLo | (WORD)g_stAwtoGpio.ucLevelsHi << 8;
    usNew = AwtoGpioRead();
    ucA0 = PCB_ADKEY1();
    ucA1 = PCB_ADKEY2();
    ucA2 = MCU_FF0B_ADC_A2_CONVERT_RESULT;
    usDiff = (usOld ^ usNew) & 0x7FFF;
    if(usDiff != 0)
    {
        usNow = AwtoGpioNow();
        g_stAwtoGpio.ucLevelsLo = (BYTE)usNew;
        g_stAwtoGpio.ucLevelsHi = (BYTE)(usNew >> 8);
        g_stAwtoGpio.ucChangedLo |= (BYTE)usDiff;
        g_stAwtoGpio.ucChangedHi |= (BYTE)(usDiff >> 8);
        g_stAwtoGpio.ucDirtyLo |= (BYTE)usDiff;
        g_stAwtoGpio.ucDirtyHi |= (BYTE)(usDiff >> 8);
        for(ucI = 0; ucI < AWTO_GPIO_N; ucI++)
            if((usDiff & ((WORD)1 << ucI)) != 0) AwtoGpioLog(ucI, (BYTE)(usNew >> ucI), usNow);
    }
    if(ucA0 != g_stAwtoGpio.ucAdc0)
    {
        g_stAwtoGpio.ucAdc0 = ucA0;
        g_stAwtoGpio.ucDirtyHi |= 0x34;          // MENU, UP, AUTO rows
    }
    if(ucA1 != g_stAwtoGpio.ucAdc1)
    {
        g_stAwtoGpio.ucAdc1 = ucA1;
        g_stAwtoGpio.ucDirtyHi |= 0x0A;          // SOURCE, DOWN rows
    }
    if(ucA2 != g_stAwtoGpio.ucAdc2)
    {
        g_stAwtoGpio.ucAdc2 = ucA2;
        g_stAwtoGpio.ucDirtyHi |= 0x01;          // ADC2 / pin 96 row
    }
    ucVgaSync = ScalerGetByte(AWTO_VGA_SYNC_REG);
    ucVgaCompare = ScalerGetByte(AWTO_VGA_COMPARE_REG);
    ucVgaPower = ScalerGetByte(AWTO_VGA_POWER_REG);
    if((ucVgaSync != g_stAwtoGpio.ucVgaSync) || (ucVgaCompare != g_stAwtoGpio.ucVgaCompare) ||
       (ucVgaPower != g_stAwtoGpio.ucVgaPower))
    {
        g_stAwtoGpio.ucVgaSync = ucVgaSync;
        g_stAwtoGpio.ucVgaCompare = ucVgaCompare;
        g_stAwtoGpio.ucVgaPower = ucVgaPower;
        g_stAwtoGpio.ucVgaDirty = 1;
    }
    AwtoIoSample(0);
    if(g_stAwtoGpio.ucOpen == 0) return;
    if((WORD)(AwtoGpioNow() - s_usAwtoDbgDraw) >= AWTO_DBG_REFRESH_MS)
    {
        s_usAwtoDbgDraw = AwtoGpioNow();
        AwtoOsdDebugLines();
    }
    if((GET_OSD_EVENT_MESSAGE() >= _OSDEVENT_SHOW_NOSIGNAL_MSG) &&
       (GET_OSD_EVENT_MESSAGE() <= _OSDEVENT_ACTIVE_DO_ONE_TIME_MSG)) SET_OSD_EVENT_MESSAGE(_OSDEVENT_NONE_MSG);
    if((g_stAwtoGpio.ucDrawn == 0) && ((WORD)(AwtoGpioNow() - s_usAwtoGpioDraw) >= AWTO_KEY_RETRY_MS))
    {
        s_usAwtoGpioDraw = AwtoGpioNow();
        AwtoOsdGpioLines();                    // own text layer (Spleen), not the SDK message card
        return;
    }
    if((g_stAwtoGpio.ucDrawn != 0) && ((g_stAwtoGpio.ucDirtyLo != 0) || (g_stAwtoGpio.ucDirtyHi != 0) || (g_stAwtoGpio.ucVgaDirty != 0) || (g_ucAwtoIoAny != 0)) &&
       ((WORD)(AwtoGpioNow() - s_usAwtoGpioDraw) >= AWTO_GPIO_REFRESH_MS))
    {
        s_usAwtoGpioShown = usNew;
        s_usAwtoGpioDraw = AwtoGpioNow();
        AwtoOsdGpioLines();
    }
}

void AwtoGpioConSet(BYTE ucOn)                 // the console opens / closes this panel's sampling (AwtoDiagConsole draws it)
{
    AwtoGpioEnsure();
    g_stAwtoGpio.ucDrawn = 0;
    if(ucOn != 0)
    {
        AwtoVgaDiagPower(1);
        g_stAwtoGpio.ucOpen = 1;
        g_stAwtoGpio.ucDirtyLo = 0xFF;
        g_stAwtoGpio.ucDirtyHi = 0x7F;
        g_stAwtoGpio.ucVgaDirty = 1;
        AwtoIoSample(1);
        s_usAwtoGpioShown = AwtoGpioRead();
        s_usAwtoGpioDraw = AwtoGpioNow();
    }
    else
    {
        g_stAwtoGpio.ucOpen = 0;
        AwtoVgaDiagPower(0);
    }
}

void AwtoGpioTestSet(BYTE ucOn)                 // menu "GPIO inputs", test cmd 0x43 / 0x44: the diagnostic console
{
    AwtoDiagConsole(ucOn);
}
#endif
