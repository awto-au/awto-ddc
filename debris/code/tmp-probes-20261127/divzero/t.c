volatile unsigned long a = 0x12345678UL, z = 0, r1, r2;
volatile unsigned int ai = 0x1234, zi = 0, r3, r4;
volatile unsigned char stage;
void main(void)
{
    stage = 1;
    r3 = ai / zi;
    stage = 2;
    r4 = ai % zi;
    stage = 3;
    while (1) ;
}
