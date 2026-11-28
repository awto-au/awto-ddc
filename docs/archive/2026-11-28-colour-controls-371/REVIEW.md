# Colour controls review - issues #371 and #278

Reviewed 28 November 2026 against main `3326a1d6f78e7c676947bf7d82f35eb6d9f7166e`.
This is a proposed patch. No monitor access, flashing, live setting change or merge was performed.

## Current evidence and newer fixes

[#371](https://github.com/awto-au/awto-ddc/issues/371) remains open without a later fix in its comments, current main, or the current PR list. Its RGB early return is still present in the base revision.

The original body of [#278](https://github.com/awto-au/awto-ddc/issues/278) is superseded by its comments. Main already has distinct preset gains in `fw/colour_temp.tsv`, a generated `ColorTempGains.h`, and a loader that ignores stale stored factory-preset items. The [27 November comment](https://github.com/awto-au/awto-ddc/issues/278#issuecomment-7214273146) reports simulator coefficient checks passing and leaves optical measurement outstanding. The earlier comment reports unit 3 coefficient-register agreement. Neither establishes measured white points. This patch retains those coefficients unchanged.

## Recommendation and alternatives

| Policy | OSD / GUI | DDC/CI / mailbox | Assessment |
|---|---|---|---|
| Automatically select User on RGB edit | Enabled controls act immediately; reread the selected preset and all gains | One RGB write acts from any preset; readback matches the active gain | Recommended: consistent across interfaces, no silent discard |
| Refuse RGB outside User | Needs an explicit refused state / explanation | Mailbox can return refusal; ordinary DDC/CI Set has no result reply, requiring Get verification | Defensible locked-preset policy, but adds a precondition and poorer generic-client behaviour |
| Disable or hide controls outside User | Clearly communicates the precondition locally | Still needs a firmware refusal policy for remote clients | A UI policy alone cannot fix #371 |

On an accepted RGB write, the shared settings path selects User **without loading the previously stored User triple**, retains the other two active gains, writes the requested channel, and applies contrast coefficients. Writing the currently reported value also selects User. Explicitly selecting User still recalls its saved or pending triple. Once already in User, the existing channel range, gain conversion and other-channel behaviour remain in effect; equal writes remain no-ops.

There is one User slot. Editing from a preset deliberately replaces the previous User triple. To recall an existing adjustment, select User first. Factory-default stores bypass the automatic transition, so a reset does not accidentally turn the default sRGB selection into User. OSD Escape / GUI drag cancellation restores the edited channel through the existing mechanism; once an edit has selected User it does not restore the previous preset or previous User slot. A transactional cancel for both mode and triple would need a separate design.

## MCCS and truthful reporting

Primary source: [VESA MCCS 2.2a](https://files.lunar.fyi/mccs.pdf), Table 8-4, printed pages 38-39; [VESA standard availability](https://vesa.org/vesa-standards/).

VCP 0x14 selects presets; User 1 is 0x0B. Codes 0x16, 0x18 and 0x1A are continuous RGB gain controls whose readbacks describe active gains. The standard does not prescribe automatic User selection for an RGB write; that is this patch's product policy. With no specified tolerance, temperature selections represent a relative warmer-to-cooler scale. The current maximum high byte is zero; no calibrated tolerance is claimed.

The normal VCP setter now returns `set_put()`'s result instead of unconditionally returning success. The settings mailbox and OSD command therefore report a refusal truthfully. DDC/CI Set remains a protocol write with no success response; a bus ACK proves transport only. A host must Get the gain and preset to verify the outcome. The GUI reads dependent colour rows from the same unit after writes.

Existing scope limit: VCP 0x02 is hardcoded to no pending changes and 0x52 is not implemented. MCCS calls for these notifications for interactive preset changes. This patch fixes RGB state/readback and refusal propagation; it does not claim complete MCCS compliance or add the missing general change-notification system.

## Store and persistence

Factory presets load from the coefficient table; User alone loads from the SDK colour item. The mode lives in the OSD item. Both must become dirty after an implicit transition. The schema, item IDs, flash layout, defaults and coefficient table stay the same.

A pending User snapshot is now used before an SDK User reload. This prevents switching User -> preset -> User, or a gamma reload, from restoring stale flash gains during the debounce window. The change applies at the SDK colour-loader entry so all its callers see the same value.

The flush writes the User gain item before the OSD mode item. That prevents the normal write order from publishing a newly selected User mode before its gain item. This is **not** a transactional two-item journal or a guarantee against flash failure. Existing SDK item integrity/recovery rules still apply.

The existing gate remains: 10 seconds stable ACTIVE, 10 seconds DDC idle, debounce / forced-save policy, menu-close and Save Current Settings requests, and power-transition flush. Acceptance means a RAM edit was accepted, not that a flash commit has completed. A power loss before the gate can lose recent edits. No flash operation is added to the DDC handler.

## What the existing panel data supports

[Panel identity and tentative datasheet facts](https://github.com/awto-au/awto-ddc/blob/3326a1d6f78e7c676947bf7d82f35eb6d9f7166e/docs/monitors/panel-innolux-m280dca-e3b.md): Innolux M280DCA-E3B rev C1. Nominal primaries and white point are not a measurement of each assembled monitor. They do not determine accurate DAC-gain adjustments, transfer curves, or panel variation.

| Available selection | Existing 12-bit R / G / B gains | Defensible support today |
|---|---|---|
| User | Existing stored gains, 0..255 channel controls | Manual adjustment; no measured CCT or tolerance claim |
| 9300 label | 0x6D0 / 0x740 / 0x7D0 | Recovered cool preset; optical target unverified |
| 7500 label | 0x740 / 0x760 / 0x770 | Recovered intermediate preset; optical target unverified |
| 6500 label | 0x760 / 0x760 / 0x6F0 | Recovered warmer preset; not established as D65 |
| 5800 label | 0x7A0 / 0x770 / 0x690 | Recovered warm preset; VCP maps it to 0x04, a relative selection with zero tolerance, not calibrated 5000 K |
| sRGB label | 0x800 / 0x800 / 0x800 | Neutral gains; not proof of an sRGB colour space or white point |
| Other Kelvin targets | No panel-specific gain data | Do not synthesize calibrated gains or advertise a tolerance |

The recovered order has medium confidence in the source TSV. Distinct register coefficients demonstrate meaningful control changes, not measured colour accuracy. Keep these as explicitly uncalibrated relative presets, or rename them Warm / Neutral / Cool with distinct intermediate names. The existing sRGB default was explicitly selected in #355 and is retained by this patch.

A defensible Kelvin calibration requires an actual colorimeter (preferably corrected for the panel backlight, or a spectroradiometer), warm-up and fixed measurement conditions. Measure white chromaticity and luminance, solve/iterate gains within clipping and brightness limits, and validate greyscale tracking and repeatability. A measured sRGB claim additionally needs gamut and transfer-function validation and the required processing; `_PCM_FUNCTION`, `_OCC_SUPPORT` and `_OGC_SUPPORT` are currently off. White-balance gains alone cannot establish an sRGB gamut/transfer-function mode. No new calibrated gain is supplied here.

Remaining product decision: approve the automatic-User policy, including replacement of the single previous User triple. Separately decide whether to retain qualified numeric preset labels pending measurements or rename/hide them. Adding/removing/relabeling presets is intentionally deferred to that decision; this patch changes RGB behaviour only.

## Validation

See the accompanying validation record for exact commands and results. `scripts/rgb_controls_sim.py` exercises the real full-image settings, coefficient-apply and SDK item-store code. Its NOR peripheral model preserves the two store sectors between fresh simulator boots. It does not replace `set_put`, the mode switch, item packing, or load/save logic. Refusal coverage injects a veto response only in the final scenario.

Review before merge; obtain Dan's approval before merging, flashing or changing a physical monitor.
