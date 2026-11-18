#include "UserCommonInclude.h"
#include "keys.h"

// #229 key click: AWTO_KEY_CLICK_MS tone on a front-key press (not POWER, combo, repeat); setting key_click, default off.
// Not when the monitor is muted (user mute) or another sound plays (AwtoPmSoundTone, fw/test/snd.c). User volume.
void AwtoKeyClick(void)
{
    BYTE ucRes;

    if((AWTO_SET(KEY_CLICK) == 0) || (AWTO_SET(MUTE) != 0))
    {
        return;
    }
    ucRes = AwtoPmSoundTone(AWTO_KEY_CLICK_SC, AWTO_KEY_CLICK_MS);
    if(ucRes == AWTO_TONE_PLAYED)
    {
        AwtoSyncPush(AWTO_SYNC_EV_AUDIO, AWTO_AUDIO_EV_CLICK, 0);
    }
    else
    {
        AwtoSyncPush(AWTO_SYNC_EV_AUDIO, (ucRes == AWTO_TONE_BUSY) ? AWTO_AUDIO_EV_CLICK_BUSY : AWTO_AUDIO_EV_CLICK_NA, 0);
    }
}
