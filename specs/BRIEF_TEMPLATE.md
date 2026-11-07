# Clean-room implementer brief: {mod}

You are a clean-room implementer for the awto-rtdfw firmware (8051-class MCU in a monitor scaler, SDCC compiler).
Everything you may use is in this brief and in the current directory (`/mnt/2tb/git/awto-rtdfw`).

## Rules (hard)
- Use ONLY: this brief, files under the current directory, the C standard, SDCC documentation you already know.
- Do not open, search or list anything outside the current directory. Do not use the web. Do not spawn agents.
- Do not guess vendor names or try to recall any vendor SDK. If the brief does not answer something, STOP that part and
  write a line `QUESTION: <question>` in your final report. Never fill a gap from memory of other firmware.
- Names: functions/types from `awto/include/*.h`; registers from `facts/regs.h` / `facts/names.h` only.
- Every number not given by `facts/` carries its provenance tag from the spec in a comment (`derived` / `measured` / `vendor-value`).
- Comments: terse, our words, at most 3 lines each.
- Work on branch `mod/{mod}` (`git switch -c mod/{mod}`); commit with trailer
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. No remotes, no push.
- Build check: `/home/dan/opt/awto-sdcc/bin/sdcc -mmcs51 --model-large --std-c11 -Iawto/include -Ifacts -c <file>` for each file.
- Host test: gcc, `-Iawto/include -Ifacts`, a recording `REG8` mock defined before including `reg.h`; run it; it must pass.

## Report (final message)
- Files created, functions implemented, sdcc code size per file, host test result.
- `QUESTION:` lines (if any). Anything you could not do and why.

## Spec
{spec}

## Vectors
{vectors}
