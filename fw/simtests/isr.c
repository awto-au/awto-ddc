/* timer0 ISR and main both call work() (main inside EA=0 sections: plain SDCC statics aren't reentrant).
   ISR keeps firing while main prints, so a work() frame overlapping sim_val's would corrupt the output. */
#include <8051.h>
#include "sim.h"
volatile unsigned char seed = 4;
volatile unsigned int isr_n, isr_bad;

unsigned int work(unsigned char x)
{
    unsigned char t[6]; unsigned char i; unsigned int s = 0;
    for (i = 0; i < 6; i++) t[i] = x + i * 3;
    for (i = 0; i < 6; i++) s += t[i] * 5;
    return s;
}
void t0_isr(void) __interrupt(1)
{
    unsigned char v = (unsigned char)(isr_n % 100);    /* keep x+15 < 256 */
    unsigned int local = work(v);
    if (local != (unsigned int)(v * 30 + 225)) isr_bad++;      /* 5*(6v + 3*15) */
    TH0 = 0xF8; TL0 = 0;                 /* period 2048 cycles > ISR runtime */
    isr_n++;
}
void main(void)
{
    unsigned int k, bad = 0; unsigned long sum = 0; unsigned int r;
    TMOD = 0x01; TH0 = 0xF8; TL0 = 0; TR0 = 1; ET0 = 1; EA = 1;
    for (k = 0; k < 300; k++) {
        unsigned char x = (unsigned char)(k % 100) + seed;
        EA = 0; r = work(x); EA = 1;
        if (r != (unsigned int)(x * 30 + 225)) bad++;
        sum += r;
    }
    while (isr_n < 20) { }
    for (k = 0; k < 40; k++) { sim_val("main_sum", sum + k); sim_val("main_bad", bad); }
    EA = 0; TR0 = 0;
    sim_val("isr_bad", isr_bad);
    sim_val("isr_ran", isr_n >= 20);
    sim_done();
}
