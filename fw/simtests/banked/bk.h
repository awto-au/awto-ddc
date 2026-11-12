/* banked-call test (scripts/bank_test.py): modules land in different banks; every call below main crosses banks */
typedef unsigned char BYTE;
typedef unsigned int WORD;
typedef unsigned long DWORD;

WORD f2(WORD a, WORD b);                    /* b1 */
WORD f3(WORD a, WORD b, WORD c);
BYTE fb(BYTE a, BYTE b, BYTE c);
DWORD fl(DWORD a, WORD b);
__bit fbit(WORD a, WORD b);
WORD chain1(WORD a, WORD b, WORD c);        /* b1 -> b2 -> b1 */

WORD g2(WORD a, WORD b);                    /* b2 */
WORD g3(WORD a, WORD b, WORD c);
WORD back(WORD a, WORD b, WORD c);          /* calls b1 */

/* Keil-ABI cases (args in R1-R7, returns in R1-R7/C must survive the stubs) */
WORD gsum(const BYTE *p, WORD n);                    /* b1: generic ptr R1-R3 + int R4:R5 */
BYTE gpick(BYTE a, WORD b, const BYTE *p);           /* b1: R7, R4:R5, R1-R3 */
BYTE gp2(BYTE a, const BYTE *p, BYTE c);             /* b1: R7, R1-R3, c in memory (R3 taken) */
DWORD lmix(DWORD a, BYTE b, BYTE c);                /* b1: long R4-R7, rest memory */
DWORD lsum3(WORD a, WORD b, WORD c);                /* b2: int x3 -> long return */
const BYTE *gret(BYTE which);                       /* b2: generic pointer return R1-R3 */
BYTE __xdata *xret(void);                           /* b2: 2 B pointer return */
BYTE __data *dret(void);                            /* b2: 1 B pointer return */
float fret(WORD n);                                 /* b2: float return R4-R7 */
float fmul(float a, WORD n);                        /* b1: float arg 1 */
char cret(char a);                                  /* b2 */
signed char scr(signed char a, signed char b);      /* b1 */
void vset(BYTE v);                                  /* b2: void */
BYTE vget(void);                                    /* b2 */
WORD gnest(const BYTE *p, WORD n, BYTE k);          /* b2 -> b1 gsum with a different generic ptr */
