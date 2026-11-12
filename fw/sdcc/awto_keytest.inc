// #39 key panel + #85 key log, fed by the key reader (fw/sdcc/awto_keys.inc, #129). Inserted into RTD2014Key.c (keil2sdcc.py).
// Layout of g_stAwtoKey: RL6449_Project.h, host: rtd_keywatch.py.
#if(_AWTO_DIAG == _ON)
typedef char AwtoKeyMaskCheck[((_POWER_KEY_MASK == AWTO_KM_POWER) && (_EXIT_KEY_MASK == AWTO_KM_MENU) && (_RIGHT_KEY_MASK == AWTO_KM_UP) &&
                              (_LEFT_KEY_MASK == AWTO_KM_DOWN) && (_MENU_KEY_MASK == AWTO_KM_AUTO) && (_KEY5_MASK == AWTO_KM_SOURCE)) ? 1 : -1];
#ifdef _AWTO_NEW_SETTINGS
#define AWTO_KEY_HELD_INJ()                     (g_ucAwtoKeyHold != 0)
#else
#define AWTO_KEY_HELD_INJ()                     0
#endif

extern void osd_tc_close(void);
__xdata StAwtoKey g_stAwtoKey;
static __xdata BYTE s_ucAwtoKeyPend;            // log index + 1 of the press still waiting for its key message
static __xdata WORD s_usAwtoKeyDraw;            // usT2Isr at the last redraw
static __xdata BYTE s_pucAwtoKeyShown[6];       // A0 A1 P30 mask msg flags as last drawn (redraw on change only)
static __xdata BYTE s_ucAwtoKeyShownN;          // ucCount as last drawn

static WORD AwtoKeyNow(void)
{
    WORD usNow;

    do
    {
        usNow = g_stAwtoDiag.usT2Isr;
    }
    while(usNow != g_stAwtoDiag.usT2Isr);
    return usNow;
}

static void AwtoKeyEnsure(void)                 // lazy: XDATA is not cleared at start
{
    BYTE __xdata *pucB = (BYTE __xdata *)&g_stAwtoKey;
    WORD usI;

    if((g_stAwtoKey.ucMagic0 == 'K') && (g_stAwtoKey.ucMagic1 == 'Y'))
    {
        return;
    }
    for(usI = 0; usI < sizeof(StAwtoKey); usI++)
    {
        pucB[usI] = 0;
    }
    g_stAwtoKey.ucMagic0 = 'K';
    g_stAwtoKey.ucMagic1 = 'Y';
    g_stAwtoKey.ucVersion = 1;
    g_stAwtoKey.ucMsg = AWTO_KEY_MSG_NONE;
    for(usI = 0; usI < AWTO_KEY_LOG_N; usI++)
    {
        g_stAwtoKey.pstLog[usI].ucMsg = AWTO_KEY_MSG_NONE;      // an empty slot: no mask, no message
    }
}

static void AwtoKeyLog(BYTE ucMask, BYTE ucMsg, BYTE ucFlags)
{
    BYTE ucI = g_stAwtoKey.ucCount & (AWTO_KEY_LOG_N - 1);
    WORD usNow = AwtoKeyNow();

    g_stAwtoKey.pstLog[ucI].ucSeq = g_stAwtoKey.ucCount;
    g_stAwtoKey.pstLog[ucI].ucTickHi = (BYTE)(usNow >> 8);
    g_stAwtoKey.pstLog[ucI].ucTickLo = (BYTE)usNow;
    g_stAwtoKey.pstLog[ucI].ucA0 = g_stAwtoGpio.ucIn[AWTO_IN_ADC0];
    g_stAwtoKey.pstLog[ucI].ucA1 = g_stAwtoGpio.ucIn[AWTO_IN_ADC1];
    g_stAwtoKey.pstLog[ucI].ucFlags = ucFlags;
    g_stAwtoKey.pstLog[ucI].ucMask = ucMask;
    g_stAwtoKey.pstLog[ucI].ucMsg = ucMsg;
    s_ucAwtoKeyPend = (ucMsg == AWTO_KEY_MSG_NONE) ? (ucI + 1) : 0;
    g_stAwtoKey.ucCount++;
}

static void AwtoKeyMsgNote(BYTE ucMsg)          // the key message of the press logged last
{
    g_stAwtoKey.ucMsg = ucMsg;
    if(s_ucAwtoKeyPend != 0)
    {
        g_stAwtoKey.pstLog[s_ucAwtoKeyPend - 1].ucMsg = ucMsg;
        s_ucAwtoKeyPend = 0;
    }
}

static void AwtoKeyShown(void)                  // the values the screen is about to draw
{
    s_pucAwtoKeyShown[0] = g_stAwtoKey.ucA0;
    s_pucAwtoKeyShown[1] = g_stAwtoKey.ucA1;
    s_pucAwtoKeyShown[2] = g_stAwtoKey.ucP30;
    s_pucAwtoKeyShown[3] = g_stAwtoKey.ucMask;
    s_pucAwtoKeyShown[4] = g_stAwtoKey.ucMsg;
    s_pucAwtoKeyShown[5] = g_stAwtoKey.ucFlags;
    s_ucAwtoKeyShownN = g_stAwtoKey.ucCount;
}

static void AwtoKeyShow(void)                   // every AwtoKeyPoll: redraw the console's key panel when a shown value changed
{
    if(SysPowerGetPowerStatus() == _POWER_STATUS_SAVING)
    {
        return;                                 // panel off: a redraw only holds off the wake poll (#144)
    }
    if((g_stAwtoKey.ucOpen != 0) && ((g_stAwtoDiag.ucHold & AWTO_HOLD_POPUP) == 0))
    {
        g_stAwtoKey.ucOpen = 0;                 // test cmd 0x27 (clear holds) took the screen away
        g_stAwtoKey.ucDrawn = 0;
    }
    if((g_stAwtoKey.ucOpen != 0) && (GET_OSD_EVENT_MESSAGE() >= _OSDEVENT_SHOW_NOSIGNAL_MSG) &&
       (GET_OSD_EVENT_MESSAGE() <= _OSDEVENT_ACTIVE_DO_ONE_TIME_MSG))
    {
        SET_OSD_EVENT_MESSAGE(_OSDEVENT_NONE_MSG);  // as the #67 menu (AwtoSetLoop): no SDK pop-up over the screen
    }
    if((g_stAwtoKey.ucOpen != 0) && (g_stAwtoKey.ucDrawn == 0) && ((WORD)(AwtoKeyNow() - s_usAwtoKeyDraw) >= AWTO_KEY_RETRY_MS))
    {
        s_usAwtoKeyDraw = AwtoKeyNow();         // open but never drawn (the first draw was skipped): draw again, every RETRY period
        AwtoOsdKeyLines();
        return;
    }
    if((g_stAwtoKey.ucOpen == 0) || (g_stAwtoKey.ucDrawn == 0) || ((WORD)(AwtoKeyNow() - s_usAwtoKeyDraw) < AWTO_KEY_REFRESH_MS))
    {
        return;
    }
    s_usAwtoKeyDraw = AwtoKeyNow();
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_SIGNAL);     // SDK pop-up / power-saving timers (seconds): every
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_CABLE);      // refresh period, not every pass (each cancel walks
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);  // the timer table)
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_GO_TO_POWER_SAVING);
    if((s_pucAwtoKeyShown[0] != g_stAwtoKey.ucA0) || (s_pucAwtoKeyShown[1] != g_stAwtoKey.ucA1) || (s_pucAwtoKeyShown[2] != g_stAwtoKey.ucP30) ||
       (s_pucAwtoKeyShown[3] != g_stAwtoKey.ucMask) || (s_pucAwtoKeyShown[4] != g_stAwtoKey.ucMsg) || (s_pucAwtoKeyShown[5] != g_stAwtoKey.ucFlags) ||
       (s_ucAwtoKeyShownN != g_stAwtoKey.ucCount))
    {
        AwtoKeyShown();
        AwtoOsdKeyLines();                      // a redraw costs main-loop time (6 proportional rows): only when a shown value changed
    }
}

void AwtoKeyOsdReset(void)                      // a mode reset cleared the OSD map under an open screen: use the bounded retry path
{
    AwtoKeyEnsure();
    if(g_stAwtoKey.ucOpen != 0)
    {
        g_stAwtoKey.ucDrawn = 0;
        s_usAwtoKeyDraw = AwtoKeyNow();
    }
}

void AwtoKeyConSet(BYTE ucOn)                   // the console opens / closes this panel (AwtoDiagConsole draws it)
{
    AwtoKeyEnsure();
    g_stAwtoKey.ucDrawn = 0;
    if(ucOn != 0)
    {
        g_stAwtoKey.ucOpen = 1;
        AwtoKeyShown();
        s_usAwtoKeyDraw = AwtoKeyNow();
    }
    else
    {
        g_stAwtoKey.ucOpen = 0;
    }
}

void AwtoKeyTestSet(BYTE ucOn)                  // 0 close, 1 open, 2 toggle (key combo UP+DOWN, test cmd 0x41 / 0x42): the diagnostic console
{
    AwtoDiagConsole(ucOn);
}
#endif
