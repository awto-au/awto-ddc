#if(_AWTO_DIAG == _ON)
// #33: 0x01..0x04 = key MENU/RIGHT/LEFT/EXIT, 0x10+n = OSD event n, 0x20 = debug pop-up (#34). Inserted into RTD2014Key.c (OSD macros).
void AwtoDiagTestCmd(void)
{
    unsigned char ucCmd = g_stAwtoDiag.ucTestCmd;

    if(ucCmd == 0)
    {
        return;
    }
    g_stAwtoDiag.ucTestCmd = 0;
    if(ucCmd <= 4)
    {
        SET_KEYMESSAGE(ucCmd - 1);
    }
    else if(ucCmd == 0x20)
    {
        g_stAwtoDiag.ucDbgPopup = 1;
        SET_OSD_EVENT_MESSAGE(_OSDEVENT_ACTIVE_DO_ONE_TIME_MSG);
    }
    else if(ucCmd >= 0x10)
    {
        SET_OSD_EVENT_MESSAGE(ucCmd - 0x10);
    }
}
#endif
