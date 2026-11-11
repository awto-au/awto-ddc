#if(_AWTO_DIAG == _ON)
// #33: 0x01..0x05 = key messages 0..4 = menu role (physical AUTO) / UP / DOWN / exit role (physical MENU) / SOURCE; logged as injected, #39), 0x41/0x42 = key test screen open/close (#39), 0x10+n = OSD event n (n<16; 0x70+n-16 above), 0x20 = debug pop-up (#34).
// 0x22/0x23: on-screen message log on/off (#56); 0x28/0x29 debug messages on/off, NVRAM (#74). #28 holds (g_stAwtoDiag.ucHold):
// 0x26 debug pop-up held, 0x27 clear all holds (0x21 / 0x24 / 0x25 were the boot logo, #144). #60: 0x31..0x33 switch to D1..D3 (fixed port),
// 0x30 auto search, 0x40 settings defaults (#67), 0x3D one store write, 0x3E POWER key (#151). 0x50+n directly holds EnumOSDDispMsg n for visual review. 0x2A..0x2F Timer0 events (#138).
// Inserted into RTD2014Key.c (OSD macros).
#define AWTO_HOLD_POPUP                         0x02

void AwtoMsgLoad(void)              // #74: after RTDNVRamStartup (keil2sdcc sub); reset value 0 = off until then
{
#if(_DEBUG_MESSAGE_SUPPORT == _ON)
    g_ucAwtoMsgOn = g_stOSDUserData.b1AwtoMsgOn;
#endif
}

// Hold guards (#28): a held visual survives the SDK's own OSD paths; each blocked path is logged (StAwtoSw, scripts/sw_timeline.py).
bit AwtoHoldBlocksDisable(void)                  // top of OsdDispDisableOsd: the SDK OSD timeout / reset paths
{
#ifdef _AWTO_NEW_SETTINGS
    if((g_ucAwtoMenuOn != 0) && (SysPowerGetPowerStatus() == _POWER_STATUS_NORMAL) && (SysModeGetModeState() != _MODE_STATUS_POWER_SAVING))
    {
        return _TRUE;                            // #67 / #88: the source search resets the SDK OSD every few seconds; the awto menu closes itself
    }
#endif
    if(g_stAwtoDiag.ucHold == 0)
    {
        return _FALSE;
    }
    AwtoSwEvent(AWTO_SW_EV_HOLD_BLOCK, SysModeGetModeState());
    g_stAwtoSw.ucHoldBlocks++;
    return _TRUE;
}

static __xdata unsigned int s_usAwtoHoldCancel;  // usT2Isr at the last OSD_DISABLE cancel

void AwtoDiagTestCmd(void)
{
    unsigned char ucCmd = g_stAwtoDiag.ucHold;

    if((ucCmd != 0) && ((unsigned int)(g_stAwtoDiag.usT2Isr - s_usAwtoHoldCancel) >= AWTO_KEY_REFRESH_MS))
    {
        s_usAwtoHoldCancel = g_stAwtoDiag.usT2Isr;                       // pending pop-up timeout (each draw re-arms it; seconds):
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);      // every 80 ms, not every pass (a cancel walks the timer table)
    }
    ucCmd = g_stAwtoDiag.ucTestCmd;
    if(ucCmd == 0)
    {
        return;
    }
    g_stAwtoDiag.ucTestCmd = 0;
    if(ucCmd <= 5)
    {
        AwtoKeyInject(ucCmd - 1);                       // routed by the next AwtoKeyPoll (#129)
    }
    else if((ucCmd == 0x41) || (ucCmd == 0x42))         // #39 key test screen: 41 open, 42 close
    {
        AwtoKeyTestSet(ucCmd == 0x41);
    }
    else if((ucCmd == 0x43) || (ucCmd == 0x44))         // unused-GPIO live screen: open / close
    {
        AwtoGpioTestSet(ucCmd == 0x43);
    }
    else if(ucCmd == 0x45)                              // limit probe: open with the stored line count (default 24) / 0x46 close
    {
        AwtoProbeSet((g_ucAwtoProbeLines != 0) ? g_ucAwtoProbeLines : 24);
    }
    else if(ucCmd == 0x46)
    {
        AwtoProbeSet(0);
    }
#if(_AWTO_WDT == _ON)
    else if((ucCmd >= 0x4C) && (ucCmd <= 0x4E))         // #131 watchdog test hangs: 4C spin, 4E spin with EA off (4D gone, #138)
    {
        AwtoWdtHang(ucCmd - 0x4C);
    }
    else if((ucCmd == 0x49) || (ucCmd == 0x4F))         // #138 WDT probe for unit 2: 49 normal mode, 4F timer mode
    {
        AwtoWdtProbe(ucCmd == 0x4F);
    }
    else if((ucCmd >= 0x2A) && (ucCmd <= 0x2F))         // #138 Timer0 events: 2A DP rebuild 30 ms, 2B/2C HDMI RR D2/D3 10 ms,
    {                                                   // 2D 2A+2B, 2E/2F = 2A/2B across a forced clock-switch reload
        AwtoT0EvTest(ucCmd - 0x2A);
    }
    else if((ucCmd >= 0x5A) && (ucCmd <= 0x5C))         // 5A/5B = 2A/2B at the PS reload, 5C three out of order + cancel
    {
        AwtoT0EvTest(ucCmd - 0x5A + 6);
    }
    else if(ucCmd == 0x24)                              // stuck Timer0 handler
    {
        AwtoT0EvTest(9);
    }
    else if((ucCmd == 0x25) || ((ucCmd >= 0x5D) && (ucCmd <= 0x5F)))   // EXINT0 hook: 25 off, 5D arm, 5E 2 ms spin, 5F stuck
    {
        g_ucAwtoT0Test = (ucCmd == 0x25) ? 0 : (ucCmd - 0x5C);
    }
#endif
    else if((ucCmd >= 0x60) && (ucCmd <= 0x6F))         // diagnostic screen font: 0x60 + font index (osd_font_load)
    {
        g_ucAwtoDiagFont = ucCmd - 0x60 + 1;
    }
    else if((ucCmd == 0x4A) || (ucCmd == 0x4B))         // diagnostic screens at 1x / 2x size
    {
        g_ucAwtoDiagSmall = (ucCmd == 0x4A);
    }
    else if(ucCmd == 0x47)                              // scroll down one row (console; the limit probe steps on)
    {
        AwtoConScroll(1);
        AwtoProbeScroll(0);
    }
    else if(ucCmd == 0x48)                              // scroll up one row (console; the limit probe goes back to 0)
    {
        AwtoConScroll(-1);
        AwtoProbeScroll(1);
    }
    else if(ucCmd >= 0xC0)                              // 0xC0 + n: probe columns = 4 * n (0xE8 = 160)
    {
        g_ucAwtoProbeCols = (ucCmd - 0xC0) << 2;
    }
    else if(ucCmd >= 0x80)                              // 0x80 + n: probe with n lines (n = 1..63)
    {
        g_ucAwtoProbeLines = ucCmd - 0x80;
        AwtoProbeSet(g_ucAwtoProbeLines);
    }
    else if((ucCmd >= 0x50) && (ucCmd <= 0x59))         // every compiled user-visible OSD message, held for review
    {
        OsdDispOsdMessage((EnumOSDDispMsg)(ucCmd - 0x50));
        g_stAwtoDiag.ucHold |= AWTO_HOLD_POPUP;
    }
    else if((ucCmd == 0x20) || (ucCmd == 0x26))         // debug pop-up: the diagnostic console
    {
        AwtoDiagConsole(1);
    }
    else if(ucCmd == 0x27)
    {
        unsigned char ucWas = g_stAwtoDiag.ucHold;

        AwtoDiagConsole(0);

        g_stAwtoDiag.ucHold = 0;                     // first: OsdDispDisableOsd is blocked while a hold is set
        if((ucWas & AWTO_HOLD_POPUP) != 0)
        {
            OsdDispDisableOsd();
        }
    }
    else if((ucCmd >= 0x31) && (ucCmd <= 0x33))      // #60 switch to D1/D2/D3, fixed port, as VCP 0x60 (RTD2014Ddcci.c)
    {
        AwtoInputSelect(_D0_INPUT_PORT + (ucCmd - 0x30), ucCmd);     // fw/sdcc/awto_ddcci.inc, shared with VCP 0x60
    }
    else if((ucCmd == 0x22) || (ucCmd == 0x23))      // #56: on-screen message log on / off
    {
        g_ucAwtoMsgLog = (ucCmd == 0x22);
    }
#if(_DEBUG_MESSAGE_SUPPORT == _ON)
    else if((ucCmd == 0x28) || (ucCmd == 0x29))      // #74: debug messages on / off; stored by the #151 gate
    {
#ifdef _AWTO_NEW_SETTINGS
        extern int set_put(unsigned char ucId, int iV, unsigned char ucNow);
        set_put(AWTO_SET_DEBUG_MSGS, (ucCmd == 0x28), 1);
#else
        g_stOSDUserData.b1AwtoMsgOn = (ucCmd == 0x28);
        g_ucAwtoMsgOn = (ucCmd == 0x28);
        SET_OSD_EVENT_MESSAGE(_OSDEVENT_SAVE_NVRAM_OSDUSERDATA_MSG);
#endif
    }
#endif
#if(_AWTO_WAKE_HOLD == _ON)
    else if((ucCmd >= 0x36) && (ucCmd <= 0x3A))      // #78 power levels: 36 all on (defaults), 37 L1 off (SDK path),
    {                                                // 38 L2 off, 39 short timeouts L2 5 s / L3 20 s (tests), 3A L3 off
        g_stAwtoPower.ucL1 = (ucCmd != 0x37);
        g_stAwtoPower.ucL2 = (ucCmd != 0x38);
        g_stAwtoPower.ucL3 = (ucCmd != 0x3A);
        g_stAwtoPower.usL2Sec = (ucCmd == 0x39) ? 5 : AWTO_L2_SEC;
        g_stAwtoPower.usL3Sec = (ucCmd == 0x39) ? 20 : AWTO_L3_SEC;
    }
#endif
#ifdef _AWTO_NEW_SETTINGS
    else if(ucCmd == 0x40)                              // #67 every settings-registry row to its default (recovery)
    {
        extern void set_defaults(void);
        set_defaults();
    }
    else if(ucCmd == 0x3D)                              // #151 test: one real item write now (inert aux row kvm_prefill toggled)
    {
        extern void AwtoNvTestWrite(void);
        AwtoNvTestWrite();
    }
#endif
    else if(ucCmd == 0x3E)                              // #151 test: the POWER key (soft off / on; off flushes the store)
    {
        if(SysPowerGetPowerStatus() == _POWER_STATUS_OFF)
        {
            SET_OSD_STATE(_MENU_NONE);
            SysPowerSetTargetPowerStatus(_POWER_STATUS_NORMAL);
        }
        else
        {
            SysPowerSetTargetPowerStatus(_POWER_STATUS_OFF);
        }
    }
    else if(ucCmd == 0x34)                              // #78 arm the switch log only (wake / power-level timing)
    {
        AwtoSwArm(SysSourceGetInputPort());
    }
#if(_AWTO_DBG_SWAP == _ON)
    else if((ucCmd == 0x3B) || (ucCmd == 0x3C))         // #79 debug link: 3B back to DDC/CI now, 3C on until told back
    {
        AwtoDbgLinkStart((ucCmd == 0x3C) ? 0xFF : 0);
    }
#endif
    else if(ucCmd == 0x30)                              // #60 back to auto search in group (NVRAM default), no switch
    {
        AwtoSwEvent(AWTO_SW_EV_CMD, ucCmd);
        SysSourceSetScanType(_SOURCE_SWITCH_AUTO_IN_GROUP);
    }
    else if((ucCmd >= 0x10) && (ucCmd <= 0x1F))         // OSD events 0..15 (#53.17); 0x20..0x22 are commands
    {
        SET_OSD_EVENT_MESSAGE(ucCmd - 0x10);
    }
    else if((ucCmd >= 0x70) && (ucCmd <= (0x70 + _OSDEVENT_DP_VERSIOM_MSG - 16)))   // OSD events 16..last (#113)
    {
        SET_OSD_EVENT_MESSAGE(ucCmd - 0x70 + 16);
    }
}
#endif
