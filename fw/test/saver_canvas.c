#include <stdint.h>
#include <string.h>
#include "UserCommonInclude.h"
#define OSD_NO_FLUSH
#include "../../tools/osd_lines/osd_lines.c"

// Shared by the savers (one runs at a time): the osd_lines renderer (Asteroids), the band canvas, the 1-bit tile upload.
// Scope 1 (the former owner of this file) is retired, docs/saver-mode.md.

#define SC_BANDS                                2                   // size of the shared band canvas (Asteroids draws into it, Scope 2 uses the tile buffer)
#define SC_ROWS                                 12
#define SC_BAND_ROWS                            (SC_ROWS / SC_BANDS)

__xdata uint8_t g_aucScPix[OSD_BITMAP_BYTES(1, SC_BAND_ROWS)];
__xdata uint8_t g_aucScDirty[OSD_DIRTY_BYTES(1, SC_BAND_ROWS)];
__xdata osd_canvas g_scCv;

void AwtoScTile(WORD usAddr, BYTE __xdata *pucB)                    // a 1-bit tile (canonical bytes; turned in place for Rotate 180) by direct port stores: Asteroids
{
    BYTE ucK;

    if(g_ucAwtoOsdRot != 0)
    {
        AwtoOsdTurn(pucB, OSD_TILE_BYTES);                              // then the upright word order = the turned word order
    }
    ScalerOsdAddrSet(_OSD_SRAM, _OSD_BYTEALL, usAddr, _OSD_WITHOUT_DB);
    for(ucK = 0; ucK < OSD_TILE_BYTES; ucK += 3)
    {
        AWTO_OSD_PORT(pucB[ucK + 2]);
        AWTO_OSD_PORT(pucB[ucK + 1]);
        AWTO_OSD_PORT(pucB[ucK]);
    }
}
