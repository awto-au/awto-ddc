# RTDCustomerTool extraction: version/layout gate

- Every parser calls `rtd_gate` before trusting a file. Unknown version or layout drift = refuse, loud.
- Static only: reads bytes, never runs the vendor tool.
- Files: `scripts/rtd_gate.py` (module + CLI), `re/formats.json` (registry), `scripts/rtd_extract_all.py` (driver).

## Registry `re/formats.json`

- Per kind: `DB.bin GPIO.bin DPCDDB.bin IPDB.bin FlashSet.dat Flash.dat SWREN.dat PE-resources ReadAll.txt version.txt`.
- Per kind, per format version (DB.bin `1`/`3`, GPIO.bin `2`, flash `.dat` keyed by 6-byte ident hex, others `-`):
  - `status`: `supported` or `known-unsupported` (gate says "known variant, no parser", driver skips).
  - `expect`: derived-signature key -> exact value, allowed list, `{min,max}` or `{regex}`. Mismatch = fatal.
  - `expect_warn`: same shape, mismatch = warning only.
  - `layout`: human description (strides, offsets) kept next to the checks.
  - `validated_tool_versions`: tool builds the layout was checked on. File passes but build not listed = WARN.
  - `reference`: path, size, sha256 of one known-good file (byte-identical = noted in gate result).
- `tool_versions_seen`: driver prints "NEW TOOL VERSION" when the root's `Vx.y_YYYYMMDD` is not here.
- Current coverage: V3.7_20190114 (flash `.dat`, SWREN, exe only; no scaler DBs in that zip), V3.8_20221101 (everything).

## Gate API (`import rtd_gate`)

- `gate(path, kind=None, warn_only=False, tool_version=None) -> GateResult{ok, state, version, status, warnings[], fatal[], notes[], signature}`
  - Raises `GateUnsupported` (known variant, no parser) or `GateError` (unknown version, bad magic, drift) unless `warn_only`.
  - `state`: `ok | warn | fail | unsupported`.
- `gate_or_exit(path, kind, warn_only=None, log=print)`: parser helper. Exit 3 on refusal, 4 on unsupported. `$RTD_GATE_WARN_ONLY=1` or `--gate-warn-only` downgrades.
- `compute_signature(path, kind=None)`: magic, version, size, sha256 and `derived` facts (hdr_size, stream record counts, pool base, pin count, flash record stride/remainder, PE sections, ReadAll page counts).
- CLI: `rtd_gate.py gate|sig|diff|register <file> [--kind K] [--tool-version V] [--warn-only]`.
- Retrofitted: `rtd_db_parse.py` (DB.bin + ReadAll.txt), `rtd_gpio_parse.py`, `pe_resources.py` (each PE). All accept `--gate-warn-only`.
- `rtd_flashdb_parse.py` is not in the repo yet: it must call `rtd_gate.gate_or_exit(path, "FlashSet.dat")` / `"Flash.dat"` / `"SWREN.dat"` first. The driver already invokes it as `rtd_flashdb_parse.py <PlugIn dir> <out.json>` once present.
- Scripts run as `python -I`, which drops the script dir from `sys.path`; parsers insert it explicitly before `import rtd_gate`.

## Driver

- `python -I scripts/rtd_extract_all.py <RTDCustomerTool root> [--out re] [--warn-only] [--strict] [--gate-only]`
- Order: gate every file, print table (file, kind, version, state), write `<out>/gate_report.json`, then parse.
- Any FAIL stops the run and names the drifted file (exit 3). `--warn-only` continues; `--strict` stops on WARN too.
- Outputs: `regdb/<chip>.tsv.gz`, `gpio/<chip>.gpio.tsv.gz`, `pe/<tool-version>.tsv.gz`, `flashdb/<tool-version>.json`.
- Log: `tmp/logs/rtd_extract_all.log`, `tmp/logs/rtd_gate.log`.

## Gate strength by kind

- DB.bin v1: independent stream walk (tail/field recognisers learned from first record): record counts, `nf` agreement, bit-range sanity, pool base and last `kt` inside file.
- GPIO.bin v2: chip tag, pin count, pin region inside file. Section chain to EOF is only enforced by the parser itself.
- FlashSet.dat: `(size-6) % 0x48 == 0`, `records == count_u16 + 7`, ASCII names (soft).
- Flash.dat, SWREN.dat, version.txt: ident/size/first-name only; `reference` sha256 gives an exact-match note.
- PE: MZ, PE sig, x86 PE32, resource directory present.
- DB.bin v3, DPCDDB.bin, IPDB.bin: magic + version only (known-unsupported).

## Onboarding a new tool version

1. Put the new zip in `~/vendors/realtek/sources/`, unpack to its own dir named `RTDCustomerTool_Vx.y_YYYYMMDD`.
2. `python -I scripts/rtd_extract_all.py <root> --gate-only` (gate table only; shows NEW TOOL VERSION).
3. For each FAIL/WARN file: `python -I scripts/rtd_gate.py diff <file>` prints computed signature vs registry (`ok`/`DIFF` per key, plus unconstrained derived values). Unknown version: it lists what each known version expects.
4. Decide per file:
   - Only the tool build is new, layout checks pass: `rtd_gate.py register <file> --tool-version Vx.y_YYYYMMDD` (adds to `validated_tool_versions`, `tool_versions_seen`; add `--reference` to replace the reference file).
   - New format version or drifted stride: reverse the layout (document in `db-bin-format.md`), add a new version entry (`status: known-unsupported` first if no parser yet), tighten `expect`, then update/extend the parser and set `supported`.
   - Same version number but changed layout (a `DIFF`): treat as a new format; do not loosen `expect` to make it pass.
5. Rerun the driver on the old and new roots; both must gate clean and the old outputs must be byte-identical (`regdb/*.tsv.gz` use `mtime=0`).
6. Update the Scope line in `db-bin-format.md` if parser coverage changed.
