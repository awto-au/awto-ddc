/* Replaces SDCC mcs51 _modulong/_moduint: the library versions never return when the divisor is 0
 * (SDK hits x % 0 after a failed eDP link: link rate/lanes = 0). Here x % 0 = x; else restoring shift-subtract. (#8)
 * Hand asm in R0-R7/B/F0 only: the C version needed 9 B of direct-RAM temporaries (OSEG, #24).
 * ABI: a in DPL,DPH[,B,ACC]; b in <fn>_PARM_2 (XDATA, LE or BE); result in the same regs. r = R0.., a = R4.. */

#if defined(__SDCCCALL) && (__SDCCCALL >= 1)
/* Register ABI (--sdcccall >= 1, awto-sdcc#7): x in DPL,DPH,B,A (lsb first), y in R4..R7 (32 bit; R4 lsb) or R6 (lo) / R7 (hi) (16 bit).
 * x % 0 = x. Paths: both < 256 -> DIV AB; y < 2^16 -> 2-byte remainder (16 or 32 iterations); y >= 2^16 -> quotient < 2^16, 16 iterations
 * with a 4-byte remainder seeded from x >> 16. x < y exits early; y stays in registers, no XDATA access. R0-R7, B, F0 only. */

unsigned long _modulong(unsigned long a, unsigned long b) __naked
{
    (void)a; (void)b;
    __asm
        mov     r0,a                    ; x3
        mov     a,r6
        orl     a,r7
        jnz     6$                      ; y >= 2^16
        mov     a,r4
        orl     a,r5
        jnz     1$
        mov     a,r0                    ; y == 0 -> x
        ret
1$:     mov     a,b                     ; y < 2^16
        orl     a,r0
        jnz     4$                      ; x >= 2^16
        mov     a,r5
        orl     a,dph
        jz      3$                      ; both < 256
        clr     c                       ; 16 / 16
        mov     a,dpl
        subb    a,r4
        mov     a,dph
        subb    a,r5
        jc      9$                      ; x < y -> x (b = 0, a = r0 = 0)
        clr     a
        mov     r6,a
        mov     r7,a
        mov     b,#16
2$:     clr     c
        mov     a,dpl
        rlc     a
        mov     dpl,a
        mov     a,dph
        rlc     a
        mov     dph,a
        mov     a,r6
        rlc     a
        mov     r6,a
        mov     a,r7
        rlc     a
        mov     r7,a
        mov     0xD5,c
        mov     a,r6
        clr     c
        subb    a,r4
        mov     r2,a
        mov     a,r7
        subb    a,r5
        jnc     21$
        jnb     0xD5,22$
21$:    mov     r7,a
        mov     ar6,r2
22$:    djnz    b,2$
        mov     dpl,r6
        mov     dph,r7
        clr     a
        mov     b,a
        ret
3$:     mov     a,dpl                   ; 8 / 8
        mov     b,r4
        div     ab
        mov     dpl,b
        clr     a
        mov     b,a
        ret
9$:     mov     a,r0
        ret
4$:     clr     a                       ; 32 / 16: x = DPL,DPH,B,R0; remainder R6,R7; counter R1
        mov     r6,a
        mov     r7,a
        mov     r1,#32
5$:     clr     c
        mov     a,dpl
        rlc     a
        mov     dpl,a
        mov     a,dph
        rlc     a
        mov     dph,a
        mov     a,b
        rlc     a
        mov     b,a
        mov     a,r0
        rlc     a
        mov     r0,a
        mov     a,r6
        rlc     a
        mov     r6,a
        mov     a,r7
        rlc     a
        mov     r7,a
        mov     0xD5,c
        mov     a,r6
        clr     c
        subb    a,r4
        mov     r2,a
        mov     a,r7
        subb    a,r5
        jnc     51$
        jnb     0xD5,52$
51$:    mov     r7,a
        mov     ar6,r2
52$:    djnz    r1,5$
        mov     dpl,r6
        mov     dph,r7
        clr     a
        mov     b,a
        ret
6$:     mov     a,r0                    ; y >= 2^16: remainder R0..R3 = x >> 16, x low half in DPL,DPH
        xch     a,b
        mov     r0,a                    ; r0 = x2
        mov     r1,b                    ; r1 = x3
        clr     a
        mov     r2,a
        mov     r3,a
        clr     c
        mov     a,dpl
        subb    a,r4
        mov     a,dph
        subb    a,r5
        mov     a,r0
        subb    a,r6
        mov     a,r1
        subb    a,r7
        jnc     7$
        mov     b,r0                    ; x < y -> x
        mov     a,r1
        ret
7$:     mov     b,#16
8$:     clr     c
        mov     a,dpl
        rlc     a
        mov     dpl,a
        mov     a,dph
        rlc     a
        mov     dph,a
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
        mov     0xD5,c
        clr     c
        mov     a,r0
        subb    a,r4
        mov     r0,a
        mov     a,r1
        subb    a,r5
        mov     r1,a
        mov     a,r2
        subb    a,r6
        mov     r2,a
        mov     a,r3
        subb    a,r7
        mov     r3,a
        jnc     81$
        jb      0xD5,81$
        clr     c                       ; restore
        mov     a,r0
        add     a,r4
        mov     r0,a
        mov     a,r1
        addc    a,r5
        mov     r1,a
        mov     a,r2
        addc    a,r6
        mov     r2,a
        mov     a,r3
        addc    a,r7
        mov     r3,a
81$:    djnz    b,8$
        mov     dpl,r0
        mov     dph,r1
        mov     b,r2
        mov     a,r3
        ret
    __endasm;
}

unsigned int _moduint(unsigned int a, unsigned int b) __naked
{
    (void)a; (void)b;
    __asm
        mov     a,r6
        orl     a,r7
        jz      9$                      ; y == 0 -> x
        mov     a,dph
        orl     a,r7
        jnz     1$
        mov     a,dpl                   ; both < 256
        mov     b,r6
        div     ab
        mov     dpl,b
        ret
1$:     clr     c
        mov     a,dpl
        subb    a,r6
        mov     a,dph
        subb    a,r7
        jc      9$                      ; x < y -> x
        clr     a
        mov     r0,a
        mov     r1,a
        mov     b,#16
2$:     clr     c
        mov     a,dpl
        rlc     a
        mov     dpl,a
        mov     a,dph
        rlc     a
        mov     dph,a
        mov     a,r0
        rlc     a
        mov     r0,a
        mov     a,r1
        rlc     a
        mov     r1,a
        mov     0xD5,c
        mov     a,r0
        clr     c
        subb    a,r6
        mov     r2,a
        mov     a,r1
        subb    a,r7
        jnc     21$
        jnb     0xD5,22$
21$:    mov     r1,a
        mov     ar0,r2
22$:    djnz    b,2$
        mov     dpl,r0
        mov     dph,r1
9$:     ret
    __endasm;
}

#else /* ABI 0 */

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

#endif
