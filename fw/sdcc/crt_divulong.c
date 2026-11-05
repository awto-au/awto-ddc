/* Replaces SDCC mcs51 _divulong: same restoring shift-subtract (x / 0 = 0xFFFFFFFF, reste kept 32 bit like the
 * library), hand asm in R0-R7/B only. The compiled C needed a 4 B direct-RAM temporary, and the ISR clone
 * (sdcc_isr_libs.py) a second copy of it (#24). ABI: x in DPL,DPH,B,ACC; y in __divulong_PARM_2 (XDATA, LE or BE).
 * x = R4..R7, reste = R0..R3. */

/* PARM_2 bytes are read LSB first. LE: LSB at the lowest address. --big-endian: MSB lowest (reload dptr). */
#define HASH #                  /* a bare # in a function-like macro body is stringify */
#ifdef __SDCC_BIG_ENDIAN
#define PARM_LO(s, n)      mov dptr,HASH(s + n - 1)
#define PARM_NEXT(s, n, k) mov dptr,HASH(s + n - 1 - k)
#else
#define PARM_LO(s, n)      mov dptr,HASH(s)
#define PARM_NEXT(s, n, k) inc dptr
#endif

unsigned long _divulong(unsigned long x, unsigned long y) __naked
{
    (void)x; (void)y;
    __asm
        mov     r4,dpl
        mov     r5,dph
        mov     r6,b
        mov     r7,a
        clr     a
        mov     r0,a
        mov     r1,a
        mov     r2,a
        mov     r3,a
        mov     b,#32
1$:
        clr     c                       ; x <<= 1, msb -> reste
        mov     a,r4
        rlc     a
        mov     r4,a
        mov     a,r5
        rlc     a
        mov     r5,a
        mov     a,r6
        rlc     a
        mov     r6,a
        mov     a,r7
        rlc     a
        mov     r7,a
        mov     a,r0
        rlc     a
        mov     r0,a
        mov     a,r1
        rlc     a
        mov     r1,a
        mov     a,r2
        rlc     a
        mov     r2,a
        mov     a,r3
        rlc     a
        mov     r3,a
        PARM_LO(__divulong_PARM_2,4)
        clr     c                       ; reste -= y
        movx    a,@dptr
        xch     a,r0
        subb    a,r0
        mov     r0,a
        PARM_NEXT(__divulong_PARM_2,4,1)
        movx    a,@dptr
        xch     a,r1
        subb    a,r1
        mov     r1,a
        PARM_NEXT(__divulong_PARM_2,4,2)
        movx    a,@dptr
        xch     a,r2
        subb    a,r2
        mov     r2,a
        PARM_NEXT(__divulong_PARM_2,4,3)
        movx    a,@dptr
        xch     a,r3
        subb    a,r3
        mov     r3,a
        jnc     2$                      ; reste >= y: keep, quotient bit 1
        PARM_LO(__divulong_PARM_2,4) ; undo
        movx    a,@dptr
        add     a,r0
        mov     r0,a
        PARM_NEXT(__divulong_PARM_2,4,1)
        movx    a,@dptr
        addc    a,r1
        mov     r1,a
        PARM_NEXT(__divulong_PARM_2,4,2)
        movx    a,@dptr
        addc    a,r2
        mov     r2,a
        PARM_NEXT(__divulong_PARM_2,4,3)
        movx    a,@dptr
        addc    a,r3
        mov     r3,a
        sjmp    3$
2$:
        inc     r4                      ; lsb is 0 after the shift
3$:
        djnz    b,1$
        mov     dpl,r4
        mov     dph,r5
        mov     b,r6
        mov     a,r7
        ret
    __endasm;
}
