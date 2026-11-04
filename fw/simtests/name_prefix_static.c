/* probe: file-scope static `led_state` has the _led_ prefix of fn `led`, so it is treated as led's local */
#include "sim.h"
volatile unsigned char seed = 2;
static unsigned int led_state;

unsigned int led(void)
{
    unsigned char t[4]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 4; i++) t[i] = i;
    for (i = 0; i < 4; i++) s += t[i];
    led_state += s;
    return led_state;
}
void main(void)
{
    led_state = 7;
    sim_val("led1", led());
    sim_val("led2", led());
    sim_done();
}
