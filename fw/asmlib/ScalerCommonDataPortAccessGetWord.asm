; Hand-written 8051 replacement for Realtek ScalerCommonDataPortAccessGetWord.c, SDCC mcs51 large --big-endian, #11.
; WORD ScalerGetDataPortWord(WORD usAddr /*DPL,DPH*/, BYTE ucValue, bit bAutoInc) -> DPH:DPL
; Realtek _AUTOINC = 0: bit clear -> index = v, v+1; set -> v, v. hi = R(a+1) after W(a,v); lo = R(a+1) after W(a,idx2).
; The C goes through memset + ScalerGetDataPortByte(len 2) + a local array; inlined here.
	.module ScalerCommonDataPortAccessGetWord
	.optsdcc -mmcs51 --model-large --big-endian
	.globl _ScalerGetDataPortWord_PARM_2
	.globl _ScalerGetDataPortWord_PARM_3
	.globl _ScalerGetDataPortWord
	.area BSEG    (BIT)
_ScalerGetDataPortWord_PARM_3:
	.ds 1
	.area XSEG    (XDATA)
_ScalerGetDataPortWord_PARM_2:
	.ds 1
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
;	 function ScalerGetDataPortWord
_ScalerGetDataPortWord:
	mov	r6,dph
	mov	r7,dpl
	mov	dptr,#_ScalerGetDataPortWord_PARM_2
	movx	a,@dptr
	mov	r5,a			; v
	mov	dpl,r7
	mov	dph,r6
	movx	@dptr,a			; W(a,v)
	inc	dptr
	movx	a,@dptr			; hi = R(a+1)
	mov	r4,a
	mov	a,r5
	jb	_ScalerGetDataPortWord_PARM_3,00101$
	inc	a			; auto-increment: second index v+1
00101$:
	mov	dpl,r7
	mov	dph,r6
	movx	@dptr,a			; W(a,idx2)
	inc	dptr
	movx	a,@dptr			; lo = R(a+1)
	mov	dpl,a
	mov	dph,r4
	ret
	.area CSEG    (CODE)
	.area CONST   (CODE)
	.area XINIT   (CODE)
	.area CABS    (ABS,CODE)
