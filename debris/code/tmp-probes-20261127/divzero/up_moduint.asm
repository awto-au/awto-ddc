;--------------------------------------------------------
; File Created by SDCC : free open source ISO C Compiler
; Version 4.5.0 #15242 (Linux)
;--------------------------------------------------------
	.module _moduint
	
	.optsdcc -mmcs51 --model-large
;--------------------------------------------------------
; Public variables in this module
;--------------------------------------------------------
	.globl __moduint_PARM_2
	.globl __moduint
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
__moduint_PARM_2:
	.ds 2
__moduint_a_10000_1:
	.ds 2
__moduint_count_10000_2:
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
;Allocation info for local variables in function '_moduint'
;------------------------------------------------------------
;b             Allocated with name '__moduint_PARM_2'
;a             Allocated with name '__moduint_a_10000_1'
;count         Allocated with name '__moduint_count_10000_2'
;------------------------------------------------------------
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:175: _moduint (unsigned int a, unsigned int b) __SDCC_NONBANKED
;	-----------------------------------------
;	 function _moduint
;	-----------------------------------------
__moduint:
	ar7 = 0x07
	ar6 = 0x06
	ar5 = 0x05
	ar4 = 0x04
	ar3 = 0x03
	ar2 = 0x02
	ar1 = 0x01
	ar0 = 0x00
	mov	r7,dph
	mov	a,dpl
	mov	dptr,#__moduint_a_10000_1
	movx	@dptr,a
	mov	a,r7
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:177: unsigned char count = 0;
	mov	dptr,#__moduint_count_10000_2
	clr	a
	movx	@dptr,a
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:179: if (!b)                 /* same as the mcs51 asm versions: no endless loop */
	mov	dptr,#__moduint_PARM_2
	movx	a,@dptr
	mov	b,a
	inc	dptr
	movx	a,@dptr
	orl	a,b
	jnz	00118$
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:180: return a;
	mov	dptr,#__moduint_a_10000_1
	movx	a,@dptr
	mov	r6,a
	inc	dptr
	movx	a,@dptr
	mov	r7,a
	mov	dpl, r6
	mov	dph, r7
	ret
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:182: while (!MSB_SET(b))
00118$:
	mov	dptr,#__moduint_a_10000_1
	movx	a,@dptr
	mov	r6,a
	inc	dptr
	movx	a,@dptr
	mov	r7,a
	mov	r5,#0x00
00105$:
	mov	dptr,#__moduint_PARM_2
	movx	a,@dptr
	mov	r3,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	rl	a
	anl	a,#0x01
	jnz	00120$
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:184: b <<= 1;
	mov	a,r3
	add	a,r3
	mov	r3,a
	mov	a,r4
	rlc	a
	mov	r4,a
	mov	dptr,#__moduint_PARM_2
	mov	a,r3
	movx	@dptr,a
	mov	a,r4
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:185: if (b > a)
	mov	dptr,#__moduint_PARM_2
	movx	a,@dptr
	mov	r3,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	clr	c
	mov	a,r6
	subb	a,r3
	mov	a,r7
	subb	a,r4
	jnc	00104$
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:187: b >>=1;
	mov	a,r4
	clr	c
	rrc	a
	xch	a,r3
	rrc	a
	xch	a,r3
	mov	r4,a
	mov	dptr,#__moduint_PARM_2
	mov	a,r3
	movx	@dptr,a
	mov	a,r4
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:188: break;
	sjmp	00120$
00104$:
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:190: count++;
	inc	r5
	mov	dptr,#__moduint_count_10000_2
	mov	a,r5
	movx	@dptr,a
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:192: do
	sjmp	00105$
00120$:
	mov	dptr,#__moduint_count_10000_2
	movx	a,@dptr
	mov	r7,a
00110$:
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:194: if (a >= b)
	mov	dptr,#__moduint_a_10000_1
	movx	a,@dptr
	mov	r5,a
	inc	dptr
	movx	a,@dptr
	mov	r6,a
	mov	dptr,#__moduint_PARM_2
	movx	a,@dptr
	mov	r3,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	clr	c
	mov	a,r5
	subb	a,r3
	mov	a,r6
	subb	a,r4
	jc	00109$
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:195: a -= b;
	mov	dptr,#__moduint_a_10000_1
	mov	a,r5
	clr	c
	subb	a,r3
	movx	@dptr,a
	mov	a,r6
	subb	a,r4
	inc	dptr
	movx	@dptr,a
00109$:
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:196: b >>= 1;
	mov	dptr,#__moduint_PARM_2
	movx	a,@dptr
	mov	r5,a
	inc	dptr
	movx	a,@dptr
	clr	c
	rrc	a
	xch	a,r5
	rrc	a
	xch	a,r5
	mov	r6,a
	mov	dptr,#__moduint_PARM_2
	mov	a,r5
	movx	@dptr,a
	mov	a,r6
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:198: while (count--);
	mov	ar6,r7
	dec	r7
	mov	a,r6
	jnz	00110$
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:199: return a;
	mov	dptr,#__moduint_a_10000_1
	movx	a,@dptr
	mov	r6,a
	inc	dptr
	movx	a,@dptr
;	/mnt/2tb/git/awto-sdcc/device/lib/_moduint.c:200: }
	mov	dpl,r6
	mov	dph,a
	ret
	.area CSEG    (CODE)
	.area CONST   (CODE)
	.area XINIT   (CODE)
	.area CABS    (ABS,CODE)
