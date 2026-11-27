;--------------------------------------------------------
; File Created by SDCC : free open source ISO C Compiler
; Version 4.5.0 #15242 (Linux)
;--------------------------------------------------------
	.module local_static
	
	.optsdcc -mmcs51 --model-large
;--------------------------------------------------------
; Public variables in this module
;--------------------------------------------------------
	.globl _main
	.globl _other
	.globl _counter
	.globl _sim_done
	.globl _sim_val
	.globl _seed
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
Llocal_static.counter$step$1_0$5==.
_counter_step_10000_5:
	.ds 1
Llocal_static.counter$total$1_0$6==.
_counter_total_10000_6:
	.ds 2
Llocal_static.counter$calls$1_0$6==.
_counter_calls_10000_6:
	.ds 1
Llocal_static.other$x$1_0$7==.
_other_x_10000_7:
	.ds 1
Llocal_static.other$t$1_0$8==.
_other_t_10000_8:
	.ds 6
Llocal_static.other$s$1_0$8==.
_other_s_10000_8:
	.ds 2
Llocal_static.main$r$1_0$12==.
_main_r_10000_12:
	.ds 2
;--------------------------------------------------------
; absolute external ram data
;--------------------------------------------------------
	.area XABS    (ABS,XDATA)
;--------------------------------------------------------
; initialized external ram data
;--------------------------------------------------------
	.area XISEG   (XDATA)
G$seed$0_0$0==.
_seed::
	.ds 1
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
;------------------------------------------------------------
;Allocation info for local variables in function 'counter'
;------------------------------------------------------------
;step          Allocated with name '_counter_step_10000_5'
;total         Allocated with name '_counter_total_10000_6'
;calls         Allocated with name '_counter_calls_10000_6'
;------------------------------------------------------------
	G$counter$0$0 ==.
	C$local_static.c$8$1_0$6 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:8: static unsigned char calls = 3;
	mov	dptr,#_counter_calls_10000_6
	mov	a,#0x03
	movx	@dptr,a
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
;Allocation info for local variables in function 'counter'
;------------------------------------------------------------
;step          Allocated with name '_counter_step_10000_5'
;total         Allocated with name '_counter_total_10000_6'
;calls         Allocated with name '_counter_calls_10000_6'
;------------------------------------------------------------
	G$counter$0$0 ==.
	C$local_static.c$5$0_0$6 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:5: unsigned int counter(unsigned char step)
;	-----------------------------------------
;	 function counter
;	-----------------------------------------
_counter:
	ar7 = 0x07
	ar6 = 0x06
	ar5 = 0x05
	ar4 = 0x04
	ar3 = 0x03
	ar2 = 0x02
	ar1 = 0x01
	ar0 = 0x00
	mov	a,dpl
	mov	dptr,#_counter_step_10000_5
	movx	@dptr,a
	C$local_static.c$9$1_0$6 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:9: total += step;
	movx	a,@dptr
	mov	r7,a
	mov	dptr,#_counter_total_10000_6
	movx	a,@dptr
	mov	r5,a
	inc	dptr
	movx	a,@dptr
	mov	r6,a
	mov	r4,#0x00
	mov	dptr,#_counter_total_10000_6
	mov	a,r7
	add	a, r5
	movx	@dptr,a
	mov	a,r4
	addc	a, r6
	inc	dptr
	movx	@dptr,a
	C$local_static.c$10$1_0$6 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:10: calls++;
	mov	dptr,#_counter_calls_10000_6
	movx	a,@dptr
	add	a, #0x01
	movx	@dptr,a
	C$local_static.c$11$1_0$6 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:11: return total + calls;
	movx	a,@dptr
	mov	r7,a
	mov	dptr,#_counter_total_10000_6
	movx	a,@dptr
	mov	r5,a
	inc	dptr
	movx	a,@dptr
	mov	r6,a
	mov	a,r7
	add	a, r5
	mov	r5,a
	mov	a,r4
	addc	a, r6
	C$local_static.c$12$1_0$6 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:12: }
	C$local_static.c$12$1_0$6 ==.
	XG$counter$0$0 ==.
	mov	dpl,r5
	mov	dph,a
	ret
;------------------------------------------------------------
;Allocation info for local variables in function 'other'
;------------------------------------------------------------
;x             Allocated with name '_other_x_10000_7'
;t             Allocated with name '_other_t_10000_8'
;i             Allocated with name '_other_i_10000_8'
;s             Allocated with name '_other_s_10000_8'
;------------------------------------------------------------
	G$other$0$0 ==.
	C$local_static.c$13$1_0$8 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:13: unsigned int other(unsigned char x)
;	-----------------------------------------
;	 function other
;	-----------------------------------------
_other:
	mov	a,dpl
	mov	dptr,#_other_x_10000_7
	movx	@dptr,a
	C$local_static.c$15$2_0$8 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:15: unsigned char t[6]; unsigned char i; unsigned int s = 0;
	mov	dptr,#_other_s_10000_8
	clr	a
	movx	@dptr,a
	inc	dptr
	movx	@dptr,a
	C$local_static.c$16$2_0$9 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:16: for (i = 0; i < 6; i++) t[i] = x + i;
	mov	dptr,#_other_x_10000_7
	movx	a,@dptr
	mov	r7,a
	mov	r6,#0x00
00103$:
	mov	a,r6
	add	a, #_other_t_10000_8
	mov	dpl,a
	clr	a
	addc	a, #(_other_t_10000_8 >> 8)
	mov	dph,a
	mov	a,r6
	add	a, r7
	movx	@dptr,a
	inc	r6
	cjne	r6,#0x06,00135$
00135$:
	jc	00103$
	C$local_static.c$17$1_0$8 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:17: for (i = 0; i < 6; i++) s += t[i];
	mov	r7,#0x00
00105$:
	mov	a,r7
	add	a, #_other_t_10000_8
	mov	dpl,a
	clr	a
	addc	a, #(_other_t_10000_8 >> 8)
	mov	dph,a
	movx	a,@dptr
	mov	r6,a
	mov	dptr,#_other_s_10000_8
	movx	a,@dptr
	mov	r4,a
	inc	dptr
	movx	a,@dptr
	mov	r5,a
	mov	r3,#0x00
	mov	dptr,#_other_s_10000_8
	mov	a,r6
	add	a, r4
	movx	@dptr,a
	mov	a,r3
	addc	a, r5
	inc	dptr
	movx	@dptr,a
	inc	r7
	cjne	r7,#0x06,00137$
00137$:
	jc	00105$
	C$local_static.c$18$1_0$8 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:18: return s;
	mov	dptr,#_other_s_10000_8
	movx	a,@dptr
	mov	r6,a
	inc	dptr
	movx	a,@dptr
	C$local_static.c$19$1_0$8 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:19: }
	C$local_static.c$19$1_0$8 ==.
	XG$other$0$0 ==.
	mov	dpl,r6
	mov	dph,a
	ret
;------------------------------------------------------------
;Allocation info for local variables in function 'main'
;------------------------------------------------------------
;r             Allocated with name '_main_r_10000_12'
;i             Allocated with name '_main_i_10000_12'
;------------------------------------------------------------
	G$main$0$0 ==.
	C$local_static.c$20$1_0$12 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:20: void main(void)
;	-----------------------------------------
;	 function main
;	-----------------------------------------
_main:
	C$local_static.c$22$2_0$12 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:22: unsigned int r = 0; unsigned char i;
	mov	dptr,#_main_r_10000_12
	clr	a
	movx	@dptr,a
	inc	dptr
	movx	@dptr,a
	C$local_static.c$23$1_0$12 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:23: for (i = 0; i < 4; i++) { r += counter(seed + i); r += other(i); }
	mov	r7,a
00102$:
	mov	dptr,#_seed
	movx	a,@dptr
	add	a, r7
	mov	dpl,a
	push	ar7
	lcall	_counter
	mov	r5, dpl
	mov	r6, dph
	pop	ar7
	mov	dptr,#_main_r_10000_12
	movx	a,@dptr
	mov	r3,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	mov	dptr,#_main_r_10000_12
	mov	a,r5
	add	a, r3
	movx	@dptr,a
	mov	a,r6
	addc	a, r4
	inc	dptr
	movx	@dptr,a
	mov	dpl, r7
	push	ar7
	lcall	_other
	mov	r5, dpl
	mov	r6, dph
	pop	ar7
	mov	dptr,#_main_r_10000_12
	movx	a,@dptr
	mov	r3,a
	inc	dptr
	movx	a,@dptr
	mov	r4,a
	mov	dptr,#_main_r_10000_12
	mov	a,r5
	add	a, r3
	movx	@dptr,a
	mov	a,r6
	addc	a, r4
	inc	dptr
	movx	@dptr,a
	inc	r7
	cjne	r7,#0x04,00119$
00119$:
	jc	00102$
	C$local_static.c$24$1_0$12 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:24: sim_val("r", r);
	mov	dptr,#_main_r_10000_12
	movx	a,@dptr
	mov	r4,a
	inc	dptr
	movx	a,@dptr
	mov	r5,a
	mov	r6,#0x00
	mov	r7,#0x00
	mov	dptr,#_sim_val_PARM_2
	mov	a,r4
	movx	@dptr,a
	mov	a,r5
	inc	dptr
	movx	@dptr,a
	mov	a,r6
	inc	dptr
	movx	@dptr,a
	mov	a,r7
	inc	dptr
	movx	@dptr,a
	mov	dptr,#___str_0
	mov	b, #0x80
	lcall	_sim_val
	C$local_static.c$25$1_0$12 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:25: sim_val("c", counter(0));
	mov	dpl, #0x00
	lcall	_counter
	mov	r6, dpl
	mov	r7, dph
	mov	dptr,#_sim_val_PARM_2
	mov	a,r6
	movx	@dptr,a
	mov	a,r7
	inc	dptr
	movx	@dptr,a
	clr	a
	inc	dptr
	movx	@dptr,a
	inc	dptr
	movx	@dptr,a
	mov	dptr,#___str_1
	mov	b, #0x80
	lcall	_sim_val
	C$local_static.c$26$1_0$12 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:26: sim_done();
	lcall	_sim_done
	C$local_static.c$27$1_0$12 ==.
;	/mnt/2tb/git/awto-ddc/fw/simtests/local_static.c:27: }
	C$local_static.c$27$1_0$12 ==.
	XG$main$0$0 ==.
	ret
	.area CSEG    (CODE)
	.area CONST   (CODE)
Flocal_static$__str_0$0_0$0 == .
	.area CONST   (CODE)
___str_0:
	.ascii "r"
	.db 0x00
	.area CSEG    (CODE)
Flocal_static$__str_1$0_0$0 == .
	.area CONST   (CODE)
___str_1:
	.ascii "c"
	.db 0x00
	.area CSEG    (CODE)
	.area XINIT   (CODE)
Flocal_static$__xinit_seed$0_0$0 == .
__xinit__seed:
	.db #0x01	; 1
	.area CABS    (ABS,CODE)
