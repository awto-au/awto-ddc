# awto-rtdfw

Clean-room firmware for the RL6449-based JXC-4K monitor board. LOCAL repo: no remote, no push, until Dan says so.

## Layout
- `awto/include/` our module interfaces (written by the process owner, in our words).
- `awto/<mod>/` module code, one directory per spec (`specs/<mod>.md` lives on the spec side, not here).
- `facts/` GENERATED register facts (`facts/regs.h`, `facts/regs/p<PP>.h`, `facts/names.h`). Never hand-edit; regenerate.

## Clean-room rules (all contributors)
- Inputs allowed here: the brief (spec + interface + facts + oracle), this tree, public datasheets/standards, the C/SDCC docs.
- Never open: the vendor SDK (any copy, mirror or worktree), awto-ddc (any checkout or worktree), `~/vendors/realtek`,
  the asmlib branch, Ghidra projects, firmware dumps, decompiler output.
- Never paste vendor names, identifiers, comments or code shapes. Names come from `awto/include` and `facts/names.h`.
- A question the spec does not answer goes back to the spec writer as a question; never "go look".
- `facts/` is register FACTS only: page, address, index, bits, reset, access. No vendor names or descriptions.
- Every vendor-derived number in code carries its provenance tag in a comment: `derived`, `measured`, `sdk-value` or `dahua-value`.
- `cleanroom_lint` must pass on every commit (SDK identifiers / 6-token n-grams; `facts/` exempt).
- Commits: normal local git identity, trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` on agent commits.

## Status
- Not public. Publishing needs: Dan's sign-off on `facts/`, every `sdk-value` and `dahua-value` replaced by a `measured` one, an SDK-free build.
