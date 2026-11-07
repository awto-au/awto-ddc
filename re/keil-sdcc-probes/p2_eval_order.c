unsigned char g(void); unsigned char h(void); void f(unsigned char a, unsigned char b);
unsigned char r;
void t_order(void) { f(g(), h()); }
void t_order2(void){ r = g() + h(); }
void t_post(void) { unsigned char i = 1; r = i++ + i; }
