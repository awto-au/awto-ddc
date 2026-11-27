unsigned char xdata a;
unsigned char code t[2] = {1, 2};
unsigned char data d;
unsigned char idata i;
bit b;
bit f(void) { return b; }
unsigned char xdata * xdata p;
sfr P0X = 0x80;
sbit P01 = P0X ^ 1;
unsigned char xdata r _at_ 0xFF00;
void isr(void) interrupt 1 using 2 { a++; }
