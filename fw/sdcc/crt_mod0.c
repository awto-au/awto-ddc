/* Replaces SDCC mcs51 _modulong/_moduint at --sdcccall 3 (Keil registers, awto-sdcc docs/keil-abi.md): x % 0 = x (SDK hits it
 * after a failed eDP link: link rate/lanes = 0). Hand asm in R0-R7/B/DPL/F0 only: no direct-RAM temporaries (#24).
 * _moduint: x = R6:R7, y = R4:R5 -> R6:R7. _modulong: x = R4..R7, y in <fn>_PARM_2 (XDATA, LE or BE) -> R4..R7.
 * 16 bit: DIV AB for y < 256, x < y early-out, 8 steps (quotient < 256) otherwise. 32 bit: y < 65536 in R0:R1 with
 * 16 steps (x < 65536) or 32, y >= 65536 16 steps with y read from XDATA. Same code as awto-sdcc device/lib/_moduint.c, _modulong.c. */

/* PARM_2 bytes are read LSB first. LE: LSB at the lowest address. --big-endian: MSB lowest (reload dptr). */
#define HASH #                  /* a bare # in a function-like macro body is stringify */
#ifdef __SDCC_BIG_ENDIAN
#define PARM_LO(s, n)      mov dptr,HASH(s + n - 1)
#define PARM_NEXT(s, n, k) mov dptr,HASH(s + n - 1 - k)
#else
#define PARM_LO(s, n)      mov dptr,HASH(s)
#define PARM_NEXT(s, n, k) inc dptr
#endif

unsigned int _moduint(unsigned int x, unsigned int y) __naked
{
    (void)x; (void)y;
    __asm
	mov	a,r4
	jnz	5$		; y >= 256
	mov	a,r5
	jz	9$		; y == 0
	mov	b,r5
	mov	a,r6
	jnz	2$		; x >= 256
	mov	a,r7
	div	ab		; both 8 bit
	mov	r7,b
	ret
2$:	div	ab		; a = xh / y, b = rest
	mov	r6,a
	mov	r3,b
	mov	r2,#8
3$:	mov	a,r7		; rest = rest * 2 + next bit of xl
	add	a,acc
	mov	r7,a
	mov	a,r3
	rlc	a
	jc	4$		; 9 bit: >= y
	mov	r3,a
	subb	a,r5		; C = 0
	jc	6$
	mov	r3,a
	inc	r7
	sjmp	6$
4$:	clr	c
	subb	a,r5
	mov	r3,a
	inc	r7
6$:	djnz	r2,3$
	mov	a,r3
	mov	r7,a
	mov	r6,#0
	ret
5$:	clr	c		; y >= 256
	mov	a,r7
	subb	a,r5
	mov	a,r6
	subb	a,r4
	jnc	7$
	ret			; x < y: remainder x
7$:	mov	a,r6
	mov	r3,a		; rest = xh (< 256 <= y)
	mov	r2,#0
	mov	r0,#8
8$:	clr	c
	mov	a,r7
	rlc	a
	mov	r7,a		; xl <<= 1, C = next bit
	mov	a,r3
	rlc	a
	mov	r3,a
	mov	a,r2
	rlc	a
	mov	r2,a
	jc	10$		; 17 bit: >= y
	mov	a,r3
	subb	a,r5		; C = 0
	mov	b,a
	mov	a,r2
	subb	a,r4
	jc	11$
	mov	r2,a
	mov	r3,b
	inc	r7
	sjmp	11$
10$:	clr	c
	mov	a,r3
	subb	a,r5
	mov	r3,a
	mov	a,r2
	subb	a,r4
	mov	r2,a
	inc	r7
11$:	djnz	r0,8$
	mov	a,r2
	mov	r6,a
	mov	a,r3
	mov	r7,a
	ret
9$:	ret			; y == 0: remainder x
	    __endasm;
}

unsigned long _modulong(unsigned long x, unsigned long y) __naked
{
    (void)x; (void)y;
    __asm
	PARM_LO(__modulong_PARM_2,4)
	movx	a,@dptr
	mov	r1,a		; y0
	PARM_NEXT(__modulong_PARM_2,4,1)
	movx	a,@dptr
	mov	r0,a		; y1
	PARM_NEXT(__modulong_PARM_2,4,2)
	movx	a,@dptr
	mov	r2,a		; y2
	PARM_NEXT(__modulong_PARM_2,4,3)
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
	mov	a,r3
	mov	r7,a
	mov	a,r2
	mov	r6,a
	clr	a
	mov	r5,a
	mov	r4,a
	ret
9$:
	ret			; y == 0: remainder x
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
	PARM_LO(__modulong_PARM_2,4)
	clr	c		; rest -= y
	movx	a,@dptr
	xch	a,r3
	subb	a,r3
	mov	r3,a
	PARM_NEXT(__modulong_PARM_2,4,1)
	movx	a,@dptr
	xch	a,r2
	subb	a,r2
	mov	r2,a
	PARM_NEXT(__modulong_PARM_2,4,2)
	movx	a,@dptr
	xch	a,r1
	subb	a,r1
	mov	r1,a
	PARM_NEXT(__modulong_PARM_2,4,3)
	movx	a,@dptr
	xch	a,r0
	subb	a,r0
	mov	r0,a
	jnc	23$		; rest >= y: keep
	jb	F0,23$		; carry out of the shift: keep
	PARM_LO(__modulong_PARM_2,4)		; undo
	movx	a,@dptr
	add	a,r3
	mov	r3,a
	PARM_NEXT(__modulong_PARM_2,4,1)
	movx	a,@dptr
	addc	a,r2
	mov	r2,a
	PARM_NEXT(__modulong_PARM_2,4,2)
	movx	a,@dptr
	addc	a,r1
	mov	r1,a
	PARM_NEXT(__modulong_PARM_2,4,3)
	movx	a,@dptr
	addc	a,r0
	mov	r0,a
	sjmp	24$
23$:	inc	r7
24$:	djnz	b,25$
	sjmp	26$
25$:	ljmp	21$
26$:
	mov	a,r3
	mov	r7,a
	mov	a,r2
	mov	r6,a
	mov	a,r1
	mov	r5,a
	mov	a,r0
	mov	r4,a
	ret
	    __endasm;
}
