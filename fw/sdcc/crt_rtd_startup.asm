; ___sdcc_external_startup for RL6449: runs before SDCC's XINIT copy and RAM clear.
; At reset XRAM, XFR and bank switching are off (MCU_FFFC); SDCC large model needs XRAM for params/locals.
; Same writes as ScalerMcuInitial() / Realtek STARTUP.a51 speed-up block (Kernel/Common, ScalerMcu.c) (#8).
	.module	awto_startup
	.globl	___sdcc_external_startup

	.area	CSEG	(CODE)
___sdcc_external_startup:
	mov	dptr,#0xFFEA		; WDT clear + CNT1 N = 8 (~4.7 s; reset default N = 1) at once (#138). On from reset:
				; FFEA[7] / FFE9[7] / FF3A[6] ORed, all 1; never cleared (docs/watchdog.md)
	movx	a,@dptr
	orl	a,#0xC7
	movx	@dptr,a
	mov	dptr,#0xFFFC		; MCU_FFFC_BANK_SWICH_CONTROL: remap, XRAM+XFR, Pbank_switch, banking on
	movx	a,@dptr
	orl	a,#0x1F
	movx	@dptr,a
	clr	a
	inc	dptr			; MCU_FFFD_XDATA_BANK_START = 0
	movx	@dptr,a
	inc	dptr			; MCU_FFFE_XDATA_BANK_SEL = 0
	movx	@dptr,a
	inc	dptr			; MCU_FFFF_PBANK_SWITCH = bank 0 (= _FLASH_PARTITION_INIT_BANK)
	movx	@dptr,a
	mov	dpl,#0			; 0 = let SDCC initialise RAM
	ret
