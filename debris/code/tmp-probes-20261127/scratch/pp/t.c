#pragma place group(font)
static const unsigned char __code blob[4] = {1, 2, 3, 4};

volatile __xdata unsigned char sink;

#pragma place group(font)
static void f(const unsigned char __code *b, unsigned char n)
{
    unsigned char i, t = 0;
    for (i = 0; i < n; i++)
        t += b[i];
    sink = t;
}

void g(void) { f(blob, 4); }
