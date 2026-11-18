# Register knowledge base (RTD2795T)

One typed, machine-checked record of every register: what the regdb says, what the SDK calls it, what our code uses, what we observed, what we concluded, and the test that would settle it. Analysis lives here as data; prose docs link to a key.
Home issue: #236 (acceptance: regdb name + status + test + result per row; generated header names stay regdb names, #161).

## Files
| file | rows | edited by |
|---|---|---|
| `regs.tsv` | one per register address (`PPAA`) + hand-noted port registers (`PPAA:II`) | generated columns: `regmap_build.py`; hand columns: you |
| `fields.tsv` | one per annotated bit range (`PPAA[hi:lo]`) | same |
| `i2c.tsv` | I2C devices and commands that are not registers: `I2C:AA` (7-bit address), `SCDC:OO` (offset at 0x54), `CMD:CC` (command byte); columns `key role status test_id result evidence source notes issue`, same values as regs.tsv, hand only | you (`regmap_build.py --set-i2c KEY col=val`) |
| `tests.tsv` | tests that are not in `docs/osd/open-items.md` (`C-*`) | you |
| `read_behind.tsv` | per page: does a first read of a dword return stale data (debug slave / ISP); see "Read-behind" | `scripts/reg_behind_probe.py --tsv` |
| `obs/*.tsv.gz` | observation store, one file per dump / scan | `regmap_import.py` only |

Format: TSV, UTF-8, header line, LF, no quoting (no tab / newline inside a cell), sorted by key. Stdlib reader: `regmap_lib.read_tsv`. Greppable: `grep -P '^FFED\t' re/regmap/regs.tsv`.
Why TSV: one line per register = one-line diffs, `grep` / `awk` / `sort` work, no dependency; same family as `docs/delay-audit.tsv`. Hand text is one line; longer text goes in a doc and the cell links it.

## Key
- `PPAA` = page hex + address hex, 4 upper-case digits (`01E0` = page 01, address E0). Same number as the regdb `address` column and the SDK `P1_E0_*` names.
- `PPAA:II` = indexed port register (data port `PPAA`, index `II`): rows only where hand-noted or observed; the regdb lists 3041 of them (`reg_type` 2..6).
- `PPAA[hi:lo]` = field.

## regs.tsv columns
Generated (never edit; `--check` fails on a stale file):
| column | meaning |
|---|---|
| key, page, addr | see Key |
| regdb_name | register name in `re/regdb/RTD2795T-CG.tsv.gz` |
| regdb_status | `documented` (>= 1 named field) / `blank-reserved` (row exists, only reserved or no fields) / `no-row` |
| regdb_reset | regdb reset value |
| regdb_fields | `name[hi:lo]ACC;...` named fields |
| access | set of regdb field access codes (`R`, `RW`, `RW4` = double buffered, `W`) |
| sdk_name | Realtek SDK symbol(s) at the address (`P<page>_<AA>_NAME`, `MCU_<AAAA>_NAME`); [sdk-hypothesis] only |
| sdk_status | `none` / `defined` / `used` (referenced by SDK C code) |
| sdk_uses | reference count in `fw/sdk` `.c` / `.h` |
| our_name | `AWTO_R_*` in `fw/sdk/Project/Header/AwtoRegs.h` (generated from the regdb by `gen_regnames.py`) |
| other_chips | other regdbs with named fields at the address: `2776B` = same name, `2776B=NAME` = different name. Same address does not mean same meaning: [regdb-other] |
| obs_n | number of observed values |
| obs_distinct, obs_min, obs_max, obs_const | distinct values; min / max (hex); value if constant |
| obs_nonzero | 1 if any observation was nonzero |
| obs_vary_state | 1 if the value differs inside one state group = same unit + label + state + method (weak: label `none` groups all unlabelled dumps of a unit) |
| obs_first, obs_last | first / last observation date |
| obs_units | distinct units observed |
| obs_hist | per method (`i` isp, `l` live, `r` regdump) `value x count`, top 5 |

Hand (survive regeneration, merged by key; checked by `--check`):
| column | allowed values |
|---|---|
| class | `config` `status` `counter` `sensor` `test` `port` `unused` `reserved` |
| role | one line: what it is / does |
| side_effects | read-clears, data port, FIFO, auto-increment, W1C, burst state (one line) |
| status | `known` (role settled at the cited evidence) / `candidate` (undocumented or unproven, worth a test) / `unknown` (seen, no role) / `ignore` (hazard or not wanted: e.g. HDCP key port); blank = not triaged |
| test_id | `OT-n`, `T-A..T-M`, `T1..T10` (ids of `docs/osd/open-items.md`) or `C-*` in `tests.tsv`; comma separated |
| result | one line: measured result + date / unit / doc link; where it differs from the regdb, say both |
| evidence | `claim=tag[+tag];...`; claim = a hand column (`role`, `class`, `result`, `status`, `side_effects`); tags below |
| notes | <= 1 line; more goes in a doc, link it |
| issue | `#N[,#M]` |

A `known` / `candidate` row with a role needs `evidence`.

## Evidence tags (order: hw > databook > spec > regdb-other > source-code > re > sdk-hypothesis > guess)
`hw` measured on our units | `databook` DW8051 v3.2a, MX25L8006E | `spec` regdb text of this chip | `regdb-other` another chip's regdb | `source-code` third-party source or a standard (Linux, flasher repos, VESA / HDMI), not Realtek SDK | `re` static reversing of the Dahua firmware image | `spec-model` simulator reading of a spec claim, not seen on hardware | `emu` our sim only | `sdk-hypothesis` Realtek SDK source or name (not reliable, Dan 2026-11-18) | `guess` | `unknown`.
Same tags as `docs/osd/README.md`; convention: awto-dan `docs/embedded/reversing/README.md`.

## fields.tsv columns
Generated: `fkey` `key` `hi` `lo`, `regdb_field` (names of regdb fields overlapping the bits), `regdb_access` / `regdb_reset` / `regdb_text` (the exactly matching regdb field, else the first overlapping one; first sentence, trimmed).
Hand: `name` (our name when the regdb has none or is wrong), `role`, `status`, `test_id`, `result`, `evidence`, `notes`, `issue`. Same values as above. A field row needs its register row in `regs.tsv`.

## Observation store (`obs/`)
- One gzip TSV per source: `<serial>-<label>-<YYYYMMDD-HHMMSS>.tsv.gz`. Header lines `#key=value`: `source` (original file), `serial`, `unit`, `label`, `state` (`halted+reset` for ISP dumps, `running`, `frozen`), `method` (`isp` | `live` | `regdump`), `time` (ISO 8601 with offset), `uptime_s` (if known), `bus`, `image`, `note`.
- Body: `p<TAB>PPAA<TAB>hex tokens` = a run of page values starting at `PPAA` (`..` = not read / excluded); `q<TAB>PPAA<TAB>tokens` = port values by index. One logical observation = key + value + the file's header (`regmap_query.py --obs KEY` prints them expanded).
- Page runs instead of one row per value: 36 files = 248 KB; one row per value was 13x larger (full-page ISP dumps, 2026-11-19: 65 KB vs 860 KB gzipped).
- Only unique (serial, label, time): an existing file is kept. Never stored: HDCP key / port registers (`71C4 72C4 71C9 71CA 72C9 72CA`, `regmap_lib.EXCLUDE_KEYS`); the check fails if one appears. No firmware bytes, no flash content.
- ISP dumps read `FFxx` (MCU registers) as 00: not the running value; use live scans for `FF00..FFFF`. Compare observations by `method`.
- Size budget: `obs/` <= 1.5 MB, `regs.tsv` <= 4 MB (`--check` fails above). Register values of our own units are fine in the public repo.

## Read-behind (read artifact on the PHY pages, found 2026-11-19)
- Rule [hw]: on a read-behind page, the first read of an aligned 32-bit dword (address & ~3 differs from the previous read's) can return the byte of the same lane of the previous dword (the old latch). Other bytes of that dword, and a repeat read of the same address, return the settled value. Verdict per page in `read_behind.tsv` (`live` = debug slave 0x35, MCU running; `isp` = ISP F4/F5, MCU halted).
- Pages (live): `88 8A 8B 8E 8F 90 A0 A3 A4 A6 A7 A8 AB AC AE AF C8 CA CB CE CF D0`; `A*` only stale-by-latch (repeat reads right), the rest also have registers whose value depends on earlier reads (`yes+other`: e.g. 88C0..88FF read 00 / 0D after a low address, 80 80 .. 10 54 44 C0 .. after a sequential scan).
- Debug slave byte path: first read of each new dword stale (A0: 93 % of the informative reads, 8E: 90 %, 88: 72 %); repeat read right.
- Debug slave block path (0x3C): every dword start inside a block and the first byte after another address are stale (targeted test: 8E 16 of 16 in-block dword starts, A0 / A8 8 of 8); lanes 1-3 right. Block reads therefore carry the artifact too.
- ISP path: 88 8A 8B 8E 8F 90 C8 CA CB CE CF D0 show it at a lower rate (8E 25 wrong of 385 new-dword reads vs 217 live); A0 A3 A4 A6 A7 A8 AB AC AE AF read clean (0 wrong).
- Tool rule: read twice on a first read in a dword (`dbg_xdata.BEHIND_PAGES`, `stale_prone`): `reg_live_scan.py` (byte path + DISCARD lines on those pages), `dbg_xdata.read_byte / read_bytes / read_blocks`, `p037_test.rd`, `rtd_dbg_read.py`. Scans with it carry `#read_fix=dword-discard`.
- Store rule: old (unfixed) observations of the affected pages are removed whole (live / regdump: the live set; isp: the isp set): lanes 1-3 are right in the probe, but old scans also read page windows (offsets C0..FF of 88 / 8A / 8B / 8E read as 00C0..00FF in fixed scans) that the old values do not match, so right and wrong cannot be separated. `regmap_strip_behind.py` applied it once (header `#read_behind_stripped=pages=..; N values`), `regmap_import.py` applies it to any JSON without `read_fix`, `regmap_build.py --check` fails on a file that still holds such values. Time-varying registers on those pages stay time-varying.
- Not the latch (`other` in `read_behind.tsv`: 23 50 67 8C 94 C1 CC): a read at another address changes the value read; port-like or read-sensitive registers.
- Cause (experiments `scripts/reg_behind_cause.py`, unit 1 AWT26110001 live 100 kHz byte path + 0x3C, MCU running, 2026-11-19T09:31 +11:00, pages A0 A8 8E CE, 12 dword pairs each, 10 008 reads):
  - [hw] Model: a per-page one-dword read cache. The first access to a dword that is not the cached one returns the cache (old dword, same lane); the dword is fetched during/after that access. Any lane read first is stale (lane 0 / 1 / 2 / 3 first: 0 of 12 ok each, on 8E / CE all four lanes); every later lane of that dword, in any order (0123, 3210, 1023, 2301), is right.
  - [hw] No time dependence: a gap of 0, 1, 10, 100, 1000 ms between the settling read and the new dword changes nothing (8E / CE 0 of 12 ok at every gap; the re-read after the same gap 12 of 12 ok). Not a prefetch that finishes in time; not the I2C speed (reads are >= 300 us apart even at the byte path).
  - [hw] The cache is not the global register bus: an intermediate read of a fast page (01, 06), of the mirror instance (A0 <-> A8, 8E <-> CE) or of a sibling page (8E -> 88 / 8A, CE -> C8 / CA) leaves it intact (Y0 still returns X in 12 of 12). A read of another dword of the same page replaces it (8E / CE: 4 of 4 informative reads returned the intermediate dword's lane).
  - [hw] Block path (0x3C, 4 bytes at the dword): byte 0 stale (12 of 12), bytes 1-3 right; the same block after one priming read of any lane of that dword (byte 2): all four right. So the block artifact is the same cache, not a separate effect: one read of the dword before the block (any address) cleans it.
  - [hw] Unmapped offsets of a page (88C0..) return the cached lane too (value follows earlier reads): this is the `other` class of the pages above, not a second mechanism.
  - [spec] FFBC `mcurd_max_cycle[4:0]` (reset 0x0F, live 0x0F on unit 1) = "limit the maximum cycles of clock gating when executing a read of Mout": the MCU is stalled until the register read returns, at most N cycles. Our own sweep: <= 10 stops the debug link (reads of normal pages already miss), 12 / 14 healthy (`docs/osd-write-sweep.md`). Hypothesis H1: the blocks on these pages answer later than 15 cycles (DDR clock domain), the stall ends first, the MCU takes the old read-data latch; the new data lands in the cache afterwards. The ISP path (MCU halted, hardware reads, own wait) shows it only on 88..90 / C8..D0 (the slower blocks), A* pages clean: matches a fixed wait that is long enough for the PHY blocks only.
  - Not tested on hardware: any register write (H1 needs `FFBC` > 0x0F on the test unit); MCU clock dependence.
  - Page 88 on unit 1: X -> Y reads were right in all 12 pairs (unit 3 probe: 72 % stale) but X -> W -> Y was not; unexplained, do not generalise from 88.
  - Clean read today: any read of the dword first (discard), then the wanted lanes; block: one priming read per dword. A 32-bit `ScalerGetDWord` (4 x MOVX, ascending) gets the MSB (lowest address) wrong and the other three right. The kept SDK only writes these pages (`ScalerSetDWord`; no `ScalerMaskSet*` on them in `RL6449_Series_DDR2.c`), so no SDK read-modify-write is hit; our own RMW on these pages would be.
- Probe: `reg_behind_probe.py --unit 3 [--isp]` (read-only; ISP halts + resets the unit: test unit only). Probe data stays in `tmp/regs/live/`.

## Add an observation
```
python scripts/regmap_import.py tmp/regs/AWT26110003-20261119-120000.json        # ISP dump (pages + ports)
python scripts/regmap_import.py tmp/regs/live/AWT26110001-A-20261119-001333.json  # scripts/reg_live_scan.py output
python scripts/regmap_import.py dump.json --label 4k60 --state frozen --method regdump --uptime 812
python scripts/regmap_build.py --write      # recompute the obs_* columns, then commit the obs file + regs.tsv
```
Formats: ISP `{serial,time,pages:{PP:[256]},ports:{PPAA:{idx:val} | "AA:DD":[vals]}}` (a `"2A:2B"` pair is taken as page 00); partial `pages:{PP:{OFF:"hh hh"}}`; live scan `{serial,unit,label,start,pages:{PP:[256|null]},excluded,...}`. JSON without register pages (gpio, power-state, DPCD) is skipped. A new source format = a new branch in `regmap_import.convert`, with a fixture in `tests/test_regmap.py`.

## Add a register note
```
python scripts/regmap_build.py --set FFED role="..." class=config status=known test_id=T-L result="..." evidence="role=spec;result=hw" issue='#236'
python scripts/regmap_build.py --set-field 'FFED[5:2]' name=flash_clk_div role="..." status=known evidence="role=spec"
```
Or edit the hand cells in the TSV directly, then `--write`. A new row needs only its key.
- A new test: one line in `tests.tsv` (`state` = `pending` / `proposed` / `done`); OT / T ids stay in `docs/osd/open-items.md`.
- After a test: fill `result` (value + date + unit + doc link), set `status`, set the test `state` to `done`.

## Commands
| command | does |
|---|---|
| `regmap_build.py --write` | regenerate both files; hand columns kept by key; refuses to write while a hand column is invalid |
| `regmap_build.py --check` | fail on: stale file, bad class / status / tag / test id / issue, field without register row, observation file without header, HDCP key in the store, size over budget |
| `regmap_build.py --stats` | counts by regdb status and triage status |
| `regmap_query.py 06A4` | one register: columns, fields |
| `regmap_query.py --undocumented-nonzero [--changing]` | regdb gives no named field, observed nonzero (and changing inside one state) |
| `regmap_query.py --candidates [sensor]` | status `candidate`, optionally one class |
| `regmap_query.py --i2c [TEXT]` | i2c.tsv rows (optionally filtered) |
| `regmap_query.py --no-test` | candidate / unknown rows with no test_id: tests still to be written |
| `regmap_query.py --tests` | candidate / unknown rows and fields whose test is not done, by test id |
| `regmap_query.py --page A7`, `--status`, `--class`, `--grep`, `--varying`, `--tsv`, `--obs KEY` | filters / raw output / every observation of a key |

Gate: `fw_gates.py` entry `regmap` (= `regmap_build.py --check`, ~4 s); pytest `tests/test_regmap.py`. Log: `tmp/logs/regmap.log`.

## Rules
- A fact lives once: here for registers; docs link the key (`FFED`), they do not restate the value or role.
- Seed only what a source states; the evidence tag says which. A guess is tagged `guess`, never `spec`.
- Generated column wrong? Fix the generator or the source (regdb, SDK, observation), never the cell.
- Superseded results are replaced, not annotated (the doc / issue holds history).
- Generated header names stay regdb names (`gen_regnames.py`, #161); `our_name` only reports them.
