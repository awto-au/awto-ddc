// #129 front keys: ONE reader (input monitor, awto_gpio.inc AwtoKeyMaskNow) -> AwtoKeyPoll (debounce, combos, repeat,
// injected keys) -> ONE dispatcher AwtoKeyRoute (context by priority). Replaces the SDK key scan / key message / OperationTable path.
// Inserted into RTD2014Key.c after awto_keytest.inc + awto_gpio.inc; AwtoKeyPoll runs where UserInterfaceKeyHandler ran.
#if(_AWTO_DIAG == _ON)
#if(_FREEZE_SUPPORT == _ON)
#error "AwtoKeyRoute does not port the SDK freeze checks of RTDOsdSystemFlowProc"
#endif
#ifndef AWTO_KEY_HOLD
#define AWTO_KEY_HOLD()                         0
#endif
// key ids = SDK key messages (menu.h MK_*); roles swapped (Dan 2026-11-08): AUTO = menu role (open / enter), MENU = exit role
#define AWTO_K_AUTO                             _MENU_KEY_MESSAGE
#define AWTO_K_UP                               _RIGHT_KEY_MESSAGE
#define AWTO_K_DOWN                             _LEFT_KEY_MESSAGE
#define AWTO_K_MENU                             _EXIT_KEY_MESSAGE
#define AWTO_K_SOURCE                           AWTO_KEY_MSG_SOURCE
#define AWTO_K_POWER                            5
#define AWTO_K_UP_DOWN                          6       // combo: diagnostic console on / off
#define AWTO_K_MENU_DOWN                        7       // combo: debug link (#79)
#define AWTO_K_NONE                             0xFF
#define AWTO_KEV_PRESS                          0
#define AWTO_KEV_REPEAT                         1
#define AWTO_KEV_HOLD                           2
#define AWTO_KEV_RELEASE                        3
#define AWTO_KEV_COMBO                          4
#define AWTO_KEV_INJ                            0x80    // flag: injected (test cmd 0x01..0x05, key_inject)
#define AWTO_KS_IDLE                            0
#define AWTO_KS_WAIT                            1       // one combo key down, PRESS held back for AWTO_KEY_COMBO_MS
#define AWTO_KS_DOWN                            2       // PRESS sent: REPEAT / HOLD timing
#define AWTO_KS_LATCH                           3       // combo or several keys: nothing until all are up
#define AWTO_KF_REPEAT                          0x01    // g_stAwtoKey.ucFlags (key panel R1 / R2 / H)
#define AWTO_KF_LATCH                           0x02
#define AWTO_KF_HOLD                            0x04

extern void MenuHotKeyDdcci(void);
extern void MenuHotKeyDpOption(void);
extern void RTDFactoryMenuOperation(void);

static __xdata BYTE s_ucKeyRaw;                 // last sample
static __xdata BYTE s_ucKeyMask;                // debounced mask (two equal samples)
static __xdata BYTE s_ucKeyPrev;                // debounced mask at the last step
static __xdata WORD s_usKeySample;
static __xdata BYTE s_ucKeyState;               // AWTO_KS_*
static __xdata BYTE s_ucKeyBit;                 // the one key down (WAIT / DOWN): mask bit and id
static __xdata BYTE s_ucKeyId;
static __xdata BYTE s_ucKeyFlags;               // AWTO_KF_*
static __xdata WORD s_usKeyT0;                  // when it went down
static __xdata WORD s_usKeyRep;                 // last REPEAT
static __xdata BYTE s_pucKeyQ[AWTO_KEY_Q_N];    // injected keys
static __xdata BYTE s_ucKeyQHead;
static __xdata BYTE s_ucKeyQN;

static BYTE AwtoKeyId(BYTE ucM)                 // single key mask -> id; AWTO_K_NONE for 0 or several
{
    switch(ucM)
    {
        case AWTO_KM_AUTO: return AWTO_K_AUTO;
        case AWTO_KM_UP: return AWTO_K_UP;
        case AWTO_KM_DOWN: return AWTO_K_DOWN;
        case AWTO_KM_MENU: return AWTO_K_MENU;
        case AWTO_KM_SOURCE: return AWTO_K_SOURCE;
        case (AWTO_KM_UP | AWTO_KM_DOWN): return AWTO_K_UP_DOWN;
        case (AWTO_KM_MENU | AWTO_KM_DOWN): return AWTO_K_MENU_DOWN;
        default: return AWTO_K_NONE;
    }
}

static void AwtoKeyOsdTimeout(void)             // RTDOsdSystemFlowProc after a key: the SDK OSD timeout restarts (ACTIVE only)
{
    if(GET_OSD_STATE() == _MENU_HOTKEY_SOURCE)  // #139: the selector has no OSD timeout (sleep rule: AwtoSrcSleepArm)
    {
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
        return;
    }
    if((GET_OSD_IN_FACTORY_MENU_STATUS() == _FALSE) && (SysModeGetModeState() == _MODE_STATUS_ACTIVE))
    {
        if(GET_OSD_TIME_OUT() <= 10)
        {
            ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
        }
        else
        {
            ScalerTimerReactiveTimerEvent(SEC(GET_OSD_TIME_OUT()), _USER_TIMER_EVENT_OSD_DISABLE);
        }
    }
}

static void AwtoKeyNoOsd(BYTE ucK)              // nothing open (SDK MenuNone; _DP_DEBUG_MSG / VGA branches are off on this board)
{
    BYTE ucMode = SysModeGetModeState();

    if(ucK == AWTO_K_UP)                        // the source selector (the SDK's second way in; SOURCE is the first)
    {
        if(ucMode == _MODE_STATUS_POWER_SAVING)
        {
            SET_OSD_POWER_SAVING_SHOW_SOURCE(_TRUE);
            if(SysPowerGetPowerStatus() == _POWER_STATUS_SAVING)
            {
                SysPowerSetTargetPowerStatus(_POWER_STATUS_NORMAL);
            }
        }
        else if((ucMode == _MODE_STATUS_NOSUPPORT) || (ucMode == _MODE_STATUS_NOSIGNAL))
        {
            SET_OSD_EVENT_MESSAGE(_OSDEVENT_SHOW_CHANGE_SOURCE_MENU_MSG);
        }
        else if(ucMode == _MODE_STATUS_ACTIVE)
        {
            AwtoSourceOpen();                   // the one open path (#132 q5)
        }
    }
    else if((ucK == AWTO_K_DOWN) && (ucMode == _MODE_STATUS_ACTIVE))
    {
        OsdDispOsdMessage(_OSD_DISP_INPUT_SIGNAL_MSG);      // input information pop-up
        ScalerTimerActiveTimerEvent(SEC(5), _USER_TIMER_EVENT_OSD_DISABLE);
    }
}

// an SDK handler that reads the key message: set for this one direct call only
#define AWTO_KEY_SDK(k, fn)                     { SET_KEYMESSAGE(k); fn(); SET_KEYMESSAGE(_NONE_KEY_MESSAGE); }

// The one dispatcher. ucEv = AWTO_KEV_* (| AWTO_KEV_INJ). Contexts in priority order; the first that applies takes the key.
static void AwtoKeyRoute(BYTE ucK, BYTE ucEv)
{
    BYTE ucMode;
    bit bRep = ((ucEv & 0x7F) == AWTO_KEV_REPEAT);

    if(((ucEv & 0x7F) == AWTO_KEV_RELEASE) || ((ucEv & 0x7F) == AWTO_KEV_HOLD))
    {
        return;                                 // no action uses these (yet)
    }
    if(SysPowerGetPowerStatus() == _POWER_STATUS_SAVING)
    {
        if((ucEv & AWTO_KEV_INJ) == 0)          // power saving: a front-key press wakes and is used up (#85)
        {
            if(bRep == 0)
            {
                SET_FORCE_POW_SAV_STATUS(_FALSE);
                SysPowerSetTargetPowerStatus(_POWER_STATUS_NORMAL);
            }
            return;
        }
    }
    if(ucK == AWTO_K_POWER)
    {
        if(AWTO_KEY_TEST_ON())
        {
            AwtoKeyTestSet(0);                  // POWER always works: the console closes first (Dan, 2026-11-12)
        }
        if(SysPowerGetPowerStatus() == _POWER_STATUS_OFF)
        {
            SET_OSD_STATE(_MENU_NONE);
            SET_OSD_IN_FACTORY_MENU_STATUS(_FALSE);
            SysPowerSetTargetPowerStatus(_POWER_STATUS_NORMAL);
        }
        else
        {
            SysPowerSetTargetPowerStatus(_POWER_STATUS_OFF);
        }
        return;
    }
    if((ucEv & 0x7F) == AWTO_KEV_COMBO)
    {
        if(ucK == AWTO_K_MENU_DOWN)
        {
            AWTO_KEY_DBG_LINK();
        }
        else
        {
            AwtoKeyTestSet(2);
        }
        return;
    }
    if(AWTO_KEY_TEST_ON())                      // main page: MENU closes it, POWER above, the rest do nothing (Dan 2026-11-12);
    {                                           // GPIO (key test) page: UP / DOWN scroll its panels, the rest swallowed
        if(g_stAwtoGpio.ucOpen == AWTO_CON_GPIO)
        {
            if((ucK == AWTO_K_UP) || (ucK == AWTO_K_DOWN))
            {
                AwtoConScroll((ucK == AWTO_K_UP) ? -1 : 1);
            }
        }
        else if(ucK == AWTO_K_MENU)
        {
            AwtoKeyTestSet(0);
        }
        return;
    }
#ifdef _AWTO_NEW_SETTINGS
    if(menu_active() != 0)                      // awto menu: UP / DOWN repeat, SOURCE does nothing
    {
        if((ucK != AWTO_K_SOURCE) && ((bRep == 0) || (ucK == AWTO_K_UP) || (ucK == AWTO_K_DOWN)))
        {
            menu_key(ucK);
        }
        return;
    }
#endif
    if(ucK == AWTO_K_SOURCE)                    // SOURCE: the input selector, with nothing open and the monitor on
    {
        if((bRep == 0) && (GET_OSD_STATE() == _MENU_NONE) && (SysPowerGetPowerStatus() != _POWER_STATUS_OFF)
#ifdef _AWTO_NEW_SETTINGS
           && (g_ucAwtoMenuOn == 0)
#endif
          )
        {
            AwtoSourceOpen();
        }
        return;
    }
    ucMode = SysModeGetModeState();
#ifdef _AWTO_NEW_SETTINGS
    if((ucK == AWTO_K_AUTO) && (bRep == 0) && (GET_OSD_STATE() == _MENU_NONE) && (GET_OSD_IN_FACTORY_MENU_STATUS() == _FALSE) &&
       ((ucMode == _MODE_STATUS_ACTIVE) || (ucMode == _MODE_STATUS_NOSIGNAL) || (ucMode == _MODE_STATUS_NOSUPPORT)))
    {
        menu_open();
        return;
    }
#endif
    // SDK OSD states: repeat only UP / DOWN with an SDK OSD other than the selector up (as the SDK's hot-key block)
    if((bRep != 0) && ((GET_OSD_STATE() == _MENU_NONE) || (GET_OSD_STATE() == _MENU_HOTKEY_SOURCE) ||
                       ((ucK != AWTO_K_UP) && (ucK != AWTO_K_DOWN)) ||
                       ((ucMode != _MODE_STATUS_ACTIVE) && (ucMode != _MODE_STATUS_NOSUPPORT) &&
                        (ucMode != _MODE_STATUS_NOSIGNAL) && (ucMode != _MODE_STATUS_POWER_SAVING))))
    {
        return;
    }
    if(GET_OSD_IN_FACTORY_MENU_STATUS() == _TRUE)
    {
        AWTO_KEY_SDK(ucK, RTDFactoryMenuOperation);
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
        return;
    }
    SET_OSD_STATE_PREVIOUS(GET_OSD_STATE());
    switch(GET_OSD_STATE())
    {
        case _MENU_NONE:
            AwtoKeyNoOsd(ucK);
            break;
        case _MENU_HOTKEY_SOURCE:
            AwtoSourceKey(ucK);
            break;
        case _MENU_HOTKEY_DDCCI:                // reachable from the test cmd OSD events only
            AWTO_KEY_SDK(ucK, MenuHotKeyDdcci);
            break;
        case _MENU_HOTKEY_DP_OPTION:
            AWTO_KEY_SDK(ucK, MenuHotKeyDpOption);
            break;
        default:                                // a Realtek menu state (built out, #120): close
            SET_OSD_STATE(_MENU_NONE);
            OsdDispDisableOsd();
            break;
    }
    AwtoKeyOsdTimeout();
}

static void AwtoKeyPress(void)                  // the single key down is a press (not the first key of a combo)
{
    s_ucKeyState = AWTO_KS_DOWN;
    AwtoKeyMsgNote(s_ucKeyId);
    AwtoKeyRoute(s_ucKeyId, AWTO_KEV_PRESS);
}

static void AwtoKeyStep(WORD usNow)             // every sample: debounced mask -> events
{
    BYTE ucM = s_ucKeyMask;
    BYTE ucK = ucM & ~AWTO_KM_POWER;
    BYTE ucId;

    if(ucM != s_ucKeyPrev)
    {
        if(ucM != 0)
        {
            AwtoKeyLog(ucM, AWTO_KEY_MSG_NONE, g_stAwtoKey.ucP30 | (AWTO_KEY_HELD_INJ() ? AWTO_KEY_F_INJ : 0));
        }
        if(((ucM ^ s_ucKeyPrev) & AWTO_KM_POWER) != 0)
        {
            AwtoKeyRoute(AWTO_K_POWER, ((ucM & AWTO_KM_POWER) != 0) ? AWTO_KEV_PRESS : AWTO_KEV_RELEASE);
        }
        s_ucKeyPrev = ucM;
    }
    if(ucK == 0)
    {
        if(s_ucKeyState == AWTO_KS_WAIT)
        {
            AwtoKeyPress();                     // a tap shorter than the combo window
        }
        if(s_ucKeyState == AWTO_KS_DOWN)
        {
            AwtoKeyRoute(s_ucKeyId, AWTO_KEV_RELEASE);
        }
        s_ucKeyState = AWTO_KS_IDLE;
        s_ucKeyFlags = 0;
        return;
    }
    if(s_ucKeyState == AWTO_KS_LATCH)
    {
        return;
    }
    if(((ucM & AWTO_KM_POWER) == 0) && (ucK == s_ucKeyBit) && (s_ucKeyState != AWTO_KS_IDLE))
    {
        if(s_ucKeyState == AWTO_KS_WAIT)
        {
            if((WORD)(usNow - s_usKeyT0) >= AWTO_KEY_COMBO_MS)
            {
                AwtoKeyPress();
            }
            return;
        }
        if(((s_ucKeyFlags & AWTO_KF_HOLD) == 0) && ((WORD)(usNow - s_usKeyT0) >= AWTO_KEY_HOLD_MS))
        {
            s_ucKeyFlags |= AWTO_KF_HOLD;
            AwtoKeyRoute(s_ucKeyId, AWTO_KEV_HOLD);
        }
        if(((s_ucKeyFlags & AWTO_KF_REPEAT) != 0) ? ((WORD)(usNow - s_usKeyRep) >= AWTO_KEY_RATE_MS) :
           ((WORD)(usNow - s_usKeyT0) >= AWTO_KEY_REPEAT_MS))
        {
            s_ucKeyFlags |= AWTO_KF_REPEAT;
            s_usKeyRep = usNow;
            AwtoKeyRoute(s_ucKeyId, AWTO_KEV_REPEAT);
        }
        return;
    }
    ucId = ((ucM & AWTO_KM_POWER) == 0) ? AwtoKeyId(ucK) : AWTO_K_NONE;      // with POWER held nothing else counts (as the SDK)
    if((s_ucKeyState == AWTO_KS_WAIT) && ((ucId == AWTO_K_NONE) || (ucId < AWTO_K_POWER)))
    {
        AwtoKeyPress();                         // no combo came of it: the waiting key acts first, as before #129
    }
    if((s_ucKeyState == AWTO_KS_DOWN) && (ucId < AWTO_K_POWER))
    {
        AwtoKeyRoute(s_ucKeyId, AWTO_KEV_RELEASE);
    }
    s_ucKeyFlags = 0;
    if(ucId < AWTO_K_POWER)                     // one key: combo keys wait for a partner, the others press now
    {
        s_ucKeyBit = ucK;
        s_ucKeyId = ucId;
        s_usKeyT0 = usNow;
        s_ucKeyState = AWTO_KS_WAIT;
        if((ucId != AWTO_K_UP) && (ucId != AWTO_K_DOWN) && (ucId != AWTO_K_MENU))
        {
            AwtoKeyPress();
        }
        return;
    }
    s_ucKeyState = AWTO_KS_LATCH;
    s_ucKeyFlags = AWTO_KF_LATCH;
    if(ucId != AWTO_K_NONE)
    {
        AwtoKeyRoute(ucId, AWTO_KEV_COMBO);
    }
}

void AwtoKeyInject(BYTE ucMsg)                  // test cmd 0x01..0x05 / key_inject: logged now, routed by the next AwtoKeyPoll
{
    AwtoKeyEnsure();
    if((ucMsg > AWTO_K_SOURCE) || (s_ucKeyQN >= AWTO_KEY_Q_N))
    {
        return;
    }
    AwtoKeyLog(0, ucMsg, g_stAwtoKey.ucP30 | AWTO_KEY_F_INJ);
    g_stAwtoKey.ucMsg = ucMsg;
    s_pucKeyQ[(s_ucKeyQHead + s_ucKeyQN) & (AWTO_KEY_Q_N - 1)] = ucMsg;
    s_ucKeyQN++;
}

void AwtoKeyPoll(void)                          // main loop, right after AwtoGpioPoll (the values it reads)
{
    WORD usNow = AwtoKeyNow();
    BYTE ucM;

    AwtoKeyEnsure();
    g_stAwtoKey.ucA0 = g_stAwtoGpio.ucIn[AWTO_IN_ADC0];
    g_stAwtoKey.ucA1 = g_stAwtoGpio.ucIn[AWTO_IN_ADC1];
    g_stAwtoKey.ucP30 = (g_stAwtoGpio.ucIn[AWTO_IN_POWER] == 0) ? AWTO_KEY_F_P30 : 0;
    while(s_ucKeyQN != 0)
    {
        ucM = s_pucKeyQ[s_ucKeyQHead];
        s_ucKeyQHead = (s_ucKeyQHead + 1) & (AWTO_KEY_Q_N - 1);
        s_ucKeyQN--;
        if(AWTO_KEY_TEST_ON() == 0)
        {
            AwtoKeyRoute(ucM, AWTO_KEV_PRESS | AWTO_KEV_INJ);       // console up: shown on its key panel, not acted on
        }
    }
    if((WORD)(usNow - s_usKeySample) >= AWTO_KEY_SAMPLE_MS)
    {
        s_usKeySample = usNow;
        ucM = AwtoKeyMaskNow() | AWTO_KEY_HOLD();
        if(ucM == s_ucKeyRaw)
        {
            s_ucKeyMask = ucM;
        }
        s_ucKeyRaw = ucM;
        AwtoKeyStep(usNow);
    }
    g_stAwtoKey.ucMask = s_ucKeyMask;
    g_stAwtoKey.ucFlags = s_ucKeyFlags | (AWTO_KEY_HELD_INJ() ? AWTO_KEY_F_INJ : 0);
    AwtoKeyShow();
}
#endif
