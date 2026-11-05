; Cross-bank call trampolines for RL6449 (whole 64 KB banked, bank reg XDATA 0xFFFF). Lives in common.
; Stub per target (scripts/sdcc_bank.py): r0/r1 = target lo/hi, r2 = bank, ljmp __bs_call.
; Args DPL/DPH/B/A and returns DPL/DPH/B/A/C preserved; r0-r6 are caller-saved in SDCC (bank 0 only, #8).
; Like Keil ?B_SWITCH: the callee returns into the caller bank's restore entry (2 B on the stack per level).
	.module	awto_bank
	.globl	__bs_call
	.globl	__bs_cur
	.globl	__bs_ret		; for scripts/fw_sim.py breakpoints
	.globl	__bs_call_sw, __bs_ret_sw	; just after the 0xFFFF write (A = new bank): fw_sim switches here
	ar0 = 0x00
	ar1 = 0x01
	ar3 = 0x03

	.area	DSEG	(DATA)
__bs_cur:	.ds	1		; current bank shadow; written before 0xFFFF so an ISR restores the target bank

	.area	CSEG	(CODE)
__bs_call:
	mov	r4,a			; save A/DPTR in regs: no transient stack use
	mov	r5,dpl
	mov	r6,dph
	mov	a,__bs_cur		; push &__bs_rtab[cur] (4 B per entry)
	rl	a
	rl	a
	add	a,#__bs_rtab
	mov	r3,a
	clr	a
	addc	a,#(__bs_rtab >> 8)
	push	ar3
	push	acc			; target's ret -> restore entry of the caller's bank
	push	ar0
	push	ar1			; our ret -> target
	mov	__bs_cur,r2
	mov	dptr,#0xFFFF
	mov	a,r2
	movx	@dptr,a			; bank switched; this code is identical in every bank
__bs_call_sw:
	mov	dpl,r5
	mov	dph,r6
	mov	a,r4
	ret

__bs_rtab:				; entry k: r1 = k, then restore (banks 0-15)
	mov	r1,#0
	sjmp	__bs_ret
	mov	r1,#1
	sjmp	__bs_ret
	mov	r1,#2
	sjmp	__bs_ret
	mov	r1,#3
	sjmp	__bs_ret
	mov	r1,#4
	sjmp	__bs_ret
	mov	r1,#5
	sjmp	__bs_ret
	mov	r1,#6
	sjmp	__bs_ret
	mov	r1,#7
	sjmp	__bs_ret
	mov	r1,#8
	sjmp	__bs_ret
	mov	r1,#9
	sjmp	__bs_ret
	mov	r1,#10
	sjmp	__bs_ret
	mov	r1,#11
	sjmp	__bs_ret
	mov	r1,#12
	sjmp	__bs_ret
	mov	r1,#13
	sjmp	__bs_ret
	mov	r1,#14
	sjmp	__bs_ret
	mov	r1,#15
	sjmp	__bs_ret
__bs_ret:
	mov	r0,a			; A = return byte; mov leaves C (bit return) untouched
	mov	__bs_cur,r1
	mov	r2,dpl
	mov	r3,dph
	mov	dptr,#0xFFFF
	mov	a,r1
	movx	@dptr,a
__bs_ret_sw:
	mov	dpl,r2
	mov	dph,r3
	mov	a,r0
	ret
