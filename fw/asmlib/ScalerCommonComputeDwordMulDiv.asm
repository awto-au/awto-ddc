; Hand-written 8051 replacement for Realtek ScalerCommonComputeDwordMulDiv.c, SDCC mcs51 large --big-endian, #11.
; DWORD ScalerComputeDwordMulDiv(DWORD A /*DPL,DPH,B,ACC*/, DWORD B /*PARM_2*/, DWORD C /*PARM_3*/)
; DWORD ScalerComputeDwordPowDiv(DWORD A, BYTE pow /*PARM_2*/, DWORD B /*PARM_3*/)
; PARMs are BE (+0 = MSB). Internal scratch is lsb-first. Same results as the C, incl. its 32-bit wraps:
;  MulDiv: if A==0 || B==0 || A < 0xFFFFFFFF/B -> (A*B)/C  else PowDiv(P>>32,32,C) + PowDiv(P&0xFFFFFFFF,0,C), P = 64-bit A*B.
;  PowDiv: pow+1 rounds of {res<<=1; if A>=B {res+=A/B; A%=B}; A<<=1}; return A>=B ? res+1 : res.
;  Rounds after the first see A < 2B (before the 32-bit shift wrap) so A/B is 0 or 1: compare-subtract, no divide.
;  Divisor 0: x/0 = 0xFFFFFFFF, x%0 = x (project lib semantics); PowDiv(,,0) takes a closed-form loop.
; Non-reentrant (static scratch), like the C. Core divmod after fw/sdcc/crt_mod0.c (R0-R7/B/F0 only).
	.module ScalerCommonComputeDwordMulDiv
	.optsdcc -mmcs51 --model-large --big-endian
	.globl _ScalerComputeDwordPowDiv_PARM_2
	.globl _ScalerComputeDwordPowDiv_PARM_3
	.globl _ScalerComputeDwordPowDiv
	.globl _ScalerComputeDwordMulDiv_PARM_2
	.globl _ScalerComputeDwordMulDiv_PARM_3
	.globl _ScalerComputeDwordMulDiv
	.area XSEG    (XDATA)
_ScalerComputeDwordPowDiv_PARM_2:
	.ds 1
_ScalerComputeDwordPowDiv_PARM_3:
	.ds 4
_ScalerComputeDwordMulDiv_PARM_2:
	.ds 4
_ScalerComputeDwordMulDiv_PARM_3:
	.ds 4
__awto_md_A:
	.ds 4
__awto_md_B:
	.ds 4
__awto_md_P:
	.ds 8
__awto_md_D:
	.ds 4
__awto_md_R:
	.ds 4
__awto_md_pow:
	.ds 1
	.area XABS    (ABS,XDATA)
	.area XISEG   (XDATA)
	.area HOME    (CODE)
	.area GSINIT0 (CODE)
	.area GSINIT1 (CODE)
	.area GSINIT2 (CODE)
	.area GSINIT3 (CODE)
	.area GSINIT4 (CODE)
	.area GSINIT5 (CODE)
	.area GSINIT  (CODE)
	.area GSFINAL (CODE)
	.area CSEG    (CODE)
;	 function ScalerComputeDwordMulDiv
_ScalerComputeDwordMulDiv:
	mov	r4,dpl
	mov	r5,dph
	mov	r6,b
	mov	r7,a
	mov	dptr,#__awto_md_A
	lcall	__awto_st32le_r4
	mov	dptr,#_ScalerComputeDwordMulDiv_PARM_2
	lcall	__awto_ld32be
	mov	dptr,#__awto_md_B
	lcall	__awto_st32le
	lcall	__awto_mul64
	mov	dptr,#__awto_md_P	; P == 0 (A==0 || B==0) -> plain path
	mov	r2,#8
	clr	a
	mov	b,a
00101$:
	movx	a,@dptr
	orl	a,b
	mov	b,a
	inc	dptr
	djnz	r2,00101$
	mov	a,b
	jnz	00102$
	ljmp	00110$
00102$:
	mov	dptr,#__awto_md_B	; limit = 0xFFFFFFFF / B
	lcall	__awto_ld32le_r4
	mov	dptr,#__awto_md_D
	lcall	__awto_st32le_r4
	mov	r4,#0xFF
	mov	r5,#0xFF
	mov	r6,#0xFF
	mov	r7,#0xFF
	lcall	__awto_dm32
	mov	dptr,#__awto_md_A	; A < limit ?
	clr	c
	movx	a,@dptr
	subb	a,r4
	inc	dptr
	movx	a,@dptr
	subb	a,r5
	inc	dptr
	movx	a,@dptr
	subb	a,r6
	inc	dptr
	movx	a,@dptr
	subb	a,r7
	jnc	00103$
	ljmp	00110$
00103$:					; 64-bit path
	mov	dptr,#_ScalerComputeDwordMulDiv_PARM_3
	lcall	__awto_ld32be
	mov	dptr,#__awto_md_D
	lcall	__awto_st32le
	mov	dptr,#__awto_md_pow
	mov	a,#32
	movx	@dptr,a
	mov	dptr,#(__awto_md_P + 4)
	lcall	__awto_ld32le_r4
	lcall	__awto_pd_body
	mov	dptr,#__awto_md_R
	lcall	__awto_st32le_r4
	mov	dptr,#__awto_md_pow
	clr	a
	movx	@dptr,a
	mov	dptr,#__awto_md_P
	lcall	__awto_ld32le_r4
	lcall	__awto_pd_body
	mov	dptr,#__awto_md_R
	movx	a,@dptr
	add	a,r4
	mov	r4,a
	inc	dptr
	movx	a,@dptr
	addc	a,r5
	mov	r5,a
	inc	dptr
	movx	a,@dptr
	addc	a,r6
	mov	r6,a
	inc	dptr
	movx	a,@dptr
	addc	a,r7
	mov	r7,a
	sjmp	00111$
00110$:					; low32(A*B) / C
	mov	dptr,#_ScalerComputeDwordMulDiv_PARM_3
	lcall	__awto_ld32be
	mov	dptr,#__awto_md_D
	lcall	__awto_st32le
	mov	dptr,#__awto_md_P
	lcall	__awto_ld32le_r4
	lcall	__awto_dm32
00111$:
	mov	dpl,r4
	mov	dph,r5
	mov	b,r6
	mov	a,r7
	ret
;	 function ScalerComputeDwordPowDiv
_ScalerComputeDwordPowDiv:
	mov	r4,dpl
	mov	r5,dph
	mov	r6,b
	mov	r7,a
	mov	dptr,#_ScalerComputeDwordPowDiv_PARM_3
	lcall	__awto_ld32be
	mov	dptr,#__awto_md_D
	lcall	__awto_st32le
	mov	dptr,#_ScalerComputeDwordPowDiv_PARM_2
	movx	a,@dptr
	mov	dptr,#__awto_md_pow
	movx	@dptr,a
	lcall	__awto_pd_body
	mov	dpl,r4
	mov	dph,r5
	mov	b,r6
	mov	a,r7
	ret
;	 function _awto_ld32be
; (dptr) 4 bytes BE -> r0 (MSB) .. r3
__awto_ld32be:
	movx	a,@dptr
	mov	r0,a
	inc	dptr
	movx	a,@dptr
	mov	r1,a
	inc	dptr
	movx	a,@dptr
	mov	r2,a
	inc	dptr
	movx	a,@dptr
	mov	r3,a
	ret
;	 function _awto_st32le
; r3 (LSB) .. r0 -> (dptr) lsb first
__awto_st32le:
	mov	a,r3
	movx	@dptr,a
	inc	dptr
	mov	a,r2
	movx	@dptr,a
	inc	dptr
	mov	a,r1
	movx	@dptr,a
	inc	dptr
	mov	a,r0
	movx	@dptr,a
	ret
;	 function _awto_ld32le_r4
; (dptr) lsb first -> r4 (LSB) .. r7
__awto_ld32le_r4:
	movx	a,@dptr
	mov	r4,a
	inc	dptr
	movx	a,@dptr
	mov	r5,a
	inc	dptr
	movx	a,@dptr
	mov	r6,a
	inc	dptr
	movx	a,@dptr
	mov	r7,a
	ret
;	 function _awto_st32le_r4
; r4 (LSB) .. r7 -> (dptr) lsb first
__awto_st32le_r4:
	mov	a,r4
	movx	@dptr,a
	inc	dptr
	mov	a,r5
	movx	@dptr,a
	inc	dptr
	mov	a,r6
	movx	@dptr,a
	inc	dptr
	mov	a,r7
	movx	@dptr,a
	ret
;	 function _awto_dm32
; N = r4 (LSB) .. r7, D = __awto_md_D -> Q = r4..r7, R = r0 (LSB) .. r3. Restoring shift-subtract, 32 rounds.
__awto_dm32:
	clr	a
	mov	r0,a
	mov	r1,a
	mov	r2,a
	mov	r3,a
	mov	b,#32
00101$:
	clr	c			; (R:N) <<= 1, carry out of R in F0
	mov	a,r4
	rlc	a
	mov	r4,a
	mov	a,r5
	rlc	a
	mov	r5,a
	mov	a,r6
	rlc	a
	mov	r6,a
	mov	a,r7
	rlc	a
	mov	r7,a
	mov	a,r0
	rlc	a
	mov	r0,a
	mov	a,r1
	rlc	a
	mov	r1,a
	mov	a,r2
	rlc	a
	mov	r2,a
	mov	a,r3
	rlc	a
	mov	r3,a
	mov	0xD5,c
	mov	dptr,#__awto_md_D
	clr	c			; R -= D
	movx	a,@dptr
	xch	a,r0
	subb	a,r0
	mov	r0,a
	inc	dptr
	movx	a,@dptr
	xch	a,r1
	subb	a,r1
	mov	r1,a
	inc	dptr
	movx	a,@dptr
	xch	a,r2
	subb	a,r2
	mov	r2,a
	inc	dptr
	movx	a,@dptr
	xch	a,r3
	subb	a,r3
	mov	r3,a
	jnc	00103$			; R >= D: keep, quotient bit 1
	jb	0xD5,00103$		; carry out of R: true R >= 2^32 > D
	mov	dptr,#__awto_md_D	; undo
	movx	a,@dptr
	add	a,r0
	mov	r0,a
	inc	dptr
	movx	a,@dptr
	addc	a,r1
	mov	r1,a
	inc	dptr
	movx	a,@dptr
	addc	a,r2
	mov	r2,a
	inc	dptr
	movx	a,@dptr
	addc	a,r3
	mov	r3,a
	sjmp	00104$
00103$:
	inc	r4
00104$:
	djnz	b,00101$
	ret
;	 function _awto_pd_body
; N = r4..r7 (A), D = __awto_md_D, pow = __awto_md_pow -> result r4..r7 (PowDiv semantics, see header)
__awto_pd_body:
	lcall	__awto_dm32		; round 1: res = A/D, A = (A%D)
	mov	a,r0			; A <<= 1 (32-bit wrap)
	add	a,r0
	mov	r0,a
	mov	a,r1
	rlc	a
	mov	r1,a
	mov	a,r2
	rlc	a
	mov	r2,a
	mov	a,r3
	rlc	a
	mov	r3,a
	mov	dptr,#__awto_md_D	; F0 = (D == 0)
	movx	a,@dptr
	mov	b,a
	inc	dptr
	movx	a,@dptr
	orl	a,b
	mov	b,a
	inc	dptr
	movx	a,@dptr
	orl	a,b
	mov	b,a
	inc	dptr
	movx	a,@dptr
	orl	a,b
	clr	0xD5
	jnz	00101$
	setb	0xD5
00101$:
	mov	dptr,#__awto_md_pow	; pow more rounds
	movx	a,@dptr
	mov	b,a
	jz	00109$
	jb	0xD5,00107$
00102$:					; q = A >= D (A -= D), res = res<<1 | q, A <<= 1
	mov	dptr,#__awto_md_D
	clr	c
	movx	a,@dptr
	xch	a,r0
	subb	a,r0
	mov	r0,a
	inc	dptr
	movx	a,@dptr
	xch	a,r1
	subb	a,r1
	mov	r1,a
	inc	dptr
	movx	a,@dptr
	xch	a,r2
	subb	a,r2
	mov	r2,a
	inc	dptr
	movx	a,@dptr
	xch	a,r3
	subb	a,r3
	mov	r3,a
	jc	00103$
	setb	c			; q = 1, A stays A - D
	sjmp	00104$
00103$:
	mov	dptr,#__awto_md_D	; q = 0: undo
	movx	a,@dptr
	add	a,r0
	mov	r0,a
	inc	dptr
	movx	a,@dptr
	addc	a,r1
	mov	r1,a
	inc	dptr
	movx	a,@dptr
	addc	a,r2
	mov	r2,a
	inc	dptr
	movx	a,@dptr
	addc	a,r3
	mov	r3,a
	clr	c
00104$:
	mov	a,r4			; res = res<<1 | C
	rlc	a
	mov	r4,a
	mov	a,r5
	rlc	a
	mov	r5,a
	mov	a,r6
	rlc	a
	mov	r6,a
	mov	a,r7
	rlc	a
	mov	r7,a
	mov	a,r0			; A <<= 1
	add	a,r0
	mov	r0,a
	mov	a,r1
	rlc	a
	mov	r1,a
	mov	a,r2
	rlc	a
	mov	r2,a
	mov	a,r3
	rlc	a
	mov	r3,a
	djnz	b,00102$
	sjmp	00109$
00107$:					; D == 0: res = res*2 + 0xFFFFFFFF = res*2 - 1
	clr	c
	mov	a,r4
	rlc	a
	mov	r4,a
	mov	a,r5
	rlc	a
	mov	r5,a
	mov	a,r6
	rlc	a
	mov	r6,a
	mov	a,r7
	rlc	a
	mov	r7,a
	clr	c
	mov	a,r4
	subb	a,#1
	mov	r4,a
	mov	a,r5
	subb	a,#0
	mov	r5,a
	mov	a,r6
	subb	a,#0
	mov	r6,a
	mov	a,r7
	subb	a,#0
	mov	r7,a
	djnz	b,00107$
00109$:					; return A >= D ? res + 1 : res
	mov	dptr,#__awto_md_D
	clr	c
	movx	a,@dptr
	mov	b,a
	mov	a,r0
	subb	a,b
	inc	dptr
	movx	a,@dptr
	mov	b,a
	mov	a,r1
	subb	a,b
	inc	dptr
	movx	a,@dptr
	mov	b,a
	mov	a,r2
	subb	a,b
	inc	dptr
	movx	a,@dptr
	mov	b,a
	mov	a,r3
	subb	a,b
	jc	00110$
	inc	r4
	cjne	r4,#0x00,00110$
	inc	r5
	cjne	r5,#0x00,00110$
	inc	r6
	cjne	r6,#0x00,00110$
	inc	r7
00110$:
	ret
;	 function _awto_mul64
; __awto_md_P (8 B, lsb first) = __awto_md_A * __awto_md_B (4 B each, lsb first); schoolbook bytes, carry ripples up.
__awto_mul64:
	clr	a
	mov	dptr,#__awto_md_P
	mov	r2,#8
00101$:
	movx	@dptr,a
	inc	dptr
	djnz	r2,00101$
	mov	r0,#0			; i
00102$:
	mov	dptr,#__awto_md_A
	mov	a,r0
	add	a,dpl
	mov	dpl,a
	clr	a
	addc	a,dph
	mov	dph,a
	movx	a,@dptr
	mov	r2,a			; A[i]
	mov	r1,#0			; j
00103$:
	mov	dptr,#__awto_md_B
	mov	a,r1
	add	a,dpl
	mov	dpl,a
	clr	a
	addc	a,dph
	mov	dph,a
	movx	a,@dptr
	mov	b,a
	mov	a,r2
	mul	ab
	mov	r4,a			; product lo
	mov	r5,b			; product hi
	mov	a,r0
	add	a,r1
	mov	r3,a			; k = i + j
	mov	a,#6
	clr	c
	subb	a,r3
	mov	r6,a			; carry slots above P[k+1]
	mov	dptr,#__awto_md_P
	mov	a,r3
	add	a,dpl
	mov	dpl,a
	clr	a
	addc	a,dph
	mov	dph,a
	movx	a,@dptr
	add	a,r4
	movx	@dptr,a
	inc	dptr
	movx	a,@dptr
	addc	a,r5
	movx	@dptr,a
00104$:
	jnc	00105$
	mov	a,r6
	jz	00105$
	inc	dptr
	movx	a,@dptr
	add	a,#1
	movx	@dptr,a
	dec	r6
	sjmp	00104$
00105$:
	inc	r1
	cjne	r1,#4,00103$
	inc	r0
	cjne	r0,#4,00102$
	ret
	.area CSEG    (CODE)
	.area CONST   (CODE)
	.area XINIT   (CODE)
	.area CABS    (ABS,CODE)
