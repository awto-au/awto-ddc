#include "UserCommonInclude.h"

// #67 settings library key hooks (integrator-owned, private).
#ifdef _AWTO_NEW_SETTINGS
BYTE set_recovery_requested(void)            // no key recovery (#132): defaults by DDC/CI VCP 0x04, debug link by VCP 0xE3
{
    return 0;
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
    s_usAwtoKeyHoldT0 = (WORD)AwtoMs();
    s_usAwtoKeyHoldMs = usMs;
    g_ucAwtoKeyHold = ucMask & (AWTO_KM_POWER | AWTO_KM_AUTO | AWTO_KM_UP | AWTO_KM_DOWN | AWTO_KM_MENU | AWTO_KM_SOURCE);
}

BYTE AwtoKeyHold(void)                       // the key reader (AWTO_KEY_HOLD): the held mask until its time is up
{
    if((WORD)((WORD)AwtoMs() - s_usAwtoKeyHoldT0) >= s_usAwtoKeyHoldMs)
    {
        g_ucAwtoKeyHold = 0;
    }
    return g_ucAwtoKeyHold;
}
#endif
