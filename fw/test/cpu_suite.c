#include "SysInclude.h"
#include "ScalerCommonFunctionInclude.h"
#include "cpu_suite.h"

// CPU suite image (-D _AWTO_CPU_SUITE; docs/cpu-suite.md; host scripts/cpu_suite.py). main() = AwtoCpuSuiteMain: startup + clock init,
// then a mailbox loop: the host writes ucGo = case id (+ request fields), the loop runs the case and clears ucGo. Nothing else runs.
// Every case is bounded (stated per case); Timer2 keeps the 1 ms tick and clears the hardware watchdog.
#ifdef _AWTO_CPU_SUITE

#define AWTO_CPU_MAGIC                          0xA5
#define AWTO_CPU_ST_IDLE                        0
#define AWTO_CPU_ST_DONE                        2
#define AWTO_CPU_ST_BAD_CASE                    3
#define AWTO_CPU_ST_REFUSED                     4                   // R_WRITE without the host's write flag
#define AWTO_CPU_F_WRITE                        0x01                // request: R_WRITE may write the scratch candidates
#define AWTO_CPU_F_LIMIT                        0x80                // result: a bounded wait expired
#define AWTO_CPU_IDLE_MS                        30000UL             // host idle limit: longest case gap seen (M_CRC loaded 1.1 s, 3 s host overhead) x 10; expiry = watchdog reset, 0.6 s, the loop restarts
#define AWTO_CPU_HANG_EA_OFF                    2                   // AwtoWdtHang: spin with EA off, no watchdog feed (586 ms bite)
#define AWTO_CPU_KEEP                           0xFF                // ucStretch: leave CKCON alone
#define AWTO_CPU_CKCON_MASK                     0x07                // CKCON[2:0] MOVX stretch (databook Table 2-5)
#define AWTO_CPU_TCON_KEEP                      0x55                // TR1 IT1 TR0 IT0
#define AWTO_CPU_TMOD_16                        0x11                // both timers mode 1
#define AWTO_CPU_TMOD_T1_AR                     0x20                // Timer1 mode 2 (8 bit auto-reload), high nibble
#define AWTO_CPU_TMOD_T0_MASK                   0x0F

#define AWTO_CPU_C_T_RATE0                      1
#define AWTO_CPU_C_T_RATE1                      2
#define AWTO_CPU_C_T_RELOAD                     3
#define AWTO_CPU_C_T_FULL                       4
#define AWTO_CPU_C_T_AUTORELOAD                 5
#define AWTO_CPU_C_T_TORN                       6
#define AWTO_CPU_C_T_MS16                       7
#define AWTO_CPU_C_T_MS32                       8
#define AWTO_CPU_C_T_DRIFT                      9
#define AWTO_CPU_C_I_TRIG_EX0                   10
#define AWTO_CPU_C_I_TRIG_T0                    11
#define AWTO_CPU_C_I_TRIG_T1                    12
#define AWTO_CPU_C_I_PRIO                       13
#define AWTO_CPU_C_I_NEST                       14
#define AWTO_CPU_C_I_EA_GATE                    15
#define AWTO_CPU_C_I_EA_RACE                    16
#define AWTO_CPU_C_I_STORM                      17
#define AWTO_CPU_C_I_ATOMIC                     18
#define AWTO_CPU_C_M_PATTERN                    20
#define AWTO_CPU_C_M_GUARD                      21
#define AWTO_CPU_C_M_CRC                        22
#define AWTO_CPU_C_R_READ                       30
#define AWTO_CPU_C_R_WRITE                      31
#define AWTO_CPU_C_D_XMS                        40
#define AWTO_CPU_C_D_5US                        41
#define AWTO_CPU_C_D_XUS                        42
#define AWTO_CPU_C_D_POLL                       43

#define AWTO_CPU_TICK_SPIN                      40000               // main-loop spins to see one 1 ms tick: >= 20 clk a spin = 0.8 M clk = 9 ms at 87.7 MHz, 9x the tick; expiry sets F_LIMIT
#define AWTO_CPU_RATE_WINDOWS                   20                  // T_RATE: one-tick windows (20 ms)
#define AWTO_CPU_RATE_WARM                      3                   // windows not counted
#define AWTO_CPU_RATE_TOL                       16                  // counts per window: sample skew between the two counters (sim: up to 8 counts, instruction granularity), EA off
#define AWTO_CPU_RELOAD_N                       5
#define AWTO_CPU_RELOAD_SPIN                    400                 // polls for 256 counts (3072 clk) at >= 16 clk a poll = 192, x2
#define AWTO_CPU_RELOAD_RATIO_PCT               40                  // quantised polls: 256 / 16 counts ratio to within 40 %
#define AWTO_CPU_AR_RELOAD                      0x00                // T1 mode 2 reload: 256 counts a period (the longest; a cold-cache pass of the poll loop can take over 128)
#define AWTO_CPU_AR_PERIODS                     20
#define AWTO_CPU_AR_WARM                        3
#define AWTO_CPU_AR_TOL                         128                 // counts over 20 periods: poll latency
#define AWTO_CPU_TORN_SAMPLES                   64                  // per batch (2 B each in the test buffer)
#define AWTO_CPU_TORN_BATCHES                   32                  // 2 x 2048 reads; EA off for 64 reads at a time
#define AWTO_CPU_TORN_STEP                      0x80                // consecutive reads are ~10 counts apart: a step above this is torn
#define AWTO_CPU_MS_TICKS                       12                  // ticks watched across a counter wrap
#define AWTO_CPU_MS_STEP_MAX                    3                   // ticks between two reads at tick edges (a cache miss can delay a read past one tick)
#define AWTO_CPU_MS_LEAD                        5                   // ticks before the wrap the counter is injected
#define AWTO_CPU_MS_START_LO                    ((WORD)(0 - AWTO_CPU_MS_LEAD))
#define AWTO_CPU_DRIFT_TICKS_DEF                200                 // T_DRIFT default window (ms); host may pass up to AWTO_CPU_DRIFT_TICKS_MAX
#define AWTO_CPU_DRIFT_TICKS_MAX                1500                // < the WDT warning (feeding every tick)
#define AWTO_CPU_DRIFT_TOL                      32                  // counts over the whole window (window errors do not add: the same sample skew every time)
#define AWTO_CPU_TRIG_N                         64
#define AWTO_CPU_TRIG_WARM                      4
#define AWTO_CPU_TRIG_SPIN                      200                 // polls for one ISR after the flag: 1 ISR = <= 100 machine cycles, a poll >= 4 cycles
#if(AWTO_CLOCK_MHZ == 350)
#define AWTO_CPU_FCPU_KHZ                       350800UL            // MCU clock of the build (docs/delay-audit.md)
#elif(AWTO_CLOCK_MHZ == 175)
#define AWTO_CPU_FCPU_KHZ                       175400UL
#else
#define AWTO_CPU_FCPU_KHZ                       87700UL
#endif
#define AWTO_CPU_COUNT_CLK                      12UL                // CPU clocks per timer count (CKCON T0M / T1M = 0)
#define AWTO_CPU_LAT_MAX_US                     20UL                // mean flag set -> ISR snapshot, incl. 3 main instructions, the vector and the prologue;
                                                                    // sim worst mean 11.5 us (87.7 MHz, uncached ISR code): 1.7x; Phase B replaces it by 1.25 x the unit's measurement
#define AWTO_CPU_LAT_MAX                        ((WORD)(AWTO_CPU_LAT_MAX_US * AWTO_CPU_FCPU_KHZ / (AWTO_CPU_COUNT_CLK * 1000UL)))
#define AWTO_CPU_LOG_N                          8
#define AWTO_CPU_NEST_NOPS                      16
#define AWTO_CPU_EA_NOPS                        200
#define AWTO_CPU_RACE_N                         20000               // 20000 x ~14 cycles = 0.3 M cycles: 12 ms at 87.7 MHz / 3 ms at 350.8
#define AWTO_CPU_RACE_RELOAD                    0x01                // T1 mode 2 period 255 counts (odd, longer than the ISR): sweeps the phase against the EA toggle
#define AWTO_CPU_STORM_MS_DEF                   10                  // storm length (Timer2 ticks); the ISR ends it itself
#define AWTO_CPU_STORM_GRACE_MS                 4                   // main loop forces the stop this long after the deadline
#define AWTO_CPU_STORM_RELOAD_MAX               0xFF                // reload 0xFF = overflow every count (12 clk): the maximum interrupt rate
#define AWTO_CPU_ATOMIC_RELOAD                  0x00                // period 256 counts (3072 clk) against a ~300 cycle light ISR: main keeps most of the CPU
#define AWTO_CPU_WORK_N                         32
#define AWTO_CPU_WORK_RMW                       16
#define AWTO_CPU_ISR_WORK_N                     8
#define AWTO_CPU_BUF_N                          320
#define AWTO_CPU_PAT_HALF                       160                 // burst copy: buf[0..159] -> buf[160..319]
#define AWTO_CPU_DELAY_DEF                      16                  // M_PATTERN: nops between write and read-back
#define AWTO_CPU_LFSR_POLY                      0x1D
#define AWTO_CPU_GUARD_N                        16
#define AWTO_CPU_CRC_FROM                       0x0100              // common code area, as the clock sweep's CRC
#define AWTO_CPU_CRC_TO                         0x1100
#define AWTO_CPU_CRC_PASSES                     3
#define AWTO_CPU_CRC_POLY                       0x1021
#define AWTO_CPU_CRC_INIT                       0xFFFF
#define AWTO_CPU_CRC_LOAD_RELOAD                0x00                // M_CRC arg bit 0: Timer1 ISR load at a 256 count period
#define AWTO_CPU_RD_REPS_DEF                    64                  // reads per register and kind
#define AWTO_CPU_RD_SLOW_NOPS                   64
#define AWTO_CPU_WR_PAT_N                       4
#define AWTO_CPU_D_5US_N                        4000                // x 5 us = 20 ms
#define AWTO_CPU_D_XUS_N                        200                 // x 100 us = 20 ms
#define AWTO_CPU_D_XUS_US                       100
#define AWTO_CPU_D_PCT_LO                       98                  // delay audit: counts are built 5 % over nominal (docs/delay-audit.md); +-1 tick of 20 ms = 5 %
#define AWTO_CPU_D_PCT_HI                       118
#define AWTO_CPU_D_XMS_MAX                      300
#define AWTO_CPU_POLL_REG                       P0_00_ID_REG        // reads 0xCF: bit 4 is 0, the wait never succeeds
#define AWTO_CPU_POLL_BIT                       0x10
#define AWTO_CPU_POLL_MAX                       250

#define AWTO_CPU_VEC_EX0                        0
#define AWTO_CPU_VEC_T0                         1
#define AWTO_CPU_VEC_T1                         3
#define AWTO_CPU_MODE_COUNT                     0
#define AWTO_CPU_MODE_NEST                      1
#define AWTO_CPU_MODE_STORM                     2
#define AWTO_CPU_MODE_RACE                      3
#define AWTO_CPU_MODE_LIGHT                     4                   // counter + deadline only
#define AWTO_CPU_EXIT_FLAG                      0x80                // log: low-priority ISR leaving

#include "cpu_suite_regs.inc"

// SDCC drops a volatile read that directly follows a volatile write of the same expression (warning 110, no MOVX emitted): a
// back-to-back read-back goes through a differently spelled pointer (verified on the asm).
#define CPU_RD(p)                               (*(volatile __xdata BYTE *)((unsigned int)(p)))

typedef struct
{
    BYTE ucGo;                                          // 0  host: case id, fw clears
    BYTE ucSeq;                                         // 1
    BYTE ucState;                                       // 2  AWTO_CPU_ST_*
    BYTE ucPass;                                        // 3
    BYTE ucStretch;                                     // 4  request: CKCON[2:0] during the case, 0xFF keep
    BYTE ucFlags;                                       // 5  request AWTO_CPU_F_WRITE; result AWTO_CPU_F_LIMIT
    WORD usArg;                                         // 6
    WORD usArg2;                                        // 8
    WORD usBad;                                         // 10 failed checks
    unsigned long ulV0;                                 // 12 measured numbers (per case, docs/cpu-suite.md)
    unsigned long ulV1;                                 // 16
    unsigned long ulV2;                                 // 20
    WORD usMs;                                          // 24 Timer2 ticks the case took
    BYTE ucCkcon;                                       // 26 CKCON during the case
    BYTE ucReady;                                       // 27 AWTO_CPU_MAGIC once the loop runs
    WORD usRcap;                                        // 28 RCAP2 (Timer2 reload)
    WORD usBeat;                                        // 30 loop passes
    BYTE ucStackHigh;                                   // 32 stack canary high-water (AwtoStackCheck)
    BYTE ucSpMax;                                       // 33 highest SP seen by a case ISR
    WORD usBufAt;                                       // 34 address of the XDATA test buffer
    WORD usBufN;                                        // 36
} StAwtoCpu;
__xdata StAwtoCpu g_stAwtoCpu;
__xdata BYTE g_aucCpuBuf[AWTO_CPU_BUF_N];
__xdata BYTE g_aucCpuGuard[2 * AWTO_CPU_GUARD_N + AWTO_CPU_GUARD_N];     // lead guard, working buffer, tail guard (M_GUARD)

volatile __xdata BYTE isr_g_ucCpuIsr;                   // IRAM is full in this image: XDATA flags, so a marker store is one statement (3 instructions)
volatile __xdata BYTE isr_g_aucCpuSnap[4];
volatile __xdata BYTE isr_s_ucMark;                     // main-loop marker read by the ISR
volatile __xdata BYTE isr_s_ucCrit;
volatile __xdata BYTE isr_s_ucMode;
volatile __xdata WORD isr_s_ausCnt[3];                  // ISR entries by vector: 0 EXINT0, 1 Timer0, 2 Timer1
volatile __xdata BYTE isr_s_aucLog[AWTO_CPU_LOG_N];
volatile __xdata BYTE isr_s_ucLogN;
volatile __xdata BYTE isr_s_ucSp;
volatile __xdata BYTE isr_s_ucMarkAtIsr;
volatile __xdata BYTE isr_s_aucSnap[4];
volatile __xdata WORD isr_s_usShared;
volatile __xdata WORD isr_s_usIsrN;
volatile __xdata BYTE isr_s_ucStorm;                    // 1 while the storm ISR runs
volatile __xdata WORD isr_s_usDeadline;
volatile __xdata BYTE isr_s_ucIsrBad;
volatile __xdata BYTE isr_s_ucRaceBad;
volatile __xdata BYTE isr_s_aucIsrBuf[AWTO_CPU_ISR_WORK_N];

static __xdata BYTE s_ucSvIe;
static __xdata BYTE s_ucSvIp;
static __xdata BYTE s_ucSvTmod;
static __xdata BYTE s_ucSvTcon;
static __xdata BYTE s_ucSvCkcon;

//--------------------------------------------------
// Guard-byte helper (cpu_suite.h)
//--------------------------------------------------
void AwtoGuardFill(volatile __xdata BYTE *pucG, BYTE ucLen, BYTE ucSeed)
{
    BYTE ucI;

    for(ucI = 0; ucI < ucLen; ucI++)
    {
        pucG[ucI] = ucSeed ^ ucI;
    }
}

BYTE AwtoGuardCheck(volatile __xdata BYTE *pucG, BYTE ucLen, BYTE ucSeed)
{
    BYTE ucI;
    BYTE ucBad = 0;

    for(ucI = 0; ucI < ucLen; ucI++)
    {
        if(pucG[ucI] != (BYTE)(ucSeed ^ ucI))
        {
            ucBad++;
        }
    }
    return ucBad;
}

//--------------------------------------------------
// Time base: d_isr_g_usTimerCounter = 1 ms tick of Timer2 (read twice: the ISR bumps it between the bytes)
//--------------------------------------------------
static WORD CpuNow(void)
{
    WORD usA;
    WORD usB;

    do
    {
        usA = d_isr_g_usTimerCounter;
        usB = d_isr_g_usTimerCounter;
    }
    while(usA != usB);
    return usA;
}

static void CpuFeed(void)
{
    AWTO_WDT_PASS(CpuNow());
}

static WORD CpuRcap(void)
{
    return ((WORD)RCAP2H << 8) | RCAP2L;
}

static unsigned long CpuTickCounts(void)                 // Timer2 counts in one ms
{
    return 0x10000UL - CpuRcap();
}

static BYTE CpuWaitTick(WORD *pusNow)                    // returns at the next tick edge; 0 = expired
{
    WORD usT = CpuNow();
    WORD usN = 0;

    do
    {
        *pusNow = CpuNow();
        if(*pusNow != usT)
        {
            return 1;
        }
    }
    while(++usN < AWTO_CPU_TICK_SPIN);
    g_stAwtoCpu.ucFlags |= AWTO_CPU_F_LIMIT;
    return 0;
}

static unsigned long CpuAbsDiff(unsigned long ulA, unsigned long ulB)
{
    return (ulA > ulB) ? (ulA - ulB) : (ulB - ulA);
}

static WORD CpuT0Rd(void)
{
    BYTE ucH;
    BYTE ucL;

    do
    {
        ucH = TH0;
        ucL = TL0;
    }
    while(ucH != TH0);
    return ((WORD)ucH << 8) | ucL;
}

static WORD CpuT1Rd(void)
{
    BYTE ucH;
    BYTE ucL;

    do
    {
        ucH = TH1;
        ucL = TL1;
    }
    while(ucH != TH1);
    return ((WORD)ucH << 8) | ucL;
}

//--------------------------------------------------
// Case frame: timers / interrupt enables / priorities saved, SDK interrupts off, restored at the end
//--------------------------------------------------
static void CpuBegin(void)
{
    EA = 0;
    s_ucSvIe = IE;
    s_ucSvIp = IP;
    s_ucSvTmod = TMOD;
    s_ucSvTcon = TCON;
    s_ucSvCkcon = CKCON;
    ET0 = 0;
    ET1 = 0;
    EX0 = 0;
    TR0 = 0;
    TR1 = 0;
    TF0 = 0;
    TF1 = 0;
    IE0 = 0;
    IT0 = 1;
    PX0 = 0;
    PT0 = 0;
    PT1 = 0;
    TMOD = AWTO_CPU_TMOD_16;
    TH0 = 0;
    TL0 = 0;
    TH1 = 0;
    TL1 = 0;
    if(g_stAwtoCpu.ucStretch != AWTO_CPU_KEEP)
    {
        CKCON = (CKCON & ~AWTO_CPU_CKCON_MASK) | (g_stAwtoCpu.ucStretch & AWTO_CPU_CKCON_MASK);
    }
    g_stAwtoCpu.ucCkcon = CKCON;
    isr_s_ucMode = AWTO_CPU_MODE_COUNT;
    isr_s_ucLogN = 0;
    isr_s_ausCnt[0] = 0;
    isr_s_ausCnt[1] = 0;
    isr_s_ausCnt[2] = 0;
    isr_s_ucSp = 0;
    isr_s_ucStorm = 0;
    isr_g_ucCpuIsr = 0;
    EA = 1;
}

static void CpuEnd(void)
{
    EA = 0;
    isr_g_ucCpuIsr = 0;
    TR0 = 0;
    TR1 = 0;
    TF0 = 0;
    TF1 = 0;
    IE0 = 0;
    TMOD = s_ucSvTmod;
    TCON = s_ucSvTcon & AWTO_CPU_TCON_KEEP;
    CKCON = s_ucSvCkcon;
    IP = s_ucSvIp;
    IE = s_ucSvIe;
    EA = 1;
}

//--------------------------------------------------
// ISR hook (AWTO_CPU_ISR in SysInt.c / SysTimer.c): EXINT0, Timer0, Timer1 while a case runs
//--------------------------------------------------
void AwtoCpuIsr(BYTE ucVec)
{
    BYTE ucMode = isr_s_ucMode;
    BYTE ucI;
    BYTE ucIdx = (ucVec == AWTO_CPU_VEC_EX0) ? 0 : ((ucVec == AWTO_CPU_VEC_T0) ? 1 : 2);
    WORD usNow;

    if(ucMode == AWTO_CPU_MODE_RACE)                    // light paths first: the period of the interrupt source is only a few hundred cycles
    {
        isr_s_ausCnt[2]++;
        if(isr_s_ucCrit != 0)
        {
            isr_s_ucRaceBad++;                          // entered after the instruction following CLR EA
        }
        return;
    }
    if(ucMode == AWTO_CPU_MODE_LIGHT)
    {
        isr_s_usShared++;
        isr_s_usIsrN++;
        usNow = d_isr_g_usTimerCounter;                 // Timer2 is the higher priority: a bump between the bytes only makes this stop one tick late
        if((WORD)(usNow - isr_s_usDeadline) < 0x8000)
        {
            TR1 = 0;
            ET1 = 0;
            isr_s_ucStorm = 0;
        }
        return;
    }
    if(SP > isr_s_ucSp)
    {
        isr_s_ucSp = SP;
    }
    isr_s_ausCnt[ucIdx]++;
    isr_s_ucMarkAtIsr = isr_s_ucMark;
    for(ucI = 0; ucI < 4; ucI++)
    {
        isr_s_aucSnap[ucI] = isr_g_aucCpuSnap[ucI];
    }
    if(isr_s_ucLogN < AWTO_CPU_LOG_N)
    {
        isr_s_aucLog[isr_s_ucLogN++] = ucVec;
    }
    if(ucMode == AWTO_CPU_MODE_NEST)
    {
        if(ucVec == AWTO_CPU_VEC_T1)
        {
            IE0 = 1;                                    // the high-priority source fires inside the low-priority ISR
            for(ucI = 0; ucI < AWTO_CPU_NEST_NOPS; ucI++)
            {
                _nop_();
            }
            if(isr_s_ucLogN < AWTO_CPU_LOG_N)
            {
                isr_s_aucLog[isr_s_ucLogN++] = ucVec | AWTO_CPU_EXIT_FLAG;
            }
        }
    }
    else if(ucMode == AWTO_CPU_MODE_STORM)
    {
        isr_s_usShared++;
        isr_s_usIsrN++;
        for(ucI = 0; ucI < AWTO_CPU_ISR_WORK_N; ucI++)
        {
            isr_s_aucIsrBuf[ucI] = (BYTE)(isr_s_usIsrN + ucI);
        }
        for(ucI = 0; ucI < AWTO_CPU_ISR_WORK_N; ucI++)
        {
            if(isr_s_aucIsrBuf[ucI] != (BYTE)(isr_s_usIsrN + ucI))
            {
                isr_s_ucIsrBad++;
            }
        }
        usNow = d_isr_g_usTimerCounter;
        if((WORD)(usNow - isr_s_usDeadline) < 0x8000)
        {
            TR1 = 0;
            ET1 = 0;
            isr_s_ucStorm = 0;
        }
    }
}

//--------------------------------------------------
// TIMERS
//--------------------------------------------------
// Timer0 / Timer1 counts against Timer2's own count over windows of one ISR-visible tick: the sample (tick counter, TF2, TH2:TL2, timer) is taken
// with EA off, so the ISR latency and the main-loop path cancel; what is left is the rate ratio of the two counters.
static void CpuSample(BYTE ucT1, unsigned long *pulT2, WORD *pusT)
{
    BYTE ucH;
    BYTE ucL;
    WORD usN;
    BYTE ucTf;
    BYTE ucPass;

    for(ucPass = 0; ucPass < 2; ucPass++)               // pass 0 loads the sample code into the flash cache (a miss inside the sample is ~80 counts at 350.8 MHz); pass 1 counts
    {
        EA = 0;
        usN = d_isr_g_usTimerCounter;
        do
        {
            ucH = TH2;
            ucL = TL2;
        }
        while(ucH != TH2);
        ucTf = TF2;
        *pusT = (ucT1 != 0) ? CpuT1Rd() : CpuT0Rd();
        EA = 1;
    }
    *pulT2 = ((unsigned long)usN + ucTf) * CpuTickCounts() + (((WORD)ucH << 8) | ucL) - CpuRcap();
}

static void CpuRateRun(BYTE ucT1, WORD usWindows, BYTE ucDrift)
{
    unsigned long ulT2A;
    unsigned long ulT2B;
    unsigned long ulSumT;
    unsigned long ulSumR;
    unsigned long ulMaxErr = 0;
    unsigned long ulErr;
    WORD usA;
    WORD usB;
    WORD usT;
    WORD usN;

    CpuBegin();
    if(ucT1 != 0) { TR1 = 1; } else { TR0 = 1; }
    ulSumT = 0;
    ulSumR = 0;
    CpuSample(ucT1, &ulT2A, &usA);
    for(usN = 0; usN < usWindows; usN++)
    {
        if(CpuWaitTick(&usT) == 0)
        {
            break;
        }
        CpuFeed();
        CpuSample(ucT1, &ulT2B, &usB);
        ulErr = (unsigned long)(WORD)(usB - usA);       // window > 2.2 ms at 350.8 MHz is not possible here: one tick is 29233 counts < 65536
        if(usN >= AWTO_CPU_RATE_WARM)                   // the first windows run the sample code cold (flash cache miss inside the sample) and start with the timer just switched on: not counted
        {
            ulSumT += ulErr;
            ulSumR += ulT2B - ulT2A;
        }
        ulErr = CpuAbsDiff(ulErr, ulT2B - ulT2A);
        if(usN < AWTO_CPU_BUF_N)
        {
            g_aucCpuBuf[usN] = (ulErr > 0xFF) ? 0xFF : (BYTE)ulErr;     // per-window error for the host (diagnosis)
        }
        if((ulErr > ulMaxErr) && (usN >= AWTO_CPU_RATE_WARM))
        {
            ulMaxErr = ulErr;
        }
        ulT2A = ulT2B;
        usA = usB;
    }
    TR0 = 0;
    TR1 = 0;
    g_stAwtoCpu.ulV0 = ulSumT;                          // timer counts over the windows
    g_stAwtoCpu.ulV1 = ulSumR;                          // Timer2 counts over the same windows
    g_stAwtoCpu.ulV2 = (ucDrift != 0) ? CpuAbsDiff(ulSumT, ulSumR) : ulMaxErr;      // drift: total difference; rate: worst single window
    if(g_stAwtoCpu.ulV2 > ((ucDrift != 0) ? AWTO_CPU_DRIFT_TOL : AWTO_CPU_RATE_TOL))
    {
        g_stAwtoCpu.usBad++;
    }
    CpuEnd();
}

static void CaseRate(BYTE ucT1)
{
    CpuRateRun(ucT1, AWTO_CPU_RATE_WINDOWS, 0);
}

static const __code WORD tAwtoCpuDist[AWTO_CPU_RELOAD_N] = {1, 2, 4, 16, 256};          // counts to the overflow: load = 0x10000 - distance

static void CaseReload(void)
{
    WORD usN[AWTO_CPU_RELOAD_N];
    BYTE ucI;
    WORD usK;

    CpuBegin();
    for(ucI = 0; ucI < AWTO_CPU_RELOAD_N; ucI++)
    {
        TR1 = 0;
        TF1 = 0;
        TH1 = (BYTE)((WORD)(0 - tAwtoCpuDist[ucI]) >> 8);
        TL1 = (BYTE)(0 - tAwtoCpuDist[ucI]);
        TR1 = 1;
        for(usK = 0; (TF1 == 0) && (usK < AWTO_CPU_RELOAD_SPIN); usK++)
        {
        }
        TR1 = 0;
        usN[ucI] = usK;
        if(TF1 == 0)
        {
            g_stAwtoCpu.usBad++;                        // never overflowed
        }
    }
    for(ucI = 1; ucI < AWTO_CPU_RELOAD_N; ucI++)
    {
        if(usN[ucI] < usN[ucI - 1])
        {
            g_stAwtoCpu.usBad++;                        // a longer distance must not overflow sooner
        }
    }
    g_stAwtoCpu.ulV0 = usN[3];                          // polls to overflow: 16 counts
    g_stAwtoCpu.ulV1 = usN[4];                          // 256 counts
    g_stAwtoCpu.ulV2 = usN[0];                          // 1 count
    if(((unsigned long)usN[4] * 16UL * 100UL < (unsigned long)usN[3] * 256UL * (100 - AWTO_CPU_RELOAD_RATIO_PCT)) ||
       ((unsigned long)usN[4] * 16UL * 100UL > (unsigned long)usN[3] * 256UL * (100 + AWTO_CPU_RELOAD_RATIO_PCT)))
    {
        g_stAwtoCpu.usBad++;
    }
    CpuEnd();
}

static void CaseFull(void)                              // load 0x0000: 65536 counts, measured in Timer2 ticks
{
    WORD usT0;
    WORD usNow = 0;
    unsigned long ulExp100;
    unsigned long ulGot100;
    unsigned long ulMaxTicks;
    BYTE ucOk = 0;

    CpuBegin();
    ulExp100 = 6553600UL / CpuTickCounts();
    ulMaxTicks = (ulExp100 / 100UL) * 2 + 2;            // twice the expected ticks: the flag did not come
    if(CpuWaitTick(&usT0) != 0)
    {
        TR0 = 1;
        while(TF0 == 0)
        {
            usNow = CpuNow();
            if((WORD)(usNow - usT0) > ulMaxTicks)
            {
                break;
            }
        }
        ucOk = TF0;
        TR0 = 0;
    }
    ulGot100 = (unsigned long)(WORD)(usNow - usT0) * 100UL;
    g_stAwtoCpu.ulV0 = ulGot100;                        // elapsed ticks x 100 (integer ticks)
    g_stAwtoCpu.ulV1 = ulExp100;
    if((ucOk == 0) || (CpuAbsDiff(ulGot100, ulExp100) >= 100UL))
    {
        g_stAwtoCpu.usBad++;                            // not within one tick of 65536 / (65536 - RCAP2)
    }
    CpuEnd();
}

static void CaseAutoReload(void)
{
    BYTE ucI;
    WORD usK;
    WORD usSw;

    CpuBegin();
    TMOD = AWTO_CPU_TMOD_T1_AR | (AWTO_CPU_TMOD_16 & AWTO_CPU_TMOD_T0_MASK);
    TH1 = AWTO_CPU_AR_RELOAD;
    TL1 = AWTO_CPU_AR_RELOAD;
    TH0 = 0;
    TL0 = 0;
    TR0 = 1;
    TR1 = 1;
    EA = 0;                                             // the 1 ms Timer2 ISR (~1000 counts) would swallow overflow flags; 23 periods = 0.8 ms at 87.7 MHz
    for(ucI = 0; ucI < AWTO_CPU_AR_PERIODS + AWTO_CPU_AR_WARM; ucI++)
    {
        if(ucI == AWTO_CPU_AR_WARM)                     // the first periods run the loop cold: the stopwatch starts after them
        {
            TH0 = 0;
            TL0 = 0;
        }
        for(usK = 0; (TF1 == 0) && (usK < AWTO_CPU_RELOAD_SPIN); usK++)
        {
        }
        if(TF1 == 0)
        {
            g_stAwtoCpu.usBad++;
            break;
        }
        TF1 = 0;
    }
    TR1 = 0;
    TR0 = 0;
    EA = 1;
    usSw = CpuT0Rd();
    g_stAwtoCpu.ulV0 = usSw;                            // stopwatch counts for 20 periods
    g_stAwtoCpu.ulV1 = (unsigned long)AWTO_CPU_AR_PERIODS * (0x100 - AWTO_CPU_AR_RELOAD);
    g_stAwtoCpu.ulV2 = TL1;                             // reloaded value seen after the last stop
    if(CpuAbsDiff(g_stAwtoCpu.ulV0, g_stAwtoCpu.ulV1) > AWTO_CPU_AR_TOL)
    {
        g_stAwtoCpu.usBad++;
    }
    CpuEnd();
}

static __xdata WORD s_ausTornAt[2];                      // first torn pair seen (previous, current): for the host's diagnosis

static unsigned long CpuTornCount(WORD usSamples)        // samples in g_aucCpuBuf (hi, lo): steps that are not small and positive
{
    volatile __xdata BYTE *pucB = g_aucCpuBuf;
    WORD usI;
    WORD usV;
    WORD usPrev = 0;
    WORD usD;
    unsigned long ulBad = 0;

    for(usI = 0; usI < usSamples; usI++)
    {
        usV = ((WORD)pucB[2 * usI] << 8) | pucB[2 * usI + 1];
        usD = (WORD)(usV - usPrev);
        if((usI != 0) && (usD > AWTO_CPU_TORN_STEP))
        {
            if(ulBad == 0)
            {
                s_ausTornAt[0] = usPrev;
                s_ausTornAt[1] = usV;
            }
            ulBad++;                                    // a torn read is off by +-256 (low byte wrapped between the two reads)
        }
        usPrev = usV;
    }
    return ulBad;
}

static void CaseTorn(void)
{
    volatile __xdata BYTE *pucB = g_aucCpuBuf;
    WORD usBatch;
    WORD usI;
    BYTE ucH;
    BYTE ucL;
    unsigned long ulNaive = 0;
    unsigned long ulProt = 0;

    CpuBegin();
    TH0 = 0;
    TL0 = 0;
    TR0 = 1;
    for(usBatch = 0; usBatch < AWTO_CPU_TORN_BATCHES; usBatch++)
    {
        EA = 0;                                         // an ISR in between would look like a torn read; off for one sampling loop only (~30 us at 87.7 MHz):
        for(usI = 0; usI < AWTO_CPU_TORN_SAMPLES; usI++)    // a long EA-off wedged the unit-1 debug slave (docs/cpu-suite.md, Phase B log)
        {
            pucB[2 * usI] = TH0;                        // naive: high byte, then low byte
            pucB[2 * usI + 1] = TL0;
        }
        EA = 1;
        if(usBatch != 0)                                // batch 0 warms the flash cache: a miss in the loop is a large step that is not a torn read
        {
            ulNaive += CpuTornCount(AWTO_CPU_TORN_SAMPLES);
        }
        EA = 0;
        for(usI = 0; usI < AWTO_CPU_TORN_SAMPLES; usI++)    // high - low - high, retried
        {
            do
            {
                ucH = TH0;
                ucL = TL0;
            }
            while(ucH != TH0);
            pucB[2 * usI] = ucH;
            pucB[2 * usI + 1] = ucL;
        }
        EA = 1;
        s_ausTornAt[0] = 0;
        s_ausTornAt[1] = 0;
        if(usBatch != 0)
        {
            ulProt += CpuTornCount(AWTO_CPU_TORN_SAMPLES);
            if((ulProt != 0) && (g_stAwtoCpu.ulV2 == 0))
            {
                g_stAwtoCpu.ulV2 = ((unsigned long)s_ausTornAt[0] << 16) | s_ausTornAt[1];       // first torn protected read
            }
        }
    }
    TR0 = 0;
    g_stAwtoCpu.ulV0 = ulNaive;                         // information: torn naive reads (the hazard is real when > 0)
    g_stAwtoCpu.ulV1 = ulProt;
    g_stAwtoCpu.usBad += (WORD)ulProt;
    CpuEnd();
}

static BYTE CpuDue(WORD usNow, WORD usDeadline)          // the firmware's deadline form
{
    return ((WORD)(usNow - usDeadline) < 0x8000) ? 1 : 0;
}

static void CaseMs16(void)
{
    static const __code WORD tD[5] = {0, 1, 2, 100, 1000};
    static const __code WORD tS[4] = {(WORD)-16, (WORD)-1, 0, 0x7FFF};
    BYTE ucS;
    BYTE ucD;
    WORD usStart;
    WORD usDead;
    WORD usPrev;
    WORD usCur;
    BYTE ucSeen = 0;
    WORD usSave;
    WORD usT0;

    CpuBegin();
    for(ucS = 0; ucS < 4; ucS++)
    {
        for(ucD = 0; ucD < 5; ucD++)
        {
            usStart = tS[ucS];
            usDead = usStart + tD[ucD];
            if(CpuDue((WORD)(usStart + tD[ucD]), usDead) != 1)
            {
                g_stAwtoCpu.usBad++;                    // due at the deadline
            }
            if((tD[ucD] != 0) && (CpuDue((WORD)(usStart + tD[ucD] - 1), usDead) != 0))
            {
                g_stAwtoCpu.usBad++;                    // not due one tick early
            }
            if(CpuDue((WORD)(usStart + tD[ucD] + 1), usDead) != 1)
            {
                g_stAwtoCpu.usBad++;                    // still due one tick late
            }
        }
    }
    EA = 0;                                             // the real counter across 65535 -> 0
    usSave = d_isr_g_usTimerCounter;
    d_isr_g_usTimerCounter = AWTO_CPU_MS_START_LO;
    EA = 1;
    usT0 = AWTO_CPU_MS_START_LO;
    usPrev = CpuNow();
    while(ucSeen < AWTO_CPU_MS_TICKS)
    {
        if(CpuWaitTick(&usCur) == 0)
        {
            g_stAwtoCpu.usBad++;
            break;
        }
        if(((WORD)(usCur - usPrev) == 0) || ((WORD)(usCur - usPrev) > AWTO_CPU_MS_STEP_MAX))
        {
            g_stAwtoCpu.usBad++;                        // a repeat, a step back or a jump across the wrap
        }
        usPrev = usCur;
        ucSeen++;
    }
    g_stAwtoCpu.ulV0 = usPrev;                          // last counter value (small = wrapped)
    EA = 0;
    d_isr_g_usTimerCounter = (WORD)(usSave + (WORD)(usPrev - usT0));
    EA = 1;
    CpuEnd();
}

static void CaseMs32(void)
{
    BYTE ucSeen = 0;
    WORD usLo;
    WORD usHi;
    unsigned long ulPrev;
    unsigned long ulCur;
    unsigned long ulNew;
    WORD usT;

    CpuBegin();
    EA = 0;
    usLo = isr_g_stAwtoDiag.usT2Isr;
    usHi = g_stAwtoHt.usUpHi;
    isr_g_stAwtoDiag.usT2Isr = AWTO_CPU_MS_START_LO;
    g_usAwtoLoSeen = AWTO_CPU_MS_START_LO;
    g_stAwtoHt.usUpHi = 0xFFFF;
    EA = 1;
    ulPrev = AwtoMs();
    while(ucSeen < AWTO_CPU_MS_TICKS)
    {
        if(CpuWaitTick(&usT) == 0)
        {
            g_stAwtoCpu.usBad++;
            break;
        }
        ulCur = AwtoMs();
        if(((unsigned long)(ulCur - ulPrev) == 0UL) || ((unsigned long)(ulCur - ulPrev) > AWTO_CPU_MS_STEP_MAX))
        {
            g_stAwtoCpu.usBad++;                        // 2^32 wrap: a jump of 65536 (hi bumped early), a repeat or a step back; a late read may see 2 ticks
        }
        ulPrev = ulCur;
        ucSeen++;
    }
    g_stAwtoCpu.ulV0 = ulPrev;                          // small = wrapped through 0xFFFFFFFF
    ulNew = (((unsigned long)usHi << 16) | usLo) + ucSeen;
    EA = 0;
    isr_g_stAwtoDiag.usT2Isr = (WORD)ulNew;
    g_usAwtoLoSeen = (WORD)ulNew;
    g_stAwtoHt.usUpHi = (WORD)(ulNew >> 16);
    EA = 1;
    CpuEnd();
}

static void CaseDrift(void)                              // Timer1 counts vs Timer2 counts over usArg ticks (one window per tick)
{
    WORD usTicks = (g_stAwtoCpu.usArg != 0) ? g_stAwtoCpu.usArg : AWTO_CPU_DRIFT_TICKS_DEF;

    if(usTicks > AWTO_CPU_DRIFT_TICKS_MAX)
    {
        usTicks = AWTO_CPU_DRIFT_TICKS_MAX;
    }
    CpuRateRun(1, usTicks, 1);
}

//--------------------------------------------------
// INTERRUPTS
//--------------------------------------------------
static void CaseTrig(BYTE ucVec)                         // software flag -> exactly one ISR; entry latency in timer counts
{
    BYTE ucI;
    BYTE ucWait;
    BYTE ucIdx = (ucVec == AWTO_CPU_VEC_EX0) ? 0 : ((ucVec == AWTO_CPU_VEC_T0) ? 1 : 2);
    WORD usS0;
    WORD usS1;
    WORD usLat;
    WORD usMin = 0xFFFF;
    WORD usMax = 0;
    unsigned long ulSum = 0;
    BYTE ucL0;
    BYTE ucH0;

    CpuBegin();
    isr_g_ucCpuIsr = 1;
    TR0 = 1;
    TR1 = 1;
    if(ucVec == AWTO_CPU_VEC_EX0) { EX0 = 1; } else if(ucVec == AWTO_CPU_VEC_T0) { ET0 = 1; } else { ET1 = 1; }
    for(ucI = 0; ucI < AWTO_CPU_TRIG_N; ucI++)
    {
        ucWait = 0;
        if(ucVec == AWTO_CPU_VEC_T0)
        {
            do
            {
                ucH0 = TH1;
                ucL0 = TL1;
            }
            while(ucH0 != TH1);
            TF0 = 1;
        }
        else
        {
            do
            {
                ucH0 = TH0;
                ucL0 = TL0;
            }
            while(ucH0 != TH0);
            if(ucVec == AWTO_CPU_VEC_EX0) { IE0 = 1; } else { TF1 = 1; }
        }
        usS0 = ((WORD)ucH0 << 8) | ucL0;
        while((isr_s_ausCnt[ucIdx] == ucI) && (++ucWait < AWTO_CPU_TRIG_SPIN))
        {
        }
        if(isr_s_ausCnt[ucIdx] == ucI)
        {
            g_stAwtoCpu.usBad++;                        // no ISR for this flag
            break;
        }
        usS1 = (ucVec == AWTO_CPU_VEC_T0) ? (((WORD)isr_s_aucSnap[3] << 8) | isr_s_aucSnap[2]) : (((WORD)isr_s_aucSnap[1] << 8) | isr_s_aucSnap[0]);
        usLat = usS1 - usS0;
        if(ucI >= AWTO_CPU_TRIG_WARM)                   // the first triggers run with a cold flash cache: slower, reported by the host as the first-run value
        {
            if(usLat < usMin) { usMin = usLat; }
            if(usLat > usMax) { usMax = usLat; }
            ulSum += usLat;
        }
    }
    CpuEnd();
    g_stAwtoCpu.ulV0 = usMin;
    g_stAwtoCpu.ulV1 = usMax;
    g_stAwtoCpu.ulV2 = ulSum / (AWTO_CPU_TRIG_N - AWTO_CPU_TRIG_WARM);
    if(isr_s_ausCnt[ucIdx] != AWTO_CPU_TRIG_N)
    {
        g_stAwtoCpu.usBad++;                            // every software flag gives exactly one ISR
    }
    if(g_stAwtoCpu.ulV2 > AWTO_CPU_LAT_MAX)
    {
        g_stAwtoCpu.usBad++;                            // the mean; the max also holds a Timer2 ISR (~1000 counts) that landed in between: information
    }
    g_stAwtoCpu.ucSpMax = isr_s_ucSp;
}

static BYTE CpuPrioRun(BYTE ucPx0, BYTE ucPt1)           // EXINT0 and Timer1 pending together: log of the order
{
    CpuBegin();
    isr_g_ucCpuIsr = 1;
    PX0 = ucPx0;
    PT1 = ucPt1;
    EA = 0;
    EX0 = 1;
    ET1 = 1;
    isr_s_ucLogN = 0;
    IE0 = 1;
    TF1 = 1;
    EA = 1;
    _nop_();
    _nop_();
    _nop_();
    _nop_();
    CpuEnd();
    return (isr_s_ucLogN == 2) ? (BYTE)((isr_s_aucLog[0] << 4) | isr_s_aucLog[1]) : 0xFF;
}

static void CasePrio(void)
{
    BYTE ucR;

    ucR = CpuPrioRun(1, 0);
    g_stAwtoCpu.ulV0 = ucR;                             // vectors as nibbles: 0x03 = EXINT0 first
    if(ucR != 0x03) { g_stAwtoCpu.usBad++; }
    ucR = CpuPrioRun(0, 1);
    g_stAwtoCpu.ulV1 = ucR;
    if(ucR != 0x30) { g_stAwtoCpu.usBad++; }
    ucR = CpuPrioRun(0, 0);
    g_stAwtoCpu.ulV2 = ucR;                             // same level: the fixed polling order, EXINT0 first
    if(ucR != 0x03) { g_stAwtoCpu.usBad++; }
    ucR = CpuPrioRun(1, 1);
    if(ucR != 0x03) { g_stAwtoCpu.usBad++; }
}

static BYTE CpuNestRun(BYTE ucPx0)                       // Timer1 ISR raises EXINT0 inside itself
{
    CpuBegin();
    isr_g_ucCpuIsr = 1;
    isr_s_ucMode = AWTO_CPU_MODE_NEST;
    PX0 = ucPx0;
    PT1 = 0;
    EX0 = 1;
    ET1 = 1;
    TF1 = 1;
    _nop_();
    _nop_();
    _nop_();
    _nop_();
    CpuEnd();
    return (isr_s_ucLogN == 3) ? (BYTE)(isr_s_aucLog[1]) : 0xFF;
}

static void CaseNest(void)
{
    BYTE ucR;
    BYTE ucA;

    ucR = CpuNestRun(1);                                // high priority EXINT0: runs inside, log 3, 0, 0x83
    ucA = (isr_s_ucLogN == 3) && (isr_s_aucLog[0] == AWTO_CPU_VEC_T1) && (isr_s_aucLog[2] == (AWTO_CPU_VEC_T1 | AWTO_CPU_EXIT_FLAG));
    g_stAwtoCpu.ulV0 = ucR;
    if((ucR != AWTO_CPU_VEC_EX0) || (ucA == 0)) { g_stAwtoCpu.usBad++; }
    ucR = CpuNestRun(0);                                // same level: waits for the low ISR to finish: log 3, 0x83, 0
    g_stAwtoCpu.ulV1 = ucR;
    if(ucR != (AWTO_CPU_VEC_T1 | AWTO_CPU_EXIT_FLAG)) { g_stAwtoCpu.usBad++; }
    g_stAwtoCpu.ulV2 = isr_s_ucSp;                      // highest SP in the nested ISR
    g_stAwtoCpu.ucSpMax = isr_s_ucSp;
    if(isr_s_ucSp >= 0xF0)
    {
        g_stAwtoCpu.usBad++;                            // < 16 B left below the top of IRAM
    }
}

static void CaseEaGate(void)
{
    BYTE ucI;

    CpuBegin();
    isr_g_ucCpuIsr = 1;
    ET1 = 1;
    EA = 0;
    TF1 = 1;                                            // pending, EA off: no ISR may run
    for(ucI = 0; ucI < AWTO_CPU_EA_NOPS; ucI++)
    {
        _nop_();
    }
    if(isr_s_ausCnt[2] != 0)
    {
        g_stAwtoCpu.usBad++;
    }
    isr_s_ucMark = 0;
    EA = 1;
    isr_s_ucMark = 1;
    isr_s_ucMark = 2;
    _nop_();
    _nop_();
    CpuEnd();
    g_stAwtoCpu.ulV0 = isr_s_ucMarkAtIsr;               // main instructions completed after SETB EA when the ISR started
    g_stAwtoCpu.ulV1 = isr_s_ausCnt[2];
    if((isr_s_ausCnt[2] != 1) || (isr_s_ucMarkAtIsr > 1))
    {
        g_stAwtoCpu.usBad++;
    }
}

static void CaseEaRace(void)
{
    WORD usN;

    CpuBegin();
    isr_g_ucCpuIsr = 1;
    isr_s_ucMode = AWTO_CPU_MODE_RACE;
    isr_s_ucRaceBad = 0;
    isr_s_ucCrit = 0;
    TMOD = AWTO_CPU_TMOD_T1_AR | (AWTO_CPU_TMOD_16 & AWTO_CPU_TMOD_T0_MASK);
    TH1 = AWTO_CPU_RACE_RELOAD;
    TL1 = AWTO_CPU_RACE_RELOAD;
    ET1 = 1;
    TR1 = 1;
    for(usN = 0; usN < AWTO_CPU_RACE_N; usN++)
    {
        EA = 0;
        isr_s_ucCrit = 1;
        _nop_();
        isr_s_ucCrit = 0;
        EA = 1;
        if((usN & 3) != 0)
        {
            _nop_();
        }
    }
    TR1 = 0;
    CpuEnd();
    g_stAwtoCpu.ulV0 = isr_s_ausCnt[2];                 // ISRs taken while the loop ran
    g_stAwtoCpu.ulV1 = isr_s_ucRaceBad;
    g_stAwtoCpu.usBad += isr_s_ucRaceBad;
    if(isr_s_ausCnt[2] == 0)
    {
        g_stAwtoCpu.usBad++;                            // the race never ran
    }
}

//--------------------------------------------------
// Storm: Timer1 mode 2 interrupts at a fixed period while the main loop works on XDATA and shared variables
//--------------------------------------------------
static void CpuStormStart(BYTE ucReload, WORD usMs, BYTE ucMode)
{
    isr_s_ucMode = ucMode;
    isr_s_usShared = 0;
    isr_s_usIsrN = 0;
    isr_s_ucIsrBad = 0;
    isr_s_usDeadline = CpuNow() + usMs;
    isr_s_ucStorm = 1;
    isr_g_ucCpuIsr = 1;
    TMOD = AWTO_CPU_TMOD_T1_AR | (AWTO_CPU_TMOD_16 & AWTO_CPU_TMOD_T0_MASK);
    TH1 = ucReload;
    TL1 = ucReload;
    ET1 = 1;
    TR1 = 1;
}

static BYTE CpuStormAlive(WORD usMs)                     // forces the stop when the ISR did not end it
{
    if(isr_s_ucStorm == 0)
    {
        return 0;
    }
    if((WORD)(CpuNow() - (WORD)(isr_s_usDeadline - usMs)) > (WORD)(usMs + AWTO_CPU_STORM_GRACE_MS + AWTO_CPU_STORM_GRACE_MS))
    {
        TR1 = 0;
        ET1 = 0;
        isr_s_ucStorm = 0;
        g_stAwtoCpu.ucFlags |= AWTO_CPU_F_LIMIT;
        return 0;
    }
    return 1;
}

static WORD CpuStormPass(BYTE ucSeq)                     // main-loop work: XDATA copy + compare, 16-bit read-modify-write
{
    static __xdata BYTE s_aucSrc[AWTO_CPU_WORK_N];
    static __xdata BYTE s_aucDst[AWTO_CPU_WORK_N];
    static __xdata WORD s_usRmw;
    BYTE ucI;
    WORD usBad = 0;
    WORD usWant;
    volatile __xdata BYTE *pucS = s_aucSrc;
    volatile __xdata BYTE *pucD = s_aucDst;

    for(ucI = 0; ucI < AWTO_CPU_WORK_N; ucI++)
    {
        pucS[ucI] = (BYTE)(ucSeq * 7 + ucI * 13);
    }
    for(ucI = 0; ucI < AWTO_CPU_WORK_N; ucI++)
    {
        *pucD++ = *pucS++;
    }
    pucS = s_aucSrc;
    pucD = s_aucDst;
    for(ucI = 0; ucI < AWTO_CPU_WORK_N; ucI++)
    {
        if(*pucD++ != (BYTE)(ucSeq * 7 + ucI * 13))
        {
            usBad++;
        }
    }
    s_usRmw = 0x00F8;                                   // the increments cross 0x00FF -> 0x0100
    usWant = s_usRmw;
    for(ucI = 0; ucI < AWTO_CPU_WORK_RMW; ucI++)
    {
        s_usRmw++;
        usWant++;
    }
    if(s_usRmw != usWant)
    {
        usBad++;
    }
    return usBad;
}

static void CaseStorm(void)
{
    WORD usMs = (g_stAwtoCpu.usArg2 != 0) ? g_stAwtoCpu.usArg2 : AWTO_CPU_STORM_MS_DEF;
    BYTE ucReload = (g_stAwtoCpu.usArg != 0) ? (BYTE)g_stAwtoCpu.usArg : AWTO_CPU_STORM_RELOAD_MAX;
    WORD usPasses = 0;
    WORD usBad = 0;
    BYTE ucSeq = 0;

    CpuBegin();
    CpuStormStart(ucReload, usMs, AWTO_CPU_MODE_STORM);
    while(CpuStormAlive(usMs) != 0)
    {
        usBad += CpuStormPass(ucSeq++);
        usPasses++;
    }
    TR1 = 0;
    ET1 = 0;
    g_stAwtoCpu.usBad += usBad + isr_s_ucIsrBad;
    g_stAwtoCpu.ulV0 = isr_s_usIsrN;                    // ISRs taken
    g_stAwtoCpu.ulV1 = usPasses;                        // main-loop passes completed during the storm
    g_stAwtoCpu.ulV2 = ((unsigned long)isr_s_ucIsrBad << 16) | usBad;
    g_stAwtoCpu.ucSpMax = isr_s_ucSp;
    if((usPasses == 0) || (isr_s_usIsrN == 0))
    {
        g_stAwtoCpu.usBad++;                            // main starved, or no storm
    }
    CpuEnd();
}

static void CaseAtomic(void)
{
    WORD usMs = (g_stAwtoCpu.usArg2 != 0) ? g_stAwtoCpu.usArg2 : AWTO_CPU_STORM_MS_DEF;
    WORD usV;
    WORD usP;
    WORD usPrev = 0;
    WORD usD;
    unsigned long ulNaive = 0;
    unsigned long ulProt = 0;
    unsigned long ulReads = 0;
    BYTE ucEa;

    CpuBegin();
    CpuStormStart(AWTO_CPU_ATOMIC_RELOAD, usMs, AWTO_CPU_MODE_LIGHT);
    while(CpuStormAlive(usMs) != 0)
    {
        usV = isr_s_usShared;                           // two byte reads: the ISR may increment in between
        ucEa = EA;
        EA = 0;
        usP = isr_s_usShared;                           // protected
        EA = ucEa;
        usD = (WORD)(usP - usPrev);
        if(usD > AWTO_CPU_TORN_STEP)
        {
            ulProt++;
        }
        usPrev = usP;
        usD = (WORD)(usV - usP);
        if((usD > AWTO_CPU_TORN_STEP) && (usD < (WORD)(0 - AWTO_CPU_TORN_STEP)))
        {
            ulNaive++;
        }
        ulReads++;
    }
    TR1 = 0;
    ET1 = 0;
    g_stAwtoCpu.ulV0 = ulNaive;                         // information: torn naive reads
    g_stAwtoCpu.ulV1 = ulProt;
    g_stAwtoCpu.ulV2 = ulReads;
    g_stAwtoCpu.usBad += (WORD)ulProt;
    if(isr_s_usShared != isr_s_usIsrN)
    {
        g_stAwtoCpu.usBad++;                            // an ISR increment lost
    }
    CpuEnd();
}

//--------------------------------------------------
// MEMORY
//--------------------------------------------------
static BYTE CpuLfsr(BYTE ucX)
{
    return (BYTE)((ucX << 1) ^ (((ucX & 0x80) != 0) ? AWTO_CPU_LFSR_POLY : 0));
}

static void CpuNops(BYTE ucN)
{
    while(ucN-- != 0)
    {
        _nop_();
    }
}

static void CaseMemPattern(void)
{
    volatile __xdata BYTE *pucB = g_aucCpuBuf;
    WORD usI;
    BYTE ucV;
    BYTE ucR;
    BYTE ucPass;
    BYTE ucDelay = (g_stAwtoCpu.usArg2 != 0) ? (BYTE)g_stAwtoCpu.usArg2 : AWTO_CPU_DELAY_DEF;
    unsigned long ulN = 0;
    WORD usBad = 0;
    volatile __xdata BYTE *pucS;
    volatile __xdata BYTE *pucD;

    CpuBegin();
    for(ucPass = 0; ucPass < 2; ucPass++)               // walking one, then its complement
    {
        for(usI = 0; usI < AWTO_CPU_BUF_N; usI++)
        {
            pucB[usI] = (BYTE)(1 << (usI & 7)) ^ ((ucPass != 0) ? 0xFF : 0x00);
        }
        for(usI = 0; usI < AWTO_CPU_BUF_N; usI++)
        {
            if(pucB[usI] != ((BYTE)(1 << (usI & 7)) ^ ((ucPass != 0) ? 0xFF : 0x00))) { usBad++; }
        }
        ulN += AWTO_CPU_BUF_N;
    }
    for(usI = 0; usI < AWTO_CPU_BUF_N; usI++)           // address in address (a shorted address line shows as a copy)
    {
        pucB[usI] = (BYTE)usI ^ (BYTE)(usI >> 8) ^ 0x5A;
    }
    for(usI = 0; usI < AWTO_CPU_BUF_N; usI++)
    {
        if(pucB[usI] != ((BYTE)usI ^ (BYTE)(usI >> 8) ^ 0x5A)) { usBad++; }
    }
    ulN += AWTO_CPU_BUF_N;
    ucV = 0x5A;                                         // LFSR data, write then read back at once (no delay)
    for(usI = 0; usI < AWTO_CPU_BUF_N; usI++)
    {
        ucV = CpuLfsr(ucV);
        pucB[usI] = ucV;
        ucR = CPU_RD(pucB + usI);
        if(ucR != ucV) { usBad++; }
    }
    ulN += AWTO_CPU_BUF_N;
    ucV = 0xA5;                                         // write, N nops, read back
    for(usI = 0; usI < AWTO_CPU_BUF_N; usI++)
    {
        ucV = CpuLfsr(ucV);
        pucB[usI] = ucV;
        CpuNops(ucDelay);
        if(pucB[usI] != ucV) { usBad++; }
    }
    ulN += AWTO_CPU_BUF_N;
    for(ucPass = 0; ucPass < 3; ucPass++)               // burst copy with pointer increment
    {
        ucV = 0x31 + ucPass;
        for(usI = 0; usI < AWTO_CPU_PAT_HALF; usI++)
        {
            ucV = CpuLfsr(ucV);
            pucB[usI] = ucV;
        }
        pucS = pucB;
        pucD = pucB + AWTO_CPU_PAT_HALF;
        for(usI = 0; usI < AWTO_CPU_PAT_HALF; usI++)
        {
            *pucD++ = *pucS++;
        }
        for(usI = 0; usI < AWTO_CPU_PAT_HALF; usI++)
        {
            if(pucB[usI] != pucB[usI + AWTO_CPU_PAT_HALF]) { usBad++; }
        }
        ulN += AWTO_CPU_PAT_HALF;
    }
    g_stAwtoCpu.ulV0 = ulN;
    g_stAwtoCpu.usBad += usBad;
    CpuEnd();
}

static void CaseGuard(void)
{
    volatile __xdata BYTE *pucW = g_aucCpuGuard + AWTO_CPU_GUARD_N;
    volatile __xdata BYTE *pucP;
    BYTE ucI;
    BYTE ucSeq;
    BYTE ucBad;
    WORD usMs = AWTO_CPU_STORM_MS_DEF;
    WORD usPasses = 0;

    CpuBegin();
    AwtoGuardFill(g_aucCpuGuard, AWTO_CPU_GUARD_N, AWTO_GUARD_SEED_LO);
    AwtoGuardFill(g_aucCpuGuard + 2 * AWTO_CPU_GUARD_N, AWTO_CPU_GUARD_N, AWTO_GUARD_SEED_HI);
    CpuStormStart(AWTO_CPU_ATOMIC_RELOAD, usMs, AWTO_CPU_MODE_LIGHT);
    ucSeq = 0;
    while(CpuStormAlive(usMs) != 0)                     // 16 byte buffer written in bursts while the ISR storm runs
    {
        pucP = pucW;
        for(ucI = 0; ucI < AWTO_CPU_GUARD_N; ucI++)
        {
            *pucP++ = ucSeq + ucI;
        }
        pucP = pucW;
        for(ucI = 0; ucI < AWTO_CPU_GUARD_N; ucI++)
        {
            if(*pucP++ != (BYTE)(ucSeq + ucI)) { g_stAwtoCpu.usBad++; }
        }
        ucSeq++;
        usPasses++;
    }
    TR1 = 0;
    ET1 = 0;
    ucBad = AwtoGuardCheck(g_aucCpuGuard, AWTO_CPU_GUARD_N, AWTO_GUARD_SEED_LO) +
            AwtoGuardCheck(g_aucCpuGuard + 2 * AWTO_CPU_GUARD_N, AWTO_CPU_GUARD_N, AWTO_GUARD_SEED_HI);
    g_stAwtoCpu.ulV0 = ucBad;                           // guard bytes changed (must be 0)
    g_stAwtoCpu.usBad += ucBad;
    g_aucCpuGuard[AWTO_CPU_GUARD_N - 1] ^= 0xFF;        // detector self-test: one deliberate overflow must be seen
    g_stAwtoCpu.ulV1 = AwtoGuardCheck(g_aucCpuGuard, AWTO_CPU_GUARD_N, AWTO_GUARD_SEED_LO);
    if(g_stAwtoCpu.ulV1 != 1)
    {
        g_stAwtoCpu.usBad++;
    }
    g_stAwtoCpu.ulV2 = usPasses;
    if(usPasses == 0)
    {
        g_stAwtoCpu.usBad++;
    }
    CpuEnd();
}

static WORD CpuCrc(void)
{
    WORD usCrc = AWTO_CPU_CRC_INIT;
    WORD usA;
    BYTE ucB;
    BYTE ucK;

    for(usA = AWTO_CPU_CRC_FROM; usA < AWTO_CPU_CRC_TO; usA++)
    {
        ucB = *((__code BYTE *)usA);
        usCrc ^= (WORD)ucB << 8;
        for(ucK = 0; ucK < 8; ucK++)
        {
            usCrc = ((usCrc & 0x8000) != 0) ? (WORD)((usCrc << 1) ^ AWTO_CPU_CRC_POLY) : (WORD)(usCrc << 1);
        }
        if((BYTE)usA == 0)
        {
            CpuFeed();
        }
    }
    return usCrc;
}

static void CaseCrc(void)
{
    BYTE ucP;
    WORD usC;
    WORD usFirst = 0;

    CpuBegin();
    if((g_stAwtoCpu.usArg & 1) != 0)
    {
        CpuStormStart(AWTO_CPU_CRC_LOAD_RELOAD, AWTO_CPU_DRIFT_TICKS_MAX, AWTO_CPU_MODE_LIGHT);     // ISR load for all passes (stopped below)
    }
    for(ucP = 0; ucP < AWTO_CPU_CRC_PASSES; ucP++)
    {
        usC = CpuCrc();
        if(ucP == 0)
        {
            usFirst = usC;
        }
        else if(usC != usFirst)
        {
            g_stAwtoCpu.usBad++;
        }
    }
    TR1 = 0;
    ET1 = 0;
    g_stAwtoCpu.ulV0 = usFirst;                         // host compares with the CRC-16 of the image bytes [CRC_FROM, CRC_TO)
    g_stAwtoCpu.ulV1 = isr_s_usIsrN;                    // ISRs taken during the passes
    CpuEnd();
}

//--------------------------------------------------
// SCALER REGISTER BLOCKS (read-only; the write case only with the host's flag, on the generated candidates)
//--------------------------------------------------
static void CaseRegRead(void)                             // entries usArg .. usArg + usArg2 - 1 of the table (usArg2 0 = all)
{
    WORD usI;
    WORD usK;
    WORD usFrom = g_stAwtoCpu.usArg;
    WORD usTo = (g_stAwtoCpu.usArg2 != 0) ? (WORD)(usFrom + g_stAwtoCpu.usArg2) : AWTO_CPU_RD_N;
    BYTE ucFirst;
    BYTE ucFast;
    BYTE ucSlow;
    unsigned long ulUnstable = 0;
    unsigned long ulFast = 0;
    unsigned long ulFirstBad = 0;
    volatile __xdata BYTE *pucR;

    CpuBegin();
    if(usTo > AWTO_CPU_RD_N)
    {
        usTo = AWTO_CPU_RD_N;
    }
    for(usI = usFrom; usI < usTo; usI++)
    {
        pucR = (volatile __xdata BYTE *)tAwtoCpuRdAddr[usI];
        ucFirst = *pucR;
        CpuNops(AWTO_CPU_RD_SLOW_NOPS);
        ucFirst = *pucR;                                // the settled value
        ucFast = 0;
        for(usK = 0; usK < AWTO_CPU_RD_REPS_DEF; usK++) // back-to-back at the MOVX rate
        {
            if(*pucR != ucFirst)
            {
                ucFast = 1;
            }
        }
        ucSlow = 0;
        for(usK = 0; usK < AWTO_CPU_RD_REPS_DEF; usK++) // with a gap: separates a fast-read fault from an unstable register
        {
            CpuNops(AWTO_CPU_RD_SLOW_NOPS);
            if(*pucR != ucFirst)
            {
                ucSlow = 1;
            }
        }
        ulFast += ucFast;
        if((ucFast | ucSlow) != 0)
        {
            ulUnstable++;
            if(ulFirstBad == 0)
            {
                ulFirstBad = tAwtoCpuRdAddr[usI];
            }
        }
        if((usI & 0x1F) == 0)
        {
            CpuFeed();
        }
    }
    g_stAwtoCpu.ulV0 = ulUnstable;                      // registers whose reads differ from their settled value
    g_stAwtoCpu.ulV1 = ulFast;                          // of those: differing in the back-to-back reads
    g_stAwtoCpu.ulV2 = ulFirstBad;
    g_stAwtoCpu.usBad += (WORD)ulUnstable;
    CpuEnd();
}

static void CaseRegWrite(void)
{
    static const __code BYTE tPat[AWTO_CPU_WR_PAT_N] = {0xA5, 0x5A, 0xFF, 0x00};
    WORD usI;
    BYTE ucP;
    BYTE ucOrig;
    BYTE ucStore;
    unsigned long ulStore = 0;
    unsigned long ulNot = 0;
    volatile __xdata BYTE *pucR;

    if((g_stAwtoCpu.ucFlags & AWTO_CPU_F_WRITE) == 0)
    {
        g_stAwtoCpu.ucState = AWTO_CPU_ST_REFUSED;
        return;
    }
    CpuBegin();
    for(usI = 0; usI < AWTO_CPU_WR_N; usI++)
    {
        pucR = (volatile __xdata BYTE *)tAwtoCpuWrAddr[usI];
        ucOrig = *pucR;
        *pucR = tPat[0];
        CpuNops(AWTO_CPU_RD_SLOW_NOPS);
        ucStore = (*pucR == tPat[0]);                   // a register that does not hold a written pattern is no scratch storage
        if(ucStore != 0)
        {
            ulStore++;
            for(ucP = 0; ucP < AWTO_CPU_WR_PAT_N; ucP++)
            {
                *pucR = tPat[ucP];
                if(CPU_RD(pucR) != tPat[ucP])
                {
                    g_stAwtoCpu.usBad++;                // read-back right after the write (no delay) differs
                }
            }
        }
        else
        {
            ulNot++;
        }
        *pucR = ucOrig;
        CpuFeed();
    }
    g_stAwtoCpu.ulV0 = ulStore;
    g_stAwtoCpu.ulV1 = ulNot;
    CpuEnd();
}

//--------------------------------------------------
// SDK timing helpers as black boxes (wall time in Timer2 ticks)
//--------------------------------------------------
static void CaseDelayXms(void)
{
    WORD usMs = g_stAwtoCpu.usArg;
    WORD usT0;
    WORD usT1;

    CpuBegin();
    if(usMs > AWTO_CPU_D_XMS_MAX)
    {
        usMs = AWTO_CPU_D_XMS_MAX;
    }
    if(CpuWaitTick(&usT0) != 0)
    {
        ScalerTimerDelayXms(usMs);
        usT1 = CpuNow();
        g_stAwtoCpu.ulV0 = (WORD)(usT1 - usT0);
        g_stAwtoCpu.ulV1 = usMs;
        if(((WORD)(usT1 - usT0) < usMs) || ((WORD)(usT1 - usT0) > (WORD)(usMs + 2)))
        {
            g_stAwtoCpu.usBad++;                        // elapsed ticks outside [ms, ms + 2] (tick quantisation: start phase + stop edge)
        }
    }
    CpuEnd();
}

static void CaseDelay5us(void)
{
    WORD usT0;
    WORD usT1;
    WORD usI;
    unsigned long ulPct;

    CpuBegin();
    if(CpuWaitTick(&usT0) != 0)
    {
        for(usI = 0; usI < AWTO_CPU_D_5US_N; usI++)
        {
            DELAY_5US();
        }
        usT1 = CpuNow();
        ulPct = (unsigned long)(WORD)(usT1 - usT0) * 100000UL / ((unsigned long)AWTO_CPU_D_5US_N * 5UL);
        g_stAwtoCpu.ulV0 = ulPct;                       // measured / nominal, percent (tick quantisation +-1 ms of 20)
        g_stAwtoCpu.ulV1 = (WORD)(usT1 - usT0);
        if((ulPct < AWTO_CPU_D_PCT_LO) || (ulPct > AWTO_CPU_D_PCT_HI))
        {
            g_stAwtoCpu.usBad++;
        }
    }
    CpuEnd();
}

static void CaseDelayXus(void)
{
    WORD usT0;
    WORD usT1;
    WORD usI;
    unsigned long ulPct;

    CpuBegin();
    if(CpuWaitTick(&usT0) != 0)
    {
        for(usI = 0; usI < AWTO_CPU_D_XUS_N; usI++)
        {
            DELAY_XUS(AWTO_CPU_D_XUS_US);
        }
        usT1 = CpuNow();
        ulPct = (unsigned long)(WORD)(usT1 - usT0) * 100000UL / ((unsigned long)AWTO_CPU_D_XUS_N * AWTO_CPU_D_XUS_US);
        g_stAwtoCpu.ulV0 = ulPct;
        g_stAwtoCpu.ulV1 = (WORD)(usT1 - usT0);
        if((ulPct < AWTO_CPU_D_PCT_LO) || (ulPct > AWTO_CPU_D_PCT_HI))
        {
            g_stAwtoCpu.usBad++;
        }
    }
    CpuEnd();
}

static void CaseDelayPoll(void)                          // ScalerTimerPollingFlagProc on a flag that never sets: returns at the timeout
{
    WORD usMs = g_stAwtoCpu.usArg;
    WORD usT0;
    WORD usT1;

    CpuBegin();
    if(usMs > AWTO_CPU_POLL_MAX)
    {
        usMs = AWTO_CPU_POLL_MAX;
    }
    if(CpuWaitTick(&usT0) != 0)
    {
        if(ScalerTimerPollingFlagProc(usMs, AWTO_CPU_POLL_REG, AWTO_CPU_POLL_BIT, _TRUE) != _FALSE)
        {
            g_stAwtoCpu.usBad++;                        // the flag cannot be set
        }
        usT1 = CpuNow();
        g_stAwtoCpu.ulV0 = (WORD)(usT1 - usT0);
        g_stAwtoCpu.ulV1 = usMs;
        if(((WORD)(usT1 - usT0) < usMs) || ((WORD)(usT1 - usT0) > (WORD)(usMs + 2)))
        {
            g_stAwtoCpu.usBad++;
        }
    }
    CpuEnd();
}

//--------------------------------------------------
// Runner
//--------------------------------------------------
static void CpuRun(BYTE ucCase)
{
    WORD usT0 = CpuNow();

    g_stAwtoCpu.usBad = 0;
    g_stAwtoCpu.ulV0 = 0;
    g_stAwtoCpu.ulV1 = 0;
    g_stAwtoCpu.ulV2 = 0;
    g_stAwtoCpu.ucFlags &= ~AWTO_CPU_F_LIMIT;
    g_stAwtoCpu.ucState = AWTO_CPU_ST_DONE;
    g_stAwtoCpu.usRcap = CpuRcap();
    switch(ucCase)
    {
        case AWTO_CPU_C_T_RATE0:        CaseRate(0); break;
        case AWTO_CPU_C_T_RATE1:        CaseRate(1); break;
        case AWTO_CPU_C_T_RELOAD:       CaseReload(); break;
        case AWTO_CPU_C_T_FULL:         CaseFull(); break;
        case AWTO_CPU_C_T_AUTORELOAD:   CaseAutoReload(); break;
        case AWTO_CPU_C_T_TORN:         CaseTorn(); break;
        case AWTO_CPU_C_T_MS16:         CaseMs16(); break;
        case AWTO_CPU_C_T_MS32:         CaseMs32(); break;
        case AWTO_CPU_C_T_DRIFT:        CaseDrift(); break;
        case AWTO_CPU_C_I_TRIG_EX0:     CaseTrig(AWTO_CPU_VEC_EX0); break;
        case AWTO_CPU_C_I_TRIG_T0:      CaseTrig(AWTO_CPU_VEC_T0); break;
        case AWTO_CPU_C_I_TRIG_T1:      CaseTrig(AWTO_CPU_VEC_T1); break;
        case AWTO_CPU_C_I_PRIO:         CasePrio(); break;
        case AWTO_CPU_C_I_NEST:         CaseNest(); break;
        case AWTO_CPU_C_I_EA_GATE:      CaseEaGate(); break;
        case AWTO_CPU_C_I_EA_RACE:      CaseEaRace(); break;
        case AWTO_CPU_C_I_STORM:        CaseStorm(); break;
        case AWTO_CPU_C_I_ATOMIC:       CaseAtomic(); break;
        case AWTO_CPU_C_M_PATTERN:      CaseMemPattern(); break;
        case AWTO_CPU_C_M_GUARD:        CaseGuard(); break;
        case AWTO_CPU_C_M_CRC:          CaseCrc(); break;
        case AWTO_CPU_C_R_READ:         CaseRegRead(); break;
        case AWTO_CPU_C_R_WRITE:        CaseRegWrite(); break;
        case AWTO_CPU_C_D_XMS:          CaseDelayXms(); break;
        case AWTO_CPU_C_D_5US:          CaseDelay5us(); break;
        case AWTO_CPU_C_D_XUS:          CaseDelayXus(); break;
        case AWTO_CPU_C_D_POLL:         CaseDelayPoll(); break;
        default:                        g_stAwtoCpu.ucState = AWTO_CPU_ST_BAD_CASE; break;
    }
    g_stAwtoCpu.usMs = (WORD)(CpuNow() - usT0);
    g_stAwtoCpu.ucPass = (g_stAwtoCpu.ucState == AWTO_CPU_ST_DONE) && (g_stAwtoCpu.usBad == 0) && ((g_stAwtoCpu.ucFlags & AWTO_CPU_F_LIMIT) == 0);
}

void AwtoCpuSuiteMain(void)
{
    BYTE ucCase;
    unsigned long ulLast;

    AwtoStackPaint();
    AwtoWdtInit();
    AwtoDiagInit();
    AwtoMeasInit();
    AwtoSyncInit();
    ScalerMcuInitial();                                 // clock tree per AWTO_CLOCK_MHZ, Timer0/1/2, WDT, debug slave 0x35 + EXINT1
    SysPowerMcuClock(_M2PLL_CLK);
    ScalerPinshareInitial();
    ScalerTimerInitialTimerEvent();
    ScalerMcuDdcRamEnable();
#if(_AWTO_DBG_SWAP == _ON)
    AwtoDbgLinkSet(0xFF);                               // debug slave 0x35 on the active port's DDC (no DDC/CI in this image to switch it on)
#endif
    g_stAwtoCpu.usBufAt = (WORD)g_aucCpuBuf;
    g_stAwtoCpu.usBufN = AWTO_CPU_BUF_N;
    g_stAwtoCpu.ucStretch = AWTO_CPU_KEEP;
    g_stAwtoCpu.ucCkcon = CKCON;
    g_stAwtoCpu.usRcap = CpuRcap();
    g_stAwtoCpu.ucReady = AWTO_CPU_MAGIC;
    ulLast = AwtoMs();
    for(;;)
    {
        AwtoDiagMainPass();
        AwtoStackCheck();
        g_stAwtoCpu.usBeat++;
        g_stAwtoCpu.ucStackHigh = g_ucAwtoStackHigh;
        ucCase = g_stAwtoCpu.ucGo;
        if(ucCase != 0)
        {
            CpuRun(ucCase);
            g_stAwtoCpu.ucSeq++;
            g_stAwtoCpu.ucGo = 0;
            ulLast = AwtoMs();
        }
        else if((AwtoMs() - ulLast) >= AWTO_CPU_IDLE_MS)
        {
            AwtoWdtHang(AWTO_CPU_HANG_EA_OFF);          // no host request for a while: the hardware watchdog resets the chip, which also clears a stuck IIC slave
        }
    }
}
#endif
