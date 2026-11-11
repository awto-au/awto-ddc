// #67 recovery keys (integrator-owned, private): inserted into RTD2014Key.c by fw/awto/settings/rules.py.
#ifdef _AWTO_NEW_SETTINGS
BYTE set_recovery_requested(void)            // physical MENU (A0) + DOWN (A1) down together (#85): a fresh input-monitor poll
{
    return ((AwtoKeyMaskLive() & (AWTO_KM_MENU | AWTO_KM_DOWN)) == (AWTO_KM_MENU | AWTO_KM_DOWN));
}

// Host key injection (#67, menu.h key_inject / key_hold): one key press through the key router, or a raw key mask
// (AWTO_KM_*) ORed into the key reader's samples for ms (long press, combinations: debounce, combo and repeat rules apply).
__xdata BYTE g_ucAwtoKeyHold;                // mask, 0 = none
static __xdata WORD s_usAwtoKeyHoldT0;
static __xdata WORD s_usAwtoKeyHoldMs;

void key_inject(BYTE ucKey)
{
    AwtoKeyInject(ucKey);                    // 0..3 SDK key messages, 4 = SOURCE (#85)
}

void key_hold(BYTE ucMask, WORD usMs)
{
    s_usAwtoKeyHoldT0 = g_usTimerCounter;
    s_usAwtoKeyHoldMs = usMs;
    g_ucAwtoKeyHold = ucMask & (AWTO_KM_POWER | AWTO_KM_AUTO | AWTO_KM_UP | AWTO_KM_DOWN | AWTO_KM_MENU | AWTO_KM_SOURCE);
}

BYTE AwtoKeyHold(void)                       // the key reader (AWTO_KEY_HOLD): the held mask until its time is up
{
    if((WORD)(g_usTimerCounter - s_usAwtoKeyHoldT0) >= s_usAwtoKeyHoldMs)
    {
        g_ucAwtoKeyHold = 0;
    }
    return g_ucAwtoKeyHold;
}
#endif
