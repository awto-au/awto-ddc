unsigned char x, y, r;
char c;
unsigned int u; int i;
unsigned long l;
bit b1;
void t1(void){ if (x > -1) r = 1; }
void t2(void){ if (x != -1) r = 2; }
void t3(void){ if (x == 0x100) r = 3; }
void t4(void){ if (c > 200) r = 4; }
void t5(void){ r = x << 8; }
void t6(void){ u = u << 16; }
void t7(void){ l = x << 24; }
void t8(void){ l = u << 8; }
void t9(void){ r = (x + y) > 255; }
void t10(void){ b1 = x & 0x80; }
void t11(void){ b1 = !x; }
void t12(void){ b1 = x == y; }
void t13(void){ if (b1 == 1) r = 1; }
void t15(void){ r = b1 ? 5 : 6; }
void t16(void){ l = (long)-x; }
void t17(void){ r = -1 > x; }
void t18(void){ l = u * u; }
void t19(void){ u = x - y; }
void t20(void){ if (x - y < 0) r = 1; }
void t21(void){ r = (x == 0xFFFF); }
void t22(void){ b1 = ~x; }
void t23(void){ b1 = c; }
