// awto speaker amp pins (awto-ddc#94, docs/audio.md): the one owner of P7.4 (amp enable) and P7.3 (AMP_MUTE, high = muted).
// Unit 3 ear test 2026-11-13: aout 116/117 feeds the amp, P7.3 high silences it [hw]. P7.4 = !mute as Dahua 1:ea99 [fw].
// Callers: PCB_ON_REGION_GPIO_SETTING_POWER_AC_ON (boot), PCB_AMP_MUTE (SysAudioMuteProc), VCP 0x63 (ear tests).
#if(_AUDIO_SUPPORT == _ON)
__xdata BYTE g_ucAwtoAudioTestN;                // ear-test step 1..AWTO_AUDIO_TEST_STEPS in force, 0 = none (RAM only)

// #94 ear-test steps (dev.py sound-test, VCP 0x63): aout; P7.4, DVC gain, P7.3 per step. Held until the step's DONE:
// the SDK unmute (AwtoAudioAmp) and volume mapping (AwtoAudioGain) apply them too.
static __code BYTE tAwtoAudioTestAmp[AWTO_AUDIO_TEST_STEPS] = {1, 0, 1, 1, 1, 1};
static __code BYTE tAwtoAudioTestMute[AWTO_AUDIO_TEST_STEPS] = {0, 0, 0, 0, 0, 1};    // P7.3 AMP_MUTE
static __code WORD tAwtoAudioTestGain[AWTO_AUDIO_TEST_STEPS] = {AWTO_AUDIO_GAIN_M6DB, AWTO_AUDIO_GAIN_M6DB, AWTO_AUDIO_GAIN_DAHUA_50,
                                                                AWTO_AUDIO_GAIN_M3DB, AWTO_AUDIO_GAIN_0DB, AWTO_AUDIO_GAIN_M6DB};

void AwtoAudioAmpBoot(void)
{
    bAMP_EN = 0;
    bAMP_MUTE = 1;                              // muted until the SDK's first unmute
    g_ucAwtoAudioTestN = 0;
}

void AwtoAudioAmp(bit bMute)
{
    if((bMute == _OFF) && (g_ucAwtoAudioTestN != 0))
    {
        bAMP_EN = tAwtoAudioTestAmp[g_ucAwtoAudioTestN - 1];
        bAMP_MUTE = tAwtoAudioTestMute[g_ucAwtoAudioTestN - 1];
        AwtoSyncPush(AWTO_SYNC_EV_AUDIO, AWTO_AUDIO_EV_AMP_TEST, g_ucAwtoAudioTestN);
        return;
    }
    bAMP_EN = (bMute == _ON) ? 0 : 1;
    bAMP_MUTE = (bMute == _ON) ? 1 : 0;
    AwtoSyncPush(AWTO_SYNC_EV_AUDIO, (bMute == _ON) ? AWTO_AUDIO_EV_AMP_OFF : AWTO_AUDIO_EV_AMP_ON, 0);
}

// Ear-test gain while a step is held, else 0 (AwtoAudioGain: user volume)
WORD AwtoAudioTestGain(void)
{
    return (g_ucAwtoAudioTestN != 0) ? tAwtoAudioTestGain[g_ucAwtoAudioTestN - 1] : 0;
}

// VCP 0x63 = AWTO_AUDIO_TEST_START + n: step n set up (pins + gain at once when playing, else at the SDK unmute);
// AWTO_AUDIO_TEST_DONE + n: back to default (amp on, unmuted, user volume); high byte AWTO_AUDIO_TEST_HZ_FLAG: tone
// frequency (15 bit Hz) announced. One console line each (sync.tsv E5).
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
    AwtoSyncPush(AWTO_SYNC_EV_AUDIO, ucLo, 0);          // "audio test n/6: <settings>" / "... end, back to default"
    g_ucAwtoAudioTestN = ((ucLo & 0xF0) == AWTO_AUDIO_TEST_START) ? ucN : 0;
    if(UserInterfaceGetAudioReadyToPlayStatus() == _TRUE)   // playing: now; else the SDK unmute applies them
    {
        bAMP_EN = (g_ucAwtoAudioTestN != 0) ? tAwtoAudioTestAmp[ucN - 1] : 1;
        bAMP_MUTE = (g_ucAwtoAudioTestN != 0) ? tAwtoAudioTestMute[ucN - 1] : 0;
        ScalerAudioDigitalAdjustVolume(UserInterfaceGetAudioVolume());
    }
}
#endif
