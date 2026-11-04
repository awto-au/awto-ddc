/* sim test runtime: serial output via SBUF; sim_done() is the halt point the harness breaks on */
#ifndef SIM_H
#define SIM_H
void sim_putc(char c);
void sim_puts(const char *s);
void sim_val(const char *tag, unsigned long v);   /* prints "tag=XXXXXXXX\n" */
void sim_done(void);                              /* prints sentinel, then halts */
#define SIM_SENTINEL "SIM-DONE"
#endif
