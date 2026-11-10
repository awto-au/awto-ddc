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
extern BYTE osd_font_glyph(char c);
extern void osd_tc_cells(BYTE ucRow, BYTE ucCell, BYTE __xdata *pucTiles, BYTE ucN, BYTE ucStyle);

#ifndef AWTO_HOLD_POPUP
#define AWTO_HOLD_POPUP     0x02                // same value as awto_testcmd.inc (another translation unit)
#endif
#define AWTO_T_MAXCOLS      160                 // cell map limit is 8192 words: 160 columns x 50 rows
#define AWTO_T_STYLE_TEXT   0
#define AWTO_T_STYLE_ONACC  2
#define AWTO_T_STYLE_ACCENT 3
__xdata BYTE g_ucAwtoProbeCols;                  // limit probe columns = 4 * (test cmd 0xC0 + n); 0 = 36
__xdata BYTE g_ucAwtoProbeLines;                 // limit probe line count (test cmd 0x80 + n); 0 = 24
__xdata BYTE g_ucAwtoDiagFont;                  // 0 = default (5x8, font 3); else 1 + font index of osd_font_load (test cmd 0x60 + n)
#define AwtoDiagFont()      ((g_ucAwtoDiagFont != 0) ? (g_ucAwtoDiagFont - 1) : 3)
static __xdata char s_pcAwtoRow[AWTO_T_MAXCOLS];
static __xdata BYTE s_ucAwtoTiles[AWTO_T_MAXCOLS];
__xdata BYTE g_ucAwtoDiagSmall;                  // 0 = diagnostic screens at 2x size (default), 1 = 1x (test cmd 0x4B / 0x4A)
static BYTE s_ucAwtoLen;
static BYTE s_ucAwtoCols;

// One diagnostic console (AwtoDiagConsole): a fixed grid with the GPIO, key test and debug panels side by side.
#define AWTO_CON_COLS       84
#define AWTO_CON_ROWS       45                  // + the pad row AwtoTextOpen adds
static __xdata BYTE s_ucConOpen;
static BYTE s_ucPanelCol;
static BYTE s_ucPanelRow;
static const __code BYTE tAwtoPanelCol[3] = {1, 44, 44};
static const __code BYTE tAwtoPanelRow[3] = {2, 2, 12};
static const __code BYTE tAwtoPanelW[3] = {40, 36, 36};

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
static void AwtoTextOpen(BYTE ucCols, BYTE ucLines, bit bTitleBar)
{
    ucLines++;                         // one blank pad row: the frame border covers the last 2 px of a full-height row
    s_ucAwtoCols = ucCols;
    s_pcAwtoRow[0] = ' ';              // every row starts one cell in, clear of the frame
    s_ucAwtoLen = 1;
    osd_tc_open(ucCols, ucLines);
    ScalerOsdSetColorPalette(1, 0, 255, 65);       // diagnostic look: green on black, title bar reversed
    ScalerOsdSetColorPalette(2, 0, 140, 40);
    ScalerOsdSetColorPalette(3, 0, 0, 0);
    osd_font_load(AwtoDiagFont());
    osd_tc_bar(0, 0, 0, (WORD)ucCols * osd_cw - 1, (WORD)ucLines * osd_rh - 1, 1);   // frame (accent)
    osd_tc_bar(1, 2, 2, (WORD)ucCols * osd_cw - 3, (WORD)ucLines * osd_rh - 3, 0);  // surface
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

// Generic text write: ucN characters of pc at map row ucRow, column ucCol (any position in the grid, any width up to 255 cells).
static void AwtoTextAt(BYTE ucRow, BYTE ucCol, const char __xdata *pc, BYTE ucN, BYTE ucStyle)
{
    BYTE ucI;

    for(ucI = 0; ucI < ucN; ucI++)
    {
        s_ucAwtoTiles[ucI] = osd_font_glyph(pc[ucI]);
    }
    osd_tc_cells(ucRow, ucCol, s_ucAwtoTiles, ucN, ucStyle);
}

// Draw the composed row on text line ucLine, padded to the full width so the previous text of that line is overwritten.
static void AwtoTextLine(BYTE ucLine, BYTE ucStyle)
{
    AwtoPutCol(s_ucAwtoCols);
    AwtoTextAt(s_ucPanelRow + ucLine, s_ucPanelCol, s_pcAwtoRow, s_ucAwtoCols, ucStyle);
    s_ucAwtoLen = 1;                   // next row: leading space kept in s_pcAwtoRow[0]
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
        AwtoTextOpen(AWTO_CON_COLS, AWTO_CON_ROWS, 1);
        s_ucAwtoCols = AWTO_CON_COLS;
        s_ucPanelCol = 0;
        s_ucPanelRow = 0;
        s_ucAwtoLen = 1;
        AwtoPutStr("AWTO DIAGNOSTICS  FW ");
        AwtoPutStr(AWTO_FW_TAG);
        AwtoTextLine(0, AWTO_T_STYLE_ONACC);
        g_stAwtoGpio.ucDrawn = 0;
        AwtoOsdGpioLines();
        g_stAwtoKey.ucDrawn = 0;
        AwtoOsdKeyLines();
        AwtoOsdDebugLines();
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
        s_ucAwtoTiles[ucC] = osd_font_glyph(ucI);
    }
    osd_tc_cells(ucR, 0, s_ucAwtoTiles, ucCols, ucStyle);
}

void AwtoProbeSet(BYTE ucLines)
{
    BYTE ucR;
    BYTE ucCols = (g_ucAwtoProbeCols != 0) ? g_ucAwtoProbeCols : 36;

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
    AwtoTextOpen(ucCols, ucLines, 1);
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
