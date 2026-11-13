// #151 one store: the Realtek SDK EEPROM emulation (bank 15 pages 11-12) holds every stored setting.
// - Registry rows with an SDK field (flag sdk) read / write that field: set_sdk_get / set_sdk_put (one RAM copy).
// - Registry rows without one (aux block, settings.c set_aux_*): items AWTO_NV_AUX_ID.. in the same store.
// - Every SDK item save is deferred (UserCommonFlashSaveItem hook): item dirty; the flush gate writes it.
// Gate: stable >= AWTO_NV_STABLE_MS, DDC/CI idle >= AWTO_NV_DDC_IDLE_MS, AWTO_NV_SAVE_MS since the last change (none after a commit);
// forced after AWTO_NV_FORCE_MS; power-off / power-saving entry writes at once. Panel time never opens the gate.
#ifdef _AWTO_NEW_SETTINGS
__xdata StAwtoNv g_stAwtoNv;
__xdata BYTE g_ucAwtoNvDdc;
__xdata BYTE g_ucAwtoNvInDdc;
__xdata BYTE g_ucAwtoNvSwitch;
static __xdata BYTE s_ucNvOn;                       // 0 = boot: SDK saves write at once (version / recovery)
static __xdata BYTE s_ucNvFlushing;                 // our flush: the hook lets the save through
static __xdata BYTE s_ucNvCommit;                   // 1 = no debounce; 2 = and the card
static __xdata BYTE s_ucNvCommitWhy;                // AWTO_NV_WHY_CLOSE (menu / selector) or AWTO_NV_WHY_DDC (MCCS save)
static __xdata BYTE s_ucNvPort;
static __xdata WORD s_usNvPrev, s_usNvFirst, s_usNvLast;
static __xdata BYTE s_ucNvSelPort, s_ucNvSelScan, s_ucNvSelItem;   // the input as last chosen in the selector (stored)
static __xdata BYTE s_ucNvBriId, s_ucNvCtId;
static __xdata BYTE s_pucNvBri[4], s_pucNvCt[6];

extern BYTE __xdata *set_aux_buf(void);
extern BYTE set_aux_pack(void);
extern void set_aux_unpack(BYTE ucLen);
extern BYTE set_load_legacy(void);
extern void AwtoSaveCard(void);

static void AwtoNvMark(BYTE ucBit)
{
    if((ucBit != AWTO_NV_PANEL) && ((g_stAwtoNv.ucMask & ~AWTO_NV_PANEL) == 0))
    {
        s_usNvFirst = 0;
    }
    if(ucBit != AWTO_NV_PANEL)
    {
        s_usNvLast = 0;
    }
    g_stAwtoNv.ucMask |= ucBit;
}

// UserCommonFlashSaveItem entry (keil2sdcc sub): _TRUE = deferred (the caller returns _TRUE), _FALSE = write it now
bit AwtoNvDefer(BYTE ucId, BYTE *pucData)
{
    if((s_ucNvOn == 0) || (s_ucNvFlushing != 0))
    {
        return _FALSE;
    }
    if((ucId >= _FLASH_ITEMID_BRICON_SRC0_VGA) && (ucId <= _FLASH_ITEMID_BRICON_SRC4_DP))
    {
        if(((g_stAwtoNv.ucMask & AWTO_NV_BRI) != 0) && (s_ucNvBriId != ucId))
        {
            g_stAwtoNv.ucWhy = AWTO_NV_WHY_SNAP;    // another source's values wait: this one is written now (no nesting)
            AwtoSyncPush(AWTO_SYNC_EV_NV, AWTO_NV_LOG_ARG(AWTO_NV_WHY_SNAP), 0);
            AwtoSyncPush(AWTO_SYNC_EV_NV, AWTO_NV_LOG_SNAP2, 0);       // its second line
            return _FALSE;
        }
        s_ucNvBriId = ucId;
        memcpy(s_pucNvBri, pucData, 4);
        ucId = AWTO_NV_BRI;
    }
    else if((ucId >= _FLASH_ITEMID_COLORPROC0_9300) && (ucId <= _FLASH_ITEMID_COLORPROC5_USER))
    {
        if(((g_stAwtoNv.ucMask & AWTO_NV_CT) != 0) && (s_ucNvCtId != ucId))
        {
            g_stAwtoNv.ucWhy = AWTO_NV_WHY_SNAP;
            AwtoSyncPush(AWTO_SYNC_EV_NV, AWTO_NV_LOG_ARG(AWTO_NV_WHY_SNAP), 0);
            AwtoSyncPush(AWTO_SYNC_EV_NV, AWTO_NV_LOG_SNAP2, 0);       // its second line
            return _FALSE;
        }
        s_ucNvCtId = ucId;
        memcpy(s_pucNvCt, pucData, 6);
        ucId = AWTO_NV_CT;
    }
    else if(ucId == _FLASH_ITEMID_SYSTEM_DATA)
    {
        ucId = AWTO_NV_SYS;
    }
    else if((ucId == _FLASH_ITEMID_OSD_DATA_0) || (ucId == _FLASH_ITEMID_OSD_DATA_1))
    {
        ucId = AWTO_NV_OSD;
    }
    else if(ucId == _FLASH_ITEMID_SIXCOLOR_DATA)
    {
        ucId = AWTO_NV_SIX;
    }
    else if(ucId == _FLASH_ITEMID_PANEL_DATA)
    {
        ucId = AWTO_NV_PANEL;
    }
    else
    {
        return _FALSE;                              // no other item is saved at run time
    }
    g_stAwtoNv.usDefer++;
    AwtoNvMark(ucId);
    return _TRUE;
}

// Locals in XDATA (static): this runs at the deepest main-loop call path (SDK item save + page move under it), where
// every DATA byte counts against the IRAM overlay
static __xdata BYTE s_ucNvA, s_ucNvB, s_ucNvK, s_ucNvLen, s_ucNvMaskW;
static BYTE __xdata *__xdata s_pucNvAux;
static __xdata BYTE s_ucNvDone;                     // AWTO_NV_LOG_G_* groups whose items were programmed in this flush
static __xdata WORD s_usNvIw, s_usNvOps0, s_usNvEr0, s_usNvBy0, s_usNvT0;
static __xdata BYTE s_ucNvNone;                     // a commit with nothing dirty: its why, logged by the next service

static void AwtoNvGroup(BYTE ucG)                   // after a group's saves: did any item get programmed (SDK compare)
{
    if(g_stAwtoNv.usItemWr != s_usNvIw)
    {
        s_ucNvDone |= ucG;
        s_usNvIw = g_stAwtoNv.usItemWr;
    }
}

#define AWTO_NV_SAT(v, m)               (((v) > (m)) ? (m) : (v))

// Two sync lines per flush, after it: why, then (fmt nvw) what was written, or "nothing changed"
static void AwtoNvLog(BYTE ucWhy)
{
    s_usNvT0 = (WORD)AwtoMs() - s_usNvT0;
    s_usNvEr0 = g_stAwtoNv.usErase - s_usNvEr0;
    s_usNvOps0 = g_stAwtoNv.usOps - s_usNvOps0 - s_usNvEr0;    // programs
    s_usNvBy0 = g_stAwtoNv.usBytes - s_usNvBy0;
    AwtoSyncPush(AWTO_SYNC_EV_NV, AWTO_NV_LOG_ARG(ucWhy), 0);                  // line 1: why (Dan: two lines)
    AwtoSyncPush(AWTO_SYNC_EV_NV, AWTO_NV_LOG_RESULT, ((DWORD)s_ucNvDone << 27) |
                 ((DWORD)AWTO_NV_SAT(s_usNvEr0, AWTO_NV_LOG_ER_MAX) << 25) | ((DWORD)AWTO_NV_SAT(s_usNvOps0, AWTO_NV_LOG_PR_MAX) << 19) |
                 ((DWORD)AWTO_NV_SAT(s_usNvBy0, AWTO_NV_LOG_B_MAX) << 9) | AWTO_NV_SAT(s_usNvT0, AWTO_NV_LOG_MS_MAX));
}

static void AwtoNvWrite(BYTE ucWhy)
{
    s_ucNvMaskW = g_stAwtoNv.ucMask;
    g_stAwtoNv.ucMask = 0;
    g_stAwtoNv.ucWhy = ucWhy;
    g_stAwtoNv.usFlush++;
    AWTO_NV_IN_DDC();
    s_usNvT0 = (WORD)AwtoMs();
    s_usNvIw = g_stAwtoNv.usItemWr;
    s_usNvOps0 = g_stAwtoNv.usOps;
    s_usNvEr0 = g_stAwtoNv.usErase;
    s_usNvBy0 = g_stAwtoNv.usBytes;
    s_ucNvDone = 0;
    s_ucNvFlushing = 1;
    if((s_ucNvMaskW & AWTO_NV_SYS) != 0)                 // the input part as chosen in the selector, not the live one (KVM, search)
    {
        s_ucNvA = UserCommonNVRamGetSystemData(_SEARCH_PORT);
        s_ucNvB = UserCommonNVRamGetSystemData(_SOURCE_SCAN_TYPE);
        UserCommonNVRamSetSystemData(_SEARCH_PORT, s_ucNvSelPort);
        UserCommonNVRamSetSystemData(_SOURCE_SCAN_TYPE, s_ucNvSelScan);
        UserCommonNVRamSaveSystemData();
        UserCommonNVRamSetSystemData(_SEARCH_PORT, s_ucNvA);
        UserCommonNVRamSetSystemData(_SOURCE_SCAN_TYPE, s_ucNvB);
        AwtoNvGroup(AWTO_NV_LOG_G_SYS);
    }
    if((s_ucNvMaskW & AWTO_NV_OSD) != 0)
    {
        s_ucNvA = GET_OSD_INPUT_PORT_OSD_ITEM();
        SET_OSD_INPUT_PORT_OSD_ITEM(s_ucNvSelItem);
        RTDNVRamSaveOSDData();
        SET_OSD_INPUT_PORT_OSD_ITEM(s_ucNvA);
        AwtoNvGroup(AWTO_NV_LOG_G_OSD);
    }
    if((s_ucNvMaskW & AWTO_NV_BRI) != 0)
    {
        UserCommonFlashSaveItem((EnumFlashItemIDType)s_ucNvBriId, s_pucNvBri, 4);
    }
    if((s_ucNvMaskW & AWTO_NV_CT) != 0)
    {
        UserCommonFlashSaveItem((EnumFlashItemIDType)s_ucNvCtId, s_pucNvCt, 6);
    }
    if((s_ucNvMaskW & AWTO_NV_SIX) != 0)
    {
        RTDNVRamSaveSixColorData();
    }
    AwtoNvGroup(AWTO_NV_LOG_G_COLOUR);
    RTDNVRamSavePanelUsedTimeData();                // rides along with every flush (the SDK skips it when unchanged)
    AwtoNvGroup(AWTO_NV_LOG_G_PANEL);
    if((s_ucNvMaskW & AWTO_NV_AUX) != 0)
    {
        s_ucNvLen = set_aux_pack();
        s_pucNvAux = set_aux_buf();                 // AWTO_SET_AUX_MAX B (#165): the last item is padded in pData
        for(s_ucNvK = 0; s_ucNvK < AWTO_NV_AUX_ITEMS; s_ucNvK++)
        {
            s_ucNvA = s_ucNvK * 14;
            for(s_ucNvB = 0; s_ucNvB < 14; s_ucNvB++)
            {
                pData[s_ucNvB] = ((s_ucNvA + s_ucNvB) < s_ucNvLen) ? s_pucNvAux[s_ucNvA + s_ucNvB] : 0;
            }
            UserCommonFlashSaveItem((EnumFlashItemIDType)(AWTO_NV_AUX_ID + s_ucNvK), pData, 14);
        }
        AwtoNvGroup(AWTO_NV_LOG_G_AUX);
    }
    s_ucNvFlushing = 0;
    AwtoNvLog(ucWhy);
}

void AwtoNvTestWrite(void)                          // test cmd 0x3D: a real item write (flash halt) through the store
{
    set_put(AWTO_SET_KVM_PREFILL, (set_get(AWTO_SET_KVM_PREFILL) == 0), 0);
    AwtoNvWrite(AWTO_NV_WHY_TEST);
}

void AwtoNvFlush(void)                              // UserInterfacePowerSwitch: power off, power saving (panel off)
{
    AwtoNvWrite(AWTO_NV_WHY_POWER);
}

static __xdata WORD s_usNvEl;
#define AWTO_NV_AGE(a)                  { a = ((a) > 60000 - s_usNvEl) ? 60000 : ((a) + s_usNvEl); }   // saturating ms

// AwtoSetLoop (<= AWTO_SET_LOOP_MS apart): gate inputs, then a write when it opens
static void AwtoNvService(void)
{
    s_usNvEl = set_now_ms() - s_usNvPrev;
    s_usNvPrev += s_usNvEl;
    if(s_usNvEl > AWTO_NV_EL_MAX_MS)
    {
        s_usNvEl = AWTO_NV_EL_MAX_MS;               // a long gap (boot, clock switch) never ages the gate past what was seen
    }
    if((SysModeGetModeState() != _MODE_STATUS_ACTIVE) || (SysPowerGetPowerStatus() != _POWER_STATUS_NORMAL) ||
       (SysSourceGetInputPort() != s_ucNvPort) || (g_ucAwtoNvSwitch != 0))
    {
        g_stAwtoNv.usStable = 0;
    }
    else
    {
        AWTO_NV_AGE(g_stAwtoNv.usStable);
    }
    if(g_ucAwtoNvDdc != 0)
    {
        g_stAwtoNv.usDdcIdle = 0;
    }
    else
    {
        AWTO_NV_AGE(g_stAwtoNv.usDdcIdle);
    }
    s_ucNvPort = SysSourceGetInputPort();
    g_ucAwtoNvSwitch = 0;
    g_ucAwtoNvDdc = 0;
    if(s_ucNvNone != 0)                             // a commit found nothing dirty: its line (never dropped)
    {
        s_usNvT0 = (WORD)AwtoMs();
        s_usNvOps0 = g_stAwtoNv.usOps;
        s_usNvEr0 = g_stAwtoNv.usErase;
        s_usNvBy0 = g_stAwtoNv.usBytes;
        s_ucNvDone = 0;
        AwtoNvLog(s_ucNvNone);
        s_ucNvNone = 0;
    }
    if((g_stAwtoNv.ucMask & ~AWTO_NV_PANEL) == 0)
    {
        s_ucNvCommit = 0;
        return;
    }
    AWTO_NV_AGE(s_usNvFirst);
    AWTO_NV_AGE(s_usNvLast);
    if((g_stAwtoNv.usStable >= AWTO_NV_STABLE_MS) && (g_stAwtoNv.usDdcIdle >= AWTO_NV_DDC_IDLE_MS) && ((s_ucNvCommit != 0) || (s_usNvLast >= AWTO_NV_SAVE_MS)))
    {
        if((s_ucNvCommit == 2) && (GET_OSD_STATE() == _MENU_NONE) && (g_ucAwtoMenuOn == 0))
        {
            AwtoSaveCard();                         // "Saving to memory" while it writes
        }
        AwtoNvWrite((s_ucNvCommit != 0) ? s_ucNvCommitWhy : AWTO_NV_WHY_GATE);
        s_ucNvCommit = 0;
    }
    else if(s_usNvFirst >= AWTO_NV_FORCE_MS)
    {
        AwtoNvWrite(AWTO_NV_WHY_FORCED);
        s_ucNvCommit = 0;
    }
}

void set_nv_dirty(void)
{
    AwtoNvMark(AWTO_NV_AUX);
}

void set_nv_commit(BYTE ucShow)                    // menu close (1), MCCS 0x0C (0): flags only, the gate writes
{
    if((g_stAwtoNv.ucMask & ~AWTO_NV_PANEL) == 0)
    {
        s_ucNvNone = (ucShow != 0) ? AWTO_NV_WHY_CLOSE : AWTO_NV_WHY_DDC;   // "nothing changed" at the next service
        return;
    }
    if((ucShow != 0) || (s_ucNvCommit == 0))
    {
        s_ucNvCommitWhy = (ucShow != 0) ? AWTO_NV_WHY_CLOSE : AWTO_NV_WHY_DDC;
    }
    if((ucShow != 0) && (SysPowerGetPowerStatus() == _POWER_STATUS_NORMAL))
    {
        s_ucNvCommit = 2;
    }
    else if(s_ucNvCommit == 0)
    {
        s_ucNvCommit = 1;
    }
}

void AwtoNvCommitSel(void)                          // the selector took a choice: this input is the stored one
{
    s_ucNvSelPort = UserCommonNVRamGetSystemData(_SEARCH_PORT);
    s_ucNvSelScan = UserCommonNVRamGetSystemData(_SOURCE_SCAN_TYPE);
    s_ucNvSelItem = GET_OSD_INPUT_PORT_OSD_ITEM();
    AwtoNvMark(AWTO_NV_SYS);
    AwtoNvMark(AWTO_NV_OSD);
    set_nv_commit(1);
}

// boot (AwtoSetInit, after RTDNVRamStartup): aux block from its items, else the old registry record once
static void AwtoNvLoad(void)
{
    BYTE ucK;
    _Bool bOk = _TRUE;
    BYTE __xdata *pucAux = set_aux_buf();

    for(ucK = 0; (ucK < AWTO_NV_AUX_ITEMS) && (bOk == _TRUE); ucK++)
    {
        bOk = UserCommonFlashLoadItem((EnumFlashItemIDType)(AWTO_NV_AUX_ID + ucK), pData, 14);
        memcpy(pucAux + ucK * 14, pData, ((AWTO_SET_AUX_MAX - ucK * 14) < 14) ? (AWTO_SET_AUX_MAX - ucK * 14) : 14);   // buffer = AWTO_SET_AUX_MAX B (#165)
    }
    s_ucNvSelPort = UserCommonNVRamGetSystemData(_SEARCH_PORT);
    s_ucNvSelScan = UserCommonNVRamGetSystemData(_SOURCE_SCAN_TYPE);
    s_ucNvSelItem = GET_OSD_INPUT_PORT_OSD_ITEM();
    s_ucNvOn = 1;                                   // from here SDK saves are deferred
    if(bOk == _TRUE)
    {
        set_aux_unpack(AWTO_SET_AUX_MAX);
    }
    else
    {
        set_load_legacy();                          // first boot of this layout: the values move into the SDK store
        AwtoNvMark(AWTO_NV_AUX);
    }
    g_stAwtoNv.ucMagic = 'N';
    s_usNvPrev = set_now_ms();
}

//---- registry rows on SDK fields: registry units <-> the field ----
static int AwtoPct(WORD usReal, WORD usMax, WORD usMin, WORD usCenter)   // exact inverse of the SDK percent -> value
{
    BYTE ucP = UserCommonAdjustRealValueToPercent(usReal, usMax, usMin, usCenter);

    if((ucP < 100) && (UserCommonAdjustPercentToRealValue(ucP + 1, usMax, usMin, usCenter) == usReal))
    {
        ucP++;
    }
    else if((ucP > 0) && (UserCommonAdjustPercentToRealValue(ucP, usMax, usMin, usCenter) != usReal) &&
            (UserCommonAdjustPercentToRealValue(ucP - 1, usMax, usMin, usCenter) == usReal))
    {
        ucP--;
    }
    return ucP;
}

int set_sdk_get(BYTE ucId)
{
    switch(ucId)
    {
        case AWTO_SET_BRIGHTNESS:       return AwtoPct(GET_OSD_BACKLIGHT(), _BACKLIGHT_MAX, _BACKLIGHT_MIN, _BACKLIGHT_CENTER);
#if(_BRIGHTNESS_SUPPORT == _ON)
        case AWTO_SET_BLACK_LEVEL:      return AwtoPct(GET_OSD_BRIGHTNESS(), _BRIGHTNESS_MAX, _BRIGHTNESS_MIN, _BRIGHTNESS_CENTER);
#endif
#if(_CONTRAST_SUPPORT == _ON)
        case AWTO_SET_CONTRAST:         return AwtoPct(GET_OSD_CONTRAST(), _CONTRAST_MAX, _CONTRAST_MIN, _CONTRAST_CENTER);
#endif
        case AWTO_SET_SHARPNESS:        return g_stOSDUserData.b3Sharpness;
        case AWTO_SET_GAMMA:            return g_stOSDUserData.b3Gamma;
        case AWTO_SET_COLOUR_TEMP:      return g_stOSDUserData.b4ColorTempType;
        case AWTO_SET_USER_RED:         return GET_COLOR_TEMP_TYPE_USER_R();
        case AWTO_SET_USER_GREEN:       return GET_COLOR_TEMP_TYPE_USER_G();
        case AWTO_SET_USER_BLUE:        return GET_COLOR_TEMP_TYPE_USER_B();
        case AWTO_SET_COLOUR_EFFECT:    return g_stOSDUserData.b4ColorEffect;
        case AWTO_SET_PCM:              return g_stOSDUserData.b3PCMStatus;
        case AWTO_SET_HUE:              return ((WORD)g_stOSDUserData.ucHue * 100 + 127) / 255;
        case AWTO_SET_SATURATION:       return ((WORD)g_stOSDUserData.ucSaturation * 100 + 127) / 255;
        case AWTO_SET_UNIFORMITY:       return g_stOSDUserData.b1PanelUniformity;
        case AWTO_SET_SA_RED_HUE:       return g_stSixColorData.ucSixColorHueR;
        case AWTO_SET_SA_RED_SAT:       return g_stSixColorData.ucSixColorSaturationR;
        case AWTO_SET_SA_YELLOW_HUE:    return g_stSixColorData.ucSixColorHueY;
        case AWTO_SET_SA_YELLOW_SAT:    return g_stSixColorData.ucSixColorSaturationY;
        case AWTO_SET_SA_GREEN_HUE:     return g_stSixColorData.ucSixColorHueG;
        case AWTO_SET_SA_GREEN_SAT:     return g_stSixColorData.ucSixColorSaturationG;
        case AWTO_SET_SA_CYAN_HUE:      return g_stSixColorData.ucSixColorHueC;
        case AWTO_SET_SA_CYAN_SAT:      return g_stSixColorData.ucSixColorSaturationC;
        case AWTO_SET_SA_BLUE_HUE:      return g_stSixColorData.ucSixColorHueB;
        case AWTO_SET_SA_BLUE_SAT:      return g_stSixColorData.ucSixColorSaturationB;
        case AWTO_SET_SA_MAGENTA_HUE:   return g_stSixColorData.ucSixColorHueM;
        case AWTO_SET_SA_MAGENTA_SAT:   return g_stSixColorData.ucSixColorSaturationM;
        case AWTO_SET_ASPECT:           return g_stOSDUserData.b3AspectRatio;
        case AWTO_SET_OVERSCAN:         return g_stOSDUserData.b1OverScan;
        case AWTO_SET_LATENCY:          return g_stOSDUserData.b2LatencyStatus;
        case AWTO_SET_DP_VERSION:       return g_stOSDUserData.b2OsdDpD1PortVersion;
        case AWTO_SET_DP_EDID:          return UserCommonNVRamGetSystemData(_EDID_D1_SELECT);
        case AWTO_SET_COLOUR_FORMAT:    return g_stOSDUserData.b3DVIRGBYUV;
        case AWTO_SET_CLONE:            return g_stOSDUserData.b1CloneMode;
        case AWTO_SET_DDCCI:            return g_stOSDUserData.b1DDCCIStatus;
        case AWTO_SET_OSD_TIMEOUT:      return g_stOSDUserData.ucOsdTimeout;
        case AWTO_SET_OSD_HPOS:         return g_stOSDUserData.ucOsdHPos;
        case AWTO_SET_OSD_VPOS:         return g_stOSDUserData.ucOsdVPos;
        case AWTO_SET_OSD_SCALE:        return g_stOSDUserData.b1OsdDoubleSize;
        case AWTO_SET_OSD_TRANSPARENCY: return ((WORD)g_stOSDUserData.ucTransparency * 100 + 127) / 255;
        case AWTO_SET_LANGUAGE:         return g_stOSDUserData.b4Language;
        case AWTO_SET_OSD_ROTATE:       return g_stOSDUserData.b2OsdRotate;
        case AWTO_SET_DEBUG_MSGS:       return g_stOSDUserData.b1AwtoMsgOn;
        case AWTO_SET_VOLUME:           return g_stOSDUserData.ucVolume;
        case AWTO_SET_MUTE:             return g_stOSDUserData.b1VolumeMute;
        case AWTO_SET_AUDIO_STANDALONE: return g_stOSDUserData.b1AudioStandAloneStatus;
        case AWTO_SET_AUDIO_SOURCE:     return g_stOSDUserData.b1AudioSourceStatus;
        case AWTO_SET_POWER_ON:         return UserCommonNVRamGetSystemData(_MONITOR_POWER_STATUS);
        case AWTO_SET_DP_LANES:         return UserCommonNVRamGetSystemData(_DP_D1_LANES);
        case AWTO_SET_DP_IRQ_10US:      return UserCommonNVRamGetSystemData(_DP_IRQ_TIME);
        case AWTO_SET_SSC:              return UserCommonNVRamGetSystemData(_SSC);
        case AWTO_SET_PANEL_HOURS:      return (GET_PANEL_TIME_HOUR() > 32767) ? 32767 : (int)GET_PANEL_TIME_HOUR();
        case AWTO_SET_PANEL_MIN:        return GET_PANEL_TIME_MIN();
        default:                        return 0;
    }
}

static BYTE AwtoTo255(int iV)
{
    return AWTO_PCT_TO_255(iV);
}

// item dirty without calling an SDK save (keeps the SDK save + page move off the DDC/CI handler's static call path)
static void AwtoNvSnap(BYTE ucBit, BYTE ucItem, BYTE *pucData, BYTE ucLen)
{
    if(ucBit == AWTO_NV_BRI)
    {
        s_ucNvBriId = ucItem;                       // a value of another source still waiting is replaced (rare)
        memcpy(s_pucNvBri, pucData, ucLen);
    }
    else if(ucBit == AWTO_NV_CT)
    {
        s_ucNvCtId = ucItem;
        memcpy(s_pucNvCt, pucData, ucLen);
    }
    AwtoNvMark(ucBit);
}

void set_sdk_put(BYTE ucId, int iV)                // the field, then its item dirty (the gate writes it)
{
    BYTE ucV = (BYTE)iV;

    switch(ucId)
    {
        case AWTO_SET_BRIGHTNESS:       SET_OSD_BACKLIGHT(UserCommonAdjustPercentToRealValue(ucV, _BACKLIGHT_MAX, _BACKLIGHT_MIN, _BACKLIGHT_CENTER)); break;
#if(_BRIGHTNESS_SUPPORT == _ON)
        case AWTO_SET_BLACK_LEVEL:      SET_OSD_BRIGHTNESS(UserCommonAdjustPercentToRealValue(ucV, _BRIGHTNESS_MAX, _BRIGHTNESS_MIN, _BRIGHTNESS_CENTER)); AwtoNvSnap(AWTO_NV_BRI, _FLASH_ITEMID_BRICON_SRC0_VGA + SysSourceGetSourceType(), (BYTE *)&g_stBriConData, 4); return;
#endif
#if(_CONTRAST_SUPPORT == _ON)
        case AWTO_SET_CONTRAST:         SET_OSD_CONTRAST(UserCommonAdjustPercentToRealValue(ucV, _CONTRAST_MAX, _CONTRAST_MIN, _CONTRAST_CENTER)); AwtoNvSnap(AWTO_NV_BRI, _FLASH_ITEMID_BRICON_SRC0_VGA + SysSourceGetSourceType(), (BYTE *)&g_stBriConData, 4); return;
#endif
        case AWTO_SET_SHARPNESS:        g_stOSDUserData.b3Sharpness = ucV; break;
        case AWTO_SET_GAMMA:            g_stOSDUserData.b3Gamma = ucV; break;
        case AWTO_SET_COLOUR_TEMP:      g_stOSDUserData.b4ColorTempType = ucV; break;
        case AWTO_SET_USER_RED:
        case AWTO_SET_USER_GREEN:
        case AWTO_SET_USER_BLUE:
            if(GET_COLOR_TEMP_TYPE() != _CT_USER)
            {
                return;                             // the gains in RAM are another preset's: User RGB edits only at User
            }
            if(ucId == AWTO_SET_USER_RED)
            {
                SET_COLOR_TEMP_TYPE_USER_R(iV);
            }
            else if(ucId == AWTO_SET_USER_GREEN)
            {
                SET_COLOR_TEMP_TYPE_USER_G(iV);
            }
            else
            {
                SET_COLOR_TEMP_TYPE_USER_B(iV);
            }
            AwtoNvSnap(AWTO_NV_CT, _FLASH_ITEMID_COLORPROC0_9300 + _CT_USER, (BYTE *)&g_stColorProcData, 6);
            return;
        case AWTO_SET_COLOUR_EFFECT:    g_stOSDUserData.b4ColorEffect = ucV; break;
        case AWTO_SET_PCM:              g_stOSDUserData.b3PCMStatus = ucV; break;
        case AWTO_SET_HUE:              g_stOSDUserData.ucHue = AwtoTo255(iV); break;
        case AWTO_SET_SATURATION:       g_stOSDUserData.ucSaturation = AwtoTo255(iV); break;
        case AWTO_SET_UNIFORMITY:       g_stOSDUserData.b1PanelUniformity = ucV; break;
        case AWTO_SET_SA_RED_HUE:       g_stSixColorData.ucSixColorHueR = ucV; AwtoNvMark(AWTO_NV_SIX); return;
        case AWTO_SET_SA_RED_SAT:       g_stSixColorData.ucSixColorSaturationR = ucV; AwtoNvMark(AWTO_NV_SIX); return;
        case AWTO_SET_SA_YELLOW_HUE:    g_stSixColorData.ucSixColorHueY = ucV; AwtoNvMark(AWTO_NV_SIX); return;
        case AWTO_SET_SA_YELLOW_SAT:    g_stSixColorData.ucSixColorSaturationY = ucV; AwtoNvMark(AWTO_NV_SIX); return;
        case AWTO_SET_SA_GREEN_HUE:     g_stSixColorData.ucSixColorHueG = ucV; AwtoNvMark(AWTO_NV_SIX); return;
        case AWTO_SET_SA_GREEN_SAT:     g_stSixColorData.ucSixColorSaturationG = ucV; AwtoNvMark(AWTO_NV_SIX); return;
        case AWTO_SET_SA_CYAN_HUE:      g_stSixColorData.ucSixColorHueC = ucV; AwtoNvMark(AWTO_NV_SIX); return;
        case AWTO_SET_SA_CYAN_SAT:      g_stSixColorData.ucSixColorSaturationC = ucV; AwtoNvMark(AWTO_NV_SIX); return;
        case AWTO_SET_SA_BLUE_HUE:      g_stSixColorData.ucSixColorHueB = ucV; AwtoNvMark(AWTO_NV_SIX); return;
        case AWTO_SET_SA_BLUE_SAT:      g_stSixColorData.ucSixColorSaturationB = ucV; AwtoNvMark(AWTO_NV_SIX); return;
        case AWTO_SET_SA_MAGENTA_HUE:   g_stSixColorData.ucSixColorHueM = ucV; AwtoNvMark(AWTO_NV_SIX); return;
        case AWTO_SET_SA_MAGENTA_SAT:   g_stSixColorData.ucSixColorSaturationM = ucV; AwtoNvMark(AWTO_NV_SIX); return;
        case AWTO_SET_ASPECT:           g_stOSDUserData.b3AspectRatio = ucV; break;
        case AWTO_SET_OVERSCAN:         g_stOSDUserData.b1OverScan = ucV; break;
        case AWTO_SET_LATENCY:          g_stOSDUserData.b2LatencyStatus = ucV; break;
        case AWTO_SET_DP_VERSION:       g_stOSDUserData.b2OsdDpD1PortVersion = ucV; break;
        case AWTO_SET_COLOUR_FORMAT:    g_stOSDUserData.b3DVIRGBYUV = ucV; g_stOSDUserData.b3VGARGBYUV = ucV; break;
        case AWTO_SET_CLONE:            g_stOSDUserData.b1CloneMode = ucV; break;
        case AWTO_SET_DDCCI:            g_stOSDUserData.b1DDCCIStatus = ucV; break;
        case AWTO_SET_OSD_TIMEOUT:      g_stOSDUserData.ucOsdTimeout = ucV; break;
        case AWTO_SET_OSD_HPOS:         g_stOSDUserData.ucOsdHPos = ucV; break;
        case AWTO_SET_OSD_VPOS:         g_stOSDUserData.ucOsdVPos = ucV; break;
        case AWTO_SET_OSD_SCALE:        g_stOSDUserData.b1OsdDoubleSize = ucV; break;
        case AWTO_SET_OSD_TRANSPARENCY: g_stOSDUserData.ucTransparency = AwtoTo255(iV); break;
        case AWTO_SET_LANGUAGE:         g_stOSDUserData.b4Language = ucV; break;
        case AWTO_SET_OSD_ROTATE:       g_stOSDUserData.b2OsdRotate = ucV; break;
        case AWTO_SET_DEBUG_MSGS:       g_stOSDUserData.b1AwtoMsgOn = ucV; break;
        case AWTO_SET_VOLUME:           g_stOSDUserData.ucVolume = ucV; break;
        case AWTO_SET_MUTE:             g_stOSDUserData.b1VolumeMute = ucV; break;
        case AWTO_SET_AUDIO_STANDALONE: g_stOSDUserData.b1AudioStandAloneStatus = ucV; break;
        case AWTO_SET_AUDIO_SOURCE:     g_stOSDUserData.b1AudioSourceStatus = ucV; break;
        case AWTO_SET_DP_EDID:          UserCommonNVRamSetSystemData(_EDID_D1_SELECT, ucV); AwtoNvMark(AWTO_NV_SYS); return;
        case AWTO_SET_POWER_ON:         UserCommonNVRamSetSystemData(_MONITOR_POWER_STATUS, ucV); AwtoNvMark(AWTO_NV_SYS); return;
        case AWTO_SET_DP_LANES:         UserCommonNVRamSetSystemData(_DP_D1_LANES, ucV); AwtoNvMark(AWTO_NV_SYS); return;
        case AWTO_SET_DP_IRQ_10US:      UserCommonNVRamSetSystemData(_DP_IRQ_TIME, ucV); AwtoNvMark(AWTO_NV_SYS); return;
        case AWTO_SET_SSC:              UserCommonNVRamSetSystemData(_SSC, ucV); AwtoNvMark(AWTO_NV_SYS); return;
        case AWTO_SET_PANEL_HOURS:      SET_PANEL_TIME_HOUR((WORD)iV); AwtoNvMark(AWTO_NV_PANEL); return;
        case AWTO_SET_PANEL_MIN:        SET_PANEL_TIME_MIN(ucV); AwtoNvMark(AWTO_NV_PANEL); return;
        default:                        return;
    }
    AwtoNvMark(AWTO_NV_OSD);                        // the OSD user-data rows
}

void set_ap_sdk_sys(BYTE ucId, int iV)             // stored SDK system data: read by its owner (most at boot)
{
    ucId = ucId;
    iV = iV;
}
#endif
