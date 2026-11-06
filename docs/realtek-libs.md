# Realtek libraries (FunctionLib, AdvancedLib)

Status 2026-11-06. Issues: #11 (toolchain, audit), #30 (library signature DB).

## What they are

| Library | Form in our SDK copy | Size | Contents | Used |
|---|---|---|---|---|
| FunctionLib `Kernel/Scaler/RL6449_Series_Scaler/Lib/Output/RL6449_FunctionLib.LIB` | Keil OMF `.LIB` + 150 C sources | 438 KB | register/data-port access, burst + multi-byte R/W, flash R/W (settings), 32-bit mul/div, timer polling, OSD engine, colour (gamma, dither, CSC, contrast, brightness), parts of DP / memory / auto / OD / TCON | yes: 78 of 289 modules |
| AdvancedLib `.../Lib/Code/RL6449_AdvancedLib.LIB` | Keil `.LIB` only, no source | 16 KB | advanced motion-blur reduction (RtkAdvMbr: `ScalerMbrRtkAdvMbrAdjust`, ...), advanced TCON (`ScalerTconAdjustByIndex`, ...) | no (features off) |

- SDK copy: `/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST`.
- C sources: `RL6449_Series_Scaler/Lib/Code/**`, `ScalerCommonFunction/Lib/Code/**`.
- Linked modules (last build): OSD 40+, colour/gamma/dither, data-port access, burst write, flash R/W, `ScalerComputeDwordMulDiv`, M-domain DB helpers. List: `tmp/logs/fw_build.log` line `lib: N/M modules selected`.

## How we build them

- SDCC cannot link Keil OMF. `scripts/fw_build.py` compiles `RL6449_Series_Lib.Uv2` sources with SDCC, then links only referenced modules (linker-style pull).
- So lib code = Realtek C + SDCC codegen, not Realtek's Keil binary.
- Cost: SDCC passes params/locals via xdata (22,810 param DPTR loads in the image); Keil uses registers + link-time packing. Image: 13 banks (SDCC) vs 7 (Realtek Keil build), #11.
- Hot paths (every main-loop pass or ISR): data-port access, burst write, mul/div, timer polling.
- Scaler register access itself is a macro, not a lib call: `ScalerSetByte(a, v)` = `*(volatile xdata *)a = v` (registers are XDATA-mapped at `page << 8 | reg`).

## Options

| Option | Gives | Effort | Risk | Decision (2026-11-06) |
|---|---|---|---|---|
| Size/speed audit vs vendor | per-function ours vs Realtek Keil size, hotness ranking | hours | none (read-only) | chosen |
| Hand-written asm, top 5-10 functions | smaller/faster hot paths, register params | days; equivalence test each | medium: exact C semantics, big-endian, banking, ISR copies | chosen |
| Wait for SDCC register-call fork (#11) | register params for all code incl. libs | weeks (awto-sdcc) | medium-high | not the only path; fork continues |
| Use AdvancedLib (MBR, adv. TCON) | backlight-strobe motion-blur reduction | weeks: OMF conversion or reversing | high: no source, Keil-convention calls, Realtek binary | not chosen |

### Not chosen, detail

- **SDCC register-call fork only**
  - Fork = first args in CPU registers like Keil (upstream RFE #934/#79: no work).
  - Fixes every function, not just libs; must be proven on all code before trust.
  - Hand asm keeps SDCC's call convention at call sites, so it survives the fork; drop any hand function the fork beats.
- **AdvancedLib**
  - 16 KB Keil object only: needs OMF -> SDCC-linker conversion (relocation, Keil register-param calls both ways) or reversing.
  - Feature: MBR backlight strobing at 60 Hz: less blur, less brightness, possible flicker. Gaming value; not needed for a desktop monitor.
  - Panel TCON tuning needs confirmed panel data (panel ID open, #3).
  - Revisit after 4K60 (#26) works, only if MBR becomes a product goal.

## Work in flight

1. Audit: `scripts/lib_audit.py` -> `tmp/lib_audit.tsv` (our size, vendor size, call sites, ISR use); summary on #11. Agent, worktree branch.
2. Hand asm for top 5-10, each with a simulator/host equivalence test, SDCC call convention kept. Same agent/branch; merge after review, test flash on unit 3 only.
3. Vendor match (#30): `scripts/omf51_lib.py` parses the Keil `.LIB`; `scripts/rtk_libsig.py build|match` stores masked signatures per library version under `~/vendors/realtek/analysis/libsigs/` and matches any firmware: EXACT / NEAR / ABSENT per function, library-version verdict, names TSV for Ghidra. Answers: does the vendor image use this library build; do our C sources match the `.LIB`.
4. More versions: firmware-package hunt and RTDCustomerTool version hunt feed the signature DB; finds indexed in `~/vendors/realtek/analysis/found_images.tsv`, `found_symbols.tsv`, `found_hostapps.tsv`.

## Open questions (Dan)

- Is MBR (motion-blur reduction) ever a product goal? Yes -> AdvancedLib moves up.
- After the SDCC fork lands: keep hand asm that is still smaller/faster, or remove it for one source of truth?
