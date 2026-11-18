#include <stdint.h>
#include "UserCommonInclude.h"
#include "../rtdfw/awto/include/dataport.h"   // the SDK data port calls are macros for dp_wr / dp_rmw (fw/awto/boundary.py)

// Pac-Man sound on the unit (docs/pacman-sound.md): the HDMI audio test generator (AFCR audio_test_enable) as the tone source,
// pitch = audio PLL S code per note. Test cmds AWTO_TC_PACMAN_SND + 0 intro, + 1 waka (loops), + 2 death, + 3 calibration tone, + 4 stop, + 5 alert.
// One generator: priorities (pacman_sound.py PRIORITY); a dropped waka / background sound stays wanted and resumes when the higher one ends.
// Needs a -D _AWTO_AUDIO_TEST build (SDK generator + SysAudioHandler hold); other builds log "unavailable". Non-blocking: AwtoPmSoundPoll per main pass.
// Data: pacman_sound_data.inc (scripts/pacman_sound.py).
#define AWTO_PS_OCT_FLAG                        0x80    // note byte bit 7: AFCR tst_i2s_sw = 0 (one octave down)
#define AWTO_PS_SC_MASK                         0x7F
#define AWTO_PS_TICK_MS                         10
#define AWTO_PS_CAL_SC                          32      // calibration tone: sc 32 = 48 kHz sample rate
#define AWTO_PS_TRACK_INTRO                     0       // track ids = TRACKS order in scripts/pacman_sound.py (tests/test_pacman_sound.py checks)
#define AWTO_PS_TRACK_WAKA                      1
#define AWTO_PS_TRACK_ALERT                     3
#define AWTO_PS_TRACK_GHOST                     4
#define AWTO_PS_TRACK_FRUIT                     5
#define AWTO_PS_TRACK_BG0                       6       // siren speed 1..3 = 6..8 (background state 1..3), frightened = 9 (state 4): track = BG0 - 1 + state
#define AWTO_PS_TRACK_NONE                      0xFE    // nothing playing
#define AWTO_PS_TRACK_CAL                       0xFF    // calibration tone: no data track
#define AWTO_PS_PRIO_TOP                        7       // intro, alert, calibration: above everything
#define AWTO_PS_CMD_WAKA                        1       // AwtoPmSound(cmd): 0 intro, 1 waka, 2 death, 3 calibration, 4 stop, 5 alert, 6 ghost eaten, 7 fruit eaten, 8 waka off
#define AWTO_PS_CMD_CAL                         3
#define AWTO_PS_CMD_STOP                        4
#define AWTO_PS_CMD_ALERT                       5
#define AWTO_PS_CMD_GHOST                       6
#define AWTO_PS_CMD_FRUIT                       7
#define AWTO_PS_CMD_WAKA_OFF                    8
#define AWTO_PS_F_BOOT                          0x01    // flags: the boot-time generator off has run
#define AWTO_PS_F_GATE                          0x02    // the amp is muted for a pitch change and opens at s_usPsGateAt
#define AWTO_PS_F_WAKA                          0x04    // eating: waka wanted
#define AWTO_PS_F_LOW_MASK                      0x0F    // flags bits 3:0; bits 7:4 = background state wanted (siren speed / frightened)
#define AWTO_PS_F_BG_SHIFT                      4
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
#define AWTO_PS_EV_GHOST                        0x88
#define AWTO_PS_EV_FRUIT                        0x89
#define AWTO_PS_EV_BG                           0x8A    // value = background state
#define AWTO_PS_EV_WAKA_OFF                     0x8B
#include "pacman_sound_data.inc"

#pragma place bank(11)                      // leaf reader in the data's bank (a const read in a function that calls banked code trips the link check)
static BYTE PsByte(WORD usIdx)
{
    return g_aucPsData[usIdx];
}

#ifdef _AWTO_AUDIO_TEST
static __xdata BYTE s_ucPsTrack;                // playing track, AWTO_PS_TRACK_NONE = off
static __xdata WORD s_usPsPos;
static __xdata WORD s_usPsAt;                   // AwtoMs low word at the current note's start
static __xdata WORD s_usPsDur;                  // current note length, ms
static __xdata WORD s_usPsGateAt;               // AwtoMs low word at which the amp opens after a pitch change
static __xdata BYTE s_ucPsFlags;                // AWTO_PS_F_*
static __xdata BYTE s_ucPsToneSc;               // held tone's S code (calibration, key click)

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
        s_ucPsFlags &= (BYTE)~AWTO_PS_F_GATE;
        return;
    }
    bAMP_MUTE = 1;                              // gate the amp: the divider change and the PLL relock are not heard
    ScalerSetDataPortBit(usBase, AWTO_I_PORT_PAGE71_HDMI_AFCR, (BYTE)~AWTO_F_PORT_PAGE71_HDMI_AFCR_TST_I2S_SW,
                         ((ucNote & AWTO_PS_OCT_FLAG) != 0) ? 0x00 : AWTO_F_PORT_PAGE71_HDMI_AFCR_TST_I2S_SW);
    ScalerSetDataPortByte(usBase, AWTO_I_PORT_PAGE71_HDMI_SCAPR, AWTO_PS_SCAPR_SLC | ucSc);
    ScalerSetDataPortBit(usBase, AWTO_I_PORT_PAGE71_HDMI_CMCR, (BYTE)~AWTO_F_PORT_PAGE71_HDMI_CMCR_DBDCB, AWTO_F_PORT_PAGE71_HDMI_CMCR_DBDCB);
    s_usPsGateAt = (WORD)AwtoMs() + AWTO_PS_GAP_MS;
    s_ucPsFlags |= AWTO_PS_F_GATE;              // AwtoPmSoundPoll opens the amp after the gap
}

static void PsStop(void)
{
    s_ucPsTrack = AWTO_PS_TRACK_NONE;
    s_ucPsFlags &= (BYTE)~AWTO_PS_F_GATE;
    SysAudioInternalGenTestProc(_OFF);          // always: the generator registers survive an MCU reset / a reflash, a tone left on by an earlier image must stop too
}

static void PsStart(BYTE ucTrack)
{
    PsStop();
    SysAudioInternalGenTestProc(_ON);
    SysAudioMuteProc(_OFF);
    AwtoAudioAmp(_OFF);                         // P7.4 + P7.3 set directly: the test generator clears the DVC mute flag, so the call above can be a no-op
    s_ucPsTrack = ucTrack;
    s_usPsPos = PsOff(ucTrack);
    s_usPsAt = (WORD)AwtoMs();
    s_usPsDur = 0;
    if(ucTrack == AWTO_PS_TRACK_CAL)
    {
        PsNote(s_ucPsToneSc);
        s_usPsDur = 0xFFFF;                     // held until the stop cmd or AwtoPmSoundTone's length
    }
}

static void PsResume(void)                      // after a sound ended: waka if eating, else the background sound, else silence
{
    BYTE ucBg = s_ucPsFlags >> AWTO_PS_F_BG_SHIFT;

    if((s_ucPsFlags & AWTO_PS_F_WAKA) != 0)
    {
        PsStart(AWTO_PS_TRACK_WAKA);
    }
    else if(ucBg != 0)
    {
        PsStart(AWTO_PS_TRACK_BG0 - 1 + ucBg);
    }
    else
    {
        PsStop();
    }
}

static void PsRequest(BYTE ucTrack)             // plays when its priority >= the playing sound's, else dropped (waka / background stay wanted)
{
    if((s_ucPsTrack == AWTO_PS_TRACK_NONE) || (PsPrio(ucTrack) >= PsPrio(s_ucPsTrack)))
    {
        PsStart(ucTrack);
    }
}
#endif

void AwtoPmSoundPoll(void)                      // each main pass
{
#ifdef _AWTO_AUDIO_TEST
    BYTE ucDur;

    if((s_ucPsFlags & AWTO_PS_F_BOOT) == 0)     // first pass after boot: a generator left on by an earlier image (or a lock-up) is switched off
    {
        s_ucPsFlags |= AWTO_PS_F_BOOT;
        PsStop();
    }
    if(((s_ucPsFlags & AWTO_PS_F_GATE) != 0) && ((WORD)((WORD)AwtoMs() - s_usPsGateAt) < AWTO_PS_MS_HALF))
    {
        s_ucPsFlags &= (BYTE)~AWTO_PS_F_GATE;
        bAMP_MUTE = 0;
        if((s_ucPsTrack == AWTO_PS_TRACK_CAL) && (s_usPsDur != 0xFFFF))
        {
            s_usPsAt = (WORD)AwtoMs();          // a tone's length counts from the amp opening: a blocked main pass does not eat it
            s_usPsDur -= AWTO_PS_GAP_MS;
        }
    }
    if((s_ucPsTrack == AWTO_PS_TRACK_NONE) || ((WORD)((WORD)AwtoMs() - s_usPsAt) < s_usPsDur))
    {
        return;
    }
    if(s_ucPsTrack == AWTO_PS_TRACK_CAL)        // a held tone ran its length: always stops
    {
        PsStop();
        return;
    }
    s_usPsAt += s_usPsDur;                      // note boundary on the schedule, not on this pass: no drift
    ucDur = PsByte(s_usPsPos + 1);
    if((ucDur == 0) && (PsLoops(s_ucPsTrack) != 0))
    {
        s_usPsPos = PsOff(s_ucPsTrack);
        ucDur = PsByte(s_usPsPos + 1);
    }
    if(ucDur == 0)
    {
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_DONE, 0);
        PsResume();
        return;
    }
    PsNote(PsByte(s_usPsPos));
    s_usPsDur = (WORD)ucDur * AWTO_PS_TICK_MS;
    s_usPsPos += AWTO_PS_NOTE_BYTES;
#endif
}

void AwtoPmSoundBg(BYTE ucState)                // background state (siren speed 1..3, frightened 4, 0 none): acts on a change only
{
#ifdef _AWTO_AUDIO_TEST
    if((s_ucPsFlags >> AWTO_PS_F_BG_SHIFT) == ucState)
    {
        return;
    }
    s_ucPsFlags = (s_ucPsFlags & AWTO_PS_F_LOW_MASK) | (BYTE)(ucState << AWTO_PS_F_BG_SHIFT);
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_BG, ucState);
    if(((s_ucPsTrack == AWTO_PS_TRACK_NONE) || ((s_ucPsTrack >= AWTO_PS_TRACK_BG0) && (s_ucPsTrack != AWTO_PS_TRACK_CAL))))
    {
        PsResume();                             // silence or another background sound is playing; a higher sound picks the new state up at its end
    }
#else
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_NA, ucState);
#endif
}

void AwtoPmSound(BYTE ucCmd)                    // AWTO_TC_PACMAN_SND + 0..5; 6 ghost, 7 fruit, 8 waka off (game events)
{
#ifdef _AWTO_AUDIO_TEST
    BYTE ucTrack = ucCmd;                       // cmds 0..2 are the track ids

    if(ucCmd == AWTO_PS_CMD_WAKA_OFF)
    {
        s_ucPsFlags &= (BYTE)~AWTO_PS_F_WAKA;
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_WAKA_OFF, 0);
        if(s_ucPsTrack == AWTO_PS_TRACK_WAKA)
        {
            PsResume();
        }
        return;
    }
    if(ucCmd == AWTO_PS_CMD_STOP)
    {
        s_ucPsFlags &= AWTO_PS_F_BOOT;          // wanted waka and background cleared too
        PsStop();
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_STOP, 0);
        return;
    }
    if(ucCmd == AWTO_PS_CMD_CAL)
    {
        s_ucPsToneSc = AWTO_PS_CAL_SC;
        PsStart(AWTO_PS_TRACK_CAL);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_CAL, 0);
        return;
    }
    if(ucCmd == AWTO_PS_CMD_WAKA)
    {
        s_ucPsFlags |= AWTO_PS_F_WAKA;
    }
    else
    {
        s_ucPsFlags &= (BYTE)~AWTO_PS_F_WAKA;   // any other sound ends the eating run; the next pellet starts waka again
    }
    if(ucCmd == AWTO_PS_CMD_ALERT)
    {
        ucTrack = AWTO_PS_TRACK_ALERT;
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_ALERT, 0);
    }
    else if(ucCmd == AWTO_PS_CMD_GHOST)
    {
        ucTrack = AWTO_PS_TRACK_GHOST;
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_GHOST, 0);
    }
    else if(ucCmd == AWTO_PS_CMD_FRUIT)
    {
        ucTrack = AWTO_PS_TRACK_FRUIT;
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_FRUIT, 0);
    }
    else
    {
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_START + ucCmd, 0);
    }
    PsRequest(ucTrack);
#else
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_NA, ucCmd);
#endif
}

BYTE AwtoPmSoundTone(BYTE ucSc, WORD usMs)      // one tone of S code ucSc, usMs audible (key click, fw/keys/key_click.c); AWTO_TONE_* (RL6449_Project.h)
{
#ifdef _AWTO_AUDIO_TEST
    if(s_ucPsTrack != AWTO_PS_TRACK_NONE)
    {
        return AWTO_TONE_BUSY;               // another sound plays: it keeps the generator
    }
    s_ucPsToneSc = ucSc;
    PsStart(AWTO_PS_TRACK_CAL);
    s_usPsDur = usMs + AWTO_PS_GAP_MS;          // the amp opens after the pitch gap
    return AWTO_TONE_PLAYED;
#else
    (void)ucSc;
    (void)usMs;
    return AWTO_TONE_NA;
#endif
}
