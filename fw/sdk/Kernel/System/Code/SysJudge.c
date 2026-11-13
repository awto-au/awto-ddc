/********************************************************************************/
/*   The  Software  is  proprietary,  confidential,  and  valuable to Realtek   */
/*   Semiconductor  Corporation  ("Realtek").  All  rights, including but not   */
/*   limited  to  copyrights,  patents,  trademarks, trade secrets, mask work   */
/*   rights, and other similar rights and interests, are reserved to Realtek.   */
/*   Without  prior  written  consent  from  Realtek,  copying, reproduction,   */
/*   modification,  distribution,  or  otherwise  is strictly prohibited. The   */
/*   Software  shall  be  kept  strictly  in  confidence,  and  shall  not be   */
/*   disclosed to or otherwise accessed by any third party.                     */
/*   c<2003> - <2012>                                                           */
/*   The Software is provided "AS IS" without any warranty of any kind,         */
/*   express, implied, statutory or otherwise.                                  */
/********************************************************************************/

//----------------------------------------------------------------------------------------------------
// ID Code      : SysJudge.c No.0000
// Update Note  : awto-ddc#162 step 3: the system machine (power status + mode), replaces SysPowerHandler,
//                SysJudgeHandler and SysModeHandler. docs/design-162.md "Step 3".
//----------------------------------------------------------------------------------------------------

#define __SYSTEM_JUDGE__

#include "SysInclude.h"

// - One state s_ucSysState (AWTO_SYS_*). The SDK views (power status / target, mode state / reset target) follow it and are
//   written here only (g_ucAwtoSysOwn = 1 while writing; gate sysm).
// - Requests: SysMachineRequest only (logged with who and outcome). Power targets and mode resets are kept in the SDK's
//   target fields until SysMachineHandler takes them; fast path / hold requests change the state at once (no scaler work).
// - Transitions: SysMachineGo only (line: old -> new, why, ms in old; the SDK mode text when the mode changes). Scaler work =
//   SysPowerSwitch / SysModeResetState / SysModeDisplaySetting, run by the transition or by the state (SysMachineWork). No waits.
//   A transition with an action logs first (SYS_AT, ring time = the transition), then the action, then SysMachineGo (#162 s3b).
#if((_DP_MST_SUPPORT == _ON) || (_USB3_RETIMER_SUPPORT == _ON) || (_HP_SOURCE_SCAN_SUPPORT == _ON) || (_AIO_MODERN_STANDBY_SUPPORT == _ON) || (_DP_TYPE_C_PORT_CTRL_SUPPORT == _ON))
#error "awto-ddc#162 system machine: no fake power off (DP MST / Type-C), no HP source scan, no modern standby"
#endif

static __xdata BYTE s_ucSysState;               // AWTO_SYS_*
static __xdata BYTE s_ucSysBack;                // DOWN: the state to go back to when the power-down is called off
static __xdata BYTE s_ucSysPwrBy;               // who asked for the pending power target (0 = nobody: a direct write)
static __xdata BYTE s_ucSysModeBy;              // who asked for the pending mode reset
static __xdata DWORD s_ulSysEntry;              // AwtoMs() at the state's entry
volatile __xdata BYTE g_ucAwtoSysOwn;           // volatile: the set and the clear around one view write both stay
static __xdata _Bool s_bSysLogged;                        // SYS_AT pushed the line: the next SysMachineGo applies it without a line

// line now, before the action (why | AWTO_SYS_WHY_AT); the SysMachineGo after the action applies the transition
#define SYS_AT(n, w)                            SysMachineGo((n), (w) | AWTO_SYS_WHY_AT, _FALSE)

// SDK mode state per machine state (DOWN keeps the mode it came from)
static const __code BYTE tSysMode[AWTO_SYS_STATES] =
{
    _MODE_STATUS_POWER_OFF, _MODE_STATUS_POWER_OFF, _MODE_STATUS_INITIAL, _MODE_STATUS_SEARCH, _MODE_STATUS_DISPLAY_SETTING,
    _MODE_STATUS_ACTIVE, _MODE_STATUS_ACTIVE, _MODE_STATUS_ACTIVE, _MODE_STATUS_NOSUPPORT, _MODE_STATUS_NOSIGNAL,
    _MODE_STATUS_POWER_SAVING, _MODE_STATUS_POWER_SAVING, _MODE_STATUS_NONE,
};

// SDK power status per machine state (SAVING: NORMAL while fake saving; DOWN keeps the status it came from)
static const __code BYTE tSysPower[AWTO_SYS_STATES] =
{
    _POWER_STATUS_AC_ON, _POWER_STATUS_OFF, _POWER_STATUS_NORMAL, _POWER_STATUS_NORMAL, _POWER_STATUS_NORMAL,
    _POWER_STATUS_NORMAL, _POWER_STATUS_NORMAL, _POWER_STATUS_NORMAL, _POWER_STATUS_NORMAL, _POWER_STATUS_NORMAL,
    _POWER_STATUS_SAVING, _POWER_STATUS_NORMAL, _POWER_STATUS_NONE,
};

// Power LED per state (awto-ddc#95, Dan 2026-11-12): on colour while on, standby colour breathing in power saving, off when
// OFF. DOWN (AWTO_LED_TARGET): its target's colour at once (SysMachineLed).
#define AWTO_LED_TARGET                         0xFF
static const __code BYTE tSysLed[AWTO_SYS_STATES] =
{
    AWTO_LED_ON, AWTO_LED_OFF, AWTO_LED_ON, AWTO_LED_ON, AWTO_LED_ON,
    AWTO_LED_ON, AWTO_LED_ON, AWTO_LED_ON, AWTO_LED_ON, AWTO_LED_ON,
    AWTO_LED_BREATHE, AWTO_LED_ON, AWTO_LED_TARGET,
};

bit SysJudgeCheckStatus(void);
WORD SysJudgeGetActiveWaitTime(void);

//--------------------------------------------------
// Description  : The LED's one writer: the colour of the state just entered, set (and logged) only when it changes
// Input Value  : ucState --> AWTO_SYS_*
// Output Value : None
//--------------------------------------------------
static void SysMachineLed(BYTE ucState)
{
    BYTE ucLed = tSysLed[ucState];

    if(ucLed == AWTO_LED_TARGET)                // POWER DOWN: off / saving already requested, shown at the key press
    {
        ucLed = (GET_TARGET_POWER_STATUS() == _POWER_STATUS_OFF) ? AWTO_LED_OFF : AWTO_LED_BREATHE;
    }
    if(ucLed != isr_g_ucAwtoLedMode)
    {
        AwtoLedSet(ucLed, ucState);
    }
}

//--------------------------------------------------
// Description  : AC on (ScalerMcuGpioInitial, PCB_LED_AC_ON_INITIAL): the AC ON colour once the GPIO latches are set
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysMachineLedBoot(void)
{
    SysMachineLed(AWTO_SYS_AC_ON);
}

//--------------------------------------------------
// Description  : The SDK rule for a mode change: every SDK handler has seen the last one (its change flag is clear)
// Input Value  : None
// Output Value : _TRUE = a mode change may happen now
//--------------------------------------------------
static bit SysMachineFlagsClear(void)
{
    return ((GET_MODE_STATE_CHANGE_SOURCE() == _FALSE) && (GET_MODE_STATE_CHANGE_MODE() == _FALSE) &&
#if(_MHL_SUPPORT == _ON)
            (GET_MODE_STATE_CHANGE_MHL() == _FALSE) &&
#endif
            (GET_MODE_STATE_CHANGE_OSD() == _FALSE) && (GET_MODE_STATE_CHANGE_OTHERS() == _FALSE));
}

//--------------------------------------------------
// Description  : The one transition: line, state, SDK views. A mode event sets the SDK change flags (as SysJudgeStateChangeEvent)
//                even for the same mode (a reset to search from SEARCH restarts the SDK handlers' mode entry).
// Input Value  : ucNew --> AWTO_SYS_*, ucWhy --> AWTO_SYS_BY_* / AWTO_SYS_WHY_*, bModeEvent --> SDK change flags
// Output Value : None
//--------------------------------------------------
static void SysMachineGo(BYTE ucNew, BYTE ucWhy, bit bModeEvent)
{
    if(s_bSysLogged == _FALSE)                  // line + entry time at the transition (SYS_AT: before the action)
    {
        g_ucAwtoSysOwn = 1;                     // console draw held (AWTO_CON_LIVE): line time = entry time
        AwtoSysLog((BYTE)((s_ucSysState << 4) | ucNew), (ucWhy & AWTO_SYS_WHY_CODE) |
                   (((tSysMode[ucNew] != _MODE_STATUS_NONE) && (tSysMode[ucNew] != GET_MODE_STATE())) ? AWTO_SYS_WHY_MODE : 0),
                   AwtoMs() - s_ulSysEntry);
        if(ucNew != s_ucSysState)
        {
            s_ulSysEntry = AwtoMs();
        }
        g_ucAwtoSysOwn = 0;
    }
    s_bSysLogged = ((ucWhy & AWTO_SYS_WHY_AT) != 0);
    if(s_bSysLogged == _TRUE)
    {
        return;
    }
    s_ucSysState = ucNew;
    g_ucAwtoSysOwn = 1;
    ucWhy = ((ucNew == AWTO_SYS_SAVING) && (GET_POWER_SWITCH_TO_FAKE_SAVING() == _TRUE)) ? _POWER_STATUS_NORMAL : tSysPower[ucNew];
    if((ucWhy != _POWER_STATUS_NONE) && (ucWhy != GET_POWER_STATUS()))      // ucWhy reused: the power status of the new state
    {
        SET_POWER_STATUS(ucWhy);                // its log lines: SysMachinePower (AwtoSyncPoll opens the console: no call cycle here)
    }
    if((tSysMode[ucNew] != _MODE_STATUS_NONE) && ((bModeEvent == _TRUE) || (tSysMode[ucNew] != GET_MODE_STATE())))
    {
        if(tSysMode[ucNew] != GET_MODE_STATE())
        {
            SET_MODE_STATE(tSysMode[ucNew]);
            AwtoSwMode(tSysMode[ucNew]);        // mode line (sync.tsv 01) at the transition
        }
        SET_MODE_STATE_CHANGE_SOURCE();
        SET_MODE_STATE_CHANGE_MODE();
        SET_MODE_STATE_CHANGE_MHL();
        SET_MODE_STATE_CHANGE_OSD();
        SET_MODE_STATE_CHANGE_OTHERS();
    }
    g_ucAwtoSysOwn = 0;
    SysMachineLed(ucNew);
}

//--------------------------------------------------
// Description  : Boot (SysMainSystemInitial): AC_ON, power target from NVRAM
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysMachineInit(void)
{
    g_ucAwtoSysOwn = 1;
    SET_POWER_STATUS(_POWER_STATUS_AC_ON);
    SET_MODE_STATE(_MODE_STATUS_POWER_OFF);
    SET_TARGET_POWER_STATUS(_POWER_STATUS_NONE);
    SET_MODE_RESET_TARGET(_MODE_ACTION_NO_RESET_MODE);
    g_ucAwtoSysOwn = 0;
    AwtoSwMode(_MODE_STATUS_POWER_OFF);         // switch log; the ring line is the RESET -> AC ON transition (ms since reset)
    AwtoSysLog((AWTO_SYS_STATES << 4) | AWTO_SYS_AC_ON, AWTO_SYS_WHY_BOOT | AWTO_SYS_WHY_MODE,
               (WORD)((WORD)AwtoMs() - (((WORD)g_stAwtoSync.ucT0Hi << 8) | g_stAwtoSync.ucT0Lo)));
    s_ucSysState = AWTO_SYS_AC_ON;
    s_ulSysEntry = AwtoMs();                    // AC ON counts from its line
    SysMachineRequest((UserCommonNVRamGetSystemData(_MONITOR_POWER_STATUS) == _ON) ? _POWER_STATUS_NORMAL : _POWER_STATUS_OFF, AWTO_SYS_BY_NVRAM);
}

//--------------------------------------------------
// Description  : The one request entry (main-loop context): logs who asked and the outcome
// Input Value  : ucReq --> EnumPowerStatus / AWTO_SYS_REQ_MODE | EnumModeAction / AWTO_SYS_REQ_FAST.. ; ucBy --> AWTO_SYS_BY_*
// Output Value : None
//--------------------------------------------------
// POWER toggle input: off, or a power-off in progress (T4..T6 still running): the next press means "on"
bit SysMachineOffOrGoing(void)
{
    return ((s_ucSysState == AWTO_SYS_OFF) || ((s_ucSysState == AWTO_SYS_DOWN) && (GET_TARGET_POWER_STATUS() == _POWER_STATUS_OFF)));
}

void SysMachineRequest(BYTE ucReq, BYTE ucBy)
{
    BYTE ucOut = AWTO_SYS_OK;                   // the one local: XDATA is full (#162 step 3)

    if(ucReq >= AWTO_SYS_REQ_FAST)              // fast path / hold: state only, the fast path owns the scaler work
    {
        ucOut = ((ucReq == AWTO_SYS_REQ_FAST) && ((s_ucSysState == AWTO_SYS_ACTIVE) || (s_ucSysState == AWTO_SYS_HOLD))) ? AWTO_SYS_FAST :
                ((ucReq == AWTO_SYS_REQ_HOLD) && (s_ucSysState == AWTO_SYS_FAST)) ? AWTO_SYS_HOLD :
                ((ucReq == AWTO_SYS_REQ_ACTIVE) && (s_ucSysState == AWTO_SYS_FAST)) ? AWTO_SYS_ACTIVE : AWTO_SYS_STATES;
        AwtoSyncPush(AWTO_SW_EV_SYS_REQ, ucReq, ((WORD)ucBy << 8) | ((ucOut == AWTO_SYS_STATES) ? AWTO_SYS_REFUSED : AWTO_SYS_OK));
        if(ucOut != AWTO_SYS_STATES)
        {
            SysMachineGo(ucOut, ucBy, _FALSE);  // ucOut = the new state here
        }
        return;
    }
    if(ucReq < AWTO_SYS_REQ_MODE)               // power target
    {
        if(((ucReq == _POWER_STATUS_OFF) && (s_ucSysState == AWTO_SYS_OFF)) || ((ucReq == _POWER_STATUS_SAVING) && (s_ucSysState == AWTO_SYS_SAVING)) ||
           ((ucReq == _POWER_STATUS_NORMAL) && (s_ucSysState >= AWTO_SYS_INITIAL) && (s_ucSysState <= AWTO_SYS_WAKE) && (s_ucSysState != AWTO_SYS_SAVING)) ||
           (ucReq == GET_TARGET_POWER_STATUS()))
        {
            ucOut = AWTO_SYS_ALREADY;
        }
        else if((ucReq == _POWER_STATUS_SAVING) && ((s_ucSysState == AWTO_SYS_OFF) || (s_ucSysState == AWTO_SYS_AC_ON)))
        {
            ucOut = AWTO_SYS_REFUSED;           // SDK: no OFF -> SAVING switch
        }
        else
        {
            ucOut = (GET_TARGET_POWER_STATUS() != _POWER_STATUS_NONE) ? AWTO_SYS_REPLACES : AWTO_SYS_OK;
            g_ucAwtoSysOwn = 1;
            SET_TARGET_POWER_STATUS(ucReq);
            g_ucAwtoSysOwn = 0;
            s_ucSysPwrBy = ucBy;
        }
    }
    else                                        // mode reset
    {
        ucReq -= AWTO_SYS_REQ_MODE;
        if((s_ucSysState <= AWTO_SYS_INITIAL) || (ucReq >= _MODE_ACTION_RESET_TO_POWER_SAVING) ||
           (((ucReq == _MODE_ACTION_RESET_TO_DISPLAY_SETTING) || (ucReq == _MODE_ACTION_RESET_TO_DISPLAY_SETTING_WITHOUT_FORCETOBG)) &&
            (s_ucSysState != AWTO_SYS_ACTIVE) && (s_ucSysState != AWTO_SYS_FAST) && (s_ucSysState != AWTO_SYS_HOLD)))
        {
            ucOut = AWTO_SYS_REFUSED;           // SDK: no reset while off / in INITIAL; display setting again only from ACTIVE
        }
        else if(ucReq == GET_MODE_RESET_TARGET())
        {
            ucOut = AWTO_SYS_ALREADY;
        }
        else
        {
            ucOut = (GET_MODE_RESET_TARGET() != _MODE_ACTION_NO_RESET_MODE) ? AWTO_SYS_REPLACES :
                    ((s_ucSysState == AWTO_SYS_SAVING) || (s_ucSysState == AWTO_SYS_DOWN) ||
                     (((s_ucSysState == AWTO_SYS_FAST) || (s_ucSysState == AWTO_SYS_HOLD)) && (ucReq != _MODE_ACTION_RESET_TO_SEARCH))) ?
                    AWTO_SYS_KEPT : AWTO_SYS_OK;        // as SysMachineReset: a search reset ends FAST / HOLD at once
            g_ucAwtoSysOwn = 1;
            SET_MODE_RESET_TARGET(ucReq);
            g_ucAwtoSysOwn = 0;
            s_ucSysModeBy = ucBy;
        }
        ucReq += AWTO_SYS_REQ_MODE;
    }
    AwtoSyncPush(AWTO_SW_EV_SYS_REQ, ucReq, ((WORD)ucBy << 8) | ucOut);
}

//--------------------------------------------------
// Description  : Mode reset action + transition (SysJudgeModeResetProc); a mode change waits while the SDK handlers have
//                not seen the last one (the reset stays pending)
// Input Value  : None
// Output Value : None
//--------------------------------------------------
static void SysMachineReset(void)
{
    BYTE ucR = GET_MODE_RESET_TARGET();

    if((ucR != _MODE_ACTION_NO_RESET_MODE) && (s_ucSysState <= AWTO_SYS_OFF))
    {
        g_ucAwtoSysOwn = 1;                     // kept through a power-down that ended in OFF: dropped (SDK: no reset while off)
        SET_MODE_RESET_TARGET(_MODE_ACTION_NO_RESET_MODE);
        g_ucAwtoSysOwn = 0;
        return;
    }
    if((ucR == _MODE_ACTION_NO_RESET_MODE) || (s_ucSysState == AWTO_SYS_SAVING) || (s_ucSysState == AWTO_SYS_DOWN) || (SysMachineFlagsClear() == _FALSE) ||
       (((s_ucSysState == AWTO_SYS_FAST) || (s_ucSysState == AWTO_SYS_HOLD)) && (ucR != _MODE_ACTION_RESET_TO_SEARCH)))
    {
        return;                                 // kept: power saving / down (taken at the wake), fast path / hold (display setting at ACTIVE)
    }
    g_ucAwtoSysOwn = 1;
    SET_MODE_RESET_TARGET(_MODE_ACTION_NO_RESET_MODE);
    g_ucAwtoSysOwn = 0;
    switch(ucR)
    {
        case _MODE_ACTION_RESET_TO_SEARCH:
            SYS_AT(AWTO_SYS_SEARCH, s_ucSysModeBy);
            AwtoSwEvent(AWTO_SW_EV_PROBE, 1);
            SysModeResetState(_MODE_ACTION_RESET_TO_SEARCH);
            AwtoSwEvent(AWTO_SW_EV_PROBE, 2);
            SysMachineGo(AWTO_SYS_SEARCH, s_ucSysModeBy, _TRUE);
            break;

        case _MODE_ACTION_RESET_TO_DISPLAY_SETTING_WITHOUT_FORCETOBG:
        case _MODE_ACTION_RESET_TO_DISPLAY_SETTING:
            if(s_ucSysState == AWTO_SYS_ACTIVE)
            {
                SYS_AT(AWTO_SYS_DISPLAY, s_ucSysModeBy);
                SysModeResetState(ucR);
                SysMachineGo(AWTO_SYS_DISPLAY, s_ucSysModeBy, _TRUE);
            }
            break;

        case _MODE_ACTION_RESET_TO_NOSIGNAL:
            ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_NOSIGNAL_STATE);
            SysMachineGo(AWTO_SYS_NOSIGNAL, s_ucSysModeBy, _TRUE);
            CLR_SOURCE_SWITCH_FINISH();
            break;

        case _MODE_ACTION_RESET_TO_NOSUPPORT:
            SYS_AT(AWTO_SYS_NOSUPPORT, s_ucSysModeBy);
            SysModeResetState(_MODE_ACTION_RESET_TO_NOSUPPORT);
            ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_NOSUPPORT_STATE);
            SysMachineGo(AWTO_SYS_NOSUPPORT, s_ucSysModeBy, _TRUE);
            break;

        default:
            break;
    }
}

//--------------------------------------------------
// Description  : Power transitions (SysPowerHandler): power target -> SysPowerSwitch action -> state. NORMAL / AC_ON -> OFF / SAVING
//                goes through DOWN: the panel machine takes the panel down first (T4, T5 are its timer steps), no wait here.
// Input Value  : None
// Output Value : None
//--------------------------------------------------
static void SysMachinePowerStep(void)
{
    if(GET_TARGET_POWER_STATUS() == _POWER_STATUS_NONE)
    {
        return;
    }
    if(s_ucSysPwrBy == 0)
    {
        s_ucSysPwrBy = AWTO_SYS_BY_DIRECT;
        AwtoSyncPush(AWTO_SW_EV_SYS_REQ, GET_TARGET_POWER_STATUS(), ((WORD)AWTO_SYS_BY_DIRECT << 8) | AWTO_SYS_OK);
    }
    if(s_ucSysState == AWTO_SYS_DOWN)
    {
        if(GET_TARGET_POWER_STATUS() == _POWER_STATUS_NORMAL)         // called off: the panel level from before, the state from before
        {
            SYS_AT(s_ucSysBack, AWTO_SYS_WHY_CALLED_OFF);
            UserCommonInterfacePanelPowerDown(_FALSE, _TRUE);
            SysMachineGo(s_ucSysBack, AWTO_SYS_WHY_CALLED_OFF, _FALSE);
        }
        else if((UserCommonInterfacePanelPowerDown(_TRUE, _TRUE) == _FALSE) || (SysMachineFlagsClear() == _FALSE))
        {
            return;                             // panel still going down (target kept), or the SDK handlers have not seen the last mode
        }
        else if(GET_TARGET_POWER_STATUS() == _POWER_STATUS_OFF)
        {
            SYS_AT(AWTO_SYS_OFF, AWTO_SYS_WHY_PANEL_DOWN);
            CLR_POWER_SWITCH_TO_FAKE_SAVING();
            SysPowerSwitch((s_ucSysBack == AWTO_SYS_AC_ON) ? _POWER_ACTION_AC_ON_TO_OFF : _POWER_ACTION_NORMAL_TO_OFF);
            UserCommonInterfacePanelPowerDown(_FALSE, _FALSE);
            SysMachineGo(AWTO_SYS_OFF, AWTO_SYS_WHY_PANEL_DOWN, _TRUE);
        }
        else if(s_ucSysBack == AWTO_SYS_AC_ON)
        {
            SYS_AT(AWTO_SYS_AC_ON, AWTO_SYS_WHY_CALLED_OFF);
            UserCommonInterfacePanelPowerDown(_FALSE, _TRUE);     // SDK: no AC_ON -> SAVING switch
            SysMachineGo(AWTO_SYS_AC_ON, AWTO_SYS_WHY_CALLED_OFF, _FALSE);
        }
        else
        {
            SYS_AT(AWTO_SYS_SAVING, AWTO_SYS_WHY_PANEL_DOWN);
            if(UserCommonInterfaceCheckFakeSaving() == _TRUE)
            {
                SET_POWER_SWITCH_TO_FAKE_SAVING();
                SysPowerSwitch(_POWER_ACTION_NORMAL_TO_FAKE_PS);
            }
            else
            {
                SysPowerSwitch(_POWER_ACTION_NORMAL_TO_PS);
            }
            UserCommonInterfacePanelPowerDown(_FALSE, _FALSE);
            SysMachineGo(AWTO_SYS_SAVING, AWTO_SYS_WHY_PANEL_DOWN, _TRUE);
        }
    }
    else if((s_ucSysState == AWTO_SYS_AC_ON) || (s_ucSysState == AWTO_SYS_OFF))
    {
        if(GET_TARGET_POWER_STATUS() == _POWER_STATUS_NORMAL)
        {
            if(s_ucSysState == AWTO_SYS_OFF)
            {
                AwtoSyncBegin(AWTO_SYNC_K_POWER_KEY, SysSourceGetInputPort());     // the episode starts with its transition line
            }
            SYS_AT(AWTO_SYS_INITIAL, s_ucSysPwrBy);
            SysPowerSwitch((s_ucSysState == AWTO_SYS_AC_ON) ? _POWER_ACTION_AC_ON_TO_NORMAL : _POWER_ACTION_OFF_TO_NORMAL);
            SysMachineGo(AWTO_SYS_INITIAL, s_ucSysPwrBy, _TRUE);
        }
        else if((GET_TARGET_POWER_STATUS() == _POWER_STATUS_OFF) && (s_ucSysState == AWTO_SYS_AC_ON))
        {
            s_ucSysBack = s_ucSysState;                  // the boot panel request may have VDD on already
            SysMachineGo(AWTO_SYS_DOWN, s_ucSysPwrBy, _FALSE);
            return;
        }
    }
    else if((s_ucSysState == AWTO_SYS_SAVING) && (GET_POWER_SWITCH_TO_FAKE_SAVING() == _FALSE))
    {
        if(GET_TARGET_POWER_STATUS() == _POWER_STATUS_NORMAL)
        {
            SYS_AT(AWTO_SYS_WAKE, s_ucSysPwrBy);
            SysPowerSwitch(_POWER_ACTION_PS_TO_NORMAL);
            SysMachineGo(AWTO_SYS_WAKE, s_ucSysPwrBy, _FALSE);
        }
        else if(GET_TARGET_POWER_STATUS() == _POWER_STATUS_OFF)
        {
            SYS_AT(AWTO_SYS_OFF, s_ucSysPwrBy);
            SysPowerSwitch(_POWER_ACTION_PS_TO_OFF);
            SysMachineGo(AWTO_SYS_OFF, s_ucSysPwrBy, _TRUE);
        }
    }
    else if((s_ucSysState == AWTO_SYS_SAVING) && (GET_TARGET_POWER_STATUS() == _POWER_STATUS_NORMAL))         // fake saving: the scaler never went down
    {
        SYS_AT(AWTO_SYS_WAKE, s_ucSysPwrBy);
        CLR_POWER_SWITCH_TO_FAKE_SAVING();
        SysPowerSwitch(_POWER_ACTION_FAKE_PS_TO_NORMAL);
        SysMachineGo(AWTO_SYS_WAKE, s_ucSysPwrBy, _FALSE);
    }
    else if((GET_TARGET_POWER_STATUS() == _POWER_STATUS_OFF) || ((GET_TARGET_POWER_STATUS() == _POWER_STATUS_SAVING) && (s_ucSysState != AWTO_SYS_SAVING)))
    {
        s_ucSysBack = s_ucSysState;                      // NORMAL (or fake saving) -> OFF / SAVING: panel down first
        SysMachineGo(AWTO_SYS_DOWN, s_ucSysPwrBy, _FALSE);
        return;
    }
    g_ucAwtoSysOwn = 1;
    SET_TARGET_POWER_STATUS(_POWER_STATUS_NONE);
    g_ucAwtoSysOwn = 0;
    s_ucSysPwrBy = 0;
}

static void SysMachinePower(void)
{
    SysMachinePowerStep();
    if(GET_POWER_STATUS() != g_ucAwtoSyncPwr)
    {
        AwtoSyncPoll();                         // power on / off / saving / wake lines (sync.tsv C0, C9), wake console
    }
}

//--------------------------------------------------
// Description  : State checks of the SDK judge: SysJudgeCheckStatus with the reason (AWTO_SYS_WHY_UNSTABLE.., 0 = all ok)
// Input Value  : None
// Output Value : reason
//--------------------------------------------------
static BYTE SysMachineCheck(void)
{
    if(GET_SOURCE_JUDGE(g_ucSearchIndex) == _TRUE)
    {
        if(SysSourceStableCheck() == _FALSE)
        {
            AwtoSwEvent(AWTO_SW_EV_PROBE, 20);
            AWTO_TMDS_STUCK();
            DebugMessageSystem("Source Unstable!!", GET_SOURCE_TYPE(g_ucSearchIndex));
            return AWTO_SYS_WHY_UNSTABLE;
        }
    }

    if(SysModeGetTimingConfirm() == _TRUE)
    {
        if(ScalerMeasureTimingChange(GET_SOURCE_TYPE(g_ucSearchIndex), SysSourceGetInputPort()) == _TRUE)
        {
            AwtoSwEvent(AWTO_SW_EV_PROBE, 21);
            DebugMessageSystem("Measured Input HV Changed", GET_SOURCE_TYPE(g_ucSearchIndex));
            return AWTO_SYS_WHY_HV;
        }

        if((GET_INPUT_TIMING_DOUBLE_CHECK() == _TRUE) &&
           ((SysModeGetDisplaySettingReady() == _TRUE) || (GET_MODE_STATE() == _MODE_STATUS_NOSUPPORT)))
        {
            if(GET_SOURCE_TYPE(g_ucSearchIndex) != _SOURCE_VGA)
            {
                if(ScalerMeasureInterlaceCheck(GET_SOURCE_TYPE(g_ucSearchIndex), SysSourceGetInputPort()) != GET_INPUT_TIMING_INTERLACE_FLG())
                {
                    AwtoSwEvent(AWTO_SW_EV_PROBE, 22);
                    DebugMessageSystem("Input Timing Double Check : Interlace Flag Change", GET_SOURCE_TYPE(g_ucSearchIndex));
                    return AWTO_SYS_WHY_INTERLACE;
                }
            }

            CLR_INPUT_TIMING_DOUBLE_CHECK();
        }
    }

    if(SysModeGetDisplaySettingReady() == _TRUE)
    {
        if((ScalerMDomainMemoryCheck() == _FALSE) || (ScalerMDomainDisplayTimingGenCheck() == _FALSE))
        {
            AwtoSwEvent(AWTO_SW_EV_PROBE, 23);
            DebugMessageSystem("Memory Check Failed", GET_SOURCE_TYPE(g_ucSearchIndex));
            return AWTO_SYS_WHY_MEMORY;
        }

#if(_ULTRA_HDR_SUPPORT == _ON)
        ScalerSyncGetColorInfoFrame(SysSourceGetInputPort(), _DP_GET_RSV0_INFO_ACTIVE);
#endif
    }

#if((_PANEL_STYLE == _PANEL_DPTX) && (_PANEL_DPTX_HPD_DETECT == _ON))
    if(GET_MODE_STATE() == _MODE_STATUS_ACTIVE)
    {
        if(ScalerDisplayDPTxStableDetect() == _FALSE)
        {
            DebugMessageSystem("eDP unstable", 0x00);
            return AWTO_SYS_WHY_EDP;
        }
    }
#endif

    return 0;
}

//--------------------------------------------------
// Description  : The judge's checks for the fast path (AwtoSwFastPoll)
// Input Value  : None
// Output Value : _FALSE => Status Changed
//--------------------------------------------------
bit SysJudgeCheckStatus(void)
{
    return (SysMachineCheck() == 0);
}

//--------------------------------------------------
// Description  : Mode transitions of the SDK judge (signal found / lost, display ready); then the pending mode reset; then
//                the state check (signal lost: L1 hold or a reset to search)
// Input Value  : None
// Output Value : None
//--------------------------------------------------
static void SysMachineJudge(void)
{
    BYTE ucWhy;

    switch(s_ucSysState)
    {
        case AWTO_SYS_INITIAL:
            if(SysMachineFlagsClear() == _TRUE)
            {
                SysMachineGo(AWTO_SYS_SEARCH, AWTO_SYS_WHY_INITIAL, _TRUE);
            }
            return;                             // SDK: INITIAL takes the whole judge pass

        case AWTO_SYS_SEARCH:
            if(UserInterfaceGetLogoStatus() == _TRUE)
            {
                return;
            }
            if(GET_SOURCE_JUDGE(g_ucSearchIndex) == _TRUE)
            {
                // If Timing can't be confirmed for 1 sec, switch to No Signal State
                ScalerTimerActiveTimerEvent(SEC(1), _SYSTEM_TIMER_EVENT_JUDGE_NOSIGNAL_STATE);

                if(SysModeGetTimingConfirm() == _TRUE)
                {
                    ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_NOSIGNAL_STATE);

                    if(UserCommonInterfaceCheckNoSupport() == _FALSE)
                    {
                        ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_NOSUPPORT_STATE);
                        if(SysMachineFlagsClear() == _TRUE)
                        {
                            SysMachineGo(AWTO_SYS_DISPLAY, AWTO_SYS_WHY_TIMING, _TRUE);
                        }
                    }
                    else
                    {
                        ScalerTimerActiveTimerEvent(SEC(0.5), _SYSTEM_TIMER_EVENT_JUDGE_NOSUPPORT_STATE);
                    }
                }
            }
            else if((GET_SOURCE_SWITCH_FINISH() == _TRUE) && (SysMachineFlagsClear() == _TRUE))
            {
                SysMachineGo(AWTO_SYS_NOSIGNAL, AWTO_SYS_WHY_NO_SOURCE, _TRUE);
                CLR_SOURCE_SWITCH_FINISH();
            }
            break;

        case AWTO_SYS_DISPLAY:
            if((SysModeGetActiveReady() == _TRUE) && (UserCommonInterfaceReadyForActive() == _TRUE))
            {
                if(SysMachineFlagsClear() == _TRUE)
                {
                    SysMachineGo(AWTO_SYS_ACTIVE, AWTO_SYS_WHY_READY, _TRUE);
                    CLR_MODE_ACTIVE_READY();
                }
            }
            else if(SysModeGetDisplaySettingReady() == _TRUE)
            {
                if(UserInterfaceGetDclkNoSupportStatus() == _TRUE)
                {
                    ScalerTimerActiveTimerEvent(SEC(0.5), _SYSTEM_TIMER_EVENT_JUDGE_NOSUPPORT_STATE);
                }
                else
                {
                    ScalerTimerActiveTimerEvent(SysJudgeGetActiveWaitTime(), _SYSTEM_TIMER_EVENT_JUDGE_ACTIVE_STATE);
                }
            }
            else
            {
                // If Display Setting can't be Ready for 2 sec, switch to No Support State
                ScalerTimerActiveTimerEvent(SEC(2), _SYSTEM_TIMER_EVENT_JUDGE_NOSUPPORT_STATE);
            }
            break;

        case AWTO_SYS_NOSIGNAL:
        case AWTO_SYS_WAKE:
            if(SysModeGetTimingConfirm() == _TRUE)
            {
                if(GET_MODE_RESET_TARGET() == _MODE_ACTION_RESET_TO_SEARCH)
                {                                       // #132: the no-signal search found a timing on the current port: the
                    g_ucAwtoSysOwn = 1;                 // pending search reset would only search it again (a second blank)
                    SET_MODE_RESET_TARGET(_MODE_ACTION_NO_RESET_MODE);
                    g_ucAwtoSysOwn = 0;
                    AwtoSyncPush(AWTO_SW_EV_SYS_REQ, AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_SEARCH, ((WORD)s_ucSysModeBy << 8) | AWTO_SYS_DROPPED);
                }
                UserCommonInterfaceOsdResetProc();

                if(UserCommonInterfaceCheckNoSupport() == _FALSE)
                {
                    ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_NOSUPPORT_STATE);
                    if(SysMachineFlagsClear() == _TRUE)
                    {
                        SysMachineGo(AWTO_SYS_DISPLAY, AWTO_SYS_WHY_TIMING, _TRUE);
                    }
                }
                else
                {
                    ScalerTimerActiveTimerEvent(SEC(0.5), _SYSTEM_TIMER_EVENT_JUDGE_NOSUPPORT_STATE);
                }
            }
            break;

        default:
            break;
    }

    SysMachineReset();

    if((s_ucSysState <= AWTO_SYS_OFF) || (s_ucSysState == AWTO_SYS_FAST) || (s_ucSysState == AWTO_SYS_HOLD) || (s_ucSysState == AWTO_SYS_DOWN) ||
       ((s_ucSysState == AWTO_SYS_ACTIVE) && (AWTO_SLOW_DUE_JUDGE() == _FALSE)))
    {
        return;                                 // fast path / hold: AwtoSwFastPoll / AwtoWakePoll run these checks
    }
    ucWhy = SysMachineCheck();
    if(ucWhy == 0)
    {
        return;
    }
#if(_AWTO_WAKE_HOLD == _ON)
    if((s_ucSysState == AWTO_SYS_ACTIVE) && (AwtoWakeHold() == _TRUE))
    {
        SysMachineGo(AWTO_SYS_HOLD, AWTO_SYS_WHY_HOLD, _FALSE);    // L1: mode stays ACTIVE, the set-up is kept
        return;
    }
#endif
    // Force Reset (SDK): the change flags are cleared, the reset target dropped
    CLR_MODE_STATE_CHANGE_SOURCE();
    CLR_MODE_STATE_CHANGE_MODE();
    CLR_MODE_STATE_CHANGE_MHL();
    CLR_MODE_STATE_CHANGE_OSD();
    CLR_MODE_STATE_CHANGE_OTHERS();
    g_ucAwtoSysOwn = 1;
    SET_MODE_RESET_TARGET(_MODE_ACTION_NO_RESET_MODE);
    g_ucAwtoSysOwn = 0;

    SYS_AT(((s_ucSysState == AWTO_SYS_NOSIGNAL) || (s_ucSysState == AWTO_SYS_WAKE) || (s_ucSysState == AWTO_SYS_SAVING)) ? s_ucSysState : AWTO_SYS_SEARCH, ucWhy);
    SysModeResetState(_MODE_ACTION_RESET_TO_SEARCH);

#if(_COLORIMETRY_SEAMLESS_CHANGE_SUPPORT == _ON)
    if(UserCommonNVRamGetSystemData(_COLORIMETRY_SEAMLESS_CHANGE) == _TRUE)
    {
        CLR_DIGITAL_COLOR_INFO_CHANGE_RESET();
    }
    else
    {
        SET_DIGITAL_COLOR_INFO_CHANGE_RESET();
    }
#endif

    // SDK: no signal / power saving keep their state (the search runs under them)
    SysMachineGo(((s_ucSysState == AWTO_SYS_NOSIGNAL) || (s_ucSysState == AWTO_SYS_WAKE) || (s_ucSysState == AWTO_SYS_SAVING)) ? s_ucSysState : AWTO_SYS_SEARCH, ucWhy,
                 ((s_ucSysState != AWTO_SYS_NOSIGNAL) && (s_ucSysState != AWTO_SYS_WAKE) && (s_ucSysState != AWTO_SYS_SAVING)));
}

//--------------------------------------------------
// Description  : System machine step, once per main-loop pass (slot of SysPowerHandler + SysJudgeHandler): power first,
//                then the mode transitions
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysMachineHandler(void)
{
    CLR_MODE_STATE_CHANGE_OTHERS();
    AWTO_TMDS_HPD_TICK();
    g_ucAwtoLedPins = MCU_FFE3_PORT3_PIN_REG;   // LED pin levels for the debug slave (it reads 0 at FFE3 itself, gpio-ir.md)
    SysMachinePower();

#if(_URGENT_EVENT_CHECK_MODE == _ON)
    if((SysPowerGetPowerStatus() == _POWER_STATUS_NORMAL) && (ScalerSyncGetUrgentEventFlg() == _TRUE))
    {
        ScalerSyncClrUrgentEventFlg();

        if(ScalerTimerSearchActiveTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_NOSIGNAL_STATE) == _TRUE)
        {
            ScalerTimerReactiveTimerEvent(SEC(1), _SYSTEM_TIMER_EVENT_JUDGE_NOSIGNAL_STATE);
        }

        if(ScalerTimerSearchActiveTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_NOSUPPORT_STATE) == _TRUE)
        {
            ScalerTimerReactiveTimerEvent((s_ucSysState == AWTO_SYS_DISPLAY) ? SEC(2) : SEC(0.5), _SYSTEM_TIMER_EVENT_JUDGE_NOSUPPORT_STATE);
        }
    }
#endif

    SysMachineJudge();

#if(_SYSTEM_LOW_POWER_IDLE_SUPPORT == _ON)
    // Flash go into idle mode to reduce overall system power consumption under power saving and power off status.
    if(((GET_POWER_STATUS() == _POWER_STATUS_SAVING) || (GET_POWER_STATUS() == _POWER_STATUS_OFF)) && (UserCommonInterfaceGetRunDdcciCommand() == _FALSE))
    {
        SysPowerIdleProc();
    }
#endif
}

//--------------------------------------------------
// Description  : The state's scaler work, once per pass (slot of SysModeHandler): measure while searching, display setting,
//                first-ACTIVE work. Requests it makes are taken by the next SysMachineHandler.
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void SysMachineWork(void)
{
#if(_URGENT_EVENT_CHECK_MODE == _ON)
    if(ScalerSyncCheckUrgentEvent() == _TRUE)
    {
        return;
    }
#endif

    switch(s_ucSysState)
    {
        case AWTO_SYS_SEARCH:
        case AWTO_SYS_NOSIGNAL:
        case AWTO_SYS_SAVING:
        case AWTO_SYS_WAKE:

#if(_DIGITAL_PORT_SUPPORT == _ON)
            if((GET_SOURCE_JUDGE(g_ucSearchIndex) == _TRUE) && (GET_MODE_TIMING_CONFIRM() == _FALSE))
            {
                CLR_INPUT_TIMING_DOUBLE_CHECK();

                // Measure Current Input Timing to gather all required timing Info
                AwtoSwEvent(AWTO_SW_EV_PROBE, 17);
                if(ScalerMeasureInputInfo(GET_SOURCE_TYPE(g_ucSearchIndex), SysSourceGetInputPort()) == _TRUE)
                {
                    DebugMessageSystem("Input Timing H Polarity is Positive", (GET_INPUT_TIMING_H_POLARITY() == _HIGH));
                    DebugMessageSystem("Input Timing V Polarity is Positive", (GET_INPUT_TIMING_V_POLARITY() == _HIGH));
                    DebugMessageSystem("Input Timing InterLace", GET_INPUT_TIMING_INTERLACE_FLG());
                    DebugMessageSystem("Input Timing HFreq", GET_INPUT_TIMING_HFREQ());
                    DebugMessageSystem("Input Timing HTotal", GET_INPUT_TIMING_HTOTAL());
                    DebugMessageSystem("Input Timing HStart", GET_INPUT_TIMING_HSTART());
                    DebugMessageSystem("Input Timing HWidth", GET_INPUT_TIMING_HWIDTH());
                    DebugMessageSystem("Input Timing HSyncWidth", GET_INPUT_TIMING_HSYNCWIDTH());
                    DebugMessageSystem("Input Timing VFreq", GET_INPUT_TIMING_VFREQ());
                    DebugMessageSystem("Input Timing VTotal", GET_INPUT_TIMING_VTOTAL());
                    DebugMessageSystem("Input Timing VStart", GET_INPUT_TIMING_VSTART());
                    DebugMessageSystem("Input Timing VHeight", GET_INPUT_TIMING_VHEIGHT());
                    DebugMessageSystem("Input Timing VSyncSWidth", GET_INPUT_TIMING_VSYNCWIDTH());

                    AwtoSyncTiming();
                    AwtoSwEvent(AWTO_SW_EV_PROBE, 18);
                    SET_MODE_TIMING_CONFIRM();
                    SET_INPUT_TIMING_DOUBLE_CHECK();
                }
            }
#endif

#if(_DDR1_PHASE_CALIBRATION == _ON)
            if((GET_MODE_TIMING_CONFIRM() == _TRUE) && (GET_FIRST_AUTOK_STATUS() == _FALSE))
            {
                ScalerDDR1SearchPhase();
                SET_FIRST_AUTOK_STATUS();
            }
#elif(_SDRAM_PHASE_CALIBRATION == _ON)
            if((GET_MODE_TIMING_CONFIRM() == _TRUE) && (GET_FIRST_AUTOK_STATUS() == _FALSE))
            {
                ScalerSdramSearchPhase();
                SET_FIRST_AUTOK_STATUS();
            }
#endif

            if((s_ucSysState == AWTO_SYS_WAKE) && (GET_SOURCE_SWITCH_FINISH() == _TRUE) && (UserInterfaceGetIntoPSStatus() == _TRUE))
            {
                SysMachineRequest(_POWER_STATUS_SAVING, AWTO_SYS_BY_WAKE_EMPTY);    // SDK: a wake whose search found nothing
                CLR_SOURCE_SWITCH_FINISH();
            }

            if(UserInterfaceGetCableResetStatus() == _TRUE)
            {
                if(SysPowerGetPowerStatus() != _POWER_STATUS_NORMAL)
                {
                    SysMachineRequest(_POWER_STATUS_NORMAL, AWTO_SYS_BY_CABLE);
                }
                SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_SEARCH, AWTO_SYS_BY_CABLE);
                SysSourceCableResetProc();
            }
            break;

        case AWTO_SYS_DISPLAY:
            if(GET_MODE_DISPLAY_SETTING_READY() == _FALSE)
            {
                AwtoSwEvent(AWTO_SW_EV_PROBE, 14);
                if(SysModeDisplaySetting() == _TRUE)
                {
#if(_DEBUG_MESSAGE_CHECK_MDOMAIN == _ON)
                    ScalerMDomainCheckDisplaySetting();
#endif
                    // #162: the panel machine brings video up on request (power switch, UserCommonInterfaceReadyForActive)
                    AwtoSwEvent(AWTO_SW_EV_PROBE, 15);
                    UserCommonInterfaceAdjustColorProc();

                    AwtoSyncFreq();
                    AwtoSwEvent(AWTO_SW_EV_PROBE, 16);
                    SET_MODE_DISPLAY_SETTING_READY();
                    ScalerTimerCancelTimerEvent(_SYSTEM_TIMER_EVENT_JUDGE_NOSUPPORT_STATE);
                }
            }
            break;

        case AWTO_SYS_ACTIVE:
        case AWTO_SYS_FAST:
        case AWTO_SYS_HOLD:
            if(GET_MODE_STATE_CHANGE_MODE() == _TRUE)
            {
                ScalerGlobalFirstActiveProc(GET_SOURCE_TYPE(g_ucSearchIndex), SysSourceGetInputPort());
                AwtoSwEvent(AWTO_SW_EV_PROBE, 11);
                UserCommonInterfaceOsdActiveProc();
                UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, AWTO_PNL_BY_FIRST_ACTIVE));
                AwtoSwCacheStore();
                AwtoSwEvent(AWTO_SW_EV_PROBE, 12);
                SysSourceFirstActiveProc();
            }

            ScalerSyncActiveProc(GET_SOURCE_TYPE(g_ucSearchIndex));

#if(((_DDR3_PHASE_CALIBRATION == _ON) && (_MEMORY_PHASE_CALIBRATION_MODE == _MEMORY_PHASE_CALIBRATION_FRC_MODE)) && (_DDR3_PHASE_CHECK == _OFF))
            ScalerDDR3PhaseCalibrationFRCMode();
#elif(_DDR1_PHASE_CALIBRATION == _ON)
            ScalerTimerActiveTimerEvent(SEC(60), _SCALER_TIMER_EVENT_DDR_PHASE_CNT_CHECK);
#elif(_SDRAM_PHASE_CALIBRATION == _ON)
            ScalerTimerActiveTimerEvent(SEC(60), _SCALER_TIMER_EVENT_SDRAM_PHASE_CNT_CHECK);
#endif
            break;

        default:                                // INITIAL, OFF, AC_ON, NOSUPPORT, DOWN: no scaler work
            break;
    }

    CLR_MODE_STATE_CHANGE_MODE();
}

//--------------------------------------------------
// Description  : Get Required Wait Time before Active
// Input Value  : None
// Output Value : Required Wait Time
//--------------------------------------------------
WORD SysJudgeGetActiveWaitTime(void)
{
    if(GET_MODE_NO_WAIT_FOR_ACTIVE() == _FALSE)
    {
        switch(GET_SOURCE_TYPE(g_ucSearchIndex))
        {
#if(_VGA_SUPPORT == _ON)
            case _SOURCE_VGA:
                return _WAIT_TIME_TO_ACTIVE_VGA;
#endif

#if(_DVI_SUPPORT == _ON)
            case _SOURCE_DVI:
                return _WAIT_TIME_TO_ACTIVE_DVI;
#endif

#if(_HDMI_SUPPORT == _ON)
            case _SOURCE_HDMI:
                return _WAIT_TIME_TO_ACTIVE_HDMI;
#endif

#if(_DP_SUPPORT == _ON)
            case _SOURCE_DP:
                return _WAIT_TIME_TO_ACTIVE_DP;
#endif

            default:
                break;
        }
    }

    return 0;
}
