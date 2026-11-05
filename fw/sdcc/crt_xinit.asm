; Replaces SDCC's crtxinit (__mcs51_genXINIT): copy XINIT (code) -> XISEG (xdata) with DPTR only.
; SDCC's version writes via movx @r0 + P2 as page byte; DW8051 page SFR unconfirmed (#8) -> avoid @Ri.
; Same area as the library module (GSINIT3) so startup falls through into GSINIT4 (RAM clear).
	.module	awto_xinit
	.globl	__mcs51_genXINIT
	.globl	l_XINIT, s_XINIT, s_XISEG
	.globl	s_XSEG1, l_XSEG1, s_XSEG2, l_XSEG2, s_XSEG3, l_XSEG3, s_XSEG4, l_XSEG4
; Empty declarations keep l_/s_ defined when split_xseg() leaves an area unused (undefined = link error).
	.area	XSEG1	(XDATA)
	.area	XSEG2	(XDATA)
	.area	XSEG3	(XDATA)
	.area	XSEG4	(XDATA)

	.area	GSINIT3	(CODE)
__mcs51_genXINIT:
	mov	r1,#l_XINIT
	mov	a,r1
	orl	a,#(l_XINIT >> 8)
	jz	00003$
	mov	r2,#((l_XINIT + 255) >> 8)
	mov	dptr,#s_XINIT
	mov	r4,#s_XISEG
	mov	r5,#(s_XISEG >> 8)
00001$:
	clr	a
	movc	a,@a+dptr
	inc	dptr
	mov	r6,dpl
	mov	r7,dph
	mov	dpl,r4
	mov	dph,r5
	movx	@dptr,a
	inc	dptr
	mov	r4,dpl
	mov	r5,dph
	mov	dpl,r6
	mov	dph,r7
	djnz	r1,00001$
	djnz	r2,00001$
00003$:
; Clear XSEG1..4 (split_xseg holes). Zero length skips the loop; same r1/r2 page scheme as above.
	mov	r1,#l_XSEG1
	mov	a,r1
	orl	a,#(l_XSEG1 >> 8)
	jz	00011$
	mov	r2,#((l_XSEG1 + 255) >> 8)
	mov	dptr,#s_XSEG1
	clr	a
00012$:
	movx	@dptr,a
	inc	dptr
	djnz	r1,00012$
	djnz	r2,00012$
00011$:
	mov	r1,#l_XSEG2
	mov	a,r1
	orl	a,#(l_XSEG2 >> 8)
	jz	00021$
	mov	r2,#((l_XSEG2 + 255) >> 8)
	mov	dptr,#s_XSEG2
	clr	a
00022$:
	movx	@dptr,a
	inc	dptr
	djnz	r1,00022$
	djnz	r2,00022$
00021$:
	mov	r1,#l_XSEG3
	mov	a,r1
	orl	a,#(l_XSEG3 >> 8)
	jz	00031$
	mov	r2,#((l_XSEG3 + 255) >> 8)
	mov	dptr,#s_XSEG3
	clr	a
00032$:
	movx	@dptr,a
	inc	dptr
	djnz	r1,00032$
	djnz	r2,00032$
00031$:
	mov	r1,#l_XSEG4
	mov	a,r1
	orl	a,#(l_XSEG4 >> 8)
	jz	00041$
	mov	r2,#((l_XSEG4 + 255) >> 8)
	mov	dptr,#s_XSEG4
	clr	a
00042$:
	movx	@dptr,a
	inc	dptr
	djnz	r1,00042$
	djnz	r2,00042$
00041$:
