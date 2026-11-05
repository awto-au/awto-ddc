# awto-ddc

Global rules apply (`~/.claude/CLAUDE.md`). Repo specifics:

- Writes to a monitor's flash/ISP are never default; `--allow-write` style flags stay opt-in.
  - Dump twice and compare only before the FIRST write over vendor firmware; keep that one original per unit in `~/vendors/realtek/analysis/dumps/`.
  - Reflashing our own builds: `rtd_flash_image.py ... --write --no-backup`. Never keep dumps of our own builds (Dan, 2026-11-05).
- Vendor binaries, flash dumps and the Ghidra project (firmware bytes) stay in `~/vendors/realtek/`; this repo holds our own tools, measurements, notes and names TSVs.
- **Exception (Dan, 2026-11-04):** full JSON extracted from Realtek's tool data (register databases etc.) may be committed under `re/regdb/`, on condition this repo stays PRIVATE. Before ever making it public: remove `re/regdb/`, the register descriptions in docs and `re/jxc-4k/` from history or scrub them.
- Repo root in scripts: `$AWTO_DDC_REPO` → file-relative. Logs: `./tmp/logs/`.
- Findings and open questions: GitHub issues (this repo; tracking issue #1), not chat.
- Reversing conventions (confidence tags): awto-dan `docs/embedded/reversing/README.md`.
- **Firmware = build on the Realtek RL6449 SDK (Dan, 2026-11-04):** we write board/panel/project/OSD/DDC layers;
  Realtek Kernel source + precompiled `.LIB`s are linked as-is. Board facts come from the old firmware (RE)
  and RTDCustomerTool data. Consequence: this repo stays **PRIVATE permanently** (Realtek confidential code).
  - Host-side tools (`scripts/`) stay clean-room: from hardware facts (regdb + measurements), cite the fact.
  - GPL projects (ORTD2662 etc.) are understood, not pasted.
