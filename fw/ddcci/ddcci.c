#include "UserCommonInclude.h"

// #60 KVM: one input-select entry (test cmds 0x31..0x33, DDC/CI VCP 0x60) + DDC/CI 0x37 on the spare IIC engines, polled
// from the main loop (no IRQ: the SDK EXINT1 ISR only serves the main engine, which stays in debug mode 0x35).
// Recipe: SDK ScalerMcuDdcciIntGetData_EXINT1 / ScalerMcuDdcciSendData on the IIC_n copy of FF22..FF2B.
BYTE AwtoPortCable(BYTE ucPort)                 // #84: cable status of a board port (D1..D3)
{
    return (ucPort == _D1_INPUT_PORT) ? GET_D1_CABLE_STATUS() : (ucPort == _D2_INPUT_PORT) ? GET_D2_CABLE_STATUS() :
           GET_D3_CABLE_STATUS();
}

void AwtoInputSelect(BYTE ucPort, BYTE ucWhy)  // main-loop context only; ucWhy = test cmd or 0x60 (logged)
{
    if((ucPort != _D1_INPUT_PORT) && (ucPort != _D2_INPUT_PORT) && (ucPort != _D3_INPUT_PORT))
    {
        return;                                 // SDK VCP 0x60 table: VGA / DVI / DP2 have no port on this board
    }
    if((ucWhy == 0x60) && (AwtoPortCable(ucPort) == _FALSE))
    {
        AwtoSwEvent(AWTO_SW_EV_DEADPORT, 1);    // #84: VCP 0x60 / menu row to a port with no cable = fixed-port dead end; test cmds still go
        AwtoSyncPush(AWTO_SYNC_EV_DEADPORT, 1, ucPort);
        return;
    }
    AwtoPortSelect(ucPort, AWTO_PORT_WHY_SELECT);   // #81: selecting a disabled port enables it (stored), then the switch
    if((ucWhy == 0x60) && (ucPort == SysSourceGetInputPort()) && (SysModeGetModeState() == _MODE_STATUS_ACTIVE))
    {
        return;                                 // KVM "switch to where we are": no re-search blank
    }
    AwtoSwArm(ucPort);
    AwtoSwEvent(AWTO_SW_EV_CMD, ucWhy);
#ifdef _AWTO_NEW_SETTINGS
    g_ucAwtoNvSwitch = 1;                       // #151 flush gate: not stable
#endif
    AwtoSyncBegin(AWTO_SYNC_K_SWITCH, ucPort);  // #139: the fast path skips SysSourceSwitchInputPort
    SET_FORCE_POW_SAV_STATUS(_FALSE);
    SysSourceSetScanType(_SOURCE_SWITCH_FIXED_PORT);
#if(_AWTO_FAST_SWITCH == _ON)
    if(AwtoSwFast(ucPort) == _FALSE)
#endif
    {
        SysSourceSwitchInputPort(ucPort);
        AwtoSwEvent(AWTO_SW_EV_PROBE, 6);
        SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_SEARCH, AWTO_SYS_BY_INPUT);
    }
}

void AwtoDeadPortPoll(void)                     // #84: fixed port, no cable on it, no signal, another port cabled: auto search
{
    BYTE ucCur = SysSourceGetInputPort();

    if((SysSourceGetScanType() != _SOURCE_SWITCH_FIXED_PORT) ||
       ((SysModeGetModeState() != _MODE_STATUS_NOSIGNAL) && (SysModeGetModeState() != _MODE_STATUS_POWER_SAVING)) ||
       (AwtoPortCable(ucCur) == _TRUE) ||
       (((ucCur == _D1_INPUT_PORT) || (GET_D1_CABLE_STATUS() == _FALSE) || AWTO_PORT_OFF(_D1_INPUT_PORT)) &&     // #81: a disabled
        ((ucCur == _D2_INPUT_PORT) || (GET_D2_CABLE_STATUS() == _FALSE) || AWTO_PORT_OFF(_D2_INPUT_PORT)) &&     // port is no way out
        ((ucCur == _D3_INPUT_PORT) || (GET_D3_CABLE_STATUS() == _FALSE) || AWTO_PORT_OFF(_D3_INPUT_PORT))))
    {
        return;
    }
    AwtoSwEvent(AWTO_SW_EV_DEADPORT, 3);
    AwtoSyncPush(AWTO_SYNC_EV_DEADPORT, 2, ucCur);
    SysSourceSetScanType(_SOURCE_SWITCH_AUTO_IN_GROUP);
    SET_FORCE_POW_SAV_STATUS(_FALSE);
    SysMachineRequest(_POWER_STATUS_NORMAL, AWTO_SYS_BY_DEADPORT);
    SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_SEARCH, AWTO_SYS_BY_DEADPORT);
}

#if(_AWTO_DBG_SWAP == _ON)
static __xdata WORD s_usAwtoDbgLinkMs;

void AwtoDbgLinkStart(BYTE ucMin)               // VCP AWTO_DBG_LINK_VCP, test cmd 0x3B; 0 = back to DDC/CI
{
    s_usAwtoDbgLinkMs = (WORD)AwtoMs();
    AwtoDbgLinkSet(ucMin);
}

void AwtoDbgLinkPoll(void)                      // AWTO_DDCCI_POLL() while the debug link is on: minutes count down
{
    WORD usNow;

    if(g_usAwtoDbgLinkSec == 0)
    {
        return;                                 // until told back
    }
    usNow = (WORD)AwtoMs();
    if((WORD)(usNow - s_usAwtoDbgLinkMs) < 1000)
    {
        return;
    }
    s_usAwtoDbgLinkMs += 1000;
    if(--g_usAwtoDbgLinkSec == 0)
    {
        AwtoDbgLinkSet(0);
    }
}
#endif

#if(_AWTO_DDCCI_ENGINES != 0)
#define AWTO_IIC_CH_SEL                 0       // register offsets from the engine base (IIC_1 = 0xFE86 .. 0xFE8F)
#define AWTO_IIC_SLAVE                  1
#define AWTO_IIC_SUB_IN                 2
#define AWTO_IIC_DATA_IN                3
#define AWTO_IIC_DATA_OUT               4
#define AWTO_IIC_STATUS                 5       // bit4 stop, bit2 data in, bit1 sub (source byte), bit0 slave
#define AWTO_IIC_IRQ                    6
#define AWTO_IIC_STATUS2                7       // bit5/4 buffer over/underflow, bit2 full, bit1 empty
#define AWTO_IIC_IRQ2                   8       // bit6 reset buffer, bit5 MCU writes the buffer
#define AWTO_IIC_CHANNEL                9       // bit5 null message when the host reads an empty buffer
#if(_AWTO_NET == _ON)
#define AWTO_DDC_RX                     17      // #80 net op D0: source + len + 14 + checksum (16-byte engine buffer)
#else
#define AWTO_DDC_RX                     14      // longest request we take: host time table write (#157) = 14 bytes incl. source + checksum
#endif
#define AWTO_DDC_CAP_CHUNK              10      // 16-byte engine buffer - 6 framing bytes

static __code WORD tAwtoIicBase[3] = {AWTO_R_IIC_1_CH_SEL, AWTO_R_IIC_2_CH_SEL, AWTO_R_IIC_3_CH_SEL};
#if(_AWTO_DDCCI_ENGINES == 3)
static __code BYTE tAwtoIicCh[3] = {0x02, 0x03, 0x04};             // DDC1 (D1 DP AUX), DDC2 (D2), DDC3 (D3): one host each
#endif
static __code char tAwtoDdcCaps[] = "(prot(monitor)type(LCD)model(awto)cmds(01 02 03 F3)vcp(10 60(0F 11 12) D6)mccs_ver(2.2))";
static __xdata BYTE s_ppucAwtoDdcRx[_AWTO_DDCCI_ENGINES][AWTO_DDC_RX];
static __xdata BYTE s_pucAwtoDdcN[_AWTO_DDCCI_ENGINES];

static BYTE AwtoDdcPortToVcp(BYTE ucPort)
{
    return (ucPort == _D1_INPUT_PORT) ? 0x0F : (ucPort == _D2_INPUT_PORT) ? 0x11 : (ucPort == _D3_INPUT_PORT) ? 0x12 : 0x00;
}

static void AwtoDdcReply(volatile __xdata BYTE *pucR, BYTE *pucTx)       // pucTx[1] = 0x80 | payload length; checksum appended
{
    BYTE ucN = (pucTx[1] & 0x7F) + 2;
    BYTE ucI;
    BYTE ucSum = 0x50;                          // DDC/CI reply checksum starts at the virtual host address

    pucR[AWTO_IIC_IRQ2] |= (_BIT6 | _BIT5);
    for(ucI = 0; ucI < ucN; ucI++)
    {
        ucSum ^= pucTx[ucI];
        pucR[AWTO_IIC_DATA_OUT] = pucTx[ucI];
    }
    pucR[AWTO_IIC_DATA_OUT] = ucSum;
    pucR[AWTO_IIC_IRQ2] &= ~_BIT5;
}

#ifdef _AWTO_NEW_SETTINGS
extern BYTE vcp_get(BYTE ucCode, WORD xdata *pusCur, WORD xdata *pusMax, BYTE xdata *pucType);
extern BYTE vcp_set(BYTE ucCode, WORD usV);
extern void set_nv_commit(BYTE ucShow);
extern WORD set_caps_len(void);
extern char set_caps_at(WORD usI);
static __xdata WORD s_usAwtoDdcCur;
static __xdata WORD s_usAwtoDdcMax;
static __xdata BYTE s_ucAwtoDdcType;

// MCCS get / set / save / capabilities from the registry (awto-rtdfw vcp.c). _TRUE = handled (replied or no reply due)
static bit AwtoDdcRegistry(volatile __xdata BYTE *pucR, BYTE *pucRx, BYTE ucLen, BYTE *pucTx)
{
    BYTE ucI;
    WORD usOff;

    if((pucRx[2] == 0x03) && (ucLen >= 7))      // set VCP: 51 84 03 vcp hi lo chk; no reply
    {
        vcp_set(pucRx[3], ((WORD)pucRx[4] << 8) | pucRx[5]);
        return _TRUE;
    }
    if((pucRx[2] == 0x0C) && (ucLen >= 4))      // save current settings: 51 81 0C chk
    {
        set_nv_commit(0);                       // #151: a flag; the gate writes after this handler
        return _TRUE;
    }
    if((pucRx[2] == 0x01) && (ucLen >= 5))      // get VCP -> 6E 88 02 rc vcp type maxH maxL curH curL chk
    {
        pucTx[3] = 0x00;
        if(vcp_get(pucRx[3], &s_usAwtoDdcCur, &s_usAwtoDdcMax, &s_ucAwtoDdcType) == 0)
        {
            pucTx[3] = 0x01;                    // unsupported VCP code
            s_usAwtoDdcCur = s_usAwtoDdcMax = 0;
            s_ucAwtoDdcType = 0;
        }
        else if(pucRx[3] == 0xD6)               // DPM: the firmware's power state, not the last request
        {
            s_usAwtoDdcCur = (SysPowerGetPowerStatus() == _POWER_STATUS_NORMAL) ? 0x01 : 0x04;
        }
        pucTx[1] = 0x88;
        pucTx[2] = 0x02;
        pucTx[4] = pucRx[3];
        pucTx[5] = s_ucAwtoDdcType;
        pucTx[6] = s_usAwtoDdcMax >> 8;
        pucTx[7] = s_usAwtoDdcMax & 0xFF;
        pucTx[8] = s_usAwtoDdcCur >> 8;
        pucTx[9] = s_usAwtoDdcCur & 0xFF;
        AwtoDdcReply(pucR, pucTx);
        return _TRUE;
    }
    if((pucRx[2] == 0xF3) && (ucLen >= 6))      // capabilities chunk from the generated string
    {
        usOff = ((WORD)pucRx[3] << 8) | pucRx[4];
        ucLen = (usOff >= set_caps_len()) ? 0 : ((set_caps_len() - usOff) > AWTO_DDC_CAP_CHUNK) ? AWTO_DDC_CAP_CHUNK : (BYTE)(set_caps_len() - usOff);
        pucTx[1] = 0x80 | (ucLen + 3);
        pucTx[2] = 0xE3;
        pucTx[3] = pucRx[3];
        pucTx[4] = pucRx[4];
        for(ucI = 0; ucI < ucLen; ucI++)
        {
            pucTx[5 + ucI] = set_caps_at(usOff + ucI);
        }
        AwtoDdcReply(pucR, pucTx);
        return _TRUE;
    }
    return _FALSE;
}
#endif

static void AwtoDdcRequest(volatile __xdata BYTE *pucR, BYTE *pucRx, BYTE ucLen)
{
    BYTE pucTx[16];
    BYTE ucI;
    BYTE ucSum = 0x6E;
    WORD usVal = 0;
    WORD usMax = 0;

    for(ucI = 0; ucI < ucLen; ucI++)
    {
        ucSum ^= pucRx[ucI];
    }
    if(ucSum != 0)
    {
        return;                                 // bad checksum: no reply, the host retries
    }
#ifdef _AWTO_NEW_SETTINGS
    g_ucAwtoNvDdc = 1;                          // #151 flush gate: DDC/CI busy
#endif
    pucTx[0] = 0x6E;
#if(_AUDIO_SUPPORT == _ON)
    // #94 ear-test steps / tone announce (dev.py sound-test): VCP 0x63 is unused by the AWTO registry; before the registry
    if((pucRx[2] == 0x03) && (ucLen >= 7) && (pucRx[3] == AWTO_AUDIO_TEST_VCP) && ((pucRx[4] != 0) || (pucRx[5] >= AWTO_AUDIO_TEST_START)))
    {
        AwtoAudioTestStep(pucRx[4], pucRx[5]);  // fw/audio/amp.c
        return;
    }
#endif
#ifdef _AWTO_AUDIO_TEST
    // Test builds only (-D _AWTO_AUDIO_TEST): VCP 0x63 = 0 / 1..0x0F internal sine generator off / on, get = generator state
    if((pucRx[2] == 0x03) && (ucLen >= 7) && (pucRx[3] == AWTO_AUDIO_TEST_VCP))
    {
        if(pucRx[5] == 0)
        {
            SysAudioInternalGenTestProc(_OFF);
        }
        else
        {
            SysAudioInternalGenTestProc(_ON);
            SysAudioMuteProc(_OFF);
        }
        return;
    }
    if((pucRx[2] == 0x01) && (ucLen >= 5) && (pucRx[3] == AWTO_AUDIO_TEST_VCP))
    {
        pucTx[1] = 0x88;
        pucTx[2] = 0x02;
        pucTx[3] = 0x00;
        pucTx[4] = 0x63;
        pucTx[5] = 0x00;
        pucTx[6] = 0x00;
        pucTx[7] = 0x01;
        pucTx[8] = 0x00;
        pucTx[9] = ScalerAudioGetInternalAudioGenEnable(SysSourceGetInputPort());
        AwtoDdcReply(pucR, pucTx);
        return;
    }
#endif
#if(_AWTO_DBG_SWAP == _ON)
    if((pucRx[2] == 0x03) && (ucLen >= 7) && (pucRx[3] == AWTO_DBG_LINK_VCP) && (pucRx[4] == AWTO_DBG_LINK_MAGIC) && (pucRx[5] != 0))
    {
        AwtoDbgLinkStart(pucRx[5]);             // #79: debug slave 0x35 on this DDC for value minutes (0xFF = until told back)
        return;
    }
#endif
    if((pucRx[3] == AWTO_HT_VCP) && (pucRx[2] == 0xE7) && (ucLen >= 14) && (pucRx[4] == 0) && (pucRx[5] == 0))
    {
        AwtoHtSync(pucRx + 6);                  // #157 table write 51 8B E7 E9 00 00 time[4] ms[2] ofs chk: store, no reply
        return;
    }
    if((pucRx[3] == AWTO_HT_VCP) && (pucRx[2] == 0x01) && (ucLen >= 5))
    {
        pucTx[1] = 0x88;                        // get: max = syncs since boot, cur = last drift ms (int16)
        pucTx[2] = 0x02;
        pucTx[3] = 0x00;
        pucTx[4] = AWTO_HT_VCP;
        pucTx[5] = 0x00;
        pucTx[6] = 0x00;
        pucTx[7] = isr_g_stAwtoHt.ucSyncs;
        pucTx[8] = (BYTE)((WORD)isr_g_stAwtoHt.iDrift >> 8);
        pucTx[9] = (BYTE)isr_g_stAwtoHt.iDrift;
        AwtoDdcReply(pucR, pucTx);
        return;
    }
#ifdef _AWTO_NEW_SETTINGS
    if(AwtoDdcRegistry(pucR, pucRx, ucLen, pucTx) == _TRUE)     // #67: MCCS 2.2 on the settings registry (fw/settings/settings_glue.c)
    {
        return;
    }
#endif
#if(_AWTO_NET == _ON)
    if((pucRx[2] == 0xD0) && (ucLen >= 7))      // #80 net: 51 len D0 seq ctl ack data[n] chk -> 6E len D1 seq flags free data[m] chk
    {
        pucTx[1] = 0x80 | (4 + AwtoNetXchgA(pucRx + 3, ucLen - 7, pucTx + 3));
        pucTx[2] = 0xD1;
        AwtoDdcReply(pucR, pucTx);
        return;
    }
#endif
    if((pucRx[2] == 0x03) && (ucLen >= 7))      // set VCP: 51 84 03 vcp hi lo chk
    {
        if(pucRx[3] == 0x60)
        {
            ucI = pucRx[5];
            ucI = (ucI == 0x0F) ? _D1_INPUT_PORT : (ucI == 0x11) ? _D2_INPUT_PORT : (ucI == 0x12) ? _D3_INPUT_PORT : _NO_INPUT_PORT;
            if(ucI != _NO_INPUT_PORT)
            {
                AwtoInputSelect(ucI, 0x60);
            }
        }
        return;
    }
    if((pucRx[2] == 0x01) && (ucLen >= 5))      // get VCP: 51 82 01 vcp chk -> 6E 88 02 rc vcp 00 maxH maxL curH curL chk
    {
        pucTx[3] = 0x00;
        if(pucRx[3] == 0x60)
        {
            usMax = 0x12;
            usVal = AwtoDdcPortToVcp(SysSourceGetInputPort());
        }
        else if(pucRx[3] == 0x10)
        {
            usMax = 100;
            usVal = UserCommonAdjustRealValueToPercent(GET_OSD_BACKLIGHT(), _BACKLIGHT_MAX, _BACKLIGHT_MIN, _BACKLIGHT_CENTER);
        }
        else if(pucRx[3] == 0xD6)
        {
            usMax = 5;
            usVal = 1;                          // on (DPM D0)
        }
        else
        {
            pucTx[3] = 0x01;                    // unsupported VCP code
        }
        pucTx[1] = 0x88;
        pucTx[2] = 0x02;
        pucTx[4] = pucRx[3];
        pucTx[5] = 0x00;
        pucTx[6] = usMax >> 8;
        pucTx[7] = usMax & 0xFF;
        pucTx[8] = usVal >> 8;
        pucTx[9] = usVal & 0xFF;
        AwtoDdcReply(pucR, pucTx);
        return;
    }
    if((pucRx[2] == 0xF3) && (ucLen >= 6))      // capabilities: 51 83 F3 offH offL chk -> 6E 80|n+3 E3 offH offL data[n] chk
    {
        usVal = ((WORD)pucRx[3] << 8) | pucRx[4];
        usMax = sizeof(tAwtoDdcCaps) - 1;
        ucLen = (usVal >= usMax) ? 0 : ((usMax - usVal) > AWTO_DDC_CAP_CHUNK) ? AWTO_DDC_CAP_CHUNK : (BYTE)(usMax - usVal);
        pucTx[1] = 0x80 | (ucLen + 3);
        pucTx[2] = 0xE3;
        pucTx[3] = pucRx[3];
        pucTx[4] = pucRx[4];
        for(ucI = 0; ucI < ucLen; ucI++)
        {
            pucTx[5 + ucI] = tAwtoDdcCaps[usVal + ucI];
        }
        AwtoDdcReply(pucR, pucTx);
    }
}

static void AwtoDdcEngineInit(volatile __xdata BYTE *pucR, BYTE ucCh)
{
    pucR[AWTO_IIC_IRQ] = 0x00;                  // polled
    pucR[AWTO_IIC_CH_SEL] = (pucR[AWTO_IIC_CH_SEL] & ~(_BIT2 | _BIT1 | _BIT0)) | ucCh;
    pucR[AWTO_IIC_SLAVE] = AWTO_DDCCI_WR_ADDR;
    pucR[AWTO_IIC_CHANNEL] |= _BIT5;
    pucR[AWTO_IIC_STATUS] = 0x00;
    pucR[AWTO_IIC_STATUS2] &= ~(_BIT5 | _BIT4);
    pucR[AWTO_IIC_IRQ2] |= _BIT6;
}

#if((_AWTO_DBG_SWAP == _ON) && (_AWTO_DDCCI_ENGINES == 3))
void AwtoDdcciDebugLink(BYTE ucPort, BYTE ucOn)
{
    BYTE ucE;

    if((ucPort < _D1_INPUT_PORT) || (ucPort > _D3_INPUT_PORT))
    {
        return;
    }
    ucE = ucPort - _D1_INPUT_PORT;
    s_pucAwtoDdcN[ucE] = 0;
    AwtoDdcEngineInit((volatile __xdata BYTE *)tAwtoIicBase[ucE],
                      (ucOn != 0) ? AWTO_DBG_PARK_CH : tAwtoIicCh[ucE]);
}
#endif

void AwtoDdcciPoll(void)                        // AWTO_DDCCI_POLL(): only when an engine flags data or lost its set-up
{
    BYTE ucE;
    BYTE ucN;
    BYTE ucK;
    BYTE *pucRx;
    volatile __xdata BYTE *pucR;

    for(ucE = 0; ucE < _AWTO_DDCCI_ENGINES; ucE++)
    {
        pucR = (volatile __xdata BYTE *)tAwtoIicBase[ucE];
        pucRx = s_ppucAwtoDdcRx[ucE];
        ucN = s_pucAwtoDdcN[ucE];
        if(pucR[AWTO_IIC_SLAVE] != AWTO_DDCCI_WR_ADDR)        // first pass, or the SDK's ScalerMcuDdcciInitial parked IIC_1 at 0x3D
        {
#if(_AWTO_DDCCI_ENGINES == 3)
            AwtoDdcEngineInit(pucR, tAwtoIicCh[ucE]);
#else
#if(_AWTO_DBG_SWAP == _ON)
            AwtoDdcEngineInit(pucR, g_ucAwtoDdcciCh);       // #79: AwtoDbgSelectChannel owns the channel
#else
            AwtoDdcEngineInit(pucR, (_AWTO_DDCCI_FIXCH != 0) ? _AWTO_DDCCI_FIXCH : (_AWTO_DDCCI_PARK == 1) ? 0x07 : (AWTO_XB(AWTO_R_IIC_CH_SEL) & AWTO_F_IIC_CH_SEL_CH_SEL));     // MCU_FF22_IIC_CH_SEL      // follows the debug engine (#28)
#endif
#endif
            ucN = 0;
        }
        if((pucR[AWTO_IIC_STATUS] & _BIT1) != 0)
        {
            ucN = 0;
            pucRx[ucN++] = pucR[AWTO_IIC_SUB_IN];
            pucR[AWTO_IIC_STATUS] &= ~_BIT1;
        }
        if((pucR[AWTO_IIC_STATUS] & _BIT2) != 0)
        {
            for(ucK = 0; (ucK < 16) && ((pucR[AWTO_IIC_STATUS2] & _BIT1) == 0); ucK++)      // 16 = buffer depth (a missing engine reads junk)
            {
                if(ucN < AWTO_DDC_RX)
                {
                    pucRx[ucN] = pucR[AWTO_IIC_DATA_IN];
                }
                else
                {
                    ucK = pucR[AWTO_IIC_DATA_IN];
                    ucK = 16;                   // too long for us: drop the packet
                }
                ucN++;
            }
            if(ucN > AWTO_DDC_RX)
            {
                ucN = 0;
                pucR[AWTO_IIC_IRQ2] |= _BIT6;
            }
            else if((ucN >= 2) && (ucN == (pucRx[1] & 0x7F) + 3))
            {
                pucR[AWTO_IIC_IRQ2] |= _BIT6;   // request consumed; a reply (if any) reloads the buffer
#ifdef _AWTO_NEW_SETTINGS
                g_ucAwtoNvInDdc = 1;            // #151: a flash op in here would be counted (g_stAwtoNv.ucInDdc)
#endif
                AwtoDdcRequest(pucR, pucRx, ucN);
#ifdef _AWTO_NEW_SETTINGS
                g_ucAwtoNvInDdc = 0;
#endif
                ucN = 0;
            }
        }
        pucR[AWTO_IIC_STATUS] &= ~(_BIT4 | _BIT0);
        pucR[AWTO_IIC_STATUS2] &= ~(_BIT5 | _BIT4);
        s_pucAwtoDdcN[ucE] = ucN;
    }
}
#endif
