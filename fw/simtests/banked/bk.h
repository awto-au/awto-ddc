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
