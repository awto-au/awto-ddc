// Input monitor: one poller owns the value of every input in fw/awto/inputs.tsv (GPIO pads, ADCs, POWER, VGA front end, board IO,
// decoded keys). A change is stored once, logged to the I2C-visible ring and marked for the console; nothing else samples or compares.
#if(_AWTO_DIAG == _ON)
#define AWTO_VGA_SYNC_REG          AWTO_R_HSYNC_TYPE_DETECTION_FLAG
#define AWTO_VGA_POWER_REG         AWTO_R_ADC_POWER
#define AWTO_VGA_COMPARE_REG       AWTO_R_ADC_COMPARE_FLAG
#define AWTO_VGA_SOG_CTRL_REG      AWTO_R_ADC_SOG_CTRL
#define AWTO_VGA_ADC_REG2          AWTO_R_ADC_REG2
#define AWTO_IN_P1                 0
#define AWTO_IN_P3                 1
#define AWTO_IN_P30                2
#define AWTO_IN_ADC0S              3
#define AWTO_IN_ADC1S              4
#define AWTO_IN_ADC2S              5
#define AWTO_IN_VSYNC              6
#define AWTO_IN_VCMP               7
#define AWTO_IN_XREG               8
#define AWTO_IN_KEY0               9
#define AWTO_IN_KEY1               10
__xdata StAwtoGpio g_stAwtoGpio;
__xdata BYTE g_pucAwtoInCnt[(AWTO_PS_CNT_N != 0) ? AWTO_PS_CNT_N : 1];
static __xdata WORD s_usAwtoGpioDraw;
static __xdata WORD s_usAwtoDbgDraw;
static __xdata BYTE s_ucVgaSync;
static __xdata BYTE s_ucVgaCmp;
#define AWTO_DBG_REFRESH_MS    500             // debug panel values (loop rate, clocks) change slowly: twice a second
#define AWTO_KEY_BAND(v, lo, hi)                (((lo) <= (v)) && ((v) < (hi)))     // key0 / key1 rows: lo <= ADC < hi
extern void osd_tc_close(void);

// GENERATED-BEGIN awto_inputs
// kind 0 bit, 1 analog (deadband), 2 byte; src: see awto_gpio.inc AwtoInRead; flags bit0 = screen row, bit1 = logged in the ring
static const __code BYTE tAwtoInKind[AWTO_IN_N] = {
    0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0,
    2, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0};
static const __code BYTE tAwtoInSrc[AWTO_IN_N] = {
    0, 0, 0, 0, 0, 0, 1, 1, 3, 4, 5, 2,
    6, 6, 7, 7, 7, 7, 6, 7, 7, 8, 8, 8,
    8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8, 8,
    8, 8, 8, 10, 9, 10, 9, 9};
static const __code BYTE tAwtoInA[AWTO_IN_N] = {
    2, 3, 4, 5, 6, 7, 1, 2, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 104, 192, 40, 40, 112};
static const __code BYTE tAwtoInB[AWTO_IN_N] = {
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1,
    2, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
    1, 1, 1, 136, 224, 72, 72, 144};
static const __code WORD tAwtoInAddr[AWTO_IN_N] = {
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, AWTO_R_PORT90_PIN_REG, AWTO_R_PORT45_PIN_REG, AWTO_R_PORT1_PIN_REG,
    AWTO_R_PORT1_PIN_REG, AWTO_R_PORT42_PIN_REG, AWTO_R_PORT94_PIN_REG, AWTO_R_PORTA2_PIN_REG, AWTO_R_PORTA3_PIN_REG, AWTO_R_PORTA4_PIN_REG, AWTO_R_PORTA5_PIN_REG, AWTO_R_PORT92_PIN_REG,
    AWTO_R_PORT72_PIN_REG, AWTO_R_PORT74_PIN_REG, AWTO_R_PORT84_PIN_REG, AWTO_R_PORT85_PIN_REG, AWTO_R_PORT97_PIN_REG, AWTO_R_PORTA0_PIN_REG, AWTO_R_PORT86_PIN_REG, 0,
    0, 0, 0, 0};
static const __code BYTE tAwtoInFlags[AWTO_IN_N] = {
    3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 3, 3, 3,
    3, 3, 3, 3, 1, 1, 1, 3, 3, 3, 3, 3,
    3, 3, 3, 2, 2, 2, 2, 2};
// GENERATED-END awto_inputs

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

// Current value of input i. Table order puts the ADCs before the keys decoded from them.
static BYTE AwtoInRead(BYTE ucI)
{
    switch(tAwtoInSrc[ucI])
    {
        case AWTO_IN_P1: return (BYTE)((MCU_FFE2_PORT1_PIN_REG >> tAwtoInA[ucI]) & 1);
        case AWTO_IN_P3: return (BYTE)((MCU_FFE3_PORT3_PIN_REG >> tAwtoInA[ucI]) & 1);
        case AWTO_IN_P30: return (P3_0 == 0) ? 1 : 0;
        case AWTO_IN_ADC0S: return PCB_ADKEY1();
        case AWTO_IN_ADC1S: return PCB_ADKEY2();
        case AWTO_IN_ADC2S: return MCU_FF0B_ADC_A2_CONVERT_RESULT;
        case AWTO_IN_VSYNC: return s_ucVgaSync;
        case AWTO_IN_VCMP: return s_ucVgaCmp;
        case AWTO_IN_XREG: return (((*(__xdata volatile BYTE *)tAwtoInAddr[ucI]) & tAwtoInB[ucI]) != 0) ? 1 : 0;
        case AWTO_IN_KEY0: return AWTO_KEY_BAND(g_stAwtoGpio.ucIn[AWTO_IN_ADC0], tAwtoInA[ucI], tAwtoInB[ucI]) ? 1 : 0;
        default: return AWTO_KEY_BAND(g_stAwtoGpio.ucIn[AWTO_IN_ADC1], tAwtoInA[ucI], tAwtoInB[ucI]) ? 1 : 0;
    }
}

static void AwtoGpioLog(BYTE ucId, BYTE ucVal, WORD usNow)
{
    BYTE ucI = g_stAwtoGpio.ucSeq & (AWTO_GPIO_LOG_N - 1);

    g_stAwtoGpio.pstLog[ucI].ucSeq = g_stAwtoGpio.ucSeq;
    g_stAwtoGpio.pstLog[ucI].ucTickHi = (BYTE)(usNow >> 8);
    g_stAwtoGpio.pstLog[ucI].ucTickLo = (BYTE)usNow;
    g_stAwtoGpio.pstLog[ucI].ucId = ucId;
    g_stAwtoGpio.pstLog[ucI].ucVal = ucVal;
    g_stAwtoGpio.ucSeq++;
    AwtoConLogEvent(ucId, ucVal, usNow);           // the console's event log (does nothing when it is closed)
}

// ucMode 0: poll (store, log, mark a change), 1: mark every input changed (console just opened), 2: take the values quietly.
static void AwtoInScan(BYTE ucMode)
{
    BYTE ucI, ucV, ucO, ucD;
    WORD usNow = 0;

    s_ucVgaSync = ScalerGetByte(AWTO_VGA_SYNC_REG);
    s_ucVgaCmp = ScalerGetByte(AWTO_VGA_COMPARE_REG);
    for(ucI = 0; ucI < AWTO_IN_N; ucI++)
    {
        ucV = AwtoInRead(ucI);
        ucO = g_stAwtoGpio.ucIn[ucI];
        if(ucMode == 0)
        {
            if(tAwtoInKind[ucI] == 1)
            {
                ucD = (ucV > ucO) ? (ucV - ucO) : (ucO - ucV);
                if(ucD < AWTO_ADC_DEADBAND) continue;
            }
            else if(ucV == ucO)
            {
                continue;
            }
            if((tAwtoInFlags[ucI] & 2) != 0)
            {
                if(usNow == 0) usNow = AwtoGpioNow();
                AwtoGpioLog(ucI, ucV, usNow);
            }
            AWTO_PS_COUNT(ucI, ucV);              // #139 selector pulse rates (fw/awto/portsig.tsv cnt rows)
        }
        g_stAwtoGpio.ucIn[ucI] = ucV;
        if(ucMode != 2)
        {
            g_stAwtoGpio.ucDirty[ucI >> 3] |= (BYTE)1 << (ucI & 7);
            g_stAwtoGpio.ucAny = 1;
        }
    }
}

static void AwtoGpioEnsure(void)
{
    BYTE __xdata *puc = (BYTE __xdata *)&g_stAwtoGpio;
    WORD usI;

    if((g_stAwtoGpio.ucMagic0 == 'G') && (g_stAwtoGpio.ucMagic1 == 'P') &&
       (g_stAwtoGpio.ucVersion == 4)) return;
    for(usI = 0; usI < sizeof(StAwtoGpio); usI++) puc[usI] = 0;
    g_stAwtoGpio.ucMagic0 = 'G';
    g_stAwtoGpio.ucMagic1 = 'P';
    g_stAwtoGpio.ucVersion = 4;
    g_stAwtoGpio.ucN = AWTO_IN_N;
    AwtoInScan(2);
}

void AwtoGpioPoll(void)
{
    AwtoGpioEnsure();
    AwtoInScan(0);
    if(SysPowerGetPowerStatus() == _POWER_STATUS_SAVING) return;  // panel off: no console work; it held off the wake poll (#144)
    AWTO_OSD_SYNC_POLL();                      // #139 selector fields, console sync lines / auto-open
    if(g_stAwtoGpio.ucOpen == 0) return;
    if((WORD)(AwtoGpioNow() - s_usAwtoDbgDraw) >= AWTO_DBG_REFRESH_MS)
    {
        s_usAwtoDbgDraw = AwtoGpioNow();
        AwtoOsdDebugLines();
    }
    if((GET_OSD_EVENT_MESSAGE() >= _OSDEVENT_SHOW_NOSIGNAL_MSG) &&
       (GET_OSD_EVENT_MESSAGE() <= _OSDEVENT_ACTIVE_DO_ONE_TIME_MSG)) SET_OSD_EVENT_MESSAGE(_OSDEVENT_NONE_MSG);
    if(g_stAwtoGpio.ucOpen != AWTO_CON_GPIO) return;        // the input table is on the GPIO page only
    if((g_stAwtoGpio.ucDrawn == 0) && ((WORD)(AwtoGpioNow() - s_usAwtoGpioDraw) >= AWTO_KEY_RETRY_MS))
    {
        s_usAwtoGpioDraw = AwtoGpioNow();
        AwtoOsdGpioLines();                    // own text layer (Spleen), not the SDK message card
        return;
    }
    if((g_stAwtoGpio.ucDrawn != 0) && (g_stAwtoGpio.ucAny != 0) &&
       ((WORD)(AwtoGpioNow() - s_usAwtoGpioDraw) >= AWTO_GPIO_REFRESH_MS))
    {
        s_usAwtoGpioDraw = AwtoGpioNow();
        AwtoOsdGpioLines();
    }
}

// Front keys as AWTO_KM_* bits, from the values the poller holds (the only band decode: inputs.tsv key0 / key1 / p30 rows).
static BYTE AwtoKeyMaskNow(void)
{
    BYTE ucM = 0;

    if(g_stAwtoGpio.ucIn[AWTO_IN_SOURCE] != 0) ucM |= AWTO_KM_SOURCE;
    if(g_stAwtoGpio.ucIn[AWTO_IN_MENU] != 0) ucM |= AWTO_KM_MENU;
    if(g_stAwtoGpio.ucIn[AWTO_IN_DOWN] != 0) ucM |= AWTO_KM_DOWN;
    if(g_stAwtoGpio.ucIn[AWTO_IN_UP] != 0) ucM |= AWTO_KM_UP;
    if(g_stAwtoGpio.ucIn[AWTO_IN_AUTO] != 0) ucM |= AWTO_KM_AUTO;
    if(g_stAwtoGpio.ucIn[AWTO_IN_POWER] != 0) ucM |= AWTO_KM_POWER;
    return ucM;
}

void AwtoGpioConSet(BYTE ucOn)                 // console page (0 closed, AWTO_CON_*); the GPIO page samples the VGA front end too
{
    AwtoGpioEnsure();
    g_stAwtoGpio.ucDrawn = 0;
    g_stAwtoGpio.ucOpen = ucOn;
    AwtoVgaDiagPower(ucOn == AWTO_CON_GPIO);
    if(ucOn != 0)
    {
        AwtoInScan(1);
        s_usAwtoGpioDraw = AwtoGpioNow();
    }
}

void AwtoGpioTestSet(BYTE ucOn)                 // menu "GPIO inputs", test cmd 0x43 / 0x44: the console's GPIO page / close
{
    AwtoDiagConsole((ucOn != 0) ? AWTO_CON_GPIO : 0);
}
#endif
