// awto speaker amp pins (awto-ddc#94, docs/audio.md): the one owner of P7.4 (amp enable) and P7.3 (static low), as the Dahua fw:
// AC on P7.4 = 0, P7.3 = 0 AWTO_AUDIO_AUX_MS later (5:d2a0); P7.4 = !mute when the speaker output is on (1:ea99) [fw]
// Callers: PCB_ON_REGION_GPIO_SETTING_POWER_AC_ON (boot), PCB_AMP_MUTE (SysAudioMuteProc), main loop (poll).
#if(_AUDIO_SUPPORT == _ON)
__xdata DWORD g_ulAwtoAudioT0;                  // AwtoMs() at the first poll after AC on; 0 = not stamped
__xdata BYTE g_ucAwtoAudioAux;                  // 1 = P7.3 driven low

void AwtoAudioAmpBoot(void)
{
    bAMP_EN = 0;
    g_ulAwtoAudioT0 = 0;
    g_ucAwtoAudioAux = 0;
}

void AwtoAudioAmp(bit bMute)
{
#if(AWTO_AUDIO_AMP_USED)
    bAMP_EN = (bMute == _ON) ? 0 : 1;
    AwtoSyncPush(AWTO_SYNC_EV_AUDIO, (bMute == _ON) ? AWTO_AUDIO_EV_AMP_OFF : AWTO_AUDIO_EV_AMP_ON, 0);
#else
    bAMP_EN = 0;
    AwtoSyncPush(AWTO_SYNC_EV_AUDIO, (bMute == _ON) ? AWTO_AUDIO_EV_AMP_OFF : AWTO_AUDIO_EV_AMP_HP, 0);
#endif
}

void AwtoAudioPoll(void)
{
    if(g_ucAwtoAudioAux != 0)
    {
        return;
    }
    if(g_ulAwtoAudioT0 == 0)
    {
        g_ulAwtoAudioT0 = AwtoMs() | 1;         // | 1: 0 means not stamped
        AwtoSyncPush(AWTO_SYNC_EV_AUDIO, AWTO_AUDIO_EV_AMP_OFF, 0);
        return;
    }
    if((AwtoMs() - g_ulAwtoAudioT0) >= AWTO_AUDIO_AUX_MS)
    {
        bAMP_AUX = 0;
        g_ucAwtoAudioAux = 1;
        AwtoSyncPush(AWTO_SYNC_EV_AUDIO, AWTO_AUDIO_EV_AUX_LOW, 0);
    }
}
#endif

#ifdef _AWTO_AUDIO_TEST
// #94 ear tests (test build): VCP 0x63 = AWTO_AUDIO_TEST_START + n sets up step n, AWTO_AUDIO_TEST_DONE + n restores;
// one console line each (sync.tsv E5). Outputs by the per-output mute bits (the SDK only watches the power bits).
#define AWTO_AUDIO_OUT_ON                       AWTO_F_REG_AOUT_CTRL_REG_AOUT_NORM     // normal mode, L/R unmuted (HPOUT_CTRL: same bits)
#define AWTO_AUDIO_OUT_MUTED                    (AWTO_F_REG_AOUT_CTRL_REG_MUTE_AOUT_L | AWTO_F_REG_AOUT_CTRL_REG_MUTE_AOUT_R | AWTO_AUDIO_OUT_ON)
#define AWTO_AUDIO_GAIN_DAHUA_50                0x098C  // Dahua fw DVC gain at its default volume 50 (sim trace, -16.5 dB) [fw]
#define AWTO_AUDIO_GAIN_M6DB                    0x1FFF  // -6 dB
static __code BYTE tAwtoAudioTestAout[AWTO_AUDIO_TEST_STEPS] = {AWTO_AUDIO_OUT_ON, AWTO_AUDIO_OUT_MUTED, AWTO_AUDIO_OUT_MUTED, AWTO_AUDIO_OUT_ON, AWTO_AUDIO_OUT_ON, AWTO_AUDIO_OUT_ON, AWTO_AUDIO_OUT_ON};
static __code BYTE tAwtoAudioTestHpout[AWTO_AUDIO_TEST_STEPS] = {AWTO_AUDIO_OUT_ON, AWTO_AUDIO_OUT_ON, AWTO_AUDIO_OUT_ON, AWTO_AUDIO_OUT_MUTED, AWTO_AUDIO_OUT_MUTED, AWTO_AUDIO_OUT_ON, AWTO_AUDIO_OUT_ON};
static __code BYTE tAwtoAudioTestAmp[AWTO_AUDIO_TEST_STEPS] = {1, 1, 0, 1, 0, 1, 1};
static __code WORD tAwtoAudioTestGain[AWTO_AUDIO_TEST_STEPS] = {0, 0, 0, 0, 0, AWTO_AUDIO_GAIN_DAHUA_50, AWTO_AUDIO_GAIN_M6DB};   // 0 = user volume

void AwtoAudioTestStep(BYTE ucV)
{
    BYTE ucN = (ucV & 0x0F) - 1;

    if((ucN >= AWTO_AUDIO_TEST_STEPS) || (((ucV & 0xF0) != AWTO_AUDIO_TEST_START) && ((ucV & 0xF0) != AWTO_AUDIO_TEST_DONE)))
    {
        return;
    }
    if((ucV & 0xF0) == AWTO_AUDIO_TEST_START)
    {
        AwtoSyncPush(AWTO_SYNC_EV_AUDIO, ucV, 0);       // "audio test n/7: <set-up>" before the sound
        ScalerSetByte(AWTO_R_REG_AOUT_CTRL, tAwtoAudioTestAout[ucN]);
        ScalerSetByte(AWTO_R_REG_HPOUT_CTRL, tAwtoAudioTestHpout[ucN]);
        bAMP_EN = tAwtoAudioTestAmp[ucN];
        ScalerAudioDigitalAdjustVolume((tAwtoAudioTestGain[ucN] != 0) ? tAwtoAudioTestGain[ucN] : UserInterfaceGetAudioVolume());
        return;
    }
    ScalerSetByte(AWTO_R_REG_AOUT_CTRL, AWTO_AUDIO_OUT_ON);
    ScalerSetByte(AWTO_R_REG_HPOUT_CTRL, AWTO_AUDIO_OUT_ON);
    bAMP_EN = 1;
    ScalerAudioDigitalAdjustVolume(UserInterfaceGetAudioVolume());
    AwtoSyncPush(AWTO_SYNC_EV_AUDIO, ucV, 0);           // "audio test n/7 done"
}
#endif
