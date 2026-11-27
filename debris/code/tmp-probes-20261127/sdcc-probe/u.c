unsigned char g;
void leaf(unsigned char a, unsigned int b) { unsigned char t[4]; t[a & 3] = b; g = t[0]; }
unsigned int mid(unsigned char a, unsigned char b, unsigned char c) { unsigned long x = a; x *= b; leaf(c, x); return x; }
void top(void) { unsigned char i; for (i = 0; i < 3; i++) g += mid(i, i, i); }
