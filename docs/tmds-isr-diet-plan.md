# TMDS ISR diet: unit 3 measurement plan (#256, #147)

- Change: `SetPhy_EXINT0` block moved from EXINT0 to the main loop (`docs/main-loop-pacing.md` section 0). Image: see the commit; flash by Dan only.
- Setup: unit 3, HDMI source on D2 (or D3), `./dev.py` sync log running. Same host, cable and mode before / after; flash the parent image (origin/main) first, then this one.

## A. HDMI lock time (monitor-side, no host involvement)
- Per lock: timestamp of the HDMI signal-detect event to the `TMDS lock` / stable event in the sync log (`scripts/sync_log.py`), plus the input rate row.
- N = 20 locks per image: source hot-plug by `./dev.py` cable / HPD toggle on the source, or source output off/on; same mode each time.
- Report: median / max lock time and the count of no-lock or re-lock loops (a repeat of the lock event without a cable event).
- Pass: median within one main-loop pass (1 ms free-run) of the before value, no re-lock loop, max not worse than before + 10 ms.

## B. Timer2 tick loss across a lock
- Read via `./dev.py dbg-read` the diag block tick counter (`t2`) and the ms counter before and after each lock, plus wall time from the host.
- Tick loss = wall ms - (t2 delta); N = 20 locks per image.
- Pass: after-image loss per lock < 1 ms (before: ~5.5 ms expected from the ISR).

## C. Regression
- `./dev.py health` on the unit after the locks (headroom row, input row), ACTIVE 1080p60 and 4K59.940 sources.
- Rest mode left per memory rule (unit 3 at 4K59.940 / 1080p60).
