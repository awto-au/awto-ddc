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
// ID Code      : RL6449_Series_McuCommonInclude.h No.0000
// Update Note  :
//----------------------------------------------------------------------------------------------------


//****************************************************************************
// LAYER DEFINITIONS / MACROS
//****************************************************************************
#define GET_REG_XTAL_CLK_SEL()                      ((ScalerGetBit(P0_09_GA_POWER_CTRL, _BIT3) == 0x00) ? _EXT_XTAL_CLK : _IOSC_CLK)


//****************************************************************************
// STRUCT / TYPE / ENUM DEFINITTIONS
//****************************************************************************


//****************************************************************************
// VARIABLE EXTERN
//****************************************************************************
//--------------------------------------------------
// Cache Controller (Page FD)
//--------------------------------------------------
__at(0xFDA0) extern volatile BYTE xdata MCU_FDA0_CACHE_FUNCTION;
__at(0xFDA1) extern volatile BYTE xdata MCU_FDA1_CACHE_OPTION;
__at(0xFDA2) extern volatile BYTE xdata MCU_FDA2_CACHE_START_ADDRESS_H;
__at(0xFDA3) extern volatile BYTE xdata MCU_FDA3_CACHE_START_ADDRESS_M;
__at(0xFDA4) extern volatile BYTE xdata MCU_FDA4_CACHE_START_ADDRESS_L;
__at(0xFDA5) extern volatile BYTE xdata MCU_FDA5_CACHE_END_ADDRESS_H;
__at(0xFDA6) extern volatile BYTE xdata MCU_FDA6_CACHE_END_ADDRESS_M;
__at(0xFDA7) extern volatile BYTE xdata MCU_FDA7_CACHE_END_ADDRESS_L;
__at(0xFDA8) extern volatile BYTE xdata MCU_FDA8_CACHE_START_ADDRESS_H2;
__at(0xFDA9) extern volatile BYTE xdata MCU_FDA9_CACHE_START_ADDRESS_M2;
__at(0xFDAA) extern volatile BYTE xdata MCU_FDAA_CACHE_START_ADDRESS_L2;
__at(0xFDAB) extern volatile BYTE xdata MCU_FDAB_CACHE_END_ADDRESS_H2;
__at(0xFDAC) extern volatile BYTE xdata MCU_FDAC_CACHE_END_ADDRESS_M2;
__at(0xFDAD) extern volatile BYTE xdata MCU_FDAD_CACHE_END_ADDRESS_L2;
__at(0xFDAE) extern volatile BYTE xdata MCU_FDAE_COMMON_START_ADDRESS_H;
__at(0xFDAF) extern volatile BYTE xdata MCU_FDAF_COMMON_START_ADDRESS_L;
__at(0xFDB0) extern volatile BYTE xdata MCU_FDB0_COMMON_END_ADDRESS_H;
__at(0xFDB1) extern volatile BYTE xdata MCU_FDB1_COMMON_END_ADDRESS_L;
__at(0xFDB2) extern volatile BYTE xdata MCU_FDB2_CACHE_ADDRESS_WILD_CARD;
__at(0xFDB3) extern volatile BYTE xdata MCU_FDB3_PERFORMANCE_METER_CONTROL;
__at(0xFDB4) extern volatile BYTE xdata MCU_FDB4_PERFORMANCE_METER_INTERRUPT;
__at(0xFDB5) extern volatile BYTE xdata MCU_FDB5_PERFORMANCE_METER_STATUS;
__at(0xFDB6) extern volatile BYTE xdata MCU_FDB6_PERFORMANCE_METER_LAST_ADDRESS_H;
__at(0xFDB7) extern volatile BYTE xdata MCU_FDB7_PERFORMANCE_METER_LAST_ADDRESS_M;
__at(0xFDB8) extern volatile BYTE xdata MCU_FDB8_PERFORMANCE_METER_LAST_ADDRESS_L;
__at(0xFDB9) extern volatile BYTE xdata MCU_FDB9_PERFORMANCE_METER_REF_COUNT_H;
__at(0xFDBA) extern volatile BYTE xdata MCU_FDBA_PERFORMANCE_METER_REF_COUNT_M1;
__at(0xFDBB) extern volatile BYTE xdata MCU_FDBB_PERFORMANCE_METER_REF_COUNT_M0;
__at(0xFDBC) extern volatile BYTE xdata MCU_FDBC_PERFORMANCE_METER_REF_COUNT_L;
__at(0xFDBD) extern volatile BYTE xdata MCU_FDBD_PERFORMANCE_METER_MISS_COUNT_H;
__at(0xFDBE) extern volatile BYTE xdata MCU_FDBE_PERFORMANCE_METER_MISS_COUNT_M1;
__at(0xFDBF) extern volatile BYTE xdata MCU_FDBF_PERFORMANCE_METER_MISS_COUNT_M0;
__at(0xFDC0) extern volatile BYTE xdata MCU_FDC0_PERFORMANCE_METER_MISS_COUNT_L;
__at(0xFDC1) extern volatile BYTE xdata MCU_FDC1_PERFORMANCE_METER_MEM_RESTART_H;
__at(0xFDC2) extern volatile BYTE xdata MCU_FDC2_PERFORMANCE_METER_MEM_RESTART_M1;
__at(0xFDC3) extern volatile BYTE xdata MCU_FDC3_PERFORMANCE_METER_MEM_RESTART_M0;
__at(0xFDC4) extern volatile BYTE xdata MCU_FDC4_PERFORMANCE_METER_MEM_RESTART_L;
__at(0xFDC5) extern volatile BYTE xdata MCU_FDC5_PERFORMANCE_METER_CRC_H;
__at(0xFDC6) extern volatile BYTE xdata MCU_FDC6_PERFORMANCE_METER_CRC_L;
__at(0xFDC7) extern volatile BYTE xdata MCU_FDC7_CACHE_CONTENT_ADDRESS_H;
__at(0xFDC8) extern volatile BYTE xdata MCU_FDC8_CACHE_CONTENT_ADDRESS_L;
__at(0xFDC9) extern volatile BYTE xdata MCU_FDC9_CACHE_CONTENT_DATA;
__at(0xFDCA) extern volatile BYTE xdata MCU_FDCA_CACHE_SRAM_BIST_CTRL;
__at(0xFDCB) extern volatile BYTE xdata MCU_FDCB_CACHE_SRAM_DRF_BIST_CTRL;
__at(0xFDCC) extern volatile BYTE xdata MCU_FDCC_CACHE_LOAD_CTRL;


//--------------------------------------------------
// EMCU GPIO Control (Page FE)
//--------------------------------------------------
__at(0xFE00) extern volatile BYTE xdata MCU_FE00_PORT40_PIN_REG;
__at(0xFE01) extern volatile BYTE xdata MCU_FE01_PORT41_PIN_REG;
__at(0xFE02) extern volatile BYTE xdata MCU_FE02_PORT42_PIN_REG;
__at(0xFE03) extern volatile BYTE xdata MCU_FE03_PORT43_PIN_REG;
__at(0xFE04) extern volatile BYTE xdata MCU_FE04_PORT44_PIN_REG;
__at(0xFE05) extern volatile BYTE xdata MCU_FE05_PORT45_PIN_REG;
__at(0xFE06) extern volatile BYTE xdata MCU_FE06_PORT46_PIN_REG;
__at(0xFE07) extern volatile BYTE xdata MCU_FE07_PORT47_PIN_REG;
__at(0xFE08) extern volatile BYTE xdata MCU_FE08_PORT50_PIN_REG;
__at(0xFE09) extern volatile BYTE xdata MCU_FE09_PORT51_PIN_REG;
__at(0xFE0A) extern volatile BYTE xdata MCU_FE0A_PORT52_PIN_REG;
__at(0xFE0B) extern volatile BYTE xdata MCU_FE0B_PORT53_PIN_REG;
__at(0xFE0C) extern volatile BYTE xdata MCU_FE0C_PORT54_PIN_REG;
__at(0xFE0D) extern volatile BYTE xdata MCU_FE0D_PORT55_PIN_REG;
__at(0xFE0E) extern volatile BYTE xdata MCU_FE0E_PORT56_PIN_REG;
__at(0xFE0F) extern volatile BYTE xdata MCU_FE0F_PORT57_PIN_REG;
__at(0xFE10) extern volatile BYTE xdata MCU_FE10_PORT60_PIN_REG;
__at(0xFE11) extern volatile BYTE xdata MCU_FE11_PORT61_PIN_REG;
__at(0xFE12) extern volatile BYTE xdata MCU_FE12_PORT62_PIN_REG;
__at(0xFE13) extern volatile BYTE xdata MCU_FE13_PORT63_PIN_REG;
__at(0xFE14) extern volatile BYTE xdata MCU_FE14_PORT64_PIN_REG;
__at(0xFE15) extern volatile BYTE xdata MCU_FE15_PORT65_PIN_REG;
__at(0xFE16) extern volatile BYTE xdata MCU_FE16_PORT66_PIN_REG;
__at(0xFE17) extern volatile BYTE xdata MCU_FE17_PORT67_PIN_REG;
__at(0xFE18) extern volatile BYTE xdata MCU_FE18_PORT70_PIN_REG;
__at(0xFE19) extern volatile BYTE xdata MCU_FE19_PORT71_PIN_REG;
__at(0xFE1A) extern volatile BYTE xdata MCU_FE1A_PORT72_PIN_REG;
__at(0xFE1B) extern volatile BYTE xdata MCU_FE1B_PORT73_PIN_REG;
__at(0xFE1C) extern volatile BYTE xdata MCU_FE1C_PORT74_PIN_REG;
__at(0xFE1D) extern volatile BYTE xdata MCU_FE1D_PORT75_PIN_REG;
__at(0xFE1E) extern volatile BYTE xdata MCU_FE1E_PORT76_PIN_REG;
__at(0xFE1F) extern volatile BYTE xdata MCU_FE1F_PORT77_PIN_REG;
__at(0xFE20) extern volatile BYTE xdata MCU_FE20_PORT80_PIN_REG;
__at(0xFE21) extern volatile BYTE xdata MCU_FE21_PORT81_PIN_REG;
__at(0xFE22) extern volatile BYTE xdata MCU_FE22_PORT82_PIN_REG;
__at(0xFE23) extern volatile BYTE xdata MCU_FE23_PORT83_PIN_REG;
__at(0xFE24) extern volatile BYTE xdata MCU_FE24_PORT84_PIN_REG;
__at(0xFE25) extern volatile BYTE xdata MCU_FE25_PORT85_PIN_REG;
__at(0xFE26) extern volatile BYTE xdata MCU_FE26_PORT86_PIN_REG;
__at(0xFE27) extern volatile BYTE xdata MCU_FE27_PORT87_PIN_REG;
__at(0xFE28) extern volatile BYTE xdata MCU_FE28_PORT90_PIN_REG;
__at(0xFE29) extern volatile BYTE xdata MCU_FE29_PORT91_PIN_REG;
__at(0xFE2A) extern volatile BYTE xdata MCU_FE2A_PORT92_PIN_REG;
__at(0xFE2B) extern volatile BYTE xdata MCU_FE2B_PORT93_PIN_REG;
__at(0xFE2C) extern volatile BYTE xdata MCU_FE2C_PORT94_PIN_REG;
__at(0xFE2D) extern volatile BYTE xdata MCU_FE2D_PORT95_PIN_REG;
__at(0xFE2E) extern volatile BYTE xdata MCU_FE2E_PORT96_PIN_REG;
__at(0xFE2F) extern volatile BYTE xdata MCU_FE2F_PORT97_PIN_REG;
__at(0xFE30) extern volatile BYTE xdata MCU_FE30_PORTA0_PIN_REG;
__at(0xFE31) extern volatile BYTE xdata MCU_FE31_PORTA1_PIN_REG;
__at(0xFE32) extern volatile BYTE xdata MCU_FE32_PORTA2_PIN_REG;
__at(0xFE33) extern volatile BYTE xdata MCU_FE33_PORTA3_PIN_REG;
__at(0xFE34) extern volatile BYTE xdata MCU_FE34_PORTA4_PIN_REG;
__at(0xFE35) extern volatile BYTE xdata MCU_FE35_PORTA5_PIN_REG;
__at(0xFE36) extern volatile BYTE xdata MCU_FE36_PORTA6_PIN_REG;
__at(0xFE37) extern volatile BYTE xdata MCU_FE37_PORTA7_PIN_REG;
__at(0xFE38) extern volatile BYTE xdata MCU_FE38_PORTB0_PIN_REG;
__at(0xFE39) extern volatile BYTE xdata MCU_FE39_PORTB1_PIN_REG;
__at(0xFE3A) extern volatile BYTE xdata MCU_FE3A_PORTB2_PIN_REG;
__at(0xFE3B) extern volatile BYTE xdata MCU_FE3B_PORTB3_PIN_REG;
__at(0xFE3C) extern volatile BYTE xdata MCU_FE3C_PORTB4_PIN_REG;
__at(0xFE3D) extern volatile BYTE xdata MCU_FE3D_DUMMY1;
__at(0xFE3E) extern volatile BYTE xdata MCU_FE3E_DUMMY2;
__at(0xFE3F) extern volatile BYTE xdata MCU_FE3F_DUMMY3;
__at(0xFE60) extern volatile BYTE xdata MCU_FE60_PORT_READ_CONTROL;
__at(0xFE61) extern volatile BYTE xdata MCU_FE61_PORT_READ_CONTROL_2;


//--------------------------------------------------
// EMCU DDC Part 0 (Page FE)
//--------------------------------------------------
__at(0xFE62) extern volatile BYTE xdata MCU_FE62_DDC2_SEGMENT_ADDRESS;
__at(0xFE63) extern volatile BYTE xdata MCU_FE63_DDC2_SEGMENT_DATA;
__at(0xFE64) extern volatile BYTE xdata MCU_FE64_DDC2_DDC_ENABLE;
__at(0xFE65) extern volatile BYTE xdata MCU_FE65_DDC2_DDC_CONTROL_1;
__at(0xFE66) extern volatile BYTE xdata MCU_FE66_DDC2_DDC_CONTROL_2;
__at(0xFE67) extern volatile BYTE xdata MCU_FE67_DDC2_DDC_INDEX;
__at(0xFE68) extern volatile BYTE xdata MCU_FE68_DDC2_DDC_ACCESS_PORT;
__at(0xFE69) extern volatile BYTE xdata MCU_FE69_DDC2_EDID_IRQ;
__at(0xFE6A) extern volatile BYTE xdata MCU_FE6A_DDC2_RESERVED;
__at(0xFE6B) extern volatile BYTE xdata MCU_FE6B_DDC3_SEGMENT_ADDRESS;
__at(0xFE6C) extern volatile BYTE xdata MCU_FE6C_DDC3_SEGMENT_DATA;
__at(0xFE6D) extern volatile BYTE xdata MCU_FE6D_DDC3_DDC_ENABLE;
__at(0xFE6E) extern volatile BYTE xdata MCU_FE6E_DDC3_DDC_CONTROL_1;
__at(0xFE6F) extern volatile BYTE xdata MCU_FE6F_DDC3_DDC_CONTROL_2;
__at(0xFE70) extern volatile BYTE xdata MCU_FE70_DDC3_DDC_INDEX;
__at(0xFE71) extern volatile BYTE xdata MCU_FE71_DDC3_DDC_ACCESS_PORT;
__at(0xFE72) extern volatile BYTE xdata MCU_FE72_DDC3_EDID_IRQ;
__at(0xFE73) extern volatile BYTE xdata MCU_FE73_DDC3_RESERVED;


//--------------------------------------------------
// EMCU DDC-CI Part 0 (Page FE)
//--------------------------------------------------
__at(0xFE86) extern volatile BYTE xdata MCU_FE86_IIC_1_CH_SEL;
__at(0xFE87) extern volatile BYTE xdata MCU_FE87_IIC_1_SET_SLAVE;
__at(0xFE88) extern volatile BYTE xdata MCU_FE88_IIC_1_SUB_IN;
__at(0xFE89) extern volatile BYTE xdata MCU_FE89_IIC_1_DATA_IN;
__at(0xFE8A) extern volatile BYTE xdata MCU_FE8A_IIC_1_DATA_OUT;
__at(0xFE8B) extern volatile BYTE xdata MCU_FE8B_IIC_1_STATUS;
__at(0xFE8C) extern volatile BYTE xdata MCU_FE8C_IIC_1_IRQ_CONTROL;
__at(0xFE8D) extern volatile BYTE xdata MCU_FE8D_IIC_1_STATUS2;
__at(0xFE8E) extern volatile BYTE xdata MCU_FE8E_IIC_1_IRQ_CONTROL2;
__at(0xFE8F) extern volatile BYTE xdata MCU_FE8F_IIC_1_CHANNEL_CONTROL;
__at(0xFE90) extern volatile BYTE xdata MCU_FE90_DDCCI_1_NULL_BYTE1;
__at(0xFE91) extern volatile BYTE xdata MCU_FE91_DDCCI_1_NULL_BYTE2;
__at(0xFE92) extern volatile BYTE xdata MCU_FE92_DDCCI_1_NULL_BYTE3;
__at(0xFE93) extern volatile BYTE xdata MCU_FE93_DDCCI_1_REMAIN_DATA;


//--------------------------------------------------
// EMCU DDCRAM Settings (Page FE)
//--------------------------------------------------
__at(0xFEB1) extern volatile BYTE xdata MCU_FEB1_DDCRAM_ST_ADDRESS;
__at(0xFEB2) extern volatile BYTE xdata MCU_FEB2_XRAM_BIST_CTRL;
__at(0xFEB3) extern volatile BYTE xdata MCU_FEB3_XRAM_DRF_BIST_CTRL;
__at(0xFEB4) extern volatile BYTE xdata MCU_FEB4_MCU_DUMMY2;


//--------------------------------------------------
// EMCU Interrupt Control Part 1 (Page FF)
//--------------------------------------------------
__at(0xFF00) extern volatile BYTE xdata MCU_FF00_IRQ_STATUS;


//--------------------------------------------------
// EMCU OSD Reorder Part 1 (Page FF)
//--------------------------------------------------
__at(0xFF03) extern volatile BYTE xdata MCU_FF03_TRIPLE_BYTES_OPERATION;
__at(0xFF04) extern volatile BYTE xdata MCU_FF04_SHIFT_BITS_NUMBER;
__at(0xFF05) extern volatile BYTE xdata MCU_FF05_SHIFT_BYTE_ADDRESS;
__at(0xFF06) extern volatile BYTE xdata MCU_FF06_INPUT_TRIPLE_BYTES;
__at(0xFF07) extern volatile BYTE xdata MCU_FF07_RESULT_TRIPLE_BYTES;


//--------------------------------------------------
// EMCU LSADC (Page FF)
//--------------------------------------------------
__at(0xFF08) extern volatile BYTE xdata MCU_FF08_ADC_ACONTROL;
__at(0xFF09) extern volatile BYTE xdata MCU_FF09_ADC_A0_CONVERT_RESULT;
__at(0xFF0A) extern volatile BYTE xdata MCU_FF0A_ADC_A1_CONVERT_RESULT;
__at(0xFF0B) extern volatile BYTE xdata MCU_FF0B_ADC_A2_CONVERT_RESULT;
__at(0xFF0C) extern volatile BYTE xdata MCU_FF0C_ADC_A3_CONVERT_RESULT;
__at(0xFF0D) extern volatile BYTE xdata MCU_FF0D_ADC_CLK_DIV;
__at(0xFF0E) extern volatile BYTE xdata MCU_FF0E_AUTO_MODE_CTRL01;
__at(0xFF0F) extern volatile BYTE xdata MCU_FF0F_ADC0_THRESHOLD_H;
__at(0xFF10) extern volatile BYTE xdata MCU_FF10_ADC0_THRESHOLD_L;
__at(0xFF11) extern volatile BYTE xdata MCU_FF11_ADC1_THRESHOLD_H;
__at(0xFF12) extern volatile BYTE xdata MCU_FF12_ADC1_THRESHOLD_L;
__at(0xFF13) extern volatile BYTE xdata MCU_FF13_ADC2_THRESHOLD_H;
__at(0xFF14) extern volatile BYTE xdata MCU_FF14_ADC2_THRESHOLD_L;
__at(0xFF15) extern volatile BYTE xdata MCU_FF15_ADC3_THRESHOLD_H;
__at(0xFF16) extern volatile BYTE xdata MCU_FF16_ADC3_THRESHOLD_L;
__at(0xFF17) extern volatile BYTE xdata MCU_FF17_CTRL0_WAIT_TIME_VALUE;


//--------------------------------------------------
// EMCU OSD Reorder Part 2 (Page FF)
//--------------------------------------------------
__at(0xFF18) extern volatile BYTE xdata MCU_FF18_BYTE_ADDRESS;


//--------------------------------------------------
// EMCU DDC Part 1 (Page FF)
//--------------------------------------------------
__at(0xFF19) extern volatile BYTE xdata MCU_FF19_ADC_SEGMENT_ADDRESS;
__at(0xFF1A) extern volatile BYTE xdata MCU_FF1A_ADC_SEGMENT_DATA;
__at(0xFF1B) extern volatile BYTE xdata MCU_FF1B_ADC_DDC_ENABLE;
__at(0xFF1C) extern volatile BYTE xdata MCU_FF1C_ADC_DDC_CONTROL_1;
__at(0xFF1D) extern volatile BYTE xdata MCU_FF1D_ADC_DDC_CONTROL_2;
__at(0xFF1E) extern volatile BYTE xdata MCU_FF1E_DDC0_DDC_ENABLE;
__at(0xFF1F) extern volatile BYTE xdata MCU_FF1F_DDC0_DDC_CONTROL_1;
__at(0xFF20) extern volatile BYTE xdata MCU_FF20_DDC0_DDC_CONTROL_2;


//--------------------------------------------------
// EMCU DDC-CI Part 1 (Page FF)
//--------------------------------------------------
__at(0xFF22) extern volatile BYTE xdata MCU_FF22_IIC_CH_SEL;
__at(0xFF23) extern volatile BYTE xdata MCU_FF23_IIC_SET_SLAVE;
__at(0xFF24) extern volatile BYTE xdata MCU_FF24_IIC_SUB_IN;
__at(0xFF25) extern volatile BYTE xdata MCU_FF25_IIC_DATA_IN;
__at(0xFF26) extern volatile BYTE xdata MCU_FF26_IIC_DATA_OUT;
__at(0xFF27) extern volatile BYTE xdata MCU_FF27_IIC_STATUS;
__at(0xFF28) extern volatile BYTE xdata MCU_FF28_IIC_IRQ_CONTROL;
__at(0xFF29) extern volatile BYTE xdata MCU_FF29_IIC_STATUS2;
__at(0xFF2A) extern volatile BYTE xdata MCU_FF2A_IIC_IRQ_CONTROL2;
__at(0xFF2B) extern volatile BYTE xdata MCU_FF2B_IIC_CHANNEL_CONTROL;


//--------------------------------------------------
// EMCU DDC Part 2 (Page FF)
//--------------------------------------------------
__at(0xFF2C) extern volatile BYTE xdata MCU_FF2C_DDC1_DDC_ENABLE;
__at(0xFF2D) extern volatile BYTE xdata MCU_FF2D_DDC1_DDC_CONTROL_1;
__at(0xFF2E) extern volatile BYTE xdata MCU_FF2E_DDC1_DDC_CONTROL_2;
__at(0xFF2F) extern volatile BYTE xdata MCU_FF2F_ADC_DDC_INDEX;
__at(0xFF30) extern volatile BYTE xdata MCU_FF30_ADC_DDC_ACCESS_PORT;
__at(0xFF31) extern volatile BYTE xdata MCU_FF31_DDC0_DDC_INDEX;
__at(0xFF32) extern volatile BYTE xdata MCU_FF32_DDC0_DDC_ACCESS_PORT;
__at(0xFF33) extern volatile BYTE xdata MCU_FF33_DDC1_DDC_INDEX;
__at(0xFF34) extern volatile BYTE xdata MCU_FF34_DDC1_DDC_ACCESS_PORT;
__at(0xFF35) extern volatile BYTE xdata MCU_FF35_DDCCI_REMAIN_DATA;
__at(0xFF36) extern volatile BYTE xdata MCU_FF36_DDC0_SEGMENT_ADDRESS;
__at(0xFF37) extern volatile BYTE xdata MCU_FF37_DDC0_SEGMENT_DATA;
__at(0xFF38) extern volatile BYTE xdata MCU_FF38_DDC1_SEGMENT_ADDRESS;
__at(0xFF39) extern volatile BYTE xdata MCU_FF39_DDC1_SEGMENT_DATA;


//--------------------------------------------------
// EMCU PWM Part 1 (Page FF)
//--------------------------------------------------
__at(0xFF3A) extern volatile BYTE xdata MCU_FF3A_PWM_CK_SEL;
__at(0xFF3B) extern volatile BYTE xdata MCU_FF3B_PWM03_M;
__at(0xFF3C) extern volatile BYTE xdata MCU_FF3C_PWM45_M;
__at(0xFF3D) extern volatile BYTE xdata MCU_FF3D_PWM01_N_MSB;
__at(0xFF3E) extern volatile BYTE xdata MCU_FF3E_PWM0_N_LSB;
__at(0xFF3F) extern volatile BYTE xdata MCU_FF3F_PWM1_N_LSB;
__at(0xFF40) extern volatile BYTE xdata MCU_FF40_PWM23_N_MSB;
__at(0xFF41) extern volatile BYTE xdata MCU_FF41_PWM2_N_LSB;
__at(0xFF42) extern volatile BYTE xdata MCU_FF42_PWM3_N_LSB;
__at(0xFF43) extern volatile BYTE xdata MCU_FF43_PWM45_N_MSB;
__at(0xFF44) extern volatile BYTE xdata MCU_FF44_PWM4_N_LSB;
__at(0xFF45) extern volatile BYTE xdata MCU_FF45_PWM5_N_LSB;
__at(0xFF46) extern volatile BYTE xdata MCU_FF46_PWML;
__at(0xFF47) extern volatile BYTE xdata MCU_FF47_PWM_VS_CTRL;
__at(0xFF48) extern volatile BYTE xdata MCU_FF48_PWM_EN;
__at(0xFF49) extern volatile BYTE xdata MCU_FF49_PWM_CK;
__at(0xFF4A) extern volatile BYTE xdata MCU_FF4A_PWM0H_DUT;
__at(0xFF4B) extern volatile BYTE xdata MCU_FF4B_PWM1H_DUT;
__at(0xFF4C) extern volatile BYTE xdata MCU_FF4C_PWM01L_DUT;
__at(0xFF4D) extern volatile BYTE xdata MCU_FF4D_PWM2H_DUT;
__at(0xFF4E) extern volatile BYTE xdata MCU_FF4E_PWM3H_DUT;
__at(0xFF4F) extern volatile BYTE xdata MCU_FF4F_PWM23L_DUT;
__at(0xFF50) extern volatile BYTE xdata MCU_FF50_PWM4H_DUT;
__at(0xFF51) extern volatile BYTE xdata MCU_FF51_PWM5H_DUT;
__at(0xFF52) extern volatile BYTE xdata MCU_FF52_PWM45L_DUT;
__at(0xFF53) extern volatile BYTE xdata MCU_FF53_PWM_DUT_TYPE;
__at(0xFF54) extern volatile BYTE xdata MCU_FF54_PWM_CNT_MODE;


//--------------------------------------------------
// EMCU I2C Control Module (Page FF)
//--------------------------------------------------
__at(0xFF55) extern volatile BYTE xdata MCU_FF55_I2CM_CR0;
__at(0xFF56) extern volatile BYTE xdata MCU_FF56_I2CM_CR1;
__at(0xFF57) extern volatile BYTE xdata MCU_FF57_I2CM_CR2;
__at(0xFF58) extern volatile BYTE xdata MCU_FF58_I2CM_CR3;
__at(0xFF59) extern volatile BYTE xdata MCU_FF59_I2CM_STR0;
__at(0xFF5A) extern volatile BYTE xdata MCU_FF5A_I2CM_STR1;
__at(0xFF5B) extern volatile BYTE xdata MCU_FF5B_I2CM_STR2;
__at(0xFF5C) extern volatile BYTE xdata MCU_FF5C_I2CM_STR3;
__at(0xFF5D) extern volatile BYTE xdata MCU_FF5D_I2CM_SR;
__at(0xFF5E) extern volatile BYTE xdata MCU_FF5E_I2CM_TD;
__at(0xFF5F) extern volatile BYTE xdata MCU_FF5F_I2CM_CCR;


//--------------------------------------------------
// EMCU SPI-FLASH Part 1 (Page FF)
//--------------------------------------------------
__at(0xFF60) extern volatile BYTE xdata MCU_FF60_COMMON_INST_EN;
__at(0xFF61) extern volatile BYTE xdata MCU_FF61_COMMON_OP_CODE;
__at(0xFF62) extern volatile BYTE xdata MCU_FF62_WREN_OP_CODE;
__at(0xFF63) extern volatile BYTE xdata MCU_FF63_EWSR_OP_CODE;
__at(0xFF64) extern volatile BYTE xdata MCU_FF64_FLASH_PROG_ISP0;
__at(0xFF65) extern volatile BYTE xdata MCU_FF65_FLASH_PROG_ISP1;
__at(0xFF66) extern volatile BYTE xdata MCU_FF66_FLASH_PROG_ISP2;
__at(0xFF67) extern volatile BYTE xdata MCU_FF67_COMMON_INST_READ_PORT0;
__at(0xFF68) extern volatile BYTE xdata MCU_FF68_COMMON_INST_READ_PORT1;
__at(0xFF69) extern volatile BYTE xdata MCU_FF69_COMMON_INST_READ_PORT2;
__at(0xFF6A) extern volatile BYTE xdata MCU_FF6A_READ_OP_CODE;
__at(0xFF6B) extern volatile BYTE xdata MCU_FF6B_FAST_READ_OP_CODE;
__at(0xFF6C) extern volatile BYTE xdata MCU_FF6C_READ_INSTRUCTION;
__at(0xFF6D) extern volatile BYTE xdata MCU_FF6D_PROGRAM_OP_CODE;
__at(0xFF6E) extern volatile BYTE xdata MCU_FF6E_READ_STATUS_REGISTER_OP_CODE;
__at(0xFF6F) extern volatile BYTE xdata MCU_FF6F_PROGRAM_INSTRUCTION;
__at(0xFF70) extern volatile BYTE xdata MCU_FF70_PROGRAM_DATA_PORT;
__at(0xFF71) extern volatile BYTE xdata MCU_FF71_PROGRAM_LENGTH;
__at(0xFF72) extern volatile BYTE xdata MCU_FF72_CRC_END_ADDR0;
__at(0xFF73) extern volatile BYTE xdata MCU_FF73_CRC_END_ADDR1;
__at(0xFF74) extern volatile BYTE xdata MCU_FF74_CRC_END_ADDR2;
__at(0xFF75) extern volatile BYTE xdata MCU_FF75_CRC_RESULT;
__at(0xFF76) extern volatile BYTE xdata MCU_FF76_CEN_CTRL;
__at(0xFF77) extern volatile BYTE xdata MCU_FF77_REV_DUMMY4;
__at(0xFF78) extern volatile BYTE xdata MCU_FF78_ACCESS_FLASH_ADDR_0;
__at(0xFF79) extern volatile BYTE xdata MCU_FF79_ACCESS_FLASH_ADDR_1;
__at(0xFF7A) extern volatile BYTE xdata MCU_FF7A_ACCESS_FLASH_ADDR_2;
__at(0xFF7B) extern volatile BYTE xdata MCU_FF7B_ACCESS_FLASH_DATA_PORT;
__at(0xFF7C) extern volatile BYTE xdata MCU_FF7C_ACCESS_FLASH_DATA_CTRL;
__at(0xFF80) extern volatile BYTE xdata MCU_FF80_AAI_MODE_BYTE_NUM;
__at(0xFF81) extern volatile BYTE xdata MCU_FF81_ISP_CMD_INSERT;
__at(0xFF82) extern volatile BYTE xdata MCU_FF82_ISP_CMD_LENGTH;


//--------------------------------------------------
// EMCU I2C Slave Module (Page FF)
//--------------------------------------------------
__at(0xFF83) extern volatile BYTE xdata MCU_FF83_I2CS_CTRL0;
__at(0xFF84) extern volatile BYTE xdata MCU_FF84_I2CS_CTRL1;
__at(0xFF85) extern volatile BYTE xdata MCU_FF85_I2CS_CTRL2;
__at(0xFF86) extern volatile BYTE xdata MCU_FF86_I2CS_STATUS0;
__at(0xFF87) extern volatile BYTE xdata MCU_FF87_I2CS_STATUS1;
__at(0xFF88) extern volatile BYTE xdata MCU_FF88_I2CS_BUFLEN;


//--------------------------------------------------
// EMCU PWM Part 2 (Page FF)
//--------------------------------------------------
__at(0xFF90) extern volatile BYTE xdata MCU_FF90_PWM01_TOTALCNT_MSB;
__at(0xFF91) extern volatile BYTE xdata MCU_FF91_PWM0_TOTALCNT_LSB;
__at(0xFF92) extern volatile BYTE xdata MCU_FF92_PWM1_TOTALCNT_LSB;
__at(0xFF93) extern volatile BYTE xdata MCU_FF93_PWM23_TOTALCNT_MSB;
__at(0xFF94) extern volatile BYTE xdata MCU_FF94_PWM2_TOTALCNT_LSB;
__at(0xFF95) extern volatile BYTE xdata MCU_FF95_PWM3_TOTALCNT_LSB;
__at(0xFF96) extern volatile BYTE xdata MCU_FF96_PWM45_TOTALCNT_MSB;
__at(0xFF97) extern volatile BYTE xdata MCU_FF97_PWM4_TOTALCNT_LSB;
__at(0xFF98) extern volatile BYTE xdata MCU_FF98_PWM5_TOTALCNT_LSB;
__at(0xFF99) extern volatile BYTE xdata MCU_FF99_PWM_CK_SEL_HS;
__at(0xFF9A) extern volatile BYTE xdata MCU_FF9A_PWM01_CYCLE_MAX;
__at(0xFF9B) extern volatile BYTE xdata MCU_FF9B_PWM23_CYCLE_MAX;
__at(0xFF9C) extern volatile BYTE xdata MCU_FF9C_PWM45_CYCLE_MAX;


//--------------------------------------------------
// EMCU Watchdog Counter Part 1 (Page FF)
//--------------------------------------------------
__at(0xFFAA) extern volatile BYTE xdata MCU_FFAA_WATCHDOG_CNT2_VALUE;
__at(0xFFAB) extern volatile BYTE xdata MCU_FFAB_WATCHDOG_CNT23_VALUE;
__at(0xFFAC) extern volatile BYTE xdata MCU_FFAC_WATCHDOG_CNT3_VALUE;
__at(0xFFAD) extern volatile BYTE xdata MCU_FFAD_WATCHDOG_CNT1_VALUE;
__at(0xFFAE) extern volatile BYTE xdata MCU_FFAE_WATCHDOG_TIMER_THRESHOLD;
__at(0xFFAF) extern volatile BYTE xdata MCU_FFAF_WATCHDOG_TIMER_THRESHOLD_MASK;
__at(0xFFB0) extern volatile BYTE xdata MCU_FFB0_WATCHDOG_TIMER_H_THRESHOLD_MASK;


//--------------------------------------------------
// EMCU DDCCI Part 2 (Page FF)
//--------------------------------------------------
__at(0xFFB1) extern volatile BYTE xdata MCU_FFB1_DDCCI_NULL_BYTE1;
__at(0xFFB2) extern volatile BYTE xdata MCU_FFB2_DDCCI_NULL_BYTE2;
__at(0xFFB3) extern volatile BYTE xdata MCU_FFB3_DDCCI_NULL_BYTE3;


//--------------------------------------------------
// EMCU Interrupt Control Part 0 (Page FF)
//--------------------------------------------------
__at(0xFFB8) extern volatile BYTE xdata MCU_FFB8_EXT_INT0_CONTROL;
__at(0xFFB9) extern volatile BYTE xdata MCU_FFB9_EXT_INT1_CONTROL;


//--------------------------------------------------
// EMCU Test Mode (Page FF)
//--------------------------------------------------
__at(0xFFBB) extern volatile BYTE xdata MCU_FFBB_PERI_TEST;
__at(0xFFBC) extern volatile BYTE xdata MCU_FFBC_CYCLE_GATING;
__at(0xFFBD) extern volatile BYTE xdata MCU_FFBD_MCU_CLK_DIV_R;
__at(0xFFBE) extern volatile BYTE xdata MCU_FFBE_MCU_DUMMY;


//--------------------------------------------------
// EMCU Interrupt Control Part 2 (Page FF)
//--------------------------------------------------
__at(0xFFC2) extern volatile BYTE xdata MCU_FFC2_IRQ_PRIORITY_1;
__at(0xFFC3) extern volatile BYTE xdata MCU_FFC3_IRQ_PRIORITY_2;
__at(0xFFC4) extern volatile BYTE xdata MCU_FFC4_IRQ_PRIORITY_3;


//--------------------------------------------------
// EMCU DDCRAM Control (Page FF)
//--------------------------------------------------
__at(0xFFD0) extern volatile BYTE xdata MCU_FFD0_A_DDCRAM_CONTROL;
__at(0xFFD1) extern volatile BYTE xdata MCU_FFD1_DDCRAM0_CONTROL;
__at(0xFFD2) extern volatile BYTE xdata MCU_FFD2_DDCRAM1_CONTROL;
__at(0xFFD3) extern volatile BYTE xdata MCU_FFD3_DDCRAM2_CONTROL;
__at(0xFFD4) extern volatile BYTE xdata MCU_FFD4_DDCRAM3_CONTROL;


//--------------------------------------------------
// EMCU In System Programming Part 1 (Page FF)
//--------------------------------------------------
__at(0xFFE0) extern volatile BYTE xdata MCU_FFE0_ISP_FLAG;
__at(0xFFE8) extern volatile BYTE xdata MCU_FFE8_ISP_CONTROL;
__at(0xFFE9) extern volatile BYTE xdata MCU_FFE9_MCU_CLK_CONTROL_1;


//--------------------------------------------------
// EMCU SFR Access (Page FF)
//--------------------------------------------------
__at(0xFFE2) extern volatile BYTE xdata MCU_FFE2_PORT1_PIN_REG;
__at(0xFFE3) extern volatile BYTE xdata MCU_FFE3_PORT3_PIN_REG;


//--------------------------------------------------
// EMCU DDC Part 3 (Page FF)
//--------------------------------------------------
__at(0xFFE4) extern volatile BYTE xdata MCU_FFE4_DDC0_EDID_IRQ;
__at(0xFFE5) extern volatile BYTE xdata MCU_FFE5_DDC1_EDID_IRQ;
__at(0xFFE7) extern volatile BYTE xdata MCU_FFE7_VGA_EDID_IRQ;


//--------------------------------------------------
// EMCU Watchdog Timer Part 2 (Page FF)
//--------------------------------------------------
__at(0xFFEA) extern volatile BYTE xdata MCU_FFEA_WATCHDOG_TIMER;
__at(0xFFEB) extern volatile BYTE xdata MCU_FFEB_WDT_TEST;


//--------------------------------------------------
// EMCU In System Programming Part 2 (Page FF)
//--------------------------------------------------
__at(0xFFEC) extern volatile BYTE xdata MCU_FFEC_ISP_SLAVE_ADDRESS;
__at(0xFFED) extern volatile BYTE xdata MCU_FFED_MCU_CONTROL;
__at(0xFFEE) extern volatile BYTE xdata MCU_FFEE_MCU_CLOCK_CONTROL;
__at(0xFFEF) extern volatile BYTE xdata MCU_FFEF_RAM_TEST;


//--------------------------------------------------
// EMCU Xdata-SPI-FLASH Write Protect (Page FF)
//--------------------------------------------------
__at(0xFFF0) extern volatile BYTE xdata MCU_FFF0_XDATA_SPI_FLASH_WRITE_PROTECT;
__at(0xFFF1) extern volatile BYTE xdata MCU_FFF1_SCA_WR_INTRVL;
__at(0xFFF2) extern volatile BYTE xdata MCU_FFF2_PWM_I2C_CLOCK_STOP;


//--------------------------------------------------
// EMCU Scalar Interface (Page FF)
//--------------------------------------------------
__at(0xFFF3) extern volatile BYTE xdata MCU_FFF3_SCA_INF_CONTROL;
__at(0xFFF4) extern volatile BYTE xdata MCU_FFF4_SCA_INF_ADDR;
__at(0xFFF5) extern volatile BYTE xdata MCU_FFF5_SCA_INF_DATA;
__at(0xFFF6) extern volatile BYTE xdata MCU_FFF6_SCA_INF_BWR_ADRH;
__at(0xFFF7) extern volatile BYTE xdata MCU_FFF7_SCA_INF_BWR_ADRM;
__at(0xFFF8) extern volatile BYTE xdata MCU_FFF8_SCA_INF_BWR_ADRL;
__at(0xFFF9) extern volatile BYTE xdata MCU_FFF9_SCA_INF_BWR_COUNT_H;
__at(0xFFFA) extern volatile BYTE xdata MCU_FFFA_SCA_INF_BWR_COUNT_L;
__at(0xFFFB) extern volatile BYTE xdata MCU_FFFB_SCA_INF_PERIOD;


//--------------------------------------------------
// EMCU Bankswitch (Page FF)
//--------------------------------------------------
__at(0xFFFC) extern volatile BYTE xdata MCU_FFFC_BANK_SWICH_CONTROL;
__at(0xFFFD) extern volatile BYTE xdata MCU_FFFD_XDATA_BANK_START;
__at(0xFFFE) extern volatile BYTE xdata MCU_FFFE_XDATA_BANK_SEL;
__at(0xFFFF) extern volatile BYTE xdata MCU_FFFF_PBANK_SWITCH;

//****************************************************************************
// FUNCTION EXTERN
//****************************************************************************
