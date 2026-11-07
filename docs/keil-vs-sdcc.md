# Keil C51 vs SDCC: semantic differences (same source, different behaviour)

- Tracking: awto-ddc#57 (catalogue + scan), awto-sdcc#25 (`--keil-compat` compiler options).
- Scanner: `scripts/keil_sdcc_scan.py` -> `re/keil_sdcc_scan.tsv` (class, file:line, snippet, risk, handled, fix_where); log `tmp/logs/keil_sdcc_scan.log`.
- Scope: 521 C files compiled for RL6449 + their headers (other chip series/boards excluded), SDK `RTD-Scaler-TEST` + `fw/overlay`.
- Not a full C parse: token scan + per-file declaration table + macro bodies + regex call graph. Operands of unknown type are skipped, so counts are lower bounds.
- Probes: `re/keil-sdcc-probes/*.c`, compiled 2026-11-07 with Keil C51 V9.60 (Wine, `scripts/keil_probe.py`, default controls INTPROMOTE) and awto-sdcc 4.6.4 (`--model-large --fsigned-char --std-sdcc11`), asm compared.
- Keil guide = `~/vendors/keil/cx51-users-guide-2001/c51.pdf` (printed page numbers). SDCC manual = `~/vendors/sdcc/sources/sdccman-20261107.pdf` (4.6.4).
- Fix where: `compiler flag` = semantic, belongs in awto-sdcc `--keil-compat` (awto-sdcc#25); `keil2sdcc` = syntax rewrite only; `library` = crt override; `none`.

## Classes

| class | C11 | Keil | SDCC | handled now | fix where | sites | status |
|---|---|---|---|---|---|---|---|
| `~` on `bit` | ext: impl-defined (`bit` is an extension) | bit NOT (`CPL C`), result 0/1 (probe p1 t_notbit) | promotes to int: `~1` = 0xFFFE, still true; no warning for `~bit` (warning 180 fires only for `bit = ~uchar`) | keil2sdcc regex `~ b[A-Z]\w*` -> `!` (wb-vfreq 2d9835b): only Hungarian names | compiler flag | 9 (8 by the name rule, 1 not: `ScalerSyncProc.c:325` `~(ScalerADCGetClampToTopStatus())`, VGA chroma path) | handled (name rule); NEEDS RULE for the 1 + any renamed bit |
| `~` on `unsigned char` in compare / bit-assign context | standard: Keil non-conforming | stays a byte: `~x == 0xFF` is `CJNE R7,#FF` (probe p1 t_uchar_not); `bit = ~x` tests the byte | ANSI promotion: `~x` is 0xFFxx; compare never true, `bit = ~x` constant 1 | none | compiler flag | 1 (`RTD2014Key.c:484` IR NEC check `buf[0] == ~buf[1]`) | NEEDS RULE (IR path; rest of `~` uses are masked, fine) |
| `bit` from int | ext: impl-defined | nonzero -> 1 (`ADD A,#FF`; probe p1 t_bitfromint, p4 t2/t3) | same | n/a | none | 73 non-trivial RHS | OK (tested) |
| arithmetic on `bit` (`+ - * << ++`) | ext: impl-defined | compile error C193 (probes p1, p3, p4) | accepted | n/a: SDK cannot contain it | none | 0 | OK |
| div / mod by zero | UB (6.5.5p5) | `/` `%` int/long via `?C?UIDIV/SIDIV/ULDIV` (result for 0 not verified); 8-bit inline `DIV AB` (hardware: undefined, OV set) | 8-bit same inline `DIV AB`; int/long C helpers: `% 0` loops forever (SF bug 3510, awto-sdcc#1) | `fw/sdcc/crt_mod0.c`, `crt_divulong.c`: `x % 0 = x` (found via eDP link rate/lanes = 0, #8) | library | 510 variable-divisor sites (415 on int/long/unknown) | handled for `%` and `/`; Keil `?C?*DIV` zero result needs a test (run C51L.LIB in ucsim) |
| `unsigned char ==/!= -1` | standard: Keil non-conforming | constant narrowed to a byte: `x != -1` is `CPL A; JZ` (probe p3 t2); ANSI says always true | ANSI fold, warning 94 | warn gate | compiler flag | 0 | OK (no sites) |
| `char == unsigned char` | standard: Keil non-conforming | compared as bytes: `CJNE A,AR7` (probe p4 t11) | int promotion: -1 != 255 (warning 185) | none | compiler flag | 0 | OK (no sites) |
| plain `char` signedness | impl-defined (6.2.5p15) | signed (guide p.98 data types) | unsigned by default (manual 3.1.8.4) | `--fsigned-char` on every file | compiler flag (already) | all | handled |
| integer promotion | standard (6.3.1.1); NOINTPROMOTE non-conforming | `INTPROMOTE` default on (guide p.41-43, KB ka003852): ANSI; probes match SDCC for `u = x*y`, `(x+y)>>1`, `x<<8` | ANSI | n/a | compiler flag if NOINTPROMOTE | 1 `ucM << 8` (`ScalerMemory.c:844`) | needs a test: SDK `.Uv2` stores options as packed `C51FL=21646608` (0x14A4D10), not decoded; INTPROMOTE assumed |
| enum size | impl-defined (6.7.2.2p4) | 1 byte if the values fit, else 2 (guide p.98, 177; probe p1 t_enum) | smallest of uchar/schar/uint... (manual 3.1.8.5) | n/a | none | 552 enum lines | OK (tested; same layout) |
| signed `>>`, signed `/` rounding | `>>`: impl-defined (6.5.7p5); `/`: standard (6.5.5p6) | arithmetic shift (probe t_sshr, t_cshr); `?C?SIDIV` truncates (untested) | arithmetic; truncation (C99) | n/a | none | 26 `>>` on signed names | OK |
| shift count >= width, const overflow | UB (6.5.7p3) | `x<<24` on uchar -> 0 (probe p3 t7) | 0, warning 116 | warn gate (#26) | none | gate | OK |
| word/long byte order, unions, byte-buffer word views | impl-defined (6.2.6.1) | big-endian (guide p.176-177, 373-374) | little-endian | `--big-endian` (AWTO_SDCC_BE=1), #15 | compiler flag (exists) | 1873 `PDATA_WORD`/word-cast sites (207 dangerous per #15), 7 unions | handled iff BE build |
| bit-field order and size | impl-defined (6.7.2.1p11) | LSB-first, packed in the byte (probe p1 t_bf: `a:1` -> bit0, `d:4` -> bits 4-7) | LSB-first, source order (manual 3.1.8.9): same | n/a | none | 22 fields wider than 8 bits (Type-C PD structs) | OK for <=8-bit (closes #20 item 2); wide fields under BE: needs a test (awto-sdcc#7 item 2) |
| generic pointer tags, memory-space casts | impl-defined (ext. pointers) | tag byte data/idata 0x00, xdata 0x01, pdata 0xFE, code 0xFF (guide, Generic Pointers storage format; the V4 values 1-5 are obsolete) | own tag values | BE builds / asm transcribed with Keil tags (awto-sdcc#8 Q7) | compiler flag | not scanned | needs a test |
| code pointers, `code BYTE *t[]` storage-first | ext | table in code | pointer-to-code in RAM | keil2sdcc storage rewrite (#20) | keil2sdcc | 40 decls | handled |
| function pointers | standard | indirect call, call-tree overlay aware | `__code` ptr | rewrite (#20) | keil2sdcc | 3 | handled |
| overlay vs reentrancy | ext: impl-defined | static call-tree overlay of locals; functions shared by ISR + main get linker warning L15 | per-function static locals (`--nooverlay` + `sdcc_overlay.py`) | `sdcc_overlay.py`, `sdcc_isr_libs.py` (#19) | none | 0 SDK functions reachable from both ISR and main | OK |
| ISR-shared non-volatile globals | unspecified/UB (no volatile: 5.1.2.3, 6.7.3) | no cross-statement value tracking of globals; ISR-written flags re-read each time (#23 loop) | genconstprop / CSE / loop opts fold them (#23) | `--nogenconstprop`, `--noinvariant`, volatile rule for 2 flags | compiler flag (treat ISR-written globals as volatile) | 46 (5 `bit`, 41 BYTE/WORD/DWORD) written in ISR-reachable code, read elsewhere, not volatile | NEEDS RULE |
| evaluation order | unspecified (6.5p3) | args left-to-right; binary `g()+h()` evaluates `h()` first (probe p2) | `g()` first | none | compiler flag | 7 (4 pairs of `ScalerGet*` register reads: `ScalerCommonIOSC.c:114,139`, `ScalerCommonDPTxMST.c:2689`, `ScalerSyncProc.c:562`) | NEEDS RULE if the reads latch (check `P6_A1/A4` OSC counter pairs) |
| `volatile` / SFR access order | impl-defined (6.7.3p7) | every access emitted | every volatile access emitted (manual 3.1.8.10) | n/a | none | n/a | OK |
| `sbit` / `bdata` | ext | `sbit X = P1^3`, `bdata` bit-addressable byte | `__sbit __at`; no `bdata` | SBIT rewrite; `bdata` -> `__data` (not bit-addressable) | keil2sdcc | 78 sbit, 0 bdata | handled |
| float format | impl-defined | IEEE-754 32-bit, big-endian (guide p.374) | IEEE 32-bit | n/a | none | 0 | OK |
| `sizeof` pointers | impl-defined | 1 B data/idata/pdata, 2 B xdata/code, 3 B generic (guide p.99) | same sizes | n/a | none | 0 sizeof-of-pointer | OK |
| string literals, const | modification UB (6.4.5p7) | literals in code space, `char code *` | `__code` literals, generic ptr taken | tags per awto-sdcc#8 Q7 | compiler flag | not scanned | needs a test |
| startup zeroing, init | standard (6.7.9p10 zero init) | STARTUP.A51 clears IDATA/XDATA | `crt_rtd_startup`, XSEG1-4 clear (#20) | handled | none | n/a | handled |
| `#pragma` | impl-defined (6.10.6) | `OT(n)`, `NOAREGS`, `disable`, `save/restore` | unknown pragmas ignored | OT/NOAREGS/... dropped by keil2sdcc; `save/restore` kept | keil2sdcc | 23 `#pragma OT(8)`; 0 `disable` | handled |
| intrinsics | ext | `_crol_ _cror_ _irol_ _lrol_ _nop_ _testbit_` | none | `fw/sdcc/intrins.h` (`_testbit_` unresolved) | keil2sdcc | 8 (`_nop_` only) | OK |
| library: memcpy/strcpy return, printf `%bd` | standard | per C51 lib | per SDCC lib | n/a | library | 0 / 0 | OK (no sites) |
| `switch` jump tables | none | JMP @A+DPTR tables | tables or compare chains | n/a | none | 1377 | OK (no semantic difference) |

- C11 column (awto-sdcc#25): only implementation-defined / unspecified / UB classes go to `--keil-compat`; where Keil contradicts standard C the option is opt-in (`--keil-char-cpl`) or none; standard-defined SDCC bugs are fixed unconditionally (awto-sdcc#26, #28).

## Findings from this pass (2026-11-07)

- Keil's library STARTUP (C51L.LIB, default `XDATALEN 0`) does not zero XDATA: an uninitialised `static` in the LARGE model held garbage in the awto-sdcc#25 probe (C requires zero); the SDK ships its own STARTUP.A51.

- The `/0` issue Dan means: `x % 0` after a failed eDP link (rate/lanes = 0) hung SDCC's C `_moduint/_modulong`; override in `fw/sdcc/crt_mod0.c` (3d9fc5f, #8), upstream patch awto-sdcc#1.
- `~bit` is not the only `~` hazard: `~unsigned char` in compare/bit context (Keil keeps a byte) has 1 SDK site; `~` on a bit-returning function has 1 more.
- SDCC warnings do not cover this: warning 180 fires only for `bit = ~uchar`; `~bit` is silent. 0 of the gated warnings in the last build were 180/185.
- Keil rejects `+ - * << ++` on `bit` (C193), so SDK sources cannot contain bit arithmetic; the class is closed.
- Bit-field order assumption of #20 (Keil MSB-first) was wrong: Keil packs LSB-first like SDCC.
- Open decisions: decode `C51FL` (INTPROMOTE/OPTIMIZE level) from a Keil project; run `?C?UIDIV/ULDIV` with divisor 0 in ucsim; list the 46 ISR-shared globals for a volatile rule.

## Sources

- Cx51 User's Guide: INTPROMOTE p.41-43, data types p.98-99, storage formats p.176-178, byte ordering Appendix E p.373-374; KB https://support.arm.com/documentation/ka003852/1-0/ (integer promotion).
- SDCC manual 3.1.8 (implementation-defined behaviour), 3.5.1 (address spaces), 3.8.1.1 (volatile in ISRs), 3.11.2 (promotion cast example).
- Porting notes (syntax only, no semantics): https://hackaday.io/project/170540-adventures-with-a-stc89c52-development-board/log/177065-notes-on-converting-keil-8051-c-to-sdcc-c , https://github.com/allan-simon/keil2sdcc , https://github.com/cjacker/opensource-toolchain-8051/blob/main/difference-between-c51-and-sdcc.md , SDCC forum "Transferring the controller from Keil C51".
- None of the public porting guides list a semantic difference (`~bit`, `/0`, evaluation order, `~uchar`); all cover syntax (`sbit`, `interrupt`, `code`, `_nop_`).
