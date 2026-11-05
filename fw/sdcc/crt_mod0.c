/* Replaces SDCC mcs51 _modulong/_moduint: the library versions never return when the divisor is 0
 * (SDK hits x % 0 after a failed eDP link: link rate/lanes = 0). Here x % 0 = x; else restoring shift-subtract. (#8)
 * Hand asm in R0-R7/B/F0 only: the C version needed 9 B of direct-RAM temporaries (OSEG, #24).
 * ABI: a in DPL,DPH[,B,ACC]; b in <fn>_PARM_2 (XDATA, LE or BE); result in the same regs. r = R0.., a = R4.. */

/* PARM_2 bytes are read LSB first. LE: LSB at the lowest address. --big-endian: MSB lowest (reload dptr). */
#define HASH #                  /* a bare # in a function-like macro body is stringify */
#ifdef __SDCC_BIG_ENDIAN
#define PARM_LO(s, n)      mov dptr,HASH(s + n - 1)
#define PARM_NEXT(s, n, k) mov dptr,HASH(s + n - 1 - k)
#else
#define PARM_LO(s, n)      mov dptr,HASH(s)
#define PARM_NEXT(s, n, k) inc dptr
#endif

unsigned long _modulong(unsigned long a, unsigned long b) __naked
{
    (void)a; (void)b;
    __asm
        mov     r4,dpl
        mov     r5,dph
        mov     r6,b
        mov     r7,a
        PARM_LO(__modulong_PARM_2,4)
        movx    a,@dptr
        mov     r0,a
        PARM_NEXT(__modulong_PARM_2,4,1)
        movx    a,@dptr
        orl     a,r0
        mov     r0,a
        PARM_NEXT(__modulong_PARM_2,4,2)
        movx    a,@dptr
        orl     a,r0
        mov     r0,a
        PARM_NEXT(__modulong_PARM_2,4,3)
        movx    a,@dptr
        orl     a,r0
        jnz     1$
        sjmp    4$                  ; b == 0 -> return a (r4..r7)
1$:
        clr     a
        mov     r0,a
        mov     r1,a
        mov     r2,a
        mov     r3,a
        mov     b,#32
2$:
        clr     c                       ; (r:a) <<= 1; carry out of r = old r bit 31
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
        mov     0xD5,c                  ; F0 = carry out
        PARM_LO(__modulong_PARM_2,4)
        clr     c                       ; r -= b
        movx    a,@dptr
        xch     a,r0
        subb    a,r0
        mov     r0,a
        PARM_NEXT(__modulong_PARM_2,4,1)
        movx    a,@dptr
        xch     a,r1
        subb    a,r1
        mov     r1,a
        PARM_NEXT(__modulong_PARM_2,4,2)
        movx    a,@dptr
        xch     a,r2
        subb    a,r2
        mov     r2,a
        PARM_NEXT(__modulong_PARM_2,4,3)
        movx    a,@dptr
        xch     a,r3
        subb    a,r3
        mov     r3,a
        jnc     3$                  ; r >= b: keep
        jb      0xD5,3$             ; carry out: keep (true r >= 2^32 > b)
        PARM_LO(__modulong_PARM_2,4) ; undo
        movx    a,@dptr
        add     a,r0
        mov     r0,a
        PARM_NEXT(__modulong_PARM_2,4,1)
        movx    a,@dptr
        addc    a,r1
        mov     r1,a
        PARM_NEXT(__modulong_PARM_2,4,2)
        movx    a,@dptr
        addc    a,r2
        mov     r2,a
        PARM_NEXT(__modulong_PARM_2,4,3)
        movx    a,@dptr
        addc    a,r3
        mov     r3,a
3$:
        djnz    b,2$
        mov     dpl,r0
        mov     dph,r1
        mov     b,r2
        mov     a,r3
        ret
4$:
        mov     dpl,r4
        mov     dph,r5
        mov     b,r6
        mov     a,r7
        ret
    __endasm;
}

unsigned int _moduint(unsigned int a, unsigned int b) __naked
{
    (void)a; (void)b;
    __asm
        mov     r4,dpl
        mov     r5,dph
        PARM_LO(__moduint_PARM_2,2)
        movx    a,@dptr
        mov     r0,a
        PARM_NEXT(__moduint_PARM_2,2,1)
        movx    a,@dptr
        orl     a,r0
        jnz     1$
        mov     dpl,r4                  ; b == 0 -> return a
        mov     dph,r5
        ret
1$:
        clr     a
        mov     r0,a
        mov     r1,a
        mov     b,#16
2$:
        clr     c
        mov     a,r4
        rlc     a
        mov     r4,a
        mov     a,r5
        rlc     a
        mov     r5,a
        mov     a,r0
        rlc     a
        mov     r0,a
        mov     a,r1
        rlc     a
        mov     r1,a
        mov     0xD5,c
        PARM_LO(__moduint_PARM_2,2)
        clr     c
        movx    a,@dptr
        xch     a,r0
        subb    a,r0
        mov     r0,a
        PARM_NEXT(__moduint_PARM_2,2,1)
        movx    a,@dptr
        xch     a,r1
        subb    a,r1
        mov     r1,a
        jnc     3$
        jb      0xD5,3$
        PARM_LO(__moduint_PARM_2,2)
        movx    a,@dptr
        add     a,r0
        mov     r0,a
        PARM_NEXT(__moduint_PARM_2,2,1)
        movx    a,@dptr
        addc    a,r1
        mov     r1,a
3$:
        djnz    b,2$
        mov     dpl,r0
        mov     dph,r1
        ret
    __endasm;
}
