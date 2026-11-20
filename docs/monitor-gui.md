# PC monitor menu: GUI (monitor tab of the OSD editor)

Dated 2026-11-20. Design chosen by Dan: "Tree + unit strip". Code: `tools/osd_editor/monitor.py`, `unit_jobs.py`.
Launch: `python3 tools/osd_editor/run.py`, toolbar "monitor".

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
- Probe = `dev.py ddc get 0x62 --unit N` (read-only, EDID guard inside dev.py), per idle unit every 15 s while the tab is visible.
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

## Not done
- Hidden "show advanced" for debug / service pages (all 15 pages always shown).
- Search flattens by hiding tree items, not a separate result list.
- Detection ignores monitors whose serial is not in devices.json.
