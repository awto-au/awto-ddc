; Hand-written 8051 replacement for Realtek ScalerCommonDataPortAccessSetWord.c, SDCC mcs51 large --big-endian, #11.
; ScalerSetDataPortWord(WORD usAddr /*DPL,DPH*/, BYTE ucValue1, WORD usValue2 /*BE: +0 hi, +1 lo*/)
; = W(a,v1) W(a+1,hi) W(a,(BYTE)(v1+1)) W(a+1,lo); the C calls ScalerSetDataPortByte twice, inlined here.
	.module ScalerCommonDataPortAccessSetWord
	.optsdcc -mmcs51 --model-large --big-endian
	.globl _ScalerSetDataPortWord_PARM_2
	.globl _ScalerSetDataPortWord_PARM_3
	.globl _ScalerSetDataPortWord
	.area XSEG    (XDATA)
_ScalerSetDataPortWord_PARM_2:
	.ds 1
_ScalerSetDataPortWord_PARM_3:
	.ds 2
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
;	 function ScalerSetDataPortWord
_ScalerSetDataPortWord:
	mov	r6,dph
	mov	r7,dpl
	mov	dptr,#_ScalerSetDataPortWord_PARM_2
	movx	a,@dptr
	mov	r5,a			; v1
	inc	dptr
	movx	a,@dptr
	mov	r4,a			; hi
	inc	dptr
	movx	a,@dptr
	mov	r3,a			; lo
	mov	dpl,r7
	mov	dph,r6
	mov	a,r5
	movx	@dptr,a
	inc	dptr
	mov	a,r4
	movx	@dptr,a
	mov	dpl,r7
	mov	dph,r6
	mov	a,r5
	inc	a
	movx	@dptr,a
	inc	dptr
	mov	a,r3
	movx	@dptr,a
	ret
	.area CSEG    (CODE)
	.area CONST   (CODE)
	.area XINIT   (CODE)
	.area CABS    (ABS,CODE)
