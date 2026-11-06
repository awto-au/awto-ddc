/* Replaces SDCC mcs51 __memcpy at --sdcccall 3 (Keil registers, awto-sdcc docs/keil-abi.md; generic-pointer loop of the library
 * needs 6 B OSEG, #24). Byte access via __gptrget/__gptrput (they keep R0 and B). State in R0-R7; dst (return value) on the stack.
 * dst = R1 (lsb), R2, R3 (tag); src (generic) in ___memcpy_PARM_2 and n in ___memcpy_PARM_3 (XDATA, LE or BE layout); returns dst in R1-R3. */

#ifdef __SDCC_BIG_ENDIAN
#define P2_LO 2                 /* generic pointer in memory: tag, msb, lsb */
#define P2_HI 1
#define P2_TAG 0
#define P3_LO 1                 /* n: msb, lsb */
#define P3_HI 0
#else
#define P2_LO 0                 /* lsb, msb, tag */
#define P2_HI 1
#define P2_TAG 2
#define P3_LO 0
#define P3_HI 1
#endif

void *__memcpy(void *dst, const void *src, unsigned int n) __naked
{
    (void)dst; (void)src; (void)n;
    __asm
        mov     a,r1                    ; dst0 on the stack, working copy: R5 lo, R4 hi, R3 tag
        push    acc
        mov     r5,a
        mov     a,r2
        push    acc
        mov     r4,a
        mov     a,r3
        push    acc
        mov     dptr,#(___memcpy_PARM_2 + P2_LO)
        movx    a,@dptr
        mov     r0,a                    ; src: R0 lo, R1 hi, R2 tag
        mov     dptr,#(___memcpy_PARM_2 + P2_HI)
        movx    a,@dptr
        mov     r1,a
        mov     dptr,#(___memcpy_PARM_2 + P2_TAG)
        movx    a,@dptr
        mov     r2,a
        mov     dptr,#(___memcpy_PARM_3 + P3_LO)
        movx    a,@dptr
        mov     r6,a                    ; n: R6 lo, R7 hi
        mov     dptr,#(___memcpy_PARM_3 + P3_HI)
        movx    a,@dptr
        mov     r7,a
1$:
        mov     a,r6
        orl     a,r7
        jz      4$
        mov     dpl,r0
        mov     dph,r1
        mov     b,r2
        lcall   __gptrget               ; A = *src
        mov     dpl,r5
        mov     dph,r4
        mov     b,r3
        lcall   __gptrput               ; *dst = A
        inc     r0
        cjne    r0,#0,2$
        inc     r1
2$:
        inc     r5
        cjne    r5,#0,3$
        inc     r4
3$:
        mov     a,r6
        jnz     5$
        dec     r7
5$:
        dec     r6
        sjmp    1$
4$:
        pop     acc
        mov     r3,a
        pop     acc
        mov     r2,a
        pop     acc
        mov     r1,a
        ret
    __endasm;
}
