bit b1, b2;
unsigned char x, y, r;
char c;
int i;
unsigned int u;
enum E1 { A0, A1, A200 = 200 };
enum E2 { B0, B1, B300 = 300 };
enum E3 { C0, C1, C128 = 128 };
enum E1 e1; enum E2 e2; enum E3 e3;
struct S { unsigned char a:1; unsigned char b:3; unsigned char d:4; } s;
void t_notbit(void)   { r = ~b1; }
void t_notbit2(void)  { b2 = ~b1; }
void t_bitfromint(void){ b1 = x; }
void t_bitfromint2(void){ b1 = i; }
void t_bitarith(void) { r = b1 & b2; }
void t_charneg(void)  { if (c == 0xff) r = 1; }
void t_ucharneg(void) { if (x == -1) r = 1; }
void t_uchar_not(void){ if (~x == 0xFF) r = 1; }
void t_sshr(void)     { i = i >> 3; }
void t_cshr(void)     { c = c >> 1; }
void t_mul(void)      { u = x * y; }
void t_add8(void)     { r = (x + y) >> 1; }
void t_enum(void)     { e1 = A200; e2 = B300; e3 = C128; }
void t_bf(void)       { s.a = 1; s.d = 5; }
void t_div0(void)     { u = u / y; r = x % y; }
void t_sdiv(void)     { i = i / 3; i = i % 3; }
void t_neg_u(void)    { u = -x; }
void t_shl(void)      { u = x << 8; }
void t_bitret(bit a) { b1 = a; }
