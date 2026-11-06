/* Replaces SDCC mcs51 _divulong at --sdcccall 3 (Keil registers, awto-sdcc docs/keil-abi.md): x / 0 = 0xFFFFFFFF (like the
 * library), hand asm in R0-R7/B/DPL/F0 only: no direct-RAM temporaries, also none in the ISR clone (sdcc_isr_libs.py, #24).
 * x = R4..R7 (R4 msb), y in __divulong_PARM_2 (XDATA, LE or BE) -> quotient R4..R7. y < 65536 in R0:R1 with 16 steps
 * (x < 65536) or 32, y >= 65536 16 steps with y read from XDATA. Same code as awto-sdcc device/lib/_divulong.c. */

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
	PARM_LO(__divulong_PARM_2,4)
	movx	a,@dptr
	mov	r1,a		; y0
	PARM_NEXT(__divulong_PARM_2,4,1)
	movx	a,@dptr
	mov	r0,a		; y1
	PARM_NEXT(__divulong_PARM_2,4,2)
	movx	a,@dptr
	mov	r2,a		; y2
	PARM_NEXT(__divulong_PARM_2,4,3)
	movx	a,@dptr
	orl	a,r2		; y3 | y2
	jz	19$
	ljmp	20$		; y >= 65536
19$:
	mov	a,r0
	orl	a,r1
	jz	9$		; y == 0
	clr	a
	mov	r2,a		; rest = 0
	mov	r3,a
	mov	dpl,#32
	mov	a,r4
	orl	a,r5
	jnz	1$
	mov	a,r6		; x < 65536: the 16 bit shift register starts at the top
	mov	r4,a
	mov	a,r7
	mov	r5,a
	clr	a
	mov	r6,a
	mov	r7,a
	mov	dpl,#16
1$:	clr	c
	mov	a,r7
	rlc	a
	mov	r7,a
	mov	a,r6
	rlc	a
	mov	r6,a
	mov	a,r5
	rlc	a
	mov	r5,a
	mov	a,r4
	rlc	a
	mov	r4,a
	mov	a,r3
	rlc	a
	mov	r3,a
	mov	a,r2
	rlc	a
	mov	r2,a
	jc	3$		; 17 bit rest: >= y
	mov	a,r3
	subb	a,r1		; C = 0
	mov	b,a
	mov	a,r2
	subb	a,r0
	jc	4$
	mov	r2,a
	mov	r3,b
	inc	r7
	sjmp	4$
3$:	clr	c
	mov	a,r3
	subb	a,r1
	mov	r3,a
	mov	a,r2
	subb	a,r0
	mov	r2,a
	inc	r7
4$:	djnz	dpl,1$
	ret
9$:
	mov	a,#0xFF
	mov	r4,a
	mov	r5,a
	mov	r6,a
	mov	r7,a
	ret
20$:	mov	a,r4		; y >= 65536: rest = xh, shift register = xl
	mov	r2,a
	mov	a,r5
	mov	r3,a
	clr	a
	mov	r4,a
	mov	r5,a
	mov	r0,a
	mov	r1,a
	mov	b,#16
21$:	clr	c
	mov	a,r7
	rlc	a
	mov	r7,a
	mov	a,r6
	rlc	a
	mov	r6,a
	mov	a,r3
	rlc	a
	mov	r3,a
	mov	a,r2
	rlc	a
	mov	r2,a
	mov	a,r1
	rlc	a
	mov	r1,a
	mov	a,r0
	rlc	a
	mov	r0,a
	mov	F0,c		; carry out of the shift
	PARM_LO(__divulong_PARM_2,4)
	clr	c		; rest -= y
	movx	a,@dptr
	xch	a,r3
	subb	a,r3
	mov	r3,a
	PARM_NEXT(__divulong_PARM_2,4,1)
	movx	a,@dptr
	xch	a,r2
	subb	a,r2
	mov	r2,a
	PARM_NEXT(__divulong_PARM_2,4,2)
	movx	a,@dptr
	xch	a,r1
	subb	a,r1
	mov	r1,a
	PARM_NEXT(__divulong_PARM_2,4,3)
	movx	a,@dptr
	xch	a,r0
	subb	a,r0
	mov	r0,a
	jnc	23$		; rest >= y: keep
	jb	F0,23$		; carry out of the shift: keep
	PARM_LO(__divulong_PARM_2,4)		; undo
	movx	a,@dptr
	add	a,r3
	mov	r3,a
	PARM_NEXT(__divulong_PARM_2,4,1)
	movx	a,@dptr
	addc	a,r2
	mov	r2,a
	PARM_NEXT(__divulong_PARM_2,4,2)
	movx	a,@dptr
	addc	a,r1
	mov	r1,a
	PARM_NEXT(__divulong_PARM_2,4,3)
	movx	a,@dptr
	addc	a,r0
	mov	r0,a
	sjmp	24$
23$:	inc	r7
24$:	djnz	b,25$
	sjmp	26$
25$:	ljmp	21$
26$:
	ret
	    __endasm;
}
