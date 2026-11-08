# Handover (2026-11-09)

State of awto-ddc after the 2026-11-04..11-09 session. Point form; every item names its issue, doc or path. Supersedes the 2026-11-05 handover (retired in `history.md`).
Tracking: #1 (umbrella), #7 (own firmware), #41 (Dahua RE), #65 (clean-room), #67 (settings/menu), #85 (keys), #87/#89/#90 (OSD). Global rules: `~/.claude/CLAUDE.md`; repo rules: `CLAUDE.md`.
Terms (no bare "vendor"): **Dahua firmware** = the monitor's original firmware (RE only); **Realtek SDK** = source our images are built from; **awto menu** = our menu (#67).

## 1. Read first
- Hardware tests go on **unit 2 only** (lower left). Units 1 and 3 are Dan's working screens: no flash, reset, DDC traffic or layout change. Enforced by `scripts/devices.json` (`test` flag; `dev.py` refuses without `--force`).
- Debug link (slave 0x35) OFF before any flash (`scripts/dbg_link.py off 11`); it has a 10 min timer that expired mid-flash on 2026-11-08 (#71).
- Waiting for a monitor to come back after reset/flash/power cycle: **5 s** max, then report failed.
- Host layout changes: temporary only (`gdctl set`, never `--persistent`), at most 2 per test (Fedora "keep changes" dialog).
- GitHub writes: `/mnt/2tb/git/awto-dan/scripts/gh_claudia.py gh|git ...` (bot identity). Both repos (awto-ddc, awto-sdcc) are PRIVATE: no scrub checks. awto-ddc stays private permanently (Realtek confidential code, `CLAUDE.md`).
- Findings go into issues, not chat. Facts carry tags ([fw] [guess] [?] ...); a guess is never written as a fact (#91).
- Agents: cheap by default (Haiku/Sonnet), narrow briefs, one at a time for RE (memory `re-slow-cheap`). Opus only when asked. Stop an agent after its report: it re-sends "waiting on background work" notices that cost tokens.
- The API weekly limit was hit on 2026-11-08 (an agent died with partial work); resets 2026-11-11 05:00 (Australia/Melbourne).

## 2. Units and desk
| unit | serial | connector (bus) | image | notes |
|---|---|---|---|---|
| 2 (test) | AWT26110002 | Intel HDMI-A-2 (i2c-11, D2) + Intel DP-1 (i2c-15, D1) | **wb-p14keys5** | lower left; relay Sonoff `so-th-1` (`scripts/power_cycle.py --relay so-th-1`); `osd_timeout` 0; settings were wiped by the recover (defaults) |
| 3 | AWT26110003 | NVIDIA DP-4 (AUX i2c-21) | wb-p14swap10 | Dan's primary, bottom middle; no relay now; NVIDIA DP AUX is slow |
| 1 | AWT26110001 | NVIDIA HDMI-A-3 (i2c-18, D3) | wb-p14swap10 | bottom right; one health run 10/11 (main loop 2 s after boot), not re-checked |
| Philips 288E2 | UK52307000611 | NVIDIA DP-2 | MStar, not Realtek | top; never touch (`docs/monitors/README.md`) |
- Layout: DP-2 at (0,0); bottom row HDMI-2 | DP-4 (primary) | HDMI-3. DP-1 is mirrored into HDMI-2 (test mode, gives unit 2 a live D1): `./dev.py mode --unit 2 --dp off` removes it. Watcher: `scripts/desk_layout.py watch` (pid `tmp/desk_layout_watch.pid`); `desk_layout.py check`.
- Bus numbers change on re-enumeration and recabling: tools find the bus by EDID serial; never pick by number.
- Recabling history: 2026-11-08 11:42 Dan moved unit 2 to HDMI-2, unit 3 to DP-4.
- Images: `tmp/fw/<serial>-<tag>-be.bin` (+ .map); every flashed image is archived in `fw/images/` (committed, `fw_archive.py`). `tmp/fw/<serial>-flashed.json` = what runs.

## 3. Decisions by Dan (still in force)
- 4K60.000 is the preferred mode; all frequencies with 3 decimals everywhere (menu `info_vfreq` still 0.1 Hz: #87).
- Production EDID adopted; interlace kept; HDCP via Realtek's key table (#44, low).
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

### 4.7 Compiler (awto-sdcc, `/mnt/2tb/git/awto-sdcc`, branch `awto/keil-compat`)
- 16 issues fixed 2026-11-08 (#12 mixed-ABI link refusal, #15 #16 struct args, #3, #6 `--sloc-xdata` opt-in, #14 #17 #19, ICEs #21 #23 #27 #29 #30 #31 #33, #13); install `/mnt/2tb/git/awto-sdcc-kc/tmp/install-9e65f99`. Firmware built with it is code-identical to the pinned compiler (4 builds, gates pass).
- **Pinned in `scripts/wb_build.py` is still `install-440cfd2`.** Bump only after the keys/ui builds finish, and only after awto-ddc#92 (`mov r7,#0` in `crt_rtd_startup.asm`) lands, otherwise the awto-sdcc#18 branch (`awto/crtstart-r7-18`, unmerged) would skip RAM init on warm reset.
- Open: #11 (small-be-sc3 IRAM), #18, #32, #46 (DPRx1.c 70 s under load), #49, #50. Earlier "keil-compat flags on" regression figures are invalid (flags never reached sdcc): re-run with `one_test.py --flags` (awto-sdcc#25 comment).
- 12 upstream bug-report drafts: `/mnt/2tb/git/awto-sdcc-kc/tmp/upstream/*.md` (+ `3.patch`); send only after Dan's 3 checks.
- Catalogue and docs live in awto-sdcc: `docs/keil-vs-sdcc.md`, `keil-c51.md`, `keil-abi.md`; awto-ddc holds stubs.

### 4.8 Clean-room (#65, #68, #69, #70)
- `/mnt/2tb/git/awto-rtdfw` main 72e0581: reg, dataport, arith, gamma, settings. Mixed build via shims in `fw/awto/`, pin `fw/awto/clean_ref.txt`. Branches: `keys-text` (#85 strings, f476b96), `ui` (#87), `audio`, `audio-fw`, `rename-vendor` (labels "Realtek menu", tags `[sdk-ui]` `[sdk-value]`; not merged into keys/ui), `fix-67-keysync`.
- Wave B not started: timer, OSD engine, NVRAM, DDC/CI, flash table, factory menu, DP CTS.

## 5. Worktrees and branches (awto-ddc)
| worktree | branch | purpose |
|---|---|---|
| `/mnt/2tb/git/awto-ddc` | main | tools + docs; local commits ahead of origin until pushed |
| `awto-ddc-swap` | wb-p14swap | the image line on units 1/3 (wake, KVM, menu, IP-over-DDC, dead-port guard) |
| `awto-ddc-keys` | wb-p14keys | #85/#39 keys (keys5 on unit 2; keys6 uncommitted) |
| `awto-ddc-ui` | wb-p14ui | #87 menu redesign (merges keys5) |
| `awto-ddc-audio` | wb-p14audio | #94 audio, unmerged |
| (no worktree) | wb-p14pf | #83 pre-fill |
| `awto-ddc-crt` | wb-no-crtmod0 | drops crt_mod0.c (library `%0` guard), to fold in |
| older lines | wb-p14kvm, wb-p14net, wb-osd67(+net), wb-p14sw, wb-sc3, wb-keilcompat, wb-mixed*, wb-port*, wb-ddrinit, wb-msgtable, wb-p14new, wb-vfreq | merged or superseded; prune with `scripts/worktree_prune.py` / `branch_prune.py` after review (they archive images first) |

## 6. Runbook
- Health: `./dev.py health --unit 2`. Flash: debug link off, then `./dev.py flash --unit 2 <image>` (incremental, burst). Wedged: `scripts/power_cycle.py --relay so-th-1`, then `./dev.py recover --unit 2 --bus 11` or `./dev.py flash --unit 2 --bus 11 --full --write-mode byte <image>`; after a wipe wake with `ddcutil --bus 11 setvcp D6 01`.
- Key presses: `scripts/dbg_link.py on 11 --minutes 10`, then in the keys worktree `python3 scripts/rtd_keywatch.py 11 --log --map <map> --serial AWT26110002 --secs 180` (`--open` / `--close` = key test screen); link off afterwards.
- Inputs: `./dev.py mode --unit 2 --dp mirror|off`; `scripts/kvm.py dp|hdmi1 --units 2`; `scripts/kvm_demo.py`.
- OSD: `./dev.py osd ...`, `./dev.py menu ...`, `./dev.py settings list|get|set --unit 2`; catalogue `python3 scripts/osd_catalog.py <bin> --menu-dir <dir>`.
- Build: `python scripts/wb_build.py --tree <worktree> --serial AWT26110002 --tag <tag>` (from this repo); gates `scripts/fw_gates.py`; speed `scripts/loop_rate.py`, sim `docs/speed-bench.tsv`.
- Logs: `tmp/logs/` (`unit-<serial>.log` per monitor, `dev.log`, tool logs); decoded one line per action, raw to `*.raw.log`.

## 7. Open decisions for Dan
1. Power LED: what do the LEDs do now? Add the drive (#95)?
2. Audio: is there a jack/amp? Flash `wb-p14audio1` on unit 2 only if yes (#94).
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
- Found only in chat and now recorded: Philips 288E2 is MStar (`docs/monitors/README.md`); OSD is display-side and independent of the picture clock (`docs/reversing/realtek-rtd/osd.md`); two Realtek SDK bugs (#100, `re/lib-review/realtek-sdk-bugs.md`); CEC (#101); recovery stub idea (#102); keys6 and #87 state (#85, #87 comments); flasher follow-ups (#71); RE plan (#41); invalid regression figures (awto-sdcc#25); wrong key labels, naming and test-unit changes (`history.md`); `buttons.md` section 3 corrected; new memory `blame-code-not-hardware`.
- Answered in chat on 2026-11-04 and filed then: Linux-loader/EDID analysis (#4, #8, `docs/edid-fix.md`).
- Not verifiable from the transcript: "45g for ddc?" (2026-11-07 message) and "30hz is fine" (2026-11-07); no action recorded.
