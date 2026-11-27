;--------------------------------------------------------
; File Created by SDCC : free open source ISO C Compiler
; Version 4.5.0 #15242 (Linux)
;--------------------------------------------------------
	.module crt_mod0
	
	.optsdcc -mmcs51 --model-large
;--------------------------------------------------------
; Public variables in this module
;--------------------------------------------------------
	.globl __moduint_PARM_2
	.globl __modulong_PARM_2
	.globl __modulong
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
	.area	OSEG    (OVR,DATA)
__modulong_sloc0_1_0:
	.ds 4
__modulong_sloc2_1_0:
	.ds 4
__modulong_sloc3_1_0:
	.ds 1
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
__modulong_sloc1_1_0:
	.ds 1
__moduint_sloc0_1_0:
	.ds 1
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
__modulong_r_10000_2:
	.ds 4
__modulong_c_10000_2:
	.ds 1
__moduint_PARM_2:
	.ds 2
__moduint_a_10000_5:
	.ds 2
__moduint_r_10000_6:
	.ds 2
__moduint_c_10000_6:
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
;r             Allocated with name '__modulong_r_10000_2'
;i             Allocated with name '__modulong_i_10000_2'
;c             Allocated with name '__modulong_c_10000_2'
;sloc0         Allocated with name '__modulong_sloc0_1_0'
;sloc2         Allocated with name '__modulong_sloc2_1_0'
;sloc3         Allocated with name '__modulong_sloc3_1_0'
;------------------------------------------------------------
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:4: unsigned long _modulong(unsigned long a, unsigned long b)
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
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:6: unsigned long r = 0;
	mov	dptr,#__modulong_r_10000_2
	clr	a
	movx	@dptr,a
	inc	dptr
	movx	@dptr,a
	inc	dptr
	movx	@dptr,a
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:9: if (b == 0)
	mov	dptr,#__modulong_PARM_2
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
	mov	a,r4
	orl	a,r5
	orl	a,r6
	orl	a,r7
	jnz	00113$
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:10: return a;
	mov	dptr,#__modulong_a_10000_1
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
	mov	dpl,r0
	mov	dph,r1
	mov	b,r2
	ret
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:11: for (i = 32; i; i--) {
00113$:
	mov	__modulong_sloc3_1_0,#0x20
00107$:
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:12: c = (r & 0x80000000UL) != 0;        /* bit shifted out: true remainder >= 2^32 > b */
	mov	dptr,#__modulong_r_10000_2
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
	clr	a
	mov	r0,a
	mov	r1,a
	mov	r2,a
	mov	a,#0x80
	anl	a,(__modulong_sloc0_1_0 + 3)
	mov	r3,a
	mov	a,r0
	orl	a,r1
	orl	a,r2
	orl	a,r3
	cjne	a,#0x01,00137$
00137$:
	cpl	c
	mov	__modulong_sloc1_1_0,c
	mov	dptr,#__modulong_c_10000_2
	clr	a
	rlc	a
	movx	@dptr,a
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:13: r = (r << 1) | (a >> 31);
	mov	a,__modulong_sloc0_1_0
	add	a,__modulong_sloc0_1_0
	mov	__modulong_sloc0_1_0,a
	mov	a,(__modulong_sloc0_1_0 + 1)
	rlc	a
	mov	(__modulong_sloc0_1_0 + 1),a
	mov	a,(__modulong_sloc0_1_0 + 2)
	rlc	a
	mov	(__modulong_sloc0_1_0 + 2),a
	mov	a,(__modulong_sloc0_1_0 + 3)
	rlc	a
	mov	(__modulong_sloc0_1_0 + 3),a
	mov	dptr,#__modulong_a_10000_1
	movx	a,@dptr
	mov	__modulong_sloc2_1_0,a
	inc	dptr
	movx	a,@dptr
	mov	(__modulong_sloc2_1_0 + 1),a
	inc	dptr
	movx	a,@dptr
	mov	(__modulong_sloc2_1_0 + 2),a
	inc	dptr
	movx	a,@dptr
	mov	(__modulong_sloc2_1_0 + 3),a
	rl	a
	anl	a,#0x01
	mov	r0,a
	mov	r1,#0x00
	mov	r2,#0x00
	mov	r3,#0x00
	mov	dptr,#__modulong_r_10000_2
	mov	a,r0
	orl	a,__modulong_sloc0_1_0
	movx	@dptr,a
	mov	a,r1
	orl	a,(__modulong_sloc0_1_0 + 1)
	inc	dptr
	movx	@dptr,a
	mov	a,r2
	orl	a,(__modulong_sloc0_1_0 + 2)
	inc	dptr
	movx	@dptr,a
	mov	a,r3
	orl	a,(__modulong_sloc0_1_0 + 3)
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:14: a <<= 1;
	mov	a,__modulong_sloc2_1_0
	add	a,__modulong_sloc2_1_0
	mov	r0,a
	mov	a,(__modulong_sloc2_1_0 + 1)
	rlc	a
	mov	r1,a
	mov	a,(__modulong_sloc2_1_0 + 2)
	rlc	a
	mov	r2,a
	mov	a,(__modulong_sloc2_1_0 + 3)
	rlc	a
	mov	r3,a
	mov	dptr,#__modulong_a_10000_1
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
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:15: if (c || r >= b)
	mov	dptr,#__modulong_c_10000_2
	movx	a,@dptr
	jnz	00103$
	mov	dptr,#__modulong_r_10000_2
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
	clr	c
	mov	a,r0
	subb	a,r4
	mov	a,r1
	subb	a,r5
	mov	a,r2
	subb	a,r6
	mov	a,r3
	subb	a,r7
	jc	00108$
00103$:
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:16: r -= b;
	mov	dptr,#__modulong_r_10000_2
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
	mov	dptr,#__modulong_r_10000_2
	mov	a,r0
	clr	c
	subb	a,r4
	movx	@dptr,a
	mov	a,r1
	subb	a,r5
	inc	dptr
	movx	@dptr,a
	mov	a,r2
	subb	a,r6
	inc	dptr
	movx	@dptr,a
	mov	a,r3
	subb	a,r7
	inc	dptr
	movx	@dptr,a
00108$:
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:11: for (i = 32; i; i--) {
	dec	__modulong_sloc3_1_0
	mov	a,__modulong_sloc3_1_0
	jz	00140$
	ljmp	00107$
00140$:
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:18: return r;
	mov	dptr,#__modulong_r_10000_2
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
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:19: }
	ret
;------------------------------------------------------------
;Allocation info for local variables in function '_moduint'
;------------------------------------------------------------
;b             Allocated with name '__moduint_PARM_2'
;a             Allocated with name '__moduint_a_10000_5'
;r             Allocated with name '__moduint_r_10000_6'
;i             Allocated with name '__moduint_i_10000_6'
;c             Allocated with name '__moduint_c_10000_6'
;------------------------------------------------------------
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:21: unsigned int _moduint(unsigned int a, unsigned int b)
;	-----------------------------------------
;	 function _moduint
;	-----------------------------------------
__moduint:
	mov	r7,dph
	mov	a,dpl
	mov	dptr,#__moduint_a_10000_5
	movx	@dptr,a
	mov	a,r7
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:23: unsigned int r = 0;
	mov	dptr,#__moduint_r_10000_6
	clr	a
	movx	@dptr,a
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:26: if (b == 0)
	mov	dptr,#__moduint_PARM_2
	movx	a,@dptr
	mov	r6,a
	inc	dptr
	movx	a,@dptr
	mov	r7,a
	orl	a,r6
	jnz	00113$
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:27: return a;
	mov	dptr,#__moduint_a_10000_5
	movx	a,@dptr
	mov	r4,a
	inc	dptr
	movx	a,@dptr
	mov	r5,a
	mov	dpl, r4
	mov	dph, r5
	ret
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:28: for (i = 16; i; i--) {
00113$:
	mov	r5,#0x10
00107$:
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:29: c = (r & 0x8000U) != 0;
	push	ar5
	mov	dptr,#__moduint_r_10000_6
	movx	a,@dptr
	mov	r3,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	mov	r1,#0x00
	mov	a,#0x80
	anl	a,r4
	orl	a,r1
	cjne	a,#0x01,00137$
00137$:
	cpl	c
	mov	__moduint_sloc0_1_0,c
	mov	dptr,#__moduint_c_10000_6
	clr	a
	rlc	a
	movx	@dptr,a
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:30: r = (r << 1) | (a >> 15);
	mov	a,r3
	add	a,r3
	mov	r3,a
	mov	a,r4
	rlc	a
	mov	r4,a
	mov	dptr,#__moduint_a_10000_5
	movx	a,@dptr
	mov	r1,a
	inc	dptr
	movx	a,@dptr
	mov	r2,a
	rl	a
	anl	a,#0x01
	mov	r0,a
	mov	r5,#0x00
	mov	dptr,#__moduint_r_10000_6
	mov	a,r0
	orl	a,r3
	movx	@dptr,a
	mov	a,r5
	orl	a,r4
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:31: a <<= 1;
	mov	a,r1
	add	a,r1
	mov	r1,a
	mov	a,r2
	rlc	a
	mov	r2,a
	mov	dptr,#__moduint_a_10000_5
	mov	a,r1
	movx	@dptr,a
	mov	a,r2
	inc	dptr
	movx	@dptr,a
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:32: if (c || r >= b)
	pop	ar5
	mov	dptr,#__moduint_c_10000_6
	movx	a,@dptr
	jnz	00103$
	mov	dptr,#__moduint_r_10000_6
	movx	a,@dptr
	mov	r3,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	clr	c
	mov	a,r3
	subb	a,r6
	mov	a,r4
	subb	a,r7
	jc	00108$
00103$:
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:33: r -= b;
	mov	dptr,#__moduint_r_10000_6
	movx	a,@dptr
	mov	r3,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	mov	dptr,#__moduint_r_10000_6
	mov	a,r3
	clr	c
	subb	a,r6
	movx	@dptr,a
	mov	a,r4
	subb	a,r7
	inc	dptr
	movx	@dptr,a
00108$:
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:28: for (i = 16; i; i--) {
	djnz	r5,00107$
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:35: return r;
	mov	dptr,#__moduint_r_10000_6
	movx	a,@dptr
	mov	r6,a
	inc	dptr
	movx	a,@dptr
;	/mnt/2tb/git/awto-ddc/fw/sdcc/crt_mod0.c:36: }
	mov	dpl,r6
	mov	dph,a
	ret
	.area CSEG    (CODE)
	.area CONST   (CODE)
	.area XINIT   (CODE)
	.area CABS    (ABS,CODE)
