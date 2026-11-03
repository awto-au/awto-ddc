# awto-ddc

Global rules apply (`~/.claude/CLAUDE.md`). Repo specifics:

- Writes to a monitor's flash/ISP are never default: dump twice and compare first; `--allow-write` style flags stay opt-in.
- Vendor binaries, flash dumps, extracted/recovered material and conclusions about vendor-software design stay in `~/vendors/realtek/`; this repo holds our own tools, measurements and public-source notes.
- Repo root in scripts: `$AWTO_DDC_REPO` → file-relative. Logs: `./tmp/logs/`.
- Findings and open questions: GitHub issues (origin: awto-dan#86), not chat.
- Reversing conventions (confidence tags): awto-dan `docs/embedded/reversing/README.md`.
