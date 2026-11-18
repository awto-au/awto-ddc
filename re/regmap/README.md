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
