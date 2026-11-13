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
