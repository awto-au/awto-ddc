// Main-loop cost per handler (#60 / main-loop split), inserted into SysMain.c by keil2sdcc.py; off unless _AWTO_LOOP_PROF.
// AWTO_LP(k) before handler k closes the previous segment; host: scripts/loop_prof.py (Timer2 counts -> us per pass).
#if(_AWTO_LOOP_PROF == _ON)
__xdata StAwtoLoopProf g_stAwtoLoopProf;
static __xdata unsigned long s_ulLpLast;

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
        usTick = g_usTimerCounter;
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
        }
        else if(g_stAwtoLoopProf.ulPasses != 0)
        {
            g_stAwtoLoopProf.pulT2[AWTO_LP_SLOTS - 1] += ulNow - s_ulLpLast;
        }
        g_stAwtoLoopProf.ulPasses++;
        g_stAwtoLoopProf.usPer = 0x10000UL - usRcap;
    }
    else
    {
        g_stAwtoLoopProf.pulT2[ucK - 1] += ulNow - s_ulLpLast;
    }
    s_ulLpLast = ulNow;
}
#endif
