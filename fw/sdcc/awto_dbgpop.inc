// Debug pop-up (#34): same window/font/colours as the input-info pop-up; hooked into OsdDispOsdMessage by keil2sdcc.py.
#if(_AWTO_DIAG == _ON)
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
#define AWTO_T_MAXCOLS      100                 // XDATA is nearly full: widest text row (console 100, probe clamped to this)
#define AWTO_T_STYLE_TEXT   0
#define AWTO_T_STYLE_ONACC  2
#define AWTO_T_STYLE_ACCENT 3
#define AWTO_T_STYLE_ALERT  4                   // red: an input that is not in the I2C ring
__xdata BYTE g_ucAwtoProbeCols;                  // limit probe columns = 4 * (test cmd 0xC0 + n); 0 = 36
__xdata BYTE g_ucAwtoProbeLines;                 // limit probe line count (test cmd 0x80 + n); 0 = 24
__xdata BYTE g_ucAwtoDiagFont;                  // 0 = default (console Spleen 8x16, probe 5x8); else 1 + osd_font_load index (cmd 0x60 + n)
#define AwtoDiagFont(d)     ((g_ucAwtoDiagFont != 0) ? (g_ucAwtoDiagFont - 1) : (d))
static __xdata char s_pcAwtoRow[AWTO_T_MAXCOLS];  // #157: glyphs converted in place (no tile copy: 100 B XDATA back)
__xdata BYTE g_ucAwtoDiagSmall;                  // 0 = diagnostic screens at 2x size (default), 1 = 1x (test cmd 0x4B / 0x4A)
static BYTE s_ucAwtoLen;
static BYTE s_ucAwtoCols;

// One diagnostic console (AwtoDiagConsole), #144: 120 x 50 shown, Spleen 8x16 at 2x (1920 x 1836 px on the 4K panel).
// Shown: inputs panel (left), event / sync log (right). Below the view (UP / DOWN scroll): key test, debug, watchdog.
// Map 120 x 63: cell rule cols x rows + rows + 1 < 8192 (docs/osd.md Limits).
#define AWTO_CON_COLS       120
#define AWTO_CON_ROWS       62                  // map rows (+ the pad row AwtoTextOpen adds)
#define AWTO_VIEW_ROWS      50                  // rows shown at a time; UP / DOWN scroll the view over the map
#define AWTO_CON_FONT       0                   // osd_font_load index: Spleen 8x16 (8 x 18 cell)
#define AWTO_LOG_COL        62                  // event log: heading row, then lines to the bottom of the view
#define AWTO_LOG_W          57
#define AWTO_LOG_HDR        2
#define AWTO_LOG_ROW0       (AWTO_LOG_HDR + 1)
#define AWTO_LOG_LINES      (AWTO_VIEW_ROWS - AWTO_LOG_ROW0)
static __xdata BYTE s_ucConOpen;
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
    ScalerSetBit(0x3A18, ~_BIT7, 0x00);            // the new map must not be shifted by our roll-up
    g_stAwtoDiag.ucHold &= ~AWTO_HOLD_POPUP;
    AwtoGpioConSet(0);
    AwtoKeyConSet(0);
    return 1;
}

static __xdata BYTE s_ucConFirst;               // first map row shown (hardware scroll)

void AwtoConScroll(signed char cD)              // UP / DOWN while the console is open
{
    BYTE ucN;

    if((s_ucConOpen == 0) || (AwtoConLost() != 0))
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
    ScalerOsdSetColorPalette(1, 0, 255, 65);       // diagnostic look: green on black, title bar reversed
    ScalerOsdSetColorPalette(2, 0, 140, 40);
    ScalerOsdSetColorPalette(3, 0, 0, 0);
    ScalerOsdSetColorPalette(4, 255, 50, 50);
    osd_font_load(AwtoDiagFont((ucView != 0) ? AWTO_CON_FONT : 3));     // console / probe
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
    if(s_ucAwtoLen < s_ucAwtoCols)
    {
        s_pcAwtoRow[s_ucAwtoLen++] = c;
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

static void AwtoPutNum(unsigned long ulV, BYTE ucMin)
{
    char pcD[10];
    BYTE ucN = 0;

    do
    {
        pcD[ucN++] = '0' + (ulV % 10);
        ulV /= 10;
    }
    while((ulV != 0) && (ucN < 10));
    while(ucN < ucMin)
    {
        pcD[ucN++] = '0';
    }
    while(ucN != 0)
    {
        AwtoPutChar(pcD[--ucN]);
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

void AwtoOsdDebugLines(void)
{
    BYTE ucPort = SysSourceGetInputPort();
    BYTE ucMode = SysModeGetModeState();
    BYTE ucPwr = SysPowerGetPowerStatus();
    unsigned long ulDclk = GET_D_CLK_FREQ();      // kHz
    WORD usV = GET_INPUT_TIMING_VFREQ();          // 0.1 Hz

    if(s_ucConOpen == 0)
    {
        AwtoDiagConsole(1);            // an SDK-triggered debug pop-up opens the console (which draws this panel)
        return;
    }
    if(AwtoConLost() != 0) return;
    g_stAwtoDiag.ucDbgPopup = 0;
    AwtoPanel(2);
    AwtoPutCol(1);
    AwtoPutStr("DEBUG");
    AwtoTextLine(0, AWTO_T_STYLE_ACCENT);

    AwtoPutStr((ucPort >= _D0_PORT) ? "D" : "A");
    AwtoPutNum((ucPort >= _D0_PORT) ? (ucPort - _D0_PORT) : 0, 1);
    AwtoPutStr(" ");
    AwtoPutNum(GET_INPUT_TIMING_HWIDTH(), 1);
    AwtoPutStr("x");
    AwtoPutNum(GET_INPUT_TIMING_VHEIGHT(), 1);
    AwtoPutStr(" ");
#if(_AWTO_FREQ == _ON)
    if(g_stAwtoFreq.ucValid != 0)
    {
        AwtoPutMilli(g_stAwtoFreq.ulVFreqmHz);
    }
    else
#endif
    {
        AwtoPutNum(usV / 10, 1);      // SDK 0.1 Hz value: no exact count yet
        AwtoPutStr(".");
        AwtoPutNum(usV % 10, 1);
    }
    AwtoPutStr("Hz");
    AwtoShowLine(_OSD_MESSAGE_ROW_START, _PFONT_PAGE_0);

    AwtoPutStr(ucMode == _MODE_STATUS_ACTIVE ? "ACTIVE" : (ucMode == _MODE_STATUS_NOSIGNAL ? "NOSIG" : (ucMode == _MODE_STATUS_POWER_SAVING ? "PSAVE" : "MODE")));
    AwtoPutStr(" ");
    AwtoPutNum(ucMode, 1);
    AwtoPutStr("  PWR ");
    AwtoPutStr(ucPwr == _POWER_STATUS_NORMAL ? "ON" : (ucPwr == _POWER_STATUS_SAVING ? "SAVE" : (ucPwr == _POWER_STATUS_OFF ? "OFF" : "AC")));
    AwtoPutNum(ucPwr, 1);
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 1, _PFONT_PAGE_1);

#if(_AWTO_FREQ == _ON)
    if(g_stAwtoFreq.ucValid != 0)
    {
        AwtoPutStr("PCLK ");
        AwtoPutMilli(g_stAwtoFreq.ulPclkHz / 1000);
        AwtoPutStr(" ");
    }
#endif
    AwtoPutStr("DCLK ");
    AwtoPutMilli(ulDclk);
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 2, _PFONT_PAGE_2);

    AwtoPutStr("LOOP ");
    AwtoPutNum(g_stAwtoDiag.usLoopRate, 1);
    AwtoPutStr("/s");
#if(_AWTO_FREQ == _ON)
    if(g_stAwtoFreq.ucValid != 0)
    {
        AwtoPutStr("  H ");
        AwtoPutMilli(g_stAwtoFreq.ulHFreqHz);
        AwtoPutStr("kHz");
    }
#endif
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 3, _PFONT_PAGE_0);

    AwtoPutStr("FW ");
    AwtoPutStr(AWTO_FW_TAG);
    AwtoShowLine(_OSD_MESSAGE_ROW_START + 4, _PFONT_PAGE_1);
}

#if(_AWTO_SYNC_LOG == _ON)
// #157 title row live part: "PANEL 0027.25h  UP 0000.42h  HOST 08:45:10" (+ " STALE"); s_pcConTitle = cells on screen.
#define AWTO_TITLE_COL      60                  // after "AWTO DIAGNOSTICS  FW <tag>" (tags up to 38 characters)
#define AWTO_TITLE_N        48
static __xdata char s_pcConTitle[AWTO_TITLE_N];
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

static void AwtoConTitle(BYTE ucAll)            // compose; draw the runs of cells that changed (ucAll: every cell)
{
    DWORD ulUp = AwtoUpMs();
    BYTE ucI, ucJ;

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
        for(ucJ = ucI; (ucJ < AWTO_TITLE_N) && ((ucAll != 0) || (s_pcAwtoRow[ucJ] != s_pcConTitle[ucJ])); ucJ++)
        {
            s_pcConTitle[ucJ] = s_pcAwtoRow[ucJ];
        }
        if(ucJ != ucI)
        {
            AwtoTextAt(0, AWTO_TITLE_COL + ucI, s_pcAwtoRow + ucI, ucJ - ucI, AWTO_T_STYLE_ONACC);
        }
        else
        {
            ucJ++;
        }
    }
    s_pcAwtoRow[0] = ' ';
    s_ucAwtoLen = 1;
}

void AwtoConTitlePoll(void)                     // every pass while the console is open (AwtoOsdSyncPoll)
{
    WORD usNow;

    do
    {
        usNow = g_stAwtoDiag.usT2Isr;
    }
    while(usNow != g_stAwtoDiag.usT2Isr);
    if(((WORD)(usNow - s_usConTitleMs) < AWTO_TITLE_MS) || (AwtoConLost() != 0))
    {
        return;
    }
    AwtoConTitle(0);
}
#else
#define AwtoConTitle(a)
#endif

// The console: open / close / toggle (2). Opens the grid and draws every panel; closing releases the panels.
void AwtoDiagConsole(BYTE ucOn)
{
    if(ucOn == 2)
    {
        ucOn = (s_ucConOpen == 0) ? 1 : 0;
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
        s_ucConOpen = 1;
        g_stAwtoDiag.ucHold |= AWTO_HOLD_POPUP;
        AwtoGpioConSet(1);
        AwtoKeyConSet(1);
        AwtoTextOpen(AWTO_CON_COLS, AWTO_CON_ROWS, AWTO_VIEW_ROWS, 1);
        s_ucConFirst = 0;
        s_ucAwtoCols = AWTO_T_MAXCOLS;          // title text; the title bar window spans the full width
        s_ucPanelCol = 0;
        s_ucPanelRow = 0;
        s_ucAwtoLen = 1;
        AwtoPutStr("AWTO DIAGNOSTICS  FW ");
        AwtoPutStr(AWTO_FW_TAG);
        AwtoTextLine(0, AWTO_T_STYLE_ONACC);
        AwtoConTitle(1);
        g_stAwtoGpio.ucDrawn = 0;
        AwtoOsdGpioLines();
        g_stAwtoKey.ucDrawn = 0;
        AwtoOsdKeyLines();
        AwtoOsdDebugLines(); AwtoOsdWdtLines();         // #131 watchdog panel; same line: warn_policy line keys stay
        AwtoConLogInit();
        AwtoTextShow();
    }
    else
    {
        s_ucConOpen = 0;
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
    WORD usFs;

    if(s_ucAwtoProbeOpen == 0) return;
    s_ucAwtoScroll = (ucReset != 0) ? 0 : (s_ucAwtoScroll + 1);
    usFs = g_usFontSelectStart + (WORD)s_ucAwtoScroll * s_ucAwtoConCols;
    ScalerSetBit(0x3A18, ~(_BIT7 | _BIT6), _BIT7);
    ScalerSetByte(0x3A19, s_ucAwtoScroll);
    ScalerSetBit(0x3A1B, 0x0F, (BYTE)((usFs >> 8) << 4));
    ScalerSetByte(0x3A1C, (BYTE)usFs);
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
#endif
