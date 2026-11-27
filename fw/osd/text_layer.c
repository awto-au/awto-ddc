#include "UserCommonInclude.h"

#if(_OSD_TYPE == _REALTEK_2014_OSD)
#ifdef _AWTO_NEW_SETTINGS
extern void osd_font_load(BYTE ucFont);
extern BYTE osd_font_cw(BYTE ucFont);
extern BYTE __xdata osd_cw;
extern BYTE __xdata osd_rh;

//---- text layer on the OSD engine (osd.h osd_tc_*, awto-ddc#89): native Spleen 8 x 16 bitmap glyphs ----
// palette (index: colour): our own entries over the SDK's, restored when the Realtek SDK menu loads its palette.
// White surface + Realtek 2014 blue (0,68,166) text/accent; selected rows retain white text on blue.
static __code BYTE tAwtoPal[AWTO_PAL_N][3] = {
    {AWTO_RGB_REALTEK_BLUE}, {AWTO_RGB_GREY_AA}, {AWTO_RGB_WHITE}, {AWTO_RGB_GREY_49}, {AWTO_RGB_GREY_6E}, {AWTO_RGB_BLUE_PALE},
    {AWTO_RGB_BLUE_DEEP}, {AWTO_RGB_GREY_55}, {AWTO_RGB_GREY_25}, {AWTO_RGB_BLUE_STEEL}, {AWTO_RGB_BLUE_NAVY}, {AWTO_RGB_BLACK}};
// 1 bit glyph foreground for each osd_style; background 0 is transparent and exposes the white/blue window.
static __code BYTE tAwtoStyle[8] = {AWTO_PAL_ACCENT, AWTO_PAL_GREY, AWTO_PAL_SURFACE, AWTO_PAL_ACCENT, AWTO_PAL_ALERT,
                                    AWTO_PAL_DIAG_WARN, AWTO_PAL_DIAG_TIMING, AWTO_PAL_DIAG_BOOT};      // styles 4..7: diagnostic console only (alert, log classes)
// Map B card (#357): opaque cells on the console's palette (no windows: they would need delay set 2, OT-6); styles 0..3 used.
#define AWTO_B2_INK         AWTO_OSD_CELL_B2(AWTO_PAL_CARDB_INK, AWTO_PAL_CARDB_SURF)
static __code BYTE tAwtoStyleB[8] = {AWTO_B2_INK, AWTO_OSD_CELL_B2(AWTO_PAL_CARDB_DIM, AWTO_PAL_CARDB_SURF),
                                     AWTO_OSD_CELL_B2(AWTO_PAL_CARDB_SURF, AWTO_PAL_CARDB_INK), AWTO_B2_INK,
                                     AWTO_OSD_CELL_B2(AWTO_PAL_DIAG_ALERT, AWTO_PAL_CARDB_SURF), AWTO_B2_INK, AWTO_B2_INK, AWTO_B2_INK};
#define AWTO_BAR_SURFACE            AWTO_PAL_SURFACE
#define AWTO_BAR_ACCENT             AWTO_PAL_ACCENT
#define AWTO_OSD_WIN_MIN_PX         2           // narrowest window drawn as asked; end == start runs to the line end (photo 2026-11-15)

static BYTE s_ucVpRows;                          // viewport rows (0 = the whole map is shown)
static BYTE s_ucVpFirst;                         // first view row shown (logical; rotated 180 the map rows are mirrored)
static BYTE s_ucVpEnd;                           // map row that currently holds the end-of-rows marker

// OSD blend, one owner for every awto screen (menu, selector, cards, backlight bar, console, GPIO page) (awto-ddc#176):
// type 11 = windows + character background (FRAME_CTRL_0A alpha_blend_type); glyph foreground stays opaque (10 = all blends it).
// 01 (windows only) showed nothing on the panel: our backgrounds are character cells. Level = osd_transparency as 0..255.
void AwtoOsdBlend(void)
{
    OsdFuncBlending(_OSD_TRANSPARENCY_WINDOW_AND_CHARACTER_BACKGROUND);
    OsdFuncTransparency(GET_OSD_TRANSPARENCY_STATUS());
}

// OSD orientation, one owner for every awto screen (#165). Rotate 180: glyphs downloaded turned by the VLC decoder (FRAME_CTRL_0B),
// the map written in reverse (osd_tc_cells), windows, position and the viewport mirrored (osd_tc_bar / _place / _scroll).
// Not the chip's auto rotation (FRAME_CTRL_41): with double size it showed boxes without text on unit 3 (SDK: they exclude each other).
// Mirror modes: no OSD mirror in hardware; the OSD stays upright.
static BYTE s_ucAwtoOsdRot = _OSD_ROTATE_DEGREE_0;

static void AwtoOsdOrient(BYTE ucRows)
{
    BYTE ucWant = _OSD_ROTATE_DEGREE_0;

#if(_DISPLAY_ROTATION_SUPPORT == _ON)
    if(GET_OSD_DISP_ROTATE() == _DISP_ROTATE_180)
    {
        ucWant = _OSD_ROTATE_DEGREE_180;
    }
#endif
    if(ucWant != s_ucAwtoOsdRot)
    {
        AwtoSyncPush(AWTO_SYNC_EV_ROT, (ucWant == _OSD_ROTATE_DEGREE_180) ? AWTO_ROT_OSD_180 : AWTO_ROT_OSD_UPRIGHT, 0);
    }
    s_ucAwtoOsdRot = ucWant;
    AwtoOsdRoll(0);
    ScalerOsdMapRotation(_OSD_ROTATE_DEGREE_0, _ENABLE, ucRows, _DISABLE, 0, _ENABLE);    // chip auto rotation off (undoes rot3 images)
}

// Map B (#357): a card in font B (delay set 2) next to the console in font A. While B shows, roll-up is off (regdb: fs_base1
// "not effective when ROLL-UP"); with fontx2_en font A still reads row_base0 / fs_base0, so osd_tc_scroll keeps scrolling A.
__xdata BYTE g_ucAwtoMapB;                       // 1 = font B on screen
__xdata BYTE g_ucAwtoMapBAsk;                    // the next OsdFuncApplyMap leaves the map B room (console open)
__xdata BYTE g_ucAwtoMapBHas;                    // the map in place has the room: g_ucAwtoMapBRow = its first word
__xdata BYTE g_ucAwtoMapBRow;
static __xdata BYTE s_ucRollWant;                // roll-up wanted by font A (back on when B goes)
static __xdata BYTE s_ucMapBTo;                  // osd_tc_* address map B (between osd_tc_b_open and osd_tc_b_show)
static __xdata BYTE s_ucMapBKeep;                // the console redraws itself: B, and the card's OSD_DISABLE timer, stay
static __xdata BYTE s_ucSaveW, s_ucSaveH, s_ucSaveVp;
static __xdata BYTE s_ucMapBLines;
static __xdata WORD s_usSaveFs;
static __xdata WORD s_usMapBMs;                  // (WORD)AwtoMs() at the B open: the close line's on-screen ms
#define AWTO_MAPB_FS()      ((WORD)g_ucAwtoMapBRow + AWTO_MAPB_ROWS + 1)   // B char words after B's rows + end word
#define AWTO_MAPB_F18      (AWTO_F_FRAME_CTRL_18_OSD_SPECIAL_EN | AWTO_F_FRAME_CTRL_18_POP_ON_EN | AWTO_F_FRAME_CTRL_18_FONTX2_EN | AWTO_F_FRAME_CTRL_18_FONT_B_DELAY_SEL)

// FRAME_CTRL_18 special function: roll-up (viewport scroll) on / off.
void AwtoOsdRoll(BYTE ucOn)
{
    s_ucRollWant = ucOn;
    if(g_ucAwtoMapB != 0)
    {
        return;                                 // font B on: A scrolls by its bases alone (above)
    }
    if(ucOn != 0)
    {
        ScalerSetBit(AWTO_R_FRAME_CTRL_18, ~(AWTO_F_FRAME_CTRL_18_OSD_SPECIAL_EN | AWTO_F_FRAME_CTRL_18_POP_ON_EN), AWTO_F_FRAME_CTRL_18_OSD_SPECIAL_EN);
    }
    else
    {
        ScalerSetBit(AWTO_R_FRAME_CTRL_18, ~AWTO_F_FRAME_CTRL_18_OSD_SPECIAL_EN, 0x00);
    }
}

// Map B off (one FRAME_CTRL_18 write: font B off, A's roll-up back as A wants it); ucWhy = AWTO_CARD_MAPB_* close line.
void osd_tc_b_off(BYTE ucWhy)
{
    if((g_ucAwtoMapB == 0) || (s_ucMapBKeep != 0))
    {
        return;
    }
    g_ucAwtoMapB = 0;
    ScalerSetBit(AWTO_R_FRAME_CTRL_18, (BYTE)~AWTO_MAPB_F18, (s_ucRollWant != 0) ? AWTO_F_FRAME_CTRL_18_OSD_SPECIAL_EN : 0x00);
    AwtoSyncPush(AWTO_SYNC_EV_CARD, ucWhy, (WORD)((WORD)AwtoMs() - s_usMapBMs));
}

static void osd_tc_b_on(void)
{
    ScalerSetByte(AWTO_R_FRAME_CTRL_40, s_ucMapBLines);                        // font B row total (the console open writes 0)
    ScalerSetBit(AWTO_R_FRAME_CTRL_18, (BYTE)~AWTO_MAPB_F18, AWTO_F_FRAME_CTRL_18_FONTX2_EN | AWTO_F_FRAME_CTRL_18_FONT_B_DELAY_SEL);
}

// 1 around the console's own redraw: B and its timer stay; 0 after it: B on again (the redraw reset FRAME_CTRL_18 / 40)
void osd_tc_b_keep(BYTE ucKeep)
{
    s_ucMapBKeep = ucKeep;
    if((ucKeep == 0) && (g_ucAwtoMapB != 0))
    {
        osd_tc_b_on();
    }
}

// ucChars x ucLines card in map B: rows, blank surface cells, bases. Until osd_tc_b_show the osd_tc_* calls address map B.
void osd_tc_b_open(BYTE ucChars, BYTE ucLines)
{
    BYTE ucI;

    s_ucSaveW = g_ucOsdWidth;
    s_ucSaveH = g_ucOsdHeight;
    s_ucSaveVp = s_ucVpRows;
    s_usSaveFs = g_usFontSelectStart;
    g_ucOsdWidth = ucChars;
    g_ucOsdHeight = ucLines;
    s_ucMapBLines = ucLines;
    s_ucVpRows = 0;
    g_usFontSelectStart = AWTO_MAPB_FS();
    s_ucMapBTo = 1;
    for(ucI = 0; ucI < ucLines; ucI++)
    {
        ScalerOsdCommandAllByte((WORD)g_ucAwtoMapBRow + ucI, AWTO_OSD_ROW_ON, osd_rh - 1, ucChars);
    }
    ScalerOsdCommandByte((WORD)g_ucAwtoMapBRow + ucLines, _OSD_BYTE0, AWTO_OSD_ROW_END);
    ScalerOsdCharCommandAllByteSeries(g_usFontSelectStart, AWTO_OSD_CHAR_1BIT_W(osd_cw), AWTO_OSD_GLYPH_BLANK, AWTO_OSD_CELL_B2(AWTO_PAL_CARDB_INK, AWTO_PAL_CARDB_SURF),
                                      (WORD)ucChars * ucLines);
    ScalerOsdSramBaseAddressSet(_OSD_B, g_ucAwtoMapBRow, g_usFontSelectStart, g_usFontTableStart);
    ScalerSetByte(AWTO_R_FRAME_CTRL_27, ScalerGetByte(AWTO_R_FRAME_CTRL_24));     // font B origin offset = font A's
    ScalerSetByte(AWTO_R_FRAME_CTRL_28, ScalerGetByte(AWTO_R_FRAME_CTRL_25));
    ScalerSetByte(AWTO_R_FRAME_CTRL_29, ScalerGetByte(AWTO_R_FRAME_CTRL_26));
}

// Back to map A, font B on (roll-up off in the same write); the OSD itself stays as it is (no disable / enable).
void osd_tc_b_show(void)
{
    g_ucOsdWidth = s_ucSaveW;
    g_ucOsdHeight = s_ucSaveH;
    s_ucVpRows = s_ucSaveVp;
    g_usFontSelectStart = s_usSaveFs;
    s_ucMapBTo = 0;
    s_usMapBMs = (WORD)AwtoMs();
    g_ucAwtoMapB = 1;
    ScalerTimerWaitForEvent(_EVENT_DEN_STOP);
    osd_tc_b_on();
}

// Map + palette + font: blank cells get the font's width (a part-written row keeps blanks; at Rotate 180, map mirrored, they
// come before its text, and blanks of another width shifted it sideways, Dan's photo 2026-11-13).
// Three parts, one per main-loop pass in the stepped console open (#311): map, palette, font.
static void osd_tc_open_map(BYTE ucChars, BYTE ucLines, BYTE ucFont)
{
    if(s_ucMapBKeep == 0)
    {
        ScalerTimerCancelTimerEvent(_USER_TIMER_EVENT_OSD_DISABLE);
        osd_tc_b_off(AWTO_CARD_MAPB_GONE);
    }
    OsdFuncDisableOsd();
    OsdFuncCloseWindow(_OSD_WINDOW_ALL);
    SET_OSD_DOUBLE_SIZE(GET_OSD_NVRAM_DOUBLE_SIZE());
    OsdFuncApplyMap(WIDTH(ucChars), HEIGHT(ucLines), COLOR(0, 0), osd_font_cw(ucFont));
    AWTO_PSTG(AWTO_PSTG_CON_MAP);
    AwtoOsdOrient(HEIGHT(ucLines));                                                            // also: roll-up (viewport scroll) off
    AWTO_PSTG(AWTO_PSTG_CON_ORIENT);
    s_ucVpRows = 0;
    s_ucVpFirst = 0;
    s_ucVpEnd = ucLines;
    AwtoOsdBlend();
}

static void osd_tc_open_pal(void)
{
    BYTE ucI;

    OsdPaletteSelectPalette(_PALETTE_MAIN_MENU);
    for(ucI = 0; ucI < AWTO_PAL_N; ucI++)
    {
        ScalerOsdSetColorPalette(ucI + AWTO_PAL_FIRST, tAwtoPal[ucI][0], tAwtoPal[ucI][1], tAwtoPal[ucI][2]);
    }
    AWTO_PSTG(AWTO_PSTG_CON_PAL);
}

static void osd_tc_open_font(BYTE ucFont)
{
    osd_font_load(ucFont);
    AWTO_PSTG(AWTO_PSTG_CON_FONT);
}

// ucPart 0 map, 1 palette, 2 font; 0xFF all three
void osd_tc_open_part(BYTE ucPart, BYTE ucChars, BYTE ucLines, BYTE ucFont)
{
    if((ucPart == 0) || (ucPart == 0xFF))
    {
        osd_tc_open_map(ucChars, ucLines, ucFont);
    }
    if((ucPart == 1) || (ucPart == 0xFF))
    {
        osd_tc_open_pal();
    }
    if((ucPart == 2) || (ucPart == 0xFF))
    {
        osd_tc_open_font(ucFont);
    }
}

void osd_tc_open(BYTE ucChars, BYTE ucLines, BYTE ucFont)
{
    osd_tc_open_part(0xFF, ucChars, ucLines, ucFont);
}

void osd_tc_rowh(BYTE ucRh)
{
    BYTE ucI;

    for(ucI = 0; ucI < g_ucOsdHeight; ucI++)
    {
        ScalerOsdCommandAllByte(ucI, 0x80, ucRh - 1, g_ucOsdWidth);   // row height - 1 (5 bit); the SDK map uses 17 = 18 px
    }
}

// Viewport (standard scrolling screen): the map has more rows than the window shows. Hardware roll-up moves the first displayed row
// (0x3A19 row base, 0x3A1B/0x3A1C font-select base, 12 bit) and the end-of-rows marker moves with it, so the shown height stays fixed.
// Call after osd_tc_open and the font load. Returns the first row actually shown (limited by the map end and by the 12-bit base).
BYTE osd_tc_scroll(BYTE ucFirst)
{
    WORD usFs;
    BYTE ucPs;                                       // first map row shown; rotated 180 the view [first, first + rows) is map rows
    BYTE ucEnd;                                      // [H - rows - first, H - first) (osd_tc_cells writes row r at H - 1 - r)

    if(s_ucVpRows == 0)
    {
        return 0;
    }
    if(ucFirst > g_ucOsdHeight - s_ucVpRows)
    {
        ucFirst = g_ucOsdHeight - s_ucVpRows;
    }
    ucPs = (s_ucAwtoOsdRot == _OSD_ROTATE_DEGREE_180) ? (g_ucOsdHeight - s_ucVpRows - ucFirst) : ucFirst;
    while((ucPs != 0) && ((WORD)ucPs * g_ucOsdWidth + g_usFontSelectStart > 4095))
    {
        ucPs--;
    }
    ucFirst = (s_ucAwtoOsdRot == _OSD_ROTATE_DEGREE_180) ? (g_ucOsdHeight - s_ucVpRows - ucPs) : ucPs;
    ucEnd = ucPs + s_ucVpRows;
    if(s_ucVpEnd < g_ucOsdHeight)
    {
        ScalerOsdCommandAllByte(s_ucVpEnd, 0x80, osd_rh - 1, g_ucOsdWidth);    // the old marker row is a text row again
    }
    if(ucEnd < g_ucOsdHeight)
    {
        ScalerOsdCommandByte(ucEnd, _OSD_BYTE0, 0x00);                         // end-of-rows marker: the view stops here
    }
    s_ucVpEnd = ucEnd;
    s_ucVpFirst = ucFirst;
    usFs = g_usFontSelectStart + (WORD)ucPs * g_ucOsdWidth;
    AwtoOsdRoll(ucPs);                                                                          // top: roll-up off (roll-up at row 0 showed a blank OSD on unit 2, Dan 2026-11-12)
    ScalerSetByte(AWTO_R_FRAME_CTRL_19, ucPs);                                                  // also at the top: font A reads them while map B shows (#357)
    ScalerSetBit(AWTO_R_FRAME_CTRL_1B, (BYTE)~AWTO_F_FRAME_CTRL_1B_FS_BASE0, (BYTE)((usFs >> 8) << 4));
    ScalerSetByte(AWTO_R_FRAME_CTRL_1C, (BYTE)usFs);
    return ucFirst;
}

void osd_tc_viewport(BYTE ucRows)
{
    s_ucVpRows = (ucRows < g_ucOsdHeight) ? ucRows : 0;
    s_ucVpFirst = 0;
    osd_tc_scroll(0);
}

void osd_tc_cells(BYTE ucRow, BYTE ucCell, BYTE __xdata *pucTiles, BYTE ucN, BYTE ucStyle)
{
    BYTE ucB0 = AWTO_OSD_CHAR_1BIT_W(osd_cw);   // 1 bit font, cell width = the loaded font's pixel width
    BYTE ucB2 = (s_ucMapBTo != 0) ? tAwtoStyleB[ucStyle] : (tAwtoStyle[ucStyle] << 4);   // foreground; transparent background (map B: opaque)

    if(s_ucAwtoOsdRot == _OSD_ROTATE_DEGREE_180)      // row r cell c -> row H-1-r cell W-1-c: write the run backwards from its last cell
    {
        ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, g_usFontSelectStart + (WORD)(g_ucOsdHeight - 1 - ucRow) * g_ucOsdWidth +
                         (g_ucOsdWidth - ucCell - ucN), _OSD_WITHOUT_DB);
        pucTiles += ucN;
        while(ucN-- != 0)
        {
            AWTO_OSD_PORT(ucB0);
            AWTO_OSD_PORT(*--pucTiles);
            AWTO_OSD_PORT(ucB2);
        }
        return;
    }
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, g_usFontSelectStart + (WORD)ucRow * g_ucOsdWidth + ucCell, _OSD_WITHOUT_DB);
    while(ucN-- != 0)                              // one address, then B0 B1 B2 per cell (the word address increments by itself)
    {
        AWTO_OSD_PORT(ucB0);
        AWTO_OSD_PORT(*pucTiles++);
        AWTO_OSD_PORT(ucB2);
    }
}

void osd_tc_bar(BYTE ucWin, WORD usX0, WORD usY0, WORD usX1, WORD usY1, BYTE ucColour)
{
    if(usX1 <= usX0)                                 // end == start: the window runs to the line end (1 % backlight bar)
    {
        usX1 = usX0 + AWTO_OSD_WIN_MIN_PX - 1;
    }
    if(usY1 <= usY0)
    {
        usY1 = usY0 + AWTO_OSD_WIN_MIN_PX - 1;
    }
    if(s_ucAwtoOsdRot == _OSD_ROTATE_DEGREE_180)      // inclusive px, mirrored inside the map box
    {
        WORD usW = (WORD)g_ucOsdWidth * osd_cw - 1;
        WORD usH = (WORD)((s_ucVpRows != 0) ? s_ucVpRows : g_ucOsdHeight) * osd_rh - 1;   // the box shown (viewport rows)
        WORD usT = usW - usX0;

        usX0 = usW - usX1;
        usX1 = usT;
        usT = usH - usY0;
        usY0 = usH - usY1;
        usY1 = usT;
    }
    OsdWindowDrawing(ucWin, usX0, usY0, usX1, usY1, (ucColour == 0) ? AWTO_BAR_SURFACE : AWTO_BAR_ACCENT);
}

void osd_tc_win_draw(BYTE ucWin, WORD usX0, WORD usY0, WORD usX1, WORD usY1)     // g_stOsdWindow as the caller set it (#226 demo): no minimum width, mirrored for Rotate 180 like osd_tc_bar
{
    if(s_ucAwtoOsdRot == _OSD_ROTATE_DEGREE_180)
    {
        WORD usW = (WORD)g_ucOsdWidth * osd_cw - 1;
        WORD usH = (WORD)((s_ucVpRows != 0) ? s_ucVpRows : g_ucOsdHeight) * osd_rh - 1;
        WORD usT = usW - usX0;

        usX0 = usW - usX1;
        usX1 = usT;
        usT = usH - usY0;
        usY0 = usH - usY1;
        usY1 = usT;
    }
    SET_OSD_WINDOW_NUMBER(ucWin);
    SET_OSD_WINDOW_ENABLE(_ENABLE);
    SET_OSD_WINDOW_BLEND_ENABLE(_ENABLE);
    ScalerTimerWaitForEvent(_EVENT_DVS);
    ScalerOsdDrawWindow(usX0, usY0, usX1, usY1);
}

void osd_tc_bar_off(BYTE ucWin)
{
    ScalerOsdWindowDisable((EnumOsdWindowsType)ucWin);
}

// VLC font download, docs/osd/glyph-load.md: value map -> 0x3A0F..0x3A16, 0x3A17[0] = 1, destination word address,
// stream bytes to the data port (3 decoded bytes = one word per 6 symbols, END code stops), 0x3A17[1:0] = 0
void osd_tc_vlc_begin(BYTE __xdata *pucMap, WORD usTile)
{
    BYTE ucI;

    for(ucI = 0; ucI < 8; ucI++)
    {
        ScalerSetByte(AWTO_R_FRAME_CTRL_0F + ucI, pucMap[ucI]);
    }
    if(s_ucAwtoOsdRot == _OSD_ROTATE_DEGREE_180)     // glyphs land rotated, as ScalerOsdHardwareVLC does for 180
    {
        ScalerSetBit(AWTO_R_FRAME_CTRL_0B, ~(AWTO_F_FRAME_CTRL_0B_F_DL_SWAP | AWTO_F_FRAME_CTRL_0B_HW_ROTATE_EN | AWTO_F_FRAME_CTRL_0B_ROTATION),
                     (_OSD_ROTATE_CW180 | _OSD_ROTATE_HARDWARE_ROTATION_ENABLE | _OSD_ROTATE_NORMAL));
    }
    ScalerSetBit(AWTO_R_FRAME_CTRL_17, ~(AWTO_F_FRAME_CTRL_17_DECODE_NOCOM_DATA | AWTO_F_FRAME_CTRL_17_OSD_COMPRESSION_EN), AWTO_F_FRAME_CTRL_17_OSD_COMPRESSION_EN);
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, g_usFontTableStart + usTile * 9, _OSD_WITHOUT_DB);
}

void osd_tc_vlc_put(BYTE __xdata *pucData, BYTE ucN)
{
    while(ucN-- != 0)
    {
        ScalerOsdDataPort(*pucData++);
    }
}

void osd_tc_vlc_end(void)
{
    // The RTD2795 decoder flushes its final decoded words after the last stream byte. Clearing compression
    // immediately truncates/corrupts glyph SRAM; Realtek's loader waits 2 ms here for the same reason.
    ScalerTimerDelayXmsQuiet(2);
    ScalerSetBit(AWTO_R_FRAME_CTRL_17, ~(AWTO_F_FRAME_CTRL_17_DECODE_NOCOM_DATA | AWTO_F_FRAME_CTRL_17_OSD_COMPRESSION_EN), 0x00);
    ScalerSetBit(AWTO_R_FRAME_CTRL_0B, ~(AWTO_F_FRAME_CTRL_0B_F_DL_SWAP | AWTO_F_FRAME_CTRL_0B_HW_ROTATE_EN | AWTO_F_FRAME_CTRL_0B_ROTATION), _OSD_ROTATE_NORMAL);
}

// Own placement: the SDK OsdDispSetPosition assumes 12 x 18 cells, so rows x 36 above the panel height wraps to an off-screen position.
void osd_tc_place(BYTE ucH, BYTE ucV, BYTE ucBig)
{
    DWORD ulW = (DWORD)g_ucOsdWidth * osd_cw;
    DWORD ulH = (DWORD)((s_ucVpRows != 0) ? s_ucVpRows : g_ucOsdHeight) * osd_rh;
    WORD usX = 0;
    WORD usY = 0;
    BYTE ucStep = (ScalerOsdGetHorizontalDelayStep() == _OSD_HORIZONTAL_DELAY_STEP_1_PIXEL) ? 1 : 4;

    if(s_ucAwtoOsdRot == _OSD_ROTATE_DEGREE_180)      // the box sits where the upright one would, turned with the panel
    {
        ucH = 100 - ucH;
        ucV = 100 - ucV;
    }
    SET_OSD_DOUBLE_SIZE(ucBig);
    ScalerOsdDoubleFunction(ucBig, ucBig);
    if(ucBig != 0)
    {
        ulW *= 2;
        ulH *= 2;
    }
    if((DWORD)_PANEL_DH_WIDTH > ulW)
    {
        usX = (WORD)((((DWORD)_PANEL_DH_WIDTH - ulW) / ucStep) * ucH / 100);
    }
    if((DWORD)_PANEL_DV_HEIGHT > ulH)
    {
        usY = (WORD)((((DWORD)_PANEL_DV_HEIGHT - ulH) * ucV) / 100);
    }
    if(ucBig != 0)
    {
        usX /= 2;
        usY /= 2;
    }
    OsdFuncSetPosition(_OSD_POSITION_GLOBAL_A, usX, usY);
}

// Box at usLeft px from the viewer's left edge and usBottom px from the bottom edge (Rotate 180: the panel's top right)
void osd_tc_place_corner(WORD usLeft, WORD usBottom, BYTE ucBig)
{
    DWORD ulW = (DWORD)g_ucOsdWidth * osd_cw * (ucBig + 1);
    DWORD ulH = (DWORD)((s_ucVpRows != 0) ? s_ucVpRows : g_ucOsdHeight) * osd_rh * (ucBig + 1);
    WORD usX = usLeft;
    WORD usY = ((DWORD)_PANEL_DV_HEIGHT > ulH + usBottom) ? (WORD)((DWORD)_PANEL_DV_HEIGHT - ulH - usBottom) : 0;
    BYTE ucStep = (ScalerOsdGetHorizontalDelayStep() == _OSD_HORIZONTAL_DELAY_STEP_1_PIXEL) ? 1 : 4;

    if(s_ucAwtoOsdRot == _OSD_ROTATE_DEGREE_180)
    {
        usX = ((DWORD)_PANEL_DH_WIDTH > ulW + usLeft) ? (WORD)((DWORD)_PANEL_DH_WIDTH - ulW - usLeft) : 0;
        usY = usBottom;
    }
    SET_OSD_DOUBLE_SIZE(ucBig);
    ScalerOsdDoubleFunction(ucBig, ucBig);
    OsdFuncSetPosition(_OSD_POSITION_GLOBAL_A, usX / ucStep / (ucBig + 1), usY / (ucBig + 1));
}

// Box top right corner at usRight px from the viewer's right edge and usTop px from the top edge (Rotate 180: the panel's lower left)
void osd_tc_place_top_right(WORD usRight, WORD usTop, BYTE ucBig)
{
    DWORD ulW = (DWORD)g_ucOsdWidth * osd_cw * (ucBig + 1);
    DWORD ulH = (DWORD)((s_ucVpRows != 0) ? s_ucVpRows : g_ucOsdHeight) * osd_rh * (ucBig + 1);
    WORD usX = ((DWORD)_PANEL_DH_WIDTH > ulW + usRight) ? (WORD)((DWORD)_PANEL_DH_WIDTH - ulW - usRight) : 0;
    WORD usY = usTop;
    BYTE ucStep = (ScalerOsdGetHorizontalDelayStep() == _OSD_HORIZONTAL_DELAY_STEP_1_PIXEL) ? 1 : 4;

    if(s_ucAwtoOsdRot == _OSD_ROTATE_DEGREE_180)
    {
        usX = usRight;
        usY = ((DWORD)_PANEL_DV_HEIGHT > ulH + usTop) ? (WORD)((DWORD)_PANEL_DV_HEIGHT - ulH - usTop) : 0;
    }
    if(s_ucMapBTo != 0)                                 // map B: delay set 2; the scale is font A's too (one global double size)
    {
        OsdFuncSetPosition(_OSD_POSITION_GLOBAL_B, usX / ucStep / (ucBig + 1), usY / (ucBig + 1));
        return;
    }
    SET_OSD_DOUBLE_SIZE(ucBig);
    ScalerOsdDoubleFunction(ucBig, ucBig);
    OsdFuncSetPosition(_OSD_POSITION_GLOBAL_A, usX / ucStep / (ucBig + 1), usY / (ucBig + 1));
}

void osd_tc_show(BYTE ucOn)
{
    g_ucAwtoMenuOn = (ucOn != 0);
    if(ucOn != 0)
    {
        OsdFuncEnableOsd();
    }
    else
    {
        OsdFuncDisableOsd();
    }
}

void osd_tc_close(void)
{
    osd_tc_b_off(AWTO_CARD_MAPB_GONE);
    g_ucAwtoMenuOn = 0;
    AwtoOsdRoll(0);                                                                             // viewport roll-up off: the next screen starts at row 0
    s_ucVpRows = 0;
    OsdFuncDisableOsd();
    OsdFuncCloseWindow(_OSD_WINDOW_ALL);
    SET_OSD_DOUBLE_SIZE(GET_OSD_NVRAM_DOUBLE_SIZE());
    g_ucOsdWidth = 0;
    g_ucOsdHeight = 0;
    SET_OSD_STATE(_MENU_NONE);
    if(SysModeGetModeState() == _MODE_STATUS_NOSIGNAL)       // the no-signal path dropped while the menu was up
    {
        ScalerTimerActiveTimerEvent(SEC(2), _USER_TIMER_EVENT_OSD_SHOW_NO_SIGNAL);
    }
}
#endif
#endif//#if(_OSD_TYPE == _REALTEK_2014_OSD)
