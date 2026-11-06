; Hand-written 8051 replacement for Realtek ScalerCommonMultiByteRead.c (ScalerRead), SDCC mcs51 large --big-endian, #11.
; ScalerRead(WORD usAddr /*DPL,DPH*/, WORD usLength, BYTE *pucArray /*generic: +0 tag, +1 hi, +2 lo*/, bit bAutoInc)
; Realtek _AUTOINC = 0: bit clear -> memcpy(pucArray, (xdata*)usAddr, len); set -> pucArray[i] = R(usAddr) for all i.
; Fast path: pucArray tag 0x00 (xdata) and len < 0xFF00: byte loop. Else generic path: __gptrput per byte, 16-bit count.
	.module ScalerCommonMultiByteRead
	.optsdcc -mmcs51 --model-large --big-endian
	.globl _ScalerRead_PARM_2
	.globl _ScalerRead_PARM_3
	.globl _ScalerRead_PARM_4
	.globl _ScalerRead
	.globl __gptrput
	ar0 = 0x00
	ar1 = 0x01
	ar2 = 0x02
	ar3 = 0x03
	ar4 = 0x04
	ar5 = 0x05
	ar6 = 0x06
	ar7 = 0x07
	.area BSEG    (BIT)
_ScalerRead_PARM_4:
	.ds 1
	.area XSEG    (XDATA)
_ScalerRead_PARM_2:
	.ds 2
_ScalerRead_PARM_3:
	.ds 3
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
;	 function ScalerRead
_ScalerRead:
	mov	r6,dph			; r6:r7 = usAddr
	mov	r7,dpl
	mov	dptr,#_ScalerRead_PARM_2
	movx	a,@dptr
	mov	r3,a			; r3:r2 = usLength
	inc	dptr
	movx	a,@dptr
	mov	r2,a
	orl	a,r3
	jnz	00101$
	ret
00101$:
	mov	dptr,#_ScalerRead_PARM_3
	movx	a,@dptr
	mov	r0,a			; tag
	inc	dptr
	movx	a,@dptr
	mov	r1,a			; r1:r4 = destination
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	mov	a,r0
	jnz	00110$
	cjne	r3,#0xFF,00102$
	sjmp	00110$
00102$:
	mov	a,r2			; r3 = hi + (lo != 0) for the djnz pair
	jz	00103$
	inc	r3
00103$:
	jb	_ScalerRead_PARM_4,00106$
00104$:					; auto-increment source
	mov	dpl,r7
	mov	dph,r6
	movx	a,@dptr
	inc	dptr
	mov	r7,dpl
	mov	r6,dph
	mov	dpl,r4
	mov	dph,r1
	movx	@dptr,a
	inc	dptr
	mov	r4,dpl
	mov	r1,dph
	djnz	r2,00104$
	djnz	r3,00104$
	ret
00106$:					; fixed source address
	mov	dpl,r7
	mov	dph,r6
	movx	a,@dptr
	mov	dpl,r4
	mov	dph,r1
	movx	@dptr,a
	inc	dptr
	mov	r4,dpl
	mov	r1,dph
	djnz	r2,00106$
	djnz	r3,00106$
	ret
00110$:					; generic destination
	mov	dpl,r7
	mov	dph,r6
	movx	a,@dptr
	mov	dpl,r4
	mov	dph,r1
	mov	b,r0
	push	ar0
	push	ar1
	push	ar2
	push	ar3
	push	ar4
	push	ar6
	push	ar7
	lcall	__gptrput
	pop	ar7
	pop	ar6
	pop	ar4
	pop	ar3
	pop	ar2
	pop	ar1
	pop	ar0
	inc	r4
	cjne	r4,#0x00,00111$
	inc	r1
00111$:
	jb	_ScalerRead_PARM_4,00113$
	inc	r7
	cjne	r7,#0x00,00113$
	inc	r6
00113$:
	dec	r2
	cjne	r2,#0xFF,00114$
	dec	r3
00114$:
	mov	a,r2
	orl	a,r3
	jnz	00110$
	ret
	.area CSEG    (CODE)
	.area CONST   (CODE)
	.area XINIT   (CODE)
	.area CABS    (ABS,CODE)
