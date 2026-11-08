# Optional MCU feature diagnostic

This is a callable diagnostic for the RTD2795T/RL6449's DW8051 CPU. It is
**not linked into the monitor firmware and has no boot-time or host-side hardware
entry point**. There is no physical result yet. Simulator results describe the
model, not the monitor. Do not flash the simulation fixtures.

The documented register scheme is from the Synopsys DW8051 Databook v3.2a,
printed pages 2-25 through 2-27:
<http://web.eecs.utk.edu/~dbouldin/protected/DW8051-databook.pdf>.
The SDK and original-firmware evidence is recorded in
[mcu-8051.md](reversing/realtek-rtd/mcu-8051.md).

## What it establishes

| Check | Operation | Limits |
|---|---|---|
| Independent pointers | Load distinct DPTR0/DPTR1 addresses through DPS.0; inspect both pairs | Tests the documented SFR scheme only |
| Selected increment | Increment each pointer across a low-byte carry; verify the other stays unchanged | Does not test decrement or automatic increment |
| Selected code read | MOVC reads two distinct local constants, including returning to DPTR0 after loading DPTR1 | Current code bank only |
| Selected XDATA access | MOVX writes and reads two distinct bytes in the caller's output buffer | Does not establish the full RAM extent or its speed |
| Control snapshot | Read entry DPS and CKCON | A programmed stretch setting is not a timing measurement |

Failure to establish independent pointers skips the three dependent checks.
Each later failed check has its own flag. Unknown capabilities remain untested:
auto-toggle/increment/decrement, extra arithmetic units, RAM size, timing,
cache, additional UARTs and USB. No unknown SFR writes, reserved opcode tests,
RAM sweep, flash operation, ISP operation or reset is included.

## Calling contract (future integration, not a deployment instruction)

`fw/sdcc/mcu_features.asm` exports `AwtoMcuFeatures`, declared in
`fw/sdcc/mcu_features.h`. The only argument is a pointer to **16 exclusively
owned contiguous XDATA bytes**, passed using `__sdcccall(0)` in DPL0/DPH0.
The entire buffer must fit in actual RAM, with no address wrap or overlap with
EDID, diagnostic blocks, active globals or memory-mapped peripherals.

Call from main/startup with DPS.0 zero and at least **18 bytes of internal
stack headroom before the call**, including the two-byte return address. It is
not an ISR entry point. It saves IE and masks interrupts, saves PSW/ACC/B,
bank-0 R0-R7, DPS and both pointers; temporarily selects bank 0; restores all
that state, including incoming register-bank selection and interrupt enable.
There are 16 pushes, no nested calls and no data-dependent loops. It does not
alter CKCON. It temporarily alters documented pointer registers and only writes
XDATA within the caller's buffer. Stack bytes used above the entry SP are scratch.

A future hardware operation must first show Dan the exact integration, image,
unit, buffer reservation, stack analysis, transport/readout and recovery steps,
and obtain approval for any firmware flash. The normal firmware is unchanged.
The vendor SDK and patched production compiler are not available in this review
environment, so full firmware integration, production ABI and hardware timing
remain unvalidated. The assembly ABI must be checked against that build before
enabling it, including a big-endian build if selected.

## Record (all fields are bytes)

| Offset | Meaning |
|---|---|
| 0..1 | ASCII `MF` |
| 2 | Version 1 |
| 3 | Size 16 |
| 4 | Attempted mask: bits 0..3 match the four checks above |
| 5 | Passed mask |
| 6 | Entry DPS |
| 7 | Entry CKCON |
| 8..9 | Buffer address, low byte then high byte, explicitly encoded |
| 10..11 | MOVC observations, expected 0x3C and 0xA7 when tested |
| 12..14 | Zero; byte 14 was temporary MOVX scratch |
| 15 | Completion marker 0xA5, written last; invalidated before probing |

This encoding does not depend on compiler byte order. Byte 15 also serves as
the second MOVX scratch byte. Read only after the routine returns; concurrent
capture is not supported. Clear the reserved buffer before starting a new
attempt: interruption before the routine's first write cannot invalidate an old
record. A completion marker means the record was published, not that the host
has independently verified restoration or that every check passed.

Decode an already captured binary, without opening any monitor device:

```sh
python3 scripts/mcu_features.py record.bin --json
```

Exit 0 means no attempted check failed; 1 means an attempted check failed; 2
means a malformed/incomplete capture or file error. Untested features are never
reported as absent.

## Offline validation

```sh
python3 scripts/mcu_features_sim.py --tools "$AWTO_SDCC_BIN"
AWTO_MCU_TEST_TOOLS="$AWTO_SDCC_BIN" python3 -m pytest -q tests/test_mcu_features.py
```

Only the assembler, linker and simulator are used. The simulation runner writes
fixtures and logs under `tmp/mcu-features/`. DS320 is the positive control for the
documented dual-pointer scheme; plain 8052 is the negative control. They are not
full RTD2795T models. Cases cover all four incoming register banks, interrupts
initially enabled/disabled, output crossing a 256-byte boundary, preservation of
both pointers/IE/PSW/ACC/B/SP/CKCON and all lower IRAM, and buffer canaries.
Tests also inject incorrect increment, MOVC/MOVX results, missing completion and
failed pointer restoration. Interrupt handlers themselves are not exercised;
interrupts are masked during the diagnostic.
