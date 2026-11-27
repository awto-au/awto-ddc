// does SDCC give a __using(1) callee bank-1 register addresses (ar7 = 0x0F)?
volatile unsigned char __xdata x[4];
unsigned char g(unsigned char a, unsigned char b) __using(1)
{
    unsigned char i, s = 0;
    for (i = 0; i < a; i++) { s += x[i & 3] ^ b; x[0] = s; }
    return s;
}
void isr(void) __interrupt(0) __using(1)
{
    x[1] = g(x[2], x[3]);
}
