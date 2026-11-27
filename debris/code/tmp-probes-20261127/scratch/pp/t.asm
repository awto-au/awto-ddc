;--------------------------------------------------------
; File Created by SDCC : free open source ISO C Compiler
; Version 4.6.4 #0 (Linux)
;--------------------------------------------------------
	.module t
	
	.optsdcc -mmcs51 --model-large sdcccall(0)
;--------------------------------------------------------
; Public variables in this module
;--------------------------------------------------------
	.globl _g
	.globl _sink
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
_sink::
	.ds 1
_f_PARM_2:
	.ds 1
_f_t_10000_2:
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
	.area PLACE_font(CODE)
;------------------------------------------------------------
;Allocation info for local variables in function 'f'
;------------------------------------------------------------
;n             Allocated with name '_f_PARM_2'
;b             Allocated to registers r6 r7 
;i             Allocated with name '_f_i_10000_2'
;t             Allocated with name '_f_t_10000_2'
;------------------------------------------------------------
;	t.c:7: static void f(const unsigned char __code *b, unsigned char n)
;	-----------------------------------------
;	 function f
;	-----------------------------------------
_f:
	ar7 = rbank0 + 0x07
	ar6 = rbank0 + 0x06
	ar5 = rbank0 + 0x05
	ar4 = rbank0 + 0x04
	ar3 = rbank0 + 0x03
	ar2 = rbank0 + 0x02
	ar1 = rbank0 + 0x01
	ar0 = rbank0 + 0x00
	mov	r6, dpl
	mov	r7, dph
;	t.c:9: unsigned char i, t = 0;
	mov	dptr,#_f_t_10000_2
	clr	a
	movx	@dptr,a
;	t.c:10: for (i = 0; i < n; i++)
	mov	dptr,#_f_PARM_2
	movx	a,@dptr
	mov	r5,a
	mov	r4,#0x00
00103$:
	clr	c
	mov	a,r4
	subb	a,r5
	jnc	00101$
;	t.c:11: t += b[i];
	mov	a,r4
	add	a, r6
	mov	dpl,a
	clr	a
	addc	a, r7
	mov	dph,a
	clr	a
	movc	a,@a+dptr
	mov	r3,a
	mov	dptr,#_f_t_10000_2
	movx	a,@dptr
	add	a, r3
	movx	@dptr,a
;	t.c:10: for (i = 0; i < n; i++)
	inc	r4
	sjmp	00103$
00101$:
;	t.c:12: sink = t;
	mov	dptr,#_f_t_10000_2
	movx	a,@dptr
	mov	dptr,#_sink
	movx	@dptr,a
;	t.c:13: }
	ret
	.area CSEG    (CODE)
;------------------------------------------------------------
;Allocation info for local variables in function 'g'
;------------------------------------------------------------
;	t.c:15: void g(void) { f(blob, 4); }
;	-----------------------------------------
;	 function g
;	-----------------------------------------
_g:
	mov	dptr,#_f_PARM_2
	mov	a,#0x04
	movx	@dptr,a
	mov	dptr,#_blob
	ljmp	_f
	.area CSEG    (CODE)
	.area CONST   (CODE)
	.area PLACE_font(CODE)
_blob:
	.db #0x01	; 1
	.db #0x02	; 2
	.db #0x03	; 3
	.db #0x04	; 4
	.area CSEG    (CODE)
	.area XINIT   (CODE)
	.area CABS    (ABS,CODE)
