; Optional, bounded DW8051 diagnostic; NOT part of fw_build.py.
; Source: Synopsys DW8051 Databook v3.2a, 2-25..2-27 (DPS=86h, CKCON=8Eh).
; https://web.eecs.utk.edu/~dbouldin/protected/DW8051-databook.pdf
;
; ABI: __sdcccall(0), sole XDATA pointer in DPL0:DPH0; DPS.0 MUST be zero.
; Preserves IE, PSW, ACC, B, R0-R7 in every bank, DPS, and both DPTRs.
; 16 pushes + the caller's 2-byte return address = 18 bytes stack headroom.
; Interrupts masked during probe. No calls, loops, flash, peripheral or code writes.
; MOVX writes confined to caller-owned record[0..15], including scratch [14..15].
; Reads CKCON without changing timing. No probing unknown SFRs/opcodes/RAM.
; Record byte 15 is invalidated first and committed as A5 last. See docs/mcu-features.md.

        .module awto_mcu_features
        .globl _AwtoMcuFeatures
        .area CSEG (CODE)

_AwtoMcuFeatures:
        push 0xa8                 ; IE, including entry EA
        clr  0xaf                 ; EA
        push 0xd0                 ; PSW
        push 0xe0                 ; ACC
        push 0xf0                 ; B
        push 0x00
        push 0x01
        push 0x02
        push 0x03
        push 0x04
        push 0x05
        push 0x06
        push 0x07
        anl  0xd0,#0xe7           ; use bank 0, saved all of its registers
        mov  r4,0x86              ; original DPS
        anl  0x86,#0xfe
        push 0x82                 ; DPTR0
        push 0x83
        push 0x84                 ; DPTR1
        push 0x85
        mov  r2,0x82              ; output pointer
        mov  r3,0x83
        mov  r5,0x8e              ; read-only CKCON snapshot
        mov  r6,#0                ; passed mask
        mov  r7,#1                ; attempted mask (independence first)
        mov  r0,#0                ; MOVC observations, valid only if attempted
        mov  r1,#0

        mov  a,r2
        add  a,#15
        mov  0x82,a
        mov  a,r3
        addc a,#0
        mov  0x83,a
        clr  a
        movx @dptr,a              ; invalidate previous completion before testing

        mov  dptr,#0x12a5         ; DPTR0
        orl  0x86,#1
        mov  dptr,#0xc35a         ; DPTR1, if implemented
        anl  0x86,#0xfe
        mov  a,0x82
        cjne a,#0xa5,00001$
        mov  a,0x83
        cjne a,#0x12,00001$
        mov  a,0x84
        cjne a,#0x5a,00001$
        mov  a,0x85
        cjne a,#0xc3,00001$
        inc  r6                   ; passed bit 0
        sjmp 00002$
00001$:
        ljmp 00010$               ; no second pointer: skip dependent tests

00002$:
        mov  r7,#3
        mov  dptr,#0x12ff
        inc  dptr                 ; carry must affect only DPTR0
        mov  a,0x82
        cjne a,#0,00003$
        mov  a,0x83
        cjne a,#0x13,00003$
        mov  a,0x84
        cjne a,#0x5a,00003$
        mov  a,0x85
        cjne a,#0xc3,00003$
        orl  0x86,#1
        mov  dptr,#0x34ff
        inc  dptr                 ; carry must affect only DPTR1
        mov  a,0x84
        cjne a,#0,00003$
        mov  a,0x85
        cjne a,#0x35,00003$
        mov  a,0x82
        cjne a,#0,00003$
        mov  a,0x83
        cjne a,#0x13,00003$
        mov  a,r6
        orl  a,#2
        mov  r6,a
00003$:
        anl  0x86,#0xfe
        mov  r7,#7
        mov  dptr,#00020$
        clr  a
        movc a,@a+dptr
        mov  r0,a
        orl  0x86,#1
        mov  dptr,#(00020$+1)
        clr  a
        movc a,@a+dptr
        mov  r1,a
        ; Re-read DPTR0 after loading DPTR1: do not just test two independent loads.
        anl  0x86,#0xfe
        clr  a
        movc a,@a+dptr
        cjne a,#0x3c,00004$
        mov  a,r0
        cjne a,#0x3c,00004$
        mov  a,r1
        cjne a,#0xa7,00004$
        mov  a,r6
        orl  a,#4
        mov  r6,a
00004$:
        mov  r7,#15
        ; DPTR0 = record + 14, DPTR1 = record + 15 (both reserved scratch bytes).
        mov  a,r2
        add  a,#14
        mov  0x82,a
        mov  a,r3
        addc a,#0
        mov  0x83,a
        mov  a,r2
        add  a,#15
        mov  0x84,a
        mov  a,r3
        addc a,#0
        mov  0x85,a
        mov  a,#0x69
        movx @dptr,a
        orl  0x86,#1
        mov  a,#0x96
        movx @dptr,a
        anl  0x86,#0xfe
        movx a,@dptr
        cjne a,#0x69,00005$
        orl  0x86,#1
        movx a,@dptr
        cjne a,#0x96,00005$
        mov  a,r6
        orl  a,#8
        mov  r6,a
00005$:
00010$:
        anl  0x86,#0xfe
        mov  0x82,r2
        mov  0x83,r3
        mov  a,#0x4d             ; 'M'
        movx @dptr,a
        inc  dptr
        mov  a,#0x46             ; 'F'
        movx @dptr,a
        inc  dptr
        mov  a,#1                ; version
        movx @dptr,a
        inc  dptr
        mov  a,#16               ; size
        movx @dptr,a
        inc  dptr
        mov  a,r7                ; attempted mask
        movx @dptr,a
        inc  dptr
        mov  a,r6                ; passed mask
        movx @dptr,a
        inc  dptr
        mov  a,r4                ; entry DPS
        movx @dptr,a
        inc  dptr
        mov  a,r5                ; entry CKCON (not measured timing)
        movx @dptr,a
        inc  dptr
        mov  a,r2                ; destination low byte
        movx @dptr,a
        inc  dptr
        mov  a,r3                ; destination high byte
        movx @dptr,a
        inc  dptr
        mov  a,r0                ; MOVC via DPTR0
        movx @dptr,a
        inc  dptr
        mov  a,r1                ; MOVC via DPTR1
        movx @dptr,a
        inc  dptr
        clr  a
        movx @dptr,a              ; reserved 12
        inc  dptr
        movx @dptr,a              ; reserved 13
        inc  dptr
        movx @dptr,a              ; scratch 14
        inc  dptr
        mov  a,#0xa5
        movx @dptr,a              ; commit record, last

        pop  0x85
        pop  0x84
        pop  0x83
        pop  0x82
        mov  0x86,r4
        pop  0x07
        pop  0x06
        pop  0x05
        pop  0x04
        pop  0x03
        pop  0x02
        pop  0x01
        pop  0x00
        pop  0xf0
        pop  0xe0
        pop  0xd0
        pop  0xa8                 ; restore interrupt state only after all other state
        ret

00020$:
        .db 0x3c,0xa7
