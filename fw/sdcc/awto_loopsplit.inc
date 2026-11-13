// #75 main-loop split, inserted into SysMain.c by keil2sdcc.py: slow checks run when AWTO_SLOW_MS have passed.
// Time base = Timer2 ISR count (1 per ms tick); d_isr_g_usTimerCounter is rebased by the timer-event code.
#if(_AWTO_LOOP_SPLIT == _ON)
__xdata StAwtoLoop g_stAwtoLoop;
static __xdata unsigned int s_pusAwtoSlowLast[AWTO_SLOW_SLOTS];
static __xdata unsigned int s_usAwtoWinMs;
static __xdata unsigned int s_usAwtoWinRuns;
static __xdata unsigned int s_usAwtoWinHb;
static __xdata unsigned int s_usAwtoWinGap;

bit AwtoSlowDue(unsigned char ucSlot)
{
    unsigned int usNow;
    unsigned int usGap;

    usNow = (WORD)AwtoMs();
    usGap = usNow - s_pusAwtoSlowLast[ucSlot];
    if(usGap < AWTO_SLOW_MS)
    {
        return _FALSE;
    }
    s_pusAwtoSlowLast[ucSlot] = usNow;
    if(ucSlot != AWTO_SLOW_JUDGE)
    {
        return _TRUE;
    }
    g_stAwtoLoop.usSlowRuns++;
    if(usGap > s_usAwtoWinGap)
    {
        s_usAwtoWinGap = usGap;
    }
    if((unsigned int)(usNow - s_usAwtoWinMs) >= 1000)
    {
        g_stAwtoLoop.usSlowRate = g_stAwtoLoop.usSlowRuns - s_usAwtoWinRuns;
        g_stAwtoLoop.usFastRate = isr_g_stAwtoDiag.usHeartbeat - s_usAwtoWinHb;
        g_stAwtoLoop.usMaxGapMs = s_usAwtoWinGap;
        s_usAwtoWinRuns = g_stAwtoLoop.usSlowRuns;
        s_usAwtoWinHb = isr_g_stAwtoDiag.usHeartbeat;
        s_usAwtoWinMs = usNow;
        s_usAwtoWinGap = 0;
    }
    return _TRUE;
}
#endif
