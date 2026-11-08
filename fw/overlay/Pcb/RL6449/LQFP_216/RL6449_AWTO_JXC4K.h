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
// ID Code      : RL6449_AWTO_JXC4K.h (awto: JXC/Dahua 4K board, from RL6449_QA_B_1A2MHL1DP1mDP_DPTX_eDP.h)
// Update Note  : ports + pinshare from live old-fw registers (docs/monitors/pinshare-live-AWT26110003.tsv, #7)
//----------------------------------------------------------------------------------------------------
#if(_PCB_TYPE == _RL6449_AWTO_JXC4K)


///////////////////
// External Xtal //
///////////////////

//--------------------------------------------------
// External Xtal Define
//--------------------------------------------------
#define _EXT_XTAL                               _XTAL14318K


///////////////////////
// Input Port Config //
///////////////////////

//--------------------------------------------------
// A0 Input Port
//--------------------------------------------------
#define _A0_INPUT_PORT_TYPE                     _A0_NO_PORT  // awto: no VGA
#define _A0_EMBEDDED_DDCRAM_MAX_SIZE            _EDID_SIZE_NONE
#define _A0_EMBEDDED_DDCRAM_LOCATION            _EDID_TABLE_LOCATION_CODE

// Boot / debug-mode DDC-CI channel: old fw ScalerMcuDdcciInitial sets IIC_CH_SEL = 3 (DDC2); default _VGA_DDC is unwired (#8)
#define _PCB_DEBUG_DDC                          _DDC2

//--------------------------------------------------
// D0 Input Port
//--------------------------------------------------
#define _D0_INPUT_PORT_TYPE                     _D0_NO_PORT  // awto: AUX0 pins are GPIO in old fw
#define _D0_DDC_CHANNEL_SEL                     _DDC0
#define _D0_EMBEDDED_DDCRAM_MAX_SIZE            _EDID_SIZE_256
#define _D0_EMBEDDED_DDCRAM_LOCATION            _EDID_TABLE_LOCATION_USER
#define _D0_DP_CONNECTOR_TYPE                   _DP_CONNECTOR_MINI
#define _D0_DP_LINK_CLK_RATE                    _DP_HIGH_SPEED2_540MHZ
#define _D0_DP_MAIN_LINK_LANES                  _DP_FOUR_LANE

//--------------------------------------------------
// D1 Input Port
//--------------------------------------------------
#define _D1_INPUT_PORT_TYPE                     _D1_DP_PORT
#define _D1_DDC_CHANNEL_SEL                     _DDC1
#define _D1_EMBEDDED_DDCRAM_MAX_SIZE            _EDID_SIZE_256
#define _D1_EMBEDDED_DDCRAM_LOCATION            _EDID_TABLE_LOCATION_CODE  // awto: old fw serves all 3 EDIDs from code (docs/edid-fix.md)
#define _D1_DP_CONNECTOR_TYPE                   _DP_CONNECTOR_NORMAL
#define _D1_DP_LINK_CLK_RATE                    _DP_HIGH_SPEED2_540MHZ
#define _D1_DP_MAIN_LINK_LANES                  _DP_FOUR_LANE

//--------------------------------------------------
// D2 Input Port
//--------------------------------------------------
#define _D2_INPUT_PORT_TYPE                     _D2_HDMI_PORT
#define _D2_DDC_CHANNEL_SEL                     _DDC2
#define _D2_EMBEDDED_DDCRAM_MAX_SIZE            _EDID_SIZE_256
#define _D2_EMBEDDED_DDCRAM_LOCATION            _EDID_TABLE_LOCATION_CODE  // awto: old fw serves all 3 EDIDs from code (docs/edid-fix.md)

//--------------------------------------------------
// D3 Input Port
//--------------------------------------------------
#define _D3_INPUT_PORT_TYPE                     _D3_HDMI_PORT
#define _D3_DDC_CHANNEL_SEL                     _DDC3
#define _D3_EMBEDDED_DDCRAM_MAX_SIZE            _EDID_SIZE_256
#define _D3_EMBEDDED_DDCRAM_LOCATION            _EDID_TABLE_LOCATION_CODE  // awto: old fw serves all 3 EDIDs from code (docs/edid-fix.md)


/////////////////////////////
// Search Group & Priority //
/////////////////////////////

//--------------------------------------------------
// Input Port Search Group Define
//--------------------------------------------------
#define _A0_INPUT_PORT_GROUP                    _INPUT_PORT_GROUP_0
#define _D0_INPUT_PORT_GROUP                    _INPUT_PORT_GROUP_0
#define _D1_INPUT_PORT_GROUP                    _INPUT_PORT_GROUP_0
#define _D2_INPUT_PORT_GROUP                    _INPUT_PORT_GROUP_0
#define _D3_INPUT_PORT_GROUP                    _INPUT_PORT_GROUP_0

//--------------------------------------------------
// Input Port Search Priority Define (Must Start From Valid Port)
//--------------------------------------------------
// awto: A0/D0 are not wired; PRI_0 is also the NVRAM default port, i.e. the boot DDC-CI channel (#8)
#define _INPUT_PORT_SEARCH_PRI_0                _D2_INPUT_PORT
#define _INPUT_PORT_SEARCH_PRI_1                _D1_INPUT_PORT
#define _INPUT_PORT_SEARCH_PRI_2                _D3_INPUT_PORT
#define _INPUT_PORT_SEARCH_PRI_3                _NO_INPUT_PORT
#define _INPUT_PORT_SEARCH_PRI_4                _NO_INPUT_PORT


/////////////////////////
// eDPTx 1.1 HBR Panel //
/////////////////////////

//--------------------------------------------------
// eDPTx 1.1 HBR Main Link Config
//--------------------------------------------------
#define _PANEL_DPTX_1_1_FB_SWAP                 _DISABLE
#define _PANEL_DPTX_1_1_LANE_SWAP               _ENABLE
#define _PANEL_DPTX_1_1_LANE_PN_SWAP            _ENABLE
#define _PANEL_DPTX_1_1_SWING_LEVEL             _DP_SWING_800_MV
#define _PANEL_DPTX_1_1_PREEMPHASIS_LEVEL       _DP_PREEMPHASIS_0_DB

//--------------------------------------------------
// eDPTx 1.1 HBR SSC Config
//--------------------------------------------------
#define _PANEL_DPTX_1_1_SPREAD_RANGE            12
#define _PANEL_DPTX_1_1_SPREAD_SPEED            _SPEED_33K


//////////////////////////
// eDPTx 1.2 HBR2 Panel //
//////////////////////////

//--------------------------------------------------
// eDPTx 1.2 HBR2 Main Link Config
//--------------------------------------------------
#define _PANEL_DPTX_1_2_SWING_LEVEL             _DP_SWING_800_MV
#define _PANEL_DPTX_1_2_PREEMPHASIS_LEVEL       _DP_PREEMPHASIS_3_5_DB

//--------------------------------------------------
// eDPTx 1.2 HBR2 SSC Config
//--------------------------------------------------
#define _PANEL_DPTX_1_2_SPREAD_RANGE            12
#define _PANEL_DPTX_1_2_SPREAD_SPEED            _SPEED_33K

//--------------------------------------------------
// eDPTx 1.2 HBR2 FB/Lane Config
//--------------------------------------------------
// old fw (rip, #7): P38_80 PN swap = 0x0F (all 4 lanes); P38_81..84 lane mux = reset (no lane swap)
#define _PANEL_DPTX_1_2_FB_SWAP                 _DISABLE
#define _PANEL_DPTX_1_2_LANE_SWAP               _DISABLE
#define _PANEL_DPTX_1_2_LANE_PN_SWAP            _ENABLE


/////////
// PWM //
/////////

//--------------------------------------------------
// PWM Setting
//--------------------------------------------------
#define _PWM_DUT_RESOLUTION                     _PWM_8BIT

// Backlight PWM = PWM4 on pin 195 (P9.1, live pin-share mode 3), docs/monitors/gpio-roles.md; polarity untested
#define _BACKLIGHT_PWM                          _PWM4
#define _BACKLIGHT_PWM_INVERSE                  _OFF

#define _PWM0_EN                                _OFF
#define _PWM1_EN                                _OFF
#define _PWM2_EN                                _OFF
#define _PWM3_EN                                _OFF
#define _PWM4_EN                                _ON
#define _PWM5_EN                                _OFF

#define _PWM0_PSAV_EN                           _OFF
#define _PWM1_PSAV_EN                           _OFF
#define _PWM2_PSAV_EN                           _OFF
#define _PWM3_PSAV_EN                           _OFF
#define _PWM4_PSAV_EN                           _OFF
#define _PWM5_PSAV_EN                           _OFF

#define _PWM0_PDOW_EN                           _OFF
#define _PWM1_PDOW_EN                           _OFF
#define _PWM2_PDOW_EN                           _OFF
#define _PWM3_PDOW_EN                           _OFF
#define _PWM4_PDOW_EN                           _OFF
#define _PWM5_PDOW_EN                           _OFF

#define _PWM0_RST_EN                            _OFF
#define _PWM1_RST_EN                            _OFF
#define _PWM2_RST_EN                            _OFF
#define _PWM3_RST_EN                            _OFF
#define _PWM4_RST_EN                            _OFF
#define _PWM5_RST_EN                            _OFF
#define _PWM_RST_SIGNAL_SEL                     _DVS


/////////////////
// SW & HW IIC //
/////////////////

//--------------------------------------------------
// Sofware and Hardware IIC Option
//--------------------------------------------------
#define _SW_IIC_SUPPORT                         _OFF
#define _SW_IIC_CLK_DIV                         _DIV_1

#define _HW_IIC_SUPPORT                         _OFF    // awto: no EEPROM / IIC device on the HW IIC pins 210/211 (GPIO here), #53.3
#define _HW_IIC_SPEED                           _HW_IIC_LOW_SPEED_100K


///////////////////
// System Eeprom //
///////////////////

//--------------------------------------------------
// Eeprom System Data Storage Option
//--------------------------------------------------
#define _EEPROM_TYPE                            _EEPROM_24LC16
#define _EEPROM_SLAVE_ADDRESS                   0xA0
#define _PCB_SYS_EEPROM_IIC                     _NO_IIC_PIN     // awto: settings are flash-emulated (#53.3)


//////////
// Misc //
//////////

//--------------------------------------------------
// AD Key Option
//--------------------------------------------------
#define _AD_KEY_SUPPORT                         _ON

//--------------------------------------------------
// Low Speed ADC Option
//--------------------------------------------------
#define _LOW_SPEED_ADC_SUPPORT                  _ON


//////////////////////
// Series Pin Share //
//////////////////////
#include "RL6449_AWTO_JXC4K_PINSHARE.h"


//////////////////////
// GPIO Power Macro //
//////////////////////

//-----------------------------------------------
// Macro of Pcb GPIO ON/OFF Region Initial Setting
//-----------------------------------------------
#define PCB_ON_REGION_GPIO_SETTING_POWER_AC_ON(){\
                                                }

#define PCB_OFF_REGION_GPIO_SETTING_POWER_AC_PD_PS_ON()\
                                                {\
                                                }

#define PCB_GPIO_SETTING_POWER_NORMAL()         {\
                                                }

#define PCB_GPIO_SETTING_POWER_SAVING()         {\
                                                }

#define PCB_GPIO_SETTING_POWER_DOWN()           {\
                                                }


/////////////////////
// PCB Power Macro //
/////////////////////

//-----------------------------------------------
// Macro of VCCK_OFF Power Control
//-----------------------------------------------
// Old fw never writes P8.1 (VCCK_OFF) or P9.6 (DDR): macros are no-ops (docs/monitors/gpio-roles.md)
#define bVCCKOFFPOWER                           (MCU_FE21_PORT81_PIN_REG) // Pin_179, P8.1

#define _VCCK_OFF_POWER_ON                      1
#define _VCCK_OFF_POWER_OFF                     0

#define PCB_VCCK_OFF_POWER(x)                   {\
                                                }

//-----------------------------------------------
// Macro of DDR Poewr Control
//-----------------------------------------------
#define bDDRPOWER                               (MCU_FE2E_PORT96_PIN_REG) // Pin_200, P9.6

#define _DDR_POWER_ON                           1
#define _DDR_POWER_OFF                          0

#define PCB_DDR_POWER(x)                        {\
                                                }

//-----------------------------------------------
// Panel power and backlight enable, from the live GPIO read (docs/monitors/gpio-roles.md)
//-----------------------------------------------
#define bPANELPOWER                             (MCU_FE1A_PORT72_PIN_REG) // Pin_159, P7.2

#define _PANEL_CONTROL_ON                       1
#define _PANEL_CONTROL_OFF                      0

#define PCB_PANEL_POWER(x)                      {\
                                                    bPANELPOWER = (x);\
                                                }

#define PCB_PANEL_POWER_DETECT()                (bPANELPOWER)

#define bBACKLIGHTPOWER                         (MCU_FE25_PORT85_PIN_REG) // Pin_185, P8.5

#define _LIGHT_CONTROL_ON                       1
#define _LIGHT_CONTROL_OFF                      0

// P9.2 = backlight enable, active LOW (proven live, #7)
#define bBACKLIGHT_EN_N                         (MCU_FE2A_PORT92_PIN_REG) // Pin_196, P9.2

#define PCB_BACKLIGHT_POWER_PIN(x)              {\
                                                    bBACKLIGHT_EN_N = !(x);\
                                                    bBACKLIGHTPOWER = (x);\
                                                }

#define PCB_BACKLIGHT_POWER(x)                  {\
                                                    if((x) == _LIGHT_CONTROL_ON)\
                                                    {\
                                                        ScalerTimerActiveTimerEvent(SEC(60), _USER_TIMER_EVENT_PANEL_USED_TIMER);\
                                                        ScalerMcuPwmAdjustFrequency(_BACKLIGHT_PWM, (((DWORD)_PANEL_TYP_FRAME_RATE * 60) / 100));\
                                                    }\
                                                    else\
                                                    {\
                                                        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_PANEL_USED_TIMER);\
                                                    }\
                                                    PCB_BACKLIGHT_POWER_PIN(x)\
                                                }

// Brightness: SDK default PCB_BACKLIGHT_PWM is empty (RL6449_Pcb_Default.h) -> duty stayed 0, dark (#7)
#define PCB_BACKLIGHT_PWM(x)                    {\
                                                    MCU_ADJUST_8BIT_PWM_DUTY(_BACKLIGHT_PWM, (x));\
                                                }

#define PCB_GET_BACKLIGHT_PWM()                 (MCU_GET_8BIT_PWM_DUTY(_BACKLIGHT_PWM))

//-----------------------------------------------
// Macro of 12V to 5V Regulator for MyDP or MHL
//-----------------------------------------------
#define bREGULATOR_5V                           (MCU_FE22_PORT82_PIN_REG) // Pin_180, P8.2

#define _REGULATOR_5V_ON                        0
#define _REGULATOR_5V_OFF                       1

#define PCB_REGULATOR_5V_OUT(x)                 {}      // awto: P8.2 role unproven, not driven (#53.4)


/////////////////////////
// Write Protect Macro //
/////////////////////////

//-----------------------------------------------
// Macro of Flash write protect pin
//-----------------------------------------------
#define bFLASH_WRITE_PROTECT                    (MCU_FE26_PORT86_PIN_REG) // Pin_190, P8.6

#define _FLASH_WRITE_PROTECT_ENABLE             0
#define _FLASH_WRITE_PROTECT_DISABLE            1

#define PCB_FLASH_WRITE_PROTECT(x)              {\
                                                    bFLASH_WRITE_PROTECT = (x);\
                                                }

//-----------------------------------------------
// Macro of System Eeprom WP High/Low
//-----------------------------------------------
// awto: no EEPROM, PA.6 is not driven (#53.3)
#define _EEPROM_WP_ENABLE                       1
#define _EEPROM_WP_DISABLE                      0

#define PCB_EEPROM_WRITE_PROTECT(x)             {}

#define PCB_EEPROM_WRITE_PROTECT_DETECT()       (_EEPROM_WP_ENABLE)

//-----------------------------------------------
// Macro of EDID Eeprom WP High/Low
//-----------------------------------------------
#define bEDID_WRITE_PROTECT                     (MCU_FE23_PORT83_PIN_REG) // Pin_181, P8.3

#define _EDID_EEPROM_WP_ENABLE                  1
#define _EDID_EEPROM_WP_DISABLE                 0

#define PCB_A0_EDID_EEPROM_WRITE_PROTECT(x)     {\
                                                    bEDID_WRITE_PROTECT = (x);\
                                                }

#define PCB_D2_EDID_EEPROM_WRITE_PROTECT(x)     {\
                                                    bEDID_WRITE_PROTECT = (x);\
                                                }

#define PCB_D3_EDID_EEPROM_WRITE_PROTECT(x)     {\
                                                    bEDID_WRITE_PROTECT = (x);\
                                                }


////////////////////////
// Cable Status Macro //
////////////////////////

//-----------------------------------------------
// Macro of Input Cable Connect
//-----------------------------------------------
#define bD0_DP_PIN15_CONNECT                    (P1_7) // Pin_70, P1.7
#define bD0_DP_PIN16_CONNECT                    (P1_6) // Pin_69, P1.6
#define bD0_DP_PIN17_CONNECT                    (P1_5) // Pin_68, P1.5
#define bD1_DP_PIN15_CONNECT                    (MCU_FE34_PORTA4_PIN_REG) // Pin_207, PA.4
#define bD1_DP_PIN16_CONNECT                    (MCU_FE35_PORTA5_PIN_REG) // Pin_208, PA.5
#define bD1_DP_PIN17_CONNECT                    (MCU_FE33_PORTA3_PIN_REG) // Pin_206, PA.3

#define bA0_CONNECT                             (P1_4)  // Pin_67, P1.4
#define bD0_CONNECT                             (((bit)bD0_DP_PIN15_CONNECT == _TRUE) && ((bit)bD0_DP_PIN16_CONNECT == _TRUE) && ((bit)bD0_DP_PIN17_CONNECT == _FALSE))
#define bD1_CONNECT                             (((bit)bD1_DP_PIN15_CONNECT == _TRUE) && ((bit)bD1_DP_PIN16_CONNECT == _TRUE) && ((bit)bD1_DP_PIN17_CONNECT == _FALSE))
#define bD2_CONNECT                             (MCU_FE32_PORTA2_PIN_REG) // PIN_204, PA.2
#define bD3_CONNECT                             (MCU_FE2C_PORT94_PIN_REG) // PIN_198, P9.4

#define PCB_A0_PIN()                            (bA0_CONNECT)
#define PCB_D0_PIN()                            (bD0_CONNECT)
#define PCB_D1_PIN()                            (bD1_CONNECT)
#define PCB_D2_PIN()                            (bD2_CONNECT)
#define PCB_D3_PIN()                            (bD3_CONNECT)

//-----------------------------------------------
// Macro of DP Source Power
//-----------------------------------------------
#define GET_PCB_D0_DP_SOURCE_POWER()            (bD0_DP_PIN17_CONNECT)
#define GET_PCB_D1_DP_SOURCE_POWER()            (bD1_DP_PIN17_CONNECT)

//-----------------------------------------------
// Macro of MHL Cable Connect
//-----------------------------------------------
#define bD2_MHL_CONNECT                         (MCU_FE30_PORTA0_PIN_REG) // Pin_202, PA.0
#define bD3_MHL_CONNECT                         (MCU_FE31_PORTA1_PIN_REG) // Pin_203, PA.1

#define PCB_D2_MHL_DETECT()                     (bD2_MHL_CONNECT)
#define PCB_D3_MHL_DETECT()                     (bD3_MHL_CONNECT)


////////////////////
// Hot Plug Macro //
////////////////////

//-----------------------------------------------
// Macro of Digital Hot Plug High/Low
//-----------------------------------------------
#define bD0_HPD                                 (MCU_FE01_PORT41_PIN_REG) // Pin_96, P4.1
#define bD1_HPD                                 (MCU_FE02_PORT42_PIN_REG) // Pin_97, P4.2
#define bD2_HPD                                 (P1_1) // Pin_14, P1.1
#define bD3_HPD                                 (P1_0) // Pin_1, P1.0

#define _D0_HOT_PLUG_HIGH                       1
#define _D0_HOT_PLUG_LOW                        0

#define _D1_HOT_PLUG_HIGH                       1
#define _D1_HOT_PLUG_LOW                        0

#define _D2_HOT_PLUG_HIGH                       1
#define _D2_HOT_PLUG_LOW                        0

#define _D3_HOT_PLUG_HIGH                       1
#define _D3_HOT_PLUG_LOW                        0

#define PCB_D0_HOTPLUG(x)                       {\
                                                    AWTO_SW_HPD(0, x);\
                                                    bD0_HPD = (x);\
                                                }

#define PCB_D1_HOTPLUG(x)                       {\
                                                    AWTO_SW_HPD(1, x);\
                                                    bD1_HPD = (x);\
                                                }

#define PCB_D2_HOTPLUG(x)                       {\
                                                    AWTO_SW_HPD(2, x);\
                                                    bD2_HPD = (x);\
                                                }

#define PCB_D3_HOTPLUG(x)                       {\
                                                    AWTO_SW_HPD(3, x);\
                                                    bD3_HPD = (x);\
                                                }

#define PCB_D0_HOTPLUG_DETECT()                 (bD0_HPD)
#define PCB_D1_HOTPLUG_DETECT()                 (bD1_HPD)
#define PCB_D2_HOTPLUG_DETECT()                 (bD2_HPD)
#define PCB_D3_HOTPLUG_DETECT()                 (bD3_HPD)


///////////////
// MHL Macro //
///////////////

//-----------------------------------------------
// Macro of HDMI/MHL Switch
//-----------------------------------------------
#define bD2_TMDS_SWITCH                         (MCU_FE2B_PORT93_PIN_REG) // Pin_197, P9.3

#define _TMDS_SWITCH_MHL_CBUS                   0
#define _TMDS_SWITCH_HDMI_HPD                   1

// No MHL on this board: P9.1/P9.2/P9.3 are backlight PWM4 / standby LED / unknown (gpio-roles.md); never driven here
#define PCB_D2_HDMI_MHL_SWITCH(x)               {\
                                                }

#define PCB_D3_HDMI_MHL_SWITCH(x)               {\
                                                }

//-----------------------------------------------
// Macro of MHL VBus Switch
//-----------------------------------------------
#define bD2_MHL_VBUS_SWITCH                     (MCU_FE29_PORT91_PIN_REG) // Pin_195, P9.1
#define bD3_MHL_VBUS_SWITCH                     (MCU_FE2F_PORT97_PIN_REG) // Pin_201, P9.7

#define _MHL_VBUS_ON                            1
#define _MHL_VBUS_OFF                           0

#define PCB_D2_MHL_VBUS_SWITCH(x)               {\
                                                }

#define PCB_D3_MHL_VBUS_SWITCH(x)               {\
                                                }

#define PCB_GET_D2_MHL_VBUS_SWITCH()            (_MHL_VBUS_OFF)
#define PCB_GET_D3_MHL_VBUS_SWITCH()            (_MHL_VBUS_OFF)


///////////////
// LED Macro //
///////////////

//--------------------------------------------------
// Macro of LED On/Off
//--------------------------------------------------
#define bLED1                                   (MCU_FE24_PORT84_PIN_REG) // Pin_184, P8.4
// awto: LED2..5 (P9.0, P9.5, P6.3, P7.0) are unproven: their macros are no-ops, only LED1 (P8.4) is driven (#53.4)
#define bLED2                                   (MCU_FE28_PORT90_PIN_REG) // Pin_194, P9.0
#define bLED3                                   (MCU_FE2D_PORT95_PIN_REG) // Pin_199, P9.5
#define bLED4                                   (MCU_FE13_PORT63_PIN_REG) // Pin_152, P6.3
#define bLED5                                   (MCU_FE18_PORT70_PIN_REG) // Pin_157, P7.0

#define _LED_ON                                 1
#define _LED_OFF                                0

#define PCB_LED_AC_ON_INITIAL()                 {\
                                                    bLED1 = _LED_OFF;\
                                                }

#define PCB_LED_ACTIVE()                        {\
                                                    bLED1 = _LED_ON;\
                                                }

#define PCB_LED_IDLE()                          {\
                                                    bLED1 = _LED_OFF;\
                                                }

#define PCB_LED_POWER_SAVING()                  {\
                                                    bLED1 = _LED_OFF;\
                                                }

#define PCB_LED_ON()                            {\
                                                    bLED1 = _LED_ON;\
                                                }

#define PCB_LED_OFF()                           {\
                                                    bLED1 = _LED_OFF;\
                                                }

#define PCB_LED_TYPE1()                         {\
                                                    bLED1 = _LED_ON;\
                                                }

#define PCB_LED_TYPE2()                         {\
                                                }

#define PCB_LED_TYPE3()                         {\
                                                }

#define PCB_LED_TYPE4()                         {\
                                                }

#define PCB_LED_TYPE5()                         {\
                                                }

#define PCB_LED_TYPE_FLASH()                    {\
                                                }


//////////////////
// AD Key Macro //
//////////////////

//-----------------------------------------------
// Macro of Keypad Setting
//-----------------------------------------------
#define AD_KEY1                                 (MCU_FF09_ADC_A0_CONVERT_RESULT) // Pin_94
#define AD_KEY2                                 (MCU_FF0A_ADC_A1_CONVERT_RESULT) // Pin_95

#define PCB_ADKEY1()                            (AD_KEY1)
#define PCB_ADKEY2()                            (AD_KEY2)

// Keys left to right: SOURCE MENU DOWN UP AUTO POWER. Vendor decode (buttons.md, #85): lo <= R < hi on 0xFF09 (A0) / 0xFF0A (A1), POWER = P3.0 low.
// SDK masks: SOURCE = _KEY5_MASK, DOWN = _LEFT, UP = _RIGHT, AUTO = _EXIT. A0 top (0xC0) vs A1 mid (0x68): which is SOURCE is unconfirmed (#85).
// _ON = A0 top is SOURCE. Combos need keys on different ladders (A0: SOURCE MENU DOWN, A1: UP AUTO), else the voltages mix.
#define _AWTO_KEY_A0TOP_SOURCE                  _ON
#define AWTO_KEY_A0_TOP_MASK                    ((_AWTO_KEY_A0TOP_SOURCE == _ON) ? _KEY5_MASK : _EXIT_KEY_MASK)
#define AWTO_KEY_A1_MID_MASK                    ((_AWTO_KEY_A0TOP_SOURCE == _ON) ? _EXIT_KEY_MASK : _KEY5_MASK)
#define AWTO_KEY_BAND(v, lo, hi)                (((lo) <= (v)) && ((v) < (hi)))

#define PCB_KEY_STATE(ucV0, ucV1,\
                      ucV2, ucV3, ucKeyState)   {\
                                                    if(AWTO_KEY_BAND(ucV1, 0xC0, 0xE0))\
                                                    {\
                                                        (ucKeyState) |= AWTO_KEY_A0_TOP_MASK;\
                                                    }\
                                                    if(AWTO_KEY_BAND(ucV1, 0x70, 0x90))\
                                                    {\
                                                        (ucKeyState) |= _MENU_KEY_MASK;\
                                                    }\
                                                    if(AWTO_KEY_BAND(ucV1, 0x28, 0x48))\
                                                    {\
                                                        (ucKeyState) |= _LEFT_KEY_MASK;\
                                                    }\
                                                    if(AWTO_KEY_BAND(ucV2, 0x68, 0x88))\
                                                    {\
                                                        (ucKeyState) |= AWTO_KEY_A1_MID_MASK;\
                                                    }\
                                                    if(AWTO_KEY_BAND(ucV2, 0x28, 0x48))\
                                                    {\
                                                        (ucKeyState) |= _RIGHT_KEY_MASK;\
                                                    }\
                                                    if(P3_0 == 0)\
                                                    {\
                                                        (ucKeyState) |= _POWER_KEY_MASK;\
                                                    }\
                                                }

#endif // End of #if(_PCB_TYPE == _RL6449_AWTO_JXC4K)
