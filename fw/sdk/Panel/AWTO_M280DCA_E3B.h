// Innolux M280DCA-E3B rev C1, 28" UHD, eDP HBR2 x4 on DPTX TX1 (JXC/Dahua 4K board; panel label, awto-ddc#3).
// Timing = old firmware's live registers, unit 1 rip 2026-11-05 (awto-ddc#7); datasheet + T-value check:
// docs/monitors/panel-innolux-m280dca-e3b.md.
#if(_PANEL_TYPE == _AWTO_M280DCA_E3B)

#define _PANEL_STYLE                            _PANEL_DPTX

#define _PANEL_DPTX_LINK_RATE                   _PANEL_DPTX_LINK_HBR2      // 540 MHz pclk @30 bpp needs HBR2 x4
#define _PANEL_DPTX_LANE_NUMBER                 _PANEL_DPTX_LANE_NUMBER_4  // P38_A1 = 0x0F
#define _PANEL_DPTX_PORT_NUMBER_SEL             _DPTX_TX1_PORT             // old fw drives page 9C (TX1)

#define _PANEL_EXIST_MULTIPANEL                 _OFF
#define _PANEL_MANUFACTURER                     _PANEL_INNOLUX
#define _PANEL_DISP_BIT_MODE                    _PANEL_DISP_30_BIT         // MSA colorbit 2 = 10 bpc

// Unit 0.1 Hz; panel rated 60 Hz only
#define _PANEL_TYP_FRAME_RATE                   600
#define _PANEL_MAX_FRAME_RATE                   610
#define _PANEL_MIN_FRAME_RATE                   590

// Display-format port (P0_2A/2B) + DPTX MSA (P9C_B7..C6) of the old firmware
#define _PANEL_DH_START                         48
#define _PANEL_DH_WIDTH                         3840
#define _PANEL_DH_END                           3888

#define _PANEL_DH_TOTAL                         4000
#define _PANEL_DH_TOTAL_MAX                     7040
#define _PANEL_DH_TOTAL_MIN                     4000

// DV start/total/min/max: old fw compiled constants (bank1 CE2A struct init, bank2 ACDF clamp), #26
#define _PANEL_DV_START                         6
#define _PANEL_DV_HEIGHT                        2160
#define _PANEL_DV_END                           2166

#define _PANEL_DV_TOTAL                         2222
#define _PANEL_DV_TOTAL_MAX                     3520
#define _PANEL_DV_TOTAL_MIN                     2200

#define _PANEL_DH_SYNC_WIDTH                    8
#define _PANEL_DV_SYNC_HEIGHT                   2

// MHz: 4000 x 2222 x 60 Hz = 533.3
#define _PANEL_PIXEL_CLOCK                      533
#define _PANEL_PIXEL_CLOCK_MAX                  600
#define _PANEL_PIXEL_CLOCK_MIN                  160

#define _PANEL_POWER_ON_T1                      10
#define _PANEL_POWER_ON_T2                      250
#define _PANEL_POWER_ON_T3                      550                        // video valid -> backlight on; datasheet T8 >= 200 ms (panel-innolux-m280dca-e3b.md)

#define _PANEL_POWER_OFF_T4                     250
#define _PANEL_POWER_OFF_T5                     20
#define _PANEL_POWER_OFF_T6                     900                        // datasheet T11 >= 1000 ms - 10 % (delay rule)
#ifdef _AWTO_NEW_SETTINGS                       // #67: power sequence from the settings registry (values above = registry defaults)
#undef _PANEL_POWER_ON_T1
#undef _PANEL_POWER_ON_T2
#undef _PANEL_POWER_ON_T3
#undef _PANEL_POWER_OFF_T4
#undef _PANEL_POWER_OFF_T5
#undef _PANEL_POWER_OFF_T6
#define _PANEL_POWER_ON_T1                      AWTO_SET(PANEL_T1)
#define _PANEL_POWER_ON_T2                      AWTO_SET(PANEL_T2)
#define _PANEL_POWER_ON_T3                      AWTO_SET(PANEL_T3)
#define _PANEL_POWER_OFF_T4                     AWTO_SET(PANEL_T4)
#define _PANEL_POWER_OFF_T5                     AWTO_SET(PANEL_T5)
#define _PANEL_POWER_OFF_T6                     AWTO_SET(PANEL_T6)
#endif

#define _LAST_LINE_TARGET                       (_PANEL_DH_TOTAL - 300)
#define _FRAME_SYNC_MARGIN                      20                         // 0.1 Hz

#include "./RTDColorDefaultTable/ColorTableInclude.h"

#endif // _PANEL_TYPE == _AWTO_M280DCA_E3B
