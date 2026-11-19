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
#define GET_DP_RX1_LINK_TRAINING_STATUS()               (isr_g_ucDpRx1LTStatus)
#define SET_DP_RX1_LINK_TRAINING_STATUS(x)              (isr_g_ucDpRx1LTStatus = (x))

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
extern BYTE isr_g_ucDpRx1LTStatus;
extern __xdata _Bool g_bDpRx0NormalLTSetPhyFinish;
extern bit d_isr_g_bDpRx1NormalLTSetPhyFinish;

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
#define AWTO_LT_PUT(id, a, b)       {isr_g_pucAwtoLtRing[isr_g_ucAwtoLtIdx] = (id); isr_g_pucAwtoLtRing[isr_g_ucAwtoLtIdx + 1] = isr_g_ucDpRx1LTStatus; isr_g_pucAwtoLtRing[isr_g_ucAwtoLtIdx + 2] = (a); isr_g_pucAwtoLtRing[isr_g_ucAwtoLtIdx + 3] = (b); isr_g_ucAwtoLtIdx = (isr_g_ucAwtoLtIdx + 4) & 0x7F;}
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
// main-loop DPCD port probe (test): g_pucAwtoProbe[0..8] = 0x000 / 0x001 normal getter, 0x000 after DELAY_5US + repeat read, C3 read-back + 0x001 after C3 = 1, PBA_C0, C2 read-back, run count
extern __xdata BYTE g_pucAwtoProbe[9];
#define AWTO_PROBE_DEF __xdata BYTE g_pucAwtoProbe[9];
#define AWTO_DPCD_PROBE_RUN()       {EX0 = 0;\
                                     g_pucAwtoProbe[0] = ScalerDpRx1GetDpcdInfo(0x00, 0x00, 0x00); g_pucAwtoProbe[1] = ScalerDpRx1GetDpcdInfo(0x00, 0x00, 0x01);\
                                     ScalerSetByte(PBA_C1_DPCD_ADDR_PORT_H, 0x00); ScalerSetByte(PBA_C2_DPCD_ADDR_PORT_M, 0x00); ScalerSetByte(PBA_C3_DPCD_ADDR_PORT_L, 0x00);\
                                     DELAY_5US(); g_pucAwtoProbe[2] = ScalerGetByte(PBA_C4_DPCD_DATA_PORT); g_pucAwtoProbe[3] = ScalerGetByte(PBA_C4_DPCD_DATA_PORT);\
                                     ScalerSetByte(PBA_C3_DPCD_ADDR_PORT_L, 0x01); g_pucAwtoProbe[4] = ScalerGetByte(PBA_C3_DPCD_ADDR_PORT_L); g_pucAwtoProbe[5] = ScalerGetByte(PBA_C4_DPCD_DATA_PORT);\
                                     g_pucAwtoProbe[6] = ScalerGetByte(PBA_C0_DPCD_CTRL); g_pucAwtoProbe[7] = ScalerGetByte(PBA_C2_DPCD_ADDR_PORT_M); g_pucAwtoProbe[8]++; EX0 = 1;}
#else
#define AWTO_PROBE_DEF
#define AWTO_DPCD_PROBE_RUN()
#endif
