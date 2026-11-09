#ifndef PM_OSD_H
#define PM_OSD_H
#include <stdint.h>
#ifdef __SDCC_mcs51
#define PM_CODE __code
#define PM_XDATA __xdata
#else
#define PM_CODE
#define PM_XDATA
#endif
#define PM_COLS 28
#define PM_ROWS 36
#define PM_CELLS (PM_COLS * PM_ROWS)
#define PM_CELL_W 12
#define PM_CELL_H 12
#define PM_FS_BASE (PM_ROWS + 1)
#define PM_FONT_BASE (PM_FS_BASE + PM_CELLS)
#define PM_ACTORS 5
#define PM_DIRTY_CAP 40
/* Host/firmware supplies this synchronous, non-reentrant OSD SRAM writer.
 * It must preserve all three bytes and increment addresses in WORDS.
 * Caller owns and serialises the OSD for the entire load/flush operation. */
void pm_hw_word(uint16_t address, uint8_t b0, uint8_t b1, uint8_t b2);
void pm_load(void);
void pm_redraw(void);
void pm_flush(void);
/* Returns 0 without changing state on invalid arguments. Slots later in the
 * array draw on top. Hidden actors retain their saved positions. */
uint8_t pm_actor(uint8_t slot, uint8_t x, uint8_t y, uint16_t glyph, uint8_t fg, uint8_t visible);
/* Cached sub-cell motion: x/y in unscaled OSD pixels, multiples of 3.
 * frame 0..7 = right/down/left/up, two mouth poses each; 8..11 = ghost
 * right/down/left/up. At most four fragments per 12x12 visible actor;
 * hardware glyph slots remain 12x18. */
uint8_t pm_actor_smooth(uint8_t slot, uint16_t x, uint16_t y, uint8_t frame, uint8_t fg, uint8_t visible);
uint8_t pm_background(uint8_t x, uint8_t y, uint8_t glyph);
uint8_t pm_eat(uint8_t x, uint8_t y);
uint8_t pm_background_at(uint8_t x, uint8_t y);
/* Adapter helper, not called by the core. Supply pm_bus_write in firmware.
 * No flash, I2C, ISP, relay, startup hook, or OSD enable operations are here. */
void pm_bus_write(uint16_t reg, uint8_t value);
void pm_rtd_word(uint16_t address, uint8_t b0, uint8_t b1, uint8_t b2);
#endif
