; Replaces SDCC's crtxinit (__mcs51_genXINIT): copy XINIT (code) -> XISEG (xdata) with DPTR only.
; SDCC's version writes via movx @r0 + P2 as page byte; DW8051 page SFR unconfirmed (#8) -> avoid @Ri.
; Same area as the library module (GSINIT3) so startup falls through into GSINIT4 (RAM clear).
	.module	awto_xinit
	.globl	__mcs51_genXINIT
	.globl	l_XINIT, s_XINIT, s_XISEG

	.area	GSINIT3	(CODE)
; RAM clear first (fw_build expands the marker: one loop per XDATA hole, fixed bounds from fw/rl6449_memory.toml;
; DDC RAM windows skipped). Before the XINIT copy: XISEG lies inside a hole. No l_XSEG: sizes must not reach common.
;@XCLEAR@
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

; Replaces the library crtxclear (l_XSEG clear): the clear above covers it. Falls through like the library code.
	.area	GSINIT4	(CODE)
__mcs51_genXRAMCLEAR::
