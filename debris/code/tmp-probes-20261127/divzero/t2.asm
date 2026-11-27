;--------------------------------------------------------
; File Created by SDCC : free open source ISO C Compiler
; Version 4.5.0 #15242 (Linux)
;--------------------------------------------------------
	.module t2
	
	.optsdcc -mmcs51 --model-large
;--------------------------------------------------------
; Public variables in this module
;--------------------------------------------------------
	.globl _I
	.globl _L
	.globl _main
	.globl _done
	.globl _fails
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
	.ds 8
;--------------------------------------------------------
; internal ram data
;--------------------------------------------------------
	.area DSEG    (DATA)
_main_sloc0_1_0:
	.ds 4
;--------------------------------------------------------
; overlayable items in internal ram
;--------------------------------------------------------
;--------------------------------------------------------
; Stack segment in internal ram
;--------------------------------------------------------
	.area SSEG
__start__stack:
	.ds	1

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
_fails::
	.ds 1
_done::
	.ds 1
_main_a_30000_4:
	.ds 4
_main_b_30000_4:
	.ds 4
_main_a_30000_6:
	.ds 2
_main_b_30000_6:
	.ds 2
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
; interrupt vector
;--------------------------------------------------------
	.area HOME    (CODE)
__interrupt_vect:
	ljmp	__sdcc_gsinit_startup
; restartable atomic support routines
	.ds	5
sdcc_atomic_exchange_rollback_start::
	nop
	nop
sdcc_atomic_exchange_pdata_impl:
	movx	a, @r0
	mov	r3, a
	mov	a, r2
	movx	@r0, a
	sjmp	sdcc_atomic_exchange_exit
	nop
	nop
sdcc_atomic_exchange_xdata_impl:
	movx	a, @dptr
	mov	r3, a
	mov	a, r2
	movx	@dptr, a
	sjmp	sdcc_atomic_exchange_exit
sdcc_atomic_compare_exchange_idata_impl:
	mov	a, @r0
	cjne	a, ar2, .+#5
	mov	a, r3
	mov	@r0, a
	ret
	nop
sdcc_atomic_compare_exchange_pdata_impl:
	movx	a, @r0
	cjne	a, ar2, .+#5
	mov	a, r3
	movx	@r0, a
	ret
	nop
sdcc_atomic_compare_exchange_xdata_impl:
	movx	a, @dptr
	cjne	a, ar2, .+#5
	mov	a, r3
	movx	@dptr, a
	ret
sdcc_atomic_exchange_rollback_end::

sdcc_atomic_exchange_gptr_impl::
	jnb	b.6, sdcc_atomic_exchange_xdata_impl
	mov	r0, dpl
	jb	b.5, sdcc_atomic_exchange_pdata_impl
sdcc_atomic_exchange_idata_impl:
	mov	a, r2
	xch	a, @r0
	mov	dpl, a
	ret
sdcc_atomic_exchange_exit:
	mov	dpl, r3
	ret
sdcc_atomic_compare_exchange_gptr_impl::
	jnb	b.6, sdcc_atomic_compare_exchange_xdata_impl
	mov	r0, dpl
	jb	b.5, sdcc_atomic_compare_exchange_pdata_impl
	sjmp	sdcc_atomic_compare_exchange_idata_impl
;--------------------------------------------------------
; global & static initialisations
;--------------------------------------------------------
	.area HOME    (CODE)
	.area GSINIT  (CODE)
	.area GSFINAL (CODE)
	.area GSINIT  (CODE)
	.globl __sdcc_gsinit_startup
	.globl __sdcc_program_startup
	.globl __start__stack
	.globl __mcs51_genXINIT
	.globl __mcs51_genXRAMCLEAR
	.globl __mcs51_genRAMCLEAR
	.area GSFINAL (CODE)
	ljmp	__sdcc_program_startup
;--------------------------------------------------------
; Home
;--------------------------------------------------------
	.area HOME    (CODE)
	.area HOME    (CODE)
__sdcc_program_startup:
	ljmp	_main
;	return from main will return to caller
;--------------------------------------------------------
; code
;--------------------------------------------------------
	.area CSEG    (CODE)
;------------------------------------------------------------
;Allocation info for local variables in function 'main'
;------------------------------------------------------------
;sloc0         Allocated with name '_main_sloc0_1_0'
;k             Allocated with name '_main_k_10000_2'
;a             Allocated with name '_main_a_30000_4'
;b             Allocated with name '_main_b_30000_4'
;a             Allocated with name '_main_a_30000_6'
;b             Allocated with name '_main_b_30000_6'
;------------------------------------------------------------
;	/mnt/2tb/git/awto-ddc/tmp/divzero/t2.c:4: void main(void){unsigned char k; fails=0;
;	-----------------------------------------
;	 function main
;	-----------------------------------------
_main:
	ar7 = 0x07
	ar6 = 0x06
	ar5 = 0x05
	ar4 = 0x04
	ar3 = 0x03
	ar2 = 0x02
	ar1 = 0x01
	ar0 = 0x00
	mov	dptr,#_fails
	clr	a
	movx	@dptr,a
;	/mnt/2tb/git/awto-ddc/tmp/divzero/t2.c:5: for(k=0;k<sizeof(L)/sizeof(L[0]);k++){volatile unsigned long a=L[k][0],b=L[k][1]; if(a%b!=L[k][2]) fails++;}
	mov	r7,a
00110$:
	mov	a,r7
	mov	b,#0x0c
	mul	ab
	add	a, #_L
	mov	r5,a
	mov	a,#(_L >> 8)
	addc	a, b
	mov	r6,a
	mov	dpl,r5
	mov	dph,r6
	clr	a
	movc	a,@a+dptr
	mov	r1,a
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r2,a
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r3,a
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r4,a
	mov	dptr,#_main_a_30000_4
	mov	a,r1
	movx	@dptr,a
	mov	a,r2
	inc	dptr
	movx	@dptr,a
	mov	a,r3
	inc	dptr
	movx	@dptr,a
	mov	a,r4
	inc	dptr
	movx	@dptr,a
	mov	dpl,r5
	mov	dph,r6
	inc	dptr
	inc	dptr
	inc	dptr
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r1,a
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r2,a
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r3,a
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r4,a
	mov	dptr,#_main_b_30000_4
	mov	a,r1
	movx	@dptr,a
	mov	a,r2
	inc	dptr
	movx	@dptr,a
	mov	a,r3
	inc	dptr
	movx	@dptr,a
	mov	a,r4
	inc	dptr
	movx	@dptr,a
	mov	dptr,#_main_b_30000_4
	movx	a,@dptr
	mov	_main_sloc0_1_0,a
	inc	dptr
	movx	a,@dptr
	mov	(_main_sloc0_1_0 + 1),a
	inc	dptr
	movx	a,@dptr
	mov	(_main_sloc0_1_0 + 2),a
	inc	dptr
	movx	a,@dptr
	mov	(_main_sloc0_1_0 + 3),a
	push	ar7
	mov	dptr,#_main_a_30000_4
	movx	a,@dptr
	mov	r0,a
	inc	dptr
	movx	a,@dptr
	mov	r3,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	inc	dptr
	movx	a,@dptr
	mov	r7,a
	mov	dptr,#__modulong_PARM_2
	mov	a,_main_sloc0_1_0
	movx	@dptr,a
	mov	a,(_main_sloc0_1_0 + 1)
	inc	dptr
	movx	@dptr,a
	mov	a,(_main_sloc0_1_0 + 2)
	inc	dptr
	movx	@dptr,a
	mov	a,(_main_sloc0_1_0 + 3)
	inc	dptr
	movx	@dptr,a
	mov	dpl, r0
	mov	dph, r3
	mov	b, r4
	mov	a, r7
	push	ar6
	push	ar5
	lcall	__modulong
	mov	r2, dpl
	mov	r3, dph
	mov	r4, b
	mov	r7, a
	pop	ar5
	pop	ar6
	mov	a,#0x08
	add	a, r5
	mov	dpl,a
	clr	a
	addc	a, r6
	mov	dph,a
	clr	a
	movc	a,@a+dptr
	mov	r0,a
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r1,a
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r5,a
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r6,a
	mov	a,r2
	cjne	a,ar0,00160$
	mov	a,r3
	cjne	a,ar1,00160$
	mov	a,r4
	cjne	a,ar5,00160$
	mov	a,r7
	cjne	a,ar6,00160$
	pop	ar7
	sjmp	00111$
00160$:
	pop	ar7
	mov	dptr,#_fails
	movx	a,@dptr
	inc	a
	movx	@dptr,a
00111$:
	inc	r7
	cjne	r7,#0x30,00161$
00161$:
	jnc	00162$
	ljmp	00110$
00162$:
;	/mnt/2tb/git/awto-ddc/tmp/divzero/t2.c:6: for(k=0;k<sizeof(I)/sizeof(I[0]);k++){volatile unsigned int a=I[k][0],b=I[k][1]; if(a%b!=I[k][2]) fails+=0x10;}
	mov	r7,#0x00
00112$:
	mov	a,r7
	mov	b,#0x06
	mul	ab
	add	a, #_I
	mov	r5,a
	mov	a,#(_I >> 8)
	addc	a, b
	mov	r6,a
	mov	dpl,r5
	mov	dph,r6
	clr	a
	movc	a,@a+dptr
	mov	r3,a
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r4,a
	mov	dptr,#_main_a_30000_6
	mov	a,r3
	movx	@dptr,a
	mov	a,r4
	inc	dptr
	movx	@dptr,a
	mov	dpl,r5
	mov	dph,r6
	inc	dptr
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r3,a
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r4,a
	mov	dptr,#_main_b_30000_6
	mov	a,r3
	movx	@dptr,a
	mov	a,r4
	inc	dptr
	movx	@dptr,a
	mov	dptr,#_main_b_30000_6
	movx	a,@dptr
	mov	r3,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	mov	dptr,#_main_a_30000_6
	movx	a,@dptr
	mov	r1,a
	inc	dptr
	movx	a,@dptr
	mov	r2,a
	mov	dptr,#__moduint_PARM_2
	mov	a,r3
	movx	@dptr,a
	mov	a,r4
	inc	dptr
	movx	@dptr,a
	mov	dpl, r1
	mov	dph, r2
	push	ar7
	push	ar6
	push	ar5
	lcall	__moduint
	mov	r3, dpl
	mov	r4, dph
	pop	ar5
	pop	ar6
	pop	ar7
	mov	dpl,r5
	mov	dph,r6
	inc	dptr
	inc	dptr
	inc	dptr
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r5,a
	inc	dptr
	clr	a
	movc	a,@a+dptr
	mov	r6,a
	mov	a,r3
	cjne	a,ar5,00163$
	mov	a,r4
	cjne	a,ar6,00163$
	sjmp	00113$
00163$:
	mov	dptr,#_fails
	movx	a,@dptr
	add	a,#0x10
	movx	@dptr,a
00113$:
	inc	r7
	cjne	r7,#0x23,00164$
00164$:
	jnc	00165$
	ljmp	00112$
00165$:
;	/mnt/2tb/git/awto-ddc/tmp/divzero/t2.c:7: done=0xA5; while(1);}
	mov	dptr,#_done
	mov	a,#0xa5
	movx	@dptr,a
00108$:
	sjmp	00108$
	.area CSEG    (CODE)
	.area CONST   (CODE)
	.area CONST   (CODE)
_L:
	.byte #0x78, #0x56, #0x34, #0x12	; 305419896
	.byte #0x00, #0x00, #0x00, #0x00	; 0
	.byte #0x78, #0x56, #0x34, #0x12	; 305419896
	.byte #0x00, #0x00, #0x00, #0x00	; 0
	.byte #0x05, #0x00, #0x00, #0x00	; 5
	.byte #0x00, #0x00, #0x00, #0x00	; 0
	.byte #0xff, #0xff, #0xff, #0xff	; 4294967295
	.byte #0x01, #0x00, #0x00, #0x00	; 1
	.byte #0x00, #0x00, #0x00, #0x00	; 0
	.byte #0xff, #0xff, #0xff, #0xff	; 4294967295
	.byte #0xff, #0xff, #0xff, #0xff	; 4294967295
	.byte #0x00, #0x00, #0x00, #0x00	; 0
	.byte #0xff, #0xff, #0xff, #0xff	; 4294967295
	.byte #0x01, #0x00, #0x00, #0x80	; 2147483649
	.byte #0xfe, #0xff, #0xff, #0x7f	; 2147483646
	.byte #0xfe, #0xff, #0xff, #0xff	; 4294967294
	.byte #0xff, #0xff, #0xff, #0xff	; 4294967295
	.byte #0xfe, #0xff, #0xff, #0xff	; 4294967294
	.byte #0x00, #0x00, #0x00, #0x80	; 2147483648
	.byte #0x01, #0x00, #0x00, #0x80	; 2147483649
	.byte #0x00, #0x00, #0x00, #0x80	; 2147483648
	.byte #0x64, #0x00, #0x00, #0x00	; 100
	.byte #0x07, #0x00, #0x00, #0x00	; 7
	.byte #0x02, #0x00, #0x00, #0x00	; 2
	.byte #0xf5, #0xb1, #0x65, #0x22	; 577090037
	.byte #0x6f, #0xb5, #0x78, #0x6c	; 1819850095
	.byte #0xf5, #0xb1, #0x65, #0x22	; 577090037
	.byte #0x30, #0x3e, #0x61, #0xcd	; 3445702192
	.byte #0x02, #0x00, #0x00, #0x00	; 2
	.byte #0x00, #0x00, #0x00, #0x00	; 0
	.byte #0x89, #0xeb, #0x2f, #0x1e	; 506456969
	.byte #0x6f, #0xce, #0xc2, #0x00	; 12766831
	.byte #0xa0, #0x78, #0x82, #0x00	; 8550560
	.byte #0xa3, #0xd8, #0x11, #0x73	; 1930549411
	.byte #0xcc, #0xce, #0xa6, #0x00	; 10931916
	.byte #0x63, #0xac, #0x63, #0x00	; 6532195
	.byte #0x96, #0x76, #0x2e, #0x61	; 1630434966
	.byte #0x18, #0x00, #0x00, #0x00	; 24
	.byte #0x06, #0x00, #0x00, #0x00	; 6
	.byte #0x82, #0x2c, #0xe4, #0x7c	; 2095328386
	.byte #0x07, #0x00, #0x00, #0x00	; 7
	.byte #0x04, #0x00, #0x00, #0x00	; 4
	.byte #0xb2, #0xb3, #0xf4, #0xd5	; 3589583794
	.byte #0xd2, #0xc9, #0x6e, #0x00	; 7260626
	.byte #0x76, #0x40, #0x2b, #0x00	; 2834550
	.byte #0x76, #0x0e, #0x81, #0x9b	; 2608926326
	.byte #0x05, #0x00, #0x00, #0x00	; 5
	.byte #0x01, #0x00, #0x00, #0x00	; 1
	.byte #0x2d, #0xe5, #0x04, #0x72	; 1912923437
	.byte #0xb6, #0xb8, #0x00, #0x00	; 47286
	.byte #0xe9, #0x3c, #0x00, #0x00	; 15593
	.byte #0x35, #0x7e, #0x44, #0xcd	; 3443818037
	.byte #0x97, #0x00, #0x00, #0x00	; 151
	.byte #0x92, #0x00, #0x00, #0x00	; 146
	.byte #0xa2, #0x42, #0xfd, #0xf1	; 4059906722
	.byte #0x07, #0x00, #0x00, #0x00	; 7
	.byte #0x04, #0x00, #0x00, #0x00	; 4
	.byte #0x93, #0x11, #0x43, #0x51	; 1363349907
	.byte #0x01, #0x00, #0x00, #0x00	; 1
	.byte #0x00, #0x00, #0x00, #0x00	; 0
	.byte #0xb9, #0x9e, #0x83, #0x06	; 109289145
	.byte #0x1e, #0x02, #0x9a, #0x8a	; 2325348894
	.byte #0xb9, #0x9e, #0x83, #0x06	; 109289145
	.byte #0x3f, #0x41, #0x5b, #0x02	; 39534911
	.byte #0x67, #0xbd, #0xaf, #0x00	; 11517287
	.byte #0x0a, #0x09, #0x4c, #0x00	; 4983050
	.byte #0xdf, #0x0e, #0x73, #0x37	; 930287327
	.byte #0x79, #0xd1, #0xb9, #0x00	; 12177785
	.byte #0xf3, #0xde, #0x48, #0x00	; 4775667
	.byte #0x87, #0x37, #0x6f, #0x07	; 124729223
	.byte #0x7e, #0x64, #0x60, #0x1c	; 476079230
	.byte #0x87, #0x37, #0x6f, #0x07	; 124729223
	.byte #0x8f, #0xe8, #0x81, #0xc3	; 3280070799
	.byte #0x3f, #0x6d, #0xf0, #0x00	; 15756607
	.byte #0x5f, #0x25, #0x29, #0x00	; 2696543
	.byte #0x14, #0x8d, #0xed, #0x7e	; 2129497364
	.byte #0x1c, #0xb6, #0xd5, #0x1d	; 500545052
	.byte #0xa4, #0xb4, #0x96, #0x07	; 127317156
	.byte #0x80, #0xd2, #0x7f, #0x58	; 1484771968
	.byte #0xad, #0x00, #0x00, #0x00	; 173
	.byte #0xa0, #0x00, #0x00, #0x00	; 160
	.byte #0xa9, #0x08, #0x02, #0x38	; 939657385
	.byte #0x4a, #0xc6, #0xf3, #0x00	; 15976010
	.byte #0xe5, #0x1b, #0xc7, #0x00	; 13048805
	.byte #0xaa, #0x20, #0x2f, #0x4a	; 1244602538
	.byte #0x03, #0x00, #0x00, #0x00	; 3
	.byte #0x02, #0x00, #0x00, #0x00	; 2
	.byte #0x9e, #0x82, #0x6b, #0xd6	; 3597370014
	.byte #0x5a, #0x46, #0x0a, #0x76	; 1980384858
	.byte #0x44, #0x3c, #0x61, #0x60	; 1616985156
	.byte #0x53, #0x67, #0x6d, #0xa4	; 2758633299
	.byte #0x01, #0x00, #0x00, #0x00	; 1
	.byte #0x00, #0x00, #0x00, #0x00	; 0
	.byte #0x9a, #0x45, #0x1d, #0xa1	; 2703050138
	.byte #0xbd, #0x74, #0x25, #0xdc	; 3693442237
	.byte #0x9a, #0x45, #0x1d, #0xa1	; 2703050138
	.byte #0xb0, #0x3d, #0xe0, #0x4b	; 1272987056
	.byte #0x05, #0x00, #0x00, #0x00	; 5
	.byte #0x01, #0x00, #0x00, #0x00	; 1
	.byte #0xf6, #0x82, #0x2b, #0x55	; 1428914934
	.byte #0x4e, #0x0f, #0x27, #0xf9	; 4180086606
	.byte #0xf6, #0x82, #0x2b, #0x55	; 1428914934
	.byte #0xf7, #0xa9, #0x10, #0xb6	; 3054545399
	.byte #0xfe, #0x48, #0xdd, #0x77	; 2010990846
	.byte #0xf9, #0x60, #0x33, #0x3e	; 1043554553
	.byte #0xae, #0x17, #0x9b, #0xf7	; 4154136494
	.byte #0xc1, #0xf9, #0x81, #0x00	; 8518081
	.byte #0x87, #0xf9, #0x58, #0x00	; 5831047
	.byte #0x0d, #0x38, #0x7d, #0xd4	; 3564976141
	.byte #0xf5, #0xfd, #0x99, #0x30	; 815398389
	.byte #0x39, #0x40, #0x15, #0x12	; 303382585
	.byte #0x1d, #0x8f, #0xa9, #0x4d	; 1302957853
	.byte #0x6b, #0x96, #0x00, #0x00	; 38507
	.byte #0xb9, #0x88, #0x00, #0x00	; 35001
	.byte #0x68, #0x1c, #0x34, #0xf9	; 4180941928
	.byte #0x64, #0xa0, #0xd8, #0x00	; 14196836
	.byte #0x90, #0xe9, #0x6b, #0x00	; 7072144
	.byte #0xa5, #0xb4, #0xdf, #0xf0	; 4041192613
	.byte #0x5e, #0x69, #0x59, #0x32	; 844720478
	.byte #0x2d, #0x0f, #0x7a, #0x27	; 662310701
	.byte #0x19, #0xda, #0xc8, #0x96	; 2529745433
	.byte #0x03, #0x00, #0x00, #0x00	; 3
	.byte #0x02, #0x00, #0x00, #0x00	; 2
	.byte #0xe3, #0x34, #0x24, #0x3e	; 1042560227
	.byte #0x58, #0xaf, #0x22, #0xcc	; 3424825176
	.byte #0xe3, #0x34, #0x24, #0x3e	; 1042560227
	.byte #0xbd, #0x6c, #0x7f, #0x67	; 1736404157
	.byte #0xa1, #0x2c, #0xaa, #0x00	; 11152545
	.byte #0x42, #0x67, #0x76, #0x00	; 7759682
	.byte #0x98, #0x36, #0x4a, #0x2c	; 743061144
	.byte #0x7e, #0x8c, #0x00, #0x00	; 35966
	.byte #0x00, #0x0e, #0x00, #0x00	; 3584
	.byte #0xd7, #0xb9, #0xfa, #0xe1	; 3791305175
	.byte #0xd8, #0x4b, #0x9d, #0xc6	; 3332197336
	.byte #0xff, #0x6d, #0x5d, #0x1b	; 459107839
	.byte #0x6b, #0x1a, #0xab, #0xac	; 2896894571
	.byte #0x8f, #0x89, #0xec, #0x5f	; 1609337231
	.byte #0xdc, #0x90, #0xbe, #0x4c	; 1287557340
	.byte #0x79, #0xbd, #0x22, #0x16	; 371375481
	.byte #0x08, #0xec, #0xa9, #0x00	; 11136008
	.byte #0x71, #0x50, #0x3b, #0x00	; 3887217
	.byte #0x15, #0x3d, #0x28, #0x82	; 2183675157
	.byte #0x06, #0x00, #0x00, #0x00	; 6
	.byte #0x03, #0x00, #0x00, #0x00	; 3
	.area CSEG    (CODE)
	.area CONST   (CODE)
_I:
	.byte #0x34, #0x12	; 4660
	.byte #0x00, #0x00	; 0
	.byte #0x34, #0x12	; 4660
	.byte #0xff, #0xff	; 65535
	.byte #0x01, #0x80	; 32769
	.byte #0xfe, #0x7f	; 32766
	.byte #0xff, #0xff	; 65535
	.byte #0xff, #0xff	; 65535
	.byte #0x00, #0x00	; 0
	.byte #0xfe, #0xff	; 65534
	.byte #0xff, #0xff	; 65535
	.byte #0xfe, #0xff	; 65534
	.byte #0x64, #0x00	; 100
	.byte #0x07, #0x00	; 7
	.byte #0x02, #0x00	; 2
	.byte #0xe8, #0x29	; 10728
	.byte #0xda, #0x5e	; 24282
	.byte #0xe8, #0x29	; 10728
	.byte #0x5c, #0x7d	; 32092
	.byte #0x03, #0x00	; 3
	.byte #0x01, #0x00	; 1
	.byte #0x21, #0x0b	; 2849
	.byte #0x08, #0x5a	; 23048
	.byte #0x21, #0x0b	; 2849
	.byte #0x2a, #0xd9	; 55594
	.byte #0xac, #0xa5	; 42412
	.byte #0x7e, #0x33	; 13182
	.byte #0x9c, #0x2b	; 11164
	.byte #0x80, #0x00	; 128
	.byte #0x1c, #0x00	; 28
	.byte #0x18, #0x3a	; 14872
	.byte #0x06, #0x00	; 6
	.byte #0x04, #0x00	; 4
	.byte #0x13, #0x33	; 13075
	.byte #0x67, #0x00	; 103
	.byte #0x61, #0x00	; 97
	.byte #0x86, #0x83	; 33670
	.byte #0xea, #0x79	; 31210
	.byte #0x9c, #0x09	; 2460
	.byte #0xf3, #0xd8	; 55539
	.byte #0xc4, #0x3a	; 15044
	.byte #0xa7, #0x28	; 10407
	.byte #0xe5, #0xe8	; 59621
	.byte #0x61, #0x54	; 21601
	.byte #0x23, #0x40	; 16419
	.byte #0x49, #0x8c	; 35913
	.byte #0x03, #0x00	; 3
	.byte #0x00, #0x00	; 0
	.byte #0x9d, #0xc8	; 51357
	.byte #0x84, #0x00	; 132
	.byte #0x09, #0x00	; 9
	.byte #0x03, #0xc7	; 50947
	.byte #0x6d, #0x00	; 109
	.byte #0x2c, #0x00	; 44
	.byte #0x20, #0xf3	; 62240
	.byte #0x03, #0x00	; 3
	.byte #0x02, #0x00	; 2
	.byte #0xb8, #0xde	; 57016
	.byte #0xf5, #0x48	; 18677
	.byte #0xd9, #0x03	; 985
	.byte #0xed, #0x8d	; 36333
	.byte #0xf0, #0x00	; 240
	.byte #0x5d, #0x00	; 93
	.byte #0x35, #0x81	; 33077
	.byte #0x24, #0x7c	; 31780
	.byte #0x11, #0x05	; 1297
	.byte #0x37, #0xd0	; 53303
	.byte #0x0b, #0x35	; 13579
	.byte #0x16, #0x31	; 12566
	.byte #0x98, #0x58	; 22680
	.byte #0x04, #0x00	; 4
	.byte #0x00, #0x00	; 0
	.byte #0x44, #0x8a	; 35396
	.byte #0xa4, #0x3a	; 15012
	.byte #0xfc, #0x14	; 5372
	.byte #0x90, #0x99	; 39312
	.byte #0x06, #0x00	; 6
	.byte #0x00, #0x00	; 0
	.byte #0xc7, #0x3a	; 15047
	.byte #0x8c, #0x00	; 140
	.byte #0x43, #0x00	; 67
	.byte #0x9f, #0x95	; 38303
	.byte #0xdc, #0x00	; 220
	.byte #0x17, #0x00	; 23
	.byte #0x73, #0x17	; 6003
	.byte #0x27, #0x04	; 1063
	.byte #0xb0, #0x02	; 688
	.byte #0x7c, #0xd7	; 55164
	.byte #0x01, #0x00	; 1
	.byte #0x00, #0x00	; 0
	.byte #0x3a, #0xde	; 56890
	.byte #0x03, #0x00	; 3
	.byte #0x01, #0x00	; 1
	.byte #0xba, #0x03	; 954
	.byte #0xf1, #0x1f	; 8177
	.byte #0xba, #0x03	; 954
	.byte #0xc5, #0x44	; 17605
	.byte #0x06, #0x00	; 6
	.byte #0x01, #0x00	; 1
	.byte #0xf3, #0x9f	; 40947
	.byte #0x58, #0x00	; 88
	.byte #0x1b, #0x00	; 27
	.byte #0x50, #0x4a	; 19024
	.byte #0x01, #0x00	; 1
	.byte #0x00, #0x00	; 0
	.area CSEG    (CODE)
	.area XINIT   (CODE)
	.area CABS    (ABS,CODE)
