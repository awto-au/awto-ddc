/********************************************************************************/
/*   The  Software  is  proprietary,  confidential,  and  valuable to Realtek   */
/*   Semiconductor  Corporation  ("Realtek").  All  rights, including but not   */
/*   limited  to  copyrights,  patents,  trademarks, trade secrets, mask work   */
/*   rights, and other similar rights and interests, are reserved to Realtek.   */
/*   Without  prior  written  consent  from  Realtek,  copying, reproduction,   */
/*   modification,  distribution,  or  otherwise  is strictly prohibited. The   */
/*   Software  shall  be  kept  strictly  in  confidence,  and  shall  not be   */
/*   disclosed to or otherwise accessed by any third party.                     */
/*   c<2003> - <2011>                                                           */
/*   The Software is provided "AS IS" without any warranty of any kind,         */
/*   express, implied, statutory or otherwise.                                  */
/********************************************************************************/

//----------------------------------------------------------------------------------------------------
// ID Code      : RL6449_Series_AudioInclude.h No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#if(_AUDIO_SUPPORT == _ON)

//****************************************************************************
// LAYER DEFINITIONS / MACROS
//****************************************************************************
#if(_D0_DP_EXIST == _ON)
#define GET_AUDIO_D0_ICODE_RELOADED()               (bit)(g_stAudioD0DigtalInfo.b1AudioICodeReloaded)
#define SET_AUDIO_D0_ICODE_RELOADED()               (g_stAudioD0DigtalInfo.b1AudioICodeReloaded = _TRUE)
#define CLR_AUDIO_D0_ICODE_RELOADED()               (g_stAudioD0DigtalInfo.b1AudioICodeReloaded = _FALSE)

#define GET_AUDIO_D0_SAMPLING_FREQ()                (g_stAudioD0DigtalInfo.b4AudioSamplingFreq)
#define SET_AUDIO_D0_SAMPLING_FREQ(x)               (g_stAudioD0DigtalInfo.b4AudioSamplingFreq = (x))

#define GET_AUDIO_D0_PACKET_DETECT()                (bit)(g_stAudioD0DigtalInfo.b1AudioDetected)
#define SET_AUDIO_D0_PACKET_DETECT()                (g_stAudioD0DigtalInfo.b1AudioDetected = _TRUE)
#define CLR_AUDIO_D0_PACKET_DETECT()                (g_stAudioD0DigtalInfo.b1AudioDetected = _FALSE)

#define GET_D0_DIGITAL_AUDIO_SOURCE()               (g_stAudioD0DigtalInfo.b2AudioDigitalSource)
#define SET_D0_DIGITAL_AUDIO_SOURCE(x)              (g_stAudioD0DigtalInfo.b2AudioDigitalSource = (x))
#endif

#if(_D1_DP_EXIST == _ON)
#define GET_AUDIO_D1_ICODE_RELOADED()               (bit)(g_stAudioD1DigtalInfo.b1AudioICodeReloaded)
#define SET_AUDIO_D1_ICODE_RELOADED()               (g_stAudioD1DigtalInfo.b1AudioICodeReloaded = _TRUE)
#define CLR_AUDIO_D1_ICODE_RELOADED()               (g_stAudioD1DigtalInfo.b1AudioICodeReloaded = _FALSE)

#define GET_AUDIO_D1_SAMPLING_FREQ()                (g_stAudioD1DigtalInfo.b4AudioSamplingFreq)
#define SET_AUDIO_D1_SAMPLING_FREQ(x)               (g_stAudioD1DigtalInfo.b4AudioSamplingFreq = (x))

#define GET_AUDIO_D1_PACKET_DETECT()                (bit)(g_stAudioD1DigtalInfo.b1AudioDetected)
#define SET_AUDIO_D1_PACKET_DETECT()                (g_stAudioD1DigtalInfo.b1AudioDetected = _TRUE)
#define CLR_AUDIO_D1_PACKET_DETECT()                (g_stAudioD1DigtalInfo.b1AudioDetected = _FALSE)

#define GET_D1_DIGITAL_AUDIO_SOURCE()               (g_stAudioD1DigtalInfo.b2AudioDigitalSource)
#define SET_D1_DIGITAL_AUDIO_SOURCE(x)              (g_stAudioD1DigtalInfo.b2AudioDigitalSource = (x))
#endif

#if((_D2_HDMI_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON))
#define _AUDIO_HDMI_D2                              0
#define _AUDIO_HDMI_D3                              1
#define AUDIO_HDMI_SEL(ucPort, d2, d3)              ((ucPort) ? (d3) : (d2))
#define AUDIO_HDMI_REG(ucPort, usAddrD2)            ((WORD)(usAddrD2) + ((WORD)(ucPort) << 8))

#define GET_AUDIO_HDMI_ICODE_RELOADED(p)            (bit)(g_astAudioHdmiInfo[p].b1AudioICodeReloaded)
#define SET_AUDIO_HDMI_ICODE_RELOADED(p)            (g_astAudioHdmiInfo[p].b1AudioICodeReloaded = _TRUE)
#define CLR_AUDIO_HDMI_ICODE_RELOADED(p)            (g_astAudioHdmiInfo[p].b1AudioICodeReloaded = _FALSE)

#define GET_AUDIO_HDMI_SAMPLING_FREQ(p)             (g_astAudioHdmiInfo[p].b4AudioSamplingFreq)
#define SET_AUDIO_HDMI_SAMPLING_FREQ(p, x)          (g_astAudioHdmiInfo[p].b4AudioSamplingFreq = (x))

#define GET_AUDIO_HDMI_PACKET_DETECT(p)             (bit)(g_astAudioHdmiInfo[p].b1AudioDetected)
#define SET_AUDIO_HDMI_PACKET_DETECT(p)             (g_astAudioHdmiInfo[p].b1AudioDetected = _TRUE)
#define CLR_AUDIO_HDMI_PACKET_DETECT(p)             (g_astAudioHdmiInfo[p].b1AudioDetected = _FALSE)

#define GET_AUDIO_HDMI_DIGITAL_SOURCE(p)            (g_astAudioHdmiInfo[p].b2AudioDigitalSource)
#define SET_AUDIO_HDMI_DIGITAL_SOURCE(p, x)         (g_astAudioHdmiInfo[p].b2AudioDigitalSource = (x))
#endif

//****************************************************************************
// STRUCT / TYPE / ENUM DEFINITTIONS
//****************************************************************************


//****************************************************************************
// VARIABLE EXTERN
//****************************************************************************
#if(_D0_DP_EXIST == _ON)
extern StructAudioDigitalInfo g_stAudioD0DigtalInfo;
#endif

#if(_D1_DP_EXIST == _ON)
extern StructAudioDigitalInfo g_stAudioD1DigtalInfo;
#endif

#if((_D2_HDMI_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON))
extern StructAudioDigitalInfo g_astAudioHdmiInfo[2];
#endif

//****************************************************************************
// FUNCTION EXTERN
//****************************************************************************
extern void ScalerAudioDigitalAudioInitial(void);
extern void ScalerAudioDisableAudioPLL(void);
extern EnumAudioSamplingFreqPacket ScalerAudioSamplingFreqDetect(BYTE ucInputPort);
extern void ScalerAudioDigitalOutputMute(bit bMute);
extern void ScalerAudioWatchDogProc(bit bOn, BYTE ucInputPort);
extern void ScalerAudioLoadStableICodeEvent(EnumScalerTimerEventID enumEventID);
extern EnumSourceSearchPort ScalerAudioGetDigitalAudioPortMapping(void);

#if(_DP_SUPPORT == _ON)

#if(_D0_DP_EXIST == _ON)
#endif

#if(_D1_DP_EXIST == _ON)
extern void ScalerAudioD1SetAudioPLL(void);
#endif
#endif

#if(_SLEEP_AUDIO_SUPPORT == _ON)
#if((_DP_SUPPORT == _ON) && ((_PS_AUDIO_INPUT == _PS_AUDIO_BOTH) || (_PS_AUDIO_INPUT == _PS_AUDIO_DP)))
extern BYTE ScalerAudioGetDigitalAudioSource(BYTE ucInputPort);
#endif
#endif

#endif // End of #if(_AUDIO_SUPPORT == _ON)
