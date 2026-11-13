#include "UserCommonInclude.h"
#include <stddef.h>

// awto OSD screens on the text layer: diagnostic console, debug pop-up (#34), message cards (#124), source selector (#134),
// backlight bar (#132), key test (#39), GPIO table (#139), watchdog panel (#131), NVRAM flush line (#151).
#if(_OSD_TYPE == _REALTEK_2014_OSD)
//---- debug pop-up + shared text helpers ----
// Shared text layer for every awto diagnostic screen (debug lines, key test, GPIO inputs): ASCII rows composed in s_pcAwtoRow,
// drawn with the menu's Spleen cells (ui_text); the SDK proportional font is not used here.
#ifdef _AWTO_NEW_SETTINGS
extern void osd_tc_open(BYTE ucChars, BYTE ucLines, BYTE ucFont);
extern void osd_tc_bar(BYTE ucWin, WORD usX0, WORD usY0, WORD usX1, WORD usY1, BYTE ucColour);
extern void osd_tc_place(BYTE ucH, BYTE ucV, BYTE ucBig);
extern void osd_tc_place_corner(WORD usLeft, WORD usBottom, BYTE ucBig);
extern void osd_tc_close(void);
extern void menu_close(void);
extern void osd_font_load(BYTE ucFont);
extern BYTE ui_font_selected(void);
extern BYTE __xdata osd_cw;
extern BYTE __xdata osd_rh;
extern void osd_tc_viewport(BYTE ucRows);
extern BYTE osd_tc_scroll(BYTE ucFirst);
extern BYTE osd_font_glyph(char c);
extern void osd_tc_cells(BYTE ucRow, BYTE ucCell, BYTE __xdata *pucTiles, BYTE ucN, BYTE ucStyle);

#ifndef AWTO_HOLD_POPUP
#define AWTO_HOLD_POPUP     0x02                // same value as awto_testcmd.inc (another translation unit)
#endif
#define AWTO_T_MAXCOLS      118                 // widest text row: the console log (cols 1..118); probe clamped to this
#define AWTO_T_STYLE_TEXT   0
#define AWTO_T_STYLE_ONACC  2
#define AWTO_T_STYLE_ACCENT 3
#define AWTO_T_STYLE_ALERT  4                   // red: an input that is not in the I2C ring
__xdata BYTE g_ucAwtoProbeCols;                  // limit probe columns = 4 * (test cmd 0xC0 + n); 0 = 36
__xdata BYTE g_ucAwtoProbeLines;                 // limit probe line count (test cmd 0x80 + n); 0 = 24
__xdata BYTE g_ucAwtoDiagFont;                  // 0 = default (console Spleen 8x16, probe 5x8); else 1 + osd_font_load index (cmd 0x60 + n)
#define AwtoDiagFont(d)     ((g_ucAwtoDiagFont != 0) ? (g_ucAwtoDiagFont - 1) : (d))
static __xdata char s_pcAwtoRow[AWTO_T_MAXCOLS];  // #157: glyphs converted in place (no tile copy)
__xdata BYTE g_ucAwtoDiagSmall;                  // 0 = diagnostic screens at 2x size (default), 1 = 1x (test cmd 0x4B / 0x4A)
static BYTE s_ucAwtoLen;
static BYTE s_ucAwtoCols;
static __xdata _Bool s_bAwtoWrap;                         // main-page log line: a full row sets s_bAwtoOver (AwtoConWrapLine draws two rows)
static __xdata _Bool s_bAwtoOver;
static __xdata _Bool s_bAwtoSkip;                         // second pass of a wrapped line: the first s_ucLogI characters are dropped
static __xdata BYTE s_ucLogI;                   // GPIO page backfill: change-ring seq; host-time row: shift index; wrap: skip count

// One diagnostic console (AwtoDiagConsole), #144: 120 x 50 shown, Spleen 8x16 at 2x (1920 x 1836 px on the 4K panel).
// Pages: main (power-on, auto-open) = title + sync / power event log, full width; GPIO (#157) = input table + input changes.
// Main page = terminal: lines added at the bottom, the map rolls up (hardware roll-up). GPIO page: key test, debug,
// watchdog below the view (UP / DOWN scroll). Map 120 x 63: cols x rows + rows + 1 < 8192 (docs/osd.md).
#define AWTO_CON_COLS       120
#define AWTO_PANEL_ACTIVE_W_MM  597             // Innolux M280DCA-E3B active width (docs/monitors/panel-innolux-m280dca-e3b.md)
#define AWTO_CON_EDGE_MM    10                  // console box from the left and bottom edges (Dan 2026-11-13)
#define AWTO_CON_EDGE_PX    ((WORD)((DWORD)_PANEL_DH_WIDTH * AWTO_CON_EDGE_MM / AWTO_PANEL_ACTIVE_W_MM))   // 64 px
#define AWTO_CON_ROWS       62                  // map rows (+ the pad row AwtoTextOpen adds)
#define AWTO_VIEW_ROWS      50                  // rows shown at a time; UP / DOWN scroll the view over the map
#define AWTO_CON_FONT       0                   // osd_font_load index: Spleen 8x16 (8 x 18 cell)
#define AWTO_LOG_COL        ((s_ucConOpen == AWTO_CON_GPIO) ? 62 : 1)    // log pane: main page full width, GPIO page right of the table
#define AWTO_LOG_W_MAIN     (AWTO_T_MAXCOLS - 1)                     // main-page log row (cells, incl. the leading space)
#define AWTO_LOG_W          ((s_ucConOpen == AWTO_CON_GPIO) ? 57 : AWTO_LOG_W_MAIN)
#define AWTO_LOG_TIME_W     6                   // AwtoSyncLine time column "nnnnn:" (left padded)
#define AWTO_LOG_TXT0       (1 + AWTO_LOG_TIME_W)                   // text column: a wrapped line continues here (gen_awto_sync.py)
#define AWTO_LOG_HDR        2                   // heading row, then lines to the bottom of the view
#define AWTO_LOG_ROW0       (AWTO_LOG_HDR + 1)
#define AWTO_LOG_LINES      (AWTO_VIEW_ROWS - AWTO_LOG_ROW0)
#define AWTO_LOG_REDRAW_N   ((AWTO_CON_ROWS - AWTO_LOG_ROW0) / 2)   // lines a map-full redraw backfills (2 rows each at most)
static __xdata BYTE s_ucConOpen;                // 0 closed, else the page: AWTO_CON_MAIN / AWTO_CON_GPIO
static BYTE s_ucPanelCol;
static BYTE s_ucPanelRow;
static const __code BYTE tAwtoPanelCol[3] = {1, 1, 40};
static const __code BYTE tAwtoPanelRow[3] = {2, 52, 52};
static const __code BYTE tAwtoPanelW[3] = {60, 36, 36};

// The console owns the OSD only while its map is the one in place. A mode reset or an SDK pop-up replaces the map: then drawing
// (field writes at console positions) would corrupt that screen, so the console lets go (no OSD change) and returns 1.
static bit AwtoConLost(void)
{
    if((s_ucConOpen == 0) || ((g_ucOsdWidth == AWTO_CON_COLS) && (g_ucOsdHeight == AWTO_CON_ROWS + 1)))
    {
        return 0;
    }
    s_ucConOpen = 0;
    AwtoOsdRoll(0);                                                                            // the new map must not be shifted by our roll-up
    isr_g_stAwtoDiag.ucHold &= ~AWTO_HOLD_POPUP;
    AwtoGpioConSet(0);
    AwtoKeyConSet(0);
    return 1;
}

static __xdata BYTE s_ucConFirst;               // first map row shown (hardware roll-up)
static __xdata BYTE s_ucConRedraw;              // main page: map full, AwtoOsdSyncPoll redraws (next main-loop pass)

void AwtoConScroll(signed char cD)              // GPIO page UP / DOWN (main page scrolls itself, as a terminal)
{
    BYTE ucN;

    if((s_ucConOpen != AWTO_CON_GPIO) || (AwtoConLost() != 0))
    {
        return;
    }
    ucN = (cD < 0) ? ((s_ucConFirst != 0) ? (s_ucConFirst - 1) : 0) : (s_ucConFirst + 1);
    s_ucConFirst = osd_tc_scroll(ucN);
}

static void AwtoPanel(BYTE ucP)
{
    s_ucPanelCol = tAwtoPanelCol[ucP];
    s_ucPanelRow = tAwtoPanelRow[ucP];
    s_ucAwtoCols = tAwtoPanelW[ucP];
    s_pcAwtoRow[0] = ' ';
    s_ucAwtoLen = 1;
}

void AwtoOsdOfsInit(void)
{
    isr_g_stAwtoDiag.ucOsdOfsState = offsetof(StructOsdInfo, usOsdState);
    isr_g_stAwtoDiag.ucOsdOfsEvent = offsetof(StructOsdInfo, ucOsdEventMsg);
    isr_g_stAwtoDiag.ucOsdOfsKey = offsetof(StructOsdInfo, ucOsdKeyMessage);
}


// Grid + frame/surface windows (+ optional title bar), centred, 2x; the OSD stays off until AwtoTextShow.
static void AwtoTextOpen(BYTE ucCols, BYTE ucLines, BYTE ucView, bit bTitleBar)   // ucView: rows shown (0 = all, no scrolling)
{
    BYTE ucWin;

    ucLines++;
    ucWin = (ucView != 0) ? (ucView + 1) : ucLines;                         // one blank pad row: the frame border covers the last 2 px of a full-height row
    s_ucAwtoCols = ucCols;
    s_pcAwtoRow[0] = ' ';              // every row starts one cell in, clear of the frame
    s_ucAwtoLen = 1;
    osd_tc_open(ucCols, ucLines, AwtoDiagFont((ucView != 0) ? AWTO_CON_FONT : 3));     // console / probe font
    UserCommonInterfacePanelPowerTick();        // #162: map clear and font load are the long parts of a console open (boot,
                                                // wake): panel steps due meanwhile (T3, backlight-to-PWM) are not held up
    ScalerOsdSetColorPalette(AWTO_PAL_DIAG_TEXT, AWTO_RGB_PHOSPHOR_GREEN);       // diagnostic look: green on black, title bar reversed
    ScalerOsdSetColorPalette(AWTO_PAL_DIAG_DIM, AWTO_RGB_PHOSPHOR_DIM);
    ScalerOsdSetColorPalette(AWTO_PAL_DIAG_BG, AWTO_RGB_BLACK);
    ScalerOsdSetColorPalette(AWTO_PAL_DIAG_ALERT, AWTO_RGB_ALERT_RED);
    UserCommonInterfacePanelPowerTick();
    if(ucView != 0)
    {
        osd_tc_viewport(ucWin);
    }
    osd_tc_bar(0, 0, 0, (WORD)ucCols * osd_cw - 1, (WORD)ucWin * osd_rh - 1, 1);   // frame (accent)
    osd_tc_bar(1, 2, 2, (WORD)ucCols * osd_cw - 3, (WORD)ucWin * osd_rh - 3, 0);  // surface
    if(bTitleBar != 0)
    {
        osd_tc_bar(2, 2, 2, (WORD)ucCols * osd_cw - 3, osd_rh - 1, 1);              // one row high title bar
    }
    osd_tc_place_corner(AWTO_CON_EDGE_PX, AWTO_CON_EDGE_PX, (g_ucAwtoDiagSmall == 0) ? 1 : 0);   // lower left (Dan 2026-11-13)
}

static void AwtoTextShow(void)
{
    OsdFuncEnableOsd();                // not osd_tc_show: that would flag the settings menu as open
}

static void AwtoPutChar(char c)
{
    if(s_bAwtoSkip != 0)
    {
        if(--s_ucLogI == 0)
        {
            s_bAwtoSkip = 0;
        }
    }
    else if(s_ucAwtoLen < s_ucAwtoCols)
    {
        s_pcAwtoRow[s_ucAwtoLen++] = c;
    }
    else if(s_bAwtoWrap != 0)
    {
        s_bAwtoOver = 1;
    }
}

static void AwtoPutCol(BYTE ucCol)
{
    while(s_ucAwtoLen < ucCol)
    {
        AwtoPutChar(' ');
    }
}

static void AwtoPutStr(const char *s)
{
    while(*s != 0)
    {
        AwtoPutChar(*s++);
    }
}

// Digits low first into the row, then reversed in place: no digit buffer (10 B XDATA), no extra local (deep DATA path).
static void AwtoPutNum(unsigned long ulV, BYTE ucMin)
{
    BYTE ucN = s_ucAwtoLen;

    do                                          // ucMin counts the digits put (not the row length: a skipped pass drops them)
    {
        AwtoPutChar('0' + (ulV % 10));
        ulV /= 10;
        if(ucMin != 0)
        {
            ucMin--;
        }
    }
    while(ulV != 0);
    for(; ucMin != 0; ucMin--)
    {
        AwtoPutChar('0');
    }
    for(ucMin = s_ucAwtoLen; (BYTE)(ucN + 1) < ucMin; ucN++)
    {
        ucMin--;
        s_pcAwtoRow[ucN] ^= s_pcAwtoRow[ucMin];
        s_pcAwtoRow[ucMin] ^= s_pcAwtoRow[ucN];
        s_pcAwtoRow[ucN] ^= s_pcAwtoRow[ucMin];
    }
}

static void AwtoPutHex2(BYTE ucV)
{
    AwtoPutChar("0123456789ABCDEF"[ucV >> 4]);
    AwtoPutChar("0123456789ABCDEF"[ucV & 15]);
}

// ulV in thousandths -> "int.ddd" (#34: every frequency with 3 decimals)
static void AwtoPutMilli(unsigned long ulV)
{
    AwtoPutNum(ulV / 1000, 1);
    AwtoPutChar('.');
    AwtoPutNum(ulV % 1000, 3);
}

static void AwtoPutVolt(BYTE ucRaw)                 // 8 bit ADC code on a 3.3 V reference
{
    AwtoPutMilli(((unsigned long)ucRaw * 3300 + 127) / 255);
    AwtoPutChar('V');
}

// Generic text write: ucN characters of pc at map row ucRow, column ucCol. pc is overwritten with the glyph ids.
static void AwtoTextAt(BYTE ucRow, BYTE ucCol, char __xdata *pc, BYTE ucN, BYTE ucStyle)
{
    BYTE ucI;

    for(ucI = 0; ucI < ucN; ucI++)
    {
        pc[ucI] = osd_font_glyph(pc[ucI]);
    }
    osd_tc_cells(ucRow, ucCol, (BYTE __xdata *)pc, ucN, ucStyle);
}

// Draw the composed row on text line ucLine, padded to the full width so the previous text of that line is overwritten.
static void AwtoTextLine(BYTE ucLine, BYTE ucStyle)
{
    AwtoPutCol(s_ucAwtoCols);
    AwtoTextAt(s_ucPanelRow + ucLine, s_ucPanelCol, s_pcAwtoRow, s_ucAwtoCols, ucStyle);
    s_pcAwtoRow[0] = ' ';              // next row: leading space (the draw left glyph ids)
    s_ucAwtoLen = 1;
}

// Stack canary hit (AwtoStackCheck, awto_wdt.inc): a small red box, nothing else drawn after it.
#define AWTO_FATAL_COLS     30
#define AWTO_FATAL_LINES    2
void AwtoStackFatal(BYTE ucHigh)
{
    AwtoTextOpen(AWTO_FATAL_COLS, AWTO_FATAL_LINES, 0, 0);
    s_ucPanelRow = 0;
    s_ucPanelCol = 0;
    AwtoPutStr("Fatal error: Stack Error!!");
    AwtoTextLine(0, AWTO_T_STYLE_ALERT);
    AwtoPutStr("SP high 0x");
    AwtoPutHex2(ucHigh);
    AwtoPutStr(" guard 0x");
    AwtoPutHex2(AWTO_STACK_GUARD);
    AwtoTextLine(1, AWTO_T_STYLE_ALERT);
    AwtoTextShow();
}

// Field update: text composed with AwtoPut* since AwtoFieldBegin is written at exactly row ucRow, column ucCol (nothing else touched).
static void AwtoFieldBegin(void)
{
    s_ucAwtoLen = 0;
}

static void AwtoFieldEnd(BYTE ucRow, BYTE ucCol, BYTE ucStyle)
{
    AwtoTextAt(s_ucPanelRow + ucRow, s_ucPanelCol + ucCol, s_pcAwtoRow, s_ucAwtoLen, ucStyle);
    s_pcAwtoRow[0] = ' ';              // rows start with the leading space the field just overwrote
    s_ucAwtoLen = 1;
}

// Pop-up rows keep their SDK message-card row numbers: row _OSD_MESSAGE_ROW_START + n is text line n + 1 (line 0 = title).
static void AwtoShowLine(BYTE ucRow, BYTE ucPage)
{
    ucPage = ucPage;
    AwtoTextLine(ucRow - _OSD_MESSAGE_ROW_START + 1, AWTO_T_STYLE_TEXT);
}

// Rotate-xor hash of s_pcAwtoRow[ucFrom..ucTo): "did this text change" without a copy of it (XDATA).
static BYTE AwtoRowHash(BYTE ucFrom, BYTE ucTo)
{
    BYTE ucH = ucTo - ucFrom;

    while(ucFrom < ucTo)
    {
        ucH = (BYTE)((ucH << 3) | (ucH >> 5)) ^ (BYTE)s_pcAwtoRow[ucFrom++];
    }
    return ucH;
}

// Debug panel (#157): a row is written only when its text changed (hash per row); below the view only on the console open.
static __xdata BYTE s_pucDbgH[5];
static __xdata BYTE s_ucDbgAll;                 // 1 = draw every row (console open)

static void AwtoDbgShow(BYTE ucRow, BYTE ucPage)
{
    BYTE ucN = ucRow - _OSD_MESSAGE_ROW_START;
    BYTE ucH = AwtoRowHash(0, s_ucAwtoLen);

    if((s_ucDbgAll == 0) && (ucH == s_pucDbgH[ucN]))
    {
        s_pcAwtoRow[0] = ' ';
        s_ucAwtoLen = 1;
        return;
    }
    s_pucDbgH[ucN] = ucH;
    AwtoShowLine(ucRow, ucPage);
}

void AwtoOsdDebugLines(void)
{
    BYTE ucPort, ucMode, ucPwr;
    WORD usV;                                      // 0.1 Hz

    if(s_ucConOpen == 0)
    {
        AwtoDiagConsole(1);            // an SDK-triggered debug pop-up opens the console (which draws this panel)
        return;
    }
    if(AwtoConLost() != 0) return;
    isr_g_stAwtoDiag.ucDbgPopup = 0;
    if((s_ucConOpen != AWTO_CON_GPIO) || ((s_ucDbgAll == 0) && (s_ucConFirst + AWTO_VIEW_ROWS <= tAwtoPanelRow[2])))
    {
        return;                        // main page has no panel; below the view: the next refresh after a scroll
    }
    ucPort = SysSourceGetInputPort();
    ucMode = SysModeGetModeState();
    ucPwr = SysPowerGetPowerStatus();
    usV = GET_INPUT_TIMING_VFREQ();
    AwtoPanel(2);
    if(s_ucDbgAll != 0)
    {
        AwtoPutCol(1);
        AwtoPutStr("DEBUG");
        AwtoTextLine(0, AWTO_T_STYLE_ACCENT);
    }

    AwtoPutStr((ucPort >= _D0_PORT) ? "D" : "A");
    AwtoPutNum((ucPort >= _D0_PORT) ? (ucPort - _D0_PORT) : 0, 1);
    AwtoPutStr(" ");
    AwtoPutNum(GET_INPUT_TIMING_HWIDTH(), 1);
    AwtoPutStr("x");
    AwtoPutNum(GET_INPUT_TIMING_VHEIGHT(), 1);
    AwtoPutStr(" ");
    if(g_stAwtoFreq.ucValid != 0)
    {
        AwtoPutMilli(g_stAwtoFreq.ulVFreqmHz);
    }
    else
    {
        AwtoPutNum(usV / 10, 1);      // SDK 0.1 Hz value: no exact count yet
        AwtoPutStr(".");
        AwtoPutNum(usV % 10, 1);
    }
    AwtoPutStr("Hz");
    AwtoDbgShow(_OSD_MESSAGE_ROW_START, _PFONT_PAGE_0);

    AwtoPutStr(ucMode == _MODE_STATUS_ACTIVE ? "ACTIVE" : (ucMode == _MODE_STATUS_NOSIGNAL ? "NOSIG" : (ucMode == _MODE_STATUS_POWER_SAVING ? "PSAVE" : "MODE")));
    AwtoPutStr(" ");
    AwtoPutNum(ucMode, 1);
    AwtoPutStr("  PWR ");
    AwtoPutStr(ucPwr == _POWER_STATUS_NORMAL ? "ON" : (ucPwr == _POWER_STATUS_SAVING ? "SAVE" : (ucPwr == _POWER_STATUS_OFF ? "OFF" : "AC")));
    AwtoPutNum(ucPwr, 1);
    AwtoDbgShow(_OSD_MESSAGE_ROW_START + 1, _PFONT_PAGE_1);

    if(g_stAwtoFreq.ucValid != 0)
    {
        AwtoPutStr("PCLK ");
        AwtoPutMilli(g_stAwtoFreq.ulPclkHz / 1000);
        AwtoPutStr(" ");
    }
    AwtoPutStr("DCLK ");
    AwtoPutMilli(GET_D_CLK_FREQ());               // kHz
    AwtoDbgShow(_OSD_MESSAGE_ROW_START + 2, _PFONT_PAGE_2);

    AwtoPutStr("LOOP ");
    AwtoPutNum(isr_g_stAwtoDiag.usLoopRate, 1);
    AwtoPutStr("/s");
    if(g_stAwtoFreq.ucValid != 0)
    {
        AwtoPutStr("  H ");
        AwtoPutMilli(g_stAwtoFreq.ulHFreqHz);
        AwtoPutStr("kHz");
    }
    AwtoDbgShow(_OSD_MESSAGE_ROW_START + 3, _PFONT_PAGE_0);

    AwtoPutStr("FW ");
    AwtoPutStr(AWTO_FW_TAG);
    AwtoDbgShow(_OSD_MESSAGE_ROW_START + 4, _PFONT_PAGE_1);
    s_ucDbgAll = 0;
}

// #157 title row live part: "PANEL 0027.25h  UP 0000.42h  HOST 08:45:10" (+ " STALE"); s_pucConTitleH = hash per 2 cells on screen.
#define AWTO_TITLE_COL      70                  // after " AWTO DIAGNOSTICS  FW <tag>  <port>  SN <serial>" (tags up to ~21 characters)
#define AWTO_TITLE_N        48
static __xdata BYTE s_pucConTitleH[AWTO_TITLE_N / 2];
static __xdata WORD s_usConTitleMs;

// Time formatters keep their values in XDATA: they sit on the deepest DATA overlay path (flash save -> sync line).
static __xdata DWORD s_ulAwtoT;                 // AwtoPutClock input: seconds of the day

static void AwtoPutClock(void)                  // s_ulAwtoT -> hh:mm:ss
{
    AwtoPutNum(s_ulAwtoT / 3600, 2);
    AwtoPutChar(':');
    AwtoPutNum((s_ulAwtoT / 60) % 60, 2);
    AwtoPutChar(':');
    AwtoPutNum(s_ulAwtoT % 60, 2);
}

static void AwtoPutHours(DWORD ulH100)          // hundredths of an hour -> hour meter "0027.25h"
{
    AwtoPutNum(ulH100 / 100, 4);
    AwtoPutChar('.');
    AwtoPutNum(ulH100 % 100, 2);
    AwtoPutChar('h');
}

static void AwtoConTitle(BYTE ucAll)            // compose; draw the runs of 2-cell groups that changed (ucAll: every cell)
{
    DWORD ulUp = AwtoMs();
    BYTE ucI, ucJ, ucH;

    s_usConTitleMs = (WORD)ulUp;
    s_ucAwtoCols = AWTO_TITLE_N;
    AwtoFieldBegin();
    AwtoPutStr("PANEL ");
    AwtoPutHours((DWORD)GET_PANEL_TIME_HOUR() * 100 + (WORD)GET_PANEL_TIME_MIN() * 100 / 60);
    AwtoPutStr("  UP ");
    AwtoPutHours(ulUp / 36000);
    AwtoPutStr("  HOST ");
    if(isr_g_stAwtoHt.ucSyncs == 0)
    {
        AwtoPutStr("--:--:--");
    }
    else
    {
        s_ulAwtoT = (isr_g_stAwtoHt.ulEpoch + (long)isr_g_stAwtoHt.cOfs * 900 + (ulUp - isr_g_stAwtoHt.ulFwMs + isr_g_stAwtoHt.usFrac) / 1000) % 86400;
        AwtoPutClock();
        if((ulUp - isr_g_stAwtoHt.ulFwMs) > AWTO_HT_STALE_MS)
        {
            AwtoPutStr(" STALE");
        }
    }
    AwtoPutCol(AWTO_TITLE_N);
    for(ucI = 0; ucI < AWTO_TITLE_N; ucI = ucJ)
    {
        for(ucJ = ucI; ucJ < AWTO_TITLE_N; ucJ += 2)    // hash before the draw: AwtoTextAt turns the run into glyph ids
        {
            ucH = AwtoRowHash(ucJ, ucJ + 2);
            if((ucAll == 0) && (ucH == s_pucConTitleH[ucJ >> 1]))
            {
                break;
            }
            s_pucConTitleH[ucJ >> 1] = ucH;
        }
        if(ucJ != ucI)
        {
            AwtoTextAt(s_ucConFirst, AWTO_TITLE_COL + ucI, s_pcAwtoRow + ucI, ucJ - ucI, AWTO_T_STYLE_ONACC);
        }
        else
        {
            ucJ += 2;
        }
    }
    s_pcAwtoRow[0] = ' ';
    s_ucAwtoLen = 1;
}

void AwtoConTitlePoll(void)                     // every pass while the console is open (AwtoOsdSyncPoll)
{
    WORD usNow;

    usNow = (WORD)AwtoMs();
    if(((WORD)(usNow - s_usConTitleMs) < AWTO_TITLE_MS) || (s_ucConOpen != AWTO_CON_MAIN) || (AwtoConLost() != 0))
    {
        return;
    }
    AwtoConTitle(0);
}

// Title row at the top of the view (map row s_ucConFirst): the title bar window is fixed on screen, the map rolls under it.
static void AwtoPortName(BYTE ucPort);          // source selector section

// Title serial: the EDID of the port in use, descriptor tag 0xFF (up to 13 characters, 0x0A ends it); '-' if none.
// XDATA, no locals: AwtoConTitleBar also runs under AwtoConLogSync (deep DATA path); inline (no new stub in full common).
static __xdata BYTE s_ucAwtoSnI, s_ucAwtoSnJ;
static BYTE __xdata *__xdata s_pucAwtoSn;

static void AwtoConTitleBar(void)
{
    s_ucAwtoCols = AWTO_T_MAXCOLS;              // covers a log row (cols 1..AWTO_T_MAXCOLS - 1) rolled under it
    s_ucPanelCol = 0;
    s_ucPanelRow = s_ucConFirst;
    s_ucAwtoLen = 1;
    if(s_ucConOpen == AWTO_CON_GPIO)            // own screen, menu "GPIO inputs" only (Dan 2026-11-12)
    {
        AwtoPutStr("GPIO INPUTS  FW ");
        AwtoPutStr(AWTO_FW_TAG);
        AwtoTextLine(0, AWTO_T_STYLE_ONACC);
        return;
    }
    AwtoPutStr(" AWTO DIAGNOSTICS  FW ");      // Dan 2026-11-13: a space before AWTO, the port in use and the serial
    AwtoPutStr(AWTO_FW_TAG);
    AwtoPutStr("  ");
    AwtoPortName(SysSourceGetInputPort());
    AwtoPutStr("  SN ");
    s_pucAwtoSn = (SysSourceGetInputPort() == _D1_INPUT_PORT) ? MCU_DDCRAM_D1 : (SysSourceGetInputPort() == _D3_INPUT_PORT) ? MCU_DDCRAM_D3 : MCU_DDCRAM_D2;
    for(s_ucAwtoSnI = 54; s_ucAwtoSnI <= 108; s_ucAwtoSnI += 18)        // the four 18-byte descriptors of the base block
    {
        if((s_pucAwtoSn[s_ucAwtoSnI] == 0) && (s_pucAwtoSn[s_ucAwtoSnI + 1] == 0) && (s_pucAwtoSn[s_ucAwtoSnI + 3] == 0xFF))
        {
            break;
        }
    }
    for(s_ucAwtoSnJ = 5; (s_ucAwtoSnI <= 108) && (s_ucAwtoSnJ < 18) && (s_pucAwtoSn[s_ucAwtoSnI + s_ucAwtoSnJ] != 0x0A); s_ucAwtoSnJ++)
    {
        AwtoPutChar(s_pucAwtoSn[s_ucAwtoSnI + s_ucAwtoSnJ]);
    }
    AwtoTextLine(0, AWTO_T_STYLE_ONACC);
    AwtoConTitle(1);
}

// The console: 0 close, AWTO_CON_MAIN / AWTO_CON_GPIO open that page (another page open: drawn anew), 2 toggle the main page.
void AwtoDiagConsole(BYTE ucOn)
{
    if(ucOn == 2)
    {
        ucOn = (s_ucConOpen == 0) ? AWTO_CON_MAIN : 0;
    }
    if(ucOn == s_ucConOpen)
    {
        return;
    }
    isr_g_stAwtoDiag.ucHold &= ~AWTO_HOLD_POPUP;       // before the disable: a hold blocks it
    if(ucOn != 0)
    {
        menu_close();
        OsdDispDisableOsd();
        s_ucConOpen = ucOn;
        isr_g_stAwtoDiag.ucHold |= AWTO_HOLD_POPUP;
        AwtoGpioConSet(ucOn);
        AwtoKeyConSet(ucOn == AWTO_CON_GPIO);   // key test / debug / watchdog panels: GPIO page only (main page = terminal)
        AwtoTextOpen(AWTO_CON_COLS, AWTO_CON_ROWS, AWTO_VIEW_ROWS, 1);
        s_ucConFirst = 0;
        AwtoConTitleBar();
        if(ucOn == AWTO_CON_GPIO)
        {
            AwtoOsdGpioLines();
            g_stAwtoKey.ucDrawn = 0;
            AwtoOsdKeyLines();
            s_ucDbgAll = 1;
            AwtoOsdDebugLines(); AwtoOsdWdtLines();     // #131 watchdog panel
        }
        AwtoConLogInit();
        s_ucConRedraw = 0;                      // after the backfill: AwtoConLogInit caps a map-full redraw
        UserCommonInterfacePanelPowerTick();
        AwtoTextShow();
    }
    else
    {
        s_ucConOpen = 0;
        s_ucConRedraw = 0;
        AwtoGpioConSet(0);
        AwtoKeyConSet(0);
        osd_tc_close();
    }
}

// Limit probe / generic console (test cmd 0x45 open, 0x46 close, 0x80 + n lines, 0xC0 + n columns = 4 * n, 0x47 / 0x48 hardware scroll
// step / reset): cols x lines numbered rows in the font chosen with cmd 0x60 + font. Rows go straight to the cell map (osd_tc_cells).
static __xdata BYTE s_ucAwtoProbeOpen;
static __xdata BYTE s_ucAwtoScroll;
static __xdata BYTE s_ucAwtoConCols;
static __xdata BYTE s_ucAwtoConRows;

static void AwtoConRow(BYTE ucR, BYTE ucCols, BYTE ucStyle)
{
    BYTE ucC, ucI;

    for(ucC = 0; ucC < ucCols; ucC++)
    {
        if(ucC == 0) ucI = ' ';
        else if(ucC == 1) ucI = '0' + (ucR / 10) % 10;
        else if(ucC == 2) ucI = '0' + ucR % 10;
        else if(ucC == 3) ucI = ' ';
        else
        {
            ucI = (ucR + ucC) % 36;
            ucI = (ucI < 10) ? ('0' + ucI) : ('A' + ucI - 10);
        }
        s_pcAwtoRow[ucC] = osd_font_glyph(ucI);
    }
    osd_tc_cells(ucR, 0, (BYTE __xdata *)s_pcAwtoRow, ucCols, ucStyle);
}

void AwtoProbeSet(BYTE ucLines)
{
    BYTE ucR;
    BYTE ucCols = (g_ucAwtoProbeCols != 0) ? g_ucAwtoProbeCols : 36;

    if(ucCols > AWTO_T_MAXCOLS) ucCols = AWTO_T_MAXCOLS;

    if(ucLines == 0)
    {
        if(s_ucAwtoProbeOpen != 0)
        {
            s_ucAwtoProbeOpen = 0;
            isr_g_stAwtoDiag.ucHold &= ~AWTO_HOLD_POPUP;
            osd_tc_close();
        }
        return;
    }
    menu_close();
    AwtoKeyTestSet(0);
    AwtoGpioTestSet(0);
    OsdDispDisableOsd();
    s_ucAwtoProbeOpen = 1;
    s_ucAwtoScroll = 0;
    s_ucAwtoConCols = ucCols;
    s_ucAwtoConRows = ucLines + 1;
    isr_g_stAwtoDiag.ucHold |= AWTO_HOLD_POPUP;
    AwtoTextOpen(ucCols, ucLines, 0, 1);
    for(ucR = 0; ucR < ucLines; ucR++)
    {
        AwtoConRow(ucR, ucCols, (ucR == 0) ? AWTO_T_STYLE_ONACC : AWTO_T_STYLE_TEXT);
    }
    AwtoTextShow();
}

// Hardware roll-up experiment (regdb 0x3A18 bit7 special enable, bit6 = 0 roll-up; 0x3A19 row base 0, 0x3A1B/0x3A1C font select base 0):
// start the displayed map one row further down per step.
void AwtoProbeScroll(BYTE ucReset)
{
    if(s_ucAwtoProbeOpen == 0) return;
    s_ucAwtoScroll = (ucReset != 0) ? 0 : (s_ucAwtoScroll + 1);
    AwtoOsdRoll(1);
    ScalerSetByte(AWTO_R_FRAME_CTRL_19, s_ucAwtoScroll);
    ScalerSetBit(AWTO_R_FRAME_CTRL_1B, (BYTE)~AWTO_F_FRAME_CTRL_1B_FS_BASE0, (BYTE)(((g_usFontSelectStart + (WORD)s_ucAwtoScroll * s_ucAwtoConCols) >> 8) << 4));
    ScalerSetByte(AWTO_R_FRAME_CTRL_1C, (BYTE)(g_usFontSelectStart + (WORD)s_ucAwtoScroll * s_ucAwtoConCols));
}
#else
void AwtoOsdOfsInit(void)
{
    isr_g_stAwtoDiag.ucOsdOfsState = offsetof(StructOsdInfo, usOsdState);
    isr_g_stAwtoDiag.ucOsdOfsEvent = offsetof(StructOsdInfo, ucOsdEventMsg);
    isr_g_stAwtoDiag.ucOsdOfsKey = offsetof(StructOsdInfo, ucOsdKeyMessage);
}

void AwtoOsdDebugLines(void)
{
    isr_g_stAwtoDiag.ucDbgPopup = 0;
}

void AwtoDiagConsole(BYTE ucOn)
{
    (void)ucOn;
}

void AwtoProbeSet(BYTE ucLines)
{
    (void)ucLines;
}

void AwtoProbeScroll(BYTE ucReset)
{
    (void)ucReset;
}
#endif

//---- user-facing screens: SDK timers and OSD states drive them as before; only the drawing is ours ----
// - Message cards (#124): OsdDispOsdMessage (the SDK body is removed by keil2sdcc), incl. the ACTIVE input-info card.
// - Source selector (#134): one row per board port + Auto. Backlight bar (#132): UP / DOWN with a picture.
#if(!defined(_AWTO_NEW_SETTINGS))
#error "console.c draws on the awto text layer (_AWTO_NEW_SETTINGS)"
#endif
#if((_FREEZE_SUPPORT == _ON) || (_DP_MST_SUPPORT == _ON))
#error "console.c: no card text for the freeze / DP MST messages"
#endif

// Board ports from the PCB config (type = port << 4 | kind). ui_port_state (fw/settings/settings_glue.c) knows D1..D3 only.
#if((_D0_INPUT_PORT_TYPE != _D0_NO_PORT) || (_D4_INPUT_PORT_TYPE != _D4_NO_PORT) || (_D5_INPUT_PORT_TYPE != _D5_NO_PORT) || (_D6_INPUT_PORT_TYPE != _D6_NO_PORT))
#error "source selector: ui_port_state covers D1..D3 only"
#endif
extern BYTE ui_port_state(BYTE ucI);
static const __code BYTE tAwtoSrcType[] = {
#if(_D1_INPUT_PORT_TYPE != _D1_NO_PORT)
    _D1_INPUT_PORT_TYPE,
#endif
#if(_D2_INPUT_PORT_TYPE != _D2_NO_PORT)
    _D2_INPUT_PORT_TYPE,
#endif
#if(_D3_INPUT_PORT_TYPE != _D3_NO_PORT)
    _D3_INPUT_PORT_TYPE,
#endif
};
#define AWTO_SRC_PORTS      ((BYTE)sizeof(tAwtoSrcType))
#define AWTO_CARD_COLS      28                  // text cells per card row
#define AWTO_CARD_ROW0      2                   // first body row: title, one blank row, then the body
#define AWTO_SRC_STATE_COL  15                  // selector: port state column
#define AWTO_SRC_ROW0       AWTO_CARD_ROW0
#define AWTO_INFO_VAL_COL   13                  // info card: value column
#define AWTO_WIN_FRAME      0                   // window ids as the awto menu (awto-rtdfw ui.c)
#define AWTO_WIN_INSET      1
#define AWTO_WIN_TITLE      2
#define AWTO_WIN_HL         5
#define AWTO_T_STYLE_DIM    1
#define AWTO_BAR_SURFACE    0                   // osd_tc_bar colours = awto-rtdfw osd.h AWTO_BAR_SURFACE / AWTO_BAR_ACCENT
#define AWTO_BAR_ACCENT     1

// Fixed texts: one table, read only by AwtoCardTxt (a constant read through a pointer sits in its reader's bank, awto-sdcc#39).
#define AWTO_CT_INPUT       0
#define AWTO_CT_AUTO        1
#define AWTO_CT_DP          2
#define AWTO_CT_HDMI        3
#define AWTO_CT_PORT        4
#define AWTO_CT_STATE       5                   // + ui_port_state: no cable, no signal, ready, ACTIVE
#define AWTO_UPS_DISABLED   4                   // ui_port_state: off by setting (awto-rtdfw ui.h UPS_DISABLED)
#define AWTO_CT_AWTO        9
#define AWTO_CT_NOSIGNAL    10
#define AWTO_CT_NOCABLE     11
#define AWTO_CT_NOSUPPORT   12
#define AWTO_CT_AUTOADJ     13
#define AWTO_CT_AUTOCOL     14
#define AWTO_CT_DDCCI       15
#define AWTO_CT_PSAVE       16
#define AWTO_CT_PANEL       17
#define AWTO_CT_ON          18                  // + 1 = Off
#define AWTO_CT_INFO        20
#define AWTO_CT_RES         21
#define AWTO_CT_REFRESH     22
#define AWTO_CT_HFREQ       23
#define AWTO_CT_PCLK        24
#define AWTO_CT_HDCP        25
#define AWTO_CT_DPLINK      26
#define AWTO_CT_SWING       27
#define AWTO_CT_STATUS      28
#define AWTO_CT_HZ          29                  // + 1 kHz, + 2 MHz
#define AWTO_CT_OFF         32
#define AWTO_CT_SINK        33                  // + 1 = repeater
#define AWTO_CT_LANES       35
#define AWTO_CT_RBR         36                  // + 1 HBR, + 2 HBR2
#define AWTO_CT_STAGE       39                  // + AWTO_SYNC_ST_* (#139)
#define AWTO_CT_HBR3        53
#define AWTO_CT_SYNCLOG     54
#define AWTO_CT_NOLINK      55
#define AWTO_CT_TMDS        56
#define AWTO_CT_SAVING      57
#define AWTO_CT_BACKLIGHT   58
#define AWTO_CT_DISABLED    59                  // selector state of a port off by setting (#81; ui_port_state 4)
static const __code char tAwtoCardS[] =
    "Input\0Auto select\0DP-1\0HDMI-\0Input D\0no cable\0no signal\0ready\0ACTIVE\0"
    "AWTO\0No signal\0No cable\0Not supported\0Auto adjust\0Auto colour\0DDC/CI on \0Power saving\0Panel uniformity\0On\0Off\0"
    "Information\0Resolution\0Refresh\0H frequency\0Pixel clock\0HDCP\0DP link\0Swing/pre\0Status\0"
    " Hz\0 kHz\0 MHz\0off\0 sink\0 repeater\0 lanes \0RBR\0HBR\0HBR2\0"
    "idle\0search\0scan\0stable\0measure\0timing ok\0display set\0active\0no signal\0no support\0sleep\0off\0fast path\0init\0"
    "HBR3\0Sync log\0no link\0TMDS \0Saving to memory\0Backlight\0disabled\0";

static void AwtoCardTxt(BYTE ucI)               // appends text ucI to the composed row (AwtoPut*)
{
    const __code char *pc = tAwtoCardS;

    while(ucI != 0)
    {
        if(*pc++ == 0)
        {
            ucI--;
        }
    }
    while(*pc != 0)
    {
        AwtoPutChar(*pc++);
    }
}

// Card frame in the awto menu look (blue frame + title bar on white, the menu font), centred, title drawn; the OSD stays off.
static void AwtoCardOpenW(BYTE ucCols, BYTE ucLines, BYTE ucTitle)
{
    WORD usW, usH;

    osd_tc_open(ucCols, ucLines, ui_font_selected());
    usW = (WORD)ucCols * osd_cw;
    usH = (WORD)ucLines * osd_rh;
    osd_tc_bar(AWTO_WIN_FRAME, 0, 0, usW - 1, usH - 1, 1);
    osd_tc_bar(AWTO_WIN_INSET, 2, 2, usW - 3, usH - 3, 0);
    osd_tc_bar(AWTO_WIN_TITLE, 2, 2, usW - 3, osd_rh - 1, 1);
    osd_tc_place(50, 50, GET_OSD_NVRAM_DOUBLE_SIZE());
    s_ucPanelRow = 0;
    s_ucPanelCol = 0;
    s_ucAwtoCols = ucCols;
    s_pcAwtoRow[0] = ' ';
    s_ucAwtoLen = 1;
    AwtoCardTxt(ucTitle);
    AwtoTextLine(0, AWTO_T_STYLE_ONACC);
}

static void AwtoCardOpen(BYTE ucLines, BYTE ucTitle)
{
    AwtoCardOpenW(AWTO_CARD_COLS, ucLines, ucTitle);
}

static void AwtoCardShow(void)
{
    ScalerTimerWaitForEvent(_EVENT_DEN_STOP);
    OsdFuncEnableOsd();                         // not osd_tc_show: that would flag the awto menu as open
}

static void AwtoCardCentre(BYTE ucLine, BYTE ucStyle)   // the composed text, centred on the row
{
    BYTE ucN = s_ucAwtoLen - 1;
    BYTE ucShift = (ucN < AWTO_CARD_COLS - 1) ? ((AWTO_CARD_COLS - ucN) / 2 - 1) : 0;
    BYTE ucI;

    for(ucI = ucN; ucI != 0; ucI--)
    {
        s_pcAwtoRow[ucI + ucShift] = s_pcAwtoRow[ucI];
    }
    for(ucI = 1; ucI <= ucShift; ucI++)
    {
        s_pcAwtoRow[ucI] = ' ';
    }
    s_ucAwtoLen = ucN + 1 + ucShift;
    AwtoTextLine(ucLine, ucStyle);
}

//---- source selector (#134) ----
static BYTE AwtoSrcPort(BYTE ucI)               // selector row 1..n -> input port
{
    return tAwtoSrcType[ucI - 1] >> 4;
}

static BYTE AwtoSrcItem(BYTE ucPort)            // input port -> OSD input item (_OSD_INPUT_D*)
{
    return ucPort - _D0_INPUT_PORT + _OSD_INPUT_D0;
}

static BYTE AwtoSrcItemPort(BYTE ucItem)        // OSD input item -> port byte of the ring line (0xFF = Auto)
{
    return (ucItem == _OSD_INPUT_AUTO) ? 0xFF : (ucItem - _OSD_INPUT_D0 + _D0_INPUT_PORT);
}

static void AwtoSrcRing(BYTE ucEv, BYTE ucItem)  // one ring line per selector outcome (#132): AWTO_SEL_EV_*
{
    AwtoSyncPush(AWTO_SYNC_EV_SEL, ucEv, AwtoSrcItemPort(ucItem));
}

static BYTE AwtoSrcSel(void)                    // OSD input item -> selector row (0 = Auto)
{
    BYTE ucI;

    for(ucI = 1; ucI <= AWTO_SRC_PORTS; ucI++)
    {
        if(AwtoSrcItem(AwtoSrcPort(ucI)) == GET_OSD_INPUT_PORT_OSD_ITEM())
        {
            return ucI;
        }
    }
    return 0;
}

static void AwtoPortName(BYTE ucPort)          // "DP-1", "HDMI-n" (n-th HDMI port of the board), else "Input Dn" (Dan, 2026-11-12)
{
    BYTE ucI, ucHdmi = 0;

    for(ucI = 1; ucI <= AWTO_SRC_PORTS; ucI++)
    {
        if((tAwtoSrcType[ucI - 1] & 0x0F) == _PORT_HDMI)
        {
            ucHdmi++;
        }
        if(AwtoSrcPort(ucI) == ucPort)
        {
            if((tAwtoSrcType[ucI - 1] & 0x0F) == _PORT_DP)
            {
                AwtoCardTxt(AWTO_CT_DP);
                return;
            }
            if((tAwtoSrcType[ucI - 1] & 0x0F) == _PORT_HDMI)
            {
                AwtoCardTxt(AWTO_CT_HDMI);
                AwtoPutNum(ucHdmi, 1);
                return;
            }
            break;
        }
    }
    AwtoCardTxt(AWTO_CT_PORT);
    AwtoPutNum(ucPort - _D0_INPUT_PORT, 1);
}

static bit AwtoPortIsDp(BYTE ucPort)
{
    BYTE ucI;

    for(ucI = 1; ucI <= AWTO_SRC_PORTS; ucI++)
    {
        if(AwtoSrcPort(ucI) == ucPort)
        {
            return ((tAwtoSrcType[ucI - 1] & 0x0F) == _PORT_DP);
        }
    }
    return 0;
}

static void AwtoSrcSet(BYTE ucI)
{
    SET_OSD_INPUT_PORT_OSD_ITEM((ucI == 0) ? _OSD_INPUT_AUTO : AwtoSrcItem(AwtoSrcPort(ucI)));
}

//---- #139 per-port live status + sync log pane ----
// Layout (AWTO_SRC_COLS wide): Auto; per port 3 lines: name + state, signals (fw/awto/portsig.tsv), stage + rate; the log.
#define AWTO_SRC_COLS       46
#define AWTO_SRC_STAGE_COL  3                   // line 3: sync stage
#define AWTO_SRC_RATE_COL   15                  // line 3: rate (timing / TMDS clock / DP link)
#define AWTO_SRC_RATE_W     (AWTO_SRC_COLS - AWTO_SRC_RATE_COL - 1)
#define AWTO_SRC_LOGN       8                   // log pane lines
#define AWTO_SRC_PROW(i)    (AWTO_SRC_ROW0 + 1 + ((i) - 1) * 3)   // port item i (1..n): first line
#define AWTO_SRC_LOGHDR     (AWTO_SRC_PROW(AWTO_SRC_PORTS) + 4)
#define AWTO_SRC_LINES      (AWTO_SRC_LOGHDR + 1 + AWTO_SRC_LOGN + 1)     // + pad row (the frame covers the last 2 px)
#define AWTO_PS_SRC_IN      0
#define AWTO_PS_SRC_CNT     1
#define AWTO_PS_SRC_XREG    2
#define AWTO_PS_SRC_CABLE   3
#define AWTO_PS_SRC_DDC     4
#define AWTO_PS_SRC_TMDS    5

// GENERATED-BEGIN awto_port_sigs
#define AWTO_PS_N 16
static const __code BYTE tAwtoPsPort[16] = {
    0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2};
static const __code BYTE tAwtoPsSrc[16] = {
    3, 0, 0, 0, 1, 4, 3, 0, 0, 5, 4, 3, 0, 0, 5, 4};
static const __code WORD tAwtoPsA[16] = {0x0000, 0x0019, 0x001D, 0x001E, 0x0000, 0x0000, 0x0000, 0x001B, 0x0018, 0x0071, 0x0000, 0x0000, 0x001A, 0x0017, 0x0072, 0x0000};
static const __code BYTE tAwtoPsB[16] = {
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00};
static const __code BYTE tAwtoPsCol[16] = {
    6, 11, 16, 21, 27, 36, 6, 10, 15, 21, 26, 6, 10, 15, 21, 26};
static const __code BYTE tAwtoPsLblCol[16] = {
    3, 8, 13, 18, 23, 33, 3, 8, 12, 17, 23, 3, 8, 12, 17, 23};
static const __code char tAwtoPsLblS[] = "cbl\0" "hpd\0" "p15\0" "p16\0" "p17\0" "ddc\0" "cbl\0" "5V\0" "hpd\0" "tmds\0" "ddc\0" "cbl\0" "5V\0" "hpd\0" "tmds\0" "ddc\0" "";
static const __code BYTE tAwtoPsLblOff[16] = {
    0, 4, 8, 12, 16, 20, 24, 28, 31, 35, 40, 44, 48, 51, 55, 60};
static void AwtoPsLbl(BYTE ucRow)                  // signal label (one table + its reader, awto-sdcc#39)
{
    const __code char *pc = &tAwtoPsLblS[tAwtoPsLblOff[ucRow]];

    while(*pc != 0)
    {
        AwtoPutChar(*pc++);
    }
}
// GENERATED-END awto_port_sigs

// GENERATED-BEGIN awto_sync_text
static const __code BYTE tAwtoSyncFmt[330] = {
    0x00, 0x0A, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x00, 0x10, 0x0B, 0x0B, 0x0B,
    0x0B, 0x0B, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x16, 0x0C, 0x0C, 0x8D, 0x0E, 0x0C,
    0x0C, 0x0F, 0x00, 0x01, 0x01, 0x01, 0x14, 0x14, 0x14, 0x14, 0x14, 0x14, 0x14, 0x14, 0x14, 0x14,
    0x14, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x13, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x00, 0x00,
    0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x0B, 0x09, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x11, 0x12, 0x15, 0x15, 0x15, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x09, 0x00,
    0x80, 0x80, 0x80, 0x83, 0x87, 0x88, 0x80, 0x82, 0x85, 0x86, 0x00, 0x80, 0x80, 0x80, 0x80, 0x80,
    0x83, 0x80, 0x80, 0x80, 0x8B, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x0D, 0x01,
    0x00, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x0C, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x0C, 0x0C, 0x0C, 0x0C,
    0x0C, 0x0C, 0x00, 0x00, 0x0C, 0x0C, 0x0C, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x0C, 0x00, 0x0C,
    0x0C, 0x0C, 0x0C, 0x0C, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x0C, 0x0C, 0x0C, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
    0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00};
static const __code char tAwtoSyncTxtS[] = "boot:cold power-up (no valid canary in RAM)\0" "boot:watchdog bite, \x01" "\0" "boot:warm reset, no capture (host ISP 0xEE, or a hardware watchdog reset with interrupts off)\0" "boot:watchdog probe reset (test cmd 0x49 / 0x4F)\0" "boot:hardware watchdog reset, no capture (an early warning IRQ came)\0" "boot:main() entered\0" "boot:GPIO set up\0" "boot:MCU set up (M2PLL clock, flash clock, code banks, Timer2 tick)\0" "boot:pin functions set\0" "boot:first main-loop pass\0" "MCU init:crystal clock, watchdog N = \x01" "\0" "Timer2 1ms tick running\0" "watchdog run-time:\x01" "\0" "NVRAM save start (since the last poke \x01" ")\0" "NVRAM save end (since the last poke \x01" ")\0" "flash erase start (since the last poke \x01" ")\0" "flash erase done (since the last poke \x01" ")\0" "NVRAM page move (since the last poke \x01" ")\0" "NVRAM flush (gate open)\0" "NVRAM flush (forced after 30s)\0" "NVRAM flush (power off / saving entry)\0" "NVRAM flush (menu / selector close)\0" "NVRAM flush (test cmd 0x3D)\0" "NVRAM write outside the gate\0" "NVRAM:a second BriCon / ColorProc item while one waits, written at once by the SDK save\0" "NVRAM flush (DDC/CI save settings)\0" "NVRAM \x01" "\0" "flash:type \x01" " found by the SDK (tFlashInformation index:24 = MX25L8006E, 254 = none)\0" "(the 2 lines above repeated \x01" " more times)\0" "wake by the SDK source detect, not our poll (poll state \x01" ")\0" "host time \x01" "\0" "(fw +\x01" " ms, first host sync since boot)\0" "(fw +\x01" " ms, host sync after a drift)\0" "drift \x01" " (host - fw clock)\0" "power on\0" "switch to \x01" "\0" "wake on \x01" "\0" "power key on, \x01" "\0" "panel on by \x01" " (accepted)\0" "panel on by \x01" " (already on)\0" "panel off by \x01" " (accepted)\0" "panel off by \x01" " (already off)\0" "backlight on by \x01" " (accepted)\0" "backlight on by \x01" " (already on)\0" "backlight off by \x01" " (accepted)\0" "backlight off by \x01" " (already off)\0" "panel on by \x01" " (deferred:power off / saving takes the panel down)\0" "backlight on by \x01" " (deferred:power off / saving takes the panel down)\0" "backlight off by \x01" " (deferred:power off / saving takes the panel down)\0" "panel:in OFF for \x01" "->VDD:VDD on, T1 starts\0" "panel:in VDD for \x01" "->HPD:T1 done, power on, eDP-1 PHY on\0" "panel:in VDD for \x01" "->T6:off before the PHY, VDD off\0" "panel:in HPD for \x01" "->LINK:eDP-1 HPD high, link training\0" "panel:in HPD for \x01" "->T6:off, PHY and VDD off\0" "panel:in LINK for \x01" "->VIDEO:eDP-1 link trained in \x01" ", stream on\0" "panel:in VIDEO for \x01" "->T4:off, backlight dark:T4 counts from the backlight pin off\0" "panel:in T4 for \x01" "->VIDEO:on again, stream still on\0" "panel:in T4 for \x01" "->T5:T4 done, stream idle\0" "panel:in T5 for \x01" "->VIDEO:on again, stream on\0" "panel:in T5 for \x01" "->T6:T5 done, link and VDD off\0" "panel:in T6 for \x01" "->OFF:T6 done, VDD may come on again\0" "panel:in VIDEO for \x01" "->T5:off, backlight never on:no T4, stream idle\0" "panel:backlight on at once (Dan:no T3 wait):pin on\0" "panel:backlight on at once at boot, PWM full (Dan:as early as possible)\0" "panel:backlight PWM:user brightness, settings loaded \x01" " after the boot full duty\0" "panel:backlight pin on, \x01" " after wanted (menu:backlight on delay)\0" "panel:backlight PWM duty set, \x01" " after the pin\0" "panel:backlight off wanted \x01" " after the pin, PWM dark\0" "panel:backlight off wanted, PWM dark (\x01" " lit)\0" "panel:backlight pin off, \x01" " after PWM dark\0" "panel:state change \x01" " (not a listed transition)\0" "panel:no eDP-1 HPD within T2, link training anyway\0" "eDP-1:link training FAIL\0" "panel VDD pin off, written outside the panel machine\0" "panel VDD pin on, written outside the panel machine\0" "panel VDD pin off again (already off), written outside the panel machine\0" "panel VDD pin on again (already on), written outside the panel machine\0" "backlight pin off, written outside the panel machine\0" "backlight pin on, written outside the panel machine\0" "backlight pin off again (already off), written outside the panel machine\0" "backlight pin on again (already on), written outside the panel machine\0" "backlight PWM written outside the panel machine\0" "system:\x01" "\0" "system:\x01" "\0" "LED:off (\x01" ")\0" "LED:on colour (\x01" ")\0" "LED:standby colour breathing (\x01" ")\0" "judge:source unstable\0" "judge:timing change\0" "judge:interlace change\0" "judge:memory / timing gen\0" "fast path refused:no cache\0" "fast path refused:receiver unstable\0" "fast path:SDK reset meanwhile\0" "fast path refused:timing field \x01" "\0" "hold:SDK reset\0" "HPD pulse (TMDS recover)\0" "HPD high again after 110ms (TMDS recover)\0" "TMDS predetect on (clock not measured yet)\0" "TMDS clock \x01" " measured\0" "DP link \x01" " detected\0" "scan done:\x01" "\0" "signal lost\0" "timing \x01" "\0" "refresh \x01" "\0" "pixel clock \x01" "\0" "console opened (sync log)\0" "cable plugged in:wake\0" "EDID read by source:wake\0" "AUX command from source:wake\0" "DPCD 600h = D0 (source powers the link):wake\0" "cable unplugged:wake\0" "wake by TMDS clock, about \x01" " (IOSC reference)\0" "DDC activity in power saving:no wake (SDK DDC handshake gated, counted)\0" "DP AUX activity in power saving:no wake (SDK AUX toggle gated, counted)\0" "AUX command from source in power saving:no wake (wake:DPCD 600h = D0 or link training)\0" "TMDS clock burst \x01" " in power saving:shorter than the hold, no wake\0" "refused:no cable on \x01" "\0" "no cable on \x01" ", no signal, another port cabled:auto search\0" "input selector opened (SOURCE key) on \x01" "\0" "input selector opened (no-signal / wake card) on \x01" "\0" "input selector:\x01" " kept (no key for 2s, the input it opened on), closed\0" "input selector:\x01" " kept (AUTO on the input it opened on), closed\0" "input selector cancelled (MENU):\x01" " kept\0" "input selector:\x01" " refused, no cable; stays open\0" "input selector:take ignored, DP version pop-up up\0" "input selector:item \x01" " is no port of this board; stays open\0" "input selector closed by a mode reset (SDK OSD reset):\x01" " kept\0" "console (opened by itself) closed by SOURCE:input selector next\0" "\x01" " disabled by setting (stored):HPD low, EDID off, receiver off, not searched\0" "\x01" " disabled by setting:HPD low, EDID off, receiver off, not searched\0" "\x01" " enabled by setting:HPD up, EDID on, receiver on, searched\0" "\x01" " enabled by the input selector:HPD up, EDID on, receiver on\0" "\x01" " enabled by input select (VCP 0x60 / menu / test cmd):HPD up, EDID on, receiver on\0" "disable \x01" " refused:the input on screen\0" "disable \x01" " refused:the last enabled input\0" "wake on \x01" " suppressed:input disabled (once per trigger per sleep)\0" "disable \x01" " requested:already disabled\0" "enable \x01" " requested:already enabled\0" "fixed search on disabled \x01" ":auto search\0" "speaker amp on:P7.4 = 1, AMP_MUTE P7.3 = 0\0" "speaker amp off:P7.4 = 0, AMP_MUTE P7.3 = 1\0" "unmute while audio test step \x01" " is held:P7.4 / AMP_MUTE P7.3 as that step sets them\0" "audio test 1/6:aout, P7.4 on, P7.3 low, -6dB\0" "audio test 2/6:aout, P7.4 OFF, P7.3 low, -6dB\0" "audio test 3/6:aout, P7.4 on, P7.3 low, -16.5dB (Dahua default)\0" "audio test 4/6:aout, P7.4 on, P7.3 low, -3dB\0" "audio test 5/6:aout, P7.4 on, P7.3 low, 0dB\0" "audio test 6/6:aout, P7.4 on, P7.3 HIGH (AMP_MUTE check), -6dB\0" "audio test 1/6 end, back to default:aout, P7.4 on, P7.3 low, your volume\0" "audio test 2/6 end, back to default:aout, P7.4 on, P7.3 low, your volume\0" "audio test 3/6 end, back to default:aout, P7.4 on, P7.3 low, your volume\0" "audio test 4/6 end, back to default:aout, P7.4 on, P7.3 low, your volume\0" "audio test 5/6 end, back to default:aout, P7.4 on, P7.3 low, your volume\0" "audio test 6/6 end, back to default:aout, P7.4 on, P7.3 low, your volume\0" "audio test (no step):\x01" " Hz\0" "audio test 1:\x01" " Hz\0" "audio test 2:\x01" " Hz\0" "audio test 3:\x01" " Hz\0" "audio test 4:\x01" " Hz\0" "audio test 5:\x01" " Hz\0" "audio test 6:\x01" " Hz\0" "M-domain set-up:start\0" "M-domain set-up:IVS wait 1\0" "M-domain set-up:memory check (WD ctrl0 x 256 + status0 = \x01" ")\0" "M-domain set-up:memory + timing gen check OK (WD ctrl0 x 256 + status0 = \x01" ")\0" "DCLK fine tune:final offset \x01" "\0" "M-domain set-up:step lines stop after \x01" " this boot\0" "M-domain set-up:the first set-up did not finish; later passes not logged\0" "frame buffer forced (test cmd 0x0C):display setting re-run\0" "memory mode back to the SDK choice (test cmd 0x0D):display setting re-run\0" "frame buffer requested:already forced\0" "SDK memory choice requested:already\0" "memory force \x01" " stored (not ACTIVE):next display setting\0" "frame buffer refused:FRC not built (_AWTO_FRC off)\0" "memory select:frame-sync line buffer (force \x01" ")\0" "memory select:frame-sync frame buffer (force \x01" ")\0" "memory select:free-run frame buffer (force \x01" ")\0" "memory select:M/N frame-sync frame buffer (force \x01" ")\0" "memory select:free run, no input (force \x01" ")\0" "picture normal:display re-set\0" "picture mirrored left-right:display re-set\0" "picture mirrored top-bottom:display re-set\0" "picture rotated 180:display re-set\0" "picture normal:stored, applies at the next display setting\0" "picture mirrored left-right:stored, applies at the next display setting\0" "picture mirrored top-bottom:stored, applies at the next display setting\0" "picture rotated 180:stored, applies at the next display setting\0" "picture normal:already in effect\0" "picture mirrored left-right:already in effect\0" "picture mirrored top-bottom:already in effect\0" "picture rotated 180:already in effect\0" "picture normal:not built (no _AWTO_ROTATION):stored only\0" "picture mirrored left-right:not built (no _AWTO_ROTATION):stored only\0" "picture mirrored top-bottom:not built (no _AWTO_ROTATION):stored only\0" "picture rotated 180:not built (no _AWTO_ROTATION):stored only\0" "OSD rotated 180 with the picture\0" "OSD upright\0" "wake suppressed (cable, once per sleep):\x01" "\0" "wake suppressed (EDID read, once per sleep):\x01" "\0" "wake suppressed (AUX command, once per sleep):\x01" "\0" "wake suppressed (DPCD 600h, once per sleep):\x01" "\0" "wake suppressed (cable unplug, once per sleep):\x01" "\0" "wake suppressed (TMDS clock, once per sleep):\x01" "\0" "line \x01" " test 1234567890\0" "line \x01" " test 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890\0" "line \x01" " test 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890 1234567890\0" "AC ON\0" "OFF\0" "INITIAL\0" "SEARCH\0" "DISPLAY SETTING\0" "ACTIVE\0" "FAST SWITCH\0" "HOLD L1\0" "NO SUPPORT\0" "NO SIGNAL\0" "POWER SAVING\0" "WAKE SEARCH\0" "POWER DOWN\0" "RESET\0" "POWER key\0" "front key in power saving\0" "test cmd 0x3E (POWER key)\0" "DDC/CI VCP D6 power mode\0" "input select (KVM / VCP 0x60 / menu / test cmd)\0" "input selector\0" "dead port:auto search\0" "our wake poll\0" "SDK power-saving source detect\0" "SDK cable reset (search port cable changed)\0" "no-signal cards:power-saving timer\0" "settings (aspect / overscan / DP version)\0" "SDK OSD (user adjust)\0" "hold L2 released:no-signal path (power-saving timers)\0" "hold:signal back, fast wake\0" "fast path taken (cached input)\0" "fast path:picture up\0" "fast path timeout:full path\0" "fast wake timeout:back to the hold\0" "judge timer:timing not confirmed (no signal)\0" "judge timer:no support\0" "NVRAM power status at boot\0" "SDK\0" "wake search found no source\0" "target written without a request\0" "hold:fast wakes used up\0" "hold:auto search, other cable\0" "INITIAL done\0" "timing confirmed, supported\0" "search done, no source\0" "display set, panel video ready\0" "judge:source unstable\0" "judge:timing change\0" "judge:interlace change\0" "judge:memory / timing gen\0" "judge:eDP unstable\0" "signal lost:L1 hold (backlight off, set-up kept)\0" "panel down (T4 / T5 done)\0" "power off / saving called off\0" "system machine started\0" "AUTO key:auto source select\0" "UP+DOWN in power saving:wake into the console\0" "input selector:no key for 2s (idle commit)\0" "input selector closed by a mode reset:its highlighted input\0" "test cmd 0x0C / 0x0D (memory mode)\0" "power off\0" "power on\0" "power saving\0" "reset to search\0" "display setting again\0" "display setting again (no forced background)\0" "no support\0" "no signal\0" "power-saving reset\0" "power-off reset\0" "factory mode\0" "fast switch\0" "back to the hold\0" "fast path done\0" "accepted\0" "already\0" "replaces a pending request\0" "refused in this state\0" "kept until the state allows it\0" "dropped:the no-signal search found a timing first\0" "->\0" " (\0" " ms):\0" " by \0" "; \0" "in \0" " for \0" "ms->\0" ":\0" "monitor off, inputs not searched\0" "monitor off, inputs not searched\0" "scaler input side reset for a new search\0" "searching for inputs\0" "scaler timing set\0" "picture on screen\0" "timing outside what scaler / panel accept\0" "search found no source\0" "no signal, low power, waiting for a wake\0" "boot (cold power-up:panel early)\0" "boot (warm reset:VDD kept on)\0" "power switch OFF->NORMAL\0" "power switch POWER SAVING->NORMAL (wake)\0" "our wake poll (console + backlight)\0" "power off / saving:panel down first\0" "power off / saving called off:previous level\0" "display setting / ACTIVE gate:video wanted\0" "display setting:backlight action off\0" "display setting:DCLK change\0" "SDK OSD reset\0" "first ACTIVE pass\0" "L1 hold:signal lost\0" "hold:signal back, fast wake\0" "input selector opened\0" "SDK OSD:no-signal card\0" "SDK OSD:no-cable card\0" "SDK OSD:no-support card\0" "SDK OSD:source menu\0" "SDK OSD:power-saving card\0" "SDK OSD:DP info\0" "FreeSync OD measure\0" "SDK power switch:AC ON->OFF\0" "SDK power switch:NORMAL->OFF\0" "SDK power switch:NORMAL->POWER SAVING\0" "UP+DOWN wake (console + backlight)\0" "";
static const __code WORD tAwtoSyncTxtOff[330] = {0, 44, 66, 160, 209, 278, 298, 315, 383, 406, 432, 471, 495, 515, 556, 595, 637, 678, 718, 742, 773, 812, 848, 876, 905, 993, 1028, 1036, 1120, 1162, 1221, 1233, 1272, 1308, 1334, 1343, 1355, 1365, 1381, 1406, 1433, 1459, 1488, 1517, 1548, 1578, 1611, 1676, 1745, 1815, 1857, 1913, 1964, 2019, 2063, 2125, 2207, 2258, 2301, 2346, 2394, 2448, 2516, 2567, 2639, 2719, 2784, 2830, 2883, 2928, 2970, 3017, 3068, 3093, 3146, 3198, 3271, 3342, 3395, 3447, 3520, 3591, 3639, 3648, 3657, 3669, 3687, 3720, 3742, 3762, 3785, 3811, 3838, 3874, 3904, 3937, 3952, 3977, 4019, 4062, 4084, 4103, 4115, 4127, 4136, 4146, 4160, 4186, 4208, 4233, 4262, 4307, 4328, 4373, 4445, 4517, 4604, 4670, 4692, 4750, 4790, 4841, 4911, 4974, 5013, 5060, 5110, 5169, 5230, 5294, 5371, 5439, 5499, 5560, 5644, 5682, 5723, 5788, 5825, 5860, 5899, 5942, 5986, 6069, 6114, 6160, 6224, 6269, 6313, 6376, 6449, 6522, 6595, 6668, 6741, 6814, 6840, 6858, 6876, 6894, 6912, 6930, 6948, 6970, 6997, 7057, 7133, 7163, 7213, 7286, 7345, 7419, 7457, 7493, 7549, 7600, 7647, 7695, 7741, 7793, 7836, 7866, 7909, 7952, 7987, 8046, 8118, 8190, 8254, 8287, 8333, 8379, 8417, 8474, 8544, 8614, 8676, 8709, 8721, 8763, 8809, 8857, 8903, 8952, 8999, 9022, 9111, 9255, 9261, 9265, 9273, 9280, 9296, 9303, 9315, 9323, 9334, 9344, 9357, 9369, 9380, 9386, 9396, 9422, 9448, 9473, 9521, 9536, 9558, 9572, 9603, 9647, 9682, 9724, 9746, 9800, 9828, 9859, 9880, 9908, 9943, 9988, 10011, 10038, 10042, 10070, 10103, 10127, 10157, 10170, 10198, 10221, 10252, 10274, 10294, 10317, 10343, 10362, 10411, 10437, 10467, 10490, 10518, 10564, 10607, 10667, 10702, 10712, 10721, 10734, 10750, 10772, 10817, 10828, 10838, 10857, 10873, 10886, 10898, 10915, 10930, 10939, 10947, 10974, 10996, 11027, 11077, 11080, 11083, 11089, 11094, 11097, 11101, 11107, 11112, 11114, 11147, 11180, 11221, 11242, 11260, 11278, 11320, 11343, 11384, 11417, 11447, 11472, 11513, 11549, 11585, 11630, 11673, 11710, 11738, 11752, 11770, 11790, 11818, 11840, 11863, 11885, 11909, 11929, 11955, 11971, 11991, 12019, 12048, 12086};
static BYTE AwtoSyncTxt(WORD usRow, BYTE ucPart)   // text after ucPart (0..2) value marks, 0xFF = none; returns the fmt
{                                                  // usRow: logged row, or AWTO_SYNC_NAME_ROW0 + name row
    const __code char *pc = &tAwtoSyncTxtS[tAwtoSyncTxtOff[usRow]];

    if(ucPart == 0xFF)
    {
        return tAwtoSyncFmt[usRow];
    }
    if(ucPart != 0)                             // at most two marks (ms2); ucPart is not written (no XDATA copy)
    {
        while((*pc != 0) && (*pc != 1))
        {
            pc++;
        }
        if(*pc == 0)
        {
            return tAwtoSyncFmt[usRow];
        }
        pc++;
        if(ucPart == 2)
        {
            while((*pc != 0) && (*pc != 1))
            {
                pc++;
            }
            if(*pc == 0)
            {
                return tAwtoSyncFmt[usRow];
            }
            pc++;
        }
    }
    while((*pc != 0) && (*pc != 1))             // AwtoPutChar inlined: no call, so the packer keeps the table in this bank
    {
        if(s_bAwtoSkip != 0)
        {
            if(--s_ucLogI == 0)                 // second pass of a wrapped console line: dropped
            {
                s_bAwtoSkip = 0;
            }
        }
        else if(s_ucAwtoLen < s_ucAwtoCols)
        {
            s_pcAwtoRow[s_ucAwtoLen++] = *pc;
        }
        else if(s_bAwtoWrap != 0)
        {
            s_bAwtoOver = 1;                    // main-page log: the line takes two rows (AwtoConWrapLine)
        }
        pc++;
    }
    return tAwtoSyncFmt[usRow];
}
#define AWTO_SYNC_NAME_FIRST 0x15
#define AWTO_SYNC_NAME_ROW0 207                 // text row of name row 0 (= the logged rows)
#define AWTO_SYNC_NAME_IDS 7
#define AWTO_SYNC_NAME_ARGS 64
static const __code BYTE tAwtoSyncNameRow[448] = {
    1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 55, 56, 57, 58,
    59, 42, 43, 0, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 60, 61, 62, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 63, 64, 65, 66, 67, 68, 69, 70, 0, 0, 0, 0, 0, 0, 0,
    71, 72, 73, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    74, 75, 76, 77, 78, 79, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    80, 0, 81, 82, 83, 84, 85, 86, 87, 88, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    89, 90, 91, 92, 93, 94, 0, 0, 95, 96, 97, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 98, 99, 100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121, 122, 123, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};
// GENERATED-END awto_sync_text

static __xdata BYTE s_pucSrcSt[3];              // last drawn: port state, sync stage, rate checksum
static __xdata BYTE s_pucSrcStage[3];
static __xdata WORD s_pusSrcRate[3];             // rate change key (AwtoSrcRateKey)
static __xdata BYTE s_pucSrcSig[AWTO_PS_N];     // last drawn value per signal row
static __xdata BYTE s_pucSrcCnt[(AWTO_PS_CNT_N != 0) ? AWTO_PS_CNT_N : 1];   // edge counter at the last poll
static __xdata WORD s_usSrcPoll;
static __xdata BYTE s_ucSrcLogSeq;              // ring seq the log pane shows up to

static void AwtoPutTenths(DWORD ulV)
{
    AwtoPutNum(ulV / 10, 1);
    AwtoPutChar('.');
    AwtoPutNum(ulV % 10, 1);
}

static void AwtoPutDpRate(BYTE ucRate, BYTE ucLanes)
{
    if(ucRate == _DP_LINK_RBR) AwtoCardTxt(AWTO_CT_RBR);
    else if(ucRate == _DP_LINK_HBR) AwtoCardTxt(AWTO_CT_RBR + 1);
    else if(ucRate == _DP_LINK_HBR2) AwtoCardTxt(AWTO_CT_RBR + 2);
    else if(ucRate == _DP_LINK_HBR3) AwtoCardTxt(AWTO_CT_HBR3);
    else AwtoPutHex2(ucRate);
    AwtoPutStr(" x");
    AwtoPutNum(ucLanes, 1);
}

// #157 unix s + UTC offset (15 min) -> "2026-11-12T08:45:10+11:00" (days -> civil date: H. Hinnant's civil_from_days).
// No parameters or locals in DATA: it sits on the deepest overlay path (flash save -> sync push -> console line).
static __xdata DWORD s_ulAwtoD;                 // days, then day of the era, then day of the year
static __xdata WORD s_usAwtoIsoY;
static __xdata BYTE s_ucAwtoIsoMp;              // March-based month 0..11
static __xdata signed char s_cAwtoIsoOfs;       // input: UTC offset, 15 min units

static void AwtoPutIso(void)                    // input s_ulAwtoT = unix s, s_cAwtoIsoOfs
{
    s_ulAwtoT += (long)s_cAwtoIsoOfs * 900;     // local s
    s_ulAwtoD = s_ulAwtoT / 86400 + 719468;     // days since 0000-03-01
    s_usAwtoIsoY = (WORD)(s_ulAwtoD / 146097) * 400;
    s_ulAwtoD %= 146097;
    s_usAwtoIsoY += (WORD)((s_ulAwtoD - s_ulAwtoD / 1460 + s_ulAwtoD / 36524 - s_ulAwtoD / 146096) / 365);
    s_ulAwtoD -= 365UL * (s_usAwtoIsoY % 400) + (s_usAwtoIsoY % 400) / 4 - (s_usAwtoIsoY % 400) / 100;
    s_ucAwtoIsoMp = (BYTE)((5 * (WORD)s_ulAwtoD + 2) / 153);
    AwtoPutNum(s_usAwtoIsoY + ((s_ucAwtoIsoMp >= 10) ? 1 : 0), 4);
    AwtoPutChar('-');
    AwtoPutNum((s_ucAwtoIsoMp < 10) ? (s_ucAwtoIsoMp + 3) : (s_ucAwtoIsoMp - 9), 2);
    AwtoPutChar('-');
    AwtoPutNum((WORD)s_ulAwtoD - (153 * (WORD)s_ucAwtoIsoMp + 2) / 5 + 1, 2);
    AwtoPutChar('T');
    s_ulAwtoT %= 86400;
    AwtoPutClock();
    AwtoPutChar((s_cAwtoIsoOfs < 0) ? '-' : '+');
    s_ucAwtoIsoMp = (s_cAwtoIsoOfs < 0) ? (BYTE)(0 - s_cAwtoIsoOfs) : (BYTE)s_cAwtoIsoOfs;
    AwtoPutNum(s_ucAwtoIsoMp / 4, 2);
    AwtoPutChar(':');
    AwtoPutNum((s_ucAwtoIsoMp % 4) * 15, 2);
}

// #162 step 3: a name from a sync.tsv table row (id 15..18): the row text, or the code in hex when there is no row
static void AwtoSyncName(BYTE ucId, BYTE ucArg)    // no locals: XDATA is full (#162 step 3)
{
    if(((BYTE)(ucId - AWTO_SYNC_NAME_FIRST) < AWTO_SYNC_NAME_IDS) && (ucArg < AWTO_SYNC_NAME_ARGS) &&
       (tAwtoSyncNameRow[(WORD)(ucId - AWTO_SYNC_NAME_FIRST) * AWTO_SYNC_NAME_ARGS + ucArg] != 0))
    {
        AwtoSyncTxt(AWTO_SYNC_NAME_ROW0 - 1 + tAwtoSyncNameRow[(WORD)(ucId - AWTO_SYNC_NAME_FIRST) * AWTO_SYNC_NAME_ARGS + ucArg], 0);
        return;
    }
    AwtoPutHex2(ucArg);
}

// One sync-ring entry as a log line: "  260:D2 timing 3840x2160" (texts and formats: fw/awto/sync.tsv).
static __xdata DWORD s_ulAwtoLnV;               // #157: value + time in XDATA (DATA overlay path depth, see AwtoPutIso)
static __xdata WORD s_usAwtoLnMs;

static void AwtoPutNvFlush(void);              // #151 fmt nvw: NVRAM flush section (last in this file)
#define ulV s_ulAwtoLnV
#define usMs s_usAwtoLnMs
static void AwtoSyncLine(BYTE ucSeq)
{
    BYTE __xdata *puc = (BYTE __xdata *)&g_stAwtoSync.stEv[AWTO_SYNC_IDX(ucSeq)];
    BYTE ucRow = AwtoSyncRow(puc[0], puc[1]);
    BYTE ucFmt;

    ulV = ((DWORD)puc[4] << 24) | ((DWORD)puc[5] << 16) | ((WORD)puc[6] << 8) | puc[7];
    usMs = (((WORD)puc[2] << 8) | puc[3]) - (((WORD)g_stAwtoSync.ucT0Hi << 8) | g_stAwtoSync.ucT0Lo);

    for(ucFmt = (usMs < 10) ? 4 : (usMs < 100) ? 3 : (usMs < 1000) ? 2 : (usMs < 10000) ? 1 : 0; ucFmt != 0; ucFmt--)
    {
        AwtoPutChar(' ');                       // left pad to 5 digits (Dan); not AwtoPutCol: a skipped pass does not move the length
    }
    AwtoPutNum(usMs, 1);
    AwtoPutChar(':');                           // time column "nnnnn:" (no '+', no unit)
    if(ucRow == 0)
    {
        AwtoPutStr("event ");
        AwtoPutHex2(puc[0]);
        AwtoPutChar(' ');
        AwtoPutHex2(puc[1]);
        return;
    }
    ucFmt = AwtoSyncTxt(ucRow - 1, 0xFF);        // 0xFF = nothing printed, the fmt only
    if((ucFmt & 0x80) != 0)
    {
        AwtoPortName(puc[1]);
        AwtoPutChar(' ');
    }
    AwtoSyncTxt(ucRow - 1, 0);
    switch(ucFmt & 0x7F)
    {
        case 1:                                 // vport
            if(puc[7] == 0xFF) AwtoPutStr("auto");
            else { AwtoPortName(puc[7]); }
            break;
        case 2: AwtoPutNum(ulV >> 16, 1); AwtoPutChar('x'); AwtoPutNum(ulV & 0xFFFF, 1); break;    // res
        case 3: AwtoPutTenths(ulV); AwtoPutStr("MHz"); break;                            // mhz1
        case 4: AwtoPutTenths(ulV); AwtoPutStr("Hz"); break;                                // hz1
        case 5: AwtoPutMilli(ulV); AwtoPutStr("Hz"); break;                                 // hz3
        case 6: AwtoPutMilli(ulV); AwtoPutStr("MHz"); break;                             // mhz3
        case 7: AwtoPutDpRate(puc[6], puc[7]); break;                                              // dp
        case 8:                                                                                    // src
            if(ulV == _SOURCE_HDMI) AwtoPutStr("HDMI");
            else if(ulV == _SOURCE_DP) AwtoPutStr("DP");
            else if(ulV == _SOURCE_DVI) AwtoPutStr("DVI");
            else AwtoPutNum(ulV, 1);
            break;
        case 9: AwtoPutHex2(puc[1]); break;                                                        // harg
        case 10:                                                                                   // pc (#29)
            AwtoPutStr(((puc[4] & 0x80) != 0) ? "STALL TEST, PC " : "STALL, PC ");
            if(puc[6] >= 0x50) AwtoPutHex2(puc[5]); else AwtoPutChar('C');
            AwtoPutChar(':');
            AwtoPutHex2(puc[6]);
            AwtoPutHex2(puc[7]);
            break;
        case 11: AwtoPutNum(ulV, 1); AwtoPutStr("ms"); break;                                     // ms (#150)
        case 12: AwtoPutNum(ulV, 1); break;                                                        // n (#150)
        case 13: AwtoPutHex2(puc[5]); AwtoPutHex2(puc[6]); AwtoPutHex2(puc[7]); break;             // x (#150)
        case 14: s_ulAwtoT = ulV; s_cAwtoIsoOfs = (signed char)puc[1]; AwtoPutIso(); break;                                     // htime (#157)
        case 15:                                                                                   // sms (#157)
            AwtoPutChar(((long)ulV < 0) ? '-' : '+');
            AwtoPutNum(((long)ulV < 0) ? (0 - ulV) : ulV, 1);
            AwtoPutStr("ms");
            break;
        case 16:                                                                                   // wdt: warning ms << 16 | reset ms
            AwtoPutStr("warning "); AwtoPutNum(ulV >> 16, 1); AwtoPutStr("ms, reset "); AwtoPutNum(ulV & 0xFFFF, 1); AwtoPutStr("ms");
            break;
        case 17:                                                                                   // sys: in old for N ms -> new: why
            AwtoSyncName(AWTO_SYNC_EV_SYS_SEP, 6); AwtoSyncName(AWTO_SYNC_EV_SYS_STATE, puc[1] >> 4);
            AwtoSyncName(AWTO_SYNC_EV_SYS_SEP, 7); AwtoPutNum(ulV & AWTO_SYS_MS_MAX, 1); AwtoSyncName(AWTO_SYNC_EV_SYS_SEP, 8);
            AwtoSyncName(AWTO_SYNC_EV_SYS_STATE, puc[1] & 0x0F); AwtoSyncName(AWTO_SYNC_EV_SYS_SEP, 9);
            AwtoSyncName(AWTO_SYNC_EV_SYS_WHY, puc[4] & AWTO_SYS_WHY_CODE);
            if((puc[4] & AWTO_SYS_WHY_MODE) != 0)                                                  // #162 s3b: the SDK mode changed
            {
                AwtoSyncName(AWTO_SYNC_EV_SYS_SEP, 5); AwtoSyncName(AWTO_SYNC_EV_SYS_MODE, puc[1] & 0x0F);
            }
            break;
        case 18:                                                                                   // sysreq: request by who (outcome)
            AwtoSyncName(AWTO_SYNC_EV_SYS_REQNAME, puc[1]); AwtoSyncName(AWTO_SYNC_EV_SYS_SEP, 4);
            AwtoSyncName(AWTO_SYNC_EV_SYS_WHY, puc[6]); AwtoSyncName(AWTO_SYNC_EV_SYS_SEP, 2);
            AwtoSyncName(AWTO_SYNC_EV_SYS_OUTCOME, puc[7]); AwtoPutChar(')');
            break;
        case 19:                                                                                   // ms2: low word ms % ... high word ms % (#162 s3b)
            AwtoPutNum(ulV & 0xFFFF, 1); AwtoPutStr("ms"); AwtoSyncTxt(ucRow - 1, 1);
            AwtoPutNum(ulV >> 16, 1); AwtoPutStr("ms"); AwtoSyncTxt(ucRow - 1, 2);
            return;                                 // its own tail: no fmt kept over the calls (DATA overlay path, #162 s3b)
        case 20: AwtoSyncName(AWTO_SYNC_EV_PNL_BY, puc[7]); break;                                 // pby: panel requester (#162 s3b)
        case 21: AwtoSyncName(AWTO_SYNC_EV_SYS_STATE, puc[7]); break;                              // sname: system state (#95 LED)
        case 22: AwtoPutNvFlush(); break;                                                          // nvw: NVRAM flush result (#151)
        default: break;
    }
    AwtoSyncTxt(ucRow - 1, 1);
}
#undef ulV
#undef usMs

static BYTE AwtoSrcStyle(BYTE ucI)
{
    return (ucI == AwtoSrcSel()) ? AWTO_T_STYLE_ONACC : AWTO_T_STYLE_TEXT;
}

static BYTE AwtoPsValue(BYTE ucR, WORD usDt)    // current value of signal row ucR; usDt = ms since the last poll (cnt rows)
{
    BYTE ucPort = _D1_INPUT_PORT + tAwtoPsPort[ucR];
    WORD usA = tAwtoPsA[ucR];
    BYTE ucV;

    switch(tAwtoPsSrc[ucR])
    {
        case AWTO_PS_SRC_IN:
            ucV = g_stAwtoGpio.ucIn[usA];
            return (tAwtoPsB[ucR] != 0) ? (ucV == 0) : (ucV != 0);
        case AWTO_PS_SRC_CNT:
            ucV = g_pucAwtoInCnt[usA] - s_pucSrcCnt[usA];
            s_pucSrcCnt[usA] = g_pucAwtoInCnt[usA];
            return (usDt == 0) ? 0 : (BYTE)(((DWORD)ucV * 1000 + usDt / 2) / usDt);
        case AWTO_PS_SRC_XREG:
            return ((ScalerGetByte(usA) & tAwtoPsB[ucR]) != 0);
        case AWTO_PS_SRC_CABLE:
            return SysSourceGetCableDetect(ucPort);
        case AWTO_PS_SRC_DDC:
            return AwtoDdcLive(tAwtoPsPort[ucR]);
        default:
            return (AwtoTmdsIdleKhz((BYTE)usA) != 0);
    }
}

static void AwtoPsField(BYTE ucR, BYTE ucV, BYTE ucStyle)    // value of signal row ucR at its column
{
    AwtoFieldBegin();
    if(tAwtoPsSrc[ucR] == AWTO_PS_SRC_CNT)
    {
        AwtoPutNum(ucV, 1);
        AwtoPutStr("/s");
        AwtoPutCol(5);
    }
    else
    {
        AwtoPutChar((ucV != 0) ? '+' : '-');
    }
    AwtoFieldEnd(AWTO_SRC_PROW(tAwtoPsPort[ucR] + 1) + 1, tAwtoPsCol[ucR], ucStyle);
}

// Rate of a port: the active port's timing, the measured timing while syncing, else what its receiver has without a switch.
static void AwtoSrcRate(BYTE ucPort)
{
    DWORD ulK;

    if((ucPort == SysSourceGetInputPort()) && (SysModeGetModeState() == _MODE_STATUS_ACTIVE))
    {
        AwtoPutNum(GET_INPUT_TIMING_HWIDTH(), 1);
        AwtoPutChar('x');
        AwtoPutNum(GET_INPUT_TIMING_VHEIGHT(), 1);
        AwtoPutChar(' ');
        if(g_stAwtoFreq.ucValid != 0)
        {
            AwtoPutMilli(g_stAwtoFreq.ulVFreqmHz);
            AwtoPutStr("Hz ");
            AwtoPutMilli(g_stAwtoFreq.ulPclkHz / 1000);
            AwtoPutStr("MHz");
            return;
        }
        AwtoPutTenths(GET_INPUT_TIMING_VFREQ());
        AwtoPutStr("Hz ");
        AwtoPutTenths(ScalerSyncGetInputPixelClk());
        AwtoPutStr("MHz");
        return;
    }
#if(_DP_SUPPORT == _ON)
    if(AwtoPortIsDp(ucPort) != 0)
    {
        ulK = ScalerDpGetLaneCount(ucPort);
        if((ulK == 0) || (SysSourceGetCableDetect(ucPort) == _FALSE))
        {
            AwtoCardTxt(AWTO_CT_NOLINK);
            return;
        }
        AwtoCardTxt(AWTO_CT_DPLINK);
        AwtoPutChar(' ');
        AwtoPutDpRate(ScalerDpGetLinkRate(ucPort), (BYTE)ulK);       // DPCD 100h / 101h: the last training
        return;
    }
#endif
    ulK = AwtoTmdsIdleKhz((ucPort == _D2_INPUT_PORT) ? 0x71 : 0x72);
    if(ulK == 0)
    {
        AwtoPutChar('-');
        return;
    }
    AwtoCardTxt(AWTO_CT_TMDS);
    AwtoPutTenths((ulK + 50) / 100);
    AwtoCardTxt(AWTO_CT_HZ + 2);
}

static WORD AwtoSrcRateKey(BYTE ucPort)         // cheap change key of what AwtoSrcRate prints (no text, no division)
{
    if((ucPort == SysSourceGetInputPort()) && (SysModeGetModeState() == _MODE_STATUS_ACTIVE))
    {
        if(g_stAwtoFreq.ucValid != 0)
        {
            return 0x8000 ^ GET_INPUT_TIMING_HWIDTH() ^ (GET_INPUT_TIMING_VHEIGHT() << 4) ^ (WORD)g_stAwtoFreq.ulVFreqmHz ^
                   (WORD)(g_stAwtoFreq.ulPclkHz >> 10);
        }
        return 0x8001 ^ GET_INPUT_TIMING_HWIDTH() ^ (GET_INPUT_TIMING_VHEIGHT() << 4) ^ GET_INPUT_TIMING_VFREQ();
    }
#if(_DP_SUPPORT == _ON)
    if(AwtoPortIsDp(ucPort) != 0)
    {
        return 0x4000 | ((WORD)SysSourceGetCableDetect(ucPort) << 13) | ((WORD)ScalerDpGetLaneCount(ucPort) << 8) |
               ScalerDpGetLinkRate(ucPort);
    }
#endif
    return (WORD)(AwtoTmdsIdleKhz((ucPort == _D2_INPUT_PORT) ? 0x71 : 0x72) >> 6);    // 64 kHz steps: count noise is no change
}

// Port item i: state, stage, rate fields; bAll = draw even if unchanged (full draw).
static void AwtoSrcPortFields(BYTE ucI, bit bAll)
{
    BYTE ucPort = AwtoSrcPort(ucI);
    BYTE ucK = ucPort - _D1_INPUT_PORT;
    BYTE ucStyle = AwtoSrcStyle(ucI);
    BYTE ucV;
    WORD usKey;

    ucV = ui_port_state(ucK);
    if((bAll != 0) || (ucV != s_pucSrcSt[ucK]))
    {
        s_pucSrcSt[ucK] = ucV;
        AwtoFieldBegin();
        AwtoCardTxt((ucV == AWTO_UPS_DISABLED) ? AWTO_CT_DISABLED : (AWTO_CT_STATE + ucV));
        AwtoPutCol(10);
        AwtoFieldEnd(AWTO_SRC_PROW(ucI), AWTO_SRC_STATE_COL, (ucStyle == AWTO_T_STYLE_ONACC) ? ucStyle : ((ucV == 3) ? AWTO_T_STYLE_TEXT : AWTO_T_STYLE_DIM));
    }
    ucV = AwtoSyncStage(ucPort);
    if((bAll != 0) || (ucV != s_pucSrcStage[ucK]))
    {
        s_pucSrcStage[ucK] = ucV;
        AwtoFieldBegin();
        AwtoCardTxt(AWTO_CT_STAGE + ucV);
        AwtoPutCol(AWTO_SRC_RATE_COL - AWTO_SRC_STAGE_COL);
        AwtoFieldEnd(AWTO_SRC_PROW(ucI) + 2, AWTO_SRC_STAGE_COL, ucStyle);
    }
    usKey = AwtoSrcRateKey(ucPort);
    if((bAll != 0) || (usKey != s_pusSrcRate[ucK]))
    {
        s_pusSrcRate[ucK] = usKey;
        AwtoFieldBegin();
        AwtoSrcRate(ucPort);
        AwtoPutCol(AWTO_SRC_RATE_W);
        AwtoFieldEnd(AWTO_SRC_PROW(ucI) + 2, AWTO_SRC_RATE_COL, ucStyle);
    }
}

static void AwtoSrcSigs(bit bAll, WORD usDt)
{
    BYTE ucR, ucV;

    for(ucR = 0; ucR < AWTO_PS_N; ucR++)
    {
        ucV = AwtoPsValue(ucR, usDt);
        if((bAll != 0) || (ucV != s_pucSrcSig[ucR]))
        {
            s_pucSrcSig[ucR] = ucV;
            AwtoPsField(ucR, ucV, AwtoSrcStyle(tAwtoPsPort[ucR] + 1));
        }
    }
}

static void AwtoSrcLog(void)                    // the last AWTO_SRC_LOGN lines of the current episode
{
    BYTE ucSeq = g_stAwtoSync.ucSeq;
    BYTE ucN = AWTO_SYNC_BACK(ucSeq, g_stAwtoSync.ucEpSeq);
    BYTE ucL;

    s_ucSrcLogSeq = ucSeq;
    if(ucN > AWTO_SRC_LOGN)
    {
        ucN = AWTO_SRC_LOGN;
    }
    for(ucL = 0; ucL < AWTO_SRC_LOGN; ucL++)
    {
        if(ucL < ucN)
        {
            AwtoSyncLine(AWTO_SYNC_BACK(ucSeq, ucN - ucL));
        }
        AwtoTextLine(AWTO_SRC_LOGHDR + 1 + ucL, AWTO_T_STYLE_DIM);
    }
}

static void AwtoSourceRows(void)                // Auto, then each port with its state, signals, stage and rate; the log
{
    BYTE ucSel = AwtoSrcSel();
    BYTE ucI, ucR;

    ucR = (ucSel == 0) ? AWTO_SRC_ROW0 : AWTO_SRC_PROW(ucSel);
    osd_tc_bar(AWTO_WIN_HL, 2, (WORD)ucR * osd_rh, (WORD)AWTO_SRC_COLS * osd_cw - 3,
               (WORD)(ucR + ((ucSel == 0) ? 1 : 3)) * osd_rh - 1, 1);
    for(ucI = 0; ucI <= AWTO_SRC_PORTS; ucI++)
    {
        if(ucI == 0)
        {
            AwtoCardTxt(AWTO_CT_AUTO);
            AwtoTextLine(AWTO_SRC_ROW0, AwtoSrcStyle(0));
            continue;
        }
        AwtoPortName(AwtoSrcPort(ucI));
        AwtoTextLine(AWTO_SRC_PROW(ucI), AwtoSrcStyle(ucI));
        for(ucR = 0; ucR < AWTO_PS_N; ucR++)          // signal labels; values follow
        {
            if(tAwtoPsPort[ucR] + 1 == ucI)
            {
                AwtoPutCol(tAwtoPsLblCol[ucR]);
                AwtoPsLbl(ucR);
            }
        }
        AwtoTextLine(AWTO_SRC_PROW(ucI) + 1, AwtoSrcStyle(ucI));
        AwtoTextLine(AWTO_SRC_PROW(ucI) + 2, AwtoSrcStyle(ucI));
        AwtoSrcPortFields(ucI, 1);
    }
    AwtoSrcSigs(1, 0);
    AwtoCardTxt(AWTO_CT_SYNCLOG);
    AwtoTextLine(AWTO_SRC_LOGHDR, AWTO_T_STYLE_TEXT);
    AwtoSrcLog();
    s_usSrcPoll = ((WORD)AwtoMs());
}

static bit AwtoSourceNoPicture(void)            // power saving / no signal / no support: the SDK hands back to its pop-up timers
{
    BYTE ucMode = SysModeGetModeState();

    return ((ucMode == _MODE_STATUS_POWER_SAVING) || (ucMode == _MODE_STATUS_NOSIGNAL) || (ucMode == _MODE_STATUS_NOSUPPORT));
}

// #139 the selector stays open until a choice or a cancel. With no picture the monitor must still sleep: after
// AWTO_SRC_SLEEP_SEC without a key, the SDK power-saving card (2 s) and power saving. With a picture: no timer.
static void AwtoSrcSleepArm(void)
{
    if(AwtoSourceNoPicture() == _TRUE)
    {
        ScalerTimerReactiveTimerEvent(SEC(AWTO_SRC_SLEEP_SEC), _USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
    }
    else
    {
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
    }
}

// The one way in (SOURCE, OSD event 7 = no signal / wake): preset to the current input (Auto while auto-scanning).
// Opening alone arms no idle commit: the selector stays (#139) until a step key starts the AWTO_SRC_IDLE_COMMIT_MS wait.
void AwtoSourceOpen(BYTE ucWhy)
{
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
    if(SysSourceGetScanType() == _SOURCE_SWITCH_AUTO_IN_GROUP)
    {
        SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_AUTO);
    }
    else
    {
        SET_OSD_INPUT_PORT_OSD_ITEM(AwtoSrcItem(SysSourceGetInputPort()));
    }
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_GO_TO_POWER_SAVING);
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_CABLE);
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_SHOW_NO_SIGNAL);
    AwtoSrcSleepArm();
    SET_OSD_STATE(_MENU_HOTKEY_SOURCE);
    OsdFuncSetOsdItemFlag();
    g_usBackupValue = GET_OSD_INPUT_PORT_OSD_ITEM();
    AwtoSrcRing(ucWhy, g_usBackupValue);
    AwtoCardOpenW(AWTO_SRC_COLS, AWTO_SRC_LINES, AWTO_CT_INPUT);
    AwtoSourceRows();
    AwtoCardShow();
    UserCommonInterfacePanelPowerAction(AWTO_PNL_REQ(_BACKLIGHT_ON, AWTO_PNL_BY_SELECTOR));
}

static void AwtoSourceStep(bit bBack)
{
    BYTE ucSel = AwtoSrcSel();

    if(bBack != 0)
    {
        ucSel = (ucSel == 0) ? AWTO_SRC_PORTS : (ucSel - 1);
    }
    else
    {
        ucSel = (ucSel == AWTO_SRC_PORTS) ? 0 : (ucSel + 1);
    }
    AwtoSrcSet(ucSel);
}

static void AwtoSourceClose(void)
{
    if(AwtoSourceNoPicture() == _TRUE)
    {
        ScalerTimerReactiveTimerEvent(SEC(0), _USER_TIMER_EVENT_OSD_SHOW_POWER_SAVING);
    }
    else
    {
        OsdDispDisableOsd();
    }
}

// Auto source select (#132): the selector's Auto row and the AUTO key with nothing open. The SDK auto search takes the first input
// with a signal; the scan type is stored at the gate ("Saving to memory"). ucWho = AWTO_SYS_BY_* of the request line.
void AwtoSourceAuto(BYTE ucWho)
{
    SET_OSD_INPUT_PORT_OSD_ITEM(_OSD_INPUT_AUTO);
    AwtoSyncBegin(AWTO_SYNC_K_SWITCH, 0xFF);
    SysSourceSetScanType(_SOURCE_SWITCH_AUTO_IN_GROUP);
    SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_SEARCH, ucWho);
    UserCommonNVRamSetSystemData(_SOURCE_SCAN_TYPE, SysSourceGetScanType());
    AwtoNvCommitSel();                          // #151: the chosen input is stored at the gate ("Saving to memory")
}

// Take the highlighted item: AUTO key (AWTO_SYS_BY_SELECTOR) or the idle commit (AWTO_SYS_BY_SELECTOR_IDLE).
static void AwtoSourceTake(BYTE ucWho)
{
    BYTE ucItem = GET_OSD_INPUT_PORT_OSD_ITEM();
    BYTE ucPort;

    if(GET_OSD_DP_VERSION_HOTKEY_DISP() != _OFF)
    {
        AwtoSrcRing(AWTO_SEL_EV_DPVER, ucItem);
        return;
    }
    if(g_usBackupValue == ucItem)
    {
        AwtoSrcRing((ucWho == AWTO_SYS_BY_SELECTOR_IDLE) ? AWTO_SEL_EV_KEPT_IDLE : AWTO_SEL_EV_KEPT_AUTO, ucItem);
        AwtoSourceClose();
    }
    else if(ucItem == _OSD_INPUT_AUTO)
    {
        AwtoSourceAuto(ucWho);
    }
    else
    {
        ucPort = (ucItem >= _OSD_INPUT_D0) ? (ucItem - _OSD_INPUT_D0 + _D0_INPUT_PORT) : _NO_INPUT_PORT;
        if(ucPort == _NO_INPUT_PORT)
        {
            AwtoSyncPush(AWTO_SYNC_EV_SEL, AWTO_SEL_EV_NOPORT, ucItem);    // not a port of this board: the selector stays up
            return;
        }
        if(AwtoPortCable(ucPort) == _FALSE)
        {
            AwtoSwEvent(AWTO_SW_EV_DEADPORT, 1);    // #84: no cable on the chosen port: refused, the selector stays up
            AwtoSrcRing(AWTO_SEL_EV_NOCABLE, ucItem);
            return;
        }
        AwtoPortSelect(ucPort, AWTO_PORT_WHY_SELECTOR);     // #81: a disabled port is enabled (stored), then the switch
        SET_FORCE_POW_SAV_STATUS(_FALSE);
        SysSourceSwitchInputPort(ucPort);
        SysSourceSetScanType(_SOURCE_SWITCH_FIXED_PORT);
        SysMachineRequest(AWTO_SYS_REQ_MODE | _MODE_ACTION_RESET_TO_SEARCH, ucWho);
        UserCommonNVRamSetSystemData(_SEARCH_PORT, SysSourceGetInputPort());
        UserCommonNVRamSetSystemData(_SOURCE_SCAN_TYPE, SysSourceGetScanType());
        AwtoNvCommitSel();                      // #151: the chosen input is stored at the gate ("Saving to memory")
    }
    SET_OSD_STATE(_MENU_NONE);
}

void AwtoSourceIdle(void)                       // OSD_DISABLE timer, selector open: no key for AWTO_SRC_IDLE_COMMIT_MS
{
    AwtoSourceTake(AWTO_SYS_BY_SELECTOR_IDLE);
}

// SDK OSD reset (mode reset, signal back in no signal) with the selector open: a highlighted other input is taken (the
// user's choice, never dropped silently, #132); else one line says what closed it. OsdDispDisableOsd follows in the caller.
void AwtoSourceReset(void)
{
    BYTE ucItem = GET_OSD_INPUT_PORT_OSD_ITEM();

    if(GET_OSD_STATE() != _MENU_HOTKEY_SOURCE)
    {
        return;
    }
    ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
    if(ucItem != g_usBackupValue)
    {
        AwtoSourceTake(AWTO_SYS_BY_SELECTOR_RESET);
        if(GET_OSD_STATE() != _MENU_HOTKEY_SOURCE)
        {
            return;                             // taken: switch + request lines
        }
    }
    AwtoSrcRing(AWTO_SEL_EV_RESET, ucItem);     // nothing to take, or the take refused (its line came first)
}

// Selector open (_MENU_HOTKEY_SOURCE), key from the key router (#129). Roles as before #132: AUTO takes, MENU cancels.
// SOURCE / UP step forward, DOWN back (wrap); every step restarts the idle commit.
void AwtoSourceKey(BYTE ucKey)
{
    if((ucKey == _RIGHT_KEY_MESSAGE) || (ucKey == _LEFT_KEY_MESSAGE) || (ucKey == AWTO_KEY_MSG_SOURCE))
    {
        AwtoSourceStep(ucKey == _LEFT_KEY_MESSAGE);
        AwtoSourceRows();
        AwtoSrcSleepArm();                      // #151: a step is never stored
        ScalerTimerReactiveTimerEvent(AWTO_SRC_IDLE_COMMIT_MS, _USER_TIMER_EVENT_OSD_DISABLE);
    }
    else if(ucKey == _EXIT_KEY_MESSAGE)        // MENU: cancel, the choice goes back
    {
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
        if(g_usBackupValue != GET_OSD_INPUT_PORT_OSD_ITEM())
        {
            SET_OSD_INPUT_PORT_OSD_ITEM(g_usBackupValue);
        }
        AwtoSrcRing(AWTO_SEL_EV_CANCEL, g_usBackupValue);
        AwtoSourceClose();
    }
    else if(ucKey == _MENU_KEY_MESSAGE)        // AUTO: take the choice now
    {
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
        AwtoSourceTake(AWTO_SYS_BY_SELECTOR);
    }
}

//---- backlight bar (#132): UP / DOWN with a picture and nothing open. One card row: bar (OSD windows) + value. ----
extern void osd_tc_bar_off(BYTE ucWin);
#define AWTO_BL_ROW         AWTO_CARD_ROW0
#define AWTO_BL_BAR_COL     1                   // bar: cells 1..AWTO_BL_VAL_COL - 2, value right of it
#define AWTO_BL_VAL_COL     23
#define AWTO_BL_VAL_W       4                   // "100%"
#define AWTO_BL_MAX         100                 // registry brightness max (percent)
#define AWTO_WIN_BL_EDGE    3                   // bar outline (accent), inside (surface), fill (accent): above the card windows 0..2
#define AWTO_WIN_BL_IN      4
#define AWTO_WIN_BL_FILL    5
#define AWTO_BL_X0          ((WORD)AWTO_BL_BAR_COL * osd_cw)
#define AWTO_BL_X1          ((WORD)(AWTO_BL_VAL_COL - 1) * osd_cw - 1)
#define AWTO_BL_Y0          ((WORD)AWTO_BL_ROW * osd_rh + 3)
#define AWTO_BL_Y1          ((WORD)(AWTO_BL_ROW + 1) * osd_rh - 4)
#define AWTO_BL_INSET       3                   // fill inset from the outline, px (1 px edge, 2 px surface gap)

static void AwtoBlDraw(void)                    // fill width and value text of the stored backlight
{
    BYTE ucV = (BYTE)AWTO_SET(BRIGHTNESS);
    WORD usW = (AWTO_BL_X1 - AWTO_BL_X0 - 2 * AWTO_BL_INSET) * ucV / AWTO_BL_MAX;

    if(usW == 0)
    {
        osd_tc_bar_off(AWTO_WIN_BL_FILL);
    }
    else
    {
        osd_tc_bar(AWTO_WIN_BL_FILL, AWTO_BL_X0 + AWTO_BL_INSET, AWTO_BL_Y0 + AWTO_BL_INSET, AWTO_BL_X0 + AWTO_BL_INSET + usW - 1,
                   AWTO_BL_Y1 - AWTO_BL_INSET, AWTO_BAR_ACCENT);
    }
    AwtoFieldBegin();
    AwtoPutNum(ucV, 1);
    AwtoPutChar('%');
    AwtoPutCol(AWTO_BL_VAL_W);
    AwtoFieldEnd(AWTO_BL_ROW, AWTO_BL_VAL_COL, AWTO_T_STYLE_TEXT);
}

void AwtoBlKey(BYTE ucKey)                      // UP = brighter, DOWN = darker; the first press opens the bar
{
    extern unsigned char set_put(unsigned char ucId, int iV, unsigned char ucNow);

    if(GET_OSD_STATE() != _MENU_HOTKEY_BACKLIGHT)
    {
        AwtoCardOpen(AWTO_CARD_ROW0 + 2, AWTO_CT_BACKLIGHT);
        osd_tc_place(50, AWTO_BL_VPOS_PCT, GET_OSD_NVRAM_DOUBLE_SIZE());
        osd_tc_bar(AWTO_WIN_BL_EDGE, AWTO_BL_X0, AWTO_BL_Y0, AWTO_BL_X1, AWTO_BL_Y1, AWTO_BAR_ACCENT);
        osd_tc_bar(AWTO_WIN_BL_IN, AWTO_BL_X0 + 1, AWTO_BL_Y0 + 1, AWTO_BL_X1 - 1, AWTO_BL_Y1 - 1, AWTO_BAR_SURFACE);
        AwtoTextLine(AWTO_BL_ROW, AWTO_T_STYLE_TEXT);
        SET_OSD_STATE(_MENU_HOTKEY_BACKLIGHT);
    }
    set_put(AWTO_SET_BRIGHTNESS, AWTO_SET(BRIGHTNESS) + ((ucKey == _RIGHT_KEY_MESSAGE) ? AWTO_BL_KEY_STEP : -AWTO_BL_KEY_STEP), 1);
    AwtoBlDraw();
    AwtoCardShow();
}

void AwtoBlClose(void)                          // another key: the bar goes first (OsdDispDisableOsd commits the value)
{
    OsdDispDisableOsd();
}

// #139 console auto-open: once per episode, when the screen is ours to take (no menu / selector / logo / hold) and the
// episode has settled (ACTIVE / no signal / no support / power saving): opening it never delays the sync. Setting: registry
// sync_console (id 110); g_ucAwtoSyncCon = 0 also stops it (test harness, fw_sim osd_render.Session).
__xdata BYTE g_ucAwtoSyncCon = 1;
__xdata BYTE g_ucAwtoConAuto;                   // the console open now opened itself (not UP+DOWN / test cmd): SOURCE passes (#132)

static void AwtoSyncConPoll(void)
{
    if(g_stAwtoSync.ucOpenReq == 0)
    {
        return;
    }
    if(g_stAwtoSync.ucOpenReq == AWTO_SYNC_OPEN_KEY)    // #132 UP+DOWN wake: waits through the wake, only POWER off drops it
    {
        if(SysPowerGetPowerStatus() == _POWER_STATUS_OFF)
        {
            g_stAwtoSync.ucOpenReq = 0;
            return;
        }
    }
    else if((g_ucAwtoSyncCon == 0) || (AWTO_SET(SYNC_CONSOLE) == 0) || (GET_OSD_STATE() == _MENU_HOTKEY_SOURCE) ||
            (SysPowerGetPowerStatus() == _POWER_STATUS_OFF) || (SysPowerGetPowerStatus() == _POWER_STATUS_SAVING))
    {
        g_stAwtoSync.ucOpenReq = 0;             // off, the selector's log pane shows it, or no screen
        return;
    }
    if(g_stAwtoSync.ucDone == 0)
    {
        return;                                 // every episode ends in one of the settled modes (search time-outs)
    }
    if((s_ucConOpen != 0) && (AwtoConLost() == 0))
    {
        BYTE ucP = s_ucConOpen;                 // open since power-on: display setting's panel cycle blanks the OSD;

        g_stAwtoSync.ucOpenReq = 0;             // redraw it as UP+DOWN opens it (re-applying the scroll alone stayed blank)
        s_ucConOpen = 0;
        AwtoDiagConsole(ucP);
        return;
    }
    if((SysPowerGetPowerStatus() != _POWER_STATUS_NORMAL) || (GET_OSD_STATE() != _MENU_NONE) || (g_ucAwtoMenuOn != 0) || AWTO_KEY_TEST_ON() ||
       (isr_g_stAwtoDiag.ucHold != 0))
    {
        return;
    }
    g_ucAwtoConAuto = (g_stAwtoSync.ucOpenReq != AWTO_SYNC_OPEN_KEY);
    g_stAwtoSync.ucOpenReq = 0;
    AwtoSyncPush(AWTO_SYNC_EV_CONSOLE, 0, 0);
    AwtoDiagConsole(1);                         // its log backfills the episode (AwtoConLogInit)
}

#if(_AWTO_BOOT_PANEL_EARLY == _ON)
// #144 power-on, mode INITIAL (RTD2014Osd.c, before the panel comes on), and a source-event wake (awto_sync.inc): the
// console with the live log, no logo.
// The auto-open request stays: at the settled mode AwtoSyncConPoll reopens it if display setting took the OSD.
void AwtoBootConsole(void)
{
    if((g_stAwtoSync.ucOpenReq != AWTO_SYNC_OPEN_KEY) && ((g_ucAwtoSyncCon == 0) || (AWTO_SET(SYNC_CONSOLE) == 0)))
    {
        return;
    }
    ScalerDDomainBackgroundEnable(_ENABLE);    // black frame under the OSD: also the short T3 (own pattern) at panel on
    AwtoSyncPush(AWTO_SYNC_EV_CONSOLE, 0, 0);
    s_ucConOpen = 0;                            // wake: power saving lost the OSD of a console left open; draw it anew
    AwtoDiagConsole(1);
    g_ucAwtoConAuto = (g_stAwtoSync.ucOpenReq != AWTO_SYNC_OPEN_KEY);
}
#endif

// Every main-loop pass (AwtoGpioPoll): console log lines, auto-open, selector fields every AWTO_SRC_POLL_MS.
void AwtoOsdSyncPoll(void)
{
    WORD usDt;                                  // ms since the last selector poll (XDATA local: one WORD, #157 merge)
    BYTE ucI;

    if(s_ucConOpen != 0)
    {
        if(s_ucConRedraw != 0)                  // terminal reached the roll-up limit: one full redraw, then it rolls again
        {
            s_ucConOpen = 0;
            AwtoDiagConsole(AWTO_CON_MAIN);
        }
        AwtoConLogSync();
        AwtoConTitlePoll();                     // #157 live title fields
    }
    AwtoSyncConPoll();
    if((GET_OSD_STATE() != _MENU_HOTKEY_SOURCE) || (g_ucOsdWidth != AWTO_SRC_COLS))
    {
        return;
    }
    usDt = ((WORD)AwtoMs()) - s_usSrcPoll;
    if(usDt < AWTO_SRC_POLL_MS)
    {
        return;
    }
    s_usSrcPoll += usDt;
    for(ucI = 1; ucI <= AWTO_SRC_PORTS; ucI++)
    {
        AwtoSrcPortFields(ucI, 0);
    }
    AwtoSrcSigs(0, usDt);
    if(s_ucSrcLogSeq != g_stAwtoSync.ucSeq)
    {
        AwtoSrcLog();
    }
}

//---- message cards (#124) ----
static void AwtoInfoLabel(BYTE ucT)
{
    AwtoCardTxt(ucT);
    AwtoPutCol(AWTO_INFO_VAL_COL);
}

static void AwtoInfoTenths(WORD usV)            // SDK 0.1-unit value (no exact measurement yet), as the awto menu shows it
{
    AwtoPutNum(usV / 10, 1);
    AwtoPutChar('.');
    AwtoPutNum(usV % 10, 1);
}

// Input information (DOWN, mode ACTIVE): what the SDK pop-up showed, exact frequencies from awto_freq (#34) when measured.
static void AwtoInfoCard(void)
{
    BYTE ucPort = SysSourceGetInputPort();
    BYTE ucRow = AWTO_CARD_ROW0;
    BYTE ucV;
    _Bool bActive = (SysModeGetModeState() == _MODE_STATUS_ACTIVE);
    _Bool bDp = AwtoPortIsDp(ucPort);

    AwtoCardOpen(AWTO_CARD_ROW0 + (bActive ? 6 : 2) + (bDp ? 2 : 0) + 1, AWTO_CT_INFO);
    AwtoInfoLabel(AWTO_CT_INPUT);
    AwtoPortName(ucPort);
    AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
    if(bActive == 0)
    {
        AwtoInfoLabel(AWTO_CT_STATUS);
        AwtoCardTxt(AWTO_CT_STATE + ui_port_state(ucPort - _D1_INPUT_PORT));
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
    }
    else
    {
        AwtoInfoLabel(AWTO_CT_RES);
        AwtoPutNum(GET_INPUT_TIMING_HWIDTH(), 1);
        AwtoPutChar('x');
        AwtoPutNum(GET_INPUT_TIMING_VHEIGHT(), 1);
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
        AwtoInfoLabel(AWTO_CT_REFRESH);
        if(g_stAwtoFreq.ucValid != 0)
        {
            AwtoPutMilli(g_stAwtoFreq.ulVFreqmHz);
        }
        else
        {
            AwtoInfoTenths(GET_INPUT_TIMING_VFREQ());
        }
        AwtoCardTxt(AWTO_CT_HZ);
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
        AwtoInfoLabel(AWTO_CT_HFREQ);
        if(g_stAwtoFreq.ucValid != 0)
        {
            AwtoPutMilli(g_stAwtoFreq.ulHFreqHz);
        }
        else
        {
            AwtoInfoTenths(GET_INPUT_TIMING_HFREQ());
        }
        AwtoCardTxt(AWTO_CT_HZ + 1);
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
        AwtoInfoLabel(AWTO_CT_PCLK);
        if(g_stAwtoFreq.ucValid != 0)
        {
            AwtoPutMilli(g_stAwtoFreq.ulPclkHz / 1000);
        }
        else
        {
            AwtoInfoTenths(ScalerSyncGetInputPixelClk());
        }
        AwtoCardTxt(AWTO_CT_HZ + 2);
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
        AwtoInfoLabel(AWTO_CT_HDCP);
        ucV = ScalerSyncHdcpCheckEnabled(ucPort);          // 0 = off, else version 0x14 / 0x22 | 0x80 = repeater
        if(ucV == 0)
        {
            AwtoCardTxt(AWTO_CT_OFF);
        }
        else
        {
            AwtoPutNum((ucV & 0x7F) >> 4, 1);
            AwtoPutChar('.');
            AwtoPutNum(ucV & 0x0F, 1);
            AwtoCardTxt(AWTO_CT_SINK + (((ucV & 0x80) != 0) ? 1 : 0));
        }
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
    }
#if(_DP_SUPPORT == _ON)
    if(bDp != 0)
    {
        AwtoInfoLabel(AWTO_CT_DPLINK);
        AwtoPutNum(ScalerDpGetLaneCount(ucPort), 1);
        AwtoCardTxt(AWTO_CT_LANES);
        ucV = ScalerDpGetLinkRate(ucPort);
        if(ucV == _DP_LINK_RBR)
        {
            AwtoCardTxt(AWTO_CT_RBR);
        }
        else if(ucV == _DP_LINK_HBR)
        {
            AwtoCardTxt(AWTO_CT_RBR + 1);
        }
        else if(ucV == _DP_LINK_HBR2)
        {
            AwtoCardTxt(AWTO_CT_RBR + 2);
        }
        else
        {
            AwtoPutHex2(ucV);
        }
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
        AwtoInfoLabel(AWTO_CT_SWING);
        for(ucV = _DP_LANE_0; ucV <= _DP_LANE_3; ucV++)  // voltage swing / pre-emphasis level per lane
        {
            if(ucV != _DP_LANE_0)
            {
                AwtoPutChar(' ');
            }
            AwtoPutNum(ScalerDpGetLaneVoltageSwingLv(ucPort, ucV), 1);
            AwtoPutChar('/');
            AwtoPutNum(ScalerDpGetLanePreEmpLv(ucPort, ucV), 1);
        }
        AwtoTextLine(ucRow++, AWTO_T_STYLE_TEXT);
    }
#endif
    AwtoCardShow();
}

#ifdef _AWTO_NEW_SETTINGS
// #151 "Saving to memory": up while the flush gate writes after a menu / selector close; off after AWTO_SAVE_CARD_MS
void AwtoSaveCard(void)
{
    AwtoCardOpen(AWTO_CARD_ROW0 + 2, AWTO_CT_AWTO);
    AwtoCardTxt(AWTO_CT_SAVING);
    AwtoCardCentre(AWTO_CARD_ROW0, AWTO_T_STYLE_TEXT);
    AwtoCardShow();
    ScalerTimerReactiveTimerEvent(AWTO_SAVE_CARD_MS, _USER_TIMER_EVENT_OSD_DISABLE);
}
#endif

// Every SDK message card: our text card. Fail-safe = No Support (one warning card); switch DDC/CI port names the input (#114).
void OsdDispOsdMessage(EnumOSDDispMsg enumMessage)  // replaces the SDK body (keil2sdcc _K124)
{
    BYTE ucT;

    if((GET_OSD_STATE() == _MENU_HOTKEY_SOURCE) && ((enumMessage == _OSD_DISP_NOSIGNAL_MSG) || (enumMessage == _OSD_DISP_NOCABLE_MSG)))
    {
        AwtoSrcSleepArm();                      // #139: the open selector stays (its rows show the state); the SDK's 3 s is not restarted
        return;
    }
    if((enumMessage == _OSD_DISP_INPUT_SIGNAL_MSG) && (s_ucConOpen != 0) && (AwtoConLost() == 0))
    {
        return;                                 // #144: the open console keeps the screen; its log has the timing lines
    }
    OsdDispDisableOsd();
    if(enumMessage == _OSD_DISP_INPUT_SIGNAL_MSG)
    {
        AwtoInfoCard();
        return;
    }
    switch(enumMessage)
    {
        case _OSD_DISP_NOSIGNAL_MSG:            ucT = AWTO_CT_NOSIGNAL; break;
        case _OSD_DISP_NOCABLE_MSG:             ucT = AWTO_CT_NOCABLE; break;
        case _OSD_DISP_AUTO_CONFIG_MSG:         ucT = AWTO_CT_AUTOADJ; break;
        case _OSD_DISP_AUTO_COLOR_MSG:          ucT = AWTO_CT_AUTOCOL; break;
        case _OSD_DISP_SWITCH_DDCCI_PORT_MSG:   ucT = AWTO_CT_DDCCI; break;
        case _OSD_DISP_POWER_SAVING_MSG:        ucT = AWTO_CT_PSAVE; break;
        case _OSD_DISP_PANEL_UNIFORMITY_ONOFF_MSG: ucT = AWTO_CT_PANEL; break;
        default:                                ucT = AWTO_CT_NOSUPPORT; break;     // no support, fail-safe
    }
    AwtoCardOpen(AWTO_CARD_ROW0 + 3, AWTO_CT_AWTO);     // message, second line, pad row
    AwtoCardTxt(ucT);
    if(ucT == AWTO_CT_DDCCI)
    {
        AwtoPortName(SysSourceGetInputPort());
    }
    AwtoCardCentre(AWTO_CARD_ROW0, AWTO_T_STYLE_TEXT);
    if(ucT == AWTO_CT_PANEL)
    {
        AwtoCardTxt(AWTO_CT_ON + ((GET_OSD_PANEL_UNIFORMITY() == _ON) ? 0 : 1));
        AwtoCardCentre(AWTO_CARD_ROW0 + 1, AWTO_T_STYLE_TEXT);
    }
    else if((ucT == AWTO_CT_NOSIGNAL) || (ucT == AWTO_CT_NOCABLE) || (ucT == AWTO_CT_NOSUPPORT))
    {
        AwtoPortName(SysSourceGetInputPort());
        AwtoCardCentre(AWTO_CARD_ROW0 + 1, AWTO_T_STYLE_DIM);
    }
    AwtoCardShow();
}

//---- #39 key test screen: rows of the debug pop-up; redrawn by AwtoKeyScan every AWTO_KEY_REFRESH_MS while open ----
#ifdef _AWTO_NEW_SETTINGS
static void AwtoPutKeys(BYTE ucMask)            // front keys left to right, space separated
{
    if(ucMask == 0)
    {
        AwtoPutStr("NONE");
        return;
    }
    if((ucMask & AWTO_KM_SOURCE) != 0)
    {
        AwtoPutStr("SOURCE ");
    }
    if((ucMask & AWTO_KM_MENU) != 0)
    {
        AwtoPutStr("MENU ");
    }
    if((ucMask & AWTO_KM_DOWN) != 0)
    {
        AwtoPutStr("DOWN ");
    }
    if((ucMask & AWTO_KM_UP) != 0)
    {
        AwtoPutStr("UP ");
    }
    if((ucMask & AWTO_KM_AUTO) != 0)
    {
        AwtoPutStr("AUTO ");
    }
    if((ucMask & AWTO_KM_POWER) != 0)
    {
        AwtoPutStr("POWER");
    }
}

static void AwtoPutKeyMsg(BYTE ucMsg)            // one call per literal: a ?: chain of string literals printed garbage (keys2 render)
{
    if(ucMsg == _EXIT_KEY_MESSAGE)
    {
        AwtoPutStr("MENU");
    }
    else if(ucMsg == _RIGHT_KEY_MESSAGE)
    {
        AwtoPutStr("UP");
    }
    else if(ucMsg == _LEFT_KEY_MESSAGE)
    {
        AwtoPutStr("DOWN");
    }
    else if(ucMsg == _MENU_KEY_MESSAGE)
    {
        AwtoPutStr("AUTO");
    }
    else if(ucMsg == AWTO_KEY_MSG_SOURCE)
    {
        AwtoPutStr("SOURCE");
    }
    else
    {
        AwtoPutStr("NONE");
    }
}

static void AwtoPutAdc(BYTE ucCh, BYTE ucRaw)   // "A0 7C 15 0.484FS": raw hex, 5-bit code, fraction of full scale (reference not in the regdb)
{
    AwtoPutChar('A');
    AwtoPutNum(ucCh, 1);
    AwtoPutStr(" ");
    AwtoPutHex2(ucRaw);
    AwtoPutStr(" ");
    AwtoPutNum(ucRaw >> 3, 2);
    AwtoPutStr(" ");
    AwtoPutMilli((WORD)ucRaw * 125 / 32);       // R / 256 in thousandths
    AwtoPutStr("FS");
}

static BYTE AwtoKeyLetter(BYTE ucI)             // press log entry -> S M D U A P (lower case = injected), '-' = combo, ' ' = empty
{
    BYTE ucMask = g_stAwtoKey.pstLog[ucI].ucMask;
    BYTE ucMsg = g_stAwtoKey.pstLog[ucI].ucMsg;
    BYTE ucL = ' ';

    if(ucMask == 0)
    {
        ucL = (ucMsg == _EXIT_KEY_MESSAGE) ? 'M' : (ucMsg == _RIGHT_KEY_MESSAGE) ? 'U' : (ucMsg == _LEFT_KEY_MESSAGE) ? 'D' :
              (ucMsg == _MENU_KEY_MESSAGE) ? 'A' : (ucMsg == AWTO_KEY_MSG_SOURCE) ? 'S' : ' ';
    }
    else
    {
        ucL = (ucMask == AWTO_KM_SOURCE) ? 'S' : (ucMask == AWTO_KM_MENU) ? 'M' : (ucMask == AWTO_KM_DOWN) ? 'D' :
              (ucMask == AWTO_KM_UP) ? 'U' : (ucMask == AWTO_KM_AUTO) ? 'A' : (ucMask == AWTO_KM_POWER) ? 'P' : '-';
    }
    if(((g_stAwtoKey.pstLog[ucI].ucFlags & AWTO_KEY_F_INJ) != 0) && (ucL >= 'A') && (ucL <= 'Z'))
    {
        ucL += 'a' - 'A';
    }
    return ucL;
}

void AwtoOsdKeyLines(void)
{
    BYTE ucK;

    _Bool bFirst = (g_stAwtoKey.ucDrawn == 0);

    g_stAwtoKey.ucDrawn = 1;
    g_stAwtoKey.ucRedraws++;
    if(AwtoConLost() != 0) return;
    AwtoPanel(1);
    if(bFirst != 0)
    {
        AwtoPutCol(1);
        AwtoPutStr("KEY TEST");
        AwtoTextLine(0, AWTO_T_STYLE_ACCENT);
    }

    AwtoPutAdc(0, g_stAwtoKey.ucA0);
    AwtoShowLine(_OSD_MESSAGE_ROW_START, _PFONT_PAGE_0);
    AwtoPutAdc(1, g_stAwtoKey.ucA1);
    AwtoPutStr(" P30 ");                         // the POWER pin: 1 idle, 0 = pressed
    AwtoPutNum(g_stAwtoKey.ucP30 & AWTO_KEY_F_P30, 1);
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 1, _PFONT_PAGE_1);

    AwtoPutStr("KEY ");
    AwtoPutKeys(g_stAwtoKey.ucMask);
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 2, _PFONT_PAGE_2);

    AwtoPutStr("MSG ");
    AwtoPutKeyMsg(g_stAwtoKey.ucMsg);
    AwtoPutStr(" R");
    AwtoPutNum(g_stAwtoKey.ucFlags & 0x01, 1);
    AwtoPutNum((g_stAwtoKey.ucFlags >> 1) & 0x01, 1);
    AwtoPutStr(" H");
    AwtoPutNum((g_stAwtoKey.ucFlags >> 2) & 0x01, 1);
    if((g_stAwtoKey.ucFlags & AWTO_KEY_F_INJ) != 0)
    {
        AwtoPutStr(" INJ");
    }
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 3, _PFONT_PAGE_0);

    AwtoPutStr("LAST");
    for(ucK = AWTO_KEY_LAST_N; ucK != 0; ucK--)      // oldest left, newest right
    {
        AwtoPutStr(" ");
        AwtoPutChar(AwtoKeyLetter((g_stAwtoKey.ucCount - ucK) & (AWTO_KEY_LOG_N - 1)));
    }
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 4, _PFONT_PAGE_1);

    AwtoPutStr("N ");
    AwtoPutNum(g_stAwtoKey.ucCount, 1);
    AwtoPutStr(" CLOSE UP DOWN");
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 5, _PFONT_PAGE_2);
}
#else
void AwtoOsdKeyLines(void)
{
}
#endif

//---- GPIO table ----
// Diagnostic input table on the console (panel 0): one row per input in fw/awto/inputs.tsv, drawn with the Spleen text layer.
// The whole row is drawn once (console open); after that only the changed field of a changed input is written, at its exact column.
#ifdef _AWTO_NEW_SETTINGS
#define AWTO_G_ROWS         AWTO_IN_ROWS
#define AWTO_G_LINES        (AWTO_G_ROWS + 3)           // title, header, rows, footer: 42 lines in the 5x8 font
#define AWTO_G_L_FIRST      2
#define AWTO_TCOL_NAME      1
#define AWTO_TCOL_PIN       8
#define AWTO_TCOL_STATE     12
#define AWTO_TCOL_RAW       15
#define AWTO_TCOL_VALUE     20
#define AWTO_TCOL_DESC      28

// GENERATED-BEGIN awto_inputs
// kind 0 bit, 1 analog (deadband), 2 byte; src: see awto_gpio.inc AwtoInRead; flags bit0 = screen row, bit1 = logged in the ring
static const __code BYTE tAwtoInKindS[AWTO_IN_N] = {
    0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0,
    2, 2, 2, 2, 2, 2, 2, 2, 2, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 0, 0, 0, 0, 0, 0, 0};
static const __code BYTE tAwtoInPinS[AWTO_IN_N] = {
    65, 66, 67, 68, 69, 70, 74, 75, 94, 95, 96, 71,
    55, 56, 57, 58, 59, 60, 61, 62, 63, 194, 113, 1,
    14, 97, 198, 204, 206, 207, 208, 196, 159, 161, 184, 185,
    201, 202, 190, 0, 0, 0, 0, 0};
static const __code BYTE tAwtoInFlagsS[AWTO_IN_N] = {
    3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3,
    1, 1, 1, 1, 1, 1, 1, 1, 1, 3, 3, 3,
    3, 3, 3, 3, 1, 1, 1, 3, 3, 3, 3, 3,
    3, 3, 3, 2, 2, 2, 2, 2};

static void AwtoInName(BYTE ucI)
{
    switch(ucI)
    {
        case 0:
        case 1:
        case 2:
        case 3:
        case 4:
        case 5:
        case 6:
        case 7:
            AwtoPutStr("GPIO"); break;
        case 8:
            AwtoPutStr("ADC0"); break;
        case 9:
            AwtoPutStr("ADC1"); break;
        case 10:
            AwtoPutStr("ADC2"); break;
        case 11:
            AwtoPutStr("POWER"); break;
        case 12:
            AwtoPutStr("AVS"); break;
        case 13:
            AwtoPutStr("AHS"); break;
        case 14:
            AwtoPutStr("BM"); break;
        case 15:
            AwtoPutStr("BP"); break;
        case 16:
            AwtoPutStr("GM"); break;
        case 17:
            AwtoPutStr("GP"); break;
        case 18:
            AwtoPutStr("SOG"); break;
        case 19:
            AwtoPutStr("RM"); break;
        case 20:
            AwtoPutStr("RP"); break;
        case 21:
            AwtoPutStr("IR"); break;
        case 22:
            AwtoPutStr("HPSEL"); break;
        case 23:
            AwtoPutStr("H2HPD"); break;
        case 24:
            AwtoPutStr("H1HPD"); break;
        case 25:
            AwtoPutStr("DPHPD"); break;
        case 26:
            AwtoPutStr("H2CBL"); break;
        case 27:
            AwtoPutStr("H1CBL"); break;
        case 28:
            AwtoPutStr("DPS17"); break;
        case 29:
            AwtoPutStr("DPS15"); break;
        case 30:
            AwtoPutStr("DPS16"); break;
        case 31:
            AwtoPutStr("BLEN"); break;
        case 32:
            AwtoPutStr("PNLPW"); break;
        case 33:
            AwtoPutStr("MUTE"); break;
        case 34:
            AwtoPutStr("PWR1"); break;
        case 35:
            AwtoPutStr("PWR2"); break;
        case 36:
            AwtoPutStr("PWR3"); break;
        case 37:
            AwtoPutStr("PWR4"); break;
        case 38:
            AwtoPutStr("FLWP"); break;
        case 39:
            AwtoPutStr("SOURCE"); break;
        case 40:
            AwtoPutStr("MENU"); break;
        case 41:
            AwtoPutStr("DOWN"); break;
        case 42:
            AwtoPutStr("UP"); break;
        case 43:
            AwtoPutStr("AUTO"); break;
        default: break;
    }
}

static void AwtoInText(BYTE ucI)
{
    switch(ucI)
    {
        case 0:
        case 1:
        case 2:
        case 3:
        case 4:
        case 5:
        case 6:
        case 7:
        case 11:
            AwtoPutStr("DIGITAL"); break;
        case 8:
        case 9:
        case 10:
            AwtoPutStr("VOLT"); break;
        case 12:
        case 13:
        case 18:
            AwtoPutStr("SYNC"); break;
        case 14:
        case 15:
        case 16:
        case 17:
        case 19:
        case 20:
            AwtoPutStr("CMP"); break;
        case 21:
        case 22:
        case 23:
        case 24:
        case 25:
        case 26:
        case 27:
        case 28:
        case 29:
        case 30:
            AwtoPutStr("IN"); break;
        case 31:
        case 32:
        case 33:
        case 34:
        case 35:
        case 36:
        case 37:
        case 38:
            AwtoPutStr("OUT"); break;
        default: break;
    }
}

#define AWTO_TXT_DESCHDR       44
#define AWTO_TXT_LOGHDR        45
#define AWTO_TXT_MS            46
#define AWTO_TXT_MARK          47
static const __code char tAwtoTxtS[] = "spare pad, high-Z input\0key ladder A0: MENU UP AUTO\0key ladder A1: SOURCE DOWN\0spare ADC, 3.3 V full scale\0front POWER key, 1 = pressed\0analog VGA vertical sync\0analog VGA horizontal sync\0VGA blue- compare flag\0VGA blue+ compare flag\0VGA green- compare flag\0VGA green+ compare flag\0VGA sync on green\0VGA red- compare flag\0VGA red+ compare flag\0IR receiver, idle high\0speaker / headphone select\0HDMI-2 hot-plug output\0HDMI-1 hot-plug output\0DisplayPort hot-plug output\0HDMI-2 cable detect, 0 = cable\0HDMI-1 cable detect, 0 = cable\0DP connector pin 17 (AUX-)\0DP connector pin 15 (AUX+)\0DP connector pin 16 (GND)\0backlight enable, 0 = on\0panel power enable, 1 = on\0speaker amp, 1 = enabled\0power-state output P8.4\0power-state output P8.5\0power-state open drain P9.7\0power-state open drain PA.0\0SPI flash write protect\0\0DESCRIPTION\0EVENT LOG\0 MS  \0-----\0";
static const __code WORD tAwtoTxtOffS[48] = {0, 0, 0, 0, 0, 0, 0, 0, 24, 52, 79, 107, 136, 161, 188, 211, 234, 258, 282, 300, 322, 344, 367, 394, 417, 440, 468, 499, 530, 557, 584, 610, 635, 662, 687, 711, 735, 763, 791, 815, 815, 815, 815, 815, 816, 828, 838, 844};
static void AwtoTxt(BYTE ucI)                  // input description (0..AWTO_IN_N-1) or AWTO_TXT_*
{
    const __code char *pc = &tAwtoTxtS[tAwtoTxtOffS[ucI]];

    while(*pc != 0)
    {
        AwtoPutChar(*pc);
        pc++;
    }
}
// GENERATED-END awto_inputs

static BYTE AwtoInStyle(BYTE ucI)               // red = not in the I2C ring (inputs.tsv log = n)
{
    return ((tAwtoInFlagsS[ucI] & 2) != 0) ? AWTO_T_STYLE_TEXT : AWTO_T_STYLE_ALERT;
}

static void AwtoInRowFull(BYTE ucI)
{
    BYTE ucV = g_stAwtoGpio.ucIn[ucI];
    BYTE ucK = tAwtoInKindS[ucI];

    AwtoPutCol(AWTO_TCOL_NAME); AwtoInName(ucI);
    AwtoPutCol(AWTO_TCOL_PIN); AwtoPutNum(tAwtoInPinS[ucI], 1);
    AwtoPutCol(AWTO_TCOL_STATE);
    if(ucK == 0) AwtoPutNum(ucV, 1); else AwtoPutChar('-');
    AwtoPutCol(AWTO_TCOL_RAW);
    if(ucK == 1) AwtoPutNum(ucV, 3); else if(ucK == 2) AwtoPutHex2(ucV); else AwtoPutChar('-');
    AwtoPutCol(AWTO_TCOL_VALUE);
    if(ucK == 1) AwtoPutVolt(ucV); else AwtoInText(ucI);
    AwtoPutCol(AWTO_TCOL_DESC); AwtoTxt(ucI);
    AwtoTextLine(AWTO_G_L_FIRST + ucI, AwtoInStyle(ucI));
}

static void AwtoInRowField(BYTE ucI)
{
    BYTE ucV = g_stAwtoGpio.ucIn[ucI];
    BYTE ucK = tAwtoInKindS[ucI];

    AwtoFieldBegin();
    if(ucK == 0)
    {
        AwtoPutNum(ucV, 1);
        AwtoFieldEnd(AWTO_G_L_FIRST + ucI, AWTO_TCOL_STATE, AwtoInStyle(ucI));
    }
    else if(ucK == 1)
    {
        AwtoPutNum(ucV, 3);
        AwtoFieldEnd(AWTO_G_L_FIRST + ucI, AWTO_TCOL_RAW, AwtoInStyle(ucI));
        AwtoFieldBegin();
        AwtoPutVolt(ucV);
        AwtoFieldEnd(AWTO_G_L_FIRST + ucI, AWTO_TCOL_VALUE, AwtoInStyle(ucI));
    }
    else
    {
        AwtoPutHex2(ucV);
        AwtoFieldEnd(AWTO_G_L_FIRST + ucI, AWTO_TCOL_RAW, AwtoInStyle(ucI));
    }
}

static void AwtoTableStatic(void)
{
    AwtoPutCol(1); AwtoPutStr("GPIO INPUT DIAGNOSTICS");
    AwtoTextLine(0, AWTO_T_STYLE_ACCENT);
    AwtoPutCol(AWTO_TCOL_NAME); AwtoPutStr("INPUT");
    AwtoPutCol(AWTO_TCOL_PIN); AwtoPutStr("PIN");
    AwtoPutCol(AWTO_TCOL_STATE); AwtoPutStr("S");
    AwtoPutCol(AWTO_TCOL_RAW); AwtoPutStr("RAW");
    AwtoPutCol(AWTO_TCOL_VALUE); AwtoPutStr("VALUE");
    AwtoPutCol(AWTO_TCOL_DESC); AwtoTxt(AWTO_TXT_DESCHDR);
    AwtoTextLine(1, AWTO_T_STYLE_ACCENT);
    AwtoPutCol(1); AwtoPutStr("I2C 44 CLOSE");
    AwtoTextLine(AWTO_G_L_FIRST + AWTO_G_ROWS, AWTO_T_STYLE_ACCENT);
    AwtoPutCol(1); AwtoPutStr("RED = NOT IN THE I2C CHANGE LOG");
    AwtoTextLine(AWTO_G_L_FIRST + AWTO_G_ROWS + 1, AWTO_T_STYLE_ALERT);
}

void AwtoOsdGpioLines(void)
{
    _Bool bAll = (g_stAwtoGpio.ucDrawn == 0);
    BYTE ucI;

    if((s_ucConOpen != AWTO_CON_GPIO) || (AwtoConLost() != 0)) return;
    AwtoPanel(0);
    if(bAll != 0)
    {
        AwtoTableStatic();
    }
    for(ucI = 0; ucI < AWTO_G_ROWS; ucI++)
    {
        if(bAll != 0)
        {
            AwtoInRowFull(ucI);
        }
        else if((g_stAwtoGpio.ucDirty[ucI >> 3] & ((BYTE)1 << (ucI & 7))) != 0)
        {
            AwtoInRowField(ucI);
        }
    }
    for(ucI = 0; ucI < (AWTO_IN_N + 7) / 8; ucI++)
    {
        g_stAwtoGpio.ucDirty[ucI] = 0;
    }
    g_stAwtoGpio.ucAny = 0;
    g_stAwtoGpio.ucDrawn = 1;
    g_stAwtoGpio.ucRedraws++;
}

// Log pane (#144, #157): main page = sync / power lines, full width; GPIO page = input changes only (right of the table).
// One line per entry, newest above the "-----" marker.
static __xdata BYTE s_ucLogHead;
static __xdata BYTE s_ucLogFull;                // 0 = first lap: rows below the head are blank, so lines are drawn unpadded

static __xdata BYTE s_ucConSyncSeq;             // #139: sync ring seq the log has shown up to

void AwtoConLogInit(void)
{
    s_ucLogHead = 0;
    s_ucLogFull = 0;
    s_ucPanelCol = AWTO_LOG_COL;
    s_ucAwtoCols = AWTO_LOG_W;
    s_ucPanelRow = AWTO_LOG_HDR;
    s_pcAwtoRow[0] = ' ';
    s_ucAwtoLen = 1;
    if(s_ucConOpen == AWTO_CON_GPIO)
    {
        AwtoPutStr("INPUT CHANGES (NOT IN THE EVENT LOG)");
        AwtoTextLine(0, AWTO_T_STYLE_ACCENT);
#define AWTO_LOG_IN         g_stAwtoGpio.pstLog[s_ucLogI & (AWTO_GPIO_LOG_N - 1)]
        for(s_ucLogI = g_stAwtoGpio.ucSeq - AWTO_GPIO_LOG_N; s_ucLogI != g_stAwtoGpio.ucSeq; s_ucLogI++)
        {
            if(AWTO_LOG_IN.ucSeq == s_ucLogI)       // an entry of this ring lap (zeroed slots carry another seq)
            {
                AwtoConLogEvent(AWTO_LOG_IN.ucId, AWTO_LOG_IN.ucVal, ((WORD)AWTO_LOG_IN.ucTickHi << 8) | AWTO_LOG_IN.ucTickLo);
            }
        }
#undef AWTO_LOG_IN
        return;
    }
    AwtoTxt(AWTO_TXT_LOGHDR);
    AwtoTextLine(0, AWTO_T_STYLE_ACCENT);
    s_ucConSyncSeq = (AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, g_stAwtoSync.ucEpSeq) <= AWTO_SYNC_N) ? g_stAwtoSync.ucEpSeq :
                     AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, AWTO_SYNC_N);   // backfill the current episode (what the ring still has)
    if((s_ucConRedraw != 0) && (AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, s_ucConSyncSeq) > AWTO_LOG_REDRAW_N))
    {
        s_ucConSyncSeq = AWTO_SYNC_BACK(g_stAwtoSync.ucSeq, AWTO_LOG_REDRAW_N);   // map-full redraw: fits even if every line wraps
    }
    AwtoConLogSync();
}

static void AwtoConLogStart(void)               // next log row: compose with AwtoPut*, then AwtoConLogEnd
{
    s_ucPanelCol = AWTO_LOG_COL;
    s_ucAwtoCols = AWTO_LOG_W;
    s_ucPanelRow = AWTO_LOG_ROW0 + s_ucLogHead;
    s_pcAwtoRow[0] = ' ';
    s_ucAwtoLen = 1;
    s_bAwtoWrap = (s_ucConOpen == AWTO_CON_MAIN);
    s_bAwtoOver = 0;
}

// Main page: 1 = the next log row is in view (rolled up one row if it was below); 0 = map end, full redraw requested.
static bit AwtoConLogRoom(void)
{
    if((s_ucConOpen != AWTO_CON_MAIN) || (AWTO_LOG_ROW0 + s_ucLogHead < s_ucConFirst + AWTO_VIEW_ROWS))
    {
        return 1;
    }
    if((AWTO_LOG_ROW0 + s_ucLogHead < AWTO_CON_ROWS) && (osd_tc_scroll(s_ucConFirst + 1) != s_ucConFirst))
    {
        s_ucConFirst++;
        AwtoConTitleBar();                      // title over the new top row (its log line scrolls off)
        return 1;
    }
    s_ucConRedraw = 1;                          // roll-up limit (map rows, 12-bit base): redraw from the ring
    return 0;
}

// Main-page log line wider than a row (s_bAwtoOver): the row is drawn up to its last space, the line composed again with that
// part dropped and the rest continued on the next row at the text column. Two rows at most (gen_awto_sync.py checks the
// texts). No locals: under AwtoConLogSync (deep DATA path), the second AwtoSyncLine is one level down only.
static void AwtoConWrapLine(void)
{
    s_bAwtoWrap = 0;
    s_bAwtoOver = 0;
    if(AWTO_LOG_ROW0 + s_ucLogHead + 1 >= s_ucConFirst + AWTO_VIEW_ROWS)
    {
        if((AWTO_LOG_ROW0 + s_ucLogHead + 1 >= AWTO_CON_ROWS) || (osd_tc_scroll(s_ucConFirst + 1) == s_ucConFirst))
        {
            s_ucConRedraw = 1;                  // map end: the row is clipped until the redraw (next pass) shows the line
            return;
        }
        s_ucConFirst++;                         // title bar redrawn by AwtoConLogEnd (the row buffer is in use here)
    }
    s_ucLogI = s_ucAwtoLen;                     // s_ucLogI = characters to drop on the second pass (free: tail lines never wrap)
    while((--s_ucLogI > AWTO_LOG_TXT0) && (s_pcAwtoRow[s_ucLogI] != ' '))
    {
    }
    if(s_ucLogI <= AWTO_LOG_TXT0)
    {
        AwtoTextAt(s_ucPanelRow, s_ucPanelCol, s_pcAwtoRow, s_ucAwtoLen, AWTO_T_STYLE_TEXT);    // no space: break at the edge
        s_ucLogI = s_ucAwtoLen - 1;
    }
    else
    {
        AwtoTextAt(s_ucPanelRow, s_ucPanelCol, s_pcAwtoRow, s_ucLogI, AWTO_T_STYLE_TEXT);       // the space is dropped too
    }
    for(s_ucAwtoLen = 0; s_ucAwtoLen < AWTO_LOG_TXT0; s_ucAwtoLen++)
    {
        s_pcAwtoRow[s_ucAwtoLen] = ' ';
    }
    s_ucPanelRow++;
    s_bAwtoSkip = 1;
    AwtoSyncLine(s_ucConSyncSeq);
    s_bAwtoSkip = 0;
    s_bAwtoOver = 1;                            // AwtoConLogSync: one wrapped line per call (each costs two compositions)
}

static void AwtoConLogEnd(void)
{
    if(s_ucConOpen == AWTO_CON_MAIN)            // terminal: rows only go down; a long line takes two (AwtoConWrapLine)
    {
        s_bAwtoWrap = 0;
        AwtoTextLine(0, AWTO_T_STYLE_TEXT);
        if(s_ucPanelRow != AWTO_LOG_ROW0 + s_ucLogHead)
        {
            s_ucLogHead++;
            if(s_ucPanelRow + 1 == s_ucConFirst + AWTO_VIEW_ROWS)
            {
                AwtoConTitleBar();              // AwtoConWrapLine may have rolled the map up under the title
            }
        }
        s_ucLogHead++;
        return;
    }
    if((s_ucLogFull == 0) && (s_ucAwtoLen < s_ucAwtoCols))
    {
        s_ucAwtoCols = (s_ucAwtoLen > 6) ? s_ucAwtoLen : 6;     // over a marker (6 cells) or a blank row
    }
    AwtoTextLine(0, AWTO_T_STYLE_TEXT);
    s_ucLogHead = (s_ucLogHead + 1 >= AWTO_LOG_LINES) ? 0 : (s_ucLogHead + 1);
    if(s_ucLogHead == 0)
    {
        s_ucLogFull = 1;
    }
    s_ucAwtoCols = (s_ucLogFull != 0) ? AWTO_LOG_W : 6;
    s_ucPanelRow = AWTO_LOG_ROW0 + s_ucLogHead;      // marker on the next row: also blanks the oldest line (after a wrap)
    s_pcAwtoRow[0] = ' ';
    s_ucAwtoLen = 1;
    AwtoTxt(AWTO_TXT_MARK);
    AwtoTextLine(0, AWTO_T_STYLE_ACCENT);
}

void AwtoConLogEvent(BYTE ucId, BYTE ucVal, WORD usTick)    // GPIO page only: input changes never go into the event log
{
    if((s_ucConOpen != AWTO_CON_GPIO) || (AwtoConLost() != 0))
    {
        return;
    }
    AwtoConLogStart();
    AwtoPutNum(usTick, 5); AwtoTxt(AWTO_TXT_MS); AwtoInName(ucId); AwtoPutChar(' '); AwtoPutChar(' '); AwtoPutNum(ucVal, 1);
    AwtoConLogEnd();
}

// #157 "host time <ISO>" + its "(fw +N ms, ...)" entry on one row: the fw entry's text without its "nnnnn:" prefix.
// XDATA, no locals: AwtoConLogSync sits on the deepest DATA overlay path (see AwtoPutIso).
static void AwtoConLogTail(void)
{
    s_bAwtoWrap = 0;                            // fits one row (gen_awto_sync.py): cells are moved below, no wrap
    s_ucLogI = s_ucAwtoLen;
    AwtoSyncLine(s_ucConSyncSeq);
    s_pcAwtoRow[s_ucLogI] = ' ';
    for(s_ucLogI += AWTO_LOG_TIME_W; s_ucLogI < s_ucAwtoLen; s_ucLogI++)    // drop the AwtoSyncLine time column
    {
        s_pcAwtoRow[s_ucLogI - (AWTO_LOG_TIME_W - 1)] = s_pcAwtoRow[s_ucLogI];
    }
    s_ucAwtoLen = s_ucLogI - (AWTO_LOG_TIME_W - 1);     // max(len, start + time column) - (time column - 1)
    s_ucConSyncSeq = AWTO_SYNC_NEXT(s_ucConSyncSeq);
}

#define AWTO_LOG_EV(s)      (g_stAwtoSync.stEv[AWTO_SYNC_IDX(s)].ucId)
void AwtoConLogSync(void)                       // #139: new sync ring lines, one log row each (same decoder as the selector)
{
    if(AWTO_CON_LIVE() == _FALSE)
    {
        return;                                 // #162 s3: a fast switch's frame checks first; the OSD poll draws the lines after
    }
    while(s_ucConSyncSeq != g_stAwtoSync.ucSeq)
    {
        if((s_ucConOpen != AWTO_CON_MAIN) || (AwtoConLost() != 0))
        {
            return;
        }
        if((AWTO_LOG_EV(s_ucConSyncSeq) == AWTO_SYNC_EV_HOST) && (AWTO_SYNC_NEXT(s_ucConSyncSeq) == g_stAwtoSync.ucSeq))
        {
            return;                             // its fw line is pushed next (AwtoHtSync): both on one row then
        }
        if(AwtoConLogRoom() == 0)
        {
            return;                             // the redraw backfills it
        }
        AWTO_WDT_FEED(AWTO_WDT_S_CONLINE);      // bounded: <= AWTO_SYNC_N lines (a map-full redraw backfills AWTO_LOG_REDRAW_N in one pass)
        AwtoConLogStart();
        AwtoSyncLine(s_ucConSyncSeq);
        if(s_bAwtoOver != 0)
        {
            AwtoConWrapLine();
        }
        s_ucConSyncSeq = AWTO_SYNC_NEXT(s_ucConSyncSeq);
        if((s_ucConSyncSeq != g_stAwtoSync.ucSeq) && (AWTO_LOG_EV(s_ucConSyncSeq) == AWTO_SYNC_EV_HOSTFW) &&
           (AWTO_LOG_EV(AWTO_SYNC_BACK(s_ucConSyncSeq, 1)) == AWTO_SYNC_EV_HOST))
        {
            AwtoConLogTail();
        }
        AwtoConLogEnd();
        if(s_bAwtoOver != 0)
        {
            s_bAwtoOver = 0;
            return;                             // the rest next pass: a burst of wide lines bit the watchdog (con_wrap_sim)
        }
    }
}
#else
void AwtoOsdGpioLines(void)
{
}

void AwtoConLogInit(void)
{
}

void AwtoConLogEvent(BYTE ucId, BYTE ucVal, WORD usTick)
{
    (void)ucId; (void)ucVal; (void)usTick;
}

void AwtoConLogSync(void)
{
}
#endif

//---- watchdog panel of the diagnostic console (#131): last bite from isr_g_stAwtoWdt ----
#if((_AWTO_WDT == _ON) && (defined(_AWTO_NEW_SETTINGS)))
#define AWTO_WDT_POP_COL    79                  // #144: right of the debug panel, below the console view
#define AWTO_WDT_POP_ROW    52
#define AWTO_WDT_POP_W      36

static void AwtoWdtPutWord(BYTE ucHi, BYTE ucLo)
{
    AwtoPutHex2(ucHi);
    AwtoPutHex2(ucLo);
}

void AwtoOsdWdtLines(void)
{
    BYTE ucOk = AwtoWdtValid();
    BYTE ucC = isr_g_stAwtoWdt.ucCause;

    s_ucPanelCol = AWTO_WDT_POP_COL;
    s_ucPanelRow = AWTO_WDT_POP_ROW;
    s_ucAwtoCols = AWTO_WDT_POP_W;
    s_ucAwtoLen = 1;
    AwtoPutStr("WATCHDOG");
    if(ucOk != 0)
    {
        AwtoPutStr("  BITES ");
        AwtoPutNum(isr_g_stAwtoWdt.ucBites, 1);
        AwtoPutStr(" WARM ");
        AwtoPutNum(isr_g_stAwtoWdt.ucWarm, 1);
    }
    AwtoTextLine(0, ((isr_g_stAwtoWdt.ucBoot & AWTO_WDT_B_NEW) != 0) ? AWTO_T_STYLE_ALERT : AWTO_T_STYLE_ACCENT);
    isr_g_stAwtoWdt.ucBoot &= ~AWTO_WDT_B_NEW;      // shown
    if((ucOk == 0) || (isr_g_stAwtoWdt.ucBites == 0))
    {
        AwtoPutStr("NO BITE RECORDED");
        AwtoTextLine(1, AWTO_T_STYLE_TEXT);
    }
    else
    {
        AwtoPutStr(((ucC & 0x3F) == AWTO_WDT_C_STALL) ? "STALL" : "?");
        AwtoPutStr(((ucC & AWTO_WDT_C_TMODE) != 0) ? " TMODE" : "");
        AwtoPutStr(((ucC & AWTO_WDT_C_TEST) != 0) ? " TEST" : "");
        AwtoPutStr("  PASS AGE ");
        AwtoPutNum(((WORD)isr_g_stAwtoWdt.ucPassAgeHi << 8) | isr_g_stAwtoWdt.ucPassAgeLo, 1);
        AwtoPutStr("MS");
        AwtoTextLine(1, AWTO_T_STYLE_TEXT);
        AwtoPutStr("PC ");
        if(isr_g_stAwtoWdt.ucPcHi >= 0x50)
        {
            AwtoPutHex2(isr_g_stAwtoWdt.ucBank);
        }
        else
        {
            AwtoPutStr("C");
        }
        AwtoPutChar(':');
        AwtoWdtPutWord(isr_g_stAwtoWdt.ucPcHi, isr_g_stAwtoWdt.ucPcLo);
        AwtoPutStr(" TOP ");
        AwtoWdtPutWord(isr_g_stAwtoWdt.ucRetHi, isr_g_stAwtoWdt.ucRetLo);
        AwtoPutStr(" SP ");
        AwtoPutHex2(isr_g_stAwtoWdt.ucSp);
        AwtoTextLine(2, AWTO_T_STYLE_TEXT);
        AwtoPutStr("A ");
        AwtoPutHex2(isr_g_stAwtoWdt.ucAcc);
        AwtoPutStr(" B ");
        AwtoPutHex2(isr_g_stAwtoWdt.ucB);
        AwtoPutStr(" PSW ");
        AwtoPutHex2(isr_g_stAwtoWdt.ucPsw);
        AwtoPutStr(" DPTR ");
        AwtoWdtPutWord(isr_g_stAwtoWdt.ucDph, isr_g_stAwtoWdt.ucDpl);
        AwtoTextLine(3, AWTO_T_STYLE_TEXT);
        AwtoPutStr("HB ");
        AwtoPutNum(((WORD)isr_g_stAwtoWdt.ucHbHi << 8) | isr_g_stAwtoWdt.ucHbLo, 1);
        AwtoPutStr(" UP ");
        AwtoPutNum(((WORD)isr_g_stAwtoWdt.ucUpHi << 8) | isr_g_stAwtoWdt.ucUpLo, 1);
        AwtoPutStr("MS ST ");
        AwtoPutNum(isr_g_stAwtoWdt.ucStage, 1);
        AwtoPutStr(" MODE ");
        AwtoPutNum(isr_g_stAwtoWdt.ucMode, 1);
        AwtoTextLine(4, AWTO_T_STYLE_TEXT);
    }
    AwtoPutStr("THIS BOOT ");
    AwtoPutStr(((isr_g_stAwtoWdt.ucBoot & AWTO_WDT_B_COLD) != 0) ? "COLD" : ((isr_g_stAwtoWdt.ucBoot & AWTO_WDT_B_AFTER) != 0) ? "BITE" :
               ((isr_g_stAwtoWdt.ucBoot & AWTO_WDT_B_HWWDT) != 0) ? "HW WDT" : "WARM");
    AwtoPutStr(" MAX PASS ");                   // x32 ms; poke gap x32 CNT3 = 4.58 ms (RL6449_Project.h)
    AwtoPutNum((WORD)isr_g_stAwtoWdt.ucMaxPass << 5, 1);
    AwtoPutStr(" POKE ");
    AwtoPutNum(((WORD)isr_g_stAwtoWdt.ucMaxPoke * 293) >> 6, 1);
    AwtoPutStr("MS AT ");
    AwtoPutNum(g_ucAwtoPokeSite, 1);            // AWTO_WDT_S_* (#150)
    AwtoTextLine(5, AWTO_T_STYLE_TEXT);
    AwtoPutStr("PROBE ");
    AwtoPutHex2(isr_g_stAwtoWdt.ucProbe);           // AWTO_WDT_P_*: 01 timer 02 armed 04 IRQ 08 reset 10 no reset
    AwtoTextLine(6, AWTO_T_STYLE_TEXT);
}
#elif(_AWTO_WDT == _ON)
void AwtoOsdWdtLines(void)
{
}
#endif

//---- #151 fmt nvw: the NVRAM flush result line (AwtoSyncLine case 22) ----
// Fields: RL6449_Project.h AWTO_NV_LOG_*; host copy: scripts/sync_log.py nv_flush. No locals (DATA path).
static __xdata WORD s_usAwtoNvF, s_usAwtoNvM;
static __xdata BYTE s_ucAwtoNvG;

static void AwtoPutNvF(void)                    // field s_usAwtoNvF; "+" when saturated (at s_usAwtoNvM)
{
    AwtoPutNum(s_usAwtoNvF, 1);
    if(s_usAwtoNvF >= s_usAwtoNvM)
    {
        AwtoPutChar('+');
    }
}

static void AwtoPutNvG(BYTE ucBit, const char *pcName)
{
    if(((BYTE)(s_ulAwtoLnV >> 27) & ucBit) != 0)
    {
        AwtoPutStr((s_ucAwtoNvG != 0) ? ", " : " (");
        AwtoPutStr(pcName);
        s_ucAwtoNvG = 1;
    }
}

static void AwtoPutNvFlush(void)
{
    s_usAwtoNvF = (WORD)s_ulAwtoLnV & AWTO_NV_LOG_MS_MAX;
    s_usAwtoNvM = AWTO_NV_LOG_MS_MAX;
    if((s_ulAwtoLnV >> 19) == 0)                // no item, program or erase
    {
        AwtoPutStr("nothing changed, no flash write (");
        AwtoPutNvF();
        AwtoPutStr("ms)");
        return;
    }
    AwtoPutStr("wrote ");
    s_usAwtoNvF = (WORD)(s_ulAwtoLnV >> 9) & AWTO_NV_LOG_B_MAX;
    s_usAwtoNvM = AWTO_NV_LOG_B_MAX;
    AwtoPutNvF();
    AwtoPutStr("B");
    s_ucAwtoNvG = 0;
    AwtoPutNvG(AWTO_NV_LOG_G_SYS, "system data");
    AwtoPutNvG(AWTO_NV_LOG_G_OSD, "OSD data");
    AwtoPutNvG(AWTO_NV_LOG_G_COLOUR, "colour");
    AwtoPutNvG(AWTO_NV_LOG_G_PANEL, "panel time");
    AwtoPutNvG(AWTO_NV_LOG_G_AUX, "awto settings");
    AwtoPutStr((s_ucAwtoNvG != 0) ? ") in " : " in ");
    s_usAwtoNvF = (WORD)(s_ulAwtoLnV >> 19) & AWTO_NV_LOG_PR_MAX;
    s_usAwtoNvM = AWTO_NV_LOG_PR_MAX;
    AwtoPutNvF();
    AwtoPutStr((s_usAwtoNvF == 1) ? " program, " : " programs, ");
    s_usAwtoNvF = (WORD)(s_ulAwtoLnV >> 25) & AWTO_NV_LOG_ER_MAX;
    s_usAwtoNvM = AWTO_NV_LOG_ER_MAX;
    AwtoPutNvF();
    AwtoPutStr((s_usAwtoNvF == 1) ? " erase, " : " erases, ");
    s_usAwtoNvF = (WORD)s_ulAwtoLnV & AWTO_NV_LOG_MS_MAX;
    s_usAwtoNvM = AWTO_NV_LOG_MS_MAX;
    AwtoPutNvF();
    AwtoPutStr("ms");
}

#endif//#if(_OSD_TYPE == _REALTEK_2014_OSD)
