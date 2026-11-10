// awto two-colour power LED.  P3.5 is the normal/on colour and P3.6 is the
// standby colour.  P8.4 is a board power-state enable and must not be used as
// an indicator output.
volatile __xdata unsigned char g_ucAwtoLedMode;
volatile __xdata unsigned char g_ucAwtoLedPhase;
volatile __xdata unsigned char g_ucAwtoLedLevel;
volatile __xdata unsigned char g_ucAwtoLedTick;
volatile __xdata unsigned char g_ucAwtoLedUp;

void AwtoLedSetMode(unsigned char ucMode)
{
    // Power-state code may report the same standby state more than once.  Do
    // not restart the ramp when it does.
    if((ucMode == AWTO_LED_BREATHE) && (g_ucAwtoLedMode == AWTO_LED_BREATHE))
    {
        return;
    }

    // Disable the ISR path while the new state is assembled.
    g_ucAwtoLedMode = AWTO_LED_OFF;
    P3_5 = 0;
    P3_6 = 0;

    if(ucMode == AWTO_LED_ON)
    {
        P3_5 = 1;
    }
    else if(ucMode == AWTO_LED_BREATHE)
    {
        g_ucAwtoLedPhase = 0;
        g_ucAwtoLedLevel = 0;
        g_ucAwtoLedTick = 0;
        g_ucAwtoLedUp = 1;
    }

    g_ucAwtoLedMode = ucMode;
}
