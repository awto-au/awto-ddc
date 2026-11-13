// Debug pop-up (#34): same window/font/colours as the input-info pop-up; hooked into OsdDispOsdMessage by keil2sdcc.py.
#include <stddef.h>
// Shared text layer for every awto diagnostic screen (debug lines, key test, GPIO inputs): ASCII rows composed in s_pcAwtoRow,
// drawn with the menu's Spleen cells (ui_text); the SDK proportional font is not used here.
#ifdef _AWTO_NEW_SETTINGS
extern void osd_tc_open(BYTE ucChars, BYTE ucLines);
extern void osd_tc_bar(BYTE ucWin, WORD usX0, WORD usY0, WORD usX1, WORD usY1, BYTE ucColour);
extern void osd_tc_place(BYTE ucH, BYTE ucV, BYTE ucBig);
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
static bit s_bAwtoWrap;                         // main-page log line: a full row sets s_bAwtoOver (AwtoConWrapLine draws two rows)
static bit s_bAwtoOver;
static bit s_bAwtoSkip;                         // second pass of a wrapped line: the first s_ucLogI characters are dropped
static __xdata BYTE s_ucLogI;                   // GPIO page backfill: change-ring seq; host-time row: shift index; wrap: skip count

// One diagnostic console (AwtoDiagConsole), #144: 120 x 50 shown, Spleen 8x16 at 2x (1920 x 1836 px on the 4K panel).
// Pages: main (power-on, auto-open) = title + sync / power event log, full width; GPIO (#157) = input table + input changes.
// Main page = terminal: lines added at the bottom, the map rolls up (hardware roll-up). GPIO page: key test, debug,
// watchdog below the view (UP / DOWN scroll). Map 120 x 63: cols x rows + rows + 1 < 8192 (docs/osd.md).
#define AWTO_CON_COLS       120
#define AWTO_CON_ROWS       62                  // map rows (+ the pad row AwtoTextOpen adds)
#define AWTO_VIEW_ROWS      50                  // rows shown at a time; UP / DOWN scroll the view over the map
#define AWTO_CON_FONT       0                   // osd_font_load index: Spleen 8x16 (8 x 18 cell)
#define AWTO_LOG_COL        ((s_ucConOpen == AWTO_CON_GPIO) ? 62 : 1)    // log pane: main page full width, GPIO page right of the table
#define AWTO_LOG_W_MAIN     (AWTO_T_MAXCOLS - 1)                     // main-page log row (cells, incl. the leading space)
#define AWTO_LOG_W          ((s_ucConOpen == AWTO_CON_GPIO) ? 57 : AWTO_LOG_W_MAIN)
#define AWTO_LOG_TIME_W     10                  // AwtoSyncLine time column "+nnnnn ms "
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
    g_stAwtoDiag.ucHold &= ~AWTO_HOLD_POPUP;
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
    g_stAwtoDiag.ucOsdOfsState = offsetof(StructOsdInfo, usOsdState);
    g_stAwtoDiag.ucOsdOfsEvent = offsetof(StructOsdInfo, ucOsdEventMsg);
    g_stAwtoDiag.ucOsdOfsKey = offsetof(StructOsdInfo, ucOsdKeyMessage);
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
    osd_tc_open(ucCols, ucLines);
    UserCommonInterfacePanelPowerTick();        // #162: map clear and font load are the long parts of a console open (boot,
                                                // wake): panel steps due meanwhile (T3, backlight-to-PWM) are not held up
    ScalerOsdSetColorPalette(AWTO_PAL_DIAG_TEXT, AWTO_RGB_PHOSPHOR_GREEN);       // diagnostic look: green on black, title bar reversed
    ScalerOsdSetColorPalette(AWTO_PAL_DIAG_DIM, AWTO_RGB_PHOSPHOR_DIM);
    ScalerOsdSetColorPalette(AWTO_PAL_DIAG_BG, AWTO_RGB_BLACK);
    ScalerOsdSetColorPalette(AWTO_PAL_DIAG_ALERT, AWTO_RGB_ALERT_RED);
    osd_font_load(AwtoDiagFont((ucView != 0) ? AWTO_CON_FONT : 3));     // console / probe
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
    osd_tc_place(50, 50, (g_ucAwtoDiagSmall == 0) ? 1 : 0);
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
    g_stAwtoDiag.ucDbgPopup = 0;
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
    AwtoPutNum(g_stAwtoDiag.usLoopRate, 1);
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
#define AWTO_TITLE_COL      60                  // after "AWTO DIAGNOSTICS  FW <tag>" (tags up to 38 characters)
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
    if(g_stAwtoHt.ucSyncs == 0)
    {
        AwtoPutStr("--:--:--");
    }
    else
    {
        s_ulAwtoT = (g_stAwtoHt.ulEpoch + (long)g_stAwtoHt.cOfs * 900 + (ulUp - g_stAwtoHt.ulFwMs + g_stAwtoHt.usFrac) / 1000) % 86400;
        AwtoPutClock();
        if((ulUp - g_stAwtoHt.ulFwMs) > AWTO_HT_STALE_MS)
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
    AwtoPutStr("AWTO DIAGNOSTICS  FW ");
    AwtoPutStr(AWTO_FW_TAG);
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
    g_stAwtoDiag.ucHold &= ~AWTO_HOLD_POPUP;       // before the disable: a hold blocks it
    if(ucOn != 0)
    {
        menu_close();
        OsdDispDisableOsd();
        s_ucConOpen = ucOn;
        g_stAwtoDiag.ucHold |= AWTO_HOLD_POPUP;
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
            g_stAwtoDiag.ucHold &= ~AWTO_HOLD_POPUP;
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
    g_stAwtoDiag.ucHold |= AWTO_HOLD_POPUP;
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
    g_stAwtoDiag.ucOsdOfsState = offsetof(StructOsdInfo, usOsdState);
    g_stAwtoDiag.ucOsdOfsEvent = offsetof(StructOsdInfo, ucOsdEventMsg);
    g_stAwtoDiag.ucOsdOfsKey = offsetof(StructOsdInfo, ucOsdKeyMessage);
}

void AwtoOsdDebugLines(void)
{
    g_stAwtoDiag.ucDbgPopup = 0;
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
