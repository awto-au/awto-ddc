; ___sdcc_external_startup for RL6449: runs before SDCC's XINIT copy and RAM clear.
; At reset XRAM, XFR and bank switching are off (MCU_FFFC); SDCC large model needs XRAM for params/locals.
; Same writes as ScalerMcuInitial() / Realtek STARTUP.a51 speed-up block (Kernel/Common, ScalerMcu.c) (#8).
; #29 / #138: reset-vector snapshot (20 B no-init XDATA at 0xF69C, RL6449_Project.h g_stAwtoSnap) before the WDT write.
	.module	awto_startup
	.globl	___sdcc_external_startup

	.macro	SFRCP	sfr
	mov	a,sfr
	movx	@dptr,a
	inc	dptr
	.endm

	.macro	XFRCP	src, dst
	mov	dptr,#src
	movx	a,@dptr
	mov	dptr,#dst
	movx	@dptr,a
	.endm

	.area	CSEG	(CODE)
___sdcc_external_startup:
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
	mov	dptr,#0xF69E		; snapshot: SFRs EICON PCON EXIF CKCON IE EIE IP EIP
	SFRCP	0xD8
	SFRCP	0x87
	SFRCP	0x91
	SFRCP	0x8E
	SFRCP	0xA8
	SFRCP	0xE8
	SFRCP	0xB8
	SFRCP	0xF8
	XFRCP	0xFFEA, 0xF6A6		; XFRs FFEA FFEB FFAA..FFAD FFE0 FFED FFEE, P0_01 HOST_CTRL
	XFRCP	0xFFEB, 0xF6A7
	XFRCP	0xFFAA, 0xF6A8
	XFRCP	0xFFAB, 0xF6A9
	XFRCP	0xFFAC, 0xF6AA
	XFRCP	0xFFAD, 0xF6AB
	XFRCP	0xFFE0, 0xF6AC
	XFRCP	0xFFED, 0xF6AD
	XFRCP	0xFFEE, 0xF6AE
	XFRCP	0x0001, 0xF6AF
	mov	dptr,#0xF69C
	mov	a,#0x52			; 'R' 'S': snapshot valid
	movx	@dptr,a
	inc	dptr
	mov	a,#0x53
	movx	@dptr,a
	mov	dptr,#0xFFEA		; WDT clear + CNT1 N = 8 (~4.7 s; reset default N = 1) at once (#138). On from reset:
	movx	a,@dptr			; FFEA[7] / FFE9[7] / FF3A[6] ORed, all 1; never cleared (docs/watchdog.md)
	orl	a,#0xC7
	movx	@dptr,a
	mov	dpl,#0			; 0 = let SDCC initialise RAM
	ret
