/* Host driver for scripts/osd_lines_view.py (awto-ddc#226): draws a 384 x 216 scope trace with osd_lines and prints every uploaded
 * tile as "tile <id> <27 bytes hex>", then the canvas as "px <y> <384 chars 0/1>" so the viewer can check the byte packing. */
#include <math.h>
#include <stdio.h>
#include "osd_lines.h"

#define COLS 32
#define ROWS 12
#define W (COLS * OSD_TILE_W)
#define H (ROWS * OSD_TILE_H)

static uint8_t pixels[OSD_BITMAP_BYTES(COLS, ROWS)];
static uint8_t dirty[OSD_DIRTY_BYTES(COLS, ROWS)];
static osd_canvas canvas;

static uint8_t upload(uint16_t id, const uint8_t *b, uint16_t n, void *user)
{
    uint16_t i;
    (void)user;
    printf("tile %u", id);
    for (i = 0; i < n; ++i) printf(" %02x", b[i]);
    printf("\n");
    return 1;
}

int main(void)
{
    int16_t y[W];
    uint16_t x;
    int yy, xx;

    osd_canvas_init(&canvas, COLS, ROWS, pixels, sizeof pixels, dirty, sizeof dirty);
    osd_clear(&canvas);
    osd_line(&canvas, 0, 0, W - 1, 0, 1);                       /* frame */
    osd_line(&canvas, W - 1, 0, W - 1, H - 1, 1);
    osd_line(&canvas, W - 1, H - 1, 0, H - 1, 1);
    osd_line(&canvas, 0, H - 1, 0, 0, 1);
    for (xx = 0; xx < W; xx += 4) osd_pixel(&canvas, (int16_t)xx, H / 2, 1);          /* dotted centre line */
    for (yy = 0; yy < H; yy += 4) osd_pixel(&canvas, W / 2, (int16_t)yy, 1);
    for (x = 0; x < W; ++x)                                      /* two sines + a square-ish burst */
    {
        double t = (double)x / W;
        double v = 0.55 * sin(2 * 3.14159265 * 6 * t) + 0.25 * sin(2 * 3.14159265 * 23 * t);
        if (t > 0.70 && t < 0.80) v = (((int)(t * 400)) & 1) ? 0.8 : -0.8;
        y[x] = (int16_t)(H / 2 - v * (H / 2 - 6));
    }
    for (x = 1; x < W; ++x) osd_line(&canvas, (int16_t)(x - 1), y[x - 1], (int16_t)x, y[x], 1);
    osd_line(&canvas, 20, 20, 120, 60, 1);                       /* a diagonal and a steep line (all octants are tested upstream) */
    osd_line(&canvas, 150, 200, 160, 20, 1);
    osd_flush(&canvas, upload, 0);
    for (yy = 0; yy < H; ++yy)
    {
        printf("px %d ", yy);
        for (xx = 0; xx < W; ++xx)
        {
            int bit = (yy % OSD_TILE_H) * OSD_TILE_W + (xx % OSD_TILE_W);
            int id = (yy / OSD_TILE_H) * COLS + (xx / OSD_TILE_W);
            putchar((pixels[id * OSD_TILE_BYTES + (bit >> 3)] & (0x80 >> (bit & 7))) ? '1' : '0');
        }
        printf("\n");
    }
    return 0;
}
