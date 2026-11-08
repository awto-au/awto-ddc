# Flash and recovery safety (#96, #82)

Unit 2 recovered at 19:19 AEDT on 8 November 2026 after a full byte-mode
flash, with health 11/11. Debug-link expiry coincided with the original
failure; its causal role remains unproven. The subsequent recovery erased
138 sectors before burst programming failed. These safeguards address both
failure paths without assuming that they share a cause.

## Before ISP

`dev.py flash`, `dev.py recover` and direct `rtd_flash_image.py` runs share
the same preflight. Identity and image checks remain mandatory. The flasher
then takes an advisory debug/ISP lock, sends the debug link's existing
`CMD_BACK` command if 0x35 responds, requires the DDC/CI return acknowledgement,
and checks that 0x35 stays silent over ten 50 ms probes. It never restores
the temporary debug link. A timeout or other bus error is a refusal, not
evidence that the debug address is absent.

The lock covers all adapters and checkouts used by the same OS user on this
host because HDMI and DP cables can reach the same scaler. It lives under
`<temporary directory>/awto-ddc-<uid>/ddc-debug-isp.lock`. Cooperating `dbg_link.on`, `off` and `linked` calls
hold the same lock; they fail immediately during ISP. The flasher holds it
through the exit reset, including failure cleanup. External clients, raw
I2C commands and clients under a different OS user or host do not honour this
advisory lock and must not operate the unit during flashing.

Turning the temporary link off before the MCU is halted removes the active
link whose expiry could change DDC ownership during ISP. This uses the
existing firmware protocol, with no firmware update required. The timer
scenario is covered by an offline link model; it has not been re-tested on
physical hardware as part of this change.

Blank-flash recovery may have neither EDID nor DDC/CI. An already silent
0x35 therefore does not require 0x37 to answer. Existing relay-based identity
and `recover --bus N` fallback remain available. ISP enable must read back,
two JEDEC reads must agree with the supported flash, and two complete
sector-0 reads must match before erasure. Short reads also refuse.

## Programming and failure handling

- Per-sector erase, program and verification is the default for every unit,
  including those with relays. A relay provides recovery access, not write
  integrity. Banked code goes first, then replicated common code, then bank-0
  common code. Sector 0, containing the reset vector, is last.
- WREN must establish the write-enable latch with protection bits clear
  before the first erase. The first non-blank changed sector is read twice
  before erasure and verified using full readback, followed by two stable
  full reads of the programmed data. No separate sacrificial sector is used.
  Any earlier sectors whose target contents are all FF are erased and
  verified individually in boot-last order.
- Persistent programming, erase or verification failure stops before the
  next sector is erased. Existing bounded retries, GMBUS nudges and burst-to-byte
  recovery remain. If the write-path proof required byte fallback, the rest
  of the session stays in byte mode.
- `recover` defaults to byte programming, the mode used for unit 2's successful
  recovery, and full sector readback verification. Explicit `--write-mode burst`
  and `--verify crc` are still available. Normal `flash` retains burst and CRC
  as its defaults. The recovery fast-path ISP reset also uses the debug-link
  interlock. Invalid recovery modes and low disk space refuse before that reset
  or a relay cycle.
- Direct `rtd_flash_image.py --erase-all` retains the legacy option, but bulk
  erasure cannot begin until the first non-blank sector passes the full write
  proof. Until then, sectors complete individually. `dev.py` always selects
  per-sector mode. `--full` means every image sector is selected; it does not
  select erase-all ordering. Bytes beyond the requested image remain untouched.
  Their existing manifest hashes are retained even with `--full`.
- The manifest marks each sector unknown and saves before erasing it, then
  records it only after verification. Untouched known sectors retain their
  hashes. An interrupted or failed run can be resumed using the existing
  unknown-sector readback and drift checks.
- SIGINT, SIGTERM and SIGHUP request a stop at a verified sector boundary.
  In explicit erase-all mode, a stop after bulk erasure still finishes the
  erased set. A third signal forces interruption; SIGKILL and power loss
  cannot be deferred. Per-sector ordering bounds erased-but-unwritten damage
  to the current sector, but a mixed image is not guaranteed to boot.

Exit 5 is reserved for the initial read-stability refusal before erasure,
so the existing reset/rate retry remains safe. Exit 6 means debug-link
preflight refusal before ISP. Both preserve the previous `flashed.json` tag.
Instability after a write is a failure (exit 7), never a no-write retry.

## Disk failures and diagnostics

The 200 MiB free-space guard remains a start condition; recovery checks it
before resetting or cycling the monitor. Mid-flash logging is best effort:
main, detail and raw protocol streams, the per-unit log, stdout and stderr
cannot interrupt page programming, verification or the exit reset. Failures
are held in memory and reported through surviving output. The parent `dev.py`
also keeps draining and waits for its child if its own log fails to open,
write, flush or close. It cannot restore the I2C rate while the child still runs.

Recovery state is stricter than diagnostics. Each pre-erase invalidation is
written to a unique temporary file, flushed and fsynced, atomically replaced,
then its containing directory is fsynced. Any failure prevents that next erase.
Verified hashes remain in memory; a failed periodic checkpoint stops per-sector
mode at the verified boundary. If the caller explicitly selected bulk erase,
the already-invalidated, erased set is completed before reporting a failed
checkpoint. A failed failure-checkpoint never masks the original SPI or
interruption exception. Temporary-file cleanup is best effort.

An older durable manifest can conservatively show a completed sector as unknown.
After fixing storage, rerun the same image incrementally: unknown sectors are
read back and matching verified content is kept. Do not delete the manifest,
use `--full`, or reflash merely because diagnostics failed.

| Exit | Meaning and next step |
| --- | --- |
| 0 | Selected image verified, normal completion. |
| 5 | Initial read instability, no erase; existing bounded reset/rate retry applies. |
| 6 | Preflight refusal (debug or low disk), no erase. |
| 7 | Hardware or mandatory checkpoint failure; inspect state before recovery. |
| 8 / 9 | Verified boundary stop due to projection / signal; resume incrementally. |
| 10 | Image verified; diagnostics, final manifest or firmware-tag persistence incomplete. Fix storage and inspect state; this is not a programming failure. |
| 11 | Storage checkpoint failed after a verified sector; stopped before the next erase. Fix storage and resume. |

Failure output now reports verified-sector and outstanding erase-intent counts,
instead of claiming that nothing was written or that every planned sector
completed after an interrupted run.

## Approval and validation

No physical flash, reset, relay operation or firmware deployment was performed
to validate this change. Before another physical flash, show Dan the exact
command, target unit and bus, image path and SHA-256, programming and verify
modes, full/incremental selection, affected image range, and any reset or relay
operation. Obtain approval for that operation. Do not merge without approval.

### Procedure for a later hardware trial (not performed)

1. Check out the reviewed PR commit on the monitor host. Record `git rev-parse
   HEAD`. Select an existing, known-good **unit-2** image, not the attempted audio
   build. Record its absolute path, `sha256sum` and `stat -c %s`; require a nonzero
   multiple of 4096, at most 1048576 bytes, containing serial `AWT26110002` only.
   No firmware binary was available in this software-only workspace, so there is
   no asserted image checksum in this review.
2. Revalidate the cable/bus mapping against unit 2's EDID using read-only
   inspection. Bus 11 was the HDMI bus in #96; it must not be assumed to remain
   so. Reconcile `scripts/devices.json` with the confirmed wiring. In particular,
   this PR corrects `so-th-1` to unit 2 and clears unit 3's relay, matching Dan's
   confirmation in #96. Unit 1 also has no relay. Use the corrected configuration
   on the monitor host before any approved recovery operation.
3. Show Dan the exact commit, unit, bus, image path, SHA-256, byte range, retained
   settings range, write/verify modes and resets/relay actions. Ask for explicit
   approval. **Stop here until approval.** Disabling the debug link and a dry-run
   ISP session also change hardware state and belong after approval.
4. For a responsive unit, the proposed command template is:

   ```sh
   ./dev.py flash --unit 2 --bus BUS --write-mode byte --verify readback /absolute/approved-unit2-image.bin
   ```

   Replace both placeholders with the recorded values before requesting
   approval. This is incremental per-sector mode, with common sectors last and
   sector 0 last of all. It disables the debug link, halts in ISP and sends the
   exit reset. It performs no relay cycle and does not use `--full` or bulk erase.
   Only after success, run the separately approved health/EDID check.
5. If the unit is unresponsive, do not automatically escalate from the flash to
   recovery. Prepare a separate approval for:

   ```sh
   ./dev.py recover --unit 2 --bus BUS --write-mode byte --verify readback /absolute/approved-unit2-image.bin
   ```

   This may reset the scaler and, if necessary, cycle its verified relay, then
   use the same incremental per-sector path. Show the relay assignment and the
   possible power cycle in that approval. For signal/storage stops, fix the
   reported cause and resume the same image without `--full`; retain manifests
   and completed sectors. Persistent SPI/I2C failure requires inspection before
   any further physical operation.

Offline validation:

```sh
python -m pytest tests/test_flash_storage.py tests/test_flash_safety.py tests/test_flash_incremental.py \
  tests/test_flash_burst.py tests/test_dev_tool_hazards.py tests/test_dev.py \
  tests/test_dev_hw_args.py -q
```

Tests inject debug-link expiry and failed cancellation, intermittent debug
responses, I2C NAKs/timeouts/permission failures, unavailable ISP, mismatched
or unstable JEDEC IDs, short/unstable readbacks, WREN failure, silent failed
programming, burst-to-byte fallback, deferred signals and abrupt interruption
at banked and boot sectors. They check resume, manifest safety, boot-last
ordering, cross-process lock contention and reset cleanup. All hardware
interfaces in these tests are fake.

Storage tests also inject ENOSPC during each log sink's write and flush, parent
tee open/write/flush/close, backup creation, pre-erase invalidation, periodic and
final checkpoints, manifest write/fsync/rename/directory-sync, and a failure save
following an interrupted page. They assert current-sector completion, no next
erase without a durable invalidation, reset/reprotection, preserved tail hashes,
conservative manifests and resume without re-erasing completed sectors.

Results for this follow-up: **185 focused tests passed** (32 added storage/
recovery cases). The broader locally available suite returned **245 passed,
13 skipped, 23 failed**. Running the existing PR #97 snapshot separately gave
**212 passed, 13 skipped, the same 23 failed test IDs**: no added failures.
Those failures cover absent regdb/SDK/header/clean-room fixtures, existing
protocol golden-output and OSD/health expectations, and the I2C-layer rule's
existing objection to `ddcnet.py` using `fcntl` for its TUN device. They were
not rewritten or suppressed for this flash change. The lock-only exception
for `dbg_link.py` still rejects `fcntl.ioctl` and raw I2C operations.

Compilation and whitespace checks passed. The new diagnostics/storage tests
and interlock detector pass Ruff; touched production code adds no lint findings
relative to the existing PR baseline. Hardware and rebuilt-firmware validation
remain pending.
