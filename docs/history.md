# History: superseded, refuted or wrong (one line each)

- Format: date | what was believed or tried | why superseded | link.
- Live docs and open issues hold current state only. Newest first, sections per area.

## 4K60 / display path (#26, #55)
- 2026-11-07 | DDR read-error bug parked; frame-buffer (FRC) path unusable | DDR frame buffer works: 4K60 frame memory clean, mirror H/V and rotate 180 verified by Dan on unit 3 (2026-11-13, images wb-p14ui-ddrinit, wb-p14ui-rot1) | #26, #165
- 2026-11-07 | P0_37, DPLL offset (+-10 %), static M-domain/FRC/DPLL config, DDR for the line buffer, memory select (frame-sync line buffer) as cause of 4K60 NOSUPPORT | all equal the vendor in the failing state; M1 FIFO flag returns within a frame with firmware frozen | #26
- 2026-11-07 | IVS2DVS phase and fine-tune passes as cause | ruled out on hardware | #26
- 2026-11-07 | HDMI 2.0 RX link errors at 594 MHz (lanes 1/2) as cause | refuted: offline config diff, live SCDC and 6 PHY trials; SCDC errors equal on the vendor firmware | #55
- 2026-11-07 | EDID DTD1 = 3840x2160@60.000, 594 MHz (VIC 97), `make_edid.py` ab8c4c9 | vendor EDID never preferred it; vendor DTD1 is 3840x2160@59.982, 533.12 MHz (panel-native 4000x2222); 594 MHz not pursued, 4K59.94 works | #26
- 2026-11-07 | FRC/frame-buffer modes (4K24/25/30/50, 1080p50) to be made to work | DDR read-error bug parked (p3); modes dropped from the EDID | #26, #36
- 2026-11-04..05 | `_FRC_SUPPORT` cut for bring-up | without FRC 4K60 cannot set the display (equal line times 7.40 us); turned back ON | #8, #26

## GPIO / board (#7)
- 2026-11-06 | P8.5 = backlight enable (high = on), SDK name `bBACKLIGHTPOWER` | backlight enable is P9.2 (FE2A) active low, proven live with `rtd_reg_poke.py`; P8.5 only follows it | #7, `docs/monitors/gpio-roles.md`
- 2026-11-05 | P9.2 = standby LED (probable) | it is the backlight enable | #7

## Toolchain / speed measurements (#11, #23)
- 2026-11-06 | main-loop rate 278/s vs 172/s between images | artefact of `rtd_diag`'s single-read figure (u16 counters wrap at 65 s, boot time in the denominator); not comparable between images | #11
- 2026-11-06 | "register calls are faster" | the 6-byte stubs cost -6.5 % loop rate, ABI 1 a further ~-2.5 %; register calls bought size, not speed | #11, `docs/speed-bench.tsv`
- 2026-11-06 | wb-step2/stepA/stepB contain the fixed compiler | built with the stale `rc-be-install-sc1` (pre-41a2b76); 345->406/s gains were stub + layout only; `fw_build` now refuses stale stamped installs | #11
- 2026-11-06 | Keil PK51 (~A$284/month) vs SDCC, "needs-dan" | decided: SDCC fork with register calling convention (awto-sdcc), not Keil | #11
- 2026-11-05 | trunk SDCC `genconstprop` folds `ScalerTimerDelayXms` into an endless loop | fixed with `--nogenconstprop` | #23
- 2026-11-06 | "stall at stage 4" in the simulator | harness artefact (`fw_sim --serial` stopped after 300 samples, read stale `fw.bin`) | #11

## Timing / delays (#40, #54)
- 2026-11-06 | TMDS pre-detect treated as ~1 ms | 6 ms blind per call (D081/D086) | #40, `docs/delays.md`
- 2026-11-06 | `0x830B6229` ulDclk in the simulator read as a firmware fault | sim artefact (unmodelled P30_41..49 counts) | #38

## Debug / recovery (#35, #48, #52)
- 2026-11-06 | self-recovery hooks (power-key reset, DDC bus watchdog, main-loop canary) on by default | no image booted with them on; behind `_AWTO_SELF_RECOVERY _OFF`, re-introduce one at a time | #35
- 2026-11-06 | safe-window / `dev.py recover --hold` available on every image | the safe block (0xF6B0) exists only on the main line; on working-base 0xF6B0.. is live firmware XDATA, so the hold corrupts globals; recover must hold only when the map has `_g_stAwtoSafe` | #52, #48
- 2026-11-05 | debug slave 0x35 usable at 1 MHz | NAKs intermittently (2 of 4 diag reads failed); 100 kHz only. ISP slave 0x4A is clean at 1 MHz | `docs/flash-burst.md`, #12

## Docs retired
- 2026-11-13 | panel = 27" (597 x 336 mm, BOE MV270QUM-N20 / Samsung LTM270FL01); input EDID size 597 x 336 mm + sRGB primaries | panel label (Dan's photo): Innolux M280DCA-E3B rev C1, 28"; the 597 x 336 mm was ours (copied from the TCON template EDID); EDID now 621 x 341 mm + datasheet primaries | #3
- 2026-11-04 | panel = Samsung LTM270FL01 (closest by size) | panel EDID read over eDP AUX (MST/AGERA, 2018); best candidate BOE MV270QUM-N20, unconfirmed | #3
- 2026-11-07 | `docs/handover.md` (2026-11-05 snapshot: unit table, "verify the flash lights the panel", Keil-vs-SDCC pending, P8.5 backlight) | all items done or superseded; state lives in issues #7, #26, #38 | git history
- 2026-11-07 | `docs/firmware-proposal.md` patch routes A/B and EDID-fail list | firmware is our own build on the SDK (#7); EDID failures fixed (`docs/edid-fix.md`) | #7
- 2026-11-04 | persistent boot-splash patch of the vendor image | our firmware draws the logo (confirmed on unit 3, `dev.py osd logo`) | #5, #46

## Front keys, naming, test units (#85, #91)
- 2026-11-04 | key labels in `buttons.md`: MENU "almost certainly 0x10 (sole long-press key)", DOWN/UP "the symmetric pair", SOURCE/AUTO "order unconfirmed" | wrong for 5 of 6 keys; settled 2026-11-08 by Dan's presses on unit 2 (ADC readings) + the Dahua dispatch trace: MENU 0x02, UP 0x04, DOWN 0x08, AUTO 0x10 (the long-press key), SOURCE 0x20 | #85, #91
- 2026-11-04 | board header kept the SDK reference keypad (LEFT/RIGHT/EXIT, `QA_B`) for the JXC board | replaced by the JXC ladder decode (keys4+); earlier combos (#34, #60, #67, #79) used keys this monitor does not have | #85, #91
- 2026-11-05 | 'AUTO long press = auto-adjust / lock / factory entry' (guess in chat) | timer 0xD has no consumer in banks 0-6; a held AUTO does nothing extra [fw, medium] | `docs/reversing/dahua-fw/keys.md`
- 2026-11-05 | 'IR/key_alt_source_poll role unknown', '8 bytes at 0xFF:3067 are a code table' | it is the IR path (NEC); the 8 bytes are the zero initialiser | #93, `dahua-fw/gpio-ir.md`
- 2026-11-05 | 'no audio-mute GPIO' (gpio-roles.md), 'P9.7/PA.0 never written' | P7.4 is the speaker-amp enable, P4.5 the jack select; P9.7/PA.0 follow the power state | #93, #95
- 2026-11-07 | all three units free for tests (units 1/2 after an image booted on unit 3) | from 2026-11-08 only unit 2 (lower left, HDMI-A-2 + DP-1, so-th-1 relay); units 1 and 3 are Dan's working screens | `scripts/devices.json`, #85
- 2026-11-08 | `docs/osd-vendor-menu.md`, 'vendor menu' | said "vendor" for the Realtek SDK demo menu; renamed `osd-realtek-sdk-menu.md`; terms: Dahua firmware / Realtek SDK menu / awto menu | `docs/osd.md` naming, #87
- 2026-11-08 | menu keys MENU = open, AUTO = back (keys4/5) | Dan: AUTO = open, MENU = back (keys6, unverified) | #85

## Handover (frozen 2026-11-16, no longer updated; Dan)
- Former `docs/handover.md`, kept as it was: state, units, decisions, runbook. Current state: open issues + `docs/power-levels.md`; commands: `./dev.py --help`.

### Handover (2026-11-09)

State of awto-ddc after the 2026-11-04..11-09 session. Point form; every item names its issue, doc or path. Supersedes the 2026-11-05 handover (retired in `history.md`).
Tracking: #1 (umbrella), #7 (own firmware), #41 (Dahua RE), #65 (clean-room), #67 (settings/menu), #85 (keys), #87/#89/#90 (OSD). Global rules: `~/.claude/CLAUDE.md`; repo rules: `CLAUDE.md`.
Terms (no bare "vendor"): **Dahua firmware** = the monitor's original firmware (RE only); **Realtek SDK** = source our images are built from; **awto menu** = our menu (#67).
- 2026-11-13: firmware line `wb-p14ui` (87ab7c7) merged into `main`; `fw/overlay/` and `keil2sdcc.py` are gone, `fw/sdk/` (+ `fw/sdk-parked/`) is the source (section "SDK source" at the end). `wb-p14ui` stays the firmware line: agents branch from it. Sections 4-9 are the 2026-11-09 state.

## 1. Read first
- Hardware tests go on **unit 3 only** (top monitor, Intel HDMI-A-2; Dan 2026-11-13). Units 1 and 2 are Dan's working screens: no flash, reset, DDC traffic or layout change. Enforced by `scripts/devices.json` (`test` flag; `dev.py` refuses without `--force`).
- Debug link (slave 0x35) OFF before any flash (`scripts/dbg_link.py off 11`); it has a 10 min timer that expired mid-flash on 2026-11-08 (#71).
- Waiting for a monitor to come back after reset/flash/power cycle: **5 s** max, then report failed.
- Host layout changes: temporary only (`gdctl set`, never `--persistent`), at most 2 per test (Fedora "keep changes" dialog).
- GitHub writes: `/mnt/2tb/git/awto-dan/scripts/gh_claudia.py gh|git ...` (bot identity). awto-ddc is public (Dan, 2026-11-13): scrub secrets and binaries; awto-sdcc is private (`CLAUDE.md`).
- Before writing a new function or researching how the chip does X: grep the stripped SDK code (#209).
  - Ported to SDCC, as before the strip: tag `pre-strip-209`, local worktree `/mnt/2tb/git/awto-ddc-prestrip`. Recreate with `git worktree add --detach ../awto-ddc-prestrip pre-strip-209`.
  - Realtek original (Keil): `/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST`. Whole files dropped: `fw/sdk_drop.txt`.
- Findings go into issues, not chat. Facts carry tags ([fw] [guess] [?] ...); a guess is never written as a fact (#91).
- Agents: cheap by default (Haiku/Sonnet), narrow briefs, one at a time for RE (memory `re-slow-cheap`). Opus only when asked. Stop an agent after its report: it re-sends "waiting on background work" notices that cost tokens.
- The API weekly limit was hit on 2026-11-08 (an agent died with partial work); resets 2026-11-11 05:00 (Australia/Melbourne).

## 2. Units and desk
| unit | serial | connector (bus) | image | notes |
|---|---|---|---|---|
| 2 | AWT26110002 | Intel DP-1 (i2c-15, D1) | wb-p14ui-audit1 | lower left; **hands off** (working screen); relay Sonoff `so-th-1` feeds this unit, not the test unit (`scripts/power_cycle.py --relay so-th-1`) |
| 3 (test) | AWT26110003 | Intel HDMI-A-2 (i2c-11) | see `tmp/fw/AWT26110003-flashed.json` | top monitor; the only unit for tests; `disp_rotate` 180 kept (set again after any flash that erases NVRAM; `scripts/devices.json`); recovery after #177 |
| 1 | AWT26110001 | NVIDIA HDMI-A-3 (i2c-18, D3) | wb-p14ui28 | bottom right; **hands off** |
| Philips 288E2 | UK52307000611 | NVIDIA DP-2 | MStar, not Realtek | top; never touch (`docs/monitors/README.md`) |
- Layout and connectors per unit: `scripts/devices.json` (single source). Watcher: `scripts/desk_layout.py watch` (pid `tmp/desk_layout_watch.pid`); `desk_layout.py check`.
- Bus numbers change on re-enumeration and recabling: tools find the bus by EDID serial; never pick by number.
- Recabling history: 2026-11-08 11:42 Dan moved unit 2 to HDMI-2, unit 3 to DP-4.
- Images: `tmp/fw/<serial>-<tag>-be.bin` (+ .map); every flashed image is archived in `build-debris/images/` (gitignored, `fw_archive.py`; before 2026-11-12 committed in `fw/images/`). `tmp/fw/<serial>-flashed.json` = what runs.

## 3. Decisions by Dan (still in force)
- 4K60.000 is the preferred mode; all frequencies with 3 decimals everywhere (menu `info_vfreq` still 0.1 Hz: #87).
- Production EDID adopted; interlace kept; HDCP via Realtek's key table (#44, low).
- Panel = Innolux M280DCA-E3B rev C1, 28" (label photo 2026-11-13, #3; `docs/monitors/panel-innolux-m280dca-e3b.md`). The 27" / 597 x 336 mm EDID size was ours and wrong; EDID now 621 x 341 mm + datasheet primaries. Panel T-values and limits: change only with Dan's OK (datasheet check in the panel doc).
- Divide by zero never hangs (guard in every build; Keil values via `--keil-div`).
- Clean-room tree is local only (`/mnt/2tb/git/awto-rtdfw`, no remote); the lint is the only gate (#65).
- OSD: always VLC-compress glyph data when the chip can decode it, encoded in a Python build step. Font: fixed 24x36 per char at 1x scale, 2 bpp. Text white on black, decorations red. Menu: **AUTO opens, MENU goes back**, UP/DOWN move, SOURCE = next input.
- 60 s waits for monitors are wrong (5 s). Don't cap parallel jobs. Only 4K60 + 1080p60 on DP and HDMI matter first.
- Units 1 and 3 are not updated for now (no urgency).

## 4. State by workstream
### 4.1 Front keys (#85, #39, #91)
- Decode settled (Dan's presses on unit 2 + Dahua trace): SOURCE A1 0x68..0x87, MENU A0 0xC0..0xDF, DOWN A1 0x28..0x47, UP A0 0x28..0x47, AUTO A0 0x70..0x8F, POWER P3.0. Chords need one key per ladder (A0 = MENU/UP/AUTO, A1 = SOURCE/DOWN): MENU+DOWN = debug link + recovery, UP+DOWN = key test screen.
- keys5 on unit 2 (hardware-verified): buttons decode, key test screen draws (`open=1 drawn=1`), wake from D6 off by a key works. Not hardware-tested: UP+DOWN toggle, menu roles, SOURCE next-input, MENU+DOWN chord.
- **keys6 (AUTO open / MENU back) is built, uncommitted and unverified**: `tmp/fw/AWT26110002-wb-p14keys6-be.bin`; 13 modified files in `/mnt/2tb/git/awto-ddc-keys` + rtdfw `keys-text` f476b96; keys_sim was mid-run. Finish: two keys_sim PASS, gates, commit, flash unit 2, test. Details: #85 comment 2026-11-09.
- Uncommitted edits in main by the stopped agent: `docs/osd.md`, `scripts/menu_cli.py`, `scripts/fw_gates.py` (keys6 wording, a longer menu gate limit): commit with keys6.
- Units 1/3 still run the SDK reference decode: an EXIT-like press switches input to an uncabled port; swap10 guards that (#84, closed).
- Root cause of the wrong labels: #91 (guess tags lost between doc, tool labels and firmware). Proposed fix: claims register + lint (~half a day), awaiting Dan.

### 4.2 Menu, OSD, tooling (#67, #87, #88, #89, #90, #86)
- #67 registry menu (101 rows, 16 pages, I2C control, MCCS 2.2) is on swap10. 49 of 101 rows still inert (`docs/settings.md`, #81). Menu gate hang with power on and no video: #88.
- #87 redesign (red/white, status strip, legend, 24x36 2 bpp, V freq 3 decimals) is part-built offline on `wb-p14ui` (`/mnt/2tb/git/awto-ddc-ui`, with rtdfw `ui`); never flashed; state in the #87 comment. Merge the #85 roles into it.
- Shared tools on main: `scripts/osd_vlc.py` (the one VLC codec), `osd_model.py` (draws 2-bit chars), `osd_render.py`, `osd_catalog.py` (sheet.png of every layout), `popup_fit.py`, `font_compare.py` (font trade-off), `tools/osd_editor/` (PySide6, `python3 tools/osd_editor/run.py`; OsdEdit study in `docs/osd-editor-spec.md`). Overview: `docs/osd.md`.
- Pending: Dan picks the selected-row look (both rendered on the sheet).

### 4.3 Power, wake, KVM, IP over DDC (#78, #79, #60, #83, #80)
- L1/L2/L3 levels (wake HDMI: 269-304 / 302-372 / ~1.4 s; DP: 509-543 / 614-635 / 1.64-1.67 s). Runtime DDC swap (#79, VCP 0xE3). KVM switch 80-96 ms monitor side; `scripts/kvm.py` 72-91 ms host side (bus cache fix, 2026-11-08); `kvm_demo.py`.
- #83 pre-fill of the idle DP port works in the sim, **not on hardware** (scan fails, link drops); needs firmware instrumentation (branch `wb-p14pf`, image wb-p14pf1). Idle HDMI ports not covered.
- After deep sleep the first switch back to HDMI takes the full path (idle receiver powered down; not investigated).
- IP over DDC = "Busorra" (`scripts/ddcnet.py`, `docs/ip-over-ddc.md`): stack test 13/13 and a real `ping` on unit 2 over DDC/CI (rtt ~140 ms), TAP via `ddcnet.py daemon --units 2 --route`.

### 4.4 Flasher and recovery (#71, #82, #102)
- Unit 2 went dark 2026-11-08 19:06 (flash with the debug link on; SPI engine busy), recovered by power cycle + byte-mode full flash (356 s, 2.5 KiB/s; burst ~36 KiB/s works when the bus is healthy). `dev.py recover` erased before proving the write path. Follow-up checklist in #71.
- Idea (Dan): recovery stub image so a failed flash leaves a flashable monitor: #102 (design only).

### 4.5 Audio, LED, GPIO, IR (#94, #95, #93)
- Audio built offline (branch `wb-p14audio` in `/mnt/2tb/git/awto-ddc-audio`, rtdfw `audio`/`audio-fw`; image wb-p14audio1; `docs/audio.md`): headphone DAC path, volume/mute via DVC, EDID declares LPCM. **Not flashed** (first attempt hit the failure above). Open: does the monitor have a jack/amp? (Dan saw none, #3/#22). With the EDID change the PC offers a silent sink if there is no jack.
- Dahua firmware drives, ours does not (#95): two-colour power LED P3.5/P3.6, power-state group P9.7/PA.0/P8.4/P8.5, P7.3 low, speaker amp P7.4, jack P4.5, IR NEC receiver (pin 194). Hardware checks listed in #41/#93.
- CEC: chip block exists, nothing drives it, board wiring unknown: #101 (p3).

### 4.6 Dahua firmware RE (#41, #93, #91)
- Done: keys, register/I2C/GPIO audit, IR. Plan for the rest (panel/video constants first: eDP swing, T-values), rule "one cheap agent at a time": #41 comment 2026-11-09. Docs: `docs/reversing/dahua-fw/{keys,register-audit,gpio-ir}.md`; `re/jxc-4k/*.tsv` (names_gpio_ir.tsv not merged into the bank names).
- Realtek SDK bugs found (FRC DHF overwrite, DPLL 16-bit overflow): `re/lib-review/realtek-sdk-bugs.md`, #100; fixes held.

### 4.7 Compiler (awto-sdcc, `/mnt/2tb/git/awto-sdcc`)
- Build compiler: `/usr/local` (stamp + library sources in `/usr/local/share/sdcc/`); the pin is `SDCC_COMMIT` in `dev.py build`, a different stamp refuses the build. BE, `--sdcccall 3`. The sdcc session asks before it swaps `/usr/local` (Dan runs the sudo).
- Far locals on, for the functions in `fw/far_locals_select.txt` (#205); `AWTO_FAR_LOCALS=all|off|list` for trials (all-on measured: +8 KB code, no gain).
- Placement: `#pragma place group(g)` / `bank(n)` before a definition (awto-sdcc#141, docs/place-pragma.md there). `scripts/place_rules.py` rewrites the compiler's PLACE_g areas back to CSEG / CONST with a `;@place` marker right after the compile; `scripts/sdcc_bank.py` puts a group in one bank (hard error when it does not fit or splits). Example: the font group in awto-rtdfw `font.c`. `common` leaves no mark: `--pin-common`.
- Chip facts (banks, common, reserved ranges, XDATA, IRAM): `fw/rl6449_memory.toml`, read through `scripts/chip_mem.py` (#149).
- Old A/B reference: `~/opt/awto-sdcc-440cfd2` (`--bin ~/opt/awto-sdcc-440cfd2/bin --src ~/opt/awto-sdcc-440cfd2/share/sdcc/awto-src --expect ''`).
- Open: #11 (small-be-sc3 IRAM), #18, #32, #46 (DPRx1.c 70 s under load), #49, #50.
- Catalogue and docs live in awto-sdcc: `docs/keil-vs-sdcc.md`, `keil-c51.md`, `keil-abi.md`; awto-ddc holds stubs.

### 4.8 Clean-room (#65, #68, #69, #70)
- `/mnt/2tb/git/awto-rtdfw` main 72e0581: reg, dataport, arith, gamma, settings. Mixed build via shims in `fw/awto/`, pin `fw/awto/clean_ref.txt`. Branches: `keys-text` (#85 strings, f476b96), `ui` (#87), `audio`, `audio-fw`, `rename-vendor` (labels "Realtek menu", tags `[sdk-ui]` `[sdk-value]`; not merged into keys/ui), `fix-67-keysync`.
- Wave B not started: timer, OSD engine, NVRAM, DDC/CI, flash table, factory menu, DP CTS.

## 5. Worktrees and branches (awto-ddc)
| worktree | branch | purpose |
|---|---|---|
| `/mnt/2tb/git/awto-ddc` | main | tools + docs + firmware (wb-p14ui merged 2026-11-13); local commits ahead of origin until pushed |
| `awto-ddc-ui` | wb-p14ui | the firmware line (all three units run it); agents branch `wb-p14ui-<topic>` from it, host tools `tools-<topic>` from main |
| `awto-ddc-swap` | wb-p14swap | the image line on units 1/3 (wake, KVM, menu, IP-over-DDC, dead-port guard) |
| `awto-ddc-keys` | wb-p14keys | #85/#39 keys (keys5 on unit 2; keys6 uncommitted) |
| `awto-ddc-audio` | wb-p14audio | #94 audio, unmerged |
| (no worktree) | wb-p14pf | #83 pre-fill |
| older lines | wb-p14kvm, wb-p14net, wb-osd67(+net), wb-p14sw, wb-sc3, wb-keilcompat, wb-mixed*, wb-port*, wb-ddrinit, wb-msgtable, wb-p14new, wb-vfreq | merged or superseded; prune with `scripts/worktree_prune.py` / `branch_prune.py` after review (they archive images first) |

## 6. Runbook
- Health: `./dev.py health --unit 2`. Flash: debug link off, then `./dev.py flash --unit 2 <image>` (incremental, burst). Needs a gate record: run `python scripts/fw_gates.py tmp/fw/<tag> --tree <worktree>` first (see Gates below); archived `build-debris/images/` images pass; `--force-ungated` overrides (ALERT line in the unit log). Wedged: `scripts/hass_power.py cycle --unit <n>` (mains via Home Assistant; the `so-th-1` relay feeds unit 2, not test unit 3; `power_cycle.py --relay so-th-1` needs the relay's own API, #152), then `./dev.py recover --unit 2 --bus 11` or `./dev.py flash --unit 2 --bus 11 --full --write-mode byte <image>`; after a wipe wake with `ddcutil --bus 11 setvcp D6 01`.
- Key presses: `scripts/dbg_link.py on 11 --minutes 10`, then in the keys worktree `python3 scripts/rtd_keywatch.py 11 --log --map <map> --serial AWT26110002 --secs 180` (`--open` / `--close` = key test screen); link off afterwards.
- Inputs: `./dev.py mode --unit 2 --dp mirror|off`; `scripts/kvm.py dp|hdmi1 --units 2`; `scripts/kvm_demo.py`.
- OSD: `./dev.py osd ...`, `./dev.py menu ...`, `./dev.py settings list|get|set --unit 2`; catalogue `python3 scripts/osd_catalog.py <bin> --menu-dir <dir>`.
- Build: `./dev.py build --tree <worktree> --serial AWT26110002 --tag <tag>` (from this repo); gates `scripts/fw_gates.py` (below); speed `scripts/loop_rate.py`, sim `docs/speed-bench.tsv`.
  - Default build = FRC + rotation 180 / mirror + OSD rotation (2026-11-13, #165); `-D _AWTO_FREEZE=_ON` = freeze instead, `-D _AWTO_FRC=_OFF` = line buffer only.
- Blocking waits (#216): every Delay / Poll / WaitForEvent >= 2 ms or expired is logged with its caller: `scripts/wait_log.py <bus> --serial S --map M` (ring `g_stAwtoWait`, 64 entries, highest SP inside a wait); offline callers `scripts/sim_waits.py`; stack high-water `scripts/stack_high.py`.
  - Pump: inside the three waits `AWTO_WAIT_PUMP()` answers DDC/CI Get-VCP / capabilities (`AwtoWaitPump`, fw/ddcci/ddcci.c); Set / save / table / mailbox are deferred to the main-loop poll. Runs only with SP <= `AWTO_PUMP_SP_MAX`; the OSD hardware-VLC paths use `ScalerTimerDelayXmsQuiet` (link gate: no code reads in the DMA closure). Gate `pump` (`scripts/pump_sim.py`); live check `scripts/ddc_probe.py <bus> --serial S --cycle`.
  - `ScalerTimerWaitForEvent`, `AwtoWaitLog`, `AwtoWaitPump` are pinned common (they read SP; `--pin-common` in fw_build.py).
- Speaker ear test: `./dev.py sound-test --unit 3 [--only 1,2] [--freqs 200,1000,4000]` (docs/audio.md, #94).
- Gates: `python scripts/fw_gates.py tmp/fw/<tag> --tree <worktree>` -> `tmp/fw/<tag>.gates.json` (image SHA-256, date, per-gate PASS/FAIL/SKIP + seconds, fw_gates commit, `complete`).
  - Gates: boot, isr, link, h1080, h2160, menu, ddc, keys, crash, wdt, sync, bootsim, wake, pokes, portcfg (#81). `--only` runs a subset and marks the record partial (not flashable).
  - SKIP = image lacks the feature (map symbol) or the gate needs `--tree`; counted and printed, allowed by the flash check.
  - `dev.py flash|recover|deploy` refuse: no record, SHA-256 mismatch, partial record, any FAIL. Override `--force-ungated`.
  - Sims use the fast in-process core by default (`docs/sim.md`); ucsim only as a cross-check.
  - Cold times per gate: awto-ddc commit message of the gate-record change.
- Logs: `tmp/logs/` (`unit-<serial>.log` per monitor, `dev.log`, tool logs); decoded one line per action, raw to `*.raw.log`.

## 7. Open decisions for Dan
1. Power LED: what do the LEDs do now? Add the drive (#95)?
2. Audio: is there a jack/amp? Flash `wb-p14audio1` on the test unit (3) only if yes (#94).
3. Build the claims register + lint (#91)?
4. Re-run the keil-compat regression with the working harness (awto-sdcc#25)?
5. Recovery stub (#102) and CEC (#101): pursue or park?
6. Roll the key fix to units 1 and 3 once keys6 is verified on unit 2.
7. Compiler pin bump to install-9e65f99 (code-identical); `--sloc-xdata` (recommend off); the 12 upstream drafts (3 checks).
8. Selected-row look for the new menu; prune old worktrees/branches; push main.

## 8. Suggested order
1. Finish and verify keys6 on unit 2 (cheap agent: keys_sim x2, gates, commit; Dan presses AUTO/MENU/UP+DOWN/SOURCE/MENU+DOWN). Then merge into `wb-p14ui`.
2. #71 flasher follow-ups (link off first, recover pre-test): small, removes the risk that took unit 2 down.
3. Resume #87 on `wb-p14ui` (3-decimal V freq, status strip, legend, red/white).
4. RE steps in #41 (panel/video constants first) and the hardware checks in #93.
5. #83 instrumentation; #95 LED/GPIO group; #100 SDK bug check.
6. #45 final cleanup after the firmware is finished (docs review, close superseded, `history.md`).

## 9. Chat review (2026-11-09)
- All 397 user messages of the 2026-11-04..11-09 session were read against issues and docs. Asks covered by an existing issue or doc: the firmware line (#7), clean-room (#65), settings/menu (#67), KVM (#60), power levels (#78), IP over DDC (#61, #80), USB (#9, #64), HEC (#32), libs (#30, #31), delays (#54), debug messages (#25, #56), warnings (#66), flasher (#50, #71, #82), compiler (awto-sdcc), RE (#41), cleanup (#45, #46).
- Found only in chat and now recorded: Philips 288E2 is MStar (`docs/monitors/README.md`); OSD is display-side and independent of the picture clock (`docs/osd/pipeline.md`); two Realtek SDK bugs (#100, `re/lib-review/realtek-sdk-bugs.md`); CEC (#101); recovery stub idea (#102); keys6 and #87 state (#85, #87 comments); flasher follow-ups (#71); RE plan (#41); invalid regression figures (awto-sdcc#25); wrong key labels, naming and test-unit changes (`history.md`); `buttons.md` section 3 corrected; new memory `blame-code-not-hardware`.
- Answered in chat on 2026-11-04 and filed then: Linux-loader/EDID analysis (#4, #8, `docs/edid-fix.md`).
- Not verifiable from the transcript: "45g for ddc?" (2026-11-07 message) and "30hz is fine" (2026-11-07); no action recorded.

## SDK source (awto-ddc#162)
- `fw/sdk/` = the Realtek SDK files the RL6449 build compiles or includes (`fw/sdk_files.txt`), in SDCC form; it is our code. Edit it directly; our changes carry `// awto: <what> (#issue)`.
- Build: `msg_tokenise.py port` (DebugMessage ids, build tag) -> `fw_compile.py` (compile) -> link. No build step patches the SDK; gate `rules` enforces it.
- History: first commit = mechanical import of the mirror (`scripts/sdk_import.py`, run by hand to compare a new SDK drop), then the overlay merge, then the behaviour edits. What each removed rule did: `docs/keil2sdcc-rules.md`.
- Bank layout: the tracked `fw/bank_layout.tsv` only (`fw_build.py` refuses a layout under `tmp/`).
