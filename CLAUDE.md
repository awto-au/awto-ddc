# awto-ddc

Global rules apply (`~/.claude/CLAUDE.md`). Repo specifics:

- Writes to a monitor's flash/ISP are never default: dump twice and compare first; `--allow-write` style flags stay opt-in.
- Vendor binaries, flash dumps and the Ghidra project (firmware bytes) stay in `~/vendors/realtek/`; this repo holds our own tools, measurements, notes and names TSVs.
- **Exception (Dan, 2026-11-04):** full JSON extracted from Realtek's tool data (register databases etc.) may be committed under `re/regdb/`, on condition this repo stays PRIVATE. Before ever making it public: remove `re/regdb/`, the register descriptions in docs and `re/jxc-4k/` from history or scrub them.
- Repo root in scripts: `$AWTO_DDC_REPO` → file-relative. Logs: `./tmp/logs/`.
- Findings and open questions: GitHub issues (this repo; tracking issue #1), not chat.
- Reversing conventions (confidence tags): awto-dan `docs/embedded/reversing/README.md`.
