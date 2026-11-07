/* input.h: video input ports (detection, selection, hot-plug).
 * DRAFT interface (wave A); specs input/hdmi/dp (steps 10-12) refine it.
 * Board: D1 = DisplayPort, D2 and D3 = HDMI (one driver, port-parametrised). */
#ifndef AWTO_INPUT_H
#define AWTO_INPUT_H

#include <stdint.h>

enum inp_port { IN_NONE = 0, IN_D1 = 1, IN_D2 = 2, IN_D3 = 3 };

void    inp_init(void);
uint8_t inp_cable(uint8_t port);            /* 1 = cable/5 V present */
uint8_t inp_locked(uint8_t port);           /* 1 = link/clock stable, data path usable */
void    inp_select(uint8_t port);           /* route the port to the capture path */
uint8_t inp_selected(void);
void    inp_hotplug(uint8_t port, uint8_t asserted);
void    inp_service(void);                  /* main loop: detection, link maintenance */

#endif
