#if(_AWTO_DIAG == _ON)
// #33: 0x01..0x04 = key MENU/RIGHT/LEFT/EXIT, 0x10+n = OSD event n, 0x20 = debug pop-up (#34), 0x21 = redraw the boot logo for 3 s (#46).
// 0x22/0x23 reserved: message log on/off (wb-msgtable, #56). #28 hold variants (stay until cleared, g_stAwtoDiag.ucHold bits):
// 0x24 logo on, 0x25 logo off, 0x26 debug pop-up held, 0x27 clear all holds. Inserted into RTD2014Key.c (OSD macros).
#define AWTO_HOLD_LOGO                          0x01
#define AWTO_HOLD_POPUP                         0x02

#if(_AWTO_DEMO_LOGO == _ON)
void AwtoTestHoldLogoOff(void)      // global: its map symbol tells hosts (osd_test.py) that 0x24..0x27 exist
{
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE_OSD_LOGO);
    OsdDispDisableOsd();
    SET_OSD_LOGO_ON(_OFF);
    ScalerDDomainPatternGenEnable(_DISABLE);
    if(SysModeGetModeState() == _MODE_STATUS_ACTIVE)
    {
        ScalerDDomainBackgroundEnable(_DISABLE);        // picture back; the SDK logo timeout blanks + backlight off (boot path)
    }
    else
    {
        ScalerTimerActiveTimerEvent(0, _USER_TIMER_EVENT_OSD_DISABLE_OSD_LOGO);   // no video: the SDK's own logo end
    }
}
#endif

void AwtoDiagTestCmd(void)
{
    unsigned char ucCmd = g_stAwtoDiag.ucTestCmd;

    if((g_stAwtoDiag.ucHold & AWTO_HOLD_POPUP) != 0)
    {
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);      // each pop-up draw re-arms its timeout
    }
    if(ucCmd == 0)
    {
        return;
    }
    g_stAwtoDiag.ucTestCmd = 0;
    if(ucCmd <= 4)
    {
        SET_KEYMESSAGE(ucCmd - 1);
    }
    else if((ucCmd == 0x20) || (ucCmd == 0x26))
    {
        g_stAwtoDiag.ucDbgPopup = 1;
        if(ucCmd == 0x26)
        {
            g_stAwtoDiag.ucHold |= AWTO_HOLD_POPUP;
        }
        SET_OSD_EVENT_MESSAGE(_OSDEVENT_ACTIVE_DO_ONE_TIME_MSG);
    }
    else if(ucCmd == 0x27)
    {
        if((g_stAwtoDiag.ucHold & AWTO_HOLD_POPUP) != 0)
        {
            OsdDispDisableOsd();
        }
#if(_AWTO_DEMO_LOGO == _ON)
        if((g_stAwtoDiag.ucHold & AWTO_HOLD_LOGO) != 0)
        {
            AwtoTestHoldLogoOff();
        }
#endif
        g_stAwtoDiag.ucHold = 0;
    }
#if(_AWTO_DEMO_LOGO == _ON)
    else if((ucCmd == 0x21) || (ucCmd == 0x24))
    {
        OsdDispShowLogo();
        if(ucCmd == 0x21)
        {
            ScalerTimerActiveTimerEvent(SEC(3), _USER_TIMER_EVENT_OSD_DISABLE_OSD_LOGO);
        }
        else
        {
            ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE_OSD_LOGO);
            g_stAwtoDiag.ucHold |= AWTO_HOLD_LOGO;
        }
    }
    else if(ucCmd == 0x25)
    {
        AwtoTestHoldLogoOff();
        g_stAwtoDiag.ucHold &= ~AWTO_HOLD_LOGO;
    }
#endif
    else if((ucCmd >= 0x10) && (ucCmd <= (0x10 + _OSDEVENT_DP_VERSIOM_MSG)))      // awto: #53.17 last event id
    {
        SET_OSD_EVENT_MESSAGE(ucCmd - 0x10);
    }
}
#endif
