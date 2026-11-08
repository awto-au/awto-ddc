// #67 recovery keys (integrator-owned, private): inserted into RTD2014Key.c (key masks) by fw/awto/settings/rules.py.
#ifdef _AWTO_NEW_SETTINGS
BYTE set_recovery_requested(void)            // MENU (A0 ladder) + DOWN (A1 ladder) down together (#85)
{
    BYTE ucState = 0;
    BYTE ucV1 = PCB_ADKEY1();
    BYTE ucV2 = PCB_ADKEY2();

    PCB_KEY_STATE(0, ucV1, ucV2, 0, ucState);
    return ((ucState & (_MENU_KEY_MASK | _LEFT_KEY_MASK)) == (_MENU_KEY_MASK | _LEFT_KEY_MASK));
}

// Host key injection (#67, menu.h key_inject / key_hold): a key message as the key scan would give it, or a raw key
// mask ORed into RTDKeyScan for ms (long press, combinations; the SDK's own hold timers see it as a held key).
__xdata BYTE g_ucAwtoKeyHold;                // mask, 0 = none
static __xdata WORD s_usAwtoKeyHoldT0;
static __xdata WORD s_usAwtoKeyHoldMs;

void key_inject(BYTE ucKey)
{
    AWTO_KEY_INJECT(ucKey);                  // 0..3 SDK messages, 4 = SOURCE (#85)
}

void key_hold(BYTE ucMask, WORD usMs)
{
    s_usAwtoKeyHoldT0 = g_usTimerCounter;
    s_usAwtoKeyHoldMs = usMs;
    g_ucAwtoKeyHold = ucMask & (_POWER_KEY_MASK | _MENU_KEY_MASK | _RIGHT_KEY_MASK | _LEFT_KEY_MASK | _EXIT_KEY_MASK | _KEY5_MASK);
}

BYTE AwtoKeyHold(void)                       // RTDKeyScan (AWTO_KEY_HOLD): the held mask until its time is up
{
    if((WORD)(g_usTimerCounter - s_usAwtoKeyHoldT0) >= s_usAwtoKeyHoldMs)
    {
        g_ucAwtoKeyHold = 0;
    }
    return g_ucAwtoKeyHold;
}
#endif
