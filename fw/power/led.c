#include "SysInclude.h"

// awto two-colour power LED (awto-ddc#95): bLED_ON (P3.5) on colour, bLED_STANDBY (P3.6) standby colour, breathing by the
// Timer2 ISR (AWTO_LED_T2ISR). Only caller: the system machine (SysJudge.c SysMachineLed), on a colour change.
volatile __xdata unsigned char isr_g_ucAwtoLedMode;
volatile __xdata unsigned char isr_g_ucAwtoLedPhase;
volatile __xdata unsigned char isr_g_ucAwtoLedLevel;
volatile __xdata unsigned char isr_g_ucAwtoLedTick;
volatile __xdata unsigned char isr_g_ucAwtoLedUp;
volatile __xdata unsigned char g_ucAwtoLedPins;

void AwtoLedSet(unsigned char ucMode, unsigned char ucState)
{
    isr_g_ucAwtoLedMode = AWTO_LED_OFF;             // ISR path off while the pins are set
    bLED_ON = 0;
    bLED_STANDBY = 0;
    isr_g_ucAwtoLedPhase = 0;                       // breathing starts dark, ramps up
    isr_g_ucAwtoLedLevel = 0;
    isr_g_ucAwtoLedTick = 0;
    isr_g_ucAwtoLedUp = 1;
    if(ucMode == AWTO_LED_ON)
    {
        bLED_ON = 1;
    }
    isr_g_ucAwtoLedMode = ucMode;
    g_ucAwtoLedPins = MCU_FFE3_PORT3_PIN_REG;
    AWTO_PNL_LOG(AWTO_SW_EV_LED, ucMode, ucState);      // "LED: <colour> (<state>)" (sync.tsv 1C)
}
