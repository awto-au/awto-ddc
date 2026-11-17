#include <stdint.h>
#include "UserCommonInclude.h"
#include "../rtdfw/awto/include/dataport.h"   // the SDK data port calls are macros for dp_wr / dp_rmw (fw/awto/boundary.py)

// Pac-Man sound on the unit (docs/pacman-sound.md): the HDMI audio test generator (AFCR audio_test_enable) as the tone source,
// pitch = audio PLL S code per note. Test cmds AWTO_TC_PACMAN_SND + 0 intro, + 1 waka (loops), + 2 death, + 3 calibration tone, + 4 stop.
// Needs a -D _AWTO_AUDIO_TEST build (SDK generator + SysAudioHandler hold); other builds log "unavailable". Non-blocking: AwtoPmSoundPoll per main pass.
// Data: pacman_sound_data.inc (scripts/pacman_sound.py).
#define AWTO_PS_OCT_FLAG                        0x80    // note byte bit 7: AFCR tst_i2s_sw = 0 (one octave down)
#define AWTO_PS_SC_MASK                         0x7F
#define AWTO_PS_TICK_MS                         10
#define AWTO_PS_CAL_SC                          32      // calibration tone: sc 32 = 48 kHz sample rate
#define AWTO_PS_TRACKS                          3
#define AWTO_PS_NOTE_BYTES                      2
#define AWTO_PS_SCAPR_SLC                       0x80    // SCAPR bit 7 = S1 div 2, as the SDK 48 kHz code 0xA0
#define AWTO_PS_EV_START                        0x80    // sync E9: + track
#define AWTO_PS_EV_CAL                          0x83
#define AWTO_PS_EV_STOP                         0x84
#define AWTO_PS_EV_DONE                         0x85
#define AWTO_PS_EV_NA                           0x86
#include "pacman_sound_data.inc"

#pragma place bank(11)                      // leaf reader in the data's bank (a const read in a function that calls banked code trips the link check)
static BYTE PsByte(WORD usIdx)
{
    return g_aucPsData[usIdx];
}

#ifdef _AWTO_AUDIO_TEST
static __xdata BYTE s_ucPsRun;                  // 0 off, 1 track playing, 2 calibration tone
static __xdata BYTE s_ucPsTrack;
static __xdata WORD s_usPsPos;
static __xdata WORD s_usPsAt;                   // AwtoMs low word at the current note's start
static __xdata WORD s_usPsDur;                  // current note length, ms

static WORD PsBase(void)
{
    return (SysSourceGetInputPort() == _D3_INPUT_PORT) ? AWTO_R_P72_HDMI_AP : AWTO_R_P71_HDMI_AP;   // generator lives in the input port's HDMI audio block
}

static void PsNote(BYTE ucNote)
{
    WORD usBase = PsBase();
    BYTE ucSc = ucNote & AWTO_PS_SC_MASK;

    if(ucSc == 0)
    {
        bAMP_MUTE = 1;                          // rest: gate at the amp, no DVC ramp (that blocks up to 400 ms)
        return;
    }
    ScalerSetDataPortBit(usBase, AWTO_I_PORT_PAGE71_HDMI_AFCR, (BYTE)~AWTO_F_PORT_PAGE71_HDMI_AFCR_TST_I2S_SW,
                         ((ucNote & AWTO_PS_OCT_FLAG) != 0) ? 0x00 : AWTO_F_PORT_PAGE71_HDMI_AFCR_TST_I2S_SW);
    ScalerSetDataPortByte(usBase, AWTO_I_PORT_PAGE71_HDMI_SCAPR, AWTO_PS_SCAPR_SLC | ucSc);
    ScalerSetDataPortBit(usBase, AWTO_I_PORT_PAGE71_HDMI_CMCR, (BYTE)~AWTO_F_PORT_PAGE71_HDMI_CMCR_DBDCB, AWTO_F_PORT_PAGE71_HDMI_CMCR_DBDCB);
    bAMP_MUTE = 0;
}

static void PsStop(void)
{
    if(s_ucPsRun != 0)
    {
        s_ucPsRun = 0;
        SysAudioInternalGenTestProc(_OFF);
    }
}

static void PsStart(BYTE ucTrack)
{
    PsStop();
    SysAudioInternalGenTestProc(_ON);
    SysAudioMuteProc(_OFF);
    s_ucPsRun = (ucTrack >= AWTO_PS_TRACKS) ? 2 : 1;
    s_ucPsTrack = ucTrack;
    s_usPsPos = (ucTrack == 0) ? AWTO_PS_OFF_INTRO : ((ucTrack == 1) ? AWTO_PS_OFF_WAKA : AWTO_PS_OFF_DEATH);
    s_usPsAt = (WORD)AwtoMs();
    s_usPsDur = 0;
    if(s_ucPsRun == 2)
    {
        PsNote(AWTO_PS_CAL_SC);
        s_usPsDur = 0xFFFF;                     // held until the stop cmd
    }
}
#endif

void AwtoPmSoundPoll(void)                      // each main pass
{
#ifdef _AWTO_AUDIO_TEST
    BYTE ucDur;

    if((s_ucPsRun != 1) || ((WORD)((WORD)AwtoMs() - s_usPsAt) < s_usPsDur))
    {
        return;
    }
    s_usPsAt += s_usPsDur;                      // note boundary on the schedule, not on this pass: no drift
    ucDur = PsByte(s_usPsPos + 1);
    if(ucDur == 0)
    {
        if(((s_ucPsTrack == 1) ? AWTO_PS_LOOP_WAKA : 0) != 0)
        {
            s_usPsPos = AWTO_PS_OFF_WAKA;
            ucDur = PsByte(s_usPsPos + 1);
        }
        else
        {
            PsStop();
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_DONE, 0);
            return;
        }
    }
    PsNote(PsByte(s_usPsPos));
    s_usPsDur = (WORD)ucDur * AWTO_PS_TICK_MS;
    s_usPsPos += AWTO_PS_NOTE_BYTES;
#endif
}

void AwtoPmSound(BYTE ucCmd)                    // AWTO_TC_PACMAN_SND + 0..4
{
#ifdef _AWTO_AUDIO_TEST
    if(ucCmd <= AWTO_PS_TRACKS)
    {
        PsStart(ucCmd);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, (ucCmd < AWTO_PS_TRACKS) ? (AWTO_PS_EV_START + ucCmd) : AWTO_PS_EV_CAL, 0);
    }
    else
    {
        PsStop();
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_STOP, 0);
    }
#else
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_NA, ucCmd);
#endif
}
