// Main-loop cost per handler (#60 / main-loop split), inserted into SysMain.c by keil2sdcc.py; off unless _AWTO_LOOP_PROF.
// AWTO_LP(k) before handler k closes the previous segment; host: scripts/loop_prof.py (Timer2 counts -> us per pass).
#if(_AWTO_LOOP_PROF == _ON)
__xdata StAwtoLoopProf g_stAwtoLoopProf;
static __xdata unsigned long s_ulLpLast;
static __xdata unsigned char s_ucLpOk;                 // 1 = this pass counts (all marks so far passed the PS-only check)

void AwtoLpMark(unsigned char ucK)
{
    unsigned int usTick;
    unsigned char ucH, ucL, ucF;
    unsigned long ulNow;
    unsigned int usRcap = ((unsigned int)RCAP2H << 8) | RCAP2L;
    bit bEa = EA;

    EA = 0;
    do
    {
        ucF = TF2;
        usTick = d_isr_g_usTimerCounter;
        do
        {
            ucH = TH2;
            ucL = TL2;
        }
        while(ucH != TH2);
    }
    while(ucF != TF2);
    EA = bEa;
    ulNow = (unsigned long)(unsigned int)(usTick + ucF) * (0x10000UL - usRcap) + ((((unsigned int)ucH << 8) | ucL) - usRcap);
    ucF = (g_stAwtoLoopProf.ucPsOnly == 0) || (GET_POWER_STATUS() == _POWER_STATUS_SAVING);   // PS-only: other passes not counted
    if(ucK == 0)
    {
        if(g_stAwtoLoopProf.ucReset != 0)
        {
            unsigned char ucI;

            for(ucI = 0; ucI < AWTO_LP_SLOTS; ucI++)
            {
                g_stAwtoLoopProf.pulT2[ucI] = 0;
            }
            g_stAwtoLoopProf.ulPasses = 0;
            g_stAwtoLoopProf.ucReset = 0;
            s_ucLpOk = 0;
        }
        else if((g_stAwtoLoopProf.ulPasses != 0) && (s_ucLpOk != 0) && (ucF != 0))
        {
            g_stAwtoLoopProf.pulT2[AWTO_LP_SLOTS - 1] += ulNow - s_ulLpLast;
        }
        if((ucF != 0) && ((s_ucLpOk != 0) || (g_stAwtoLoopProf.ulPasses == 0)))
        {
            g_stAwtoLoopProf.ulPasses++;
        }
        s_ucLpOk = ucF;
        g_stAwtoLoopProf.usPer = 0x10000UL - usRcap;
    }
    else if((s_ucLpOk != 0) && (ucF != 0))
    {
        g_stAwtoLoopProf.pulT2[ucK - 1] += ulNow - s_ulLpLast;
    }
    else
    {
        s_ucLpOk = 0;
    }
    s_ulLpLast = ulNow;
}
#endif
