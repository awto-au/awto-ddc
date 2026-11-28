# DRAM log consistency (#391)

Review base: `ce8e1625f5c168f67f0f28145395f2bee448f5f0` (28 November 2026).
This includes the merged #392 defensive port fix at `b43178cb` and the DDR-keep changes.
No hardware, relay, ISP, flash or monitor debug-link operation was performed for this patch.

## Branch review before implementation

All fetched remote refs were inspected for changes to `scripts/dram_log.py`, `scripts/unit_log.py` and `fw/log/hostnote.c`.
The relevant named heads were:

| Branch | Head | Result |
| --- | --- | --- |
| main | ce8e1625 | selected base |
| porta-busy | b43178cb | merged into base; preserved |
| ddr-keep | caefa11f | included in base |
| log-times | d4235798 | earlier reader/saver work, included in base |
| log-merge | 53c3721c | log presentation work, no newer header-reader/publication implementation |
| saver-cmd | dec4137b | older saver command work |
| sync-word-index | bcf9dfc9 | older log work |

Sources: [issue #391](https://github.com/awto-au/awto-ddc/issues/391),
[#392 merged verification](https://github.com/awto-au/awto-ddc/issues/392#issuecomment-7234160615).
The 12,496-burst hardware result belongs to #392, not to this unflashed patch.

## Alternatives

| Mechanism | Benefit | Limitation / decision |
| --- | --- | --- |
| Compatible bounded host retries | Works with existing v1 firmware; retries a bad checksum or individual failed burst locally | Cannot guarantee recovery from a persistently corrupt single header; retained in this patch |
| Compare whole header before / after body | Detects change | Rejects normal hint writes every 64 entries and boot/note updates; repeated multi-minute reads may never finish; rejected |
| Compare generation and boot before / after body | Detects reset/reinitialization and unsafe clock association without rejecting logging progress | Does not make a single header atomic; retained together with local retries |
| Alternating firmware header copies | One previous valid publication remains while the other is rewritten; CRC16 and a serial identify valid/newer copies | Requires host-first upgrade, another 16 bytes of reserved DDR and 7 static XDATA bytes; selected for v2 |

The entry format, ring address, generation byte, boot byte and 24-bit entry index remain unchanged.
V2 header format and migration are in `dram-log-design.md`. Old host readers reject v2;
new host readers support v1 and v2. The first migration write goes to the shadow,
so the sole valid legacy header survives an interrupted upgrade.

## Read contract

A snapshot fixes its generation and end index at the start. Entries are individually
validated by checksum, generation and expected absolute index. Body reads do not chase
a moving write pointer. At the end only generation and boot identity are compared;
normal hint/publication advancement does not restart any body read.

Retries are bounded to three attempts per header observation or individual burst,
with 10 ms between failed attempts. A permanently bad body burst produces a partial
snapshot with valid rows retained and compact missing-index ranges. The saver resumes
at its first unresolved burst, retaining a sparse set of already appended later indexes
so a subsequent poll fills the hole without duplicating rows. Ring clipping and a
newer index in the same slot are separately identifiable as overwrites. Missing bytes
alone never prove a cold boot.

A transport/checksum failure in the forward end scan returns an unavailable snapshot,
not a falsely shortened log. Stable arbitrary unwritten bytes whose index/generation
do not match the requested entry can terminate a scan; this is distinct from a corrupt
entry with matching identity. Scan-limit exhaustion is explicitly unavailable. A stale
XDATA write index of zero never suppresses existing DDR history.

| Snapshot status / diagnostic | Meaning and caller action |
| --- | --- |
| ok | requested range validated; ordinary logging may have advanced |
| partial | some requested rows missing; preserve all valid rows and report reasons |
| generation_changed | reset/reinitialization during read; keep validated old-generation rows; next poll uses a new index namespace |
| boot_changed | warm reset during read; retain history and remove current-boot wall-clock association |
| unverified | final header unavailable; keep rows and retry without advancing an established saver cursor |
| unavailable + absent | repeated blank headers; no claim about cold boot vs not initialized |
| unavailable + invalid | stable invalid headers after bounded attempts |
| unavailable + transient_checksum | differing invalid header observations |
| unavailable + io_failure | header bytes could not be transferred |
| boundary_error | end index could not be established; never print a successful smaller count |
| missing reason overwritten | a newer index occupies the requested slot, or end hint proves it aged out |
| missing reason checksum / io_failure | unresolved per-entry read error, retained for subsequent polling |

## Caller review

- `dram_log.header` keeps its dict/None API, with optional diagnostics; `entry` keeps dict/None and retries locally.
- `snapshot` returns structured status even when unavailable, with no entries and no end index in that case. All repository snapshot callers were updated.
- `sync_log --dram` emits diagnostics in text and JSON. An unavailable snapshot exits 2 and still emits structured JSON. The saver therefore does not fall back to the smaller XDATA view when the header is transiently unreadable.
- `sync_log._ring_v4` does not read the DDR header: it anchors its limited/episode view to a single XDATA image. Its DDR entry calls gain retries; its existing `dram_missing` count remains. This path does not make a full-history claim.
- The host saver stores generation with the cursor and passes `--generation` with `--since`. Generation mismatch or backwards index resets the requested range. Existing generation-less state is migrated conservatively with a fresh recent-range read. Previously saved file contents are preserved.
- The GUI passes generation with page/follow requests, retains earlier generations in its view/export, retains existing rows after partial/unavailable reads, and queues a bounded page retry for unread bursts. History pages never move the global follow end backwards.
- Standalone `dram_log.py` uses the same snapshot implementation and reports unavailability without calling it a cold boot.
- Sync-log wall-clock inputs are bracketed by XDATA identity observations; a reset removes an unproven clock join. End-of-body reset detection also removes the console clock join.

## Simulated validation

`tests/test_dram_log_concurrency.py` creates 5,142 entries: 2,866 historical and
2,276 current-boot entries. A synthetic sequence of first-read checksum failures
makes the old single-read decoder return exactly 2,276; local retries recover all
5,142. A separate transient header checksum test recovers the complete fixture.
This reproduces the symptom/counts, not the exact unrecorded hardware interleaving.

The deterministic tests cover over 300 seconds of virtual body-read time while
hints change continuously, header and entry I/O failures, short reads, persistent
holes and saver recovery/deduplication, genuine namespace changes, warm boot clock
handling, ring overwrites, publication wrap, legacy/downgraded headers, and CLI
unavailable output. No wall-time multi-minute sleep is needed.

`tests/test_dram_log_firmware.py` compiles the actual C publisher, CRC, selector,
end scan and boot initializer function bodies with a native compiler and undefined
behavior sanitizer, replacing only DDR transfer / clock / boot-reason dependencies.
It checks every byte boundary of an interrupted update, alternating slots, dirty
publication retries, legacy migration, corrupt copies, one/both unread copies,
24-bit publication wrap, warm repair, cold generation wrap and failed boot scans.
The resulting native-published header is decoded by the production Python reader.
This is not an SDCC target build or a timing measurement.

Focused validation command:

```sh
python -m pytest -q tests/test_dram_log.py tests/test_dram_log_concurrency.py \
  tests/test_dram_log_firmware.py tests/test_dram_log_gui.py \
  tests/test_log_times.py tests/test_unit_log.py
```

Result at packaging: **65 passed**. Python compilation and whitespace checks pass.
Touched host Python and new tests pass Ruff. Existing GUI-module import/default-argument
lint findings are unchanged.

Broader checks reproduced identically on unchanged base `ce8e1625`:

- `tests/test_gui_client.py::test_event_stream_survives_repeated_read_timeouts`
  cannot create an AF_UNIX socket (`Operation not permitted`) in this environment.
- `QT_QPA_PLATFORM=offscreen python tools/osd_editor/test_log_view.py` passes the
  1,601-row history/follow/dedupe/export and legacy fallback portions, then fails
  the existing `yields_to_flash_and_jobs` scheduling assertion at line 158.
  New offscreen GUI consistency tests all pass.

## Release gates and limits

The pinned `/usr/local/bin/sdcc` toolchain is absent here. Full target build, generated
bank/XDATA tables, overlay depth, CRC publication cost, normal/extensive firmware gates
and the existing `dram_log_sim` image run remain pending. Do not merge or deploy based
only on the native harness. Seven new static XDATA bytes and new bank-5 functions
require the normal target layout review; no guessed generated tables are included.

The original 8-bit generation/boot and 24-bit entry identity still have finite wrap
limits: after enough unobserved resets the identity can alias. CRC16 detects corruption
with finite collision probability, not cryptographic certainty. Simultaneous raw
clients can still interfere with MCU_DC; this patch preserves all #392 port defenses
and does not claim to solve its unidentified register writer.

Before a live check: build the pinned target, pass offline gates, identify the image
hash and eligible unit, and obtain Dan's explicit approval. Suggested approved test:
repeat a several-minute full-history read with ongoing logging across header updates,
then verify notes, port state and continuity; separately test warm/cold reset cases.
No approval has been requested for or inferred for any live operation in this patch.

## Applied source branch

The implementation is now applied to the source files on
`review/dram-log-consistency-391` (draft PR #395). The previous embedded review
package was removed from that branch to present the code changes directly.
The shadow address is derived in the project-owned `fw/log/hostnote.c` from
`AWTO_DLOG_HDR_UNITS - AWTO_DLOG_ENTRY_UNITS`; the Realtek SDK header is unchanged.
The native harness uses that production definition. This applied source was
validated against current main `cac1c66f7ce73112787040d11f6f5c7903a980e0`,
retaining its later DDC/CI, layout and validation changes. Focused tests were rerun
after this adjustment; target SDCC and live validation remain pending.
