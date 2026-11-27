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
// ID Code      : ScalerDisplayDPTx.c No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

#define __SCALER_DISPLAY_DP_TX__

#include "ScalerFunctionInclude.h"
#include <stddef.h>

#if(_PANEL_STYLE == _PANEL_DPTX)

//****************************************************************************
// DEFINITIONS / MACROS
//****************************************************************************
#if(_DISPLAY_DP_TX_PORT_1 == _ON)
#define _DISPLAY_DP_TX1_TU_SIZE                          32
#endif

#if(_DISPLAY_DP_TX_PORT_2 == _ON)
#define _DISPLAY_DP_TX2_TU_SIZE                          32
#endif

//****************************************************************************
// STRUCT / TYPE / ENUM DEFINITTIONS
//****************************************************************************

//****************************************************************************
// CODE TABLES
//****************************************************************************

//****************************************************************************
// VARIABLE DECLARATIONS
//****************************************************************************
__xdata _Bool g_bDptxSscEn = 0;

#if(_DISPLAY_DP_TX_PORT_1 == _ON)
StructDownStreamInfo g_stDisplayDPTx1Info;
StructDPTxLTInfo g_stDisplayDPTx1LTInfo;
StructTimingInfo g_stDisplayDPTx1TimingInfo;
StructDisplayDPTxInputInfo g_stDisplayDPTx1InputInfo;
#endif

#if(_DISPLAY_DP_TX_PORT_2 == _ON)
StructDownStreamInfo g_stDisplayDPTx2Info;
StructDPTxLTInfo g_stDisplayDPTx2LTInfo;
StructTimingInfo g_stDisplayDPTx2TimingInfo;
StructDisplayDPTxInputInfo g_stDisplayDPTx2InputInfo;
#endif

//****************************************************************************
// FUNCTION DECLARATIONS
//****************************************************************************
#if(_DISPLAY_DP_TX_PORT_1 == _ON)
void ScalerDisplayDPTx1Initial(void);
bit ScalerDisplayDPTx1LinkConfig(void);
void ScalerDisplayDPTx1VideoStreamOutput(bit bOutput);
void ScalerDisplayDPTx1DisplayFormatSetting(void);
void ScalerDisplayDPTx1DisplayMSASetting(void);
void ScalerDisplayDPTx1LinkTraining(void);
void ScalerDisplayDPTx1TPInitialSet(void);
BYTE ScalerDisplayDPTx1TrainPattern1(void);
BYTE ScalerDisplayDPTx1TrainPattern2(void);
void ScalerDisplayDPTx1TrainPatternEnd(void);
static void ScalerDisplayDPTxLaneSetCurrent(BYTE __xdata *pucCur, BYTE ucVol, BYTE ucPre);
static BYTE ScalerDisplayDPTx1TP1SameVolCnt(BYTE ucLane, bit bAdd);
static bit ScalerDisplayDPTx1TP1LaneAdjust(BYTE ucLane);
static void ScalerDisplayDPTx1TP2LaneAdjust(BYTE ucLane);

// The lane Adjust functions index the lane bytes by pointer arithmetic
#define DPTX_LANE_CHK(expr, n)                      typedef char DptxLaneChk##n[(expr) ? 1 : -1]
DPTX_LANE_CHK(offsetof(StructDPTxLTInfo, ucLane1Adjust) == offsetof(StructDPTxLTInfo, ucLane0Adjust) + 1, 1);
DPTX_LANE_CHK(offsetof(StructDPTxLTInfo, ucLane2Adjust) == offsetof(StructDPTxLTInfo, ucLane0Adjust) + 2, 2);
DPTX_LANE_CHK(offsetof(StructDPTxLTInfo, ucLane3Adjust) == offsetof(StructDPTxLTInfo, ucLane0Adjust) + 3, 3);
DPTX_LANE_CHK(offsetof(StructDPTxLTInfo, ucAdjustReqLane23) == offsetof(StructDPTxLTInfo, ucAdjustReqLane01) + 1, 4);

#if(_PANEL_DPTX_FORCE_OUTPUT_SUPPORT == _ON)
void ScalerDisplayDPTx1LinkForceOutput(void);
void ScalerDisplayDPTx1ForceOutputPreCheck(void);
#endif

void ScalerDisplayDPTx1SignalReset(void);
void ScalerDisplayDPTx1EnhanceFramingMode(bit bEnable);
bit ScalerDisplayDPTx1MeasureInputInfo(void);
void ScalerDisplayDPTx1MLPHYSet(void);
bit ScalerDisplayDPTx1NativeAuxWrite(BYTE ucAddrH, BYTE ucAddrM, BYTE ucAddrL, BYTE ucLength, BYTE *pucWriteArray);
bit ScalerDisplayDPTx1NativeAuxRead(BYTE ucAddrH, BYTE ucAddrM, BYTE ucAddrL, BYTE ucLength, BYTE *pucReadArray);
void ScalerDisplayDPTx1AuxInitial(void);
bit ScalerDisplayDPTx1AuxRead(BYTE ucCommandAddrH, BYTE ucAddrM, BYTE ucAddrL, BYTE ucLength, BYTE *pucReadArray);
bit ScalerDisplayDPTx1AuxWrite(BYTE ucCommandAddrH, BYTE ucAddrM, BYTE ucAddrL, BYTE ucLength, BYTE *pucWriteArray);
void ScalerDisplayDPTx1HpdInitial(void);

#if(_PANEL_DPTX_HPD_DETECT == _ON)
bit ScalerDisplayDPTx1HpdDetect(void);
#endif
#endif // End of #if(_DISPLAY_DP_TX_PORT_1 == _ON)

#if(_DISPLAY_DP_TX_PORT_2 == _ON)

#if(_PANEL_DPTX_FORCE_OUTPUT_SUPPORT == _ON)
#endif


#if(_PANEL_DPTX_HPD_DETECT == _ON)
#endif

#endif // End of #if(_DISPLAY_DP_TX_PORT_2 == _ON)

void ScalerDisplayDPTxAnalogPhyConrol(bit bEnable);

#if(_PANEL_DPTX_HPD_DETECT == _ON)
bit ScalerDisplayDPTxStableDetect(void);
#endif


//****************************************************************************
// FUNCTION DEFINITIONS
//****************************************************************************
#if(_DISPLAY_DP_TX_PORT_1 == _ON)
//--------------------------------------------------
// Description  : DP Tx Initial
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDisplayDPTx1Initial(void)
{
    ScalerDisplayDPTx1AuxInitial();

    ScalerDisplayDPTx1HpdInitial();

    // Enable DPTX1 Small FIFO ouput 10bits __data for each lane of Analog PHY driver ciruit.
    ScalerSetBit(P9C_10_DPTX_SFIFO_CTRL0, ~_BIT7, _BIT7);

    // Enable Arbiter Stuffing and Framing
    ScalerSetBit(P9C_C9_ARBITER_CTRL, ~_BIT0, _BIT0);

    SET_DISPLAY_DP_TX1_INPUT_COLOR_DEPTH(_PANEL_DISP_BIT_MODE);
    SET_DISPLAY_DP_TX1_INPUT_COLOR_SPACE(_COLOR_SPACE_RGB);

#if(_PANEL_DPTX_HPD_DETECT == _ON)
    SET_DISPLAY_DP_TX1_STREAM_OUTPUT(_DISABLE);
#endif
}

//--------------------------------------------------
// Description  : Dp Tx Read DPCD Rx Capability
// Input Value  :
// Output Value :
//--------------------------------------------------
bit ScalerDisplayDPTx1LinkConfig(void)
{
    SET_DISPLAY_DP_TX1_LT_RESULT(_DISPLAY_DP_TX_TRAINING_NO_RESULT);
    SET_DISPLAY_DP_TX1_LT_STATE(_DISPLAY_DP_TX_TRAINING_PATTERN1);

    // Set Power Normal
    pData[0] = 0x01;
    if(ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x06, 0x00, 1, pData) == _FALSE)
    {
        return _FALSE;
    }

    ScalerTimerDelayXms(10);

    // Read Sink Power Status
    if(ScalerDisplayDPTx1NativeAuxRead(0x00, 0x06, 0x00, 1, pData) == _FALSE)
    {
        return _FALSE;
    }

    // Check if Power State is Normal
    if(pData[0] != 0x01)
    {
        return _FALSE;
    }

    // Read Sink Cabability
    if(ScalerDisplayDPTx1NativeAuxRead(0x00, 0x00, 0x00, 16, pData) == _FALSE)
    {
        return _FALSE;
    }

    if(_PANEL_DPTX_LINK_RATE >= _PANEL_DPTX_LINK_HBR2)
    {
        // Check TP3 support
        if((_PANEL_DPTX_LT_TPS3_SUPPORT_BY_USER == _ON) && ((pData[2] & _BIT6) == _BIT6))
        {
            SET_DISPLAY_DP_TX1_TP3_SUPPORT();
        }
        else
        {
            CLR_DISPLAY_DP_TX1_TP3_SUPPORT();
        }
    }
    else
    {
        CLR_DISPLAY_DP_TX1_TP3_SUPPORT();
    }

    // Set Link Rate
    SET_DISPLAY_DP_TX1_MAX_LINK_RATE(_PANEL_DPTX_LINK_RATE);

    // Set Lane Number
    if(_PANEL_DPTX_LANE_NUMBER >= _PANEL_DPTX_LANE_NUMBER_4)
    {
        SET_DISPLAY_DP_TX1_LANE_NUM(_DP_FOUR_LANE);
    }
    else if(_PANEL_DPTX_LANE_NUMBER == _PANEL_DPTX_LANE_NUMBER_2)
    {
        SET_DISPLAY_DP_TX1_LANE_NUM(_DP_TWO_LANE);
    }
    else
    {
        SET_DISPLAY_DP_TX1_LANE_NUM(_DP_ONE_LANE);
    }

    // Set Enhanceed Framing
    SET_DISPLAY_DP_TX1_ENHANCE_FRAMING((bit)(pData[2] & _BIT7));

    // Set Max Downspread
    SET_DISPLAY_DP_TX1_DOWN_SPREAD((bit)(pData[3] & _BIT0));

    // Set Framing Change for eDP
    SET_DISPLAY_DP_TX1_FRAMING_CHANGE_CAPABLE((bit)(pData[13] & _BIT1));

    // Set Alternate SR Capable for eDP
    SET_DISPLAY_DP_TX1_ALTERNATE_SR_CAPABLE((bit)(pData[13] & _BIT0));

    return _TRUE;
}

//--------------------------------------------------
// Description  : Handle Tx Output stream
// Input Value  : DP Tx Input Source
// Output Value : None
//--------------------------------------------------
void ScalerDisplayDPTx1VideoStreamOutput(bit bOutput)
{
    bit bMvidHWMode = _TRUE;
    BYTE ucCnt = 0;
    BYTE ucValidHwMvidMeaCnt = 0;
    WORD usLoopCnt = 0;
    WORD usMeasureTime = 0;
    DWORD ulHwMvidMin = 0xFFFFFFFF;
    DWORD ulHwMvidMax = 0x00000000;

    if(bOutput == _ENABLE)
    {
#if(_DISPLAY_DP_TX_FB_MODE == _ON)
        // Set Front-Back Mode
        ScalerSetBit(P9C_D9_DPTX_TOP_CTL, ~(_BIT3 | _BIT2), (((BYTE)_PANEL_DPTX_FB_SWAP << 3) | _BIT2));
#else
#if(_PANEL_DPTX_LANE_NUMBER == _PANEL_DPTX_LANE_NUMBER_8)
        // Set Progressive Mode for TX1(MAC0)
        ScalerSetBit(P9C_D9_DPTX_TOP_CTL, ~(_BIT3 | _BIT2), ((BYTE)_PANEL_DPTX_FB_SWAP << 3));
#else
        // Set Progressive Mode for TX1(MAC0)
        ScalerSetBit(P9C_D9_DPTX_TOP_CTL, ~(_BIT3 | _BIT2), 0x00);
#endif
#endif
        // DPTx CTS Fifo reset
        ScalerSetBit(P9C_D7_DPTX_CTSFIFO_CTRL, ~_BIT2, 0x00);
        ScalerSetBit(P9C_D7_DPTX_CTSFIFO_CTRL, ~_BIT2, _BIT2);

        ScalerDisplayDPTx1MeasureInputInfo();

        PDATA_DWORD(0) = 0;
        PDATA_DWORD(1) = 0x8000;
        PDATA_DWORD(2) = 0;
        PDATA_DWORD(3) = 0;

        // Mvid = Stream clk x Nvid / Link clk
        PDATA_DWORD(0) = GET_DWORD_MUL_DIV(GET_D_CLK_FREQ(), PDATA_DWORD(1), ((DWORD)_PANEL_DPTX_DCLK_DIV * 10UL));
        PDATA_DWORD(0) /= ((GET_DISPLAY_DP_TX_SSCG_CONFIG() == _TRUE) ? (270UL * GET_DISPLAY_DP_TX1_LINK_RATE() * 9975UL / 10000UL) : (270UL * GET_DISPLAY_DP_TX1_LINK_RATE()));

        PDATA_DWORD(0) = PDATA_DWORD(0) / 10UL + (PDATA_DWORD(0) % 10 > 5 ? 1 : 0);

        // Calculate HW measure Mvid period time, / 5 for get 5us times
        usMeasureTime = (WORD)(PDATA_DWORD(1) / ((GET_DISPLAY_DP_TX_SSCG_CONFIG() == _TRUE) ? (27UL * GET_DISPLAY_DP_TX1_LINK_RATE() * 9975UL / 10000UL) : (27UL * GET_DISPLAY_DP_TX1_LINK_RATE())) / 5UL);
        usMeasureTime *= 2;

        // Debounce 10 times
        ucCnt = 0x0A;

        do
        {
            --ucCnt;

            // Enable HW Mvid measure
            ScalerSetBit(P9C_A8_MN_VID_AUTO_EN_1, ~_BIT7, _BIT7);

            // Delay time for one HW mvid measurement period time
            for(usLoopCnt = 0; usLoopCnt < usMeasureTime; usLoopCnt++)
            {
                DELAY_5US();
            }

            // Disable HW Mvid measure
            ScalerSetBit(P9C_A8_MN_VID_AUTO_EN_1, ~_BIT7, 0x00);

            PDATA_DWORD(2) = (((DWORD)ScalerGetByte(P9C_AF_MVID_AUTO_H) << 16) | ((DWORD)ScalerGetByte(P9C_B0_MVID_AUTO_M) << 8) | ScalerGetByte(P9C_B1_MVID_AUTO_L));

            // For RLE0779A/RL6449A disable auto Mvid is zero
            if(PDATA_DWORD(2) == 0)
            {
                // HW Auto Mvid is wrong Set Mvid for FW mode
                ScalerSetByte(P9C_A9_MN_M_VID_H, pData[1]);
                ScalerSetByte(P9C_AA_MN_M_VID_M, pData[2]);
                ScalerSetByte(P9C_AB_MN_M_VID_L, pData[3]);

                bMvidHWMode = _FALSE;

                break;
            }

            // (abs(PDATA_DWORD(0) - PDATA_DWORD(2)) > (PDATA_DWORD(0) >> 2)) for HW measure abnormal
            if(abs(PDATA_DWORD(0) - PDATA_DWORD(2)) > (PDATA_DWORD(0) >> 2))
            {
                // Drop this time measure result
                continue;
            }

            // (PDATA_DWORD(3) != 0) for get the first time measurement result
            if(PDATA_DWORD(3) == 0)
            {
                if(PDATA_DWORD(2) < ulHwMvidMin)
                {
                    ulHwMvidMin = PDATA_DWORD(2);
                }

                if(PDATA_DWORD(2) > ulHwMvidMax)
                {
                    ulHwMvidMax = PDATA_DWORD(2);
                }

                PDATA_DWORD(3) = PDATA_DWORD(2);

                // Record total valid hw measure times
                ucValidHwMvidMeaCnt++;

                continue;
            }

            // (abs(PDATA_DWORD(2) - PDATA_DWORD(3)) < 0x50) for avoid get the measurement value far away from the average value
            if(abs(((PDATA_DWORD(3) + (ucValidHwMvidMeaCnt / 2)) / ucValidHwMvidMeaCnt) - PDATA_DWORD(2)) < 0x50)
            {
                if(PDATA_DWORD(2) < ulHwMvidMin)
                {
                    ulHwMvidMin = PDATA_DWORD(2);
                }

                if(PDATA_DWORD(2) > ulHwMvidMax)
                {
                    ulHwMvidMax = PDATA_DWORD(2);
                }

                // Accumulate every hw measure mvid
                PDATA_DWORD(3) += PDATA_DWORD(2);

                // Record total valid hw measure times
                ucValidHwMvidMeaCnt++;
            }
        }
        while(ucCnt > 0);

        if(bMvidHWMode == _TRUE)
        {
            // Drop the min and max value of hw mvid measurement result
            if(ucValidHwMvidMeaCnt > 2)
            {
                PDATA_DWORD(3) -= (ulHwMvidMax + ulHwMvidMin);
                ucValidHwMvidMeaCnt -= 2;

                // Calculate the hw mvid average value
                PDATA_DWORD(3) = ((PDATA_DWORD(3) + (ucValidHwMvidMeaCnt / 2)) / ucValidHwMvidMeaCnt);

                if(abs(PDATA_DWORD(0) - PDATA_DWORD(3)) > (PDATA_DWORD(0) >> 1))
                {
                    // HW Auto Mvid is wrong Set Mvid for FW mode
                    PDATA_DWORD(3) = PDATA_DWORD(0);
                }
            }
            else
            {
                // HW Auto Mvid is wrong Set Mvid for FW mode
                PDATA_DWORD(3) = PDATA_DWORD(0);
            }

            // Set Mvid value
            ScalerSetByte(P9C_A9_MN_M_VID_H, pData[13]);
            ScalerSetByte(P9C_AA_MN_M_VID_M, pData[14]);
            ScalerSetByte(P9C_AB_MN_M_VID_L, pData[15]);
        }

        // Set Nvid for FW mode
        ScalerSetByte(P9C_AC_MN_N_VID_H, pData[5]);
        ScalerSetByte(P9C_AD_MN_N_VID_M, pData[6]);
        ScalerSetByte(P9C_AE_MN_N_VID_L, pData[7]);

        // Set Mvid DB Direct Effective
        ScalerSetBit(P9C_B4_MSA_CTRL, ~_BIT6, 0x00);

        // Set Mvid DB for FW mode
        ScalerSetBit(P9C_A8_MN_VID_AUTO_EN_1, ~(_BIT7 | _BIT6), _BIT6);

        // For Mvid Auto New Mode, M/N mode Measure and Generate are Independant.
        // SET_DISPLAY_DP_TX1_MVID_FW_MODE -> FW Manually Set Mvid/Nvid
        SET_DISPLAY_DP_TX1_MVID_FW_MODE();

        // MSA fill
        ScalerDisplayDPTx1DisplayMSASetting();

        // DP Tx TU Setting
        ScalerDisplayDPTx1DisplayFormatSetting();

        // Clear FIFO Status
        ScalerSetByte(P9C_A4_PG_FIFO_CTRL, 0xFF);

        // Main Link Switch to VIDEO pattern
        ScalerSetBit(P9C_01_DPTX_ML_PAT_SEL, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4), _BIT6);

        // Double buffer only by Vsync
        ScalerSetBit(P9C_01_DPTX_ML_PAT_SEL, ~(_BIT1 | _BIT0), _BIT1);

#if(_PANEL_DPTX_HPD_DETECT == _ON)
        // Clear HPD IRQ Flag
        ScalerSetByte(P9C_71_HPD_IRQ, 0xFE);

        SET_DISPLAY_DP_TX1_STREAM_OUTPUT(_ENABLE);
#endif
    }
    else
    {
        // Main Link Switch to IDLE pattern
        ScalerSetBit(P9C_01_DPTX_ML_PAT_SEL, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4), 0x00);

        // Double buffer only by Vsync
        ScalerSetBit(P9C_01_DPTX_ML_PAT_SEL, ~(_BIT1 | _BIT0), _BIT1);

#if(_PANEL_DPTX_HPD_DETECT == _ON)
        SET_DISPLAY_DP_TX1_STREAM_OUTPUT(_DISABLE);
#endif
    }
}

//--------------------------------------------------
// Description  : DP Tx Arbiter
// Input Value  :
// Output Value :
//--------------------------------------------------
void ScalerDisplayDPTx1DisplayFormatSetting(void)
{
    // Disable HW Auto Calculate H Delay
    ScalerSetBit(P9C_D3_LFIFO_WL_SET, ~_BIT7, 0x00);

    // Pixel Generation Block Reset
    ScalerSetBit(P9C_A1_DP_RESET_CTRL, ~_BIT7, _BIT7);
    ScalerSetBit(P9C_A1_DP_RESET_CTRL, ~_BIT7, 0x00);

    // Get Bit Per Chrome
    switch(GET_DISPLAY_DP_TX1_INPUT_COLOR_DEPTH())
    {
        case _PANEL_DISP_18_BIT:
            pData[0] = 6;
            break;

        case _PANEL_DISP_24_BIT:
            pData[0] = 8;
            break;

        case _PANEL_DISP_30_BIT:
            pData[0] = 10;
            break;

        case _PANEL_DISP_36_BIT:
            pData[0] = 12;
            break;

        case _PANEL_DISP_48_BIT:
            pData[0] = 16;
            break;

        default:

            pData[0] = 8;
            break;
    }

    // Calculate Vaild Symbol in TU
    // Average TU = TU Size x (Stream_Clk x Byte of 1 pixel / Lane Number) / Link Rate
    if(GET_DISPLAY_DP_TX_SSCG_CONFIG() == _FALSE)
    {
        DWORD ulA = (DWORD)_DISPLAY_DP_TX1_TU_SIZE * 3UL * pData[0];
        DWORD ulB = (DWORD)GET_D_CLK_FREQ();
        DWORD ulC = (DWORD)_PANEL_DPTX_DCLK_DIV * 10UL * GET_DISPLAY_DP_TX1_LANE_NUM() * 270UL * GET_DISPLAY_DP_TX1_LINK_RATE();

        // Average TU = TU Size x Color Depth x Stream_Clk / (Lane Number x Link Rate)
        PDATA_WORD(1) = GET_DWORD_MUL_DIV(ulA, ulB, ulC);
    }
    else
    {
        DWORD ulA = (DWORD)_DISPLAY_DP_TX1_TU_SIZE * 3UL * pData[0];
        DWORD ulB = (DWORD)GET_D_CLK_FREQ() * 100UL;
        DWORD ulC = (DWORD)_PANEL_DPTX_DCLK_DIV * GET_DISPLAY_DP_TX1_LANE_NUM() * 27UL * GET_DISPLAY_DP_TX1_LINK_RATE() * 9975UL;

        // Average TU = TU Size x Color Depth x Stream_Clk / Lane Number * SSCG of Link Rate)
        PDATA_WORD(1) = GET_DWORD_MUL_DIV(ulA, ulB, ulC);
    }

    PDATA_WORD(1) = PDATA_WORD(1) / 10UL + (PDATA_WORD(1) % 10 >= 5 ? 1 : 0);

    ScalerSetByte(P9C_CC_TU_SIZE, _DISPLAY_DP_TX1_TU_SIZE);

    // HW Can't Set Valid TU < 0
    if((PDATA_WORD(1) >> 3) == 0x00)
    {
        ScalerSetByte(P9C_CD_TU_DATA_SIZE0, 0x01);
        ScalerSetByte(P9C_CE_TU_DATA_SIZE1, 0x00);
    }
    else
    {
        ScalerSetByte(P9C_CD_TU_DATA_SIZE0, (PDATA_WORD(1) >> 3));
        ScalerSetByte(P9C_CE_TU_DATA_SIZE1, (PDATA_WORD(1) & 0x07));
    }

    PDATA_WORD(1) = ((DWORD)g_stDisplayDPTx1TimingInfo.usHWidth * pData[0] * 3) / (GET_DISPLAY_DP_TX1_LANE_NUM() * 8);
    PDATA_WORD(1) += ((bit)(((DWORD)g_stDisplayDPTx1TimingInfo.usHWidth * pData[0] * 3) % (GET_DISPLAY_DP_TX1_LANE_NUM() * 8)) ? 1 : 0);

    ScalerSetByte(P9C_CA_V_DATA_PER_LINE0, pData[2]);
    ScalerSetByte(P9C_CB_V_DATA_PER_LINE1, pData[3]);

    // Enable HW Auto Calculate H Delay
    ScalerSetBit(P9C_D3_LFIFO_WL_SET, ~_BIT7, _BIT7);

    // This dealy be used to wait HW circuit complete the transition from firt frame to sencond frame aviod two frame picture's diffrent size issue
    ScalerTimerDelayXms(_DP_ONE_FRAME_TIME_MAX);

    ScalerSetByte(P9C_D4_ARBITER_SEC_END_CNT_HB, 0x00);
    ScalerSetByte(P9C_D5_ARBITER_SEC_END_CNT_LB, 0x47);
}

//--------------------------------------------------
// Description  : DP Tx MSA Generation
// Input Value  :
// Output Value :
//--------------------------------------------------
void ScalerDisplayDPTx1DisplayMSASetting(void)
{
    // Reset MSA Generation Block and SEC Block
    ScalerSetBit(P9C_A1_DP_RESET_CTRL, ~_BIT6, _BIT6);
    ScalerSetBit(P9C_A1_DP_RESET_CTRL, ~_BIT6, 0x00);

    // Set Htotal
    ScalerSetByte(P9C_B7_MN_STRM_ATTR_HTT_M, HIBYTE(g_stDisplayDPTx1TimingInfo.usHTotal));
    ScalerSetByte(P9C_B8_MN_STRM_ATTR_HTT_L, LOBYTE(g_stDisplayDPTx1TimingInfo.usHTotal));

    // Set Hstart
    ScalerSetByte(P9C_B9_MN_STRM_ATTR_HST_M, HIBYTE(g_stDisplayDPTx1TimingInfo.usHStart));
    ScalerSetByte(P9C_BA_MN_STRM_ATTR_HST_L, LOBYTE(g_stDisplayDPTx1TimingInfo.usHStart));

    // Set Hwidth
    ScalerSetByte(P9C_BB_MN_STRM_ATTR_HWD_M, HIBYTE(g_stDisplayDPTx1TimingInfo.usHWidth));
    ScalerSetByte(P9C_BC_MN_STRM_ATTR_HWD_L, LOBYTE(g_stDisplayDPTx1TimingInfo.usHWidth));

    // Set Hsyc
    ScalerSetByte(P9C_BD_MN_STRM_ATTR_HSW_M, HIBYTE(g_stDisplayDPTx1TimingInfo.usHSWidth));
    ScalerSetByte(P9C_BE_MN_STRM_ATTR_HSW_L, LOBYTE(g_stDisplayDPTx1TimingInfo.usHSWidth));

    // Set Vtotal
    ScalerSetByte(P9C_BF_MN_STRM_ATTR_VTTE_M, HIBYTE(g_stDisplayDPTx1TimingInfo.usVTotal));
    ScalerSetByte(P9C_C0_MN_STRM_ATTR_VTTE_L, LOBYTE(g_stDisplayDPTx1TimingInfo.usVTotal));

    // Set VStart
    ScalerSetByte(P9C_C1_MN_STRM_ATTR_VST_M, HIBYTE(g_stDisplayDPTx1TimingInfo.usVStart));
    ScalerSetByte(P9C_C2_MN_STRM_ATTR_VST_L, LOBYTE(g_stDisplayDPTx1TimingInfo.usVStart));

    // Set VHeight
    ScalerSetByte(P9C_C3_MN_STRM_ATTR_VHT_M, HIBYTE(g_stDisplayDPTx1TimingInfo.usVHeight));
    ScalerSetByte(P9C_C4_MN_STRM_ATTR_VHT_L, LOBYTE(g_stDisplayDPTx1TimingInfo.usVHeight));

    // Set Vsync
    ScalerSetByte(P9C_C5_MN_STRM_ATTR_VSW_M, HIBYTE(g_stDisplayDPTx1TimingInfo.usVSWidth));
    ScalerSetByte(P9C_C6_MN_STRM_ATTR_VSW_L, LOBYTE(g_stDisplayDPTx1TimingInfo.usVSWidth));

    // Set Color Space
    ScalerSetBit(P9C_B5_MSA_MISC0, ~(_BIT2 | _BIT1), (GET_DISPLAY_DP_TX1_INPUT_COLOR_SPACE() << 1));

    // Set Color Depth
    ScalerSetBit(P9C_B5_MSA_MISC0, ~(_BIT7 | _BIT6 | _BIT5), (GET_DISPLAY_DP_TX1_INPUT_COLOR_DEPTH() << 5));

    // Set MISC1
    ScalerSetByte(P9C_B6_MN_STRM_ATTR_MISC1, 0x00);

    // MSA_DB = 1 and Bouble Buffer at V Blanking
    ScalerSetBit(P9C_B4_MSA_CTRL, ~(_BIT7 | _BIT6), _BIT7);
}

//--------------------------------------------------
// Description  : DP Tx Link Training
// Input Value  :
// Output Value :
//--------------------------------------------------
void ScalerDisplayDPTx1LinkTraining(void)
{
    if(GET_DISPLAY_DP_TX1_LINK_CONFIG() == _TRUE)
    {
        ScalerDisplayDPTx1TPInitialSet();

        while((GET_DISPLAY_DP_TX1_LT_RESULT() != _DISPLAY_DP_TX_TRAINING_PASS) && (GET_DISPLAY_DP_TX1_LT_RESULT() != _DISPLAY_DP_TX_TRAINING_FAIL))
        {
            switch(GET_DISPLAY_DP_TX1_LT_STATE())
            {
                case _DISPLAY_DP_TX_TRAINING_PATTERN1:

                    SET_DISPLAY_DP_TX1_LT_RESULT(ScalerDisplayDPTx1TrainPattern1());

                    // CR OK
                    if(GET_DISPLAY_DP_TX1_LT_RESULT() == _DISPLAY_DP_TX_TRAINING_PATTERN1_PASS)
                    {
                        SET_DISPLAY_DP_TX1_LT_STATE(_DISPLAY_DP_TX_TRAINING_PATTERN2);

                        DebugMessageCheck("eDP Tx1 LT1 Pass", 0x00);
                    }
                    else if(GET_DISPLAY_DP_TX1_LT_RESULT() == _DISPLAY_DP_TX_TRAINING_PATTERN1_ADJUST_FAIL) // Can not Adjust voltage swing
                    {
                        SET_DISPLAY_DP_TX1_LT_STATE(_DISPLAY_DP_TX_TRAINING_PATTERN_END);

                        DebugMessageCheck("eDP Tx1 LT1 Freq Fail", 0x00);
                    }

                    break;

                case _DISPLAY_DP_TX_TRAINING_PATTERN2:

                    SET_DISPLAY_DP_TX1_LT_RESULT(ScalerDisplayDPTx1TrainPattern2());

                    if(GET_DISPLAY_DP_TX1_LT_RESULT() == _DISPLAY_DP_TX_TRAINING_PATTERN2_PASS)
                    {
                        SET_DISPLAY_DP_TX1_LT_STATE(_DISPLAY_DP_TX_TRAINING_PATTERN_END);

                        DebugMessageCheck("eDP Tx1 LT2 Pass", 0x00);
                    }
                    else if(GET_DISPLAY_DP_TX1_LT_RESULT() == _DISPLAY_DP_TX_TRAINING_PATTERN2_ADJUST_FAIL)
                    {
                        SET_DISPLAY_DP_TX1_LT_STATE(_DISPLAY_DP_TX_TRAINING_PATTERN_END);

                        DebugMessageCheck("eDP Tx1 LT2 Lane or PN Fail", 0x00);
                    }

                    break;

                case _DISPLAY_DP_TX_TRAINING_PATTERN_END:

                    if(GET_DISPLAY_DP_TX1_LT_RESULT() != _DISPLAY_DP_TX_TRAINING_PATTERN2_PASS)
                    {
                        SET_DISPLAY_DP_TX1_LT_RESULT(_DISPLAY_DP_TX_TRAINING_FAIL);

                        DebugMessageCheck("eDP Tx1 LTend Fail", 0x00);
                    }
                    else
                    {
                        SET_DISPLAY_DP_TX1_LT_RESULT(_DISPLAY_DP_TX_TRAINING_PASS);

                        DebugMessageCheck("eDP Tx1 LTend Pass", 0x00);
                    }

                    ScalerDisplayDPTx1TrainPatternEnd();

                    break;

                default:

                    break;
            }
        }
    }
    else
    {
        DebugMessageCheck("eDP Tx1 Link Config Fail", 0x00);
    }
}

//--------------------------------------------------
// Description  : DP Tx Link Training 1 Inital Set
// Input Value  :
// Output Value :
//--------------------------------------------------
void ScalerDisplayDPTx1TPInitialSet(void)
{
    BYTE ucMsaIgnore = 0;

    // Panel DPTx Power Sequence Check Point
    PCB_DPTX1_POWER_SEQUENCE(_DPTX_POWER_SEQUENCE_LINK_TRAINING);

    SET_DISPLAY_DP_TX1_LT_RESULT(_DISPLAY_DP_TX_TRAINING_NO_RESULT);
    SET_DISPLAY_DP_TX1_LT_STATE(_DISPLAY_DP_TX_TRAINING_PATTERN1);

    // Set Link Rate
    SET_DISPLAY_DP_TX1_LINK_RATE(_PANEL_DPTX_LINK_RATE);

    // Set Link Rate for DPCD table of the Sink
    ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x00, 1, &GET_DISPLAY_DP_TX1_MAX_LINK_RATE());

    // Set Link Rate
    ScalerDisplayDPTxSetLinkRate();

    if(GET_DISPLAY_DP_TX1_FRAMING_CHANGE_CAPABLE() == _TRUE)
    {
        // Set Link Count and Disable Enhance Framing for External DP Sink
        pData[0] = GET_DISPLAY_DP_TX1_LANE_NUM();
        ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x01, 1, pData);

        // Set Enhance Framing Mode for eDP
        pData[0] = ((BYTE)GET_DISPLAY_DP_TX1_FRAMING_CHANGE_CAPABLE() << 1);
        ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x0A, 1, pData);

        ScalerDisplayDPTx1EnhanceFramingMode(_ENABLE);
    }
    else
    {
        // Set Link Count and Enhance Framing for DPCD table of the Sink
        pData[0] = ((BYTE)GET_DISPLAY_DP_TX1_ENHANCE_FRAMING() << 7) | GET_DISPLAY_DP_TX1_LANE_NUM();
        ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x01, 1, pData);

        ScalerDisplayDPTx1EnhanceFramingMode(GET_DISPLAY_DP_TX1_ENHANCE_FRAMING());
    }

    // Initialize Main Link Signal
    ScalerDisplayDPTx1SignalInitialSetting();

    ScalerDisplayDPTx1NativeAuxRead(0x00, 0x00, 0x07, 1, pData);

    ucMsaIgnore = ((pData[0] & _BIT6) == _BIT6 ? ((_PANEL_DPTX_MSA_TIMING_PAR_IGNORE_EN == _ENABLE) ? _BIT7 : 0x00) : 0x00);

    ScalerDisplayDPTx1NativeAuxRead(0x00, 0x01, 0x07, 1, pData);

    // Set Down Spread for DPCD table of the Sink
    pData[0] = ((pData[0] & ~_BIT4) | ((BYTE)GET_DISPLAY_DP_TX_SSCG_CONFIG() << 4) | ucMsaIgnore);
    ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x07, 1, pData);

    // Set DPTx Spread Spectrum
    ScalerDisplayDPTxSSCSet(GET_DISPLAY_DP_TX_SSCG_CONFIG());
}

//--------------------------------------------------
// Description  : DP Tx Link Training 1
// Input Value  :
// Output Value :
//--------------------------------------------------
BYTE ScalerDisplayDPTx1TrainPattern1(void)
{
    // Start TP1 Process
    if(GET_DISPLAY_DP_TX1_LT_RESULT() == _DISPLAY_DP_TX_TRAINING_NO_RESULT)
    {
        // Repeat Bist Pattern --> for Training Pattern
        ScalerSetBit(P38_85_PHY0_TXBIST_00_H2, ~(_BIT7 | _BIT6), (_BIT7 | _BIT6));

        // Select TP1
        ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~_BIT5, _BIT5);

        pData[0] = (_DISPLAY_DP_TX_TP_1 | _DISPLAY_DP_TX_SCRAMBLING_DISABLE);
        pData[1] = g_stDisplayDPTx1LTInfo.ucLane0Adjust;
        pData[2] = g_stDisplayDPTx1LTInfo.ucLane1Adjust;
        pData[3] = g_stDisplayDPTx1LTInfo.ucLane2Adjust;
        pData[4] = g_stDisplayDPTx1LTInfo.ucLane3Adjust;

        // Write DPCD 102h to Start TP1
        ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x02, 5, pData);
    }
    else
    {
        // Set Output Signal According to Request
        ScalerDisplayDPTx1MLPHYSet();

        pData[0] = g_stDisplayDPTx1LTInfo.ucLane0Adjust;
        pData[1] = g_stDisplayDPTx1LTInfo.ucLane1Adjust;
        pData[2] = g_stDisplayDPTx1LTInfo.ucLane2Adjust;
        pData[3] = g_stDisplayDPTx1LTInfo.ucLane3Adjust;

        // Write DPCD 103h-107h  (Voltage Swing and Pre-emphasis)
        ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x03, 4, pData);
    }

    // Delay Time us [400,x]
    DELAY_XUS(400);

    // Read Lane Status and Request Adjust Level
    ScalerDisplayDPTx1NativeAuxRead(0x00, 0x02, 0x02, 6, pData);
    g_stDisplayDPTx1LTInfo.ucLane01LTStatus = pData[0];
    g_stDisplayDPTx1LTInfo.ucLane23LTStatus = pData[1];
    g_stDisplayDPTx1LTInfo.ucAdjustReqLane01 = pData[4];
    g_stDisplayDPTx1LTInfo.ucAdjustReqLane23 = pData[5];

    if(((GET_DISPLAY_DP_TX1_LANE_NUM() == _DP_FOUR_LANE) && ((GET_DISPLAY_DP_TX1_LANE3_CR_DONE() & GET_DISPLAY_DP_TX1_LANE2_CR_DONE() & GET_DISPLAY_DP_TX1_LANE1_CR_DONE() & GET_DISPLAY_DP_TX1_LANE0_CR_DONE()) == _TRUE)) ||
       ((GET_DISPLAY_DP_TX1_LANE_NUM() == _DP_TWO_LANE) && ((GET_DISPLAY_DP_TX1_LANE1_CR_DONE() & GET_DISPLAY_DP_TX1_LANE0_CR_DONE()) == _TRUE)) ||
       ((GET_DISPLAY_DP_TX1_LANE_NUM() == _DP_ONE_LANE) && (GET_DISPLAY_DP_TX1_LANE0_CR_DONE() == _TRUE)))
    {
        return _DISPLAY_DP_TX_TRAINING_PATTERN1_PASS;
    }

    switch(GET_DISPLAY_DP_TX1_LANE_NUM())
    {
        case _DP_FOUR_LANE:

            if((ScalerDisplayDPTx1TP1LaneAdjust(3) == _FAIL) ||
               (ScalerDisplayDPTx1TP1LaneAdjust(2) == _FAIL) ||
               (ScalerDisplayDPTx1TP1LaneAdjust(1) == _FAIL) ||
               (ScalerDisplayDPTx1TP1LaneAdjust(0) == _FAIL))
            {
                return _DISPLAY_DP_TX_TRAINING_PATTERN1_ADJUST_FAIL;
            }

            break;

        case _DP_TWO_LANE:

            if((ScalerDisplayDPTx1TP1LaneAdjust(1) == _FAIL) ||
               (ScalerDisplayDPTx1TP1LaneAdjust(0) == _FAIL))
            {
                return _DISPLAY_DP_TX_TRAINING_PATTERN1_ADJUST_FAIL;
            }

            break;

        case _DP_ONE_LANE:
        default:

            if(ScalerDisplayDPTx1TP1LaneAdjust(0) == _FAIL)
            {
                return _DISPLAY_DP_TX_TRAINING_PATTERN1_ADJUST_FAIL;
            }

            break;
    }

    return _DISPLAY_DP_TX_TRAINING_PATTERN1_FAIL;
}

//--------------------------------------------------
// Description  : DP Tx Link Training 2
// Input Value  :
// Output Value :
//--------------------------------------------------
BYTE ScalerDisplayDPTx1TrainPattern2(void)
{
    // Start TP2 Process
    if(GET_DISPLAY_DP_TX1_LT_RESULT() == _DISPLAY_DP_TX_TRAINING_PATTERN1_PASS)
    {
        // Repeat Bist Pattern --> for Training Pattern
        ScalerSetBit(P38_85_PHY0_TXBIST_00_H2, ~(_BIT7 | _BIT6), (_BIT7 | _BIT6));

        // Disable De-Scambling
        ScalerSetBit(P38_89_PHY0_TXBIST_01_H2, ~_BIT1, _BIT1);

        // Set TP2 Pattern Type
        pData[0] = ScalerDisplayDPTx1SetTp2PatternType() | _DISPLAY_DP_TX_SCRAMBLING_DISABLE;

        pData[1] = g_stDisplayDPTx1LTInfo.ucLane0Adjust;
        pData[2] = g_stDisplayDPTx1LTInfo.ucLane1Adjust;
        pData[3] = g_stDisplayDPTx1LTInfo.ucLane2Adjust;
        pData[4] = g_stDisplayDPTx1LTInfo.ucLane3Adjust;

        // Write DPCD 102h-107h to Start TP2
        ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x02, 5, pData);
    }
    else
    {
        // Set Output Signal According to Request
        ScalerDisplayDPTx1MLPHYSet();

        pData[0] = g_stDisplayDPTx1LTInfo.ucLane0Adjust;
        pData[1] = g_stDisplayDPTx1LTInfo.ucLane1Adjust;
        pData[2] = g_stDisplayDPTx1LTInfo.ucLane2Adjust;
        pData[3] = g_stDisplayDPTx1LTInfo.ucLane3Adjust;

        // Write DPCD 103h-107h (Voltage Swing and Pre-emphasis)
        ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x03, 4, pData);
    }

    // Delay Time us [400,x]
    DELAY_XUS(400);

    // Read Lane Status and Request Adjust Level
    ScalerDisplayDPTx1NativeAuxRead(0x00, 0x02, 0x02, 6, pData);
    g_stDisplayDPTx1LTInfo.ucLane01LTStatus = pData[0];
    g_stDisplayDPTx1LTInfo.ucLane23LTStatus = pData[1];
    g_stDisplayDPTx1LTInfo.ucLaneAlignStatus = pData[2];
    g_stDisplayDPTx1LTInfo.ucAdjustReqLane01 = pData[4];
    g_stDisplayDPTx1LTInfo.ucAdjustReqLane23 = pData[5];

    // CDR unlock => Reduce bit rate and return to TP1
    if(((GET_DISPLAY_DP_TX1_LANE_NUM() == _DP_FOUR_LANE) && ((GET_DISPLAY_DP_TX1_LANE3_CR_DONE() & GET_DISPLAY_DP_TX1_LANE2_CR_DONE() & GET_DISPLAY_DP_TX1_LANE1_CR_DONE() & GET_DISPLAY_DP_TX1_LANE0_CR_DONE()) != _TRUE)) ||
       ((GET_DISPLAY_DP_TX1_LANE_NUM() == _DP_TWO_LANE) && ((GET_DISPLAY_DP_TX1_LANE1_CR_DONE() & GET_DISPLAY_DP_TX1_LANE0_CR_DONE()) != _TRUE)) ||
       ((GET_DISPLAY_DP_TX1_LANE_NUM() == _DP_ONE_LANE) && (GET_DISPLAY_DP_TX1_LANE0_CR_DONE() != _TRUE)))
    {
        CLR_DISPLAY_DP_TX1_TP2_CNT();

        return _DISPLAY_DP_TX_TRAINING_PATTERN2_ADJUST_FAIL;
    }

    if((((GET_DISPLAY_DP_TX1_LANE_NUM() == _DP_FOUR_LANE) && ((GET_DISPLAY_DP_TX1_LANE3_EQ_DONE() & GET_DISPLAY_DP_TX1_LANE2_EQ_DONE() & GET_DISPLAY_DP_TX1_LANE1_EQ_DONE() & GET_DISPLAY_DP_TX1_LANE0_EQ_DONE()) == _TRUE)) ||
        ((GET_DISPLAY_DP_TX1_LANE_NUM() == _DP_TWO_LANE) && ((GET_DISPLAY_DP_TX1_LANE1_EQ_DONE() & GET_DISPLAY_DP_TX1_LANE0_EQ_DONE()) == _TRUE)) ||
        ((GET_DISPLAY_DP_TX1_LANE_NUM() == _DP_ONE_LANE) && (GET_DISPLAY_DP_TX1_LANE0_EQ_DONE() == _TRUE))) &&
       (GET_DISPLAY_DP_TX1_LANE_ALIGN_DONE() == _TRUE))
    {
        CLR_DISPLAY_DP_TX1_TP2_CNT();

        return _DISPLAY_DP_TX_TRAINING_PATTERN2_PASS;
    }

    if(GET_DISPLAY_DP_TX1_TP2_CNT() == 5)
    {
        CLR_DISPLAY_DP_TX1_TP2_CNT();

        return _DISPLAY_DP_TX_TRAINING_PATTERN2_ADJUST_FAIL;
    }
    else
    {
        ADD_DISPLAY_DP_TX1_TP2_CNT();
    }

    switch(GET_DISPLAY_DP_TX1_LANE_NUM())
    {
        case _DP_FOUR_LANE:

            ScalerDisplayDPTx1TP2LaneAdjust(3);
            ScalerDisplayDPTx1TP2LaneAdjust(2);
            ScalerDisplayDPTx1TP2LaneAdjust(1);
            ScalerDisplayDPTx1TP2LaneAdjust(0);
            break;

        case _DP_TWO_LANE:

            ScalerDisplayDPTx1TP2LaneAdjust(1);
            ScalerDisplayDPTx1TP2LaneAdjust(0);
            break;

        case _DP_ONE_LANE:
        default:

            ScalerDisplayDPTx1TP2LaneAdjust(0);
            break;
    }

    return _DISPLAY_DP_TX_TRAINING_PATTERN2_FAIL;
}

//--------------------------------------------------
// Description  : DP Tx Link Training Pattern End
// Input Value  :
// Output Value :
//--------------------------------------------------
void ScalerDisplayDPTx1TrainPatternEnd(void)
{
#if(_PANEL_DPTX_AUX_SET_TP_END_SEQUENCE == _TRAIN_PATTERN_END_BEFORE_IDEL_PATTERN)
    // Write TRAINING_PATTERN_SET = 00
    pData[0] = _DISPLAY_DP_TX_TP_NONE;
    ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x02, 1, pData);
#endif

    if(GET_DISPLAY_DP_TX1_LT_RESULT() == _DISPLAY_DP_TX_TRAINING_PASS)
    {
#if(_PANEL_DPTX_SCRAMBLE_SEED_TYPE == _PANEL_DPTX_SCRAMBLE_SEED_AUTO)
        if(GET_DISPLAY_DP_TX1_ALTERNATE_SR_CAPABLE() == _TRUE)
        {
            // Scambling Seed Select to 0xFFFE
            ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~_BIT4, 0x00);

            pData[0] = ((BYTE)GET_DISPLAY_DP_TX1_FRAMING_CHANGE_CAPABLE() << 1) | _BIT0;
            ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x0A, 1, pData);
        }
        else
        {
            // Scambling Seed Select to 0xFFFF
            ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~_BIT4, _BIT4);
        }
#elif(_PANEL_DPTX_SCRAMBLE_SEED_TYPE == _PANEL_DPTX_SCRAMBLE_SEED_0XFFFE)

        // Scambling Seed Select to 0xFFFE
        ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~_BIT4, 0x00);

#elif(_PANEL_DPTX_SCRAMBLE_SEED_TYPE == _PANEL_DPTX_SCRAMBLE_SEED_0XFFFF)

        // Scambling Seed Select to 0xFFFF
        ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~_BIT4, _BIT4);

#endif // End of #if(_PANEL_DPTX_SCRAMBLE_SEED_TYPE == _PANEL_DPTX_SCRAMBLE_SEED_AUTO)

        // Enable Scrambling
        ScalerSetBit(P38_89_PHY0_TXBIST_01_H2, ~_BIT1, 0x00);

        // Enable BS replaced by SR
        ScalerSetBit(P9C_0D_DPTX_PHY_CTRL, ~_BIT4, _BIT4);

        // Main Link switch to IDLE Pattern
        ScalerDisplayDPTx1VideoStreamOutput(_DISABLE);

        // Panel DPTx Power Sequence Check Point
        PCB_DPTX1_POWER_SEQUENCE(_DPTX_POWER_SEQUENCE_IDLE_PATTERN);

        // Disable bist mode
        ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~(_BIT3 | _BIT2), 0x00);

        // Disable Bist Pattern --> for Video Data
        ScalerSetBit(P38_85_PHY0_TXBIST_00_H2, ~_BIT7, 0x00);
    }
    else
    {
        // Main Link switch to IDLE Pattern
        ScalerDisplayDPTx1VideoStreamOutput(_DISABLE);

        // Panel DPTx Power Sequence Check Point
        PCB_DPTX1_POWER_SEQUENCE(_DPTX_POWER_SEQUENCE_IDLE_PATTERN);

        // Disable bist mode
        ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~(_BIT3 | _BIT2), 0x00);

        // Disable Bist Pattern --> for Video Data
        ScalerSetBit(P38_85_PHY0_TXBIST_00_H2, ~_BIT7, 0x00);
    }
}

//--------------------------------------------------
// Description  : TP1 same-voltage counter of a lane: bAdd = 1 counts up and returns it, 0 clears it
// Input Value  : ucLane, bAdd
// Output Value : counter
//--------------------------------------------------
static BYTE ScalerDisplayDPTx1TP1SameVolCnt(BYTE ucLane, bit bAdd)
{
    switch(ucLane)
    {
        case 0:

            if(bAdd == _TRUE)
            {
                ADD_DISPLAY_DP_TX1_TP1_LANE0_SAME_VOL_CNT();
            }
            else
            {
                CLR_DISPLAY_DP_TX1_TP1_LANE0_SAME_VOL_CNT();
            }

            return GET_DISPLAY_DP_TX1_TP1_LANE0_SAME_VOL_CNT();
        case 1:

            if(bAdd == _TRUE)
            {
                ADD_DISPLAY_DP_TX1_TP1_LANE1_SAME_VOL_CNT();
            }
            else
            {
                CLR_DISPLAY_DP_TX1_TP1_LANE1_SAME_VOL_CNT();
            }

            return GET_DISPLAY_DP_TX1_TP1_LANE1_SAME_VOL_CNT();
        case 2:

            if(bAdd == _TRUE)
            {
                ADD_DISPLAY_DP_TX1_TP1_LANE2_SAME_VOL_CNT();
            }
            else
            {
                CLR_DISPLAY_DP_TX1_TP1_LANE2_SAME_VOL_CNT();
            }

            return GET_DISPLAY_DP_TX1_TP1_LANE2_SAME_VOL_CNT();
        default:

            if(bAdd == _TRUE)
            {
                ADD_DISPLAY_DP_TX1_TP1_LANE3_SAME_VOL_CNT();
            }
            else
            {
                CLR_DISPLAY_DP_TX1_TP1_LANE3_SAME_VOL_CNT();
            }

            return GET_DISPLAY_DP_TX1_TP1_LANE3_SAME_VOL_CNT();
    }
}

//--------------------------------------------------
// Description  : Store a lane's current vol swing / pre-emphasis and their max-reach flags (#295)
// Input Value  : pucCur = ucLaneNAdjust, level values 0..3
// Output Value :
//--------------------------------------------------
static void ScalerDisplayDPTxLaneSetCurrent(BYTE __xdata *pucCur, BYTE ucVol, BYTE ucPre)
{
    BYTE ucNew = (*pucCur & (_BIT7 | _BIT6)) | ucVol | (ucPre << 3);

    if(ucVol == _DISPLAY_DP_TX_LEVEL_3)
    {
        ucNew |= _BIT2;
    }

    if(ucPre == _DISPLAY_DP_TX_LEVEL_3)
    {
        ucNew |= _BIT5;
    }

    *pucCur = ucNew;
}

//--------------------------------------------------
// Description  : DP Tx Link Training 1 Lane Adjust (lane 0..3, #295)
// Input Value  : ucLane
// Output Value : _FAIL when the same voltage level repeats, else _SUCCESS
//--------------------------------------------------
static bit ScalerDisplayDPTx1TP1LaneAdjust(BYTE ucLane)
{
    BYTE __xdata *pucCur = &g_stDisplayDPTx1LTInfo.ucLane0Adjust + ucLane;
    BYTE __xdata *pucReq = &g_stDisplayDPTx1LTInfo.ucAdjustReqLane01 + (ucLane >> 1);
    BYTE ucShift = (ucLane & 1) << 2;
    BYTE ucAdjVol = (*pucReq >> ucShift) & (_BIT1 | _BIT0);
    BYTE ucAdjPre = (*pucReq >> (ucShift + 2)) & (_BIT1 | _BIT0);
    BYTE ucCurPre = (*pucCur & (_BIT4 | _BIT3)) >> 3;
    BYTE ucCnt;

    // Check1: (Adjust Vol swing level + Current Vol pre emphasisl) > 3
    if((ucAdjVol + ucCurPre) > _DISPLAY_DP_TX_LEVEL_3)
    {
        ucAdjVol = _DISPLAY_DP_TX_LEVEL_3 - ucCurPre;
        *pucReq = (*pucReq & ~((_BIT1 | _BIT0) << ucShift)) | (ucAdjVol << ucShift);
    }

    // Check2: Current Vol swing level is the same as adjust Vol swing level
    if((*pucCur & (_BIT1 | _BIT0)) == ucAdjVol)
    {
        ucCnt = ScalerDisplayDPTx1TP1SameVolCnt(ucLane, 1);

        if((ucCnt == 5) || ((ucCnt == 1) && (ucAdjVol == _DISPLAY_DP_TX_LEVEL_3)))
        {
            ScalerDisplayDPTx1TP1SameVolCnt(ucLane, 0);

            return _FAIL;
        }
    }
    else
    {
        ScalerDisplayDPTx1TP1SameVolCnt(ucLane, 0);
    }

    // Tx current level = Rx adjust request; max-reach flags follow the level
    ScalerDisplayDPTxLaneSetCurrent(pucCur, ucAdjVol, ucAdjPre);

    return _SUCCESS;
}

//--------------------------------------------------
// Description  : DP Tx Link Training 2 Lane Adjust (lane 0..3, #295)
// Input Value  : ucLane
// Output Value :
//--------------------------------------------------
static void ScalerDisplayDPTx1TP2LaneAdjust(BYTE ucLane)
{
    BYTE __xdata *pucCur = &g_stDisplayDPTx1LTInfo.ucLane0Adjust + ucLane;
    BYTE __xdata *pucReq = &g_stDisplayDPTx1LTInfo.ucAdjustReqLane01 + (ucLane >> 1);
    BYTE ucShift = (ucLane & 1) << 2;
    BYTE ucCurVol = *pucCur & (_BIT1 | _BIT0);
    BYTE ucAdjPre = (*pucReq >> (ucShift + 2)) & (_BIT1 | _BIT0);

    // Check: (Current Vol swing level + Adjust pre emphasis level) > 3
    if((ucCurVol + ucAdjPre) > _DISPLAY_DP_TX_LEVEL_3)
    {
        ucAdjPre = _DISPLAY_DP_TX_LEVEL_3 - ucCurVol;
    }
    else
    {
        ucCurVol = (*pucReq >> ucShift) & (_BIT1 | _BIT0);
    }

    ScalerDisplayDPTxLaneSetCurrent(pucCur, ucCurVol, ucAdjPre);
}

#if(_PANEL_DPTX_FORCE_OUTPUT_SUPPORT == _ON)
//--------------------------------------------------
// Description  : DP Tx Link Signal Force Output
// Input Value  :
// Output Value :
//--------------------------------------------------
void ScalerDisplayDPTx1LinkForceOutput(void)
{
    ScalerDisplayDPTx1ForceOutputPreCheck();

    ScalerDisplayDPTx1TPInitialSet();

    // Set Output Signal According to Request
    ScalerDisplayDPTx1MLPHYSet();

    // Training Pattern 1 For Link Training
    // Repeat Bist Pattern --> for Training Pattern
    ScalerSetBit(P38_85_PHY0_TXBIST_00_H2, ~(_BIT7 | _BIT6), (_BIT7 | _BIT6));

    // Select TP1
    ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~_BIT5, _BIT5);

    pData[0] = (_DISPLAY_DP_TX_TP_1 | _DISPLAY_DP_TX_SCRAMBLING_DISABLE);
    pData[1] = g_stDisplayDPTx1LTInfo.ucLane0Adjust;
    pData[2] = g_stDisplayDPTx1LTInfo.ucLane1Adjust;
    pData[3] = g_stDisplayDPTx1LTInfo.ucLane2Adjust;
    pData[4] = g_stDisplayDPTx1LTInfo.ucLane3Adjust;

    // Write DPCD 102h-107h to Start TP1
    ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x02, 5, pData);

    // Delay Time us [400,x]
    DELAY_XUS(400);

    // Training Pattern 2 For Link Training
    // Repeat Bist Pattern --> for Training Pattern
    ScalerSetBit(P38_85_PHY0_TXBIST_00_H2, ~(_BIT7 | _BIT6), (_BIT7 | _BIT6));

    // Disable De-Scambling
    ScalerSetBit(P38_89_PHY0_TXBIST_01_H2, ~_BIT1, _BIT1);

    // Select TP2
    ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~_BIT5, 0x00);

    pData[0] = (_DISPLAY_DP_TX_TP_2 | _DISPLAY_DP_TX_SCRAMBLING_DISABLE);
    pData[1] = g_stDisplayDPTx1LTInfo.ucLane0Adjust;
    pData[2] = g_stDisplayDPTx1LTInfo.ucLane1Adjust;
    pData[3] = g_stDisplayDPTx1LTInfo.ucLane2Adjust;
    pData[4] = g_stDisplayDPTx1LTInfo.ucLane3Adjust;

    // Write DPCD 102h-107h to Start TP2
    ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x02, 5, pData);

    // Delay Time us [400,x]
    DELAY_XUS(400);

#if(_PANEL_DPTX_AUX_SET_TP_END_SEQUENCE == _TRAIN_PATTERN_END_BEFORE_IDEL_PATTERN)
    // Training Pattern End For Link Training
    pData[0] = _DISPLAY_DP_TX_TP_NONE;
    ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x02, 1, pData);
#endif

#if(_PANEL_DPTX_SCRAMBLE_SEED_TYPE == _PANEL_DPTX_SCRAMBLE_SEED_AUTO)
    if(GET_DISPLAY_DP_TX1_ALTERNATE_SR_CAPABLE() == _TRUE)
    {
        // Scambling Seed Select to 0xFFFE
        ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~_BIT4, 0x00);

        pData[0] = ((BYTE)GET_DISPLAY_DP_TX1_FRAMING_CHANGE_CAPABLE() << 1) | _BIT0;
        ScalerDisplayDPTx1NativeAuxWrite(0x00, 0x01, 0x0A, 1, pData);
    }
    else
    {
        // Scambling Seed Select to 0xFFFF
        ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~_BIT4, _BIT4);
    }
#elif(_PANEL_DPTX_SCRAMBLE_SEED_TYPE == _PANEL_DPTX_SCRAMBLE_SEED_0XFFFE)

    // Scambling Seed Select to 0xFFFE
    ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~_BIT4, 0x00);

#elif(_PANEL_DPTX_SCRAMBLE_SEED_TYPE == _PANEL_DPTX_SCRAMBLE_SEED_0XFFFF)

    // Scambling Seed Select to 0xFFFF
    ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~_BIT4, _BIT4);

#endif // End of #if(_PANEL_DPTX_SCRAMBLE_SEED_TYPE == _PANEL_DPTX_SCRAMBLE_SEED_AUTO)

    // Enable Scambling
    ScalerSetBit(P38_89_PHY0_TXBIST_01_H2, ~_BIT1, 0x00);

    // Enable BS replaced by SR
    ScalerSetBit(P9C_0D_DPTX_PHY_CTRL, ~_BIT4, _BIT4);

    // Main Link switch to IDLE Pattern
    ScalerDisplayDPTx1VideoStreamOutput(_DISABLE);

    // Disable bist mode
    ScalerSetBit(P38_88_PHY0_TXBIST_00_L1, ~(_BIT3 | _BIT2), 0x00);

    // Disable Bist Pattern --> for Video Data
    ScalerSetBit(P38_85_PHY0_TXBIST_00_H2, ~_BIT7, 0x00);
}

//--------------------------------------------------
// Description  : DP Tx Force Output Pre-Check
// Input Value  :
// Output Value :
//--------------------------------------------------
void ScalerDisplayDPTx1ForceOutputPreCheck(void)
{
    if(GET_DISPLAY_DP_TX1_LINK_CONFIG() == _TRUE)
    {
        return;
    }

    switch(_PANEL_DPTX_LANE_NUMBER)
    {
        case _PANEL_DPTX_LANE_NUMBER_1:

            // Set Lane Number: 1
            SET_DISPLAY_DP_TX1_LANE_NUM(_DP_ONE_LANE);

            break;

        case _PANEL_DPTX_LANE_NUMBER_2:

            // Set Lane Number: 2
            SET_DISPLAY_DP_TX1_LANE_NUM(_DP_TWO_LANE);

            break;

        case _PANEL_DPTX_LANE_NUMBER_4:
        case _PANEL_DPTX_LANE_NUMBER_8:

            // Set Lane Number: 4
            SET_DISPLAY_DP_TX1_LANE_NUM(_DP_FOUR_LANE);

            break;

        default:

            // Set Lane Number: 4
            SET_DISPLAY_DP_TX1_LANE_NUM(_DP_FOUR_LANE);

            break;
    }
}
#endif

//--------------------------------------------------
// Description  : DP Tx Link Training Link Rate Reduce
// Input Value  :
// Output Value :
//--------------------------------------------------
void ScalerDisplayDPTx1SignalReset(void)
{
    // Set Voltage Swing and pre-emphasis Variable to level 0
    CLR_DISPLAY_DP_TX1_TP1_LANE0_SAME_VOL_CNT();
    CLR_DISPLAY_DP_TX1_TP1_LANE1_SAME_VOL_CNT();
    CLR_DISPLAY_DP_TX1_TP1_LANE2_SAME_VOL_CNT();
    CLR_DISPLAY_DP_TX1_TP1_LANE3_SAME_VOL_CNT();

    SET_DISPLAY_DP_TX1_LANE0_CURRENT_VOL_SWING(_DISPLAY_DP_TX_LEVEL_0);
    CLR_DISPLAY_DP_TX1_LANE0_CURRENT_VOL_SWING_MAX_REACH();
    SET_DISPLAY_DP_TX1_LANE0_CURRENT_PRE_EMPHASIS(_DISPLAY_DP_TX_LEVEL_0);
    CLR_DISPLAY_DP_TX1_LANE0_CURRENT_PRE_EMPHASIS_MAX_REACH();

    SET_DISPLAY_DP_TX1_LANE1_CURRENT_VOL_SWING(_DISPLAY_DP_TX_LEVEL_0);
    CLR_DISPLAY_DP_TX1_LANE1_CURRENT_VOL_SWING_MAX_REACH();
    SET_DISPLAY_DP_TX1_LANE1_CURRENT_PRE_EMPHASIS(_DISPLAY_DP_TX_LEVEL_0);
    CLR_DISPLAY_DP_TX1_LANE1_CURRENT_PRE_EMPHASIS_MAX_REACH();

    SET_DISPLAY_DP_TX1_LANE2_CURRENT_VOL_SWING(_DISPLAY_DP_TX_LEVEL_0);
    CLR_DISPLAY_DP_TX1_LANE2_CURRENT_VOL_SWING_MAX_REACH();
    SET_DISPLAY_DP_TX1_LANE2_CURRENT_PRE_EMPHASIS(_DISPLAY_DP_TX_LEVEL_0);
    CLR_DISPLAY_DP_TX1_LANE2_CURRENT_PRE_EMPHASIS_MAX_REACH();

    SET_DISPLAY_DP_TX1_LANE3_CURRENT_VOL_SWING(_DISPLAY_DP_TX_LEVEL_0);
    CLR_DISPLAY_DP_TX1_LANE3_CURRENT_VOL_SWING_MAX_REACH();
    SET_DISPLAY_DP_TX1_LANE3_CURRENT_PRE_EMPHASIS(_DISPLAY_DP_TX_LEVEL_0);
    CLR_DISPLAY_DP_TX1_LANE3_CURRENT_PRE_EMPHASIS_MAX_REACH();

    // Clear TP2 Count
    CLR_DISPLAY_DP_TX1_TP2_CNT();

    // Set Output Signal According to Request
    ScalerDisplayDPTx1MLPHYSet();
}

//--------------------------------------------------
// Description  : Handle Enhance Framing
// Input Value  : _ENABLE of _DISABLE
// Output Value : None
//--------------------------------------------------
void ScalerDisplayDPTx1EnhanceFramingMode(bit bEnable)
{
    // Disable Digital PHY Enhancement
    ScalerSetBit(P38_89_PHY0_TXBIST_01_H2, ~_BIT3, 0x00);

    // Enable Enhancement
    ScalerSetBit(P9C_A0_DP_MAC_CTRL, ~_BIT2, ((BYTE)bEnable << 2));
}

//--------------------------------------------------
// Description  : Measure function for DPTX SST D0
// Input Value  : None
// Output Value : _TRUE or _FALSE
//--------------------------------------------------
bit ScalerDisplayDPTx1MeasureInputInfo(void)
{
    ScalerSetByte(P0_2A_DISPLAY_FORMAT_ADDR_PORT, _P0_2B_PT_02_DISPLAY_HOR_SYNC_END);
    ScalerRead(P0_2B_DISPLAY_FORMAT_DATA_PORT, 3, &pData[3], _NON_AUTOINC);

    ScalerSetByte(P0_2A_DISPLAY_FORMAT_ADDR_PORT, _P0_2B_PT_09_DISPLAY_HOR_BG_END_H);
    ScalerRead(P0_2B_DISPLAY_FORMAT_DATA_PORT, 2, &pData[6], _NON_AUTOINC);

    // Htotal
    g_stDisplayDPTx1TimingInfo.usHTotal = GET_DIS_TIMING_GEN_H_TOTAL() / _PANEL_DPTX_DCLK_DIV;

    // Hstart
    g_stDisplayDPTx1TimingInfo.usHStart = (PDATA_WORD(2) & 0x1FFF) / _PANEL_DPTX_DCLK_DIV;

    // Hwidth
    g_stDisplayDPTx1TimingInfo.usHWidth = ((PDATA_WORD(3) & 0x1FFF) - (PDATA_WORD(2) & 0x1FFF)) / _PANEL_DPTX_DCLK_DIV;

    // Hsyc
    g_stDisplayDPTx1TimingInfo.usHSWidth = pData[3] / _PANEL_DPTX_DCLK_DIV;

    // Hsyc polarity
    g_stDisplayDPTx1TimingInfo.b1HSP = 1;

    if(ScalerMDomainGetFrameSyncMode() == _FRAME_SYNC_MODE)
    {
#if(_FRC_SUPPORT == _ON)
        // M:N frame sync
        if(ScalerGetDataPortBit(P0_2A_DISPLAY_FORMAT_ADDR_PORT, _P0_2B_PT_25_MN_FRAME_RATE_EN, _BIT7) == _BIT7)
        {
            BYTE ucTemp = 0;

            // Get DVtotal of frame sync frame in M:N case
            ScalerSetBit(P0_43_FS_DELAY_FINE_TUNE, ~_BIT5, _BIT5);
            ScalerSetBit(P0_44_LAST_LINE_H, ~_BIT7, _BIT7);

            // Get N+1 frame
            ucTemp = (ScalerMemoryGetMNRatio() & 0x00FF) + 1;

            // Wait N+1 dvs for get correct __data
            do
            {
                ucTemp--;
                ScalerTimerWaitForEvent(_EVENT_DVS);
            }
            while(ucTemp > 0);

            GET_DVTOTAL_LASTLINE(PDATA_WORD(0));
            ScalerSetBit(P0_43_FS_DELAY_FINE_TUNE, ~_BIT5, 0x00);

            PDATA_WORD(1) = GET_FREE_RUN_DVTOTAL();

            // Compare DVtotal of frame sync frame and DVtotal of free run frame
            if(PDATA_WORD(1) < PDATA_WORD(0))
            {
                PDATA_WORD(0) = PDATA_WORD(1);
            }
        }
        else
#endif
        {
            ScalerSetBit(P0_43_FS_DELAY_FINE_TUNE, ~_BIT5, 0x00);
            ScalerSetBit(P0_44_LAST_LINE_H, ~_BIT7, _BIT7);
            ScalerTimerWaitForEvent(_EVENT_DVS);
            ScalerTimerWaitForEvent(_EVENT_DVS);
            GET_DVTOTAL_LASTLINE(PDATA_WORD(0));
        }

#if((_PANEL_DPTX_VENDOR_SPECIFIC_TYPE & _PANEL_DPTX_VENDOR_SPECIFIC_VTOTAL_MINUS_1) == _PANEL_DPTX_VENDOR_SPECIFIC_VTOTAL_MINUS_1)
        // Vtotal
        PDATA_WORD(0) = ((PDATA_WORD(0) >= 1) ? (PDATA_WORD(0) - 1) : (PDATA_WORD(0)));
#endif
    }
    else
    {
        PDATA_WORD(0) = GET_FREE_RUN_DVTOTAL();
    }

    ScalerSetByte(P0_2A_DISPLAY_FORMAT_ADDR_PORT, _P0_2B_PT_0D_DISPLAY_VER_SYNC_END);
    ScalerRead(P0_2B_DISPLAY_FORMAT_DATA_PORT, 3, &pData[3], _NON_AUTOINC);

    ScalerSetByte(P0_2A_DISPLAY_FORMAT_ADDR_PORT, _P0_2B_PT_14_DISPLAY_VER_BG_END_H);
    ScalerRead(P0_2B_DISPLAY_FORMAT_DATA_PORT, 2, &pData[6], _NON_AUTOINC);

    // Vtotal
    g_stDisplayDPTx1TimingInfo.usVTotal = ((PDATA_WORD(0) + 1) & 0x1FFF);

    // VStart
    g_stDisplayDPTx1TimingInfo.usVStart = (PDATA_WORD(2) & 0x1FFF);

    // VHeight
    g_stDisplayDPTx1TimingInfo.usVHeight = (PDATA_WORD(3) & 0x1FFF) - (PDATA_WORD(2) & 0x1FFF);

    // Vsync
    g_stDisplayDPTx1TimingInfo.usVSWidth = (pData[3]);

    // Vsyc polarity
    g_stDisplayDPTx1TimingInfo.b1VSP = 1;

    return _TRUE;
}

//--------------------------------------------------
// Description  : Dp Tx ML set VoltageSwing and PreEmphasis
// Input Value  : LaneX - 0~3 VoltageSwing - 0~3 PreEmphasis - 0~3     //Linqian
// Output Value :
//--------------------------------------------------
void ScalerDisplayDPTx1MLPHYSet(void)
{
    switch(GET_DISPLAY_DP_TX1_LANE_NUM())
    {
        case _DP_FOUR_LANE:

            // Adjust Lane3 PHY voltage swing level and Pre-emphasis
            ScalerDisplayDPTx1SetSignalLevel(_DISPLAY_DP_TX_LANE_3, GET_DISPLAY_DP_TX1_LANE3_CURRENT_VOL_SWING(), GET_DISPLAY_DP_TX1_LANE3_CURRENT_PRE_EMPHASIS());

            // Adjust Lane2 PHY voltage swing level and Pre-emphasis
            ScalerDisplayDPTx1SetSignalLevel(_DISPLAY_DP_TX_LANE_2, GET_DISPLAY_DP_TX1_LANE2_CURRENT_VOL_SWING(), GET_DISPLAY_DP_TX1_LANE2_CURRENT_PRE_EMPHASIS());

            // Adjust Lane1 PHY voltage swing level and Pre-emphasis
            ScalerDisplayDPTx1SetSignalLevel(_DISPLAY_DP_TX_LANE_1, GET_DISPLAY_DP_TX1_LANE1_CURRENT_VOL_SWING(), GET_DISPLAY_DP_TX1_LANE1_CURRENT_PRE_EMPHASIS());

            // Adjust Lane0 PHY voltage swing level and Pre-emphasis
            ScalerDisplayDPTx1SetSignalLevel(_DISPLAY_DP_TX_LANE_0, GET_DISPLAY_DP_TX1_LANE0_CURRENT_VOL_SWING(), GET_DISPLAY_DP_TX1_LANE0_CURRENT_PRE_EMPHASIS());

            break;

        case _DP_TWO_LANE:

            // Adjust Lane1 PHY voltage swing level and Pre-emphasis
            ScalerDisplayDPTx1SetSignalLevel(_DISPLAY_DP_TX_LANE_1, GET_DISPLAY_DP_TX1_LANE1_CURRENT_VOL_SWING(), GET_DISPLAY_DP_TX1_LANE1_CURRENT_PRE_EMPHASIS());

            // Adjust Lane0 PHY voltage swing level and Pre-emphasis
            ScalerDisplayDPTx1SetSignalLevel(_DISPLAY_DP_TX_LANE_0, GET_DISPLAY_DP_TX1_LANE0_CURRENT_VOL_SWING(), GET_DISPLAY_DP_TX1_LANE0_CURRENT_PRE_EMPHASIS());

            break;

        case _DP_ONE_LANE:

            // Adjust Lane0 PHY voltage swing level and Pre-emphasis
            ScalerDisplayDPTx1SetSignalLevel(_DISPLAY_DP_TX_LANE_0, GET_DISPLAY_DP_TX1_LANE0_CURRENT_VOL_SWING(), GET_DISPLAY_DP_TX1_LANE0_CURRENT_PRE_EMPHASIS());

            break;

        default:

            // Adjust Lane0 PHY voltage swing level and Pre-emphasis
            ScalerDisplayDPTx1SetSignalLevel(_DISPLAY_DP_TX_LANE_0, GET_DISPLAY_DP_TX1_LANE0_CURRENT_VOL_SWING(), GET_DISPLAY_DP_TX1_LANE0_CURRENT_PRE_EMPHASIS());

            break;
    }
}

//--------------------------------------------------
// Description  : DP Tx Native Aux Write
// Input Value  : ucCommand --> Native Aux Write Command
//                ucHighAddress --> High Byte of  Native Aux Write Address
//                ucMidAddress --> Middle Byte of  Native Aux Write Address
//                ucLowAddress --> Low Byte of  Native Aux Write Address
//                ucLength --> Native Aux Write Length
//                ucAutoInc --> Address Auto Increase flag
//                pWriteArray --> Data Array of of  Native Aux Write
// Output Value : TRUE --> Native Aux Write Sucessful
//--------------------------------------------------
bit ScalerDisplayDPTx1NativeAuxWrite(BYTE ucAddrH, BYTE ucAddrM, BYTE ucAddrL, BYTE ucLength, BYTE *pucWriteArray)
{
    if(ScalerDisplayDPTx1AuxWrite((0x80 | ucAddrH), ucAddrM, ucAddrL, ucLength, pucWriteArray) == _FALSE)
    {
        return _FALSE;
    }

    return _TRUE;
}

//--------------------------------------------------
// Description  : DP Tx Native Aux Read
// Input Value  : ucCommand --> Native Aux Read Command
//                ucHighAddress --> High Byte of  Native Aux Read Address
//                ucMidAddress --> Middle Byte of  Native Aux Read Address
//                ucLowAddress --> Low Byte of  Native Aux Read Address
//                ucLength --> Native Aux Read Length
//                ucAutoInc --> Address Auto Increase flag
//                pWriteArray --> Data Array of of  Native Aux Read
// Output Value : TRUE --> Native Aux Read Sucessful
//--------------------------------------------------
bit ScalerDisplayDPTx1NativeAuxRead(BYTE ucAddrH, BYTE ucAddrM, BYTE ucAddrL, BYTE ucLength, BYTE *pucReadArray)
{
    if(ScalerDisplayDPTx1AuxRead((0x90 | ucAddrH), ucAddrM, ucAddrL, ucLength, pucReadArray) == _FALSE)
    {
        return _FALSE;
    }

    return _TRUE;
}

//--------------------------------------------------
// Description  : DP Tx AuxInitial
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDisplayDPTx1AuxInitial(void)
{
    // Power Down Aux CH
    ScalerSetBit(P9D_A0_AUX_TX_CTRL, ~_BIT0, 0x00);

    // Setting Aux
    ScalerDisplayDPTx1AuxPHYSet(_DISPLAY_DP_TX_AUX_DIFF_MODE);

    // Set Aux Timeout
    ScalerSetByte(P9D_A1_AUX_TIMEOUT, 0x95);

    // Sync end Pattern Error Handle Disable
    ScalerSetBit(P9D_F6_AUX_DIG_PHY8, ~_BIT1, _BIT1);

    // Power On Aux Channel
    ScalerSetBit(P9D_A0_AUX_TX_CTRL, ~_BIT0, _BIT0);
}

//--------------------------------------------------
// Description  : DP Tx Aux Read
// Input Value  : ucCommand --> Aux Read Command
//                ucHighAddress --> High Byte of  Aux Read Address
//                ucMidAddress --> Middle Byte of  Aux Read Address
//                ucLowAddress --> Low Byte of  Aux Read Address
//                ucLength --> Aux Read Length
//                ucAutoInc --> Address Auto Increase flag
//                pWriteArray --> Data Array of Aux Read
// Output Value : TRUE --> Aux Read Sucessful
//--------------------------------------------------
bit ScalerDisplayDPTx1AuxRead(BYTE ucCommandAddrH, BYTE ucAddrM, BYTE ucAddrL, BYTE ucLength, BYTE *pucReadArray)
{
    BYTE ucAuxPollingCount = 0;
    BYTE ucDataCount = 0;
    BYTE ucReadRetryNum = 0;
    BYTE ucCheckLength = 0;
    BYTE ucOffsetLength = 0;
    BYTE ucTotal = ((ucLength == 0) ? 1 : ucLength);    // ucLength below is the rest of this request

    // Enable AUX FW Handle Mode
    ScalerSetBit(P9D_A3_AUXTX_TRAN_CTRL, ~(_BIT7 | _BIT5), _BIT5);

    // Disable Address only transaction
    ScalerSetBit(P9D_A3_AUXTX_TRAN_CTRL, ~_BIT7, 0x00);

    do
    {
        ucReadRetryNum = 0;

        // Enable Retry Mechanism
        ScalerSetBit(P9D_B0_AUX_RETRY_2, ~_BIT7, 0x00);

        // Enable Timeout HW Retry
        ScalerSetBit(P9D_B0_AUX_RETRY_2, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), (_BIT7 | _BIT5));

        // CLR Flag
        ScalerSetByte(P9D_B1_AUX_IRQ_EVENT, 0x3F);

        // Reset AUX FIFO
        ScalerSetBit(P9D_AB_AUX_FIFO_CTRL, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));

        // Setting DPCD Read Address
        ScalerSetByte(P9D_A4_AUXTX_REQ_CMD, ucCommandAddrH);
        ScalerSetByte(P9D_A5_AUXTX_REQ_ADDR_M, ucAddrM);
        ScalerSetByte(P9D_A6_AUXTX_REQ_ADDR_L, (ucAddrL + ucOffsetLength));

        ucLength = ucTotal - ucOffsetLength;

        if(ucLength == 0)
        {
            ucLength = 1;
        }
        else if(ucLength > 16)
        {
            ucLength = 16;
        }

        // Set Read Length : TX_LEN = ucLength-1
        ScalerSetByte(P9D_A7_AUXTX_REQ_LEN, (ucLength - 1));

        // Reset AUX Start Bit
        ScalerSetBit(P9D_A3_AUXTX_TRAN_CTRL, ~_BIT0, 0x00);

        // Enable Aux to Start Read
        ScalerSetBit(P9D_A3_AUXTX_TRAN_CTRL, ~_BIT0, _BIT0);

        do
        {
            // Delay Time us [400,x]
            DELAY_XUS(400);

            // Delay Time us [5,175] Polling AUX Done Bit
            for(ucAuxPollingCount = 0; ucAuxPollingCount < 25; ucAuxPollingCount++)
            {
                DELAY_5US();

                if(ScalerGetBit(P9D_B1_AUX_IRQ_EVENT, _BIT5) == _BIT5)
                {
                    // awto: one FIFO_WR_PTR read bounds both the check and the copy; longer than the request = stale FIFO, retried (#247)
                    ucCheckLength = ScalerGetBit(P9D_AE_AUX_FIFO_WR_PTR, (_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0));

                    // Reply Error or Nack or Command is not ACK
                    if((ScalerGetBit(P9D_B1_AUX_IRQ_EVENT, _BIT2) != 0x00) || (ScalerGetBit(P9D_A9_AUX_REPLY_CMD, (_BIT5 | _BIT4)) != 0x00) ||
                       (ucCheckLength > ucLength))
                    {
                        // CLR Flag
                        ScalerSetByte(P9D_B1_AUX_IRQ_EVENT, 0x3F);

                        // Reset AUX FIFO
                        ScalerSetBit(P9D_AB_AUX_FIFO_CTRL, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));

                        // Reset AUX Start Bit
                        ScalerSetBit(P9D_A3_AUXTX_TRAN_CTRL, ~_BIT0, 0x00);

                        // Enable Aux to Start Read
                        ScalerSetBit(P9D_A3_AUXTX_TRAN_CTRL, ~_BIT0, _BIT0);
                    }
                    else
                    {
                        ucOffsetLength += ucCheckLength;

                        // Read Data From Buffer
                        for(ucDataCount = 0; ucDataCount < ucCheckLength; ucDataCount++)
                        {
                            *pucReadArray = ScalerGetByte(P9D_AA_AUX_REPLY_DATA);
                            pucReadArray++;
                        }

                        if(ucOffsetLength == ucTotal)
                        {
                            // Disable Timeout Retry
                            ScalerSetBit(P9D_B0_AUX_RETRY_2, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), 0x00);

                            // CLR Flag
                            ScalerSetByte(P9D_B1_AUX_IRQ_EVENT, 0x3F);

                            // Reset AUX FIFO
                            ScalerSetBit(P9D_AB_AUX_FIFO_CTRL, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));

                            return _TRUE;
                        }
                    }

                    break;
                }
                else
                {
                    // HW Retry Times Reaches RETRY_NUM
                    if(ScalerGetBit(P9D_B1_AUX_IRQ_EVENT, _BIT1) == _BIT1)
                    {
                        // Disable Timeout Retry
                        ScalerSetBit(P9D_B0_AUX_RETRY_2, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), 0x00);

                        // CLR Flag
                        ScalerSetByte(P9D_B1_AUX_IRQ_EVENT, 0x3F);

                        // Reset AUX FIFO
                        ScalerSetBit(P9D_AB_AUX_FIFO_CTRL, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));

                        return _FALSE;
                    }
                }
            }

            // Increasing Retry Num
            ucReadRetryNum += 1;
        }
        while((ucReadRetryNum < 7) && (ScalerGetBit(P9D_AE_AUX_FIFO_WR_PTR, (_BIT4 | _BIT3 | _BIT2 | _BIT1 | _BIT0)) == 0x00));
    }
    while((ucOffsetLength != ucTotal) && (ucReadRetryNum < 7));

    // Disable Timeout Retry
    ScalerSetBit(P9D_B0_AUX_RETRY_2, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), 0x00);

    // CLR Flag
    ScalerSetByte(P9D_B1_AUX_IRQ_EVENT, 0x3F);

    // Reset AUX FIFO
    ScalerSetBit(P9D_AB_AUX_FIFO_CTRL, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));

    // Delay Time us [400,x]
    DELAY_XUS(400);

    return _FALSE;
}

//--------------------------------------------------
// Description  : DP Tx Aux Write
// Input Value  : ucCommand --> Aux Write Command
//                ucHighAddress --> High Byte of  Aux Write Address
//                ucMidAddress --> Middle Byte of  Aux Write Address
//                ucLowAddress --> Low Byte of  Aux Write Address
//                ucLength --> Aux Write Length
//                ucAutoInc --> Address Auto Increase flag
//                pWriteArray --> Data Array of of Aux Write
// Output Value : TRUE --> Aux Write Sucessful
//--------------------------------------------------
bit ScalerDisplayDPTx1AuxWrite(BYTE ucCommandAddrH, BYTE ucAddrM, BYTE ucAddrL, BYTE ucLength, BYTE *pucWriteArray)
{
    BYTE ucAuxPollingCount = 0;
    BYTE ucDataCount = 0;
    BYTE ucWriteRetryNum = 0;

    // Enable Timeout Retry
    ScalerSetBit(P9D_B0_AUX_RETRY_2, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), (_BIT7 | _BIT5));

    // Reset FIFO
    ScalerSetBit(P9D_AB_AUX_FIFO_CTRL, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));

    // CLR Flag
    ScalerSetByte(P9D_B1_AUX_IRQ_EVENT, 0x3F);

    // Disable Address only transaction
    ScalerSetBit(P9D_A3_AUXTX_TRAN_CTRL, ~_BIT7, 0x00);

    ScalerSetByte(P9D_A4_AUXTX_REQ_CMD, ucCommandAddrH);
    ScalerSetByte(P9D_A5_AUXTX_REQ_ADDR_M, ucAddrM);
    ScalerSetByte(P9D_A6_AUXTX_REQ_ADDR_L, ucAddrL);

    // Check Length
    if(ucLength == 0)
    {
        ucLength = 1;
    }
    else if(ucLength > 16)
    {
        ucLength = 16;
    }

    // Setting AUX Write Length : TX_LEN = ucLength-1
    ScalerSetByte(P9D_A7_AUXTX_REQ_LEN, (ucLength - 1));

    // Write Data to Buffer
    for(ucDataCount = 0; ucDataCount < ucLength; ucDataCount++)
    {
        ScalerSetByte(P9D_A8_AUXTX_REQ_DATA, pucWriteArray[ucDataCount]);
    }

    // Reset AUX Start Bit
    ScalerSetBit(P9D_A3_AUXTX_TRAN_CTRL, ~_BIT0, 0x00);

    // Enable Aux to Start Write
    ScalerSetBit(P9D_A3_AUXTX_TRAN_CTRL, ~_BIT0, _BIT0);

    while(ucWriteRetryNum < 7)
    {
        // Delay Time us [400,x]
        DELAY_XUS(400);

        // Delay Time us [5,175] Polling AUX Done Bit
        for(ucAuxPollingCount = 0; ucAuxPollingCount < 25; ucAuxPollingCount++)
        {
            DELAY_5US();

            if(ScalerGetBit(P9D_B1_AUX_IRQ_EVENT, _BIT5) == _BIT5)
            {
                // Reply Error or Nack or Command is not ACK
                if((ScalerGetBit(P9D_B1_AUX_IRQ_EVENT, _BIT2) != 0x00) || (ScalerGetBit(P9D_A9_AUX_REPLY_CMD, (_BIT5 | _BIT4)) != 0x00))
                {
                    // CLR Flag
                    ScalerSetByte(P9D_B1_AUX_IRQ_EVENT, 0x3F);

                    // Reset FIFO
                    ScalerSetBit(P9D_AB_AUX_FIFO_CTRL, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));

                    // Write Data to Buffer
                    for(ucDataCount = 0; ucDataCount < ucLength; ucDataCount++)
                    {
                        ScalerSetByte(P9D_A8_AUXTX_REQ_DATA, pucWriteArray[ucDataCount]);
                    }

                    // Reset AUX Start Bit
                    ScalerSetBit(P9D_A3_AUXTX_TRAN_CTRL, ~_BIT0, 0x00);

                    // Enable Aux to Start Write
                    ScalerSetBit(P9D_A3_AUXTX_TRAN_CTRL, ~_BIT0, _BIT0);

                    break;
                }
                else
                {
                    // Disable Timeout Retry
                    ScalerSetBit(P9D_B0_AUX_RETRY_2, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), 0x00);

                    // CLR Flag
                    ScalerSetByte(P9D_B1_AUX_IRQ_EVENT, 0x3F);

                    // Reset FIFO
                    ScalerSetBit(P9D_AB_AUX_FIFO_CTRL, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));

                    return _TRUE;
                }
            }
            else
            {
                // HW Retry Times Reaches RETRY_NUM
                if(ScalerGetBit(P9D_B1_AUX_IRQ_EVENT, _BIT1) == _BIT1)
                {
                    // Disable Timeout Retry
                    ScalerSetBit(P9D_B0_AUX_RETRY_2, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), 0x00);

                    // CLR Flag
                    ScalerSetByte(P9D_B1_AUX_IRQ_EVENT, 0x3F);

                    // Reset FIFO
                    ScalerSetBit(P9D_AB_AUX_FIFO_CTRL, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));

                    return _FALSE;
                }
            }
        }

        // Increasing Retry Num
        ucWriteRetryNum += 1;
    }

    // Disable Timeout Retry
    ScalerSetBit(P9D_B0_AUX_RETRY_2, ~(_BIT7 | _BIT6 | _BIT5 | _BIT4 | _BIT3), 0x00);

    // CLR Flag
    ScalerSetByte(P9D_B1_AUX_IRQ_EVENT, 0x3F);

    // Reset FIFO
    ScalerSetBit(P9D_AB_AUX_FIFO_CTRL, ~(_BIT1 | _BIT0), (_BIT1 | _BIT0));

    // Delay Time us [400,x]
    DELAY_XUS(400);

    return _FALSE;
}

//--------------------------------------------------
// Description  : DP Tx Hpd Initial
// Input Value  : None
// Output Value : None
//--------------------------------------------------
void ScalerDisplayDPTx1HpdInitial(void)
{
    // Set HPD 1ms Timer to 2ms
    ScalerSetBit(P9C_73_HPD_TIMER1, ~(_BIT3 | _BIT2 | _BIT1 | _BIT0), (_BIT3 | _BIT2 | _BIT0));
    ScalerSetByte(P9C_75_HPD_TIMER3, 0x2C);

    // Set HPD 30ms Timer
    ScalerSetByte(P9C_78_HPD_TIMER6, 0xC5);
    ScalerSetByte(P9C_79_HPD_TIMER7, 0xBD);

    // Enable HPD Detection
    ScalerSetBit(P9C_70_HPD_CTRL, ~_BIT7, 0x00);
    ScalerSetBit(P9C_70_HPD_CTRL, ~_BIT7, _BIT7);

    // Clear HPD IRQ Flag
    ScalerSetByte(P9C_71_HPD_IRQ, 0xFE);

    // Disable Short IRQ and Disable Long IRQ
    ScalerSetByte(P9C_72_HPD_IRQ_EN, 0x00);
}

#if(_PANEL_DPTX_HPD_DETECT == _ON)
//--------------------------------------------------
// Description  : Display DP Tx HPD Detection
// Input Value  : None
// Output Value : None
//--------------------------------------------------
bit ScalerDisplayDPTx1HpdDetect(void)
{
    // Determine Current HPD Event Status
    // Current HPD Level HIGH
    if(GET_DISPLAY_DP_TX1_HPD_DEBOUNCE_LEVEL() == _HIGH)
    {
        // Long HPD
        if(ScalerGetBit(P9C_71_HPD_IRQ, _BIT2) == _BIT2)
        {
            // Clr All flag
            ScalerSetByte(P9C_71_HPD_IRQ, 0xFE);

            return _TRUE;
        }
    }

    return _FALSE;
}
#endif

#endif // End of #if(_DISPLAY_DP_TX_PORT_1 == _ON)

#if(_DISPLAY_DP_TX_PORT_2 == _ON)


















#if(_PANEL_DPTX_FORCE_OUTPUT_SUPPORT == _ON)

#endif











#if(_PANEL_DPTX_HPD_DETECT == _ON)
#endif




#endif // End of #if(_DISPLAY_DP_TX_PORT_2 == _ON)

//--------------------------------------------------
// Description  : Control Vby1 Phy
// Input Value  : bit bEnable
// Output Value : None
//--------------------------------------------------
void ScalerDisplayDPTxAnalogPhyConrol(bit bEnable)
{
    // Initial Vby1 Analog PHY for DPTx
    ScalerDisplayDPTxPower(bEnable);

    // Initial Vby1 PLL for DPTx
    ScalerDisplayDPTxPLL(bEnable);

    // Initial Vby1 Digital PHY for DPTx
    ScalerDisplayDPTxPhy(bEnable);
}

#if(_PANEL_DPTX_HPD_DETECT == _ON)
//--------------------------------------------------
// Description  : Display DP Tx Stable Detection
// Input Value  : None
// Output Value : None
//--------------------------------------------------
bit ScalerDisplayDPTxStableDetect(void)
{
#if(_DISPLAY_DP_TX_PORT_1 == _ON)
    if(GET_DISPLAY_DP_TX1_STREAM_OUTPUT() != _ENABLE)
    {
        return _TRUE;
    }

    if(ScalerDisplayDPTx1HpdDetect() == _TRUE)
    {
        return _FALSE;
    }
#endif

#if(_DISPLAY_DP_TX_PORT_2 == _ON)
    if(GET_DISPLAY_DP_TX2_STREAM_OUTPUT() != _ENABLE)
    {
        return _TRUE;
    }

    if(ScalerDisplayDPTx2HpdDetect() == _TRUE)
    {
        return _FALSE;
    }
#endif

    return _TRUE;
}
#endif

#endif // End of #if(_PANEL_STYLE == _PANEL_DPTX)

