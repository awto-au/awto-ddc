/* Replaces SDCC mcs51 __memcpy (generic-pointer loop, 6 B OSEG, #24). Byte access via __gptrget/__gptrput (they keep R0
 * and B). State in R0-R7; dst0 (3 B return value) is spilled to the stack, as no register is left for it.
 * ABI: dst in DPL,DPH,B; src in ___memcpy_PARM_2 (generic, XDATA); n in ___memcpy_PARM_3 (XDATA, LE); returns dst. */

void *__memcpy(void *dst, const void *src, unsigned int n) __naked
{
    (void)dst; (void)src; (void)n;
    __asm
        push    dpl                     ; dst0
        push    dph
        push    b
        mov     r3,dpl                  ; dst: R3,R4 addr, R5 type
        mov     r4,dph
        mov     r5,b
        mov     dptr,#___memcpy_PARM_2
        movx    a,@dptr
        mov     r0,a                    ; src: R0,R1 addr, R2 type
        inc     dptr
        movx    a,@dptr
        mov     r1,a
        inc     dptr
        movx    a,@dptr
        mov     r2,a
        inc     dptr
        movx    a,@dptr
        mov     r6,a                    ; n: R6 lo, R7 hi
        inc     dptr
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
        mov     dpl,r3
        mov     dph,r4
        mov     b,r5
        lcall   __gptrput               ; *dst = A
        inc     r0
        cjne    r0,#0,2$
        inc     r1
2$:
        inc     r3
        cjne    r3,#0,3$
        inc     r4
3$:
        mov     a,r6
        jnz     5$
        dec     r7
5$:
        dec     r6
        sjmp    1$
4$:
        pop     b
        pop     dph
        pop     dpl
        ret
    __endasm;
}
