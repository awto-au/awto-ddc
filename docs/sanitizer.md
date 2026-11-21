# sdcc_san: ISR race sanitizer for the DW8051 sim

KCSAN / TSan-style runtime detector in `scripts/mcs51_core.c` (`-DSDCC_SAN` build), host side `scripts/sdcc_san.py`.
Design: awto-sdcc#176. Self-test: `./dev.py san` (`scripts/san_test.py`, snippets in `fw/sansim/`).

## Run
- `AWTO_SIM_SAN=<outdir> [AWTO_SIM_SAN_MARKS=<marks.tsv>] <any sim script or fw_gates.py IMAGE_STEM>`
  - builds `tmp/mcs51_core_san.so` (separate from the normal `tmp/mcs51_core.so`); every `FastMachine` writes `<outdir>/<tag>-<pid>-<n>.san.{tsv,json}` at exit.
  - child processes inherit the variable: fw_gates runs every gate under the sanitizer.
- `scripts/sdcc_san.py merge <outdir> -o <file.tsv>`: union over runs, ranked.
- Log: `tmp/logs/sdcc_san.log`.

## Model (core)
- Context = source, not priority: main, EXINT0, T0, EXINT1, T1, serial, T2, WDT (EXINT2 0x43). Frame stack parallel to `lvl[]` (`fr[nlvl]`), ISR names from the vector LJMP target in the .map.
- Preemptor mask, at each instruction boundary (before the IRQ poll): source s can preempt if EA, its enable bit and priority > running level (IP / EIP), and the instruction was not RETI / an IE write.
  - `__critical`, EX0/ET* masking and the IP=0x81 window need no special case.
- Shadow: per context x byte, last read and last write (tick, instance id, pc). Spaces: XDATA pool 0xD000..0xF7FF, IRAM direct + `@Ri`, bit space 0x00..0x7F (bit instructions only).
  - Not tracked: SFRs, registers R0-R7, stack pushes/pops, `push direct` / `pop direct` (ISR context save of e.g. the BIT_BANK byte), host writes (`Machine.wr`), stubbed functions.
  - Bit accesses and byte accesses to 0x20..0x2F do not alias.
- `could` = mask allowed a preemptor that is also seen touching the byte somewhere in the run; `did` = it really ran an access inside the window.
  - Window of a pair = boundaries between the two own accesses of one ISR/main instance (per-instance last-open stamps).
- Reports:
  - A conflict: own access at a boundary where a source is open, that source reads/writes the byte (>= 1 write); `did` = a conflicting access between this and the previous own access.
  - B lost update: own read, then own write, preemptor wrote between.
  - C torn: two same-direction accesses to adjacent bytes within 16 own instructions, preemptor accessed either byte between; host side keeps it only when both bytes are in one map symbol (size >= 2).
  - D clobber: own write, then own read within 512 ticks, preemptor wrote between. Overlaps A for any state variable; ranked below B and C.
- Joined at exit: a candidate counts only when the preemptor context ever accessed the byte (`evr` / `evw`), so a `could` needs the ISR to have run once.

## Mark list (awto-sdcc isr-marks v1 and v1.1)
- TSV, first line `# awto-sdcc isr-marks v1` or `v1.1`; columns `symbol module size class contexts reason` (+ `space` = data|idata|xdata|pdata|bit|code in v1.1); other versions rejected.
- Classes: `attr` drop everything; `volatile` / `marked` drop A only; `exempt` drop everything, report `MISS` when the run saw >= 2 contexts on it; `unmarked` / not listed: report all (`mark` column shows `unlisted`).
- Address resolution is ours (`scripts/san_names.py`): (symbol, module) -> linked address of this build.
  - globals: `.map`; statics (module = file stem, long linker names such as `_isr0_sv_65536_12`): the linked listings `tmp/sdcc-port/asm_bank/*.rst`, set `AWTO_SIM_SAN_RST=<dir>`.
  - listings are used only if the map's globals have the same addresses (a listing of another build is ignored, `tmp/logs/sdcc_san.log` says which source was used).
  - `__at` hardware registers (scaler / MCU registers outside 0xD000..0xF7FF) are not tracked and their rows stay unresolved by design.
- Report names: objects with their extent (`_isr_g_stAwtoDiag+22`), bits by their bit object (`_d_isr_g_bNotifyTimer2Int`), else area (`[BIT_BANK]`, `[BSEG_BYTES]+4.bit4`).
- Reader: `sdcc_san.read_marks`.

## Cost
- Normal build: no sanitizer code (`#ifdef SDCC_SAN`); `bit_read` / `bit_write` / `@Ri` accesses go through equivalent inline helpers.
- Measured 2026-11-21 (`scripts/san_bench.py`, raw core, dw8051 model + flash fetch, 20 M instr from reset, shared box at load ~12): origin/main core vs this core, normal build, alternating runs: 59..124 vs 59..124 Minstr/s, no difference outside the load noise.
- Sanitizer build, off: 0.98x of the normal build. On: 0.33x (35.8 vs 109 Minstr/s, same run).
- fw_gates `--tier extensive` of one image under the sanitizer: same PASS / FAIL set as without it (keys_full, sync fail on both in a bare worktree).

## Limits
- The sim runs what the scenarios drive: a race that no scenario provokes is `could` at best, and only if the ISR ran once.
- Compiler may drop an access (constant propagation): the sanitizer sees the code as built.
- Snapshot / restore does not carry sanitizer state.
