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
// ID Code      : ScalerAudio_SeptPhyInclude.h No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#if(_AUDIO_SUPPORT == _ON)

//****************************************************************************
// LAYER DEFINITIONS / MACROS
//****************************************************************************
//----------------------------------------------------------------------------
// Definition of VCO Frequency of Audio PLL With Frequency Up
//----------------------------------------------------------------------------
#define _AUDIO_PLL_VCO                              378000 // 1KHz,

//----------------------------------------------------------------------------
// Definition of Offset of Audio PLL With Path1 and Frequency Up
//----------------------------------------------------------------------------
#define _HDMI_SAMPLING_FREQ_32K_GROUP_D_CODE        0xD847
#define _HDMI_SAMPLING_FREQ_44K_GROUP_D_CODE        0x2CC8
#define _HDMI_SAMPLING_FREQ_48K_GROUP_D_CODE        0xD847

#define _DP_SAMPLING_FREQ_32K_GROUP_D_CODE          0x29E0
#define _DP_SAMPLING_FREQ_44K_GROUP_D_CODE          0xD334
#define _DP_SAMPLING_FREQ_48K_GROUP_D_CODE          0x29E0

//****************************************************************************
// STRUCT / TYPE / ENUM DEFINITTIONS
//****************************************************************************


//****************************************************************************
// VARIABLE EXTERN
//****************************************************************************


//****************************************************************************
// FUNCTION EXTERN
//****************************************************************************

#if(_DP_SUPPORT == _ON)
extern bit ScalerAudioDPGetMuteProc(BYTE ucInputPort);
extern void ScalerAudioDpAudioEnable(bit bEnable, BYTE ucInputPort);
extern void ScalerAudioDpAudioEnable_EXINT0(bit bEnable, BYTE ucInputPort);

#if(_D0_DP_EXIST == _ON)
extern void ScalerAudioD0DPAudioInitial(void);
extern void ScalerAudioD0DPDigitalOutputProc(bit bEnable);
extern void ScalerAudioD0DPSetDVCWindowSize(bit bAdjustType, EnumAudioSamplingFreqPacket enumSamplingFreqPacket);
#endif

#if(_D1_DP_EXIST == _ON)
extern void ScalerAudioD1DPAudioInitial(void);
extern void ScalerAudioD1DPDigitalOutputProc(bit bEnable);
extern void ScalerAudioD1DPSetDVCWindowSize(bit bAdjustType, EnumAudioSamplingFreqPacket enumSamplingFreqPacket);
#endif

#endif

#if(_HDMI_SUPPORT == _ON)
#if((_D2_HDMI_SUPPORT == _ON) && (_D3_HDMI_SUPPORT == _ON))
extern void ScalerAudioHdmiDigitalDetectProc(BYTE ucPort);
extern bit ScalerAudioHdmiGetAudioDetected(BYTE ucPort);
extern void ScalerAudioHdmiAudioInitial(BYTE ucPort);
extern void ScalerAudioHdmiLoadInitialICode(BYTE ucPort);
extern void ScalerAudioHdmiLoadStableICodeEvent(BYTE ucPort);
extern EnumAudioSamplingFreqType ScalerAudioHdmiSamplingFreqDetect(BYTE ucPort);
extern void ScalerAudioHdmiSetAudioPLL(BYTE ucPort);
extern void ScalerAudioHdmiWatchDogProc(BYTE ucPort, bit bOn);

#if(_INTERNAL_AUDIO_TEST_SUPPORT == _ON)
extern bit ScalerAudioHdmiGetInternalAudioGenEnable(BYTE ucPort);
extern void ScalerAudioHdmiInternalAudioGenSwitch(BYTE ucPort, bit bOn);
#endif

#endif
#endif

#if(_LINE_IN_SUPPORT == _ON)
extern void ScalerAudioSetADCAudioPLL(void);
#endif

#endif
