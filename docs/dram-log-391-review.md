# Concurrent DRAM log retrieval (#391)

Review base: `ce8e1625` (main, 28 November 2026). Host-only change. No merge,
flash, monitor access or live test was performed.

## What #392 establishes

The [merged port-A fix](https://github.com/awto-au/awto-ddc/issues/392#issuecomment-7234160615)
rewrites LEN_A, clears late read flags and recovers reserved commands. The reported
12,496-burst run kept the port usable. The reserved-command writer is still unknown.
That run is evidence for port reliability, not an atomic-header protocol or proof
that [#391](https://github.com/awto-au/awto-ddc/issues/391) no longer occurs.

Inspection of all fetched branches' history for `scripts/dram_log.py` and
`fw/log/hostnote.c` found the merged #392 work, and no subsequent header-snapshot
fix. The GitHub DRAM PR search and `dram` branch-name search returned no matches.
The branch is based on main including #392 and DDR retention (#365).

`AwtoDlHdr` still replaces a single 16-byte v1 header every 64 entries, at boot,
and for host notes. It has an XOR check, not a commit sequence. Its hint is a
recovery position, not a snapshot identifier. The original reader rejects one
bad header and skips failed body reads. Offline interrupted-burst tests reproduce
those reader failure conditions independently of the reserved-command recovery.
A hardware claim about whether #392 eliminated the original observed trigger
remains unverified; doing that requires Dan's approval for monitor access.

## Selected change

Keep firmware and its on-DDR formats unchanged. Retry each failed header / entry
burst up to three attempts, with 5 ms between attempts. Validate exact length,
existing checksum, generation, and the expected absolute entry index. A short
hardware buffer now returns a failed read rather than raising IndexError.

Read a valid header before the range and another after it. Generation / boot
changes or a regressing hint reject the range. A normal advancing hint is
recorded in diagnostics and **does not restart the retrieval**. A copied record
remains usable if its ring slot is overwritten later. An overwritten / persistently
unreadable record encountered before it can be copied rejects the range, preserving
the caller's cursor. Stop at the first persistent body failure so a dead port
cannot incur three failures for all 32,768 slots.

The XDATA write-index shortcut now requires matching generation / boot, an index
within the bounded hint recovery window, and a validated entry at index-1. The
window also rejects torn XDATA high bytes that could alias a 24-bit entry index.
Zero is no longer trusted as an unconditional empty-log shortcut. XDATA is sampled
before the host clock; a mismatch with the DDR header suppresses that boot's wall
clock estimate. Otherwise a bounded forward scan supplies the boundary. An
exhausted scan is an error, rather than a truncated successful result. A readable
unwritten slot may contain arbitrary nonchecksummed bytes; it is retried before
being accepted as the scan boundary, and its index is never consumed. Records
appended after the sampled boundary belong to the next poll.

The guarantee is a validated copied index range within one generation / boot,
not a freeze of the entire live ring at one instant. Persistently bad slots are
reported rather than silently discarded. A later explicit retry can recover;
there is no automatic several-minute whole-ring retry.

## JSON and consumer behavior

Existing successful fields and entry format remain. Additive fields:

| Field | Meaning |
| --- | --- |
| `status` | `ok`, `empty`, or `error` |
| `complete` | Only a validated requested range is true |
| `error.code`, `error.message`, `retryable` | Present for bounded read failures; distinguish them from an empty range |
| `diagnostics.retries` | Additional burst attempts |
| `diagnostics.hint_advanced` | Normal concurrent hint movement, accepted |
| `start`, `end` | Consumed index range, end exclusive |
| `next` | Observed ring boundary, which can exceed a page's `end` |
| `gaps` | Explicit overwritten ranges before the retained ring, end exclusive |
| `cursor_reset` | A supplied cursor belonged to a different generation or a regressed index |

Errors contain no publishable entries. `synclog --dram --json` still emits
`SYNCJSON` on failure, followed by a diagnostic and exit code 2. The saver raises
on that structured error without falling back to a smaller XDATA ring. Failed
reads cannot modify saved state or the GUI cache. GUI errors preserve the displayed
records and explain the failure. Valid empty generations clear the old view.
Overwritten ranges appear as gap separators in the GUI and exported text.

Cursors now include `--since-gen`; the saver state stores generation with the
absolute index, including an empty new generation. Deduplication survives warm
reset and retained DDR sleep / wake. Generation changes reuse indices, so the
saver writes a reset marker and accepts the new generation's records. Note IDs
also restart: an unscoped note registry from an older generation must not suppress
new records with reused IDs.

The saver reads at most 300 entries per poll. The GUI's follow cursor advances to
the consumed page end, not directly to the ring boundary. This fixes skipped
pages when more than one chunk arrives between polls. Legacy states without a
generation restart with the normal newest-64 read and report an observed gap or
index reset. Historical data never obtained before migrating cannot be inferred.

## Alternatives examined

| Approach | Cost / benefit | Decision |
| --- | --- | --- |
| Bounded local retries | No firmware change; recovers interrupted bursts without scanning history again | Implemented |
| Header/body/header identity validation | One additional header burst on the XDATA path; catches generation / boot replacement, tolerates ordinary hint movement | Implemented |
| Reject any changed header | Ongoing logging changes hints and note sequence; can repeatedly restart a minutes-long full read | Rejected |
| Two alternating checksummed headers | Keeps a previous committed copy through a torn update, but needs firmware and recovery protocol changes | Deferred pending host fix review and evidence of persistent header failures |

An alternating-header design must reserve another DDR burst after checking the
memory map, add a commit serial in the reserved bytes, invalidate the target copy
before replacement, and accept only a fully validated copy. Recovery must compare
both serials with wrap rules, and handle one valid / two invalid copies. A cold
generation change must retire both old-generation copies before appending new
records: otherwise falling back to a valid old header can resurrect a discarded
generation. Warm-init, note numbering and power-saving recovery must all use the
same selection protocol. Old firmware only reads the primary, so alternating
without a primary compatibility policy is not backward compatible.

If the primary remains a v1 compatibility copy and a second copy is also written
on every checkpoint, that adds at least one 16-byte write per checkpoint (one per
64 entries, plus notes and boot), plus any invalidation writes and recovery reads.
Using the measured ~68 us burst-load figure from dram-log-design.md gives a lower
bound of ~1.06 us per entry for that extra periodic write; it is not a measured
implementation result and excludes arbitration, validation and initialization.
No second-copy storage address or firmware prototype is committed by this change.

The v1 XOR checksum can miss compensating corruption. Generation and boot are
8-bit counters; a complete wrap between observations can alias an older identity.
The entry index stores 24 bits (the live ring has only 32,768 slots); ordinary
24-bit index rollover is tested, but the 32-bit firmware counter reset is treated
as a cursor reset when observed. Strong protection against arbitrary corruption
or unobserved identity reuse requires a stronger checksum and wider persistent
identity in a future format. Retried consistent observations cannot manufacture
those guarantees from v1 fields.

## Offline cost measurements

Counters assert calls to the real reader abstraction using synthetic DDR and a
fake debug-link transport. No host timing was measured on a live monitor.

| Case | Measured operations |
| --- | --- |
| 6,000 records, matching XDATA position, advancing final hint | 6,003 DDR bursts: 6,000 entries + one position check + two headers; no repeated body |
| Baseline equivalent XDATA path | 6,002 bursts from the former algorithm; delta +1 burst (16 bytes), ~0.017% |
| One interrupted body record, two failed attempts | Only that record is retried; +2 burst attempts and 10 ms configured backoff |
| Permanently invalid initial header | Three attempts; no body reads |
| Full-ring request with first body record unreadable | Six attempts total: initial header + position check + three entry attempts + final header |
| Additional header, idle/ready port, clean debug replies | 23 debug-link `io.write` / `io.read` calls: two byte reads (6), five byte writes (15), one block read (2) |
| Firmware overhead | Zero added source instructions, RAM bytes, DDR storage or writes; firmware is unchanged |

The scan fallback adds one final header plus two retries of an unwritten end slot
relative to the former single-read scan: +3 burst attempts and 10 ms backoff in
that case. Polling or lower-level debug-block retries can add transactions beyond
the clean transport count. `ddr_reader` now counts attempts separately from
successful bursts and records short buffers.

## Validation

Run from this checkout (Python with pytest and PySide6):

```sh
python -m pytest -q tests/test_dram_snapshot.py tests/test_dram_log_view.py \
  tests/test_dram_log.py tests/test_unit_log.py tests/test_log_times.py \
  tests/test_gui_client.py -k 'not event_stream_survives_repeated_read_timeouts'
```

Result: **96 passed, one deselected**. Tests cover all 15 header split positions
with an interrupted checksum, short / failed reads, transient and permanent
entry failures, changed generation / boot, moving / regressing hints, stale
XDATA identity, actual ring wrap, overwrite during a read, 24-bit index rollover,
retained sleep / warm boot, generation reset to empty, saver deduplication and
page continuation, structured error propagation, GUI cache preservation and gaps.
A fake transport counts the actual debug-link calls for the extra header.

The deselected socket-stream test cannot create AF_UNIX sockets in this executor
(`PermissionError: Operation not permitted`). The broader standalone
`tools/osd_editor/test_log_view.py` passes its history / follow / fallback checks,
then fails the existing unit-1-writability assertion in `yields_to_flash_and_jobs`.
The same assertion fails on an untouched archive of main `ce8e1625`. These are
reported limitations, not successful suite runs. No firmware build / simulator
gates were run because firmware is unchanged. Live monitor validation and merging
remain subject to Dan's approval.
