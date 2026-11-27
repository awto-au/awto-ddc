# Proposed closes / corrections (2026-11-13), NOT POSTED
Per CLAUDE.md only Dan closes; agents comment "Ready to close" + label `ready-to-close`. Drafts below are for Dan's approval. Repo is public: texts are scrubbed (no keys, hashes, vendor material).

| # | title | action | why |
|---|---|---|---|
| 164 | PIP / PBP and a second input kept synced | CLOSE (wrong premise) | own comment 2026-11-12: RTD2795T has ONE video path; QC PIP/PBP code is dead (`_QC_4P_MODE_` undefined) |
| 3 | identify the OEM, the driver board and the panel | CLOSE (Dan's call; OEM/seller still unknown) | panel = Innolux M280DCA-E3B rev C1 (label photo); all 27" guesses wrong; EDID fixed 621 x 341 mm (docs/monitors/panel-innolux-m280dca-e3b.md, edid-fix.md, main f54cf13 range). Board = RTD2795T/RL6449 JXC4K header known. Keep open only if OEM/seller hunt is still wanted |
| 177 | Unit 3 half-flashed and dark | CLOSE | recovered 2026-11-13T10:53 over Intel HDMI-A-2 bus 11, health ACTIVE 4K60, now the test unit (scripts/devices.json note); follow-up flasher rules in #167 / closed #71 |
| 167 | Unit 2 flash failed mid-program | CLOSE (optional) | `--write-mode byte` completed and verified; unit 2 healthy; no open work beyond #177 lesson (byte mode over DP AUX is too slow) |
| 44 | HDCP: enable for protected video | CORRECT (comment, keep open) | body says per-unit licensed keys needed; phase A found one SDK-wide key set (identical in all dumps, already in every image); HDCP compiled out by default (`_AWTO_HDCP`) |
| 21 | re-add FreeSync/Adaptive-Sync and MHL | CORRECT (retitle: FreeSync only; MHL dropped) | MHL dropped (no hardware); body cites removed `fw/overlay/` paths |
| 100 | Realtek SDK source bugs (FRC DHF, DPLL overflow) | CORRECT (comment) | fixes "held until the Dahua 4K60 memory mode is known"; DDR frame buffer now works, so the held fixes can be decided (needs Dan) |
| 165 | Planned features: picture tuning, rotation + freeze | CORRECT (comment) | rotation 180 and mirror H/V verified by Dan on unit 3 2026-11-13; freeze and picture tuning remain; PIP link line stale after #164 |
| 109 | Unit 2 does not sync at 4K30 | NEEDS DAN'S EYES | frame buffer now works; 4K30 not retested here; unit 2 is a working screen, retest on unit 3 |
| 152 | Unit 2 relay so-th-1 unreachable | NOTE | relay feeds unit 2, test unit is now 3: hass power cycles of the test unit need the relay moved (devices.json) |
| 35 / 162 / others | "customer branches", `fw/overlay` references | no action | already corrected in #162 comments / docs/design-162.md; `fw/overlay` text lives only in old issue bodies (history) |

Already closed, premise now disproved (no action, FYI): #26 and #36 ("DDR read error"): DDR frame buffer works (wb-p14ui-ddrinit, rot1); docs/history.md row added in branch `docs-fix-1113` (a018989).

## Draft texts

### #164
🤖 Closing (Dan, 2026-11-13): not feasible. The RTD2795T has one video path (one capture, one display pipe). The "second capture and display path" in the opening post came from Realtek's factory chip test, which only splits one source into several registers sets and is compiled out (`_FACTORY_RTD_QC_SUPPORT _OFF`, `_QC_4P_MODE_` never defined). PIP / PBP and a second synced picture are not possible on this chip; instant KVM switching stays with the fast-switch cache work (#83). Evidence: read-only study comment 2026-11-12 on this issue.

### #3
🤖 Closing (Dan, 2026-11-13): panel identified from Dan's photo of the panel label: Innolux M280DCA-E3B rev C1, 28.0", active 620.9 x 341.3 mm, eDP 4-lane. The Samsung LTM270FL01, BOE MV270QUM-N20 and Innolux 27" guesses were wrong; the 597 x 336 mm in the panel TCON EDID was a template value and our input EDID copy was wrong too, now 621 x 341 mm with datasheet primaries (`docs/monitors/panel-innolux-m280dca-e3b.md`, `docs/monitors/panel-edid.md`, `docs/edid-fix.md`). The board is the Realtek RTD2795T / RL6449 JXC4K layout documented under `docs/monitors/`. The OEM / seller is still unknown and is not needed for the firmware; reopen if wanted.

### #177
🤖 Closing (Dan, 2026-11-13): unit 3 was recovered on 2026-11-13 over Intel HDMI-A-2 (bus 11) with a burst-mode resume, image wb-p14ui-rec3, health ACTIVE at 4K60. It is now the test unit (`scripts/devices.json`). Lesson kept in the flasher rules: no forced byte mode over NVIDIA DP AUX (about 21 ms per byte).

### #167
🤖 Closing (Dan, 2026-11-13): unit 2 was reflashed in byte mode, verified and has been healthy since; the failure mode (burst ENXIO, SPI engine busy mid-program) and the recovery path are recorded in the flasher docs and #177. No open work left here.

### #44 (comment, no close)
🤖 Correction (2026-11-13): the body's "needs the unit's licensed keys" is wrong. The key set is one SDK-wide set (identical in all dumps, same as the SDK sample header), not per unit, and HDCP 1.4 is already in every image we build. HDCP is now compiled out by default (`_AWTO_HDCP` off, branch wb-p14ui-hdcpoff); what remains is deciding ON vs OFF per build (shared receiver ID may be revoked) and the XDATA cost of HDCP 2.2.

### #21 (comment, retitle "Later: FreeSync / Adaptive-Sync")
🤖 Correction (2026-11-13): MHL is dropped (no hardware on the board, Dan 2026-11-12); remove it from this issue's scope. File paths in the body (`fw/overlay/...`) are gone: sources are `fw/sdk/` now. Remaining work: FreeSync / Adaptive-Sync only (panel VRR range, EDID range block, timing), after the #162 machines.

### #100 (comment)
🤖 Update (2026-11-13): the DDR frame buffer now works (4K60 frame memory clean, mirror and rotate verified on unit 3), so the memory mode in use is known. The two held fixes (FRC DHF byte overwrite, DPLL 16-bit overflow) can be decided now: both sit in paths that run with the frame buffer. Needs Dan: apply and test on unit 3, or keep held.

### #165 (comment)
🤖 Update (2026-11-13): rotate 180 and mirror H / V are verified by Dan on unit 3 (DDR frame buffer works). Left here: freeze and the picture tuning set. The "PIP / PBP: separate issue" line is void: #164 found it not feasible.
