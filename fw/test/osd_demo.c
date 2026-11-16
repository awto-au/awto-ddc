#include "UserCommonInclude.h"

// #226 / #215 / #227: OSD window demo on the unit (test cmds 0xA0..0xA5). Windows and effects as Realtek's QC code sets them
// (RL6449_Series_QC_OSD.c ScalerQC_OSDSetGradient / SetGridLine / SetShadowBorder), on an OSD we open ourselves; the picture stays
// until 0xA5. Each case writes one sync line (E9) saying what it is. Windows are drawn raw: no minimum width (osd_tc_win_draw).
//   0xA0 #215 measurement: zero-width / zero-height / point / end-before-start windows
//   0xA1 gradients: horizontal 0, 5, 6 and vertical 7, 8, 9 (R / G / B enables and polarities)
//   0xA2 grid lines: windows 2, 3, 4 (width, pitch, H / V)
//   0xA3 shadow / border / 3D button types
//   0xA4 saturated + reversed gradient, window priority (overlap)
//   0xA5 close
extern void osd_tc_open(BYTE ucChars, BYTE ucLines, BYTE ucFont);
extern void osd_tc_place(BYTE ucH, BYTE ucV, BYTE ucBig);
extern void osd_tc_show(BYTE ucOn);
extern void osd_tc_close(void);
extern void osd_tc_bar(BYTE ucWin, WORD usX0, WORD usY0, WORD usX1, WORD usY1, BYTE ucColour);

#define AWTO_DEMO_CHARS                         48                  // 48 x 12 = 576 px wide
#define AWTO_DEMO_LINES                         20                  // 20 x 18 = 360 px high
#define AWTO_DEMO_PAL                           20                  // first demo palette index (the awto screens use 1..12)
#define AWTO_DEMO_W                             150
#define AWTO_DEMO_H                             90

static const __code BYTE tAwtoDemoRgb[8][3] =
{
    {0x00, 0x00, 0x00}, {0xFF, 0x20, 0x20}, {0x20, 0xFF, 0x20}, {0x30, 0x60, 0xFF},
    {0xFF, 0xFF, 0x20}, {0xFF, 0x20, 0xFF}, {0x20, 0xFF, 0xFF}, {0xFF, 0xFF, 0xFF},
};

static void AwtoDemoOpen(void)
{
    BYTE ucI;

    osd_tc_open(AWTO_DEMO_CHARS, AWTO_DEMO_LINES, 0);
    for(ucI = 0; ucI < 8; ucI++)
    {
        ScalerOsdSetColorPalette(AWTO_DEMO_PAL + ucI, tAwtoDemoRgb[ucI][0], tAwtoDemoRgb[ucI][1], tAwtoDemoRgb[ucI][2]);
    }
    osd_tc_place(50, 50, 0);
    osd_tc_show(1);
    osd_tc_bar(0, 0, 0, AWTO_DEMO_CHARS * 12 - 1, AWTO_DEMO_LINES * 18 - 1, 0);             // window 0: the dark panel behind the cases
}

static void AwtoDemoReset(void)
{
    memset(&g_stOsdWindow, 0, sizeof(g_stOsdWindow));
    memset(&g_stOsdGridWindow, 0, sizeof(g_stOsdGridWindow));
    SET_OSD_WINDOW_REFERENCE_DELAY(_OSD_FIRST_DELAY);
}

static void AwtoDemoPlain(BYTE ucWin, BYTE ucCol, WORD usX0, WORD usY0, WORD usX1, WORD usY1)
{
    AwtoDemoReset();
    SET_OSD_WINDOW_COLOR(AWTO_DEMO_PAL + ucCol);
    osd_tc_win_draw(ucWin, usX0, usY0, usX1, usY1);
}

static void AwtoDemoGradient(BYTE ucWin, BYTE ucIdx, BYTE ucStep, BYTE ucPer, BYTE ucDir, BYTE ucR, BYTE ucG, BYTE ucB, BYTE ucPr, BYTE ucPg, BYTE ucPb, WORD usX0, WORD usY0)
{
    AwtoDemoReset();
    SET_OSD_WINDOW_COLOR(AWTO_DEMO_PAL + ucIdx);
    SET_OSD_WINDOW_GRADIENT_LEVEL_SETP(ucStep);
    SET_OSD_WINDOW_GRADIENT_LEVEL_PER(ucPer);
    SET_OSD_WINDOW_GRADIENT_POLARITY_R(ucPr);
    SET_OSD_WINDOW_GRADIENT_POLARITY_G(ucPg);
    SET_OSD_WINDOW_GRADIENT_POLARITY_B(ucPb);
    SET_OSD_WINDOW_GRADIENT_ENABLE_R(ucR);
    SET_OSD_WINDOW_GRADIENT_ENABLE_G(ucG);
    SET_OSD_WINDOW_GRADIENT_ENABLE_B(ucB);
    SET_OSD_WINDOW_GRADIENT_LEVEL_EXTENSION(_OSD_WINDOW_GRADIENT_LEVEL_EXTENSION_8);
    SET_OSD_WINDOW_GRADIENT_ENABLE(_ENABLE);
    SET_OSD_WINDOW_GRADIENT_DIRECTION(ucDir);
    osd_tc_win_draw(ucWin, usX0, usY0, usX0 + AWTO_DEMO_W, usY0 + AWTO_DEMO_H);
}

void AwtoOsdDemo(BYTE ucGroup)
{
    BYTE ucI;

    if(ucGroup == 5)
    {
        osd_tc_close();
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 0xFF, 0);
        return;
    }
    AwtoDemoOpen();
    if(ucGroup == 0)                                    // #215: where does a degenerate window end? (x, y in OSD px)
    {
        AwtoDemoPlain(1, 2, 100, 40, 100, 140);         // x0 == x1, 100 px tall
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 1, 1);
        AwtoDemoPlain(2, 3, 150, 200, 300, 200);        // y0 == y1, 150 px wide
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 2, 2);
        AwtoDemoPlain(3, 4, 400, 100, 400, 100);        // x0 == x1 and y0 == y1
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 3, 3);
        AwtoDemoPlain(4, 5, 480, 40, 479, 140);         // x1 = x0 - 1
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 4, 4);
        AwtoDemoPlain(5, 6, 200, 300, 300, 299);        // y1 = y0 - 1
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 5, 5);
    }
    else if(ucGroup == 1)                               // gradients, QC tQCGRADIENT_POLITY rows
    {
        AwtoDemoGradient(1, 7, _OSD_WINDOW_GRADIENT_LEVEL_STEP_1, _OSD_WINDOW_GRADIENT_LEVEL_PER_1, _OSD_WINDOW_GRADIENT_DIRECTION_HORIZONTAL, 0, 0, 0, 0, 0, 0, 10, 10);
        AwtoDemoGradient(2, 7, _OSD_WINDOW_GRADIENT_LEVEL_STEP_2, _OSD_WINDOW_GRADIENT_LEVEL_PER_2, _OSD_WINDOW_GRADIENT_DIRECTION_HORIZONTAL, 0, 0, 1, 0, 0, 0, 200, 10);
        AwtoDemoGradient(3, 7, _OSD_WINDOW_GRADIENT_LEVEL_STEP_3, _OSD_WINDOW_GRADIENT_LEVEL_PER_3, _OSD_WINDOW_GRADIENT_DIRECTION_HORIZONTAL, 0, 0, 1, 0, 0, 1, 390, 10);
        AwtoDemoGradient(4, 7, _OSD_WINDOW_GRADIENT_LEVEL_STEP_4, _OSD_WINDOW_GRADIENT_LEVEL_PER_4, _OSD_WINDOW_GRADIENT_DIRECTION_VERTICAL, 0, 1, 0, 0, 0, 0, 10, 150);
        AwtoDemoGradient(5, 7, _OSD_WINDOW_GRADIENT_LEVEL_STEP_4, _OSD_WINDOW_GRADIENT_LEVEL_PER_5, _OSD_WINDOW_GRADIENT_DIRECTION_VERTICAL, 0, 1, 0, 0, 1, 0, 200, 150);
        AwtoDemoGradient(6, 7, _OSD_WINDOW_GRADIENT_LEVEL_STEP_4, _OSD_WINDOW_GRADIENT_LEVEL_PER_6, _OSD_WINDOW_GRADIENT_DIRECTION_VERTICAL, 0, 1, 1, 0, 0, 0, 390, 150);
        for(ucI = 1; ucI <= 6; ucI++)
        {
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 0x10 + ucI, ucI);
        }
    }
    else if(ucGroup == 2)                               // grid lines (QC ScalerQC_OSDWindowGridLine)
    {
        ScalerOsdDrawGridLinePanelPitch(993, 993);
        for(ucI = 0; ucI < 3; ucI++)
        {
            AwtoDemoReset();
            SET_OSD_WINDOW_COLOR(AWTO_DEMO_PAL + 3);
            SET_OSD_GRID_WINDOW_NUMBER(2 + ucI);
            SET_OSD_GRID_LINE_WIDTH(ucI);
            SET_OSD_GRID_LINE_COLOR(AWTO_DEMO_PAL + 4 + ucI);
            SET_OSD_GRID_LINE_HORIZONTAL_ENABLE(ucI != 1);
            SET_OSD_GRID_LINE_VERTICAL_ENABLE(ucI != 2);
            SET_OSD_GRID_LINE_OFFSET(3);
            SET_OSD_GRID_LINE_PITCH(10000);
            SET_OSD_GRID_LINE_FUNCTION_ENABLE(_ENABLE);
            ScalerOsdDrawGridLine();
            osd_tc_win_draw(2 + ucI, 20 + ucI * 190, 40, 20 + ucI * 190 + AWTO_DEMO_W, 40 + AWTO_DEMO_H);
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 0x20 + ucI, ucI);
        }
    }
    else if(ucGroup == 3)                               // shadow / border / 3D button types (QC ScalerQC_OSDWindowShadowBorder)
    {
        for(ucI = 0; ucI < 8; ucI++)
        {
            AwtoDemoReset();
            SET_OSD_WINDOW_COLOR(AWTO_DEMO_PAL + 7);
            SET_OSD_WINDOW_COLOR_SHADOW(AWTO_DEMO_PAL + 1);
            SET_OSD_WINDOW_COLOR_BORDER(AWTO_DEMO_PAL + 3);
            SET_OSD_WINDOW_SHADOW_BORDER_PIXEL_WIDTH(7 - ucI);
            SET_OSD_WINDOW_SHADOW_BORDER_PIXEL_HEIGHT(7 - ucI);
            SET_OSD_WINDOW_BUTTON_ENABLE(_ENABLE);
            SET_OSD_WINDOW_BUTTON_TYPE(ucI);
            osd_tc_win_draw(1 + ucI, 20 + (ucI & 3) * 140, 40 + (ucI >> 2) * 150, 20 + (ucI & 3) * 140 + 100, 40 + (ucI >> 2) * 150 + 100);
            AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 0x30 + ucI, ucI);
        }
    }
    else if(ucGroup == 4)                               // saturated / reversed gradient, overlapping windows (priority)
    {
        AwtoDemoGradient(1, 4, _OSD_WINDOW_GRADIENT_LEVEL_STEP_1, _OSD_WINDOW_GRADIENT_LEVEL_PER_1, _OSD_WINDOW_GRADIENT_DIRECTION_HORIZONTAL, 1, 1, 0, 0, 0, 0, 10, 10);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 0x41, 1);
        AwtoDemoGradient(2, 4, _OSD_WINDOW_GRADIENT_LEVEL_STEP_1, _OSD_WINDOW_GRADIENT_LEVEL_PER_1, _OSD_WINDOW_GRADIENT_DIRECTION_HORIZONTAL, 1, 1, 0, 0, 0, 0, 200, 10);
        SET_OSD_WINDOW_GRADIENT_SATURATED_COLOR_MODE(_ENABLE);
        osd_tc_win_draw(2, 200, 10, 200 + AWTO_DEMO_W, 10 + AWTO_DEMO_H);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 0x42, 2);
        AwtoDemoGradient(3, 4, _OSD_WINDOW_GRADIENT_LEVEL_STEP_1, _OSD_WINDOW_GRADIENT_LEVEL_PER_1, _OSD_WINDOW_GRADIENT_DIRECTION_HORIZONTAL, 1, 1, 0, 0, 0, 0, 390, 10);
        SET_OSD_WINDOW_GRADIENT_REVERSED_COLOR_MODE(_ENABLE);
        osd_tc_win_draw(3, 390, 10, 390 + AWTO_DEMO_W, 10 + AWTO_DEMO_H);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 0x43, 3);
        AwtoDemoPlain(4, 1, 40, 180, 240, 320);         // overlap: higher number on top?
        AwtoDemoPlain(5, 2, 140, 220, 340, 340);
        AwtoDemoPlain(6, 3, 240, 180, 440, 300);
        AwtoSyncPush(AWTO_SYNC_EV_ODEMO, 0x44, 4);
    }
}
