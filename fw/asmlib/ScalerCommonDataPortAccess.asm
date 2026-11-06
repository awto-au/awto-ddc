; Hand-written 8051 replacement for Realtek ScalerCommonDataPortAccess.c (SDCC mcs51 large, --big-endian), #11.
; Same ABI as the compiled C: arg1 in DPL/DPH, other args in static xdata/bit PARMs (BE: MSB at lowest address),
; 8-bit return in DPL. Same register-access order as the C; Enable/DisableAccessPort are no-ops, so inlined.
; Generic pointer (BE): +0 tag (0x00 xdata), +1 hi, +2 lo.
	.module ScalerCommonDataPortAccess
	.optsdcc -mmcs51 --model-large --big-endian
	.globl _ScalerEnableAccessPort_PARM_2
	.globl _ScalerEnableAccessPort
	.globl _ScalerDisableAccessPort
	.globl _ScalerSetDataPortByte_PARM_2
	.globl _ScalerSetDataPortByte_PARM_3
	.globl _ScalerSetDataPortByte
	.globl _ScalerGetDataPortByte_PARM_2
	.globl _ScalerGetDataPortByte_PARM_3
	.globl _ScalerGetDataPortByte_PARM_4
	.globl _ScalerGetDataPortByte_PARM_5
	.globl _ScalerGetDataPortByte
	.globl _ScalerSetDataPortBit_PARM_2
	.globl _ScalerSetDataPortBit_PARM_3
	.globl _ScalerSetDataPortBit_PARM_4
	.globl _ScalerSetDataPortBit
	.globl _ScalerGetDataPortBit_PARM_2
	.globl _ScalerGetDataPortBit_PARM_3
	.globl _ScalerGetDataPortBit
	.globl __gptrput
	ar0 = 0x00
	ar1 = 0x01
	ar2 = 0x02
	ar3 = 0x03
	ar4 = 0x04
	ar5 = 0x05
	ar6 = 0x06
	ar7 = 0x07
	.area BSEG    (BIT)
_ScalerGetDataPortByte_PARM_5:
	.ds 1
	.area XSEG    (XDATA)
_ScalerEnableAccessPort_PARM_2:
	.ds 1
_ScalerSetDataPortByte_PARM_2:
	.ds 1
_ScalerSetDataPortByte_PARM_3:
	.ds 1
_ScalerGetDataPortByte_PARM_2:
	.ds 1
_ScalerGetDataPortByte_PARM_3:
	.ds 2
_ScalerGetDataPortByte_PARM_4:
	.ds 3
_ScalerSetDataPortBit_PARM_2:
	.ds 1
_ScalerSetDataPortBit_PARM_3:
	.ds 1
_ScalerSetDataPortBit_PARM_4:
	.ds 1
_ScalerGetDataPortBit_PARM_2:
	.ds 1
_ScalerGetDataPortBit_PARM_3:
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
;	 function ScalerEnableAccessPort
_ScalerEnableAccessPort:
	mov	dptr,#_ScalerEnableAccessPort_PARM_2
	movx	a,@dptr
	mov	dpl,a
	ret
;	 function ScalerDisableAccessPort
_ScalerDisableAccessPort:
	ret
;	 function ScalerSetDataPortByte
; W(addr,v1); W(addr+1,v2)
_ScalerSetDataPortByte:
	mov	r6,dph
	mov	r7,dpl
	mov	dptr,#_ScalerSetDataPortByte_PARM_2
	movx	a,@dptr
	mov	r5,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	mov	dpl,r7
	mov	dph,r6
	mov	a,r5
	movx	@dptr,a
	inc	dptr
	mov	a,r4
	movx	@dptr,a
	ret
;	 function ScalerGetDataPortByte
; len==0: return; else per byte: W(addr, v [+i unless bAutoInc]); *p++ = R(addr+1)
_ScalerGetDataPortByte:
	mov	r6,dph
	mov	r7,dpl
	mov	dptr,#_ScalerGetDataPortByte_PARM_3
	movx	a,@dptr
	mov	r3,a
	inc	dptr
	movx	a,@dptr
	mov	r2,a
	orl	a,r3
	jnz	00101$
	ret
00101$:
	mov	dptr,#_ScalerGetDataPortByte_PARM_2
	movx	a,@dptr
	mov	r5,a
	mov	dptr,#_ScalerGetDataPortByte_PARM_4
	movx	a,@dptr
	mov	r0,a
	inc	dptr
	movx	a,@dptr
	mov	r1,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	mov	a,r0
	jnz	00110$			; not xdata: generic path
	cjne	r3,#0xFF,00102$
	sjmp	00110$			; len >= 0xFF00: djnz pair cannot count it
00102$:
	mov	a,r2			; r3:r2 -> r3 = hi + (lo != 0) for the djnz pair
	jz	00103$
	inc	r3
00103$:
	mov	dpl,r7
	mov	dph,r6
	mov	a,r5
	movx	@dptr,a
	inc	dptr
	movx	a,@dptr
	mov	dpl,r4
	mov	dph,r1
	movx	@dptr,a
	inc	dptr
	mov	r4,dpl
	mov	r1,dph
	jb	_ScalerGetDataPortByte_PARM_5,00104$
	inc	r5
00104$:
	djnz	r2,00103$
	djnz	r3,00103$
	ret
00110$:					; generic pointer, exact 16-bit count r3:r2
	mov	dpl,r7
	mov	dph,r6
	mov	a,r5
	movx	@dptr,a
	inc	dptr
	movx	a,@dptr
	mov	dpl,r4
	mov	dph,r1
	mov	b,r0
	push	ar0
	push	ar1
	push	ar2
	push	ar3
	push	ar4
	push	ar5
	push	ar6
	push	ar7
	lcall	__gptrput
	pop	ar7
	pop	ar6
	pop	ar5
	pop	ar4
	pop	ar3
	pop	ar2
	pop	ar1
	pop	ar0
	inc	r4
	cjne	r4,#0x00,00111$
	inc	r1
00111$:
	jb	_ScalerGetDataPortByte_PARM_5,00112$
	inc	r5
00112$:
	dec	r2
	cjne	r2,#0xFF,00113$
	dec	r3
00113$:
	mov	a,r2
	orl	a,r3
	jnz	00110$
	ret
;	 function ScalerSetDataPortBit
; W(addr,v); t = (R(addr+1) & and) | or; W(addr,v); W(addr+1,t)
_ScalerSetDataPortBit:
	mov	r6,dph
	mov	r7,dpl
	mov	dptr,#_ScalerSetDataPortBit_PARM_2
	movx	a,@dptr
	mov	r5,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	inc	dptr
	movx	a,@dptr
	mov	r3,a
	mov	dpl,r7
	mov	dph,r6
	mov	a,r5
	movx	@dptr,a
	inc	dptr
	movx	a,@dptr
	anl	a,r4
	orl	a,r3
	mov	r2,a
	mov	dpl,r7
	mov	dph,r6
	mov	a,r5
	movx	@dptr,a
	inc	dptr
	mov	a,r2
	movx	@dptr,a
	ret
;	 function ScalerGetDataPortBit
; W(addr,v); return R(addr+1) & and
_ScalerGetDataPortBit:
	mov	r6,dph
	mov	r7,dpl
	mov	dptr,#_ScalerGetDataPortBit_PARM_2
	movx	a,@dptr
	mov	r5,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	mov	dpl,r7
	mov	dph,r6
	mov	a,r5
	movx	@dptr,a
	inc	dptr
	movx	a,@dptr
	anl	a,r4
	mov	dpl,a
	ret
	.area CSEG    (CODE)
	.area CONST   (CODE)
	.area XINIT   (CODE)
	.area CABS    (ABS,CODE)
