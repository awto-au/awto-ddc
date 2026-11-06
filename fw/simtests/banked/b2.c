#include "bk.h"
WORD g2(WORD a, WORD b) { return a * 5 + b; }
WORD g3(WORD a, WORD b, WORD c) { return a * 11 + b * 13 + c * 17; }
WORD back(WORD a, WORD b, WORD c) { return f3(c, b, a) + f2(a, c); }
