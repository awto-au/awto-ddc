// #67 recovery keys (integrator-owned, private): inserted into RTD2014Key.c (key masks) by fw/awto/settings/rules.py.
#ifdef _AWTO_NEW_SETTINGS
BYTE set_recovery_requested(void)            // Menu (ADC A0 ladder) + Left (ADC A1 ladder) down together
{
    BYTE ucState = 0;
    BYTE ucV1 = PCB_ADKEY1();
    BYTE ucV2 = PCB_ADKEY2();

    PCB_KEY_STATE(0, ucV1, ucV2, 0, ucState);
    return ((ucState & (_MENU_KEY_MASK | _LEFT_KEY_MASK)) == (_MENU_KEY_MASK | _LEFT_KEY_MASK));
}
#endif
