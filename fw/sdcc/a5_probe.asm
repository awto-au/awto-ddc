; What the RL6449 DW8051 does with the reserved 8051 opcode 0xA5 (test cmd 0x21, fw/test/testcmd.c; asked by Dan via the sdcc session).
; _AwtoA5RunN: known registers, `.db 0xA5` + 1-byte markers (inc rN: a byte eaten by A5 = a missing increment), capture.
; Capture (17 B + 0x5A) at _g_pucAwtoA5Probe + 20 * N: R7..R0 (bank 0), DPH1, DPL1, DPH, DPL, DPS, SP, PSW, B, A.
; Caller: EA off; buf[80] / buf[81] = marker bytes DPTR0 / DPTR1 point at. Clobbers every register (Keil ABI: caller saves).
	.module	a5_probe
	.globl	_AwtoA5Run0, _AwtoA5Run1, _AwtoA5Run2, _AwtoA5Run3
	.globl	_g_pucAwtoA5Probe

	DPL1 = 0x84
	DPH1 = 0x85
	DPS = 0x86
	STRIDE = 20
	DONE = 0x5A
	MARK0 = 80			; buffer offsets of the bytes DPTR0 / DPTR1 point at
	MARK1 = 81

	.macro	SETUP
	mov	DPS,#1
	mov	dptr,#(_g_pucAwtoA5Probe + MARK1)
	mov	DPS,#0
	mov	dptr,#(_g_pucAwtoA5Probe + MARK0)
	mov	b,#0xB0
	mov	0x00,#0x10
	mov	0x01,#0x11
	mov	0x02,#0x12
	mov	0x03,#0x13
	mov	0x04,#0x14
	mov	0x05,#0x15
	mov	0x06,#0x16
	mov	0x07,#0x17
	mov	psw,#0x00
	mov	a,#0xA0
	.endm

	.macro	CAPTURE	n
	push	acc
	push	b
	push	psw
	mov	a,sp
	push	acc
	push	DPS
	push	dpl
	push	dph
	push	DPL1
	push	DPH1
	push	0x00
	push	0x01
	push	0x02
	push	0x03
	push	0x04
	push	0x05
	push	0x06
	push	0x07
	mov	DPS,#0
	mov	psw,#0x00
	mov	dptr,#(_g_pucAwtoA5Probe + STRIDE * n)
	mov	r0,#17
1$:	pop	acc
	movx	@dptr,a
	inc	dptr
	djnz	r0,1$
	mov	a,#DONE
	movx	@dptr,a
	ret
	.endm

	.area	CSEG	(CODE)
_AwtoA5Run0:				; bytes A5 consumes
	SETUP
	.db	0xA5
	inc	r2
	inc	r3
	inc	r4
	inc	r5
	CAPTURE	0

_AwtoA5Run1:				; A5 before inc dptr (DS390-style DPTR prefix?)
	SETUP
	.db	0xA5
	inc	dptr
	inc	r2
	inc	r3
	inc	r4
	CAPTURE	1

_AwtoA5Run2:				; A5 before mov dptr,#imm16
	SETUP
	.db	0xA5
	mov	dptr,#0x9ABC
	inc	r2
	inc	r3
	inc	r4
	CAPTURE	2

_AwtoA5Run3:				; A5 before movx a,@dptr (A = buf[80] via DPTR0 or buf[81] via DPTR1)
	SETUP
	.db	0xA5
	movx	a,@dptr
	inc	r2
	inc	r3
	inc	r4
	CAPTURE	3
