;--------------------------------------------------------
; File Created by SDCC : free open source ISO C Compiler
; Version 4.5.0 #15242 (Linux)
;--------------------------------------------------------
	.module u
	
	.optsdcc -mmcs51 --model-large
;--------------------------------------------------------
; Public variables in this module
;--------------------------------------------------------
	.globl _top
	.globl _mid
	.globl _leaf
	.globl _mid_PARM_3
	.globl _mid_PARM_2
	.globl _leaf_PARM_2
	.globl _g
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
	.ds 8
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
_g::
	.ds 1
_leaf_PARM_2:
	.ds 2
_leaf_a_10000_1:
	.ds 1
_leaf_t_10000_2:
	.ds 4
_mid_PARM_2:
	.ds 1
_mid_PARM_3:
	.ds 1
_mid_a_10000_3:
	.ds 1
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
;Allocation info for local variables in function 'leaf'
;------------------------------------------------------------
;b             Allocated with name '_leaf_PARM_2'
;a             Allocated with name '_leaf_a_10000_1'
;t             Allocated with name '_leaf_t_10000_2'
;------------------------------------------------------------
;	/mnt/2tb/git/awto-ddc/tmp/sdcc-probe/u.c:2: void leaf(unsigned char a, unsigned int b) { unsigned char t[4]; t[a & 3] = b; g = t[0]; }
;	-----------------------------------------
;	 function leaf
;	-----------------------------------------
_leaf:
	ar7 = 0x07
	ar6 = 0x06
	ar5 = 0x05
	ar4 = 0x04
	ar3 = 0x03
	ar2 = 0x02
	ar1 = 0x01
	ar0 = 0x00
	mov	a,dpl
	mov	dptr,#_leaf_a_10000_1
	movx	@dptr,a
	movx	a,@dptr
	mov	r7,a
	mov	a,#0x03
	anl	a,r7
	add	a, #_leaf_t_10000_2
	mov	r6,a
	clr	a
	addc	a,#(_leaf_t_10000_2 >> 8)
	mov	r7,a
	mov	dptr,#_leaf_PARM_2
	movx	a,@dptr
	mov	dpl,r6
	mov	dph,r7
	movx	@dptr,a
	mov	dptr,#_leaf_t_10000_2
	movx	a,@dptr
	mov	dptr,#_g
	movx	@dptr,a
	ret
;------------------------------------------------------------
;Allocation info for local variables in function 'mid'
;------------------------------------------------------------
;b             Allocated with name '_mid_PARM_2'
;c             Allocated with name '_mid_PARM_3'
;a             Allocated with name '_mid_a_10000_3'
;x             Allocated with name '_mid_x_10000_4'
;------------------------------------------------------------
;	/mnt/2tb/git/awto-ddc/tmp/sdcc-probe/u.c:3: unsigned int mid(unsigned char a, unsigned char b, unsigned char c) { unsigned long x = a; x *= b; leaf(c, x); return x; }
;	-----------------------------------------
;	 function mid
;	-----------------------------------------
_mid:
	mov	a,dpl
	mov	dptr,#_mid_a_10000_3
	movx	@dptr,a
	movx	a,@dptr
	mov	r7,a
	mov	dptr,#_mid_PARM_2
	movx	a,@dptr
	mov	b,r7
	mul	ab
	mov	r7,a
	mov	r5,b
	mov	dptr,#_mid_PARM_3
	movx	a,@dptr
	mov	r6,a
	mov	dptr,#_leaf_PARM_2
	mov	a,r7
	movx	@dptr,a
	mov	a,r5
	inc	dptr
	movx	@dptr,a
	mov	dpl, r6
	push	ar7
	push	ar5
	lcall	_leaf
	pop	ar5
	pop	ar7
	mov	dpl, r7
	mov	dph, r5
	ret
;------------------------------------------------------------
;Allocation info for local variables in function 'top'
;------------------------------------------------------------
;i             Allocated with name '_top_i_10000_6'
;------------------------------------------------------------
;	/mnt/2tb/git/awto-ddc/tmp/sdcc-probe/u.c:4: void top(void) { unsigned char i; for (i = 0; i < 3; i++) g += mid(i, i, i); }
;	-----------------------------------------
;	 function top
;	-----------------------------------------
_top:
	mov	r7,#0x00
00102$:
	mov	dptr,#_mid_PARM_2
	mov	a,r7
	movx	@dptr,a
	mov	dptr,#_mid_PARM_3
	mov	a,r7
	movx	@dptr,a
	mov	dpl, r7
	push	ar7
	lcall	_mid
	mov	r5, dpl
	pop	ar7
	mov	dptr,#_g
	movx	a,@dptr
	add	a, r5
	movx	@dptr,a
	inc	r7
	cjne	r7,#0x03,00113$
00113$:
	jc	00102$
	ret
	.area CSEG    (CODE)
	.area CONST   (CODE)
	.area XINIT   (CODE)
	.area CABS    (ABS,CODE)
