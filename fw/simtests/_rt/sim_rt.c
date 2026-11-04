#include <8051.h>
#include "sim.h"

void sim_putc(char c)
{
    SBUF = c;
    while (!TI) { }
    TI = 0;
}

void sim_puts(const char *s)
{
    while (*s)
        sim_putc(*s++);
}

void sim_val(const char *tag, unsigned long v)
{
    signed char i;
    sim_puts(tag);
    sim_putc('=');
    for (i = 28; i >= 0; i -= 4)
        sim_putc("0123456789ABCDEF"[(unsigned char)(v >> i) & 15]);
    sim_putc('\n');
}

void sim_halt(void)       /* harness sets its breakpoint here */
{
    for (;;) { }
}

void sim_done(void)
{
    sim_puts(SIM_SENTINEL "\n");
    sim_halt();
}
