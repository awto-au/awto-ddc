# PC monitor menu: GUI (monitor tab of the OSD editor)

Dated 2026-11-20. Design chosen by Dan: "Tree + unit strip". Code: `tools/osd_editor/monitor.py`, `unit_jobs.py`.
Launch: `python3 tools/osd_editor/run.py --monitor` (opens on the monitor tab) or toolbar "monitor".

## Registry
- `scripts/settings_table.py`: 118 rows, 15 pages (picture 4, colour 11, sixaxis 12, display 6, input 10, kvm 3, signal 11, power 10, osd 13, panel 7, debug 7, audio 5, system 3, service 6, info 10).
- 54 int / 29 enum / 29 bool / 6 action; 10 `ro`, 11 `risky`, 8 `reboot`.
- group == page name, so the tree has two levels: page > setting.

## Layout
- Top: unit strip (one button per unit) + search box.
- Quick strip: volume (VCP 0x62), mute (0x8D), brightness (mailbox `settings set`), input select (`scripts/kvm.py`), screensaver start / stop (VCP 0xEB).
- Left: tree page > setting (counts per page; `[risky]`, `[action]`, `[ro]` tags).
- Middle: form of the selected page, one `SettingRow` per row; selecting a setting highlights its row and shows id, VCP code, range, default, flags, note.
- Right: host time, health, action log, boot / sync log, last output.

## Unit strip
- Source: `scripts/devices.json` (names, serial, input, `test`). Button: hotkey number, unit, last 4 of serial, input, status dot.
- Hotkeys: Ctrl+1..9 anywhere on the page, plain 1..9 when focus is not in a text field, Ctrl+Tab next unit, Ctrl+F search.
- Dot: green = probe answered, amber = a job queued or running, red = no answer or monitor not detected, grey = read-only unit (not probed).
- Probe = `dev.py ddc get 0x62 --unit N` (read-only, EDID guard inside dev.py), per idle unit every 15 s while the tab is visible; the reply also refreshes the volume value.
- Auto-detect: EDID serials from `/sys/class/drm/*/edid` (kernel copy, no I2C from the GUI), rescanned every 15 s (hotplug). A unit whose serial is not seen is red and not probed or read. No known serial seen at all = no scan result, devices.json stands.
- Per-unit state in memory (values, touched-not-set values, last read, tree node, output, banner): a switch is a view swap, no read.
- "Get all" runs only on the button, the live-refresh checkbox, or when a selected unit's view is older than 60 s (or never read).
- QSettings (`awto/osd_editor`): last unit, tree node per unit.
- Only `test=true` units are writable; other units grey out every control and `run()` refuses.

## Jobs
- One `QThreadPool` with one worker per unit (`unit_jobs.UnitQueues`): different units run in parallel, one unit's jobs one at a time (one bus).
- Backend stays `dev.py` / `scripts/` subprocesses with per-call limits (`LIMIT_S`); debug link on/off and EDID guard are inside dev.py. No I2C in the GUI.
- A failed or timed-out call sets a per-unit red banner and the unit's dot red.

## Confirm
- `risky` rows (11) and action rows (6) ask before Set / Run (dialog names the unit and row; notes a needed reboot).

## Search
- Substring over name, label, id and VCP code (`0x10`, `10` or decimal); non-matching rows and empty pages are hidden, page counts show `matches/total`, Enter selects the first match.

## Tests
- `tools/osd_editor/test_monitor_gui.py` (fake backend, offscreen; strip, hotkeys, tree counts, search, confirm, read-only, parallel vs serial queues, remembered unit, detect + probe, screenshot).
- `tools/osd_editor/test_smoke.py` (editor tabs, monitor page get / set / quick / banner).
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
- Quick strip: mute = switch, input = D1 / D2 / D3 segmented (one click runs `scripts/kvm.py`), screensaver = combo + Start / Stop (7 options).
- Greyed on read-only and unknown units.

## Advanced pages, unknown units, last read
- "show advanced (debug, service)" under the tree: pages hidden by default (tree, form, search), remembered in QSettings `monitor/advanced`.
- Monitors seen by EDID and not in devices.json: strip button "unknown (ro)", grey dot, read-only, never probed; removed when unplugged.
- Strip tooltip: last successful read (any kind) as ISO time, or "not read yet".

## Not done
- Search flattens by hiding tree items, not a separate result list.
- Get all needs an image with the mailbox and its `.map` (units 1, 2, 3 have neither today): flashing is out of scope here.
- Closing the window waits for running calls (at most their limit).
