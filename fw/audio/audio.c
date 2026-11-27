#include <stdint.h>
#include "UserCommonInclude.h"
#include "../rtdfw/awto/include/dataport.h"   // the SDK data port calls are macros for dp_wr / dp_rmw (fw/awto/boundary.py)

// fw/audio = the one owner of the speaker path (#229): amp pins + ear tests (docs/audio.md), then the tone player below.
// awto speaker amp pins (awto-ddc#94, docs/audio.md): the one owner of P7.4 (amp enable) and P7.3 (AMP_MUTE, high = muted).
// aout 116/117 feeds the amp; P7.4 = !mute as Dahua 1:ea99 (evidence: docs/audio.md).
// Callers: PCB_ON_REGION_GPIO_SETTING_POWER_AC_ON (boot), PCB_AMP_MUTE (SysAudioMuteProc), VCP 0x63 (ear tests).
#if(_AUDIO_SUPPORT == _ON)
__xdata BYTE g_ucAwtoAudioTestN;                // ear-test step 1..AWTO_AUDIO_TEST_STEPS in force, 0 = none (RAM only)

// #94 ear-test steps (dev.py sound-test, VCP 0x63): aout; P7.4, DVC gain, P7.3 per step. Held until the step's DONE:
// the SDK unmute (AwtoAudioAmp) and volume mapping (AwtoAudioGain) apply them too.
static __code BYTE tAwtoAudioTestAmp[AWTO_AUDIO_TEST_STEPS] = {1, 0, 1, 1, 1, 1};
static __code BYTE tAwtoAudioTestMute[AWTO_AUDIO_TEST_STEPS] = {0, 0, 0, 0, 0, 1};    // P7.3 AMP_MUTE
static __code WORD tAwtoAudioTestGain[AWTO_AUDIO_TEST_STEPS] = {AWTO_AUDIO_GAIN_M6DB, AWTO_AUDIO_GAIN_M6DB, AWTO_AUDIO_GAIN_DAHUA_50,
                                                                AWTO_AUDIO_GAIN_M3DB, AWTO_AUDIO_GAIN_0DB, AWTO_AUDIO_GAIN_M6DB};

// Pop-free order (#249, docs/audio.md "Sequence"): the PAM8006A MUTE pin cuts the outputs without a fade and its switch-on / off is the pop,
// so both happen with the DAC input at zero (DVC ramped) and in this order: unmute = EN, wake, MUTE low; mute = MUTE high, settle, EN low.
// By ear: the datasheet (/vendors/diodes/PAM8006A.pdf) gives no MUTE / SD timing. Both waits are blocking and skipped when nothing changes.
#define AWTO_AMP_MUTE_MS                        2       // P7.3 high -> P7.4 low / generator change; scripts/audio_sim.py ORDER
#define AWTO_AMP_WAKE_MS                        20      // P7.4 high -> P7.3 low

static void AmpSet(BYTE ucEn, BYTE ucMute)
{
    if((ucMute != 0) && (bAMP_MUTE == 0))
    {
        bAMP_MUTE = 1;
        ScalerTimerDelayXms(AWTO_AMP_MUTE_MS);
    }
    if(bAMP_EN != ucEn)
    {
        bAMP_EN = ucEn;
        if(ucEn != 0)
        {
            ScalerTimerDelayXms(AWTO_AMP_WAKE_MS);
        }
    }
    bAMP_MUTE = ucMute;
}

void AwtoAudioAmpBoot(void)
{
    bAMP_MUTE = 1;                              // muted first, then disabled: the pins are still driven after a warm reset
    bAMP_EN = 0;
    g_ucAwtoAudioTestN = 0;
}

void AwtoAudioAmpEnable(void)                   // P7.4 on, P7.3 stays high: the tone player opens the gate after the pitch is set
{
    AmpSet(1, 1);
}

void AwtoAudioAmp(bit bMute)
{
    if((bMute == _OFF) && (g_ucAwtoAudioTestN != 0))
    {
        AmpSet(tAwtoAudioTestAmp[g_ucAwtoAudioTestN - 1], tAwtoAudioTestMute[g_ucAwtoAudioTestN - 1]);
        AwtoSyncPush(AWTO_SYNC_EV_AUDIO, AWTO_AUDIO_EV_AMP_TEST, g_ucAwtoAudioTestN);
        return;
    }
    AmpSet((bMute == _ON) ? 0 : 1, (bMute == _ON) ? 1 : 0);
    AwtoSyncPush(AWTO_SYNC_EV_AUDIO, (bMute == _ON) ? AWTO_AUDIO_EV_AMP_OFF : AWTO_AUDIO_EV_AMP_ON, 0);   // a repeat never gets here (PCB_AMP_MUTE, #359)
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
    AwtoSyncPush(AWTO_SYNC_EV_AUDIO, ((ucLo & 0xF0) == AWTO_AUDIO_TEST_START) ? ucLo : AWTO_AUDIO_TEST_DONE,
                 ((ucLo & 0xF0) == AWTO_AUDIO_TEST_START) ? 0 : ucN);   // "audio test n/6: <settings>" / "... end, back to default" (one row, n = value)
    g_ucAwtoAudioTestN = ((ucLo & 0xF0) == AWTO_AUDIO_TEST_START) ? ucN : 0;
    if(UserInterfaceGetAudioReadyToPlayStatus() == _TRUE)   // playing: now; else the SDK unmute applies them
    {
        AmpSet((g_ucAwtoAudioTestN != 0) ? tAwtoAudioTestAmp[ucN - 1] : 1, (g_ucAwtoAudioTestN != 0) ? tAwtoAudioTestMute[ucN - 1] : 0);
        ScalerAudioDigitalAdjustVolume(UserInterfaceGetAudioVolume());
    }
}
#endif


// Sound player of the unit (alert, key click, calibration; module snd): the HDMI audio test generator (AFCR audio_test_enable) as the tone source,
// pitch = audio PLL S code per note. Test cmds AWTO_TC_SND + 0 calibration tone, + 1 stop, + 2 alert.
// One generator: the alert track and the calibration tone are top priority (they replace what plays); a key click is refused while one plays.
// Every build (#229): SDK generator + SysAudioHandler hold are always compiled. No host-stream gate: state PLAYBACK = stream present, not audible (a PC host is always there). Non-blocking: AwtoPmSoundPoll per main pass.
// Data: snd_data.inc (scripts/snd_data_gen.py): the notes of the alert track.
#define AWTO_PS_OCT_FLAG                        0x80    // note byte bit 7: AFCR tst_i2s_sw = 0 (one octave down)
#define AWTO_PS_SC_MASK                         0x7F
#define AWTO_PS_TICK_MS                         10
#define AWTO_PS_CAL_SC                          32      // calibration tone: sc 32 = 48 kHz sample rate
#define AWTO_PS_TRACK_ALERT                     0       // data track (notes at AWTO_PS_OFF_ALERT)
#define AWTO_PS_TRACK_NONE                      0xFE    // nothing playing
#define AWTO_PS_TRACK_CAL                       0xFF    // calibration tone: no data track
#define AWTO_PS_CMD_CAL                         0       // AwtoPmSound(cmd): 0 calibration tone, 1 stop, 2 alert
#define AWTO_PS_CMD_STOP                        1
#define AWTO_PS_CMD_ALERT                       2
#define AWTO_PS_CMDS                            3
#define AWTO_PS_F_BOOT                          0x01    // flags: the boot-time generator off has run
#define AWTO_PS_F_GATE                          0x02    // the amp is muted for a pitch change and opens at s_usPsGateAt
#define AWTO_PS_F_DVC_UP                        0x08    // the DVC has been ramped up (gain written); cleared by the ramp down
#define AWTO_PS_NOTE_BYTES                      2
#define AWTO_PS_GAP_MS                          4       // amp muted while the audio PLL divider changes (the pitch step was a click): by ear, not measured; Dan 2026-11-18 "a bit clicky at the change of sounds"
#define AWTO_DVC_STEP_1DB                       0x00    // DVC_EN dvc_down_db / dvc_up_db = 00: +-1 dB per step (gain * 7/8 down, 9/8 up)
#define AWTO_DVC_ZC_SAMPLES                     1       // DVC_ZC_WIN: samples a step waits for a zero crossing before it applies anyway
#define AWTO_DVC_RAMP_POLL_MS                   1       // DVC_GAIN_DONE poll period = ScalerTimerDelayXms granularity
#define AWTO_DVC_RAMP_POLLS                     2       // ramp down 68 steps (ln 8191 / ln 8/7) x 1 sample / 48 kHz = 1.4 ms, x1.25 = 1.8 ms -> 2 polls of 1 ms
#define AWTO_PS_MS_HALF                         0x8000  // WORD ms difference below this = the time has passed
#define AWTO_PS_SCAPR_SLC                       0x80    // SCAPR bit 7 = S1 div 2, as the SDK 48 kHz code 0xA0
#define AWTO_PS_EV_CAL                          0x83
#define AWTO_PS_EV_STOP                         0x84
#define AWTO_PS_EV_DONE                         0x85
#define AWTO_PS_EV_ALERT                        0x87
#include "snd_data.inc"

#pragma place group(audio_11)                      // leaf reader in the data's bank (a const read in a function that calls banked code trips the link check)
static BYTE PsByte(WORD usIdx)
{
    return g_aucPsData[usIdx];
}

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

// Short DVC ramp (hardware, steps at zero crossings) so the MUTE pin only ever switches a zero signal; the SDK mute / unmute rewrites these fields.
static void DvcRamp(WORD usGain)
{
    BYTE ucPolls = 0;

    ScalerSetBit(AWTO_R_DVC_EN, (BYTE)~(AWTO_F_DVC_EN_DVC_DOWN_DB | AWTO_F_DVC_EN_DVC_UP_DB), AWTO_DVC_STEP_1DB);
    ScalerSetBit(AWTO_R_DVC_ZC_WIN_CTRL_0, (BYTE)~AWTO_F_DVC_ZC_WIN_CTRL_0_DVC_ZC_WIN, HIBYTE(AWTO_DVC_ZC_SAMPLES));
    ScalerSetByte(AWTO_R_DVC_ZC_WIN_CTRL_1, LOBYTE(AWTO_DVC_ZC_SAMPLES));
    ScalerAudioDVCAdjustVolume(usGain);
    if(usGain != 0)
    {
        s_ucPsFlags |= AWTO_PS_F_DVC_UP;        // up: the hardware ramps behind this call, nothing to wait for
        return;
    }
    s_ucPsFlags &= (BYTE)~AWTO_PS_F_DVC_UP;
    do
    {
        ScalerTimerDelayXms(AWTO_DVC_RAMP_POLL_MS);
        ucPolls++;
    }
    while((ScalerGetBit(AWTO_R_DVC_GAIN_DONE, AWTO_F_DVC_GAIN_DONE_DVC_DONE) == 0) && (ucPolls < AWTO_DVC_RAMP_POLLS));
    if(ScalerGetBit(AWTO_R_DVC_GAIN_DONE, AWTO_F_DVC_GAIN_DONE_DVC_DONE) == 0)
    {
        AwtoSyncPush(AWTO_SYNC_EV_AUDIO, AWTO_AUDIO_EV_DVC_SLOW, 0);   // gate closes anyway
    }
}

static void PsGateClose(void)                   // DVC to 0 first (only if it was up), then the MUTE pin, then the settle
{
    if((s_ucPsFlags & AWTO_PS_F_DVC_UP) != 0)
    {
        DvcRamp(0);
    }
    AmpSet(bAMP_EN, 1);                         // MUTE high + settle only when it was low
}

static void PsNote(BYTE ucNote)
{
    WORD usBase = PsBase();
    BYTE ucSc = ucNote & AWTO_PS_SC_MASK;

    if(ucSc == 0)
    {
        PsGateClose();                          // rest: ramp to 0, then the gate
        s_ucPsFlags &= (BYTE)~AWTO_PS_F_GATE;
        return;
    }
    PsGateClose();                              // the divider change and the PLL relock are not heard; the gate has closed before the divider moves
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
    PsGateClose();                              // DVC ramp, gate, then the generator and the amp enable (SysAudioInternalGenTestProc)
    SysAudioInternalGenTestProc(_OFF);          // always: the generator registers survive an MCU reset / a reflash, a tone left on by an earlier image must stop too
}

static void PsStart(BYTE ucTrack)
{
    if(s_ucPsTrack == AWTO_PS_TRACK_NONE)       // generator already running (a sound ended or is replaced): no off / on cycle, no click
    {
        SysAudioInternalGenTestProc(_ON);       // generator on, DVC at 0, amp disabled and muted
        AwtoAudioAmpEnable();                   // P7.4 on while the input is silent; P7.3 opens after the first pitch
        ScalerAudioMuteProc(_OFF, 0);           // DVC mute status off, gain stays 0: the ramp up follows the gate opening (AwtoPmSoundPoll)
    }
    s_ucPsTrack = ucTrack;
    s_usPsAt = (WORD)AwtoMs();
    s_usPsDur = 0;
    s_usPsPos = 0;
    if(ucTrack == AWTO_PS_TRACK_CAL)
    {
        PsNote(s_ucPsToneSc);
        s_usPsDur = 0xFFFF;                     // held until the stop cmd or AwtoPmSoundTone's length
    }
    else
    {
        s_usPsPos = AWTO_PS_OFF_ALERT;
    }
}

void AwtoPmSoundPoll(void)                      // each main pass
{
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
        DvcRamp(UserInterfaceGetAudioVolume());
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
    if(ucDur == 0)
    {
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_DONE, 0);
        PsStop();
        return;
    }
    PsNote(PsByte(s_usPsPos));
    s_usPsDur = (WORD)ucDur * AWTO_PS_TICK_MS;
    s_usPsPos += AWTO_PS_NOTE_BYTES;
}

void AwtoPmSound(BYTE ucCmd)                    // AWTO_TC_SND + 0..2: 0 calibration tone, 1 stop, 2 alert
{
    if(ucCmd >= AWTO_PS_CMDS)
    {
        return;
    }
    if(ucCmd == AWTO_PS_CMD_STOP)
    {
        s_ucPsFlags &= AWTO_PS_F_BOOT;
        PsStop();
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_STOP, 0);
    }
    else if(ucCmd == AWTO_PS_CMD_CAL)
    {
        s_ucPsToneSc = AWTO_PS_CAL_SC;
        PsStart(AWTO_PS_TRACK_CAL);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_CAL, 0);
    }
    else
    {
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_PS_EV_ALERT, 0);
        PsStart(AWTO_PS_TRACK_ALERT);
    }
}

BYTE AwtoPmSoundTone(BYTE ucSc, WORD usMs)      // one tone of S code ucSc, usMs audible (key click, fw/keys/key_click.c); AWTO_TONE_* (RL6449_Project.h)
{
    if(s_ucPsTrack != AWTO_PS_TRACK_NONE)
    {
        return AWTO_TONE_BUSY;               // another sound plays: it keeps the generator
    }
    s_ucPsToneSc = ucSc;
    PsStart(AWTO_PS_TRACK_CAL);
    s_usPsDur = usMs + AWTO_PS_GAP_MS;          // the amp opens after the pitch gap
    return AWTO_TONE_PLAYED;
}
