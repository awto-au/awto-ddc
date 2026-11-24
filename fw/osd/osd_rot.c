#include "UserCommonInclude.h"

// OSD 180 degree rotation helpers for full-screen OSD users that draw their own map + glyphs (flash screen, test screens): docs/osd/rotation.md.
// The OSD circuit is not rotated with the picture: with display Rotate 180 (panel mounted turned) an upright map shows upside down.
// Same rule as the menu text layer (fw/osd/text_layer.c): map cell c -> cells - 1 - c, glyph bitmaps turned 180 degrees.

#define AWTO_ROT_BYTES_PER_WORD                 3       // a glyph word = 24 bits = two 12 px rows

__xdata BYTE g_ucAwtoOsdRot;                            // latched by the screen being drawn (one full-screen OSD screen at a time): XDATA is scarce

BYTE AwtoOsdRot180(void)                                // 1 = draw the OSD turned (display Rotate 180), 0 = upright
{
#if(_DISPLAY_ROTATION_SUPPORT == _ON)
    return (GET_OSD_DISP_ROTATE() == _DISP_ROTATE_180) ? 1 : 0;
#else
    return 0;
#endif
}

#define AWTO_REV2(n)                            (n), (n) + 2 * 64, (n) + 1 * 64, (n) + 3 * 64     // bit reverse table of 256: the usual 2-bit-at-a-time pattern
#define AWTO_REV4(n)                            AWTO_REV2(n), AWTO_REV2((n) + 2 * 16), AWTO_REV2((n) + 1 * 16), AWTO_REV2((n) + 3 * 16)
#define AWTO_REV6(n)                            AWTO_REV4(n), AWTO_REV4((n) + 2 * 4), AWTO_REV4((n) + 1 * 4), AWTO_REV4((n) + 3 * 4)

#pragma place group(osdrot_13)                          // table and its leaf reader share a bank (movc reads the running bank)
static const __code BYTE s_aucRev[256] = { AWTO_REV6(0), AWTO_REV6(2), AWTO_REV6(1), AWTO_REV6(3) };

#pragma place group(osdrot_13)
BYTE AwtoOsdRevByte(BYTE ucB)                           // bit order of one byte reversed
{
    return s_aucRev[ucB];
}

WORD AwtoOsdRotCell(WORD usCell, WORD usCells)          // map cell index when the whole map is turned 180
{
    return usCells - 1 - usCell;
}

// Byte ucOut of a glyph that has ucWords words (3 bytes each, low byte first, row-major bits), turned 180: it is
// AwtoOsdRevByte(source byte AwtoOsdRotSrc(ucOut, ucWords)) of the unturned glyph.
BYTE AwtoOsdRotSrc(BYTE ucOut, BYTE ucWords)
{
    BYTE ucWord = ucOut / AWTO_ROT_BYTES_PER_WORD;
    BYTE ucByte = ucOut % AWTO_ROT_BYTES_PER_WORD;

    return (BYTE)((ucWords - 1 - ucWord) * AWTO_ROT_BYTES_PER_WORD + (AWTO_ROT_BYTES_PER_WORD - 1 - ucByte));
}
