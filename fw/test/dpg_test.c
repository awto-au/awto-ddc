#include "UserCommonInclude.h"

// #228: Realtek's D-domain pattern generator test (RL6449_Series_QC_Color_DDomain.c ScalerQCDDomainPatternGenOn / Off, 12-bit mode),
// test cmds 0xB2 on / 0xB3 off. Main set P7 F0..FF + sub set P87 F0..FD (sub names: gen_regnames EXTRA, from the RTD2797UPM regdb). The picture is the scaler's own
// R / G / B ramp generator; the QC then compares its CRC, which we do not.
#define AWTO_DPG_R_CTRL                         0x8D            // QC value: enable + gradient setup, see the regdb DISP_PG_*_CTRL fields
#define AWTO_DPG_GB_CTRL                        0x0D
#define AWTO_DPG_R_INIT                         0x30
#define AWTO_DPG_G_INIT                         0x60
#define AWTO_DPG_B_INIT                         0x90
#define AWTO_DPG_PIXEL_DELTA_H                  0x09
#define AWTO_DPG_LINE_DELTA_H                   0x13
#define AWTO_DPG_PIXEL_STEP_H                   0x01
#define AWTO_DPG_LINE_STEP_H                    0x10
#define AWTO_DPG_INITIAL_L_12BIT                0x80            // _BIT_MODE_12
#define AWTO_DPG_ZERO                           0x00
#define AWTO_DPG_ARG_ON                         0x60            // sync E9 args: 0x60 DPG on, 0x61 off
#define AWTO_DPG_ARG_OFF                        0x61

void AwtoDpgTest(unsigned char ucOn)
{
    if(ucOn == 0)
    {
        AWTO_XFR(AWTO_R_DISP_PG_R_CTRL) = AWTO_DPG_ZERO;           // QC PatternGenOff: the enable bit lives in the R control byte
        AWTO_XFR(AWTO_R_DISP_PG_R_CTRL_SUB) = AWTO_DPG_ZERO;
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_DPG_ARG_OFF, 0);
        return;
    }
    AWTO_XFR(AWTO_R_DISP_PG_R_CTRL) = AWTO_DPG_R_CTRL;
    AWTO_XFR(AWTO_R_DISP_PG_G_CTRL) = AWTO_DPG_GB_CTRL;
    AWTO_XFR(AWTO_R_DISP_PG_B_CTRL) = AWTO_DPG_GB_CTRL;
    AWTO_XFR(AWTO_R_DISP_PG_R_INITIAL) = AWTO_DPG_R_INIT;
    AWTO_XFR(AWTO_R_DISP_PG_G_INITIAL) = AWTO_DPG_G_INIT;
    AWTO_XFR(AWTO_R_DISP_PG_B_INITIAL) = AWTO_DPG_B_INIT;
    AWTO_XFR(AWTO_R_DISP_PG_PIXEL_DELTA_H) = AWTO_DPG_PIXEL_DELTA_H;
    AWTO_XFR(AWTO_R_DISP_PG_LINE_DELTA_H) = AWTO_DPG_LINE_DELTA_H;
    AWTO_XFR(AWTO_R_DISP_PG_PIXEL_STEP_H) = AWTO_DPG_PIXEL_STEP_H;
    AWTO_XFR(AWTO_R_DISP_PG_LINE_STEP_H) = AWTO_DPG_LINE_STEP_H;
    AWTO_XFR(AWTO_R_DISP_PG_DELTA_H_STEP_M) = AWTO_DPG_ZERO;
    AWTO_XFR(AWTO_R_D_PG_CTRL_0) = AWTO_DPG_ZERO;
    AWTO_XFR(AWTO_R_D_PG_INITIAL_M_STEP_L) = AWTO_DPG_ZERO;
    AWTO_XFR(AWTO_R_D_PG_INITIAL_L_CTRL) = AWTO_DPG_INITIAL_L_12BIT;
    AWTO_XFR(AWTO_R_DISP_PG_R_CTRL_SUB) = AWTO_DPG_R_CTRL;         // sub path: same values (QC main + sub set)
    AWTO_XFR(AWTO_R_DISP_PG_G_CTRL_SUB) = AWTO_DPG_GB_CTRL;
    AWTO_XFR(AWTO_R_DISP_PG_B_CTRL_SUB) = AWTO_DPG_GB_CTRL;
    AWTO_XFR(AWTO_R_DISP_PG_R_INITIAL_SUB) = AWTO_DPG_R_INIT;
    AWTO_XFR(AWTO_R_DISP_PG_G_INITIAL_SUB) = AWTO_DPG_G_INIT;
    AWTO_XFR(AWTO_R_DISP_PG_B_INITIAL_SUB) = AWTO_DPG_B_INIT;
    AWTO_XFR(AWTO_R_DISP_PG_PIXEL_DELTA_H_SUB) = AWTO_DPG_PIXEL_DELTA_H;
    AWTO_XFR(AWTO_R_DISP_PG_LINE_DELTA_H_SUB) = AWTO_DPG_LINE_DELTA_H;
    AWTO_XFR(AWTO_R_DISP_PG_PIXEL_STEP_H_SUB) = AWTO_DPG_PIXEL_STEP_H;
    AWTO_XFR(AWTO_R_DISP_PG_LINE_STEP_H_SUB) = AWTO_DPG_LINE_STEP_H;
    AWTO_XFR(AWTO_R_DISP_PG_DELTA_H_STEP_M_SUB) = AWTO_DPG_ZERO;
    AWTO_XFR(AWTO_R_D_PG_CTRL_0_SUB) = AWTO_DPG_ZERO;
    AWTO_XFR(AWTO_R_D_PG_INITIAL_M_STEP_L_SUB) = AWTO_DPG_ZERO;
    AWTO_XFR(AWTO_R_D_PG_INITIAL_L_CTRL_SUB) = AWTO_DPG_INITIAL_L_12BIT;
    AWTO_XFR(AWTO_R_DISP_PG_DELTA_L) = AWTO_DPG_ZERO;
    AWTO_XFR(AWTO_R_D_PATTERN_RESET) = AWTO_DPG_ZERO;
    AwtoSyncPush(AWTO_SYNC_EV_ODEMO, AWTO_DPG_ARG_ON, 0);
}
