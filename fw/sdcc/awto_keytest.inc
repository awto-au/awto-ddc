// #39 key test + #85 key log. Inserted into RTD2014Key.c after the test-command code (keil2sdcc.py); hooks: AWTO_KEY_SCAN after the
// scan, AWTO_KEY_MSG after the message conversion (RL6449_Project.h). Layout of g_stAwtoKey: RL6449_Project.h, host: rtd_keywatch.py.
#if(_AWTO_DIAG == _ON)
typedef char AwtoKeyMaskCheck[((_POWER_KEY_MASK == AWTO_KM_POWER) && (_EXIT_KEY_MASK == AWTO_KM_MENU) && (_RIGHT_KEY_MASK == AWTO_KM_UP) &&
                              (_LEFT_KEY_MASK == AWTO_KM_DOWN) && (_MENU_KEY_MASK == AWTO_KM_AUTO) && (_KEY5_MASK == AWTO_KM_SOURCE)) ? 1 : -1];
#ifdef _AWTO_NEW_SETTINGS
#define AWTO_KEY_HELD_INJ()                     (g_ucAwtoKeyHold != 0)
extern void menu_close(void);
#else
#define AWTO_KEY_HELD_INJ()                     0
#endif

__xdata StAwtoKey g_stAwtoKey;
static __xdata BYTE s_ucAwtoKeyPend;            // log index + 1 of the press still waiting for its key message
static __xdata WORD s_usAwtoKeyDraw;            // usT2Isr at the last redraw
static __xdata BYTE s_pucAwtoKeyShown[6];       // A0 A1 P30 mask msg flags as last drawn (redraw on change only)
static __xdata BYTE s_ucAwtoKeyShownN;          // ucCount as last drawn
static __xdata BYTE s_ucAwtoKeyCombo;           // a combo was down: no key message / SOURCE until all keys are up (release passes single keys)

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

static BYTE AwtoKeyFlags(void)
{
    BYTE ucF = 0;

    if(GET_KEYREPEATENABLE() == _TRUE)
    {
        ucF |= 0x01;
    }
    if(GET_KEYREPEATSTART() == _TRUE)
    {
        ucF |= 0x02;
    }
    if(GET_KEY_HOLD() == _TRUE)
    {
        ucF |= 0x04;
    }
    if(AWTO_KEY_HELD_INJ())
    {
        ucF |= AWTO_KEY_F_INJ;
    }
    return ucF;
}

static void AwtoKeyLog(BYTE ucMask, BYTE ucMsg, BYTE ucFlags)
{
    BYTE ucI = g_stAwtoKey.ucCount & (AWTO_KEY_LOG_N - 1);
    WORD usNow = AwtoKeyNow();

    g_stAwtoKey.pstLog[ucI].ucSeq = g_stAwtoKey.ucCount;
    g_stAwtoKey.pstLog[ucI].ucTickHi = (BYTE)(usNow >> 8);
    g_stAwtoKey.pstLog[ucI].ucTickLo = (BYTE)usNow;
    g_stAwtoKey.pstLog[ucI].ucA0 = PCB_ADKEY1();
    g_stAwtoKey.pstLog[ucI].ucA1 = PCB_ADKEY2();
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

void AwtoKeyScan(void)                          // every key scan, before the power key / message processing
{
    BYTE ucP30 = (P3_0 != 0) ? AWTO_KEY_F_P30 : 0;

    AwtoKeyEnsure();
    g_stAwtoKey.ucA0 = PCB_ADKEY1();
    g_stAwtoKey.ucA1 = PCB_ADKEY2();
    g_stAwtoKey.ucP30 = ucP30;
    g_stAwtoKey.ucMask = g_ucKeyStateCurr;
    g_stAwtoKey.ucFlags = AwtoKeyFlags();
    if((g_ucKeyStateCurr & (g_ucKeyStateCurr - 1)) != 0)
    {
        s_ucAwtoKeyCombo = 1;
    }
    else if((g_ucKeyStateCurr == 0) && (g_ucKeyStatePrev == 0))
    {
        s_ucAwtoKeyCombo = 0;                   // two empty scans: RTDKeyScan returns one 0 on every change of keys
    }
    if((g_ucKeyStateCurr != 0) && (g_ucKeyStateCurr != g_ucKeyStatePrev))
    {
        AwtoKeyLog(g_ucKeyStateCurr, AWTO_KEY_MSG_NONE, ucP30 | (g_stAwtoKey.ucFlags & AWTO_KEY_F_INJ));
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
        OsdDispOsdMessage(_OSD_DISP_INPUT_SIGNAL_MSG);
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

void AwtoKeyMsg(void)                           // after RTDKeyMessageProc: note the message; swallow it while the test screen is up
{
    BYTE ucM = GET_KEYMESSAGE();

    if(ucM >= _KEY_AMOUNT)
    {
        return;
    }
    if((s_ucAwtoKeyCombo != 0) && ((g_stAwtoKey.ucFlags & AWTO_KEY_F_INJ) == 0))
    {
        SET_KEYMESSAGE(_NONE_KEY_MESSAGE);      // the last key of a combo let go: not a press
        s_ucAwtoKeyPend = 0;                    // its log entry keeps "no message" (a later message is not its)
        return;
    }
    AwtoKeyMsgNote(ucM);
    g_stAwtoKey.ucFlags = AwtoKeyFlags();
    if(g_stAwtoKey.ucOpen != 0)
    {
        SET_KEYMESSAGE(_NONE_KEY_MESSAGE);
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

static void AwtoKeySourceDo(void)               // SOURCE = next input, only with no menu up and the monitor on
{
    if((g_stAwtoKey.ucOpen != 0) || (GET_OSD_STATE() != _MENU_NONE) || (SysPowerGetPowerStatus() == _POWER_STATUS_OFF))
    {
        return;
    }
#ifdef _AWTO_NEW_SETTINGS
    if(g_ucAwtoMenuOn != 0)
    {
        return;
    }
#endif
    AwtoKeyNextInput();
}

void AwtoKeySourcePress(void)                   // RTDKeyMessageProc: SOURCE key edge
{
    AwtoKeyEnsure();
    if(s_ucAwtoKeyCombo != 0)
    {
        return;                                 // SOURCE left down after SOURCE + AUTO
    }
    AwtoKeyMsgNote(AWTO_KEY_MSG_SOURCE);
    AwtoKeySourceDo();
}

void AwtoKeyInject(BYTE ucMsg)                  // I2C test cmd 0x01..0x05 / key_inject: logged as injected, acted on as a real press
{
    AwtoKeyEnsure();
    if(ucMsg > AWTO_KEY_MSG_SOURCE)
    {
        return;
    }
    AwtoKeyLog(0, ucMsg, ((P3_0 != 0) ? AWTO_KEY_F_P30 : 0) | AWTO_KEY_F_INJ);
    g_stAwtoKey.ucMsg = ucMsg;
    if(g_stAwtoKey.ucOpen != 0)
    {
        return;                                 // test screen up: shown, not acted on
    }
    if(ucMsg == AWTO_KEY_MSG_SOURCE)
    {
        AwtoKeySourceDo();
    }
    else
    {
        SET_KEYMESSAGE(ucMsg);
    }
}

void AwtoKeyTestSet(BYTE ucOn)                  // 0 close, 1 open, 2 toggle (key combo UP+DOWN, test cmd 0x41 / 0x42)
{
    AwtoKeyEnsure();
    if(ucOn == 2)
    {
        ucOn = (g_stAwtoKey.ucOpen == 0) ? 1 : 0;
    }
    if((ucOn == g_stAwtoKey.ucOpen) && ((ucOn == 0) || (g_stAwtoKey.ucDrawn != 0)))
    {
        return;                                 // already so; an open screen that was never drawn is drawn again (below)
    }
    g_stAwtoKey.ucDrawn = 0;
    g_stAwtoDiag.ucHold &= ~AWTO_HOLD_POPUP;    // a re-open: the hold would block the disable below
    if(ucOn != 0)
    {
#ifdef _AWTO_NEW_SETTINGS
        menu_close();                           // #67 menu up: a real close (open edit reverted, settings saved); the disable only forgets it
#endif
        OsdDispDisableOsd();                    // before the hold: it blocks the disable
        g_stAwtoKey.ucOpen = 1;
        g_stAwtoDiag.ucHold |= AWTO_HOLD_POPUP;
        AwtoKeyShown();
        s_usAwtoKeyDraw = AwtoKeyNow();
        OsdDispOsdMessage(_OSD_DISP_INPUT_SIGNAL_MSG);     // draw now: the ACTIVE one-time event never comes with no signal (after SOURCE)
    }
    else
    {
        g_stAwtoKey.ucOpen = 0;
        g_stAwtoDiag.ucHold &= ~AWTO_HOLD_POPUP;
        OsdDispDisableOsd();
        if(SysModeGetModeState() == _MODE_STATUS_NOSIGNAL)     // re-arm what the open screen cancelled (as osd_tc_close)
        {
            ScalerTimerActiveTimerEvent(SEC(2), _USER_TIMER_EVENT_OSD_SHOW_NO_SIGNAL);
        }
    }
}
#endif
