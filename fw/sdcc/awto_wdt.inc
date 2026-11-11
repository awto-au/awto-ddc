// Watchdog + crash canary (#131, #138, docs/watchdog.md), inserted into SysMain.c (fw/awto/wdt/rules.py). Record: RL6449_Project.h StAwtoWdt.
// One hardware watchdog: pokes in the main-loop pass and bounded loops; the WDT threshold IRQ (int2, high priority) captures.
#if(_AWTO_WDT == _ON)
#define AWTO_P0_01_HOST_CTRL    0x0001          // regdb P0_01 HOST_CTRL (scaler register names are not visible in SysMain.c)
__sfr __at(0xD8) AWTO_EICON;                    // DW8051 EICON: bit 3 WDTI = core watchdog interrupt input flag (databook)
bit AwtoWdtValid(void)
{
    BYTE ucI;
    BYTE ucS = AWTO_WDT_SEED;

    for(ucI = 0; ucI < AWTO_WDT_REC_N; ucI++)
    {
        ucS ^= ((volatile __xdata BYTE *)&g_stAwtoWdt)[ucI];
    }
    return (g_stAwtoWdt.ucMagic0 == 'W') && (g_stAwtoWdt.ucMagic1 == 'D') && (g_stAwtoWdt.ucVersion == 2) && (g_stAwtoWdt.ucCheck == ucS);
}

static void AwtoWdtSeal(void)
{
    BYTE ucI;
    BYTE ucS = AWTO_WDT_SEED;

    for(ucI = 0; ucI < AWTO_WDT_REC_N; ucI++)
    {
        ucS ^= ((volatile __xdata BYTE *)&g_stAwtoWdt)[ucI];
    }
    g_stAwtoWdt.ucCheck = ucS;
}

static void AwtoWdtFresh(void)                  // empty record: cold RAM, a host clear, or another layout
{
    BYTE ucI;

    for(ucI = 0; ucI < 32; ucI++)
    {
        ((volatile __xdata BYTE *)&g_stAwtoWdt)[ucI] = 0;
    }
    g_stAwtoWdt.ucMagic0 = 'W';
    g_stAwtoWdt.ucMagic1 = 'D';
    g_stAwtoWdt.ucVersion = 2;
}

volatile __xdata BYTE g_ucAwtoPokeSite;         // AWTO_WDT_S_* that ended the longest poke gap this boot (#150)
volatile __xdata BYTE g_ucAwtoPokeFrom;         // ... and the site that started it
volatile __xdata BYTE g_ucAwtoPokeLast;

void AwtoWdtLibPoke(BYTE ucSite)                // the FunctionLib flash read / write loops (no project header there)
{
    AWTO_WDT_POKE(ucSite);
}

// Once per reset, before EA: classify the boot, keep the record, reset the live counters.
void AwtoWdtInit(void)
{
    BYTE ucOld = g_stAwtoWdt.ucBoot;
    BYTE ucNew = 0;

    ScalerSetBit(AWTO_P0_01_HOST_CTRL, ~(_BIT6 | _BIT0), _BIT6);   // reset_chk set again (any reset clears it; raw in the snapshot)
    // cold = no valid record; warm = valid record (P0_01[6] reads 0 after every reset on unit 2, #131: not used)
    if(AwtoWdtValid() == _FALSE)
    {
        AwtoWdtFresh();
        ucOld = 0;
        ucNew |= AWTO_WDT_B_COLD;
    }
    else if((ucOld & AWTO_WDT_B_BITE) != 0)
    {
        ucNew |= AWTO_WDT_B_NEW | AWTO_WDT_B_AFTER;
    }
    else
    {
        ucNew |= AWTO_WDT_B_WARM | (((g_stAwtoWdt.ucProbe & AWTO_WDT_P_EARLY) != 0) ? AWTO_WDT_B_HWWDT : 0);
        if(g_stAwtoWdt.ucWarm != 0xFF)
        {
            g_stAwtoWdt.ucWarm++;
        }
    }
    g_stAwtoWdt.ucProbe &= ~AWTO_WDT_P_EARLY;
    ucNew |= ucOld & AWTO_WDT_B_NEW;            // not yet shown: keep it over another reset
    if((g_stAwtoWdt.ucProbe & AWTO_WDT_P_ARMED) != 0)
    {
        g_stAwtoWdt.ucProbe = (g_stAwtoWdt.ucProbe & ~AWTO_WDT_P_ARMED) | AWTO_WDT_P_RESET;    // the probe's reset
        ucNew |= AWTO_WDT_B_PROBE;
    }
    AwtoWdtSeal();
    g_stAwtoWdt.ucBoot = ucNew;
    g_stAwtoWdt.ucPassHi = 0;                   // g_usTimerCounter starts at 0 with Timer2 (ScalerMcuInitial)
    g_stAwtoWdt.ucPassLo = 0;
    g_stAwtoWdt.ucMaxPass = 0;
    g_stAwtoWdt.ucMaxPoke = 0;
}

// Why this boot (#29). Inputs: the canary only (no reset-cause flag in DW8051 or RL6449; a found one goes in here first).
BYTE AwtoBootReason(void)
{
    BYTE ucB = g_stAwtoWdt.ucBoot;

    return ((ucB & AWTO_WDT_B_COLD) != 0) ? AWTO_BOOT_COLD : ((ucB & AWTO_WDT_B_AFTER) != 0) ? AWTO_BOOT_BITE :
           ((ucB & AWTO_WDT_B_PROBE) != 0) ? AWTO_BOOT_PROBE : ((ucB & AWTO_WDT_B_HWWDT) != 0) ? AWTO_BOOT_HWWDT : AWTO_BOOT_WARM;
}

DWORD AwtoBootValue(void)                       // bite: cause << 24 | bank << 16 | PC (sync.tsv fmt pc)
{
    return ((DWORD)g_stAwtoWdt.ucCause << 24) | ((DWORD)g_stAwtoWdt.ucBank << 16) | ((WORD)g_stAwtoWdt.ucPcHi << 8) | g_stAwtoWdt.ucPcLo;
}

// WDT IRQ context (SysTimerWDIntProc), never returns. Frame at entry: SP0 + 1 PCL, + 2 PCH, then the ISR prologue pushes
// (acc, psw, r7..r0, bits, dpl, dph, b). No poke: the reset follows; sof_rst only shortens the wait.
static void AwtoWdtBite(BYTE ucSp, BYTE ucBank, BYTE ucCause)
{
    __idata BYTE *pucF = (__idata BYTE *)(BYTE)(ucSp - AWTO_WDT_FRAME);
    WORD usAge = g_usTimerCounter - AWTO_WDT_PASS_AT();

    EA = 0;
    if(AwtoWdtValid() == _FALSE)
    {
        AwtoWdtFresh();
    }
    g_stAwtoWdt.ucCause = ucCause | (((g_stAwtoWdt.ucBoot & AWTO_WDT_B_TEST) != 0) ? AWTO_WDT_C_TEST : 0) |
                          ((AWTO_WDT_MODE == AWTO_WDT_TIMER_IRQ) ? AWTO_WDT_C_TMODE : 0);
    if(g_stAwtoWdt.ucBites != 0xFF)
    {
        g_stAwtoWdt.ucBites++;
    }
    g_stAwtoWdt.ucPcHi = pucF[2];
    g_stAwtoWdt.ucPcLo = pucF[1];
    g_stAwtoWdt.ucBank = ucBank;
    g_stAwtoWdt.ucSp = (BYTE)(ucSp - AWTO_WDT_FRAME);
    g_stAwtoWdt.ucAcc = pucF[3];
    g_stAwtoWdt.ucPsw = pucF[4];
    g_stAwtoWdt.ucDpl = pucF[14];
    g_stAwtoWdt.ucDph = pucF[15];
    g_stAwtoWdt.ucB = pucF[16];
    g_stAwtoWdt.ucRetHi = pucF[0];
    g_stAwtoWdt.ucRetLo = *(__idata BYTE *)(BYTE)(ucSp - AWTO_WDT_FRAME - 1);
    g_stAwtoWdt.ucStage = g_stAwtoDiag.ucStage;
    g_stAwtoWdt.ucMode = GET_MODE_STATE();
    g_stAwtoWdt.ucHbHi = (BYTE)(g_stAwtoDiag.usHeartbeat >> 8);
    g_stAwtoWdt.ucHbLo = (BYTE)g_stAwtoDiag.usHeartbeat;
    g_stAwtoWdt.ucUpHi = (BYTE)(g_usTimerCounter >> 8);
    g_stAwtoWdt.ucUpLo = (BYTE)g_usTimerCounter;
    g_stAwtoWdt.ucPassAgeHi = (BYTE)(usAge >> 8);
    g_stAwtoWdt.ucPassAgeLo = (BYTE)usAge;
    AwtoWdtSeal();
    g_stAwtoWdt.ucBoot |= AWTO_WDT_B_BITE;
    MCU_FFEE_MCU_CLOCK_CONTROL |= _BIT1;          // sof_rst now (as the host's ISP 0xEE <- 0x02); else CNT1 = N resets
    while(_TRUE)
    {
    }
}

// SysTimerWDIntProc (int2, PX2 = 1): CNT3 matched the threshold. Warning only at CNT1 = N - 1; earlier wraps' matches return.
void AwtoWdtIrq(BYTE ucSp, BYTE ucBank)
{
    BYTE ucCnt1;

    if((MCU_FFEB_WDT_TEST & _BIT7) == 0)
    {
        return;
    }
    MCU_FFEB_WDT_TEST = (MCU_FFEB_WDT_TEST & ~_BIT7) | _BIT3;     // latch the counters (no clear)
    ucCnt1 = AWTO_XFR(0xFFAD) & 0x07;
    if((g_stAwtoWdt.ucProbe & AWTO_WDT_P_ARMED) != 0)
    {
        g_stAwtoWdt.ucProbe |= AWTO_WDT_P_IRQ | (((AWTO_EICON & _BIT3) != 0) ? AWTO_WDT_P_WDTI : 0);
        MCU_FFEB_WDT_TEST = (MCU_FFEB_WDT_TEST & ~_BIT2) | _BIT7;  // flag cleared, IRQ off; counting goes on to the reset
        return;
    }
#if(AWTO_WDT_N > 1)
    if(ucCnt1 < (AWTO_WDT_N - 1))
    {
        g_stAwtoWdt.ucProbe |= AWTO_WDT_P_EARLY;    // evidence for the next boot if the warning never captures
        MCU_FFEB_WDT_TEST |= _BIT7;             // flag cleared (W1C); counting goes on
        return;
    }
#else
    ucCnt1 = ucCnt1;                            // N = 1: the first match is the warning (no early match, no P_EARLY)
#endif
    AwtoWdtBite(ucSp, ucBank, AWTO_WDT_C_STALL);
}

// Test cmd 0x4C + n (#131): 0 spin (STALL), 2 spin with EA off (hardware reset only, no capture). 1 (spin in a poking wait)
// is gone (#138): an unbounded loop around a poking wait is a bug the audit forbids (docs/watchdog.md), not a run-time case.
void AwtoWdtHang(BYTE ucHow)
{
    if(ucHow == 1)
    {
        return;
    }
    g_stAwtoWdt.ucBoot |= AWTO_WDT_B_TEST;
    if(ucHow == 2)
    {
        EA = 0;
    }
    while(_TRUE)
    {
    }
}

// Test cmd 0x49 (normal mode) / 0x4F (timer mode), for unit 2: no pokes, threshold PROBE_THR, N = 1; does the IRQ come, does
// the chip reset? Result in ucProbe (kept over the reset; rtd_crash.py, console). Back to the configured watchdog if no reset.
void AwtoWdtProbe(BYTE ucTimer)
{
    WORD usT0;
    WORD usNow;

    g_stAwtoWdt.ucProbe = AWTO_WDT_P_ARMED | ((ucTimer != 0) ? AWTO_WDT_P_TIMER : 0);
    EA = 0;
    MCU_FFEB_WDT_TEST = (MCU_FFEB_WDT_TEST & ~(_BIT7 | _BIT4 | _BIT2)) | _BIT7 | ((ucTimer != 0) ? _BIT4 : 0);
    AWTO_XFR(0xFFB0) = (AWTO_XFR(0xFFB0) & 0x0F) | ((AWTO_WDT_PROBE_THR >> 4) & 0xF0);
    AWTO_XFR(0xFFAE) = (BYTE)AWTO_WDT_PROBE_THR;
    MCU_FFEA_WATCHDOG_TIMER = (MCU_FFEA_WATCHDOG_TIMER & ~(_BIT2 | _BIT1 | _BIT0)) | _BIT6;       // N = 1, clear
    MCU_FFEB_WDT_TEST = (MCU_FFEB_WDT_TEST & ~_BIT7) | _BIT2;
    EA = 1;
    do
    {
        usT0 = g_usTimerCounter;
    }
    while(usT0 != g_usTimerCounter);
    do
    {
        usNow = g_usTimerCounter;
    }
    while((WORD)(usNow - usT0) < AWTO_WDT_PROBE_MS);
    g_stAwtoWdt.ucProbe = (g_stAwtoWdt.ucProbe & ~AWTO_WDT_P_ARMED) | AWTO_WDT_P_NORESET | (((AWTO_EICON & _BIT3) != 0) ? AWTO_WDT_P_WDTI : 0);
    ScalerTimerWDInitial();                     // the configured watchdog again (clears the counters)
}

// Main loop while AWTO_WDT_B_NEW: open the console (watchdog panel) once picture / no-signal state has settled AWTO_WDT_SHOW_MS.
// Not through the info pop-up (ucDbgPopup): the pop-up repositions the OSD after the console opened (sim render, #131).
static __xdata WORD s_usAwtoWdtSettled;         // 0 = not settled; else g_usTimerCounter | 1 when it settled

void AwtoWdtShow(void)
{
    BYTE ucMode = GET_MODE_STATE();
    WORD usNow;

    do
    {
        usNow = g_usTimerCounter;
    }
    while(usNow != g_usTimerCounter);
    if((g_stAwtoDiag.ucStage < 8) || (SysPowerGetPowerStatus() != _POWER_STATUS_NORMAL) ||
       ((ucMode != _MODE_STATUS_ACTIVE) && (ucMode != _MODE_STATUS_NOSIGNAL) && (ucMode != _MODE_STATUS_NOSUPPORT)))
    {
        s_usAwtoWdtSettled = 0;
        return;
    }
    if(s_usAwtoWdtSettled == 0)
    {
        s_usAwtoWdtSettled = usNow | 1;
        return;
    }
    if((WORD)(usNow - s_usAwtoWdtSettled) >= AWTO_WDT_SHOW_MS)
    {
        AwtoDiagConsole(1);                     // draws the watchdog panel, which clears AWTO_WDT_B_NEW
    }
}
#endif
