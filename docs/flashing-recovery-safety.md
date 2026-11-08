# Flash and recovery safety (#96)

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
  recovery. Explicit `--write-mode burst` is still available. Normal `flash`
  retains burst as its default.
- Direct `rtd_flash_image.py --erase-all` retains the legacy option, but bulk
  erasure cannot begin until the first non-blank sector passes the full write
  proof. Until then, sectors complete individually. `dev.py` always selects
  per-sector mode. `--full` means every image sector is selected; it does not
  select erase-all ordering. Bytes beyond the requested image remain untouched.
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

## Approval and validation

No physical flash, reset, relay operation or firmware deployment was performed
to validate this change. Before another physical flash, show Dan the exact
command, target unit and bus, image path and SHA-256, programming and verify
modes, full/incremental selection, affected image range, and any reset or relay
operation. Obtain approval for that operation. Do not merge without approval.

Offline validation:

```sh
python -m pytest tests/test_flash_safety.py tests/test_flash_incremental.py \
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
