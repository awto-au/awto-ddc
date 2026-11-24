#include "UserCommonInclude.h"
#include "AwtoApps.h"

// Example extra app (docs/extra-apps.md): counts its steps and keys, draws nothing. Built only by `./dev.py build --extra-fw fw/apps/example`;
// tests/test_extra_apps.py + scripts/apps_sim.py start it (VCP 0xEB = 0x20) and read the counters by map symbol.

#define HELLO_STATE_IDLE                        0
#define HELLO_STATE_RUN                         1
#define HELLO_STATE_STOPPED                     2
#define HELLO_KEY_QUIT                          AWTO_K_MENU         // MENU ends the app

__xdata WORD g_usHelloSteps;                                        // step hook calls since the last start
__xdata BYTE g_ucHelloState;
__xdata BYTE g_ucHelloKeys;                                         // key hook calls (every event)
__xdata BYTE g_ucHelloLastKey;

void HelloInit(void)
{
    g_usHelloSteps = 0;
    g_ucHelloKeys = 0;
    g_ucHelloState = HELLO_STATE_RUN;
}

void HelloStep(void)
{
    g_usHelloSteps++;
}

void HelloKey(BYTE ucKey, BYTE ucEv)
{
    g_ucHelloKeys++;
    g_ucHelloLastKey = ucKey;
    if((ucKey == HELLO_KEY_QUIT) && (ucEv == AWTO_KEV_PRESS))
    {
        AwtoAppStop();
    }
}

void HelloStop(void)
{
    g_ucHelloState = HELLO_STATE_STOPPED;
}

AWTO_APP(hello, HelloInit, HelloStep, HelloKey, HelloStop);
