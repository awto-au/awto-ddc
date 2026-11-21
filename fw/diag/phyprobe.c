#include "ScalerFunctionInclude.h"

// Test-only (-D AWTO_TMDS_PHY_PROBE): per-lock TMDS PHY set-up timing to the sync ring (AWTO_SYNC_EV_PHYT, #256).
#if(AWTO_TMDS_PHY_PROBE != 0)
typedef struct
{
    unsigned int usTick;
    unsigned char ucF, ucH, ucL;
} StPhyT2;

static __xdata StPhyT2 s_stBegin, s_stNow;
static __xdata unsigned int s_usCk, s_usAdp, s_usCk2, s_usTot;
static __xdata unsigned char s_ucCkEnd, s_ucAdpEnd, s_ucWdOld, s_ucPath;
__xdata unsigned char g_ucPhyProbeSkip;

static void PhySnap(__xdata StPhyT2 *p)
{
    unsigned char ucEa = EA;

    EA = 0;
    do
    {
        p->ucF = TF2;
        p->usTick = d_isr_g_usTimerCounter;
        do
        {
            p->ucH = TH2;
            p->ucL = TL2;
        }
        while(p->ucH != TH2);
    }
    while(p->ucF != TF2);
    EA = ucEa;
}

static __xdata unsigned char s_ucFld[4];
static __xdata unsigned int s_usStamp[5];
static __xdata unsigned char s_ucPort, s_ucRetry, s_ucSeq;     // s_ucSeq: lock counter, keeps the ring from collapsing equal lines
static __xdata unsigned int s_usRegWd, s_usRegCk, s_usRegAdp, s_usT, s_usPer;
static __xdata unsigned long s_ulC;

static unsigned int PhyUsSince(__xdata StPhyT2 *a)
{
    s_usPer = 0x10000UL - (((unsigned int)RCAP2H << 8) | RCAP2L);
    PhySnap(&s_stNow);
    s_ulC = (unsigned long)(unsigned int)((s_stNow.usTick + s_stNow.ucF) - (a->usTick + a->ucF)) * s_usPer;
    s_ulC += (((unsigned int)s_stNow.ucH << 8) | s_stNow.ucL) - (((unsigned int)a->ucH << 8) | a->ucL);
    s_ulC = (s_ulC * 1000UL) / s_usPer;
    return (s_ulC > 0xFFFEUL) ? 0xFFFEU : (unsigned int)s_ulC;
}

// ucPort 2 / 3 = page 7B / 7C
void AwtoPhyProbeStart(unsigned char ucPort, unsigned char ucPath)
{
    s_ucPort = ucPort;
    s_usRegWd = (ucPort == 2) ? P7B_0F_WD : P7C_0F_WD;
    s_usRegCk = (ucPort == 2) ? P7B_0E_SDM_03 : P7C_0E_SDM_03;
    s_usRegAdp = (ucPort == 2) ? P7B_2A_ANA_CDR_00 : P7C_2A_ANA_CDR_00;
    s_ucWdOld = ScalerGetBit_EXINT(s_usRegWd, _BIT0);
    ScalerSetBit_EXINT(s_usRegWd, ~_BIT0, _BIT0);
    s_usCk = 0xFFFF;
    s_usAdp = 0xFFFF;
    s_usCk2 = 0xFFFF;
    s_ucCkEnd = 0;
    s_ucAdpEnd = 0;
    s_ucPath = ucPath;
    s_ucRetry = 0;
    s_usStamp[0] = s_usStamp[1] = s_usStamp[2] = s_usStamp[3] = s_usStamp[4] = 0xFFFF;
    s_ucFld[0] = s_ucFld[1] = s_ucFld[2] = s_ucFld[3] = 0xFF;
    s_ucSeq++;
    PhySnap(&s_stBegin);
}

// ucKind 0: FLD wait 360 us (adp_en x3 and ckrdy), 1: CMU wait 150 us (ckrdy); polls to the full time, first-high times kept
void AwtoPhyProbeWait(unsigned char ucKind)
{
    static __xdata StPhyT2 stA;
    static __xdata unsigned int usN;

    usN = (ucKind == 0) ? 360 : 150;
    PhySnap(&stA);
    do
    {
        s_usT = PhyUsSince(&stA);
        if(ScalerGetBit_EXINT(s_usRegCk, _BIT4) != 0)
        {
            if((ucKind == 0) && (s_usCk == 0xFFFF)) { s_usCk = s_usT; }
            if((ucKind == 1) && (s_usCk2 == 0xFFFF)) { s_usCk2 = s_usT; }
        }
        if((ucKind == 0) && (s_usAdp == 0xFFFF) && (ScalerGetBit_EXINT(s_usRegAdp, (_BIT6 | _BIT5 | _BIT4)) == (_BIT6 | _BIT5 | _BIT4)))
        {
            s_usAdp = s_usT;
        }
    }
    while(s_usT < usN);
    s_ucCkEnd = (ScalerGetBit_EXINT(s_usRegCk, _BIT4) != 0) ? 1 : 0;
    if(ucKind == 0)
    {
        s_ucAdpEnd = ScalerGetBit_EXINT(s_usRegAdp, (_BIT6 | _BIT5 | _BIT4)) >> 4;
    }
}

// knob bit 1: plain blind waits, no polling (timing reference)
bit AwtoPhyProbePlain(void)
{
    return ((g_ucPhyProbeSkip & 2) != 0) ? _TRUE : _FALSE;
}

bit AwtoPhyProbeSkip(void)
{
    return ((g_ucPhyProbeSkip & 1) != 0) ? _TRUE : _FALSE;
}

void AwtoPhyProbeMark(void)
{
    s_usTot = PhyUsSince(&s_stBegin);
}

// us since the set-up start at a checkpoint
void AwtoPhyProbeStamp(unsigned char ucN)
{
    s_usStamp[ucN] = PhyUsSince(&s_stBegin);
}

// band fine-tune poll loops: iterations used (61 = timed out, 0xFF = loop not run)
void AwtoPhyProbeFld(unsigned char ucLoop, unsigned char ucCount)
{
    s_ucFld[ucLoop] = ucCount;
}

void AwtoPhyProbeRetry(void)
{
    s_ucRetry = 1;
}

void AwtoPhyProbeEnd(unsigned char ucCdrOk)
{
    ScalerSetBit_EXINT(s_usRegWd, ~_BIT0, (s_ucWdOld != 0) ? _BIT0 : 0x00);
    AwtoSyncPush(AWTO_SYNC_EV_PHYT, s_ucPort, ((unsigned long)s_usTot << 16) | ((unsigned int)(s_ucSeq & 7) << 13) | isr_g_usInputPixelClk);
    AwtoSyncPush(AWTO_SYNC_EV_PHYT, 0x10 | s_ucPort, ((unsigned long)s_usAdp << 16) | s_usCk);
    AwtoSyncPush(AWTO_SYNC_EV_PHYT, 0x40 | s_ucPort, ((unsigned long)s_ucFld[0] << 24) | ((unsigned long)s_ucFld[1] << 16) | ((unsigned int)s_ucFld[2] << 8) | s_ucFld[3]);
    AwtoSyncPush(AWTO_SYNC_EV_PHYT, 0x50 | s_ucPort, ((unsigned long)s_usStamp[0] << 16) | s_usStamp[1]);
    AwtoSyncPush(AWTO_SYNC_EV_PHYT, 0x60 | s_ucPort, ((unsigned long)s_usStamp[2] << 16) | s_usStamp[3]);
    AwtoSyncPush(AWTO_SYNC_EV_PHYT, 0x70 | s_ucPort, ((unsigned long)s_usStamp[4] << 16) | s_usTot);
    AwtoSyncPush(AWTO_SYNC_EV_PHYT, 0x20 | s_ucPort, ((unsigned long)s_usCk2 << 16) | ((unsigned int)(s_ucSeq & 0x3F) << 10) | ((unsigned int)s_ucPath << 8) | (s_ucAdpEnd << 4) | (s_ucRetry << 3) | (s_ucCkEnd << 2) | ((g_ucPhyProbeSkip & 1) << 1) | ucCdrOk);
}
#endif
