// Samsung LTM270FL01 27" UHD PLS, eDP HBR2 x4 on DPTX TX1 (JXC/Dahua 4K board).
// Timing = old firmware's live registers, unit 1 rip 2026-11-05 (awto-ddc#7); panel notes:
// docs/monitors/panel-samsung-ltm270fl01.md. Power-sequence T1..T6: SDK example values (no datasheet).
#if(_PANEL_TYPE == _AWTO_LTM270FL01)

#define _PANEL_STYLE                            _PANEL_DPTX

#define _PANEL_DPTX_LINK_RATE                   _PANEL_DPTX_LINK_HBR2      // 540 MHz pclk @30 bpp needs HBR2 x4
#define _PANEL_DPTX_LANE_NUMBER                 _PANEL_DPTX_LANE_NUMBER_4  // P38_A1 = 0x0F
#define _PANEL_DPTX_PORT_NUMBER_SEL             _DPTX_TX1_PORT             // old fw drives page 9C (TX1)

#define _PANEL_EXIST_MULTIPANEL                 _OFF
#define _PANEL_MANUFACTURER                     _PANEL_SAMSUNG
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

#define _PANEL_DV_START                         8
#define _PANEL_DV_HEIGHT                        2160
#define _PANEL_DV_END                           2168

#define _PANEL_DV_TOTAL                         2251                       // MSA Vtotal, frame-synced at 60 Hz
#define _PANEL_DV_TOTAL_MAX                     2311                       // old fw DV total register
#define _PANEL_DV_TOTAL_MIN                     2180

#define _PANEL_DH_SYNC_WIDTH                    8
#define _PANEL_DV_SYNC_HEIGHT                   2

// MHz: 4000 x 2251 x 60 Hz = 540.2
#define _PANEL_PIXEL_CLOCK                      540
#define _PANEL_PIXEL_CLOCK_MAX                  600
#define _PANEL_PIXEL_CLOCK_MIN                  160

#define _PANEL_POWER_ON_T1                      10
#define _PANEL_POWER_ON_T2                      250
#define _PANEL_POWER_ON_T3                      550                        // video valid -> backlight on: >= 500 ms (27" 4K eDP datasheets, docs/monitors/panel-edid.md)

#define _PANEL_POWER_OFF_T4                     250
#define _PANEL_POWER_OFF_T5                     20
#define _PANEL_POWER_OFF_T6                     1100

#define _LAST_LINE_TARGET                       (_PANEL_DH_TOTAL - 300)
#define _FRAME_SYNC_MARGIN                      20                         // 0.1 Hz

#include "./RTDColorDefaultTable/ColorTableInclude.h"

#endif // _PANEL_TYPE == _AWTO_LTM270FL01
