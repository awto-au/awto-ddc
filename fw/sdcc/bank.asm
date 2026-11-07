; Cross-bank call trampolines for RL6449 (whole 64 KB banked, bank reg XDATA 0xFFFF). Lives in common.
; Stub per target (scripts/sdcc_bank.py, 8 B): mov r0,#bank; mov dptr,#target; ljmp __bs_call.
; Keil ABI (--sdcccall 3, awto-sdcc#7): args live in R1-R7, returns in R1-R7/C. Free scratch: R0, A, B, DPTR, C on entry;
; R0, A, B, DPTR on return. R1-R7 and C (bit return) are never touched. Interrupts: ISRs push what they use (bank 0 only, #8).
; Like Keil ?B_SWITCH: the callee returns into the caller bank's restore entry (2 B on the stack per level).
	.module	awto_bank
	.globl	__bs_call
	.globl	__bs_cur
	.globl	__bs_ret		; for scripts/fw_sim.py breakpoints
	.globl	__bs_keil		; marker: images with these stubs use the Keil register ABI (scripts/fw_sim.py)
	.globl	__bs_call_sw, __bs_ret_sw	; just after the 0xFFFF write (A = new bank): fw_sim switches here

	.area	DSEG	(DATA)
__bs_cur:	.ds	1		; current bank shadow; written before 0xFFFF so an ISR restores the target bank

	.area	CSEG	(CODE)
__bs_keil = .
__bs_call:				; r0 = bank, dptr = target (set by the stub)
	mov	a,__bs_cur		; push &__bs_rtab[cur] (4 B per entry): target's ret -> restore entry of the caller's bank
	rl	a
	rl	a
	add	a,#__bs_rtab
	push	acc
	clr	a
	addc	a,#(__bs_rtab >> 8)
	push	acc
	push	dpl			; our ret -> target (lo, hi)
	push	dph
	mov	__bs_cur,r0		; written before 0xFFFF so an ISR restores the target bank
	mov	dptr,#0xFFFF
	mov	a,r0
	movx	@dptr,a			; bank switched; this code is identical in every bank
__bs_call_sw:
	ret

__bs_rtab:				; entry k: r1 = k, then restore (banks 0-15)
	mov	a,#0
	sjmp	__bs_ret
	mov	a,#1
	sjmp	__bs_ret
	mov	a,#2
	sjmp	__bs_ret
	mov	a,#3
	sjmp	__bs_ret
	mov	a,#4
	sjmp	__bs_ret
	mov	a,#5
	sjmp	__bs_ret
	mov	a,#6
	sjmp	__bs_ret
	mov	a,#7
	sjmp	__bs_ret
	mov	a,#8
	sjmp	__bs_ret
	mov	a,#9
	sjmp	__bs_ret
	mov	a,#10
	sjmp	__bs_ret
	mov	a,#11
	sjmp	__bs_ret
	mov	a,#12
	sjmp	__bs_ret
	mov	a,#13
	sjmp	__bs_ret
	mov	a,#14
	sjmp	__bs_ret
	mov	a,#15
	sjmp	__bs_ret
__bs_ret:				; a = caller bank; returns in R1-R7/C untouched (mov/movx leave C alone)
	mov	__bs_cur,a
	mov	dptr,#0xFFFF
	movx	@dptr,a
__bs_ret_sw:
	ret
