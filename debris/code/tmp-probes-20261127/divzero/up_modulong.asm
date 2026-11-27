;--------------------------------------------------------
; File Created by SDCC : free open source ISO C Compiler
; Version 4.5.0 #15242 (Linux)
;--------------------------------------------------------
	.module _modulong
	
	.optsdcc -mmcs51 --model-large
;--------------------------------------------------------
; Public variables in this module
;--------------------------------------------------------
	.globl __modulong_PARM_2
	.globl __modulong
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
	.area	OSEG    (OVR,DATA)
__modulong_sloc0_1_0:
	.ds 4
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
__modulong_PARM_2:
	.ds 4
__modulong_a_10000_1:
	.ds 4
__modulong_count_10000_2:
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
;Allocation info for local variables in function '_modulong'
;------------------------------------------------------------
;b             Allocated with name '__modulong_PARM_2'
;a             Allocated with name '__modulong_a_10000_1'
;count         Allocated with name '__modulong_count_10000_2'
;sloc0         Allocated with name '__modulong_sloc0_1_0'
;------------------------------------------------------------
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:342: _modulong (unsigned long a, unsigned long b) __SDCC_NONBANKED
;	-----------------------------------------
;	 function _modulong
;	-----------------------------------------
__modulong:
	ar7 = 0x07
	ar6 = 0x06
	ar5 = 0x05
	ar4 = 0x04
	ar3 = 0x03
	ar2 = 0x02
	ar1 = 0x01
	ar0 = 0x00
	mov	r7,dpl
	mov	r6,dph
	mov	r5,b
	mov	r4,a
	mov	dptr,#__modulong_a_10000_1
	mov	a,r7
	movx	@dptr,a
	mov	a,r6
	inc	dptr
	movx	@dptr,a
	mov	a,r5
	inc	dptr
	movx	@dptr,a
	mov	a,r4
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:344: unsigned char count = 0;
	mov	dptr,#__modulong_count_10000_2
	clr	a
	movx	@dptr,a
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:346: if (!b)                 /* same as the mcs51 asm versions: no endless loop */
	mov	dptr,#__modulong_PARM_2
	movx	a,@dptr
	mov	b,a
	inc	dptr
	movx	a,@dptr
	orl	b,a
	inc	dptr
	movx	a,@dptr
	orl	b,a
	inc	dptr
	movx	a,@dptr
	orl	a,b
	jnz	00118$
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:347: return a;
	mov	dptr,#__modulong_a_10000_1
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
	mov	dpl,r4
	mov	dph,r5
	mov	b,r6
	ret
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:349: while (!MSB_SET(b))
00118$:
	mov	dptr,#__modulong_a_10000_1
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
	mov	r3,#0x00
00105$:
	mov	dptr,#__modulong_PARM_2
	movx	a,@dptr
	mov	__modulong_sloc0_1_0,a
	inc	dptr
	movx	a,@dptr
	mov	(__modulong_sloc0_1_0 + 1),a
	inc	dptr
	movx	a,@dptr
	mov	(__modulong_sloc0_1_0 + 2),a
	inc	dptr
	movx	a,@dptr
	mov	(__modulong_sloc0_1_0 + 3),a
	rl	a
	anl	a,#0x01
	jnz	00120$
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:351: b <<= 1;
	push	ar3
	mov	a,__modulong_sloc0_1_0
	add	a,__modulong_sloc0_1_0
	mov	r0,a
	mov	a,(__modulong_sloc0_1_0 + 1)
	rlc	a
	mov	r1,a
	mov	a,(__modulong_sloc0_1_0 + 2)
	rlc	a
	mov	r2,a
	mov	a,(__modulong_sloc0_1_0 + 3)
	rlc	a
	mov	r3,a
	mov	dptr,#__modulong_PARM_2
	mov	a,r0
	movx	@dptr,a
	mov	a,r1
	inc	dptr
	movx	@dptr,a
	mov	a,r2
	inc	dptr
	movx	@dptr,a
	mov	a,r3
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:352: if (b > a)
	mov	dptr,#__modulong_PARM_2
	movx	a,@dptr
	mov	__modulong_sloc0_1_0,a
	inc	dptr
	movx	a,@dptr
	mov	(__modulong_sloc0_1_0 + 1),a
	inc	dptr
	movx	a,@dptr
	mov	(__modulong_sloc0_1_0 + 2),a
	inc	dptr
	movx	a,@dptr
	mov	(__modulong_sloc0_1_0 + 3),a
	clr	c
	mov	a,r4
	subb	a,__modulong_sloc0_1_0
	mov	a,r5
	subb	a,(__modulong_sloc0_1_0 + 1)
	mov	a,r6
	subb	a,(__modulong_sloc0_1_0 + 2)
	mov	a,r7
	subb	a,(__modulong_sloc0_1_0 + 3)
	pop	ar3
	jnc	00104$
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:354: b >>=1;
	mov	a,(__modulong_sloc0_1_0 + 3)
	clr	c
	rrc	a
	mov	(__modulong_sloc0_1_0 + 3),a
	mov	a,(__modulong_sloc0_1_0 + 2)
	rrc	a
	mov	(__modulong_sloc0_1_0 + 2),a
	mov	a,(__modulong_sloc0_1_0 + 1)
	rrc	a
	mov	(__modulong_sloc0_1_0 + 1),a
	mov	a,__modulong_sloc0_1_0
	rrc	a
	mov	__modulong_sloc0_1_0,a
	mov	dptr,#__modulong_PARM_2
	movx	@dptr,a
	mov	a,(__modulong_sloc0_1_0 + 1)
	inc	dptr
	movx	@dptr,a
	mov	a,(__modulong_sloc0_1_0 + 2)
	inc	dptr
	movx	@dptr,a
	mov	a,(__modulong_sloc0_1_0 + 3)
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:355: break;
	sjmp	00120$
00104$:
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:357: count++;
	inc	r3
	mov	dptr,#__modulong_count_10000_2
	mov	a,r3
	movx	@dptr,a
	ljmp	00105$
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:359: do
00120$:
	mov	dptr,#__modulong_count_10000_2
	movx	a,@dptr
	mov	r7,a
00110$:
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:361: if (a >= b)
	mov	dptr,#__modulong_a_10000_1
	movx	a,@dptr
	mov	r3,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	inc	dptr
	movx	a,@dptr
	mov	r5,a
	inc	dptr
	movx	a,@dptr
	mov	r6,a
	mov	dptr,#__modulong_PARM_2
	movx	a,@dptr
	mov	__modulong_sloc0_1_0,a
	inc	dptr
	movx	a,@dptr
	mov	(__modulong_sloc0_1_0 + 1),a
	inc	dptr
	movx	a,@dptr
	mov	(__modulong_sloc0_1_0 + 2),a
	inc	dptr
	movx	a,@dptr
	mov	(__modulong_sloc0_1_0 + 3),a
	clr	c
	mov	a,r3
	subb	a,__modulong_sloc0_1_0
	mov	a,r4
	subb	a,(__modulong_sloc0_1_0 + 1)
	mov	a,r5
	subb	a,(__modulong_sloc0_1_0 + 2)
	mov	a,r6
	subb	a,(__modulong_sloc0_1_0 + 3)
	jc	00109$
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:362: a -= b;
	mov	dptr,#__modulong_a_10000_1
	mov	a,r3
	clr	c
	subb	a,__modulong_sloc0_1_0
	movx	@dptr,a
	mov	a,r4
	subb	a,(__modulong_sloc0_1_0 + 1)
	inc	dptr
	movx	@dptr,a
	mov	a,r5
	subb	a,(__modulong_sloc0_1_0 + 2)
	inc	dptr
	movx	@dptr,a
	mov	a,r6
	subb	a,(__modulong_sloc0_1_0 + 3)
	inc	dptr
	movx	@dptr,a
00109$:
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:363: b >>= 1;
	mov	dptr,#__modulong_PARM_2
	movx	a,@dptr
	mov	r3,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	inc	dptr
	movx	a,@dptr
	mov	r5,a
	inc	dptr
	movx	a,@dptr
	clr	c
	rrc	a
	mov	r6,a
	mov	a,r5
	rrc	a
	mov	r5,a
	mov	a,r4
	rrc	a
	mov	r4,a
	mov	a,r3
	rrc	a
	mov	dptr,#__modulong_PARM_2
	movx	@dptr,a
	mov	a,r4
	inc	dptr
	movx	@dptr,a
	mov	a,r5
	inc	dptr
	movx	@dptr,a
	mov	a,r6
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:365: while (count--);
	mov	ar6,r7
	dec	r7
	mov	a,r6
	jnz	00110$
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:367: return a;
	mov	dptr,#__modulong_a_10000_1
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
	mov	dpl,r4
	mov	dph,r5
	mov	b,r6
;	/mnt/2tb/git/awto-sdcc/device/lib/_modulong.c:368: }
	ret
	.area CSEG    (CODE)
	.area CONST   (CODE)
	.area XINIT   (CODE)
	.area CABS    (ABS,CODE)
