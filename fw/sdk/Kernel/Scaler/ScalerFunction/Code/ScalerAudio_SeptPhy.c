/********************************************************************************/
/*   The  Software  is  proprietary,  confidential,  and  valuable to Realtek   */
/*   Semiconductor  Corporation  ("Realtek").  All  rights, including but not   */
/*   limited  to  copyrights,  patents,  trademarks, trade secrets, mask work   */
/*   rights, and other similar rights and interests, are reserved to Realtek.   */
/*   Without  prior  written  consent  from  Realtek,  copying, reproduction,   */
/*   modification,  distribution,  or  otherwise  is strictly prohibited. The   */
/*   Software  shall  be  kept  strictly  in  confidence,  and  shall  not be   */
/*   disclosed to or otherwise accessed by any third party.                     */
/*   c<2003> - <2012>                                                           */
/*   The Software is provided "AS IS" without any warranty of any kind,         */
/*   express, implied, statutory or otherwise.                                  */
/********************************************************************************/

//----------------------------------------------------------------------------------------------------
// ID Code      : ScalerAudio_SeptPhy.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#include "ScalerFunctionInclude.h"

//****************************************************************************
// DEFINITIONS / MACROS
//****************************************************************************

//****************************************************************************
// STRUCT / TYPE / ENUM DEFINITTIONS
//****************************************************************************

//****************************************************************************
// CODE TABLES
//****************************************************************************

//****************************************************************************
// VARIABLE DECLARATIONS
//****************************************************************************

//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
#if(_AUDIO_SUPPORT == _ON)
bit ScalerAudioGetAudioInputPortChanged(EnumAudioInputSource enumAudioSource, BYTE ucInputPort);

#if(_DP_SUPPORT == _ON)
bit ScalerAudioDPGetMuteProc(BYTE ucInputPort);
void ScalerAudioDpAudioEnable(bit bEnable, BYTE ucInputPort);
void ScalerAudioDpAudioEnable_EXINT0(bit bEnable, BYTE ucInputPort);

#if(_D0_DP_EXIST == _ON)
#endif

#if(_D1_DP_EXIST == _ON)
void ScalerAudioD1DPAudioInitial(void);
void ScalerAudioD1DPDigitalOutputProc(bit bEnable);
void ScalerAudioD1DPSetDVCWindowSize(bit bAdjustType, EnumAudioSamplingFreqPacket enumSamplingFreqPacket);
void ScalerAudioD1DPSetDVCVolumeAdjustType(bit bAdjustType);
#endif

#endif // End of #if(_DP_SUPPORT == _ON)

#if(_HDMI_SUPPORT == _ON)
#if((_D2_HDMI_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON))
void ScalerAudioHdmiDigitalDetectProc(BYTE ucPort);
bit ScalerAudioHdmiGetAudioDetected(BYTE ucPort);
void ScalerAudioHdmiAudioInitial(BYTE ucPort);
void ScalerAudioHdmiLoadInitialICode(BYTE ucPort);
void ScalerAudioHdmiLoadStableICodeEvent(BYTE ucPort);
EnumAudioSamplingFreqType ScalerAudioHdmiSamplingFreqDetect(BYTE ucPort);
void ScalerAudioHdmiSetAudioPLL(BYTE ucPort);
void ScalerAudioHdmiWatchDogProc(BYTE ucPort, bit bOn);

#if(_INTERNAL_AUDIO_TEST_SUPPORT == _ON)
bit ScalerAudioHdmiGetInternalAudioGenEnable(BYTE ucPort);
void ScalerAudioHdmiInternalAudioGenSwitch(BYTE ucPort, bit bOn);
#endif

#endif
#endif

#if(_LINE_IN_SUPPORT == _ON)
void ScalerAudioSetADCAudioPLL(void);
#endif

#if(_SLEEP_AUDIO_SUPPORT == _ON)
#if((_DP_SUPPORT == _ON) && ((_PS_AUDIO_INPUT == _PS_AUDIO_BOTH) || (_PS_AUDIO_INPUT == _PS_AUDIO_DP)))
bit ScalerAudioGetDpStandaloneAudioStatus(BYTE ucInputPort);
#endif
#endif

#endif // End of #if(_AUDIO_SUPPORT == _ON)

//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
#if(_AUDIO_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Get if Digital Audio Port Changed
// Input Value  : ucInputPort
// Output Value : _TRUE of _FALSE
//--------------------------------------------------
bit ScalerAudioGetAudioInputPortChanged(EnumAudioInputSource enumAudioSource, BYTE ucInputPort)
{
#if(_LINE_IN_SUPPORT == _ON)
    if(enumAudioSource != ScalerAudioGetInputSource())
    {
        return _TRUE;
    }
#endif

    if(enumAudioSource == _DIGITAL_AUDIO)
    {
        return (ucInputPort != ScalerAudioGetDigitalAudioPortMapping());
    }

    return _FALSE;
}

#if(_DP_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Check if Mute Audio
// Input Value  : ucInputPort
// Output Value : _TRUE or _FALSE
//--------------------------------------------------
bit ScalerAudioDPGetMuteProc(BYTE ucInputPort)
{
    if(ucInputPort == ScalerAudioGetDigitalAudioPortMapping())
    {
        return _TRUE;
    }

    return _FALSE;
}
//--------------------------------------------------
// Description  : Enable DP audio FSM
// Input Value  : Enable or Disable, Input Port
// Output Value : None
//--------------------------------------------------
void ScalerAudioDpAudioEnable(bit bEnable, BYTE ucInputPort)
{
    switch(ucInputPort)
    {
        case _D0_INPUT_PORT:

#if((_D6_INPUT_PORT_TYPE != _D6_NO_PORT) && (_D6_INPUT_PORT_SWITCH_FROM == _SWITCH_FROM_D0))
        case _D6_INPUT_PORT:
#endif

#if(_D0_DP_EXIST == _ON)
            ScalerSetBit(PB6_74_AUD_FSM_CTRL_0, ~_BIT7, ((BYTE)bEnable) << 7);
#endif
            break;

        case _D1_INPUT_PORT:

#if(_D1_DP_EXIST == _ON)
            ScalerSetBit(PB9_74_AUD_FSM_CTRL_0, ~_BIT7, ((BYTE)bEnable) << 7);
#endif
            break;

        default:
            break;
    }
}

//--------------------------------------------------
// Description  : Enable DP audio FSM
// Input Value  : Enable or Disable, Input Port
// Output Value : None
//--------------------------------------------------
void ScalerAudioDpAudioEnable_EXINT0(bit bEnable, BYTE ucInputPort)
{
    switch(ucInputPort)
    {
        case _D0_INPUT_PORT:

#if((_D6_INPUT_PORT_TYPE != _D6_NO_PORT) && (_D6_INPUT_PORT_SWITCH_FROM == _SWITCH_FROM_D0))
        case _D6_INPUT_PORT:
#endif

#if(_D0_DP_EXIST == _ON)
            ScalerSetBit_EXINT(PB6_74_AUD_FSM_CTRL_0, ~_BIT7, ((BYTE)bEnable) << 7);
#endif
            break;

        case _D1_INPUT_PORT:

#if(_D1_DP_EXIST == _ON)
            ScalerSetBit_EXINT(PB9_74_AUD_FSM_CTRL_0, ~_BIT7, ((BYTE)bEnable) << 7);
#endif
            break;

        default:
            break;
    }
}

#if(_D0_DP_EXIST == _ON)


#endif

#if(_D1_DP_EXIST == _ON)
//--------------------------------------------------
// Description  : Initial D1 DP audio setting
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerAudioD1DPAudioInitial(void)
{
    ScalerAudioD1SetAudioPLL();

    // Disable Check VBID[4] to Mute Audio by HW and disable Audio FSM
    ScalerSetBit(PB9_74_AUD_FSM_CTRL_0, ~(_BIT7 | _BIT1), 0x00);

    // Disable AFD, set 2ms for auto freq. detect and disable 44.1kHz as 48kHz
    ScalerSetBit(PB9_50_AUD_FREQUENY_DET_0, ~(_BIT7 | _BIT3 | _BIT2 | _BIT0), _BIT2);

    // Set threshold to sepeerate sampling frequency
    ScalerSetByte(PB9_52_AUD_FREQUENY_TH_0, 0x00);
    ScalerSetByte(PB9_53_AUD_FREQUENY_TH_1, 0x00);
    ScalerSetByte(PB9_54_AUD_FREQUENY_TH_2, 0x28);
    ScalerSetByte(PB9_55_AUD_FREQUENY_TH_3, 0x4C);
    ScalerSetByte(PB9_56_AUD_FREQUENY_TH_4, 0x5C);
    ScalerSetByte(PB9_57_AUD_FREQUENY_TH_5, 0x70);

    // Enable RS Decode
    ScalerSetBit(PB9_2B_MN_RS_DEC_CTRL, ~(_BIT7 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT7 | _BIT3 | _BIT2 | _BIT1 | _BIT0));

    // Set xtal divider for sampling freq. detection
    ScalerSetByte(PB9_51_AUD_FREQUENY_DET_1, _AUTO_FREQ_DETECT_XTAL_DIV);

    // Enable SDM control
    ScalerSetBit(PB9_80_AUD_PS_CTRL_0, ~_BIT7, _BIT7);

    // Disable Boundary Tracking Method
    ScalerSetBit(PB9_81_AUD_BDRY_0, ~_BIT7, 0x00);

    // Set I __code of boundary tracking
    ScalerSetByte(PB9_83_AUD_BDRY_2, HIBYTE(_INITIAL_I_CODE));
    ScalerSetByte(PB9_84_AUD_BDRY_3, LOBYTE(_INITIAL_I_CODE));

    // Set P __code of boundary tracking
    ScalerSetByte(PB9_85_AUD_BDRY_4, 0x7F);
    ScalerSetByte(PB9_86_AUD_BDRY_5, 0xFF);

    // Disable Trend Tracking Method
    ScalerSetBit(PB9_92_AUD_TRND_0, ~_BIT7, 0x00);

    // Set I __code of trend tracking
    ScalerSetByte(PB9_99_AUD_TRND_7, 0x00);
    ScalerSetByte(PB9_9A_AUD_TRND_8, 0x02);

    // Set P __code of trend tracking
    ScalerSetByte(PB9_9B_AUD_TRND_9, 0x7F);
    ScalerSetByte(PB9_9C_AUD_TRND_10, 0xFF);

    // Enable Audio Buffer
    ScalerSetBit(PB9_B0_DP_AUD_CTRL, ~(_BIT7 | _BIT5), (_BIT7 | _BIT5));

    // Set AUD PKT ID
    ScalerSetByte(PB9_B1_DP_AUD_ID, 0x00);

#if(_AUDIO_MANUAL_SAMPLING_FREQ_SUPPORT == _ON)

    // Set S __code by FW manual
    ScalerSetBit(PB9_58_SCODE_0, ~_BIT7, _BIT7);

    // Set D __code by FW manual
    ScalerSetBit(PB9_80_AUD_PS_CTRL_0, ~_BIT6, 0x00);

#if(_FIX_SAMPLING_FREQ_TYPE == _FIX_FREQ_32KHZ)

    // S __code for 32kHz
    ScalerSetBit(PB9_5A_SCODE_2, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _DP_SAMPLING_FREQ_32K_GROUP_S_CODE);

    // D __code for 32kHz
    ScalerSetByte(PB9_9D_AUD_D_CODE_0, HIBYTE(_DP_SAMPLING_FREQ_32K_GROUP_D_CODE));
    ScalerSetByte(PB9_A0_AUD_D_CODE_1, LOBYTE(_DP_SAMPLING_FREQ_32K_GROUP_D_CODE));

#elif(_FIX_SAMPLING_FREQ_TYPE == _FIX_FREQ_44_1KHZ)

    // S __code for 44.1kHz
    ScalerSetBit(PB9_5A_SCODE_2, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _DP_SAMPLING_FREQ_44K_GROUP_S_CODE);

    // D __code for 44.1kHz
    ScalerSetByte(PB9_9D_AUD_D_CODE_0, HIBYTE(_DP_SAMPLING_FREQ_44K_GROUP_D_CODE));
    ScalerSetByte(PB9_A0_AUD_D_CODE_1, LOBYTE(_DP_SAMPLING_FREQ_44K_GROUP_D_CODE));

#else // _FIX_SAMPLING_FREQ_TYPE == _FIX_FREQ_48KHZ

    // S __code for 48kHz
    ScalerSetBit(PB9_5A_SCODE_2, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _DP_SAMPLING_FREQ_48K_GROUP_S_CODE);

    // D __code for 48kHz
    ScalerSetByte(PB9_9D_AUD_D_CODE_0, HIBYTE(_DP_SAMPLING_FREQ_48K_GROUP_D_CODE));
    ScalerSetByte(PB9_A0_AUD_D_CODE_1, LOBYTE(_DP_SAMPLING_FREQ_48K_GROUP_D_CODE));

#endif

    // D __code Double Buffer
    ScalerSetBit(PB9_7C_AUD_FSM_CTRL_1, ~_BIT7, _BIT7);
#else
    // Set S __code by HW auto
    ScalerSetBit(PB9_58_SCODE_0, ~_BIT7, 0x00);

    // Set D __code by HW auto
    ScalerSetBit(PB9_80_AUD_PS_CTRL_0, ~_BIT6, _BIT6);

    // S __code for 32kHz
    ScalerSetBit(PB9_58_SCODE_0, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _DP_SAMPLING_FREQ_32K_GROUP_S_CODE);

    // S __code for 44.1kHz
    ScalerSetBit(PB9_59_SCODE_1, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _DP_SAMPLING_FREQ_44K_GROUP_S_CODE);

    // S __code for 48kHz
    ScalerSetBit(PB9_5A_SCODE_2, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _DP_SAMPLING_FREQ_48K_GROUP_S_CODE);

    // D __code for 32kHz
    ScalerSetByte(PB9_5B_DCODE_0, HIBYTE(_DP_SAMPLING_FREQ_32K_GROUP_D_CODE));
    ScalerSetByte(PB9_5C_DCODE_1, LOBYTE(_DP_SAMPLING_FREQ_32K_GROUP_D_CODE));

    // D __code for 44.1kHz
    ScalerSetByte(PB9_5D_DCODE_2, HIBYTE(_DP_SAMPLING_FREQ_44K_GROUP_D_CODE));
    ScalerSetByte(PB9_5E_DCODE_3, LOBYTE(_DP_SAMPLING_FREQ_44K_GROUP_D_CODE));

    // D __code for 48kHz
    ScalerSetByte(PB9_5F_DCODE_4, HIBYTE(_DP_SAMPLING_FREQ_48K_GROUP_D_CODE));
    ScalerSetByte(PB9_60_DCODE_5, LOBYTE(_DP_SAMPLING_FREQ_48K_GROUP_D_CODE));

    // D __code Double Buffer
    ScalerSetBit(PB9_7C_AUD_FSM_CTRL_1, ~_BIT7, _BIT7);
#endif // End of #if(_AUDIO_MANUAL_SAMPLING_FREQ_SUPPORT == _ON)

    // DP Audio DVC Mode Setting
    ScalerAudioD1DPSetDVCVolumeAdjustType(_DP_DVC_ADJUST_TYPE);

    // Enable AFD, Disable Samping Freq. Change INT
    ScalerSetBit(PB9_50_AUD_FREQUENY_DET_0, ~(_BIT7 | _BIT6), _BIT7);

    // Enable I2S Output
    ScalerSetBit(PB9_B8_DP_I2S_CTRL, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT2 | _BIT1 | _BIT0));

    // Enable SPDIF Output
    ScalerSetBit(PB9_A9_SPDIF_TX_0, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT2 | _BIT1 | _BIT0));

    CLR_AUDIO_D1_ICODE_RELOADED();
}
//--------------------------------------------------
// Description  : DP Digital Audio Output Process
// Input Value  : Enable or Disable
// Output Value : None
//--------------------------------------------------
void ScalerAudioD1DPDigitalOutputProc(bit bEnable)
{
    ScalerSetByte(PB9_B3_DP_CHANNEL_EN, ((bEnable == _ENABLE) ? 0xFF : 0x00));
}

//--------------------------------------------------
// Description  : Set ZCD Timeout for DP Audio
// Input Value  : bAdjustType, enumSamplingFreqPacket
// Output Value : None
//--------------------------------------------------
void ScalerAudioD1DPSetDVCWindowSize(bit bAdjustType, EnumAudioSamplingFreqPacket enumSamplingFreqPacket)
{
    if(enumSamplingFreqPacket == _AUDIO_FREQ_PACKET_NO_AUDIO)
    {
        enumSamplingFreqPacket = _AUDIO_FREQ_PACKET_48K;
    }

    if(bAdjustType == _DB_GAIN)
    {
        // Get numbers of the volume step for mute or unmute
        PDATA_WORD(0) = _DVC_DB_STEP_NUMBER << 3;
    }
    else
    {
        // Volume Max = 0x3FFF
        PDATA_WORD(0) = 0x3FFF / _DP_VOLUME_STEP_SIZE_VALUE + 1;
    }

    // Calculate samples of ZCD timeout
    PDATA_DWORD(1) = (DWORD)enumSamplingFreqPacket * _DP_DVC_VOLUME_MUTE_TIMER / PDATA_WORD(0);

    // Avoid Overflow
    if(PDATA_DWORD(1) > 0x0FFF)
    {
        PDATA_WORD(0) = 0x0FFF;
    }
    else
    {
        PDATA_WORD(0) = (WORD)PDATA_DWORD(1);
    }

    // Set DVC ZCD window size
    ScalerSetBit(PB9_78_DVC_WINDOW_CONTROL_0, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), HIBYTE(PDATA_WORD(0)));
    ScalerSetByte(PB9_79_DVC_WINDOW_CONTROL_1, LOBYTE(PDATA_WORD(0)));
}

//--------------------------------------------------
// Description  : Select DVC Volume Adjust Type
// Input Value  : _DB_GAIN, _VOLUME_STEP_SIZE
// Output Value : None
//--------------------------------------------------
void ScalerAudioD1DPSetDVCVolumeAdjustType(bit bAdjustType)
{
    if(bAdjustType == _DB_GAIN)
    {
        // Select Value Mode to DB Gain Setp
        ScalerSetBit(PB9_76_DVC_CTRL, ~(_BIT7 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT7 | (_DP_DB_GAIN_DOWN_VALUE << 2) | _DP_DB_GAIN_UP_VALUE));

        // Initial Volume Step Size for DB Gain Mode
        ScalerSetByte(PB9_77_DVC_VA, 0x01);
    }
    else // _VOLUME_STEP_SIZE
    {
        // Select Value Mode to Volume Setp
        ScalerSetBit(PB9_76_DVC_CTRL, ~(_BIT7 | _BIT4), (_BIT7 | _BIT4));

        // Set Volume Step Size
        ScalerSetByte(PB9_77_DVC_VA, _DP_VOLUME_STEP_SIZE_VALUE);
    }

    // DP Audio DVC Window Setting
    ScalerAudioD1DPSetDVCWindowSize(bAdjustType, _AUDIO_FREQ_PACKET_48K);
}
#endif

#endif // End of #if(_DP_SUPPORT == _ON)

#if(_HDMI_SUPPORT == _ON)
#if((_D2_HDMI_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON))
//--------------------------------------------------
// Description  : HDMI audio register access of port ucPort (0 = D2, 1 = D3): data port and status register of page 0x71 + port
//--------------------------------------------------
static void AudioHdmiSetDpBitAO(BYTE ucPort, BYTE ucIndex, WORD usAndOr)  // awto: And:Or in one WORD, 3 register arguments (#336)
{
    ScalerSetDataPortBit(AUDIO_HDMI_REG(ucPort, P71_C9_HDMI_AP), ucIndex, (BYTE)(usAndOr >> 8), (BYTE)usAndOr);
}
#define AudioHdmiSetDpBit(p, i, a, o)  AudioHdmiSetDpBitAO((p), (i), (((WORD)(BYTE)(a) << 8) | (BYTE)(o)))  // awto: call sites keep the 4 argument form (#336)

static void AudioHdmiSetDpByte(BYTE ucPort, BYTE ucIndex, BYTE ucValue)
{
    ScalerSetDataPortByte(AUDIO_HDMI_REG(ucPort, P71_C9_HDMI_AP), ucIndex, ucValue);
}

static BYTE AudioHdmiGetDpBit(BYTE ucPort, BYTE ucIndex, BYTE ucAnd)
{
    return ScalerGetDataPortBit(AUDIO_HDMI_REG(ucPort, P71_C9_HDMI_AP), ucIndex, ucAnd);
}

static BYTE AudioHdmiGetSr(BYTE ucPort, BYTE ucAnd)
{
    return ScalerGetBit(AUDIO_HDMI_REG(ucPort, P71_CB_HDMI_SR), ucAnd);
}

static void AudioHdmiSetSr(BYTE ucPort, BYTE ucAnd, BYTE ucOr)
{
    ScalerSetBit(AUDIO_HDMI_REG(ucPort, P71_CB_HDMI_SR), ucAnd, ucOr);
}

//--------------------------------------------------
// Description  : Detect HDMI digital audio for HDMI/DP interface
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerAudioHdmiDigitalDetectProc(BYTE ucPort)
{
    if(ScalerAudioHdmiSamplingFreqDetect(ucPort) != 0x00)
    {
        if(AudioHdmiGetDpBit(ucPort, _P71_CA_PT_15_PORT_PAGE71_HDMI_PSCR, (_BIT3 | _BIT2)) == 0x00)
        {
            // Enable Audio FIFO Tracking
            AudioHdmiSetDpBit(ucPort, _P71_CA_PT_15_PORT_PAGE71_HDMI_PSCR, ~(_BIT3 | _BIT2), (_BIT3 | _BIT2));

            // Set Double Buffer bit
            AudioHdmiSetDpBit(ucPort, _P71_CA_PT_10_PORT_PAGE71_HDMI_CMCR, ~_BIT4, _BIT4);

            // Clear Audio Freq Changed Flag
            AudioHdmiSetDpBit(ucPort, _P71_CA_PT_8A_PORT_PAGE71_AUDIO_FREQDET, ~(_BIT1 | _BIT0), _BIT1);

            // Enable Audio Freq Changed INT
            AudioHdmiSetDpBit(ucPort, _P71_CA_PT_8A_PORT_PAGE71_AUDIO_FREQDET, ~(_BIT3 | _BIT1 | _BIT0), _BIT3);

            DebugMessageAudio("HDMI Audio Tracking Enable", 0);
        }

        SET_AUDIO_HDMI_PACKET_DETECT(ucPort);
        SET_AUDIO_HDMI_DIGITAL_SOURCE(ucPort, _DIGITAL_AUDIO_SOURCE_HDMI);

        if(GET_AUDIO_HDMI_ICODE_RELOADED(ucPort) == _FALSE)
        {
            ScalerTimerReactiveTimerEvent(_AUDIO_DYNAMIC_I_CODE_TIMER_MS, AUDIO_HDMI_SEL(ucPort, _SCALER_TIMER_EVENT_AUDIO_D2_LOAD_STABLE_I_CODE, _SCALER_TIMER_EVENT_AUDIO_D3_LOAD_STABLE_I_CODE));

            SET_AUDIO_HDMI_ICODE_RELOADED(ucPort);
        }
    }
    else
    {
        if(AudioHdmiGetDpBit(ucPort, _P71_CA_PT_15_PORT_PAGE71_HDMI_PSCR, (_BIT3 | _BIT2)) != 0x00)
        {
            // Diable Audio Freq Changed INT
            AudioHdmiSetDpBit(ucPort, _P71_CA_PT_8A_PORT_PAGE71_AUDIO_FREQDET, ~(_BIT3 | _BIT1 | _BIT0), 0x00);

            // Disable Audio FIFO Tracking
            AudioHdmiSetDpBit(ucPort, _P71_CA_PT_15_PORT_PAGE71_HDMI_PSCR, ~(_BIT3 | _BIT2), 0x00);

            // Set Double Buffer bit
            AudioHdmiSetDpBit(ucPort, _P71_CA_PT_10_PORT_PAGE71_HDMI_CMCR, ~_BIT4, _BIT4);

            // Reload D __code
            AudioHdmiSetDpBit(ucPort, _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~_BIT6, _BIT6);
            AudioHdmiSetDpBit(ucPort, _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~_BIT6, 0x00);

            DebugMessageAudio("HDMI Audio Tracking Disable", 0);
        }

        CLR_AUDIO_HDMI_PACKET_DETECT(ucPort);
        SET_AUDIO_HDMI_DIGITAL_SOURCE(ucPort, _DIGITAL_AUDIO_SOURCE_NONE);

        if(GET_AUDIO_HDMI_ICODE_RELOADED(ucPort) == _TRUE)
        {
            ScalerTimerCancelTimerEvent(AUDIO_HDMI_SEL(ucPort, _SCALER_TIMER_EVENT_AUDIO_D2_LOAD_STABLE_I_CODE, _SCALER_TIMER_EVENT_AUDIO_D3_LOAD_STABLE_I_CODE));

            ScalerAudioHdmiLoadInitialICode(ucPort);

            CLR_AUDIO_HDMI_ICODE_RELOADED(ucPort);
        }
    }
}
//--------------------------------------------------
// Description  : Get HDMI Audio Detected
// Input Value  : None
// Output Value : TRUE => Audio Detected
//--------------------------------------------------
bit ScalerAudioHdmiGetAudioDetected(BYTE ucPort)
{
    // Check audio packet
    if(GET_AUDIO_HDMI_PACKET_DETECT(ucPort) == _FALSE)
    {
        DebugMessageAudio("False : D3 Audio Packet", 0);
        return _FALSE;
    }

    // Check AVMute
    if(AudioHdmiGetSr(ucPort, _BIT6) == _BIT6)
    {
        DebugMessageAudio("False : D3 AVMute", 0);
        return _FALSE;
    }

    // Check Audio Tracking
    if(AudioHdmiGetDpBit(ucPort, _P71_CA_PT_15_PORT_PAGE71_HDMI_PSCR, (_BIT3 | _BIT2)) == 0x00)
    {
        DebugMessageAudio("False : D3 HDMI Audio Tracking Disable", 0);
        return _FALSE;
    }

    // Check HDMI audio FIFO overflow and underflow
    if(AudioHdmiGetSr(ucPort, (_BIT2 | _BIT1)) != 0x00)
    {
        DebugMessageAudio("False : D3 HDMI Audio FIFO", AudioHdmiGetSr(ucPort, (_BIT2 | _BIT1)));

        if(AudioHdmiGetDpBit(ucPort, _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, (_BIT2 | _BIT1)) == 0x00)
        {
            // Clear HDMI audio FIFO overflow and underflow status
            AudioHdmiSetSr(ucPort, ~(_BIT2 | _BIT1), (_BIT2 | _BIT1));

            if(AudioHdmiGetSr(ucPort, (_BIT2 | _BIT1)) != 0x00)
            {
                DebugMessageAudio("False : D3 HDMI Audio DB Retry", AudioHdmiGetSr(ucPort, (_BIT2 | _BIT1)));

                // Set Double Buffer bit
                AudioHdmiSetDpBit(ucPort, _P71_CA_PT_10_PORT_PAGE71_HDMI_CMCR, ~_BIT4, _BIT4);

                // Clear HDMI audio FIFO overflow and underflow status
                AudioHdmiSetSr(ucPort, ~(_BIT2 | _BIT1), (_BIT2 | _BIT1));
            }
        }

        return _FALSE;
    }

    return _TRUE;
}
//--------------------------------------------------
// Description  : Initial HDMI audio setting
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerAudioHdmiAudioInitial(BYTE ucPort)
{
    ScalerAudioHdmiSetAudioPLL(ucPort);

    // Disable sine wave generator
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_03_PORT_PAGE71_HDMI_AFCR, ~_BIT4, 0x00);

    // Disable AVMUTE function and enable Audio FIFO Tracking main control (I/P code)
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~(_BIT7 | _BIT5), _BIT5);

    // Disable FIFO Boundary Tracking, Disable Trend Tracking
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_15_PORT_PAGE71_HDMI_PSCR, ~(_BIT7 | _BIT6 | _BIT5 | _BIT3 | _BIT2), (_BIT7 | _BIT6 | _BIT5));

    // Enable SDM
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_2D_PORT_PAGE71_HDMI_AAPNR, ~_BIT1, _BIT1);

    // Set auto gain delay mode and final gain = full gain
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_07_PORT_PAGE71_HDMI_MAG_M_FINAL, ~_BIT3, 0x00);

    // Set wait time for load parameter
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_0A_PORT_PAGE71_AUDIO_LD_P_TIME_M, ~(_BIT1 | _BIT0), 0x00);
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_0B_PORT_PAGE71_AUDIO_LD_P_TIME_N, 0x10);

    // Set ZCD timeout
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_0D_PORT_PAGE71_ZCD_TIMEOUT, ~(_BIT6 | _BIT5 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _ZCD_TIMEOUT_DEFAULT);

    // Set Boundary Address = 5 for Boundary Tracking
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_1B_PORT_PAGE71_HDMI_FBR, ~(_BIT2 | _BIT1 | _BIT0), (_BIT2 | _BIT0));

    // Set I __code of trend
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_20_PORT_PAGE71_HDMI_ICTPSR0, 0x00);
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_21_PORT_PAGE71_HDMI_ICTPSR1, 0x02);

    // Set P __code of trend
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_22_PORT_PAGE71_HDMI_PCTPSR0, 0x7F);
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_23_PORT_PAGE71_HDMI_PCTPSR1, 0xFF);

    // Set I __code of boundary
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_24_PORT_PAGE71_HDMI_ICBPSR0, HIBYTE(_INITIAL_I_CODE));
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_25_PORT_PAGE71_HDMI_ICBPSR1, LOBYTE(_INITIAL_I_CODE));

    // Set P __code of boundary
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_26_PORT_PAGE71_HDMI_PCBPSR0, 0x7F);
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_27_PORT_PAGE71_HDMI_PCBPSR1, 0xFF);

    // Audio Normal Output
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_30_PORT_PAGE71_HDMI_AVMCR, ~(_BIT6 | _BIT5), (_BIT6 | _BIT5));

    // Disable Audio Watchdog for FIFO Overflow/Underflow
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~(_BIT2 | _BIT1), 0x00);

    // Set X Value
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_32_PORT_PAGE71_HDMI_WDCR1, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT1 | _BIT0));

    // Set Y Value
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_33_PORT_PAGE71_HDMI_WDCR2, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT1 | _BIT0));

    // Bit2: When no audio or changing sampling rate, AFSM load double buffer one more.
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_9F_PORT_PAGE71_PRESET_AFSM_MOD, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT2), (_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT2));

    // Seperate the detected sampling frequency
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_8B_PORT_PAGE71_AUDIO_FREQ_RESULT, ~(_BIT6 | _BIT5 | _BIT4), 0x00);

    // Set 2ms for auto frequency detecttion
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_8C_PORT_PAGE71_AUDIO_FREQ_RESULT_M, ~(_BIT6 | _BIT5), _BIT5);

    // Change audio clk divider according to SYSCLK = 27MHz
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_8E_PORT_PAGE71_XTAL_DIV, _AUTO_FREQ_DETECT_XTAL_DIV);

    // Set threshold to sepeerate sampling frequency
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_90_PORT_PAGE71_TH1, 0x00);
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_91_PORT_PAGE71_TH2, 0x28);
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_92_PORT_PAGE71_TH3, 0x4C);
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_93_PORT_PAGE71_TH4, 0x5C);
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_94_PORT_PAGE71_TH5, 0x70);

#if(_AUDIO_MANUAL_SAMPLING_FREQ_SUPPORT == _ON)

    // Disable Auto Load S Code
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_8A_PORT_PAGE71_AUDIO_FREQDET, ~_BIT6, 0x00);

#if(_FIX_SAMPLING_FREQ_TYPE == _FIX_FREQ_32KHZ)

    // Set S __code for 32kHz
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_12_PORT_PAGE71_HDMI_SCAPR, _HDMI_SAMPLING_FREQ_32K_GROUP_S_CODE);

    // Set D __code for 32kHz
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_13_PORT_PAGE71_HDMI_DCAPR0, HIBYTE(_HDMI_SAMPLING_FREQ_32K_GROUP_D_CODE));
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_14_PORT_PAGE71_HDMI_DCAPR1, LOBYTE(_HDMI_SAMPLING_FREQ_32K_GROUP_D_CODE));

#elif(_FIX_SAMPLING_FREQ_TYPE == _FIX_FREQ_44_1KHZ)

    // Set S __code for 44.1kHz
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_12_PORT_PAGE71_HDMI_SCAPR, _HDMI_SAMPLING_FREQ_44K_GROUP_S_CODE);

    // Set D __code for 44.1kHz
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_13_PORT_PAGE71_HDMI_DCAPR0, HIBYTE(_HDMI_SAMPLING_FREQ_44K_GROUP_D_CODE));
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_14_PORT_PAGE71_HDMI_DCAPR1, LOBYTE(_HDMI_SAMPLING_FREQ_44K_GROUP_D_CODE));

#else // _FIX_SAMPLING_FREQ_TYPE == _FIX_FREQ_48KHZ

    // Set S __code for 48kHz
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_12_PORT_PAGE71_HDMI_SCAPR, _HDMI_SAMPLING_FREQ_48K_GROUP_S_CODE);

    // Set D __code for 48kHz
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_13_PORT_PAGE71_HDMI_DCAPR0, HIBYTE(_HDMI_SAMPLING_FREQ_48K_GROUP_D_CODE));
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_14_PORT_PAGE71_HDMI_DCAPR1, LOBYTE(_HDMI_SAMPLING_FREQ_48K_GROUP_D_CODE));

#endif

    // Set Double Buffer bit
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_10_PORT_PAGE71_HDMI_CMCR, ~_BIT4, _BIT4);

    // Load D __code
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~_BIT6, _BIT6);
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~_BIT6, 0x00);

#else

    // Disable Auto Load S Code
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_8A_PORT_PAGE71_AUDIO_FREQDET, ~_BIT6, 0x00);

    // Set S __code for 32kHz
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_12_PORT_PAGE71_HDMI_SCAPR, _HDMI_SAMPLING_FREQ_32K_GROUP_S_CODE);

    // Set D __code for 32kHz
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_13_PORT_PAGE71_HDMI_DCAPR0, HIBYTE(_HDMI_SAMPLING_FREQ_32K_GROUP_D_CODE));
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_14_PORT_PAGE71_HDMI_DCAPR1, LOBYTE(_HDMI_SAMPLING_FREQ_32K_GROUP_D_CODE));

    // Set Double Buffer bit
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_10_PORT_PAGE71_HDMI_CMCR, ~_BIT4, _BIT4);

    // Load D __code
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~_BIT6, _BIT6);
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~_BIT6, 0x00);

    // Set S __code for auto load mode
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_95_PORT_PAGE71_PRESET_S_CODE0, _HDMI_SAMPLING_FREQ_32K_GROUP_S_CODE);
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_96_PORT_PAGE71_PRESET_S_CODE1, _HDMI_SAMPLING_FREQ_44K_GROUP_S_CODE);
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_97_PORT_PAGE71_PRESET_S_CODE2, _HDMI_SAMPLING_FREQ_48K_GROUP_S_CODE);

    // Set D __code for auto load mode
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_99_PORT_PAGE71_PRESET_D_CODE_0, HIBYTE(_HDMI_SAMPLING_FREQ_32K_GROUP_D_CODE));
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_9A_PORT_PAGE71_PRESET_D_CODE_1, LOBYTE(_HDMI_SAMPLING_FREQ_32K_GROUP_D_CODE));
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_9B_PORT_PAGE71_PRESET_D_CODE_2, HIBYTE(_HDMI_SAMPLING_FREQ_44K_GROUP_D_CODE));
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_9C_PORT_PAGE71_PRESET_D_CODE_3, LOBYTE(_HDMI_SAMPLING_FREQ_44K_GROUP_D_CODE));
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_9D_PORT_PAGE71_PRESET_D_CODE_4, HIBYTE(_HDMI_SAMPLING_FREQ_48K_GROUP_D_CODE));
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_9E_PORT_PAGE71_PRESET_D_CODE_5, LOBYTE(_HDMI_SAMPLING_FREQ_48K_GROUP_D_CODE));

    // Enable Auto Load S Code
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_8A_PORT_PAGE71_AUDIO_FREQDET, ~_BIT6, _BIT6);

    // Set Double Buffer bit
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_10_PORT_PAGE71_HDMI_CMCR, ~_BIT4, _BIT4);

#endif // End of #if(_AUDIO_MANUAL_SAMPLING_FREQ_SUPPORT == _ON)

    // Enable Audio Freq Detect, Disable Samping Freq. Change INT
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_8A_PORT_PAGE71_AUDIO_FREQDET, ~(_BIT7 | _BIT3 | _BIT1 | _BIT0), _BIT7);

    // Enable SPDIF/I2S Output
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_62_PORT_PAGE71_HDMI_AOCR, 0xFF);

    CLR_AUDIO_HDMI_ICODE_RELOADED(ucPort);
}
//--------------------------------------------------
// Description  : Load initial I Code
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerAudioHdmiLoadInitialICode(BYTE ucPort)
{
    // Set high byte of I __code for boundary tracking for HDMI audio
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_24_PORT_PAGE71_HDMI_ICBPSR0, HIBYTE(_INITIAL_I_CODE));

    // Set low byte of I __code for boundary tracking for HDMI audio
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_25_PORT_PAGE71_HDMI_ICBPSR1, LOBYTE(_INITIAL_I_CODE));

    DebugMessageAudio("Load initial I code", _INITIAL_I_CODE);
}
//--------------------------------------------------
// Description  : Timer Event to Load Stable I Code
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerAudioHdmiLoadStableICodeEvent(BYTE ucPort)
{
    // Set high byte of I __code for boundary tracking
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_24_PORT_PAGE71_HDMI_ICBPSR0, HIBYTE(_STABLE_I_CODE));

    // Set low byte of I __code for boundary tracking
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_25_PORT_PAGE71_HDMI_ICBPSR1, LOBYTE(_STABLE_I_CODE));

    DebugMessageAudio("Load stable I code", _STABLE_I_CODE);
}
//--------------------------------------------------
// Description  : Detect HDMI Audio Sampling Freq
// Input Value  : None
// Output Value : Audio Sampling Freq
//--------------------------------------------------
EnumAudioSamplingFreqType ScalerAudioHdmiSamplingFreqDetect(BYTE ucPort)
{
    EnumAudioSamplingFreqType enumAudioFreq = _AUDIO_FREQ_NO_AUDIO;

#if(_INTERNAL_AUDIO_TEST_SUPPORT == _ON)
    if(ScalerAudioHdmiGetInternalAudioGenEnable(ucPort) == _ENABLE)
    {
        // For Audio test pattern
        SET_AUDIO_HDMI_SAMPLING_FREQ(ucPort, _AUDIO_FREQ_48K);
        return _AUDIO_FREQ_48K;
    }
#endif

    enumAudioFreq = AudioHdmiGetDpBit(ucPort, _P71_CA_PT_8B_PORT_PAGE71_AUDIO_FREQ_RESULT, (_BIT3 | _BIT2 | _BIT1 | _BIT0));

#if(_EMBEDDED_DAC_SUPPORT == _ON)
    if(enumAudioFreq != GET_AUDIO_HDMI_SAMPLING_FREQ(ucPort))
    {
        if(enumAudioFreq <= _AUDIO_FREQ_64K)
        {
            ScalerSetBit(P6_D4_DA_CLK_CTRL, ~(_BIT7 | _BIT6), 0x00);
        }
        else if(enumAudioFreq <= _AUDIO_FREQ_128K)
        {
            ScalerSetBit(P6_D4_DA_CLK_CTRL, ~(_BIT7 | _BIT6), _BIT6);
        }
        else
        {
            ScalerSetBit(P6_D4_DA_CLK_CTRL, ~(_BIT7 | _BIT6), _BIT7);
        }
    }
#endif

    SET_AUDIO_HDMI_SAMPLING_FREQ(ucPort, enumAudioFreq);

    return enumAudioFreq;
}

//--------------------------------------------------
// Description  : Initial D3 Auido PLL Settings
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerAudioHdmiSetAudioPLL(BYTE ucPort)
{
    // DPLL power down
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_38_PORT_PAGE71_HDMI_DPCR0, ~_BIT7, _BIT7);

    // Set M __code
    AudioHdmiSetDpByte(ucPort, _P71_CA_PT_11_PORT_PAGE71_HDMI_MCAPR, (_AUDIO_PLL_M - 2));

    // Set O __code
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_38_PORT_PAGE71_HDMI_DPCR0, ~(_BIT5 | _BIT4), 0x00);

    // Set K __code and enable double buffer
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_10_PORT_PAGE71_HDMI_CMCR, ~(_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT4 | ((_AUDIO_PLL_K - 2) & 0x0F)));

    // Initial VCO Band = 10
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_3A_PORT_PAGE71_HDMI_DPCR2, ~(_BIT4 | _BIT3), _BIT4);

    // Set MN PLL Path1 => [2]: 1 = Path1, 0 = Path2
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_3A_PORT_PAGE71_HDMI_DPCR2, ~(_BIT7 | _BIT2), _BIT2);

#if(_HW_PLL_EDGE_SELECT_TYPE == _PLL_EDGE_GEN_1_DEFAULT_POSITIVE)
    // Set PLL Edge = Negative
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_3F_PORT_PAGE71_DPLL_LDO, ~_BIT1, _BIT1);
#endif

    // DPLL VCORSTB Set to Normal
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_3B_PORT_PAGE71_HDMI_DPCR3, ~_BIT0, _DPLL_VCORSTB_NORMAL_VALUE);

    // DPLL power up
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_38_PORT_PAGE71_HDMI_DPCR0, ~_BIT7, 0x00);

    // Delay 2000us
    ScalerTimerDelayXms(2);

    // DPLL CMP enable
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_38_PORT_PAGE71_HDMI_DPCR0, ~_BIT0, _BIT0);

    // Delay 1000us
    ScalerTimerDelayXms(2);

    // DPLL latch calibration enable
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_38_PORT_PAGE71_HDMI_DPCR0, ~_BIT1, _BIT1);

    // Delay 1000us
    ScalerTimerDelayXms(2);

    // DPLL calibration validated
    AudioHdmiSetDpBit(ucPort, _P71_CA_PT_38_PORT_PAGE71_HDMI_DPCR0, ~_BIT2, _BIT2);
}
//--------------------------------------------------
// Description  : D3 Audio Watch Dog Proc
// Input Value  : bOn
// Output Value : None
//--------------------------------------------------
void ScalerAudioHdmiWatchDogProc(BYTE ucPort, bit bOn)
{
    if(bOn == _ON)
    {
        // Clear audio FIFO overflow and underflow status
        AudioHdmiSetSr(ucPort, ~(_BIT2 | _BIT1), (_BIT2 | _BIT1));

        // Enable Audio Watch Dog for FIFO Overflow/Underflow
        AudioHdmiSetDpBit(ucPort, _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~(_BIT2 | _BIT1), (_BIT2 | _BIT1));
    }
    else
    {
        // Disable Audio Watch Dog for FIFO Overflow/Underflow
        AudioHdmiSetDpBit(ucPort, _P71_CA_PT_31_PORT_PAGE71_HDMI_WDCR0, ~(_BIT2 | _BIT1), 0x00);
    }
}

#if(_INTERNAL_AUDIO_TEST_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Get Whether Internal Audio Pattern Gen is Enabled
// Input Value  : None
// Output Value : _ENABLE or _DISABLE
//--------------------------------------------------
bit ScalerAudioHdmiGetInternalAudioGenEnable(BYTE ucPort)
{
    if(AudioHdmiGetDpBit(ucPort, _P71_CA_PT_03_PORT_PAGE71_HDMI_AFCR, _BIT4) == _BIT4)
    {
        return _ENABLE;
    }
    else
    {
        return _DISABLE;
    }
}
//--------------------------------------------------
// Description  : D3 Auido Speaker Testing Process
// Input Value  : Enable or Disable
// Output Value : None
//--------------------------------------------------
void ScalerAudioHdmiInternalAudioGenSwitch(BYTE ucPort, bit bOn)
{
    if(bOn == _ON)
    {
        DebugMessageAudio("HDMI Audio Test On", AudioHdmiGetDpBit(ucPort, _P71_CA_PT_03_PORT_PAGE71_HDMI_AFCR, _BIT4));

        // Disable audio FIFO and Enable audio internal generator
        AudioHdmiSetDpBit(ucPort, _P71_CA_PT_03_PORT_PAGE71_HDMI_AFCR, ~(_BIT6 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), _BIT4);

        // Disbale DPLL Freq. Tuning
        AudioHdmiSetDpBit(ucPort, _P71_CA_PT_3A_PORT_PAGE71_HDMI_DPCR2, ~_BIT1, 0x00);

        // Set S __code
        AudioHdmiSetDpByte(ucPort, _P71_CA_PT_12_PORT_PAGE71_HDMI_SCAPR, _HDMI_SAMPLING_FREQ_48K_GROUP_S_CODE);

        // Set D __code
        AudioHdmiSetDpByte(ucPort, _P71_CA_PT_13_PORT_PAGE71_HDMI_DCAPR0, HIBYTE(_HDMI_SAMPLING_FREQ_48K_GROUP_D_CODE));
        AudioHdmiSetDpByte(ucPort, _P71_CA_PT_14_PORT_PAGE71_HDMI_DCAPR1, LOBYTE(_HDMI_SAMPLING_FREQ_48K_GROUP_D_CODE));

        // Disable sample freq. detection and auto load S code / D __code
        AudioHdmiSetDpBit(ucPort, _P71_CA_PT_8A_PORT_PAGE71_AUDIO_FREQDET, ~(_BIT7 | _BIT6), 0x00);

        // Enable double buffer
        AudioHdmiSetDpBit(ucPort, _P71_CA_PT_10_PORT_PAGE71_HDMI_CMCR, ~_BIT4, _BIT4);

        ScalerAudioDigitalOutputMute(_OFF);
    }
    else
    {
        DebugMessageAudio("HDMI Aduio Test Off", AudioHdmiGetDpBit(ucPort, _P71_CA_PT_03_PORT_PAGE71_HDMI_AFCR, _BIT4));

        ScalerAudioDigitalOutputMute(_ON);

        // Enable sample freq. detection and auto load S __code
        AudioHdmiSetDpBit(ucPort, _P71_CA_PT_8A_PORT_PAGE71_AUDIO_FREQDET, ~(_BIT7 | _BIT6), (_BIT7 | _BIT6));

        // Enable double buffer
        AudioHdmiSetDpBit(ucPort, _P71_CA_PT_10_PORT_PAGE71_HDMI_CMCR, ~_BIT4, _BIT4);

        // Enable DPLL Freq. Tuning
        AudioHdmiSetDpBit(ucPort, _P71_CA_PT_3A_PORT_PAGE71_HDMI_DPCR2, ~_BIT1, _BIT1);

        // Enable audio FIFO and Disable audio internal generator
        AudioHdmiSetDpBit(ucPort, _P71_CA_PT_03_PORT_PAGE71_HDMI_AFCR, ~(_BIT6 | _BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT6 | _BIT2 | _BIT1));
    }
}
#endif

#endif
#endif

#if(_LINE_IN_SUPPORT == _ON)
//--------------------------------------------------
// Description  : Initial ADC Auido PLL Settings
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerAudioSetADCAudioPLL(void)
{
    // DPLL power down
    ScalerSetBit(PBF_BD_MN_SCLKG_PLL_PWR, ~_BIT7, _BIT7);

    // Set ADC PLL input clock
    ScalerSetBit(PBF_A0_MN_SCLKG_CTRL, ~(_BIT7 | _BIT6), 0x00);

    // Set M __code
    ScalerSetBit(PBF_A0_MN_SCLKG_CTRL, ~(_BIT1 | _BIT0), 0x00);
    ScalerSetByte(PBF_A1_MN_SCLKG_DIVM, 0x33);

    // Set S __code
    ScalerSetByte(PBF_A3_MN_SCLKG_DIVS, 0x08);

    // Set Double Buffer
    ScalerSetBit(PBF_A0_MN_SCLKG_CTRL, ~_BIT4, _BIT4);

    // Enable SDM
    ScalerSetBit(PBF_B8_MN_SCLKG_SDM_CTRL, ~_BIT4, _BIT4);

    // Set Offset
    ScalerSetBit(PBF_A4_MN_SCLKG_OFFS_H, ~(_BIT2 | _BIT1 | _BIT0), 0x01);
    ScalerSetByte(PBF_A5_MN_SCLKG_OFFS_M, 0x29);
    ScalerSetByte(PBF_A6_MN_SCLKG_OFFS_L, 0xB5);

    // Load Offset
    ScalerSetBit(PBF_A4_MN_SCLKG_OFFS_H, ~_BIT7, _BIT7);

    // Initial DPLL VCO Band
    ScalerSetBit(PBF_BF_MN_SCLKG_PLL_WD, ~(_BIT4 | _BIT3), _BIT4);

    // Set MN PLL Path1 => [2]: 1 = Path1, 0 = Path2
    ScalerSetBit(PBF_BF_MN_SCLKG_PLL_WD, ~(_BIT7 | _BIT2), _BIT2);

#if(_HW_PLL_EDGE_SELECT_TYPE == _PLL_EDGE_GEN_1_DEFAULT_POSITIVE)
    // Set PLL Edge = Negative
    ScalerSetBit(PBF_C1_MN_SCLKG_PLL_RESERVE, ~_BIT1, _BIT1);
#endif

    // DPLL VCORSTB Set to Normal
    ScalerSetBit(PBF_C0_MN_SCLKG_PLL_INSEL, ~_BIT0, _DPLL_VCORSTB_NORMAL_VALUE);

    // DPLL power up
    ScalerSetBit(PBF_BD_MN_SCLKG_PLL_PWR, ~_BIT7, 0x00);

    // Delay 2000us
    ScalerTimerDelayXms(2);

    // DPLL CMP enable
    ScalerSetBit(PBF_BD_MN_SCLKG_PLL_PWR, ~_BIT2, _BIT2);

    // Delay 1000us
    ScalerTimerDelayXms(2);

    // DPLL latch calibration enable
    ScalerSetBit(PBF_BD_MN_SCLKG_PLL_PWR, ~_BIT3, _BIT3);

    // Delay 1000us
    ScalerTimerDelayXms(2);

    // DPLL calibration validated
    ScalerSetBit(PBF_BD_MN_SCLKG_PLL_PWR, ~_BIT4, _BIT4);
}
#endif

#if(_SLEEP_AUDIO_SUPPORT == _ON)
#if((_DP_SUPPORT == _ON) && ((_PS_AUDIO_INPUT == _PS_AUDIO_BOTH) || (_PS_AUDIO_INPUT == _PS_AUDIO_DP)))
//--------------------------------------------------
// Description  : Get Dp audio Status for Sleep Audio
// Input Value  : Input Port
// Output Value : _TRUE or _FALSE
//--------------------------------------------------
bit ScalerAudioGetDpStandaloneAudioStatus(BYTE ucInputPort)
{
    return ((ScalerAudioGetDigitalAudioSource(ucInputPort) == _DIGITAL_AUDIO_SOURCE_DP) ? _TRUE : _FALSE);
}
#endif
#endif

#endif // End of #if(_AUDIO_SUPPORT == _ON)
