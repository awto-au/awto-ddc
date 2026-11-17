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
#define AWTO_PS_TRACKS                          4       // intro, waka, death, alert (data tracks)
#define AWTO_PS_TRACK_ALERT                     3
#define AWTO_PS_TRACK_CAL                       0xFF    // calibration tone: no data track
#define AWTO_PS_CMD_CAL                         3       // AwtoPmSound(cmd): 0..2 = tracks, 3 calibration, 4 stop, 5 alert
#define AWTO_PS_CMD_STOP                        4
#define AWTO_PS_CMD_ALERT                       5
#define AWTO_PS_NOTE_BYTES                      2
#define AWTO_PS_GAP_MS                          4       // amp muted while the audio PLL divider changes (the pitch step was a click): by ear, not measured; Dan 2026-11-18 "a bit clicky at the change of sounds"
#define AWTO_PS_MS_HALF                         0x8000  // WORD ms difference below this = the time has passed
#define AWTO_PS_SCAPR_SLC                       0x80    // SCAPR bit 7 = S1 div 2, as the SDK 48 kHz code 0xA0
#define AWTO_PS_EV_START                        0x80    // sync E9: + track
#define AWTO_PS_EV_CAL                          0x83
#define AWTO_PS_EV_STOP                         0x84
#define AWTO_PS_EV_DONE                         0x85
#define AWTO_PS_EV_NA                           0x86
#define AWTO_PS_EV_ALERT                        0x87
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
static __xdata WORD s_usPsGateAt;               // AwtoMs low word at which the amp opens after a pitch change
static __xdata BYTE s_ucPsBootOff;               // 1 = the boot-time generator off has run
static __xdata BYTE s_ucPsGate;                 // 1 = the amp is muted for a pitch change and opens at s_usPsGateAt

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
        s_ucPsGate = 0;
        return;
    }
    bAMP_MUTE = 1;                              // gate the amp: the divider change and the PLL relock are not heard
    ScalerSetDataPortBit(usBase, AWTO_I_PORT_PAGE71_HDMI_AFCR, (BYTE)~AWTO_F_PORT_PAGE71_HDMI_AFCR_TST_I2S_SW,
                         ((ucNote & AWTO_PS_OCT_FLAG) != 0) ? 0x00 : AWTO_F_PORT_PAGE71_HDMI_AFCR_TST_I2S_SW);
    ScalerSetDataPortByte(usBase, AWTO_I_PORT_PAGE71_HDMI_SCAPR, AWTO_PS_SCAPR_SLC | ucSc);
    ScalerSetDataPortBit(usBase, AWTO_I_PORT_PAGE71_HDMI_CMCR, (BYTE)~AWTO_F_PORT_PAGE71_HDMI_CMCR_DBDCB, AWTO_F_PORT_PAGE71_HDMI_CMCR_DBDCB);
    s_usPsGateAt = (WORD)AwtoMs() + AWTO_PS_GAP_MS;
    s_ucPsGate = 1;                             // AwtoPmSoundPoll opens the amp after the gap
}

static void PsStop(void)
{
    s_ucPsRun = 0;
    s_ucPsGate = 0;
    SysAudioInternalGenTestProc(_OFF);          // always: the generator registers survive an MCU reset / a reflash, a tone left on by an earlier image must stop too
}

static void PsStart(BYTE ucTrack)
{
    PsStop();
    SysAudioInternalGenTestProc(_ON);
    SysAudioMuteProc(_OFF);
    AwtoAudioAmp(_OFF);                         // P7.4 + P7.3 set directly: the test generator clears the DVC mute flag, so the call above can be a no-op
    s_ucPsRun = (ucTrack == AWTO_PS_TRACK_CAL) ? 2 : 1;
    s_ucPsTrack = ucTrack;
    s_usPsPos = (ucTrack == 0) ? AWTO_PS_OFF_INTRO : ((ucTrack == 1) ? AWTO_PS_OFF_WAKA : ((ucTrack == 2) ? AWTO_PS_OFF_DEATH : AWTO_PS_OFF_ALERT));
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

    if(s_ucPsBootOff == 0)                      // first pass after boot: a generator left on by an earlier image (or a lock-up) is switched off
    {
        s_ucPsBootOff = 1;
        PsStop();
    }
    if((s_ucPsGate != 0) && ((WORD)((WORD)AwtoMs() - s_usPsGateAt) < AWTO_PS_MS_HALF))
    {
        s_ucPsGate = 0;
        bAMP_MUTE = 0;
    }
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

void AwtoPmSound(BYTE ucCmd)                    // AWTO_TC_PACMAN_SND + 0..5
{
#ifdef _AWTO_AUDIO_TEST
    if(ucCmd == AWTO_PS_CMD_ALERT)
    {
        PsStart(AWTO_PS_TRACK_ALERT);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_ALERT, 0);
    }
    else if(ucCmd == AWTO_PS_CMD_CAL)
    {
        PsStart(AWTO_PS_TRACK_CAL);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_CAL, 0);
    }
    else if(ucCmd < AWTO_PS_CMD_CAL)
    {
        PsStart(ucCmd);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_START + ucCmd, 0);
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
