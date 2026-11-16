/* mode.h: input timing, mode state and display setup.
 * DRAFT interface (wave A); spec mode (step 8) refines it.
 * mode_state values are read by host tools (awto-ddc unit_health): keep the numbers. */
#ifndef AWTO_MODE_H
#define AWTO_MODE_H

#include <stdint.h>

enum mode_state {
    MS_START = 0, MS_SEARCH = 1, MS_SETUP = 2, MS_SHOWING = 3, MS_UNSUPPORTED = 4,
    MS_NO_SIGNAL = 5, MS_SAVING = 6, MS_OFF = 7, MS_SERVICE = 8
};

#define TF_INTERLACED 0x01
#define TF_HSYNC_POS  0x02
#define TF_VSYNC_POS  0x04

struct timing {
    uint16_t h_total, h_active, h_start, h_sync;   /* pixels */
    uint16_t v_total, v_active, v_start, v_sync;   /* lines */
    uint32_t pclk_khz;
    uint16_t vfreq_mhz10;                          /* field rate, 0.01 Hz units */
    uint8_t  flags;                                /* TF_* */
    uint8_t  colour;                               /* space / depth / range, packed per spec mode */
};

uint8_t mode_state(void);
uint32_t mode_dclk_khz(void);                      /* current display (output) pixel clock */
const struct timing *mode_timing(void);            /* valid in MS_SETUP and MS_SHOWING */
uint8_t mode_measure(uint8_t port, struct timing *t);   /* 1 = stable measurement */
uint8_t mode_setup(const struct timing *in);       /* program capture, memory, scaling, output; 1 = ok */
void    mode_service(void);                        /* main-loop step of the mode state machine */

#endif
