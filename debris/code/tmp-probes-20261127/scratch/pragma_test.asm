;--------------------------------------------------------
; File Created by SDCC : free open source ISO C Compiler
; Version 4.6.4 #0 (Linux)
;--------------------------------------------------------
	.module pragma_test
	
	.optsdcc -mmcs51 --model-large sdcccall(0)
;--------------------------------------------------------
; Public variables in this module
;--------------------------------------------------------
	.globl _CopySpeed
	.globl _CopySize
;--------------------------------------------------------
; special function registers
;--------------------------------------------------------
	.area RSEG    (ABS,DATA)
	.org 0x0000
;--------------------------------------------------------
; special function bits
;--------------------------------------------------------
	.area RSEG    (ABS,DATA)
	.org 0x0000
;--------------------------------------------------------
; overlayable register banks
;--------------------------------------------------------
	.area REG_BANK_0	(REL,OVR,DATA)
rbank0:	.ds 8
;--------------------------------------------------------
; internal ram data
;--------------------------------------------------------
	.area DSEG    (DATA)
;--------------------------------------------------------
; overlayable items in internal ram
;--------------------------------------------------------
;--------------------------------------------------------
; indirectly addressable internal ram data
;--------------------------------------------------------
	.area ISEG    (DATA)
;--------------------------------------------------------
; absolute internal ram data
;--------------------------------------------------------
	.area IABS    (ABS,DATA)
	.area IABS    (ABS,DATA)
;--------------------------------------------------------
; bit data
;--------------------------------------------------------
	.area BSEG    (BIT)
;--------------------------------------------------------
; paged external ram data
;--------------------------------------------------------
	.area PSEG    (PAG,XDATA)
;--------------------------------------------------------
; uninitialized external ram data
;--------------------------------------------------------
	.area XSEG    (XDATA)
;--------------------------------------------------------
; absolute external ram data
;--------------------------------------------------------
	.area XABS    (ABS,XDATA)
;--------------------------------------------------------
; initialized external ram data
;--------------------------------------------------------
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
;--------------------------------------------------------
; global & static initialisations
;--------------------------------------------------------
	.area HOME    (CODE)
	.area GSINIT  (CODE)
	.area GSFINAL (CODE)
	.area GSINIT  (CODE)
;--------------------------------------------------------
; Home
;--------------------------------------------------------
	.area HOME    (CODE)
	.area HOME    (CODE)
;--------------------------------------------------------
; code
;--------------------------------------------------------
	.area CSEG    (CODE)
;------------------------------------------------------------
;Allocation info for local variables in function 'CopySize'
;------------------------------------------------------------
;i             Allocated with name '_CopySize_i_10000_2'
;------------------------------------------------------------
;	pragma_test.c:4: void CopySize(void)
;	-----------------------------------------
;	 function CopySize
;	-----------------------------------------
_CopySize:
	ar7 = rbank0 + 0x07
	ar6 = rbank0 + 0x06
	ar5 = rbank0 + 0x05
	ar4 = rbank0 + 0x04
	ar3 = rbank0 + 0x03
	ar2 = rbank0 + 0x02
	ar1 = rbank0 + 0x01
	ar0 = rbank0 + 0x00
;	pragma_test.c:7: for(i = 0; i < 64; i++) { g_a[i] = g_b[i] + 3; }
	mov	r7,#0x00
00102$:
	mov	a,r7
	add	a, #_g_a
	mov	r5,a
	clr	a
	addc	a, #(_g_a >> 8)
	mov	r6,a
	mov	a,r7
	add	a, #_g_b
	mov	dpl,a
	clr	a
	addc	a, #(_g_b >> 8)
	mov	dph,a
	movx	a,@dptr
	mov	r4,a
	inc	r4
	inc	r4
	inc	r4
	mov	dpl,r5
	mov	dph,r6
	mov	a,r4
	movx	@dptr,a
	inc	r7
	cjne	r7,#0x40,00114$
00114$:
	jc	00102$
;	pragma_test.c:8: }
	ret
;------------------------------------------------------------
;Allocation info for local variables in function 'CopySpeed'
;------------------------------------------------------------
;i             Allocated with name '_CopySpeed_i_10000_6'
;------------------------------------------------------------
;	pragma_test.c:11: void CopySpeed(void)
;	-----------------------------------------
;	 function CopySpeed
;	-----------------------------------------
_CopySpeed:
;	pragma_test.c:14: for(i = 0; i < 64; i++) { g_a[i] = g_b[i] + 3; }
	mov	r7,#0x00
00102$:
	mov	a,r7
	add	a, #_g_a
	mov	r5,a
	clr	a
	addc	a, #(_g_a >> 8)
	mov	r6,a
	mov	a,r7
	add	a, #_g_b
	mov	dpl,a
	clr	a
	addc	a, #(_g_b >> 8)
	mov	dph,a
	movx	a,@dptr
	mov	r4,a
	inc	r4
	inc	r4
	inc	r4
	mov	dpl,r5
	mov	dph,r6
	mov	a,r4
	movx	@dptr,a
	inc	r7
	cjne	r7,#0x40,00114$
00114$:
	jc	00102$
;	pragma_test.c:15: }
	ret
	.area CSEG    (CODE)
	.area CONST   (CODE)
	.area XINIT   (CODE)
	.area CABS    (ABS,CODE)
