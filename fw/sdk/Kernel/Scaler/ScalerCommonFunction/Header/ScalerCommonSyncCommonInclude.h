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
// ID Code      : ScalerCommonSyncCommonInclude.h No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------

//****************************************************************************
// LAYER DEFINITIONS / MACROS
//****************************************************************************
//--------------------------------------------------
// Definitions of DP Link Traiinng Status
//--------------------------------------------------
#ifndef _DP_RX_PORT_COUNT
#define _DP_RX_PORT_COUNT                               1   // DP Rx ports with state in the per-port tables (only D1 wired)
#endif
#define _DP_RX1_PORT_INDEX                              0
#if(_DP_RX_PORT_COUNT > 1)
#define DPRX_PD1                                        BYTE ucDpRxPort   // port parameter, sole
#define DPRX_PD                                         BYTE ucDpRxPort,  // port parameter, first of several
#define DPRX_PA1                                        ucDpRxPort        // forward own port, sole
#define DPRX_PA                                         ucDpRxPort,
#define DPRX_CA1                                        _DP_RX1_PORT_INDEX // entry-point call: the Rx1 port
#define DPRX_CA                                         _DP_RX1_PORT_INDEX,
#define DPRX_P                                          ucDpRxPort
#define DPRX_TP1INIT(p)                                 (g_pucDpRxTp1Initial[p])
#define DPRX_TP1INIT_DEF                                volatile BYTE g_pucDpRxTp1Initial[_DP_RX_PORT_COUNT];
#else
#define DPRX_PD1                                        void              // one port: no parameter, index folds to 0
#define DPRX_PD
#define DPRX_PA1
#define DPRX_PA
#define DPRX_CA1
#define DPRX_CA
#define DPRX_P                                          _DP_RX1_PORT_INDEX
#define DPRX_TP1INIT(p)                                 d_g_bDpRx1Tp1Initial
#define DPRX_TP1INIT_DEF                                bit d_g_bDpRx1Tp1Initial = _FALSE;
#endif
#if(_DP_RX_PORT_COUNT > 1)
#define DPRX_T1(TYPE, NEW, OLD)  TYPE NEW[_DP_RX_PORT_COUNT]
#define DPRX_T3(TYPE, NEW, OLD)  TYPE NEW[_DP_RX_PORT_COUNT][3]
#define DPRX_T4(TYPE, NEW, OLD)  TYPE NEW[_DP_RX_PORT_COUNT][4]
#define g_pucDpRxLinkRate_P(p) g_pucDpRxLinkRate[p]
#define g_pucDpRxLaneCount_P(p) g_pucDpRxLaneCount[p]
#define g_pucDpRxLinkStatus01_P(p) g_pucDpRxLinkStatus01[p]
#define g_pucDpRxLinkStatus23_P(p) g_pucDpRxLinkStatus23[p]
#define g_pucDpRxLinkRequest01_P(p) g_pucDpRxLinkRequest01[p]
#define g_pucDpRxLinkRequest23_P(p) g_pucDpRxLinkRequest23[p]
#define g_pucDpRxEQCRC_P(p) g_pucDpRxEQCRC[p]
#define isr_g_pucDpRxLTStatus_P(p) isr_g_pucDpRxLTStatus[p]
#define g_pucDpRxTrainingPatternSet_P(p) g_pucDpRxTrainingPatternSet[p]
#define g_pucDpRxAuxAddressBackup_P(p) g_pucDpRxAuxAddressBackup[p]
#define g_ppucDpRxBackup_P(p) g_ppucDpRxBackup[p]
#define isr_g_ppucDpRxLEBound_P(p) isr_g_ppucDpRxLEBound[p]
#define isr_g_ppucDpRxTap1Max_P(p) isr_g_ppucDpRxTap1Max[p]
#define isr_g_ppucDpRxLEMax_P(p) isr_g_ppucDpRxLEMax[p]
#define g_ppucDpRxTap1MinTemp_P(p) g_ppucDpRxTap1MinTemp[p]
#define g_ppucDpRxLEMinTemp_P(p) g_ppucDpRxLEMinTemp[p]
#define isr_g_ppusDpRxClockCount_P(p) isr_g_ppusDpRxClockCount[p]
#define isr_g_ppusDpRxClockCount1_P(p) isr_g_ppusDpRxClockCount1[p]
#else
#define DPRX_T1(TYPE, NEW, OLD)  TYPE OLD
#define DPRX_T3(TYPE, NEW, OLD)  TYPE OLD[3]
#define DPRX_T4(TYPE, NEW, OLD)  TYPE OLD[4]
#define g_pucDpRxLinkRate_P(p) g_ucDpRx1LinkRate
#define g_pucDpRxLaneCount_P(p) g_ucDpRx1LaneCount
#define g_pucDpRxLinkStatus01_P(p) g_ucDpRx1LinkStatus01
#define g_pucDpRxLinkStatus23_P(p) g_ucDpRx1LinkStatus23
#define g_pucDpRxLinkRequest01_P(p) g_ucDpRx1LinkRequest01
#define g_pucDpRxLinkRequest23_P(p) g_ucDpRx1LinkRequest23
#define g_pucDpRxEQCRC_P(p) g_ucDpRx1EQCRC
#define isr_g_pucDpRxLTStatus_P(p) isr_g_ucDpRx1LTStatus
#define g_pucDpRxTrainingPatternSet_P(p) g_ucDpRx1TrainingPatternSet
#define g_pucDpRxAuxAddressBackup_P(p) g_ucDpRx1AuxAddressBackup
#define g_ppucDpRxBackup_P(p) g_pucDpRx1Backup
#define isr_g_ppucDpRxLEBound_P(p) isr_g_pucDpRx1LEBound
#define isr_g_ppucDpRxTap1Max_P(p) isr_g_pucDpRx1Tap1Max
#define isr_g_ppucDpRxLEMax_P(p) isr_g_pucDpRx1LEMax
#define g_ppucDpRxTap1MinTemp_P(p) g_pucDpRx1Tap1MinTemp
#define g_ppucDpRxLEMinTemp_P(p) g_pucDpRx1LEMinTemp
#define isr_g_ppusDpRxClockCount_P(p) isr_g_pusDpRx1ClockCount
#define isr_g_ppusDpRxClockCount1_P(p) isr_g_pusDpRx1ClockCount1
#endif
#define _DP_LINK_TRAINING_NONE                          0
#define _DP_NORMAL_TRAINING_PATTERN_1_PASS              1
#define _DP_NORMAL_TRAINING_PATTERN_1_FAIL              2
#define _DP_FAKE_TRAINING_PATTERN_1_PASS                3
#define _DP_FAKE_TRAINING_PATTERN_1_FAIL                4
#define _DP_NORMAL_TRAINING_PATTERN_2_PASS              5
#define _DP_NORMAL_TRAINING_PATTERN_2_FAIL              6
#define _DP_FAKE_TRAINING_PATTERN_2_PASS                7
#define _DP_FAKE_TRAINING_PATTERN_2_FAIL                8
#define _DP_NORMAL_LINK_TRAINING_PASS                   9
#define _DP_FAKE_LINK_TRAINING_PASS                     10
#define _DP_FAKE_LINK_TRAINING_PASS_VBIOS               11
#define _DP_LINK_TRAINING_FAIL                          12
#define _DP_LINK_STATUS_FAIL                            13
#define _DP_NORMAL_TRAINING_PATTERN_END_REBUILD_PHY     14


//--------------------------------------------------
// Macro of Link Training Status
//--------------------------------------------------
#define GET_DP_RX0_LINK_TRAINING_STATUS()               (g_ucDpRx0LTStatus)
#define SET_DP_RX0_LINK_TRAINING_STATUS(x)              (g_ucDpRx0LTStatus = (x))
#define GET_DP_RX1_LINK_TRAINING_STATUS()               (isr_g_pucDpRxLTStatus_P(_DP_RX1_PORT_INDEX))
#define GET_DP_RX_LINK_TRAINING_STATUS(port)            (isr_g_pucDpRxLTStatus_P(port))
#define SET_DP_RX1_LINK_TRAINING_STATUS(x)              (isr_g_pucDpRxLTStatus_P(_DP_RX1_PORT_INDEX) = (x))

#define GET_DP_RX0_NORMAL_LINK_TRAINING_SETPHY_FINISH() ((bit)g_bDpRx0NormalLTSetPhyFinish)
#define SET_DP_RX0_NORMAL_LINK_TRAINING_SETPHY_FINISH() (g_bDpRx0NormalLTSetPhyFinish = _TRUE)
#define CLR_DP_RX0_NORMAL_LINK_TRAINING_SETPHY_FINISH() (g_bDpRx0NormalLTSetPhyFinish = _FALSE)

#define GET_DP_RX1_NORMAL_LINK_TRAINING_SETPHY_FINISH() ((bit)d_isr_g_bDpRx1NormalLTSetPhyFinish)
#define SET_DP_RX1_NORMAL_LINK_TRAINING_SETPHY_FINISH() (d_isr_g_bDpRx1NormalLTSetPhyFinish = _TRUE)
#define CLR_DP_RX1_NORMAL_LINK_TRAINING_SETPHY_FINISH() (d_isr_g_bDpRx1NormalLTSetPhyFinish = _FALSE)


//--------------------------------------------------
//  DP LEQ RELOAD Define
//--------------------------------------------------
#define _DP_RELOAD_LEQ_INITIAL                          0
#define _DP_RELOAD_LEQ_LARGE                            1
#define _DP_RELOAD_LEQ_DEFAULT                          2


//--------------------------------------------------
// DP Sync Polarity Type
//--------------------------------------------------
#define _DP_SYNC_POLARITY_POSITIVE                      0
#define _DP_SYNC_POLARITY_NEGATIVE                      1


//--------------------------------------------------
// Definitions of Signal Detection Target Value
//--------------------------------------------------
#define _DP_VCO_TARGET_COUNT_1000_RBR                   (WORD)(((DWORD)(_DP_LINK_RBR * 27 / 2) * 1000000) / _GDI_CLK_KHZ)
#define _DP_VCO_TARGET_COUNT_1000_HBR                   (WORD)(((DWORD)(_DP_LINK_HBR * 27 / 2) * 1000000) / _GDI_CLK_KHZ)
#define _DP_VCO_TARGET_COUNT_1000_HBR2                  (WORD)(((DWORD)(_DP_LINK_HBR2 * 27 / 2) * 1000000) / _GDI_CLK_KHZ)
#define _DP_VCO_TARGET_COUNT_1000_HBR3                  (WORD)(((DWORD)(_DP_LINK_HBR3 * 27 / 2) * 1000000) / _GDI_CLK_KHZ)

#define _DP_VCO_TARGET_COUNT_2000_RBR                   (WORD)(((DWORD)(_DP_LINK_RBR * 27 / 2) * 1000000 * 2) / _GDI_CLK_KHZ)
#define _DP_VCO_TARGET_COUNT_2000_HBR                   (WORD)(((DWORD)(_DP_LINK_HBR * 27 / 2) * 1000000 * 2) / _GDI_CLK_KHZ)
#define _DP_VCO_TARGET_COUNT_2000_HBR2                  (WORD)(((DWORD)(_DP_LINK_HBR2 * 27 / 2) * 1000000 * 2) / _GDI_CLK_KHZ)
#define _DP_VCO_TARGET_COUNT_2000_HBR3                  (WORD)(((DWORD)(_DP_LINK_HBR3 * 27 / 2) * 1000000 * 2) / _GDI_CLK_KHZ)

#define _DP_RAWDATA_COUNT_SST_UPPER_BOUND_2000_RBR      (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_RBR * 65) / 100)
#define _DP_RAWDATA_COUNT_SST_UPPER_BOUND_2000_HBR      (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_HBR * 65) / 100)
#define _DP_RAWDATA_COUNT_SST_UPPER_BOUND_2000_HBR2     (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_HBR2 * 65) / 100)
#define _DP_RAWDATA_COUNT_SST_UPPER_BOUND_2000_HBR3     (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_HBR3 * 65) / 100)

#define _DP_RAWDATA_COUNT_SST_LOWER_BOUND_2000_RBR      (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_RBR * 55) / 100)
#define _DP_RAWDATA_COUNT_SST_LOWER_BOUND_2000_HBR      (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_HBR * 55) / 100)
#define _DP_RAWDATA_COUNT_SST_LOWER_BOUND_2000_HBR2     (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_HBR2 * 55) / 100)
#define _DP_RAWDATA_COUNT_SST_LOWER_BOUND_2000_HBR3     (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_HBR3 * 55) / 100)

#define _DP_RAWDATA_COUNT_MST_UPPER_BOUND_2000_RBR      (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_RBR * 65) / 100)
#define _DP_RAWDATA_COUNT_MST_UPPER_BOUND_2000_HBR      (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_HBR * 65) / 100)
#define _DP_RAWDATA_COUNT_MST_UPPER_BOUND_2000_HBR2     (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_HBR2 * 65) / 100)
#define _DP_RAWDATA_COUNT_MST_UPPER_BOUND_2000_HBR3     (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_HBR3 * 65) / 100)

#define _DP_RAWDATA_COUNT_MST_LOWER_BOUND_2000_RBR      (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_RBR * 40) / 100)
#define _DP_RAWDATA_COUNT_MST_LOWER_BOUND_2000_HBR      (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_HBR * 40) / 100)
#define _DP_RAWDATA_COUNT_MST_LOWER_BOUND_2000_HBR2     (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_HBR2 * 40) / 100)
#define _DP_RAWDATA_COUNT_MST_LOWER_BOUND_2000_HBR3     (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_2000_HBR3 * 40) / 100)

#define _DP_RAWDATA_COUNT_D10P2_UPPER_BOUND_1000_RBR    (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_1000_RBR * 110) / 100)
#define _DP_RAWDATA_COUNT_D10P2_UPPER_BOUND_1000_HBR    (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_1000_HBR * 110) / 100)
#define _DP_RAWDATA_COUNT_D10P2_UPPER_BOUND_1000_HBR2   (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_1000_HBR2 * 110) / 100)
#define _DP_RAWDATA_COUNT_D10P2_UPPER_BOUND_1000_HBR3   (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_1000_HBR3 * 110) / 100)

#define _DP_RAWDATA_COUNT_D10P2_LOWER_BOUND_1000_RBR    (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_1000_RBR * 90) / 100)
#define _DP_RAWDATA_COUNT_D10P2_LOWER_BOUND_1000_HBR    (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_1000_HBR * 90) / 100)
#define _DP_RAWDATA_COUNT_D10P2_LOWER_BOUND_1000_HBR2   (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_1000_HBR2 * 90) / 100)
#define _DP_RAWDATA_COUNT_D10P2_LOWER_BOUND_1000_HBR3   (WORD)(((DWORD)_DP_VCO_TARGET_COUNT_1000_HBR3 * 90) / 100)

//****************************************************************************
// STRUCT / TYPE / ENUM DEFINITTIONS
//****************************************************************************
typedef enum
{
    _DP_LONG_HPD_TIME = 700,
    _DP_HDCP_LONG_HPD_TIME = 800,
    _DP_MST_LONG_HPD_TIME = 800,
    _DP_HBR2_MARGIN_LINK_HPD_TIME = 800,
    _DP_MST_FORCE_LONG_HPD_TIME = 5000,
    _DP_HPD_ASSERTED_TIME = 0,
    _DP_HPD_TIME_NONE = 0xFFFF,
} EnumDpHotPlugTime;

typedef enum
{
    _DP_MEASURE_TARGET_RAW_DATA = 0x00,
    _DP_MEASURE_TARGET_CDR_CLOCK = _BIT5,
} EnumDpMeasureTarget;

typedef enum
{
#if(_HW_SIGNAL_MEASURE_GEN_TYPE == _SIGNAL_MEASURE_GEN_1)
    _DP_MEASURE_PERIOD_250_CYCLE,
#endif
    _DP_MEASURE_PERIOD_1000_CYCLE,
    _DP_MEASURE_PERIOD_2000_CYCLE,
} EnumDpMeasurePeriod;


//****************************************************************************
// VARIABLE EXTERN
//****************************************************************************
extern BYTE g_ucDpRx0LTStatus;
extern DPRX_T1(volatile BYTE, isr_g_pucDpRxLTStatus, isr_g_ucDpRx1LTStatus);
extern __xdata _Bool g_bDpRx0NormalLTSetPhyFinish;
extern volatile bit d_isr_g_bDpRx1NormalLTSetPhyFinish;

//****************************************************************************
// FUNCTION EXTERN
//****************************************************************************
extern void ScalerSyncSetDdcForceNack(BYTE ucInputPort, bit bSelect);

#if(_HW_FLASH_ACCESS_METHOD == _XDATA_MAP_ACCESS)
extern bit ScalerSyncVGAUseEmbeddedEDID(void);
extern void ScalerSyncVGADdcCheckBusyAndForceNack(void);
#endif

#ifndef AWTO_LT_RING
#define AWTO_LT_RING 0
#endif
#if(AWTO_LT_RING != 0)
// test ring (default off): 32 x {id, LT status, a, b}; idx = next slot; read with dbg-read
extern __xdata BYTE isr_g_pucAwtoLtRing[128];
extern __xdata BYTE isr_g_ucAwtoLtIdx;
#define AWTO_LT_PUT(id, a, b)       {isr_g_pucAwtoLtRing[isr_g_ucAwtoLtIdx] = (id); isr_g_pucAwtoLtRing[isr_g_ucAwtoLtIdx + 1] = isr_g_pucDpRxLTStatus_P(_DP_RX1_PORT_INDEX); isr_g_pucAwtoLtRing[isr_g_ucAwtoLtIdx + 2] = (a); isr_g_pucAwtoLtRing[isr_g_ucAwtoLtIdx + 3] = (b); isr_g_ucAwtoLtIdx = (isr_g_ucAwtoLtIdx + 4) & 0x7F;}
#define AWTO_LT_LOG_I(id)           AWTO_LT_PUT((id), ScalerDpRx1GetDpcdInfo_EXINT0(0x00, 0x01, 0x00), ScalerDpRx1GetDpcdInfo_EXINT0(0x00, 0x02, 0x02))
#define AWTO_LT_LOG_M(id)           AWTO_LT_PUT((id), ScalerDpRx1GetDpcdInfo(0x00, 0x01, 0x00), ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0x02))
#define AWTO_LT_LOG_V(id, v)        AWTO_LT_PUT((id), (v), ScalerDpRx1GetDpcdInfo(0x00, 0x02, 0x02))
#define AWTO_LT_RING_DEF __xdata BYTE isr_g_pucAwtoLtRing[128]; __xdata BYTE isr_g_ucAwtoLtIdx;
#else
#define AWTO_LT_RING_DEF
#define AWTO_LT_PUT(id, a, b)
#define AWTO_LT_LOG_I(id)
#define AWTO_LT_LOG_M(id)
#define AWTO_LT_LOG_V(id, v)
#endif

#ifndef AWTO_DPCD_PROBE
#define AWTO_DPCD_PROBE 0
#endif
#if(AWTO_DPCD_PROBE != 0)
// main-loop DPCD port probe (test), g_pucAwtoProbe[0..8]: after a read at 0x100 (C2 1 -> 0) the read of 0x000 (expect 12) with gap 0 / 0.25 / 1 / 5 us; after a read at 0x200 (C2 2 -> 0, C3 0 -> 1) the read of 0x001 (expect 14) with the same gaps; [8] = run count
extern __xdata BYTE g_pucAwtoProbe[9];
#define AWTO_PROBE_DEF __xdata BYTE g_pucAwtoProbe[9];
#define AWTO_PROBE_ONE(slot, preC2, postL, gapstmt)  {ScalerSetByte(PBA_C2_DPCD_ADDR_PORT_M, (preC2)); ScalerSetByte(PBA_C3_DPCD_ADDR_PORT_L, 0x00); g_pucAwtoProbe[8] ^= ScalerGetByte(PBA_C4_DPCD_DATA_PORT);\
                                     ScalerSetByte(PBA_C2_DPCD_ADDR_PORT_M, 0x00); ScalerSetByte(PBA_C3_DPCD_ADDR_PORT_L, (postL)); gapstmt g_pucAwtoProbe[slot] = ScalerGetByte(PBA_C4_DPCD_DATA_PORT);}
#define AWTO_DPCD_PROBE_RUN()       {EX0 = 0; ScalerSetByte(PBA_C1_DPCD_ADDR_PORT_H, 0x00); g_pucAwtoProbe[8] = 0;\
                                     AWTO_PROBE_ONE(0, 0x01, 0x00,) AWTO_PROBE_ONE(1, 0x01, 0x00, AWTO_GAP_RUN(AWTO_GAP_025US)) AWTO_PROBE_ONE(2, 0x01, 0x00, AWTO_GAP_RUN(AWTO_GAP_1US)) AWTO_PROBE_ONE(3, 0x01, 0x00, DELAY_5US();)\
                                     AWTO_PROBE_ONE(4, 0x02, 0x01,) AWTO_PROBE_ONE(5, 0x02, 0x01, AWTO_GAP_RUN(AWTO_GAP_025US)) AWTO_PROBE_ONE(6, 0x02, 0x01, AWTO_GAP_RUN(AWTO_GAP_1US)) AWTO_PROBE_ONE(7, 0x02, 0x01, DELAY_5US();)\
                                     EX0 = 1;}
#else
#define AWTO_PROBE_DEF
#define AWTO_DPCD_PROBE_RUN()
#endif
