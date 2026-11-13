#include "UserCommonInclude.h"

// #81 per-port settings block: the one owner of a port's enable state (RL6449_Project.h AWTO_PORT_*).
// - State: isr_g_ucAwtoPortOff, one bit per port (AWTO_PORT_BIT). Changed only by AwtoPortBoot / AwtoPortSet; every line E1 (sync.tsv).
// - Rows: tAwtoPortRow maps a registry row to (field, port). A new per-port field = a new row kind + its bitmask.
// - Readers: PCB_Dn_HOTPLUG (HPD), ScalerMcuDdcRamEnable (EDID), ScalerGDIPhyPowerProc (receiver), SysSource (search), fast-switch
//   cache, wake poll, selector state.
__xdata BYTE isr_g_ucAwtoPortOff;                   // 0 at reset: all on until the settings load (AwtoPortBoot)

#ifdef _AWTO_NEW_SETTINGS
extern unsigned char set_put(unsigned char ucId, int iV, unsigned char ucNow);
extern unsigned char set_in_boot(void);
extern void ScalerGDIPhyPowerProc(BYTE ucPortSelect, EnumPowerAction enumPowerAction);     // Scaler-side owner of the receiver power

#define AWTO_PF_ENABLE                  0       // field: port enable (registry dN_enable)
static __code BYTE tAwtoPortRow[][3] = {        // registry id, field, port
    {AWTO_SET_D1_ENABLE, AWTO_PF_ENABLE, _D1_INPUT_PORT},
    {AWTO_SET_D2_ENABLE, AWTO_PF_ENABLE, _D2_INPUT_PORT},
    {AWTO_SET_D3_ENABLE, AWTO_PF_ENABLE, _D3_INPUT_PORT},
};
#define AWTO_PORT_ROWS                  ((BYTE)(sizeof(tAwtoPortRow) / sizeof(tAwtoPortRow[0])))
#define AWTO_PORT_NO_ROW                0xFF

static __xdata BYTE s_ucAwtoPortWhy;            // AwtoPortSelect: why the next enable happens (0 = by setting)

static BYTE AwtoPortRow(BYTE ucId)              // registry id -> tAwtoPortRow index
{
    BYTE ucR;

    for(ucR = 0; ucR < AWTO_PORT_ROWS; ucR++)
    {
        if(tAwtoPortRow[ucR][0] == ucId)
        {
            return ucR;
        }
    }
    return AWTO_PORT_NO_ROW;
}

static BYTE AwtoPortEnableId(BYTE ucPort)       // port -> its enable row id
{
    BYTE ucR;

    for(ucR = 0; ucR < AWTO_PORT_ROWS; ucR++)
    {
        if((tAwtoPortRow[ucR][1] == AWTO_PF_ENABLE) && (tAwtoPortRow[ucR][2] == ucPort))
        {
            return tAwtoPortRow[ucR][0];
        }
    }
    return AWTO_PORT_NO_ROW;
}

// The transition: line first (its time = the change), then HPD, EDID channel, receiver, search.
static void AwtoPortSet(BYTE ucPort, BYTE ucOn, BYTE ucWhy)
{
    BYTE ucBit = AWTO_PORT_BIT(ucPort);

    if(((isr_g_ucAwtoPortOff & ucBit) == 0) == (ucOn != 0))
    {
        AwtoSyncPush(AWTO_SYNC_EV_PORT, (ucOn != 0) ? AWTO_PORT_WHY_ALREADY_ON : AWTO_PORT_WHY_ALREADY_OFF, ucPort);
        return;
    }
    AwtoSyncPush(AWTO_SYNC_EV_PORT, ucWhy, ucPort);
    if(ucOn != 0)
    {
        isr_g_ucAwtoPortOff &= ~ucBit;
        ScalerMcuDdcRamEnable();
        ScalerGDIPhyPowerProc(ucPort, _POWER_ACTION_OFF_TO_NORMAL);
        if(ucPort == _D1_INPUT_PORT)
        {
            ScalerDpSetHotPlugEvent(_D1_INPUT_PORT, _DP_HPD_ASSERTED);     // the SDK DP HPD handler raises it (cable checked there)
        }
        else if(ucPort == _D2_INPUT_PORT)
        {
            PCB_D2_HOTPLUG(_D2_HOT_PLUG_HIGH);                              // HDMI: as SysSourceHdmi5VDetection (toggle off)
        }
        else
        {
            PCB_D3_HOTPLUG(_D3_HOT_PLUG_HIGH);
        }
        return;
    }
    isr_g_ucAwtoPortOff |= ucBit;
    if(ucPort == _D1_INPUT_PORT)
    {
        PCB_D1_HOTPLUG(_D1_HOT_PLUG_LOW);
    }
    else if(ucPort == _D2_INPUT_PORT)
    {
        PCB_D2_HOTPLUG(_D2_HOT_PLUG_LOW);
    }
    else
    {
        PCB_D3_HOTPLUG(_D3_HOT_PLUG_LOW);
    }
    ScalerMcuDdcRamEnable();
    ScalerGDIPhyPowerProc(ucPort, _POWER_ACTION_SWITCH_INTERFACE_TO_OFF);
    if(SysSourceGetInputPort() == ucPort)
    {
        AwtoPortSkipSearch();                   // searching it now (not on screen: set_veto): on to the next port
        SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_SEARCH, AWTO_SYS_BY_SETTINGS);
    }
}

// UserInterfaceInitial (AwtoSetInit), after the settings load, before the first HPD high of the SDK (DP: SysSourceInitial / the
// cable detect; HDMI: GPIO init raised it at reset, so a disabled HDMI port goes low here).
void AwtoPortBoot(void)
{
    BYTE ucR;
    BYTE ucPort;

    for(ucR = 0; ucR < AWTO_PORT_ROWS; ucR++)
    {
        ucPort = tAwtoPortRow[ucR][2];
        if((tAwtoPortRow[ucR][1] == AWTO_PF_ENABLE) && (set_get(tAwtoPortRow[ucR][0]) == 0))
        {
            isr_g_ucAwtoPortOff |= AWTO_PORT_BIT(ucPort);
            AwtoSyncPush(AWTO_SYNC_EV_PORT, AWTO_PORT_WHY_BOOT, ucPort);
        }
    }
    if(AWTO_PORT_OFF(_D2_INPUT_PORT))
    {
        PCB_D2_HOTPLUG(_D2_HOT_PLUG_LOW);
    }
    if(AWTO_PORT_OFF(_D3_INPUT_PORT))
    {
        PCB_D3_HOTPLUG(_D3_HOT_PLUG_LOW);
    }
}

// settings.c set_put: 1 = refuse. Disabling the input on screen would blank the picture; the last enabled one would leave
// nothing to search (settings.c refuses that too, silently).
unsigned char set_veto(unsigned char ucId, int iV)
{
    BYTE ucR = AwtoPortRow(ucId);
    BYTE ucPort;
    BYTE ucMode = SysModeGetModeState();

    if((ucR == AWTO_PORT_NO_ROW) || (iV != 0))
    {
        return 0;
    }
    ucPort = tAwtoPortRow[ucR][2];
    if((SysSourceGetInputPort() == ucPort) && ((ucMode == _MODE_STATUS_ACTIVE) || (ucMode == _MODE_STATUS_DISPLAY_SETTING)))
    {
        AwtoSyncPush(AWTO_SYNC_EV_PORT, AWTO_PORT_WHY_ON_SCREEN, ucPort);
        return 1;
    }
    if((isr_g_ucAwtoPortOff | AWTO_PORT_BIT(ucPort)) == (AWTO_PORT_BIT(_D1_INPUT_PORT) | AWTO_PORT_BIT(_D2_INPUT_PORT) | AWTO_PORT_BIT(_D3_INPUT_PORT)))
    {
        AwtoSyncPush(AWTO_SYNC_EV_PORT, AWTO_PORT_WHY_LAST, ucPort);
        return 1;
    }
    return 0;
}

void set_ap_port(unsigned char ucId, int iV)    // registry apply 'port': menu, DDC/CI (VCP 0xEC..0xEE), mailbox, test cmd
{
    BYTE ucR = AwtoPortRow(ucId);
    BYTE ucWhy = s_ucAwtoPortWhy;

    s_ucAwtoPortWhy = 0;
    if((ucR == AWTO_PORT_NO_ROW) || (set_in_boot() == _TRUE))
    {
        return;                                 // boot: AwtoPortBoot applied the stored values
    }
    AwtoPortSet(tAwtoPortRow[ucR][2], (iV != 0), (iV == 0) ? AWTO_PORT_WHY_OFF : ((ucWhy != 0) ? ucWhy : AWTO_PORT_WHY_ON));
}

// Input selector / input select to a disabled port: enable it through the registry (stored at the NVRAM gate), then the caller
// switches. ucWhy = AWTO_PORT_WHY_SELECTOR / _SELECT.
void AwtoPortSelect(unsigned char ucPort, unsigned char ucWhy)
{
    BYTE ucId = AwtoPortEnableId(ucPort);

    if((ucId == AWTO_PORT_NO_ROW) || !AWTO_PORT_OFF(ucPort))
    {
        return;
    }
    s_ucAwtoPortWhy = ucWhy;
    set_put(ucId, 1, 1);
    s_ucAwtoPortWhy = 0;
}
#else
void AwtoPortSelect(unsigned char ucPort, unsigned char ucWhy)
{
    ucPort = ucPort;
    ucWhy = ucWhy;
}
#endif
