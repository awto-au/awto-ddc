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
// Color Default Value
//----------------------------------------------------------------------------------------------------
#include "ColorDitherDefault.h"
#include "ColorTempDefault.h"

#ifdef __USER_PANEL__

#if(_DCC_FUNCTION == _ON)
//----------------------------------------------------------------------------------------------------
// DCC Table
//----------------------------------------------------------------------------------------------------
BYTE __code tDCC_GAME[] =
{
#include "./DCC/DccModeGame.h"
};

BYTE __code tDCC_MOVIE[] =
{
#include "./DCC/DccModeMovie.h"
};

BYTE __code tDCC_PHOTO[] =
{
#include "./DCC/DccModePhoto.h"
};

BYTE __code tDCC_VIVID[] =
{
#include "./DCC/DccModeVivid.h"
};

BYTE __code * __code tDCC_TABLE[] =
{
    NULL,  // Standard
    tDCC_GAME,
    tDCC_MOVIE,
    tDCC_PHOTO,
    tDCC_VIVID,
};
#endif // End of #if(_DCC_FUNCTION == _ON)

#if(_ICM_SUPPORT == _ON)
//----------------------------------------------------------------------------------------------------
// ICM Table
//----------------------------------------------------------------------------------------------------
BYTE __code tICM_GAME[] =
{
#include "./ICM/IcmModeGame.h"
};

BYTE __code tICM_MOVIE[] =
{
#include "./ICM/IcmModeMovie.h"
};

BYTE __code tICM_PHOTO[] =
{
#include "./ICM/IcmModePhoto.h"
};

BYTE __code tICM_VIVID[] =
{
#include "./ICM/IcmModeVivid.h"
};

BYTE __code * __code tICM_TABLE[] =
{
    NULL,  // Standard
    tICM_GAME,
    tICM_MOVIE,
    tICM_PHOTO,
    tICM_VIVID,
};

//----------------------------------------------------------------------------------------------------
// SCM Table
//----------------------------------------------------------------------------------------------------
BYTE __code tSCM_VIVID[] =
{
#include "./ICM/ScmModeVivid.h"
};

BYTE __code * __code tSCM_TABLE[] =
{
    NULL,  // Standard
    NULL,  // Game
    NULL,  // Movie
    NULL,  // Photo
    tSCM_VIVID,
};

#endif // End of #if(_ICM_SUPPORT == _ON)



#if(_OD_SUPPORT == _ON)
//----------------------------------------------------------------------------------------------------
// OD Table
//----------------------------------------------------------------------------------------------------
#include "ODTable.h"

BYTE __code * __code tOD_TABLE[] =
{
    tOD_TABLE_COMMON,
};

#if(_FREESYNC_SUPPORT == _ON)
BYTE __code * __code tOD_FREESYNC_TABLE[] =
{
    tOD_TABLE_FREESYNC,
};
#endif
#endif // End of #if(_OD_SUPPORT == _ON)

#if(_SDR_TO_HDR_SUPPORT == _ON)
BYTE __code tSDRTOHDR_INPUTGAMMA[] =
{
#include "./SDRtoHDR/SDRtoHDRInputGammaTable.h"
};

BYTE __code tSDRTOHDR_ICM[] =
{
#include "./SDRtoHDR/SDRtoHDRICMTable.h"
};

BYTE __code tSDRTOHDR_DCC[] =
{
#include "./SDRtoHDR/SDRtoHDRDCCTable.h"
};
#endif
#endif // End of #ifdef __USER_PANEL__

#ifdef __USER_COMMON_ADJUST__

//----------------------------------------------------------------------------------------------------
// Dithering Table
//----------------------------------------------------------------------------------------------------
#if(_I_DITHER_SUPPORT == _ON)
BYTE __code tIDITHER_TABLE_FIFO8[] =
{
#if((_IDITHER_TYPE == _IDITHER_GEN_0_1_SEQ_TRUNCATE_2_0_BIT) || (_IDITHER_TYPE == _IDITHER_GEN_2_1_SEQ_NO_TEMPO_TRUNCATE_2_0_BIT))
#include "./IDither/IDitherTableGen0Fifo8.h"
#elif((_IDITHER_TYPE == _IDITHER_GEN_1_4_SEQ_TRUNCATE_4_2_BIT) || (_IDITHER_TYPE == _IDITHER_GEN_3_4_SEQ_TRUNCATE_6_4_2_BIT))
#include "./IDither/IDitherTableGen1Fifo8.h"
#endif
};

BYTE __code tIDITHER_TABLE_FIFO10[] =
{
#if((_IDITHER_TYPE == _IDITHER_GEN_0_1_SEQ_TRUNCATE_2_0_BIT) || (_IDITHER_TYPE == _IDITHER_GEN_2_1_SEQ_NO_TEMPO_TRUNCATE_2_0_BIT))
#include "./IDither/IDitherTableGen0Fifo10.h"
#elif((_IDITHER_TYPE == _IDITHER_GEN_1_4_SEQ_TRUNCATE_4_2_BIT) || (_IDITHER_TYPE == _IDITHER_GEN_3_4_SEQ_TRUNCATE_6_4_2_BIT))
#include "./IDither/IDitherTableGen1Fifo10.h"
#endif
};

BYTE __code tIDITHER_SEQ_TABLE[] =
{
#if((_IDITHER_TYPE == _IDITHER_GEN_0_1_SEQ_TRUNCATE_2_0_BIT) || (_IDITHER_TYPE == _IDITHER_GEN_2_1_SEQ_NO_TEMPO_TRUNCATE_2_0_BIT))
#include "./IDither/IDitherTableSeq1.h"
#elif((_IDITHER_TYPE == _IDITHER_GEN_1_4_SEQ_TRUNCATE_4_2_BIT) || (_IDITHER_TYPE == _IDITHER_GEN_3_4_SEQ_TRUNCATE_6_4_2_BIT))
#if(((_I_DITHER_MULTI_SEQ_ENABLE == _DISABLE) && (_I_DITHER_SERIES_SEQ_ENABLE == _DISABLE)))
#include "./IDither/IDitherTableSeq1.h"
#else
#include "./IDither/IDitherTableSeq4.h"
#endif
#endif
};

#if((_IDITHER_TYPE == _IDITHER_GEN_0_1_SEQ_TRUNCATE_2_0_BIT) || (_IDITHER_TYPE == _IDITHER_GEN_1_4_SEQ_TRUNCATE_4_2_BIT) || (_IDITHER_TYPE == _IDITHER_GEN_3_4_SEQ_TRUNCATE_6_4_2_BIT))
BYTE __code tIDITHER_TEMPOFFSET_TABLE[] =
{
#include "./IDither/IDitherTableTempo.h"
};
#endif
#endif // End of #if(_I_DITHER_SUPPORT == _ON)

#if(_D_DITHER_SUPPORT == _ON)

#if((_PANEL_EXIST_MULTIPANEL == _OFF) && (_CUSTOMER != _CUS_MINDRAY))

BYTE __code tDDITHER_TABLE[] =
{
#if(_PANEL_DISP_BIT_MODE == _PANEL_DISP_18_BIT)

#if((_DDITHER_TYPE == _DDITHER_GEN_0_4BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_2_4_SEQ_NO_TEMPO_4BIT_DITHERTBL))
#include "./DDither/DDitherGen0Dither18Bit.h"
#elif(_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL)
#include "./DDither/DDitherGen1Dither30Bit.h"
#elif(_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2)
#include "./DDither/DDitherGen1Dither24Bit.h"
#endif

#elif(_PANEL_DISP_BIT_MODE == _PANEL_DISP_24_BIT)

#if((_DDITHER_TYPE == _DDITHER_GEN_0_4BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_2_4_SEQ_NO_TEMPO_4BIT_DITHERTBL))
#include "./DDither/DDitherGen0Dither24Bit.h"
#elif((_DDITHER_TYPE == _DDITHER_GEN_1_6BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL) || (_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2))
#include "./DDither/DDitherGen1Dither24Bit.h"
#endif

#elif(_PANEL_DISP_BIT_MODE == _PANEL_DISP_30_BIT)

#if((_DDITHER_TYPE == _DDITHER_GEN_0_4BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_2_4_SEQ_NO_TEMPO_4BIT_DITHERTBL))
#include "./DDither/DDitherGen0Dither30Bit.h"
#elif((_DDITHER_TYPE == _DDITHER_GEN_1_6BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL) || (_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2))
#include "./DDither/DDitherGen1Dither30Bit.h"
#endif

#endif
};

#else // Else of #if(_PANEL_EXIST_MULTIPANEL == _OFF)

#if(_DDITHER_TYPE != _DDITHER_GEN_1_6BIT_DITHERTBL)
BYTE __code tDDITHER_TABLE18Bit[] =
{
#if((_DDITHER_TYPE == _DDITHER_GEN_0_4BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_2_4_SEQ_NO_TEMPO_4BIT_DITHERTBL))
#include "./DDither/DDitherGen0Dither18Bit.h"
#elif(_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL)
#include "./DDither/DDitherGen1Dither30Bit.h"
#elif(_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2)
#include "./DDither/DDitherGen1Dither24Bit.h"
#endif
};
#endif

BYTE __code tDDITHER_TABLE24Bit[] =
{
#if((_DDITHER_TYPE == _DDITHER_GEN_0_4BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_2_4_SEQ_NO_TEMPO_4BIT_DITHERTBL))
#include "./DDither/DDitherGen0Dither24Bit.h"
#elif((_DDITHER_TYPE == _DDITHER_GEN_1_6BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL) || (_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2))
#include "./DDither/DDitherGen1Dither24Bit.h"
#endif
};

BYTE __code tDDITHER_TABLE30Bit[] =
{
#if((_DDITHER_TYPE == _DDITHER_GEN_0_4BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_2_4_SEQ_NO_TEMPO_4BIT_DITHERTBL))
#include "./DDither/DDitherGen0Dither30Bit.h"
#elif((_DDITHER_TYPE == _DDITHER_GEN_1_6BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL) || (_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2))
#include "./DDither/DDitherGen1Dither30Bit.h"
#endif
};

#endif

BYTE __code tDDITHER_SEQ_TABLE[] =
{
#if((_DDITHER_TYPE == _DDITHER_GEN_0_4BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_2_4_SEQ_NO_TEMPO_4BIT_DITHERTBL))
#if(_D_DITHER_MULTI_SEQ_ENABLE == _DISABLE)
#include "./DDither/DDitherGen0Seq1.h"
#else
#include "./DDither/DDitherGen0Seq4.h"
#endif
#elif((_DDITHER_TYPE == _DDITHER_GEN_1_6BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL) || (_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2))
#if(((_D_DITHER_MULTI_SEQ_ENABLE == _DISABLE) && (_D_DITHER_SERIES_SEQ_ENABLE == _DISABLE)) && (_D_DITHER_ADVANCE_SETTING_ENABLE != _ENABLE))
#include "./DDither/DDitherGen1Seq1.h"
#else
#include "./DDither/DDitherGen1Seq4.h"
#endif
#endif
};

#if((_DDITHER_TYPE == _DDITHER_GEN_0_4BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_1_6BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL) || (_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2))
BYTE __code tDDITHER_TEMPOFFSET_TABLE[] =
{
#if(_DDITHER_TYPE == _DDITHER_GEN_0_4BIT_DITHERTBL)
#include "./DDither/DDitherGen0Tempo.h"
#elif((_DDITHER_TYPE == _DDITHER_GEN_1_6BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL) || (_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2))
#include "./DDither/DDitherGen1Tempo.h"
#endif
};
#endif

#if((_DDITHER_TYPE == _DDITHER_GEN_1_6BIT_DITHERTBL) || (_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL) || (_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2))
#if(_D_DITHER_ADVANCE_SETTING_ENABLE == _ENABLE)
BYTE __code tDDITHER_REALIGN_TABLE[] =
{
#include "./DDither/DDitherGen1Realign.h"
};

BYTE __code tDDITHER_REALIGN_TEMPO_TABLE[] =
{
#include "./DDither/DDitherGen1RealignTempo.h"
};

#if((_PANEL_EXIST_MULTIPANEL == _OFF) && (_CUSTOMER != _CUS_MINDRAY))

BYTE __code tDDITHER_LSB_TABLE[] =
{
#if(_PANEL_DISP_BIT_MODE == _PANEL_DISP_18_BIT)
#if(_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL)
#include "./DDither/DDitherGen1LSB30Bit.h"
#elif(_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2)
#include "./DDither/DDitherGen1LSB24Bit.h"
#endif
#elif(_PANEL_DISP_BIT_MODE == _PANEL_DISP_24_BIT)
#include "./DDither/DDitherGen1LSB24Bit.h"
#elif(_PANEL_DISP_BIT_MODE == _PANEL_DISP_30_BIT)
#include "./DDither/DDitherGen1LSB30Bit.h"
#endif
};

BYTE __code tDDITHER_ADVANCE_SETTING_TABLE[] =
{
#if(_PANEL_DISP_BIT_MODE == _PANEL_DISP_18_BIT)
#if(_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL)
#include "./DDither/DDitherGen1AdvanceS418Bit.h"
#elif(_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2)
#include "./DDither/DDitherGen1AdvanceS218Bit.h"
#endif
#elif(_PANEL_DISP_BIT_MODE == _PANEL_DISP_24_BIT)
#include "./DDither/DDitherGen1Advance24Bit.h"
#elif(_PANEL_DISP_BIT_MODE == _PANEL_DISP_30_BIT)
#include "./DDither/DDitherGen1Advance30Bit.h"
#endif
};

#else // Else of #if(_PANEL_EXIST_MULTIPANEL == _OFF)

#if((_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL) || (_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2))
BYTE __code tDDITHER_LSB_TABLE18Bit[] =
{
#if(_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL)
#include "./DDither/DDitherGen1LSB30Bit.h"
#elif(_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2)
#include "./DDither/DDitherGen1LSB24Bit.h"
#endif
};
#endif

BYTE __code tDDITHER_LSB_TABLE24Bit[] =
{
#include "./DDither/DDitherGen1LSB24Bit.h"
};

BYTE __code tDDITHER_LSB_TABLE30Bit[] =
{
#include "./DDither/DDitherGen1LSB30Bit.h"
};

#if((_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL) || (_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2))
BYTE __code tDDITHER_ADVANCE_SETTING_TABLE18Bit[] =
{
#if(_DDITHER_TYPE == _DDITHER_GEN_3_6BIT_DITHERTBL_6BIT_PANEL)
#include "./DDither/DDitherGen1AdvanceS418Bit.h"
#elif(_DDITHER_TYPE == _DDITHER_GEN_4_6BIT_DITHERTBL_6BIT_PANEL_S2)
#include "./DDither/DDitherGen1AdvanceS218Bit.h"
#endif
};
#endif

BYTE __code tDDITHER_ADVANCE_SETTING_TABLE24Bit[] =
{
#include "./DDither/DDitherGen1Advance24Bit.h"
};

BYTE __code tDDITHER_ADVANCE_SETTING_TABLE30Bit[] =
{
#include "./DDither/DDitherGen1Advance30Bit.h"
};

#endif // End of #if(_PANEL_EXIST_MULTIPANEL == _OFF)

#endif
#endif
#endif

#endif // End of #ifdef __USER_COMMON_ADJUST__

#ifdef __USER_ADJUST_OUTPUT_GAMMA__

#if((_GAMMA_FUNCTION == _ON) && (_OGC_SUPPORT == _OFF))
//----------------------------------------------------------------------------------------------------
// Gamma Table
//----------------------------------------------------------------------------------------------------
#if(_USER_ADJUST_GAMMA_FOR_BEACON == _ON)
#if((_GAMMA_IN_FLASH_BANK == _ON) && (BEACON_GAMMA_TYPE != Gamma_default))

#else
#include "Gamma/GammaBeaconUse.h"
BYTE __code * __code tGAMMA_TABLE[] =
{
    tGAMMA_0,//No use._GAMMA_OFF
    tGAMMA_1,
    tGAMMA_2,
    tGAMMA_3,
    tGAMMA_4,
    tGAMMA_5,
    tGAMMA_6,
    tGAMMA_7,
    tGAMMA_8,
    tGAMMA_9,
    tGAMMA_10,
    tGAMMA_11,
    tGAMMA_12,
    tGAMMA_13,
    tGAMMA_14,
    tGAMMA_15,
    tGAMMA_16,
    tGAMMA_17,
    tGAMMA_18,
    tGAMMA_19,
    tGAMMA_20,
    tGAMMA_21,
};
#define USER_MAX_GAMMAS                  22
#endif
#else
BYTE __code tLUTGAMMA_18_TABLE[] =
{
#include "Gamma/Gamma18.h"
};

BYTE __code tLUTGAMMA_20_TABLE[] =
{
#include "Gamma/Gamma20.h"
};

BYTE __code tLUTGAMMA_22_TABLE[] =
{
#include "Gamma/Gamma22.h"
};

BYTE __code tLUTGAMMA_24_TABLE[] =
{
#include "Gamma/Gamma24.h"
};

BYTE __code * __code tGAMMA_TABLE[] =
{
    tLUTGAMMA_18_TABLE,
    tLUTGAMMA_20_TABLE,
    tLUTGAMMA_22_TABLE,
    tLUTGAMMA_24_TABLE,
};
#endif
#endif // End of #if(_GAMMA_FUNCTION == _ON)

#if(_PCM_FUNCTION == _ON)
//----------------------------------------------------------------------------------------------------
// PCM Table
//----------------------------------------------------------------------------------------------------
BYTE __code tPCM_USER_INPUT_GAMMA_TABLE[] =
{
#include "./PCM/PCMUserInputGammaTable.h"
};

BYTE __code tPCM_USER_MATRIX[] =
{
#include "./PCM/PCMUserColorMatrixTable.h"
};

BYTE __code tPCM_USER_OUTPUT_GAMMA_TABLE[] =
{
#include "./PCM/PCMUserOutputGammaTable.h"
};

BYTE __code * __code tPCM_USER_TABLE[] =
{
    tPCM_USER_INPUT_GAMMA_TABLE,    tPCM_USER_OUTPUT_GAMMA_TABLE,   tPCM_USER_MATRIX,
};
#endif // End of #if(_PCM_FUNCTION == _ON)

#endif // End of #ifdef __USER_ADJUST_OUTPUT_GAMMA__

#ifdef __USER_ADJUST_RGB_GAMMA__

#if(_RGB_GAMMA_FUNCTION == _ON)

BYTE __code tLUTRGBGAMMA_18_TABLE[] =
{
#include "Gamma/RGBGamma18.h"
};

BYTE __code tLUTRGBGAMMA_20_TABLE[] =
{
#include "Gamma/RGBGamma20.h"
};

BYTE __code tLUTRGBGAMMA_22_TABLE[] =
{
#include "Gamma/RGBGamma22.h"
};

BYTE __code tLUTRGBGAMMA_24_TABLE[] =
{
#include "Gamma/RGBGamma24.h"
};

BYTE __code * __code tRGBGAMMA_TABLE[] =
{
    tLUTRGBGAMMA_18_TABLE,
    tLUTRGBGAMMA_20_TABLE,
    tLUTRGBGAMMA_22_TABLE,
    tLUTRGBGAMMA_24_TABLE,
};
#endif// End of #if(_RGB_GAMMA_FUNCTION == _ON)

#endif // End of #ifdef __USER_ADJUST_RGB_GAMMA__


#ifdef __USER_ADJUST_3D_GAMMA__

#if(_RGB_3D_GAMMA == _ON)

BYTE __code tRGB3DGAMMA_MODE0_TABLE[] =
{
#include "Gamma/3DGammaMode0.h"
};

BYTE __code tRGB3DGAMMA_MODE1_TABLE[] =
{
#include "Gamma/3DGammaMode1.h"
};

BYTE __code * __code tRGB3DGAMMA_TABLE[] =
{
    tRGB3DGAMMA_MODE0_TABLE,
    tRGB3DGAMMA_MODE1_TABLE,
};

#endif // End of #if(_RGB_3D_GAMMA == _ON)
#endif // End of #ifdef __USER_ADJUST_3D_GAMMA__

#ifdef __USER_INTERFACE_HDR__
#if(_HDR10_LIGHT_ENHANCE_SUPPORT == _ON)
//----------------------------------------------------------------------------------------------------
// LightEnhance TABLE
//----------------------------------------------------------------------------------------------------
BYTE __code tDCC_LIGHTENHANCE_120_540_TABLE[] =
{
#include "./HDR/HDR10_LightEnhance_Type1_540nit_Table.h"
};

BYTE __code tDCC_LIGHTENHANCE_120_1200_TABLE[] =
{
#include "./HDR/HDR10_LightEnhance_Type1_1200nit_Table.h"
};

BYTE __code tDCC_LIGHTENHANCE_120_4000_TABLE[] =
{
#include "./HDR/HDR10_LightEnhance_Type1_4000nit_Table.h"
};

BYTE __code tDCC_LIGHTENHANCE_120_10000_TABLE[] =
{
#include "./HDR/HDR10_LightEnhance_Type1_10000nit_Table.h"
};

BYTE __code tDCC_LIGHTENHANCE_140_540_TABLE[] =
{
#include "./HDR/HDR10_LightEnhance_Type2_540nit_Table.h"
};

BYTE __code tDCC_LIGHTENHANCE_140_1200_TABLE[] =
{
#include "./HDR/HDR10_LightEnhance_Type2_1200nit_Table.h"
};

BYTE __code tDCC_LIGHTENHANCE_140_4000_TABLE[] =
{
#include "./HDR/HDR10_LightEnhance_Type2_4000nit_Table.h"
};

BYTE __code tDCC_LIGHTENHANCE_140_10000_TABLE[] =
{
#include "./HDR/HDR10_LightEnhance_Type2_10000nit_Table.h"
};

BYTE __code tDCC_LIGHTENHANCE_160_540_TABLE[] =
{
#include "./HDR/HDR10_LightEnhance_Type3_540nit_Table.h"
};

BYTE __code tDCC_LIGHTENHANCE_160_1200_TABLE[] =
{
#include "./HDR/HDR10_LightEnhance_Type3_1200nit_Table.h"
};

BYTE __code tDCC_LIGHTENHANCE_160_4000_TABLE[] =
{
#include "./HDR/HDR10_LightEnhance_Type3_4000nit_Table.h"
};

BYTE __code tDCC_LIGHTENHANCE_160_10000_TABLE[] =
{
#include "./HDR/HDR10_LightEnhance_Type3_10000nit_Table.h"
};

BYTE __code * __code tDCC_LIGHTENHANCE_120_TABLE[] =
{
    tDCC_LIGHTENHANCE_120_540_TABLE,
    tDCC_LIGHTENHANCE_120_1200_TABLE,
    tDCC_LIGHTENHANCE_120_4000_TABLE,
    tDCC_LIGHTENHANCE_120_10000_TABLE,
};

BYTE __code * __code tDCC_LIGHTENHANCE_140_TABLE[] =
{
    tDCC_LIGHTENHANCE_140_540_TABLE,
    tDCC_LIGHTENHANCE_140_1200_TABLE,
    tDCC_LIGHTENHANCE_140_4000_TABLE,
    tDCC_LIGHTENHANCE_140_10000_TABLE,
};

BYTE __code * __code tDCC_LIGHTENHANCE_160_TABLE[] =
{
    tDCC_LIGHTENHANCE_160_540_TABLE,
    tDCC_LIGHTENHANCE_160_1200_TABLE,
    tDCC_LIGHTENHANCE_160_4000_TABLE,
    tDCC_LIGHTENHANCE_160_10000_TABLE,
};
#endif

#if(_HDR10_COLOR_ENHANCE_SUPPORT == _ON)
BYTE __code tICM_COLORENHANCE_LEVEL1_TABLE[] =
{
#include "./HDR/HDR10_ColorEnhance_Level1_Table.h"
};

BYTE __code tICM_COLORENHANCE_LEVEL2_TABLE[] =
{
#include "./HDR/HDR10_ColorEnhance_Level2_Table.h"
};

BYTE __code tICM_COLORENHANCE_LEVEL3_TABLE[] =
{
#include "./HDR/HDR10_ColorEnhance_Level3_Table.h"
};

BYTE __code * __code tICM_COLORENHANCE_TABLE[] =
{
    tICM_COLORENHANCE_LEVEL1_TABLE,
    tICM_COLORENHANCE_LEVEL2_TABLE,
    tICM_COLORENHANCE_LEVEL3_TABLE,
};
#endif

#if(_HDR10_SUPPORT == _ON)
#if(_DCC_FUNCTION == _ON)
//----------------------------------------------------------------------------------------------------
// HDR10 DCC Table
//----------------------------------------------------------------------------------------------------
BYTE __code tDCC_HDR10_GAME[] =
{
#include "./DCC/DccModeGame.h"
};

BYTE __code tDCC_HDR10_MOVIE[] =
{
#include "./DCC/DccModeMovie.h"
};

BYTE __code tDCC_HDR10_PHOTO[] =
{
#include "./DCC/DccModePhoto.h"
};

BYTE __code tDCC_HDR10_VIVID[] =
{
#include "./DCC/DccModeVivid.h"
};

BYTE __code * __code tDCC_HDR10_TABLE[] =
{
    NULL,  // Standard
    tDCC_HDR10_GAME,
    tDCC_HDR10_MOVIE,
    tDCC_HDR10_PHOTO,
    tDCC_HDR10_VIVID,
};
#endif

#if(_ICM_SUPPORT == _ON)
//----------------------------------------------------------------------------------------------------
// HDR10 ICM Table
//----------------------------------------------------------------------------------------------------
BYTE __code tICM_HDR10_GAME[] =
{
#include "./ICM/IcmModeGame.h"
};

BYTE __code tICM_HDR10_MOVIE[] =
{
#include "./ICM/IcmModeMovie.h"
};

BYTE __code tICM_HDR10_PHOTO[] =
{
#include "./ICM/IcmModePhoto.h"
};

BYTE __code tICM_HDR10_VIVID[] =
{
#include "./ICM/IcmModeVivid.h"
};

BYTE __code * __code tICM_HDR10_TABLE[] =
{
    NULL,  // Standard
    tICM_HDR10_GAME,
    tICM_HDR10_MOVIE,
    tICM_HDR10_PHOTO,
    tICM_HDR10_VIVID,
};
#endif
#endif

#endif
