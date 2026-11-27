# PC monitor menu: GUI (monitor tab of the OSD editor)

Dated 2026-11-20. Design chosen by Dan: "Tree + unit strip". Code: `tools/osd_editor/monitor.py`, `unit_jobs.py`.
Launch: `python3 tools/osd_editor/run.py --monitor` (opens on the monitor tab) or toolbar "monitor"; `run.py --headless` = no window (offscreen), control port only.

## Registry
- `scripts/settings_table.py`: 118 rows, 15 pages (picture 4, colour 11, sixaxis 12, display 6, input 10, kvm 3, signal 11, power 10, osd 13, panel 7, debug 7, audio 5, system 3, service 6, info 10).
- 54 int / 29 enum / 29 bool / 6 action; 10 `ro`, 11 `risky`, 8 `reboot`.
- group == page name, so the tree has two levels: page > setting.

## Layout
- Top: unit strip (one button per unit) + search box.
- Quick strip: volume (VCP 0x62, live), mute (0x8D), backlight (VCP 0x10, live), input select (`scripts/kvm.py`), screensaver start / stop (VCP 0xEB).
- Left: tree page > setting (counts per page; `[risky]`, `[action]`, `[ro]` tags).
- Middle: form of the selected page, one `SettingRow` per row; selecting a setting highlights its row and shows id, VCP code, range, default, flags, note.
- Right: host time, health, action log, boot / sync log, last output.
- Sync table (`monitor.sync_rows`): the decoder's columns, never its own arithmetic: time (host clock / `u` uptime / the ISO stamp of a decoder without the real column), +delta (`sync_log.fmt_delta`), line. Episode start rows (`-- text --`) and `relative time reset: counter wrap` rows red, `--- boot N` grey; raw `[fw .. ms, ring ..]` in the tooltip; delta > 100 ms red. Parses the ring, `--dram` and the log-times row form (test: `test_smoke.py` `sync_rows_on_decoder_output`, input `sync_fixture.py` built with `scripts/sync_log.py`).
- Bottom: status line of the selected unit (see "Status line").

## Unit strip
- Source: `scripts/devices.json` (names, serial, input, `test`). Button: hotkey number, unit, last 4 of serial, input, status dot.
- Hotkeys: Ctrl+1..9 anywhere on the page, plain 1..9 when focus is not in a text field, Ctrl+Tab next unit, Ctrl+F search.
- Dot: green = probe answered, amber = a job queued or running, red = no answer or monitor not detected, grey = read-only unit (not probed).
- Probe policy per unit (`monitor.probe_policy`): `ddc` (HDMI / DVI) = `dev.py ddc get 0x62 --unit N` (read-only, EDID guard inside dev.py), per idle unit every 15 s while the tab is visible; the reply also refreshes the volume value.
  - `light` (connector `card*-DP-*`, I2C over DP AUX) = no DDC/CI at all: dot green when the sysfs scan sees the unit's EDID; Get all / quick read / sets stay on demand.
  - `dev.py ddc` / `ddc_ctl.py --bus N` no longer runs a full `ddcutil detect` (all buses incl. AUX, ~1 s): the connector comes from the DRM sysfs `ddc` link, one `ddcutil --bus N getvcp`.
  - Unit 2 went black 2026-11-20 23:00: brightness set to 0 from the GUI (15 sets); the probe was tested and did not blank the unit; cause of the POWER-key pair near 23:02 unknown.
- Auto-detect: EDID serials from `/sys/class/drm/*/edid` (kernel copy, no I2C from the GUI), rescanned every 15 s (hotplug). A unit whose serial is not seen is red and not probed or read. No known serial seen at all = no scan result, devices.json stands.
- Per-unit state in memory (values, touched-not-set values, last read, tree node, output, banner): a switch is a view swap, no read.
- "Get all" runs only on the button, the live-refresh checkbox, or when a selected unit's view is older than 60 s (or never read).
- QSettings (`awto/osd_editor`): last unit, tree node per unit.
- Only `test=true` units are writable; other units grey out every control and `run()` refuses.

## Jobs
- One `QThreadPool` with one worker per unit (`unit_jobs.UnitQueues`): different units run in parallel, one unit's jobs one at a time (one bus).
- Backend stays `dev.py` / `scripts/` subprocesses with per-call limits (`LIMIT_S`); debug link on/off and EDID guard are inside dev.py. No I2C in the GUI.
- A failed or timed-out call sets a per-unit red banner and the unit's dot red.

## Job limits (awto-ddc#358)
- `synclog` jobs: limit sized per request, `gui_client.synclog_limit`: 1.25 x (`SYNC_BASE_S` 2.2 s + entries / `DRAM_RATE` 77 per s). Logged in the job's started line with the arithmetic. The port request and client waits are that limit + `SERVER_LIMIT_S` (queueing, as any request).
  - entries: `--dram --last K` = K (default 64); `--all` / `--boot` / `--since` = `AWTO_DLOG_SLOTS` (32768: 535 s); `--whole` = `AWTO_SYNC_N` (88); one episode = `AWTO_SYNC_WRAP` - 1 (175, read from the DDR).
  - Measured 2026-11-27, unit 3, image `55cbc742`, through the app: `--dram --last 200` 202 bursts in 2.6 s, job 3.9 s; `--last 1000` (968 entries) 1002 bursts in 12.9 s, job 15.1 s: 77.7 entries/s, fixed part 1.3-2.2 s. One-episode ring read 1.8 s.
  - Limits then: `--last 64` 3.8 s, `--last 200` 6.0 s, `--last 1000` 19.0 s, one episode 5.6 s. The old fixed 4 s killed `--last 200` (rc 124).
  - No stall guard: sync_log prints nothing until the read ends. A progress line from the DRAM read would allow one (asked of the decoder owner, #358).
- `note` keeps the old 4 s.

## Log view (awto-ddc#358, Dan 2026-11-27)
- Window page "log" (toolbar, or `run.py --log`): one unit's whole DRAM log (up to `AWTO_DLOG_SLOTS` 32768 lines), not the 88-line ring view. Code `tools/osd_editor/log_view.py`.
- Columns: index (absolute DDR index), time, +delta, line. Time = host clock of the read join (`poll_wall`, this boot, marked `~`) or `u` uptime of the line's boot. Delta / start from `sync_log.dram_deltas` / `is_start` (32-bit fw ms: exact over any gap; no wrap row on the DRAM path).
- Red rows: episode starts (and `relative time reset: counter wrap` if the decoder prints one); grey `--- boot N ---` before each boot counter. Filter box (separators stay), jump list (boots + starts), Copy (selected rows, else all shown), Save... (shown rows).
- Source: `dev.py synclog --dram --json` (SYNCJSON) through the unit's job queue, rows deduplicated by index; a new DDR log generation drops the old rows.
  - History: newest `CHUNK` 300, then older chunks of <= 300 down to the oldest slot, one job at a time. Needs a range read in the decoder (`--since A --count K`, asked of its owner); without it one `--last 1000` job and the view says "newest 1000 only".
  - Follow: every `FOLLOW_S` 10 s, `--since next [--count 300]`.
- Bus budget (measured 2026-11-27, unit 3, through the app): `--since` poll with a few new lines = 1.2 s job, debug link held ~0.4 s: ~4 % of the time at 10 s. A 300-entry chunk: 3.9 s at 77 entries/s + 2.2 s fixed (limit 7.6 s).
- Yields: no read while the page is hidden (a headless app never reads), while the unit flashes, has other jobs, or has a log read in flight. A port `flash` that finds a log read running holds new reads (`log_hold`), waits for it (<= its limit + 2 s), then starts.
- Real data (unit 3, 968 entries, 8 boots): lines before the Timer2 start carry a `poll_wall` from the unsigned ms (hours off); the view shows them as uptime. Decoder fix asked in #358.
- Tests: `test_log_view.py` (fake DDR log of 1601 lines: chunked history, follow, dedupe, filter / jump / save, fallback, yields, screenshot `tmp/scratch/qt/log-view.png`); `--snapshot FILE` renders a captured `synclog --dram --json` output (`log-view-real.png`).

## Confirm
- `risky` rows (11) and action rows (6) ask before Set / Run (dialog names the unit and row; notes a needed reboot).

## Search
- Substring over name, label, id and VCP code (`0x10`, `10` or decimal); non-matching rows and empty pages are hidden, page counts show `matches/total`, Enter selects the first match.

## Tests
- `tools/osd_editor/test_monitor_gui.py` (fake backend, offscreen; strip, hotkeys, tree counts, search, confirm, read-only, parallel vs serial queues, remembered unit, detect + probe, status line, screenshot).
- `tools/osd_editor/test_smoke.py` (editor tabs, monitor page get / set / quick / banner).
- `tools/osd_editor/test_control_port.py` (port: commands change model and view, save read back, failed call, parallel / serial queues, events, socket perms, auto-start, thin CLI, no-app error, `--direct` refusal, raw i2c, async flash, rc and gate refusal, detached survival + re-attach, tree mismatch restart / busy refusal, second app exit + lock, sized synclog limit; fake backend and `fake_flasher.py`). `tests/test_flash_job_stale.py`: stale records, zombie. `tests/test_gui_client.py`: client translation, flash progress parsing (no Qt).
- Run: `QT_QPA_PLATFORM=offscreen tools/osd_editor/.venv/bin/python tools/osd_editor/test_monitor_gui.py`.

## Live pass 2026-11-20 (units 1, 2, 3 read-only, locks held, GUI on Dan's desktop)
- Probe (`dev.py ddc get 0x62`): 0.55-1.2 s alone, 1.2-2.4 s with other units' calls in flight. Unit switch (view swap): 1-7 ms. Scan (sysfs EDID, UI thread): <1 ms. Max UI-thread stall over 50 s of live use: 55 ms.
- Every `dev.py ddc` call runs `ddcutil detect` over all buses: three units in parallel were no faster than in turn (1.6 / 2.4 / 3.0 s vs 2.3 s) and hit the 4.5 s detect limit (rc 124 / rc 2). Fix: ddc calls of all units are serialised in `unit_jobs.DDC_LOCK` (limit starts when the call starts); mailbox jobs (`settings list`) stay parallel per unit.
- Quick read = ONE call `dev.py ddc get 0x62 0x8D 0x10 0x60 0xEB` (ddc_ctl `get` takes several codes, one detect): 1.9-2.5 s per unit, was 5 calls, 9-12 s. A failed read now returns rc 1 (was rc 0 with an `ERROR` line).
- Get all (`settings list`) fails on all three units today (units 1, 2: "mailbox magic missing", old image; unit 3: map `AWT26110003-7bce876+-be.map` gone with its worktree). Failing call 0.9-2.0 s; three in parallel 2.0 s wall vs 2.8 s one after another. Banner names the reason line; it is not "no answer" and the dot stays green.
- Probe dot needs 2 failed probes in a row to go red (`dev.py` EDID bus lookup misses now and then, #76).
- Auto-detect: units 1, 2, 3 found by EDID serial; a fourth monitor (Philips, serial `UK52307000611`) shows as read-only "unknown".
- Values read live: volume 100 / 100 / 50, mute On on all, brightness 64 / 100 / 51, input D2 / D1 / D2 (unit 3 `devices.json` says DP, unit 2 says HDMI: the file's `input` field is not updated by the GUI), screensaver Stop on all.
- Not tested live: the real Wayland window cannot be grabbed by an agent; screenshots are offscreen renders (`tmp/scratch/qt/monitor-gui.png`). The live window run showed no stall and the offscreen grab of it matched.
- Limits (stated): probe `ddc` 5 s, quick read `ddcmany` 10 s, Get all `list` 20 s, health 13 s; expiry = TERM, banner + red dot, UI never blocks (all calls in worker threads).

## One-click rows (#275, 2026-11-20)
- bool rows (29) = switch (one checkable button showing off / on); enum rows with 2..4 options (20) = segmented buttons, all options visible; enums with 5+ options (9) = combo box + Set; int rows (54) = slider + Set.
- A click sends exactly one write, then one read-back (`settings get NAME`, or `ddc get` for volume / mute); the row shows what the unit reports.
- Cancelled confirm (risky / action rows) or failed write puts the widget back to the last known value.
- Quick strip: mute = switch, input = D1 / D2 / D3 segmented (one click runs `scripts/kvm.py`), screensaver = combo + Start / Stop (3 options).
- Greyed on read-only and unknown units.

## Advanced pages, unknown units, last read
- "show advanced (debug, service)" under the tree: pages hidden by default (tree, form, search), remembered in QSettings `monitor/advanced`.
- Monitors seen by EDID and not in devices.json: strip button "unknown (ro)", grey dot, read-only, never probed; removed when unplugged.
- Strip tooltip: last successful read (any kind) as ISO time, or "not read yet".

## Control port (#276, 2026-11-20)
- Writes (set / run / save / kvm / saver / note / host-time / vcp set / i2c with write bytes / passthrough / flash) need an explicit `unit` or `serial`: no fallback to the window's selected unit, error "a write needs an explicit unit or serial". Reads keep the fallback.
- The GUI app is the only owner of the unit buses; scripts, agents and the human use its port. Code: `tools/osd_editor/control_port.py` (server), `scripts/gui_client.py` (client), `scripts/unit_ops.py` (the device ops), `scripts/flash_job.py` (detached flash).
- One implementation: `scripts/unit_ops.py` (ddc, settings, synclog, note, kvm, i2c) + `dev.py _flash_direct`. The app's workers run `dev.py <cmd> --direct` (env `AWTO_GUI_WORKER=1`). `dev.py ddc / settings / kvm / synclog / note / i2c / flash` are thin port clients.
- No fallback: no app answering = dev.py auto-starts `run.py --headless` (detached, log `tmp/logs/gui-headless.log`), prints `gui: starting the GUI app headless ...` and polls the socket every 0.1 s up to `START_WAIT_S` = 3 s, then FAILS naming that log (no silent retry; an app process that exits while starting fails at once with its rc). Nothing runs on the unit.
  - Bound: measured 2026-11-20, 5 starts each: warm 0.31 s max; cold (venv, Python and repo files evicted from the page cache with `posix_fadvise(DONTNEED)`, no root needed) 0.40 s max; cold with every core busy 1.11 s max. 1.25 x 1.11 = 1.4 s is under the 3 s floor, so the floor is the bound.
  - A worktree without `tools/osd_editor/.venv` builds it on its first start (uv, network): far beyond the bound; run `python3 tools/osd_editor/run.py --headless` once by hand there.
- `--direct` = for the app's workers and for recovery by a human with the app stopped. While the app answers, `--direct` writes from anything but a worker are refused (message: use the port without `--direct`). Never chosen automatically.
- Socket: `$XDG_RUNTIME_DIR/awto-gui.sock` (fallback `tmp/run/`), mode 0600; server checks `SO_PEERCRED` uid (other user = refused); client refuses a socket not owned by it or open to others. Env `AWTO_GUI_SOCKET` overrides the path.
- Wire: one JSON object per line. Request `{"id", "method", "params"}`; reply `{"id", "ok", "result" | "error", "elapsed_ms"}`; job-based replies carry `rc` + `output`. `subscribe` turns the connection into an event stream (`select`, `status`, `job`, `flash`, `flash_done`).
- Threads: connection threads parse and wait; every request runs on the UI thread; device calls go through the per-unit queues (parallel across units, serial per unit, ddc calls serialised app-wide). Request limit 45 s (write + read back + save, each <= 5 s, plus queueing behind two other units' ddc calls, x1.8): expiry = error reply, jobs still finish. Idle headless app exits after 900 s without a request (no lingering daemon), never while a job or flash runs.
- The window follows the port: a command with a unit selects it; `state` dumps what the window shows.
- Writes only for `test=true` units (the page refuses others, with the reason in the reply). Reads of other units are refused too (dev.py needs `--force` there).

### Flash state is derived, not remembered (#276 follow-up)
- The app derives "flashing" on every query (quit, flash, job refusal, strip dot, `jobs`) from the unit lock + the job file (`tmp/flash_jobs/<serial>.json`) + a live check of the wrapper pid (a process that is `flash_job.py`, not a zombie, not a reused pid). No cached belief.
- A tracked job the disk no longer backs (file gone, replaced by another job, wrapper dead without rc) is closed as rc 255 with a log line (`closed as stale`) and a `flash_done` event; `flash_job.load()` also writes rc 255 + error into a record whose wrapper pid is gone.
- Cause of the divergence: the app cached `flash` per unit and kept a job "running" until the job file said otherwise; a deleted file never did, and an unreaped wrapper (zombie) still answered signal 0. Wrappers are now reaped and zombies count as dead.
- Quit and the idle exit (900 s) use the same derived state, so a stale job cannot block them. A refusal names the job id, pid and age.
- `./dev.py gui jobs`: per tracked job unit, job id, wrapper pid, alive, age, rc, the job id/rc currently on disk, log path; `--json` for the raw reply.

### Commands (`./dev.py gui [--serial S | --unit N] [--hdmi | --dp] [--confirm] [--json] CMD ...`)
- `ping`, `list` (serial, status, pending, flashing %), `state` (unit, page, node, banner, quick widgets, every row's widget / unit value / dirty), `select [--page P] [--row NAME]`.
- `get NAME... | --all | --quick`: value + label read from the unit. `set NAME VALUE`: value or option label (`on`, `2.2`), range checked, read back, `verified`. `run NAME --confirm` (action rows). Risky / action rows need `--confirm` (replaces the dialog).
- `save [NAME...]`: `settings save`, then reads the named rows back. `kvm TARGET` (`hdmi-1`, `D2`, `dp`, `next`, `here`): kvm.py, then VCP 0x60 read back vs expected. `saver NAME | stop`. `health`, `synclog [--whole]`, `host-time`, `note TEXT`.
- Raw: `vcp get CODE...`, `vcp set CODE VALUE` (read back), `i2c ADDR [BYTES...] [--read N]` (7-bit; write, repeated start, read; `scripts/i2c_raw.py` via `dev.py i2c`, EDID-proven bus), `ddc ARGS` (list / sleep / wake / brightness).
- `events`: print the event stream. `flash-status`, `quit` (refused while a flash runs).
- Flag form, run in order, a failed step stops the rest: `--kvm T`, `--set NAME=VALUE`, `--volume N`, `--mute on`, `--brightness N`, `--saver NAME`, `--get NAME`, `--save` (verifies everything set before it), `--i2c ADDR BYTES... [--read N]`.
- Examples:
  - `./dev.py gui --serial AWT26110002 --kvm hdmi-1 --save` (view changes, input switches, setting saved, read back)
  - `./dev.py gui --serial AWT26110002 --hdmi --i2c 0x34 0x22`
  - `./dev.py gui --unit 1 get volume mute` / `set gamma 2.2` / `state --json`
  - `./dev.py ddc get 0x62 --unit 1` (same reply as before, through the app)

### Flash (async)
- `./dev.py flash [IMAGE] [--unit N] [--full] [--write-mode ..] [--aux-fast ..] [--verify ..] [--force-ungated ...]` sends the job; the app starts `dev.py flash ... --direct` as a DETACHED worker (`scripts/flash_job.py`: own session, holds `unit_lock` for the whole flash, `AWTO_UNIT_OWNER` set for the child). Gate check (`check_gated`, `.gates.json`, `--force-ungated`) runs inside that worker exactly as before; a refusal = the worker's rc + message.
- The port replies at once with the job; `flash` events stream parsed log progress (phase, sectors n/N, percent, ETA, errors, ISP recoveries, burst redone) and `flash_done` (rc). The client prints them and exits with the flash's rc; Ctrl-C only detaches. `FLASH_SILENCE_S` = 60 s without events prints a WARN; the client never stops a flash.
- Job records: a spawn that fails or a record without a pid is closed as rc 255 ("stale", logged in `tmp/logs/unit_lock.log`), never left "running". Human cleanup: `python3 scripts/flash_job.py clean` (finished + stale records and logs).
- Handshake: `ping` returns `root` (tree the app runs from), `head` (its git HEAD at start), `code` (stamp of dev.py, scripts/, tools/osd_editor/) and `busy` (flashes followed, queued / running device jobs). Code: `gui_client.check_tree` (awto-ddc#358).
  - Every dev.py call compares the app's root + code with its own tree. Same = served.
  - Differs (another tree, code changed on disk, tree gone, no handshake) and idle: `quit {idle_only}`, then one fresh app from the caller's tree. Line `gui: restarting the app from <tree> @<head>: <why> (was pid P, <tree> @<head>)`.
  - Differs and busy, or the app is a window (the user's GUI is never closed by a client): refused, nothing run. One line names both trees, their HEADs and the running jobs. Exception: queries that run no unit code (`gui ping / list / state / jobs / flash-status / events / quit`) are served by that app, with the same line.
  - Decisions also go to the caller's `tmp/logs/gui-client.log`. The app logs `tree <root> @<head>` in every job's started / verdict line; `gui state` has `tree` {root, head, code, pid}.
  - Two trees alternating calls restart the app each time (0.3-1.1 s start, see the start bound). Isolate a tree with `AWTO_GUI_SOCKET` to avoid it.
- One app per socket (= per user): `flock` on `<socket>.lock` for the app's life, holder `pid root @head` written in it. A second headless app exits at once, rc 3, one line `headless app pid N exiting: control port unavailable: ... lock ... held by ...`. A window takes over from a headless app (quit, waits `TAKEOVER_WAIT_S` 3 s for the lock); a window that finds another window keeps its banner, no port.
- Old orphans: `ensure_app` launched twice after a restart (restart path + start path), the second app lingered. Now one launch per call.
- The control socket is per user, shared by all worktrees: a flash run by an app of worktree X uses X's dev.py.
- Job file `tmp/flash_jobs/<serial>.json` (shared by worktrees; pid, unit, argv, log, rc). The app re-attaches on restart (running, or finished and not yet reported). A dead worker without rc = rc 255 and an ERROR line.
- Nothing signals a flash. The app refuses `quit` (port, headless SIGINT / SIGTERM) while one is followed; the window asks before closing. The flash runs on either way.
- GUI: strip dot violet "FLASHING 47 %", progress panel (bar, sectors, errors, recoveries, ETA, last log lines). The unit's other operations and probes are refused with "flashing" until the lock is released.
- Not routed through the port: `deploy`, `recover` (they call the flash code in-process).

## Live sliders (#277, 2026-11-20)
- Live rows = registry flag `live`, not `risky` / `ro`; sliders 11: brightness (label Backlight), black_level, contrast, user_red / green / blue, osd_hpos / vpos / transparency, volume, screensaver_s. Combos 3 (stored settings only): gamma, colour_temp, screensaver (one write on pick). `power_mode` and `screensaver_now` are `live` but commands: keep Set. Other rows keep Set; a live row has no Set button. Quick strip volume + backlight are the same rows.
- Coalescing, per unit + setting (`tools/osd_editor/live_writer.py`): one write in flight, one pending value (the latest). A completed write sends the latest pending value at once. A value equal to the last sent value (or the pre-drag value) is skipped. Release sends the exact released value last, then ONE read-back. Keyboard / wheel steps coalesce the same way; no release event, so `SETTLE_S` 0.5 s without a change = released (above key-repeat and wheel gaps).
- Floor between write starts = max(30 ms, 1.25 x median of the unit's last 8 write times). 30 ms: the firmware serves DDC/CI in one pass per `AWTO_SET_LOOP_MS` (20 ms), one deferred request per engine. A slow bus (DP AUX) raises the floor by itself from its measured latency.
- Esc during a drag / key run: the pre-drag value is written back (one write, none if nothing was sent), read back, the widget shows it. Row shows "sending" while a write or the read-back runs; the label shows the read-back as `unit: N`.
- Log: one line per drag, e.g. `drag 20 -> 100: 161 value changes, 55 writes sent, 70 values never sent, 0 saves, 1.77 s, median write 2.1 ms, floor 30 ms`; event `live` on the port stream.
- Backlight safety (unit 2 was blacked by `set brightness = 0` x15, 2026-11-20): the backlight slider (row `brightness`) stops at `BL_MIN` 5 % ("min 5 %"; Home / wheel too). 0 % only through the "0 %..." button, which asks "Backlight 0 % = black screen. Set?"; port `set brightness 0` needs `--confirm`, any 1..100 never does. After any backlight set below `BL_LOW` 10 % the quick strip shows "Restore previous backlight (N %)" for 10 s (`BL_RESTORE_MS`).
- Port: `./dev.py gui --unit N drag NAME FROM TO [--steps N] [--step-ms M]` = a scripted drag through the same path (summary reply); `set` is unchanged (one write). `vcp set CODE VALUE` now runs in-process too.

### Fast write path
- `scripts/unit_ops.py`: `set_frame` / `get_frame` / `parse_get_reply` (frame `51 84 03 code hi lo chk`, chk = 0x6E ^ all bytes; reply chk seeded 0x50), `DdcSession` (persistent `/dev/i2c-N` fd via `i2cbus.Bus`, EDID serial proven once at open, frames spaced >= 20 ms, 40 ms Get wait, paged rows 0xE0 select once per drag then 0xE1). The app keeps one session per unit and runs it on the unit's worker thread (`UnitQueues.submit_fn`); no `ddcutil detect`.
- `dev.py ddc set CODE VALUE` (also the workers' subprocess) uses the same session. A bus error is logged (`fast DDC/CI write failed ... falling back to ddcutil`) and then runs the old `ddc_ctl.py` path; get / list / sleep / wake stay on ddcutil.
- Measured 2026-11-20, unit 1 (NVIDIA HDMI, bus 18, HDMI DDC), backlight 0x10: old `ddc_ctl.py set` 1.24-1.28 s per write (detect); first in-process write 0.6 s (open + EDID proof); warm write 2-3 ms; Get read-back 65 ms (40 ms MCCS wait); `gui vcp set` with read-back 67-70 ms over the port. DP AUX units not measured (unit 2 is out of bounds today): the floor derives from the measured median at run time.
- Scripted drag 100 -> 20 and back, 161 value changes 10 ms apart, 6 drags: 49-56 writes each (1.8 s, floor 30 ms), 0 saves, every read-back = the released value, no NAK. Unit restored to backlight 64, read back 64.

### NVRAM (#151) during a drag
- A VCP set = `vcp_set` -> `set_put(.., apply_now 1)`: RAM store + apply; a changed stored value marks the record dirty (`set_sdk_put` / `set_nv_dirty`), an equal value stores nothing. No flash write in the handler.
- The flush gate (`fw/nvram/nv_gate.c`, constants `AWTO_NV_*` in `RL6449_Project.h`): writes when stable >= 3000 ms, DDC/CI idle >= 500 ms (every DDC/CI request restarts it) and 2000 ms since the last change; or 30000 ms after the first dirty value regardless (`AWTO_NV_FORCE_MS`, the forced branch does not wait for DDC idle). MCCS save (0x0C) only sets a commit flag (no 2 s wait).
- Consequences for a live drag: writes 30 ms apart keep DDC idle at 0, so no flush while moving. One flush ~2 s after the last change. A pause > 2 s mid-drag with the mouse held flushes once (and each later pause > 2 s again). A drag longer than 30 s from the first change is forced to flush once mid-drag. The live path never sends 0x0C; the row stays dirty until the firmware gate or the explicit Save.

## Status line (#277, 2026-11-21)
- One label at the bottom, selected unit only: `unit 3  CPU 350.8 PLL 350.8 SPI 116.9  3840x2160 60.1Hz  power On  input D2 HDMI  sound muted vol 50  bright 50  contrast 50  PWM 125 (51 %)  loop 300/s  fw <tag>`.
- Read-only. `unit_ops.status` (`scripts/unit_ops.py`, decode / format in `scripts/unit_status.py`) runs on the unit's queue (`UnitQueues.submit_fn`); port command `./dev.py gui --unit N status` = one fresh pass, same code.
- Sources, in order:
  - DDC/CI Get VCP: volume 0x62, mute 0x8D, brightness 0x10, contrast 0x12, power 0xD6, input 0x60.
  - Info rows by the paged read: its only Set frame is the RAM-only row selector 0xE0 (no setting changes; same path as the live sliders).
    - `info_hres / vres / vfreq / loop`.
    - `info_cpu / pll / spi` (0.1 MHz; PLL / SPI 0 on the crystal clock; `AwtoClkMhz10` in `fw/osd/console.c`, same formula as the console title), `info_pwm` (PWM4 duty `0xFF50`, backlight % = (255 - duty) / 255, inverse), `info_tag_hi / lo` (first 6 hex digits of the commit in the build tag, 12 bit each; `scripts/msg_tokenise.py` `tag_hex12`) (awto-ddc#279).
  - Debug slave 0x35, only when it ALREADY answers (no DDC <-> debug swap: that is a Set of a unit mode): diag block (stage, loop rate 0x2A), exact timing when the flashed image's map exists; clocks and PWM from the registers as fallback for firmware without the rows.
  - Firmware tag: the rows' hash; the flash record (`flash_registry.current`) is shown instead when it contains that hash, and is the only source on firmware without the rows.
- A missing source shows `n/a` and its reason in brackets (`dbg_err` / `ddc_err`); a stale value is never kept for a failed source. Debug-link readings win over the info rows for timing and loop; the info rows win for clocks and PWM.
- Pace: timer `STATUS_S` 2 s, single shot, re-armed after each tick; no pass while the unit flashes ("status reads paused"), has a queued / running job, a slider drag is active, a pass is already in flight, or it is a DP AUX (`light`) / read-only / undetected unit. Pass = 6 Gets + 10 paged reads (each a selector Set + Get).
- Measured 2026-11-21, unit 3 (`lk2` image, HDMI DDC): pass 0.69 s (5 passes via the port, 691-1045 ms). A slider drag that starts while a pass runs waits at most that long for its first write.
- Unit 3's 0x35 did not answer in that run (`dbg_link.py state`: 0x35 NAK, 0x37 ACK: DDC/CI owns the bus by default, #79), so CPU / PLL / SPI / PWM showed `n/a` until the firmware rows of awto-ddc#279 (image with `info_cpu`..`info_tag_lo` flashed).
- Tests: `test_monitor_gui.py` `status_line` / `status_clocks` (selected unit only, no write, paused while flashing / dragging, one at a time, failed source named), `tests/test_unit_ops_ddc.py` (Get frames + selector only, debug part over a fake 0x35, no link).

## Not done
- Search flattens by hiding tree items, not a separate result list.
- Get all needs an image with the mailbox and its `.map` (units 1, 2, 3 have neither today): flashing is out of scope here.
- Closing the window waits for running calls (at most their limit).
