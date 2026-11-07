unsigned char x, y, r; bit b1, b2; unsigned int u; char c;
bit rb(unsigned char a) { return a; }
void fb(bit a);
void t1(void){ r = ~(x == y); }
void t2(void){ b1 = x & 0x81; }
void t3(void){ fb(x); }
void t4(void){ fb(u); }
void t5(void){ if (~b1) r = 1; }
void t6(void){ r = (bit)x; }
void t7(void){ r = (bit)u; }
void t8(void){ b1 = (bit)(x & 2); }
void t9(void){ r = ~b1 & 1; }
void t10(void){ r = (unsigned char)(~b1) << 5; }
void t11(void){ if (c == x) r = 1; }
void t12(void){ b1 = b2 | x; }
