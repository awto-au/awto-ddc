// awto speaker amp pins (awto-ddc#94, docs/audio.md): the one owner of P7.4 (amp enable) and P7.3 (static low), as the Dahua fw:
// AC on P7.4 = 0, P7.3 = 0 AWTO_AUDIO_AUX_MS later (5:d2a0); P7.4 = !mute (1:ea99, speaker path) [fw]; speaker out only (#94)
// Callers: PCB_ON_REGION_GPIO_SETTING_POWER_AC_ON (boot), PCB_AMP_MUTE (SysAudioMuteProc), main loop (poll), VCP 0x63 (ear tests).
#if(_AUDIO_SUPPORT == _ON)
__xdata DWORD g_ulAwtoAudioT0;                  // AwtoMs() at the first poll after AC on; 0 = not stamped
__xdata BYTE g_ucAwtoAudioAux;                  // 1 = P7.3 driven low
__xdata BYTE g_ucAwtoAudioTestN;                // ear-test step 1..AWTO_AUDIO_TEST_STEPS in force, 0 = none (RAM only)

// #94 ear-test steps (dev.py sound-test, VCP 0x63): speaker out only; amp P7.4 and DVC gain per step (0 = user volume).
// Held until the step's DONE: the SDK unmute (AwtoAudioAmp) and volume mapping (AwtoAudioGain) apply them too.
static __code BYTE tAwtoAudioTestAmp[AWTO_AUDIO_TEST_STEPS] = {1, 0, 1, 1, 1, 1};
static __code WORD tAwtoAudioTestGain[AWTO_AUDIO_TEST_STEPS] = {0, 0, AWTO_AUDIO_GAIN_DAHUA_50, AWTO_AUDIO_GAIN_M6DB,
                                                                AWTO_AUDIO_GAIN_M3DB, AWTO_AUDIO_GAIN_0DB};

void AwtoAudioAmpBoot(void)
{
    bAMP_EN = 0;
    g_ucAwtoAudioTestN = 0;
    g_ulAwtoAudioT0 = 0;
    g_ucAwtoAudioAux = 0;
}

void AwtoAudioAmp(bit bMute)
{
    if((bMute == _OFF) && (g_ucAwtoAudioTestN != 0) && (tAwtoAudioTestAmp[g_ucAwtoAudioTestN - 1] == 0))
    {
        bAMP_EN = 0;                            // ear-test step without the amp: unmute keeps P7.4 low
        AwtoSyncPush(AWTO_SYNC_EV_AUDIO, AWTO_AUDIO_EV_AMP_TEST_OFF, 0);
        return;
    }
    bAMP_EN = (bMute == _ON) ? 0 : 1;
    AwtoSyncPush(AWTO_SYNC_EV_AUDIO, (bMute == _ON) ? AWTO_AUDIO_EV_AMP_OFF : AWTO_AUDIO_EV_AMP_ON, 0);
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

// Ear-test gain while a step is held, else 0 (AwtoAudioGain: user volume)
WORD AwtoAudioTestGain(void)
{
    return (g_ucAwtoAudioTestN != 0) ? tAwtoAudioTestGain[g_ucAwtoAudioTestN - 1] : 0;
}

// VCP 0x63 = AWTO_AUDIO_TEST_START + n: step n set up; AWTO_AUDIO_TEST_DONE + n: amp / user volume back;
// high byte AWTO_AUDIO_TEST_HZ_FLAG: tone frequency (15 bit Hz) announced. One console line each (sync.tsv E5).
void AwtoAudioTestStep(BYTE ucHi, BYTE ucLo)
{
    BYTE ucN = (ucLo & 0x0F);

    if((ucHi & AWTO_AUDIO_TEST_HZ_FLAG) != 0)
    {
        AwtoSyncPush(AWTO_SYNC_EV_AUDIO, AWTO_AUDIO_TEST_HZ + g_ucAwtoAudioTestN, ((WORD)(ucHi & 0x7F) << 8) | ucLo);
        return;
    }
    if((ucN == 0) || (ucN > AWTO_AUDIO_TEST_STEPS) || (((ucLo & 0xF0) != AWTO_AUDIO_TEST_START) && ((ucLo & 0xF0) != AWTO_AUDIO_TEST_DONE)))
    {
        return;
    }
    AwtoSyncPush(AWTO_SYNC_EV_AUDIO, ucLo, 0);          // "audio test n/6: <set-up>" before the sound / "... done"
    g_ucAwtoAudioTestN = ((ucLo & 0xF0) == AWTO_AUDIO_TEST_START) ? ucN : 0;
    if(UserInterfaceGetAudioReadyToPlayStatus() == _TRUE)   // playing: apply now; else the SDK unmute applies it
    {
        bAMP_EN = (g_ucAwtoAudioTestN != 0) ? tAwtoAudioTestAmp[ucN - 1] : 1;
        ScalerAudioDigitalAdjustVolume(UserInterfaceGetAudioVolume());
    }
}
#endif
