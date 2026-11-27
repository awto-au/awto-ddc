volatile __bit f = 0;
unsigned int c;
void isr(void) __interrupt(5) { f = 1; }
void g(void) { f = 0; c = 0; if (f == 1) { c = 0; } }
