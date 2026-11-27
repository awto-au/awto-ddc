;--------------------------------------------------------
; File Created by SDCC : free open source ISO C Compiler
; Version 4.6.4 #0 (Linux)
;--------------------------------------------------------
	.module u
	
	.optsdcc -mmcs51 --model-large
;--------------------------------------------------------
; Public variables in this module
;--------------------------------------------------------
	.globl _isr
	.globl _g
	.globl _g_PARM_2
	.globl _x
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
	.area REG_BANK_1	(REL,OVR,DATA)
rbank1:	.ds 8
;--------------------------------------------------------
; overlayable bit register bank
;--------------------------------------------------------
	.area BIT_BANK	(REL,OVR,DATA)
bits:
	.ds 1
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
_x::
	.ds 4
_g_PARM_2:
	.ds 1
_g_a_10000_1:
	.ds 1
_g_s_10000_2:
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
;Allocation info for local variables in function 'g'
;------------------------------------------------------------
;b             Allocated with name '_g_PARM_2'
;a             Allocated with name '_g_a_10000_1'
;i             Allocated with name '_g_i_10000_2'
;s             Allocated with name '_g_s_10000_2'
;------------------------------------------------------------
;	/mnt/2tb/git/awto-ddc/tmp/using_test/u.c:3: unsigned char g(unsigned char a, unsigned char b) __using(1)
;	-----------------------------------------
;	 function g
;	-----------------------------------------
_g:
	ar7 = rbank1 + 0x07
	ar6 = rbank1 + 0x06
	ar5 = rbank1 + 0x05
	ar4 = rbank1 + 0x04
	ar3 = rbank1 + 0x03
	ar2 = rbank1 + 0x02
	ar1 = rbank1 + 0x01
	ar0 = rbank1 + 0x00
	mov	a,dpl
	mov	dptr,#_g_a_10000_1
	movx	@dptr,a
;	/mnt/2tb/git/awto-ddc/tmp/using_test/u.c:5: unsigned char i, s = 0;
	mov	dptr,#_g_s_10000_2
	clr	a
	movx	@dptr,a
;	/mnt/2tb/git/awto-ddc/tmp/using_test/u.c:6: for (i = 0; i < a; i++) { s += x[i & 3] ^ b; x[0] = s; }
	mov	dptr,#_g_PARM_2
	movx	a,@dptr
	mov	r7,a
	mov	dptr,#_g_a_10000_1
	movx	a,@dptr
	mov	r6,a
	mov	r5,#0x00
00103$:
	clr	c
	mov	a,r5
	subb	a,r6
	jnc	00101$
	mov	ar4,r5
	mov	a,#0x03
	anl	a,r4
	add	a, #_x
	mov	dpl,a
	clr	a
	addc	a,#(_x >> 8)
	mov	dph,a
	movx	a,@dptr
	mov	r4,a
	mov	a,r7
	xrl	ar4,a
	mov	dptr,#_g_s_10000_2
	movx	a,@dptr
	add	a, r4
	movx	@dptr,a
	movx	a,@dptr
	mov	dptr,#_x
	movx	@dptr,a
	inc	r5
	sjmp	00103$
00101$:
;	/mnt/2tb/git/awto-ddc/tmp/using_test/u.c:7: return s;
	mov	dptr,#_g_s_10000_2
	movx	a,@dptr
;	/mnt/2tb/git/awto-ddc/tmp/using_test/u.c:8: }
	mov	dpl,a
	ret
;------------------------------------------------------------
;Allocation info for local variables in function 'isr'
;------------------------------------------------------------
;	/mnt/2tb/git/awto-ddc/tmp/using_test/u.c:9: void isr(void) __interrupt(0) __using(1)
;	-----------------------------------------
;	 function isr
;	-----------------------------------------
_isr:
	push	acc
	push	psw
	mov	psw,#0x08
	push	dpl
	push	dph
	push	b
;	/mnt/2tb/git/awto-ddc/tmp/using_test/u.c:11: x[1] = g(x[2], x[3]);
	mov	dptr,#(_x + 0x0002)
	movx	a,@dptr
	mov	r7,a
	mov	dptr,#(_x + 0x0003)
	movx	a,@dptr
	mov	dptr,#_g_PARM_2
	movx	@dptr,a
	mov	dpl, r7
	lcall	_g
	mov	r7, dpl
	mov	dptr,#(_x + 0x0001)
	mov	a,r7
	movx	@dptr,a
;	/mnt/2tb/git/awto-ddc/tmp/using_test/u.c:12: }
	pop	b
	pop	dph
	pop	dpl
	pop	psw
	pop	acc
	reti
;	eliminated unneeded push/pop bits[0]
	.area CSEG    (CODE)
	.area CONST   (CODE)
	.area XINIT   (CODE)
	.area CABS    (ABS,CODE)
