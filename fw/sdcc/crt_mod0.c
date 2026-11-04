/* Replaces SDCC mcs51 _modulong/_moduint: the library versions never return when the divisor is 0
 * (SDK hits x % 0 after a failed eDP link: link rate/lanes = 0). Here x % 0 = x; else restoring shift-subtract. (#8) */

unsigned long _modulong(unsigned long a, unsigned long b)
{
    unsigned long r = 0;
    unsigned char i, c;

    if (b == 0)
        return a;
    for (i = 32; i; i--) {
        c = (r & 0x80000000UL) != 0;        /* bit shifted out: true remainder >= 2^32 > b */
        r = (r << 1) | (a >> 31);
        a <<= 1;
        if (c || r >= b)
            r -= b;
    }
    return r;
}

unsigned int _moduint(unsigned int a, unsigned int b)
{
    unsigned int r = 0;
    unsigned char i, c;

    if (b == 0)
        return a;
    for (i = 16; i; i--) {
        c = (r & 0x8000U) != 0;
        r = (r << 1) | (a >> 15);
        a <<= 1;
        if (c || r >= b)
            r -= b;
    }
    return r;
}
