// #129 front keys: ONE reader (input monitor, awto_gpio.inc AwtoKeyMaskNow) -> AwtoKeyPoll (debounce, combos, repeat,
// injected keys) -> ONE dispatcher AwtoKeyRoute (context by priority). Replaces the SDK key scan / key message / OperationTable path.
// Inserted into RTD2014Key.c after awto_keytest.inc + awto_gpio.inc; AwtoKeyPoll runs where UserInterfaceKeyHandler ran.
#if(_FREEZE_SUPPORT == _ON)
#error "AwtoKeyRoute does not port the SDK freeze checks of RTDOsdSystemFlowProc"
#endif
#ifndef AWTO_KEY_HOLD
#define AWTO_KEY_HOLD()                         0
#endif
// key ids = SDK key messages (menu.h MK_*), test cmd 0x01..0x05 - 1. Inside the menu / selector (Dan 2026-11-08, kept #132):
// AUTO = enter / take, MENU = back / cancel. Nothing open (#132): MENU opens the menu, AUTO = auto source select.
#define AWTO_K_AUTO                             _MENU_KEY_MESSAGE
#define AWTO_K_UP                               _RIGHT_KEY_MESSAGE
#define AWTO_K_DOWN                             _LEFT_KEY_MESSAGE
#define AWTO_K_MENU                             _EXIT_KEY_MESSAGE
#define AWTO_K_SOURCE                           AWTO_KEY_MSG_SOURCE
#define AWTO_K_POWER                            5
#define AWTO_K_UP_DOWN                          6       // combo: diagnostic console on / off
#define AWTO_K_NONE                             0xFF
#define AWTO_KEV_PRESS                          0
#define AWTO_KEV_REPEAT                         1
#define AWTO_KEV_RELEASE                        2
#define AWTO_KEV_COMBO                          3
#define AWTO_KEV_INJ                            0x80    // flag: injected (test cmd 0x01..0x05, key_inject)
#define AWTO_KS_IDLE                            0
#define AWTO_KS_WAIT                            1       // UP / DOWN down, PRESS held back for AWTO_KEY_COMBO_MS (UP+DOWN partner)
#define AWTO_KS_DOWN                            2       // PRESS sent: REPEAT timing
#define AWTO_KS_LATCH                           3       // combo or several keys: nothing until all are up
#define AWTO_KF_REPEAT                          0x01    // g_stAwtoKey.ucFlags (key panel R1 / R2)
#define AWTO_KF_LATCH                           0x02

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
        default: return AWTO_K_NONE;
    }
}

static void AwtoKeyOsdTimeout(void)             // RTDOsdSystemFlowProc after a key: the SDK OSD timeout restarts (ACTIVE only)
{
    if(GET_OSD_STATE() == _MENU_HOTKEY_SOURCE)  // #139 / #132: the selector's timer is its idle commit (AwtoSourceKey)
    {
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

static void AwtoKeyNoOsd(BYTE ucK)              // nothing open, a picture: UP / DOWN = backlight bar (#132; input info: menu Information page)
{
    if(((ucK == AWTO_K_UP) || (ucK == AWTO_K_DOWN)) && (SysModeGetModeState() == _MODE_STATUS_ACTIVE))
    {
        AwtoBlKey(ucK);
    }
}

// an SDK handler that reads the key message: set for this one direct call only
#define AWTO_KEY_SDK(k, fn)                     { SET_KEYMESSAGE(k); fn(); SET_KEYMESSAGE(_NONE_KEY_MESSAGE); }

// The one dispatcher. ucEv = AWTO_KEV_* (| AWTO_KEV_INJ). Contexts in priority order; the first that applies takes the key.
static void AwtoKeyRoute(BYTE ucK, BYTE ucEv)
{
    BYTE ucMode;
    bit bRep = ((ucEv & 0x7F) == AWTO_KEV_REPEAT);

    if((ucEv & 0x7F) == AWTO_KEV_RELEASE)
    {
        return;                                 // no action uses it
    }
    if(SysPowerGetPowerStatus() == _POWER_STATUS_SAVING)
    {
        if(bRep == 0)                           // power saving: a key press (front or injected) wakes and is used up (#85)
        {
            SET_FORCE_POW_SAV_STATUS(_FALSE);
            if((ucEv & 0x7F) == AWTO_KEV_COMBO)
            {
                SysMachineRequest(_POWER_STATUS_NORMAL, AWTO_SYS_BY_KEY_CONSOLE);
                g_stAwtoSync.ucOpenReq = AWTO_SYNC_OPEN_KEY;    // #132 q2: the console opens once awake (drawing in power saving resets the chip)
            }
            else
            {
                SysMachineRequest(_POWER_STATUS_NORMAL, AWTO_SYS_BY_KEY_WAKE);
            }
        }
        return;
    }
    if(ucK == AWTO_K_POWER)
    {
        if(AWTO_KEY_TEST_ON())
        {
            AwtoKeyTestSet(0);                  // POWER always works: the console closes first (Dan, 2026-11-12)
        }
        if(SysMachineOffOrGoing() == _TRUE)     // pressed again during power-down: calls it off (back on)
        {
            SET_OSD_STATE(_MENU_NONE);
            SET_OSD_IN_FACTORY_MENU_STATUS(_FALSE);
            SysMachineRequest(_POWER_STATUS_NORMAL, AWTO_SYS_BY_KEY);
        }
        else
        {
            SysMachineRequest(_POWER_STATUS_OFF, AWTO_SYS_BY_KEY);
        }
        return;
    }
    if((ucEv & 0x7F) == AWTO_KEV_COMBO)
    {
        AwtoKeyTestSet(2);                      // UP+DOWN: diagnostic console
        return;
    }
    if(AWTO_KEY_TEST_ON() && (ucK == AWTO_K_SOURCE) && (bRep == 0) && (g_ucAwtoConAuto != 0) && (g_stAwtoGpio.ucOpen != AWTO_CON_GPIO))
    {                                           // #132: a console that opened by itself (settled episode) never traps SOURCE:
        AwtoKeyTestSet(0);                      // it closes, the selector opens below (its log pane shows the same lines)
        AwtoSyncPush(AWTO_SYNC_EV_SEL, AWTO_SEL_EV_CON_CLOSE, 0xFF);
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
    if(menu_active() != 0)                      // awto menu: UP / DOWN repeat; SOURCE closes it from any page (#132, save rule of menu_close)
    {
        if((ucK == AWTO_K_SOURCE) && (bRep == 0))
        {
            menu_close();
        }
        else if((ucK != AWTO_K_SOURCE) && ((bRep == 0) || (ucK == AWTO_K_UP) || (ucK == AWTO_K_DOWN)))
        {
            menu_key(ucK);
        }
        return;
    }
#endif
    if((GET_OSD_STATE() == _MENU_HOTKEY_BACKLIGHT) && (ucK != AWTO_K_UP) && (ucK != AWTO_K_DOWN))
    {
        if(bRep != 0)
        {
            return;
        }
        AwtoBlClose();                          // #132: another key closes the bar (value stored), then acts as with nothing open
    }
    if(ucK == AWTO_K_SOURCE)                    // SOURCE: the input selector, with nothing open and the monitor on; in it: next item
    {
        if((bRep == 0) && (GET_OSD_STATE() == _MENU_HOTKEY_SOURCE))
        {
            AwtoSourceKey(ucK);
            return;
        }
        if((bRep == 0) && (GET_OSD_STATE() == _MENU_NONE) && (SysPowerGetPowerStatus() != _POWER_STATUS_OFF)
#ifdef _AWTO_NEW_SETTINGS
           && (g_ucAwtoMenuOn == 0)
#endif
          )
        {
            AwtoSourceOpen(AWTO_SEL_EV_OPEN_KEY);
        }
        return;
    }
    ucMode = SysModeGetModeState();
#ifdef _AWTO_NEW_SETTINGS
    if(((ucK == AWTO_K_MENU) || (ucK == AWTO_K_AUTO)) && (GET_OSD_STATE() == _MENU_NONE) && (GET_OSD_IN_FACTORY_MENU_STATUS() == _FALSE))
    {                                           // #132 nothing open: MENU = the awto menu, AUTO = auto source select
        if((bRep == 0) && ((ucMode == _MODE_STATUS_ACTIVE) || (ucMode == _MODE_STATUS_NOSIGNAL) || (ucMode == _MODE_STATUS_NOSUPPORT)))
        {
            if(ucK == AWTO_K_MENU)
            {
                menu_open();
            }
            else
            {
                AwtoSourceAuto(AWTO_SYS_BY_KEY_AUTO);
            }
        }
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
        case _MENU_HOTKEY_BACKLIGHT:            // only UP / DOWN get here (above: other keys closed it)
            AwtoBlKey(ucK);
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
        if((ucId != AWTO_K_UP) && (ucId != AWTO_K_DOWN))
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
    WORD usNow = ((WORD)AwtoMs());
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
        AwtoKeyRoute(ucM, AWTO_KEV_PRESS | AWTO_KEV_INJ);           // the front-key rules: power saving wakes only, console page rules
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
