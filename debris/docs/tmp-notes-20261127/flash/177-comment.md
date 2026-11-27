🤖 Tool fixes for this incident: branch `tools-flash` (worktree /mnt/2tb/git/awto-ddc-flash, 419427b + 58025d8), not merged.

**What changed**
1. No reset onto a mixed image. `rtd_flash_image.py` sends 0xEE <- 0x02 only when the image region is whole: either nothing was erased and the manifest is clean, or every changed sector was written and verified. In all other cases the MCU stays halted in ISP, so a rerun on the same bus continues. This covers a signal stop, an error after the first erase, and a manifest source `write-in-progress`/`write-failed` left by an earlier session. Every run ends with a `UNIT STATE: ...` line. `dev.py flash` repeats it from the manifest when a flash fails.
2. The time budget now runs before the first erase. `--max-min` (dev.py: 20 min, `--max-min` overrides) times one dry page program of 256 x 0xFF in the session's write mode. 0xFF clears no NOR bits, and the target is the last page of the highest changed sector; that sector's CRC is checked after. The projection is the dry-page time x the non-blank pages, plus the measured write/read cost x the fixed per-sector messages, plus tSE max.
   - Over budget: a byte-mode run is re-projected in burst. If it is still over: rc 8, nothing erased, reset sent, old image runs.
   - If the burst dry page fails, the run uses byte mode (#167). A failed burst inside the dry page is never flushed: the flush would program stale SRAM into a live sector.
   - Once writing has started there is no time stop. After 5 sectors the measured rate is logged only.
3. Bus kind:
   - `i2cbus.bus_kind`: an `i915 gmbus*` adapter is ddc and an `AUX *` adapter is dp-aux; otherwise the DRM connector's ddc link decides.
   - NVIDIA names DP and HDMI adapters alike, so `devices.json` now has `bus_kind`, `bus_kind_dp` and `write_mode` per unit:
     - unit 1: ddc, burst
     - unit 2: ddc + dp-aux on DP-1, byte (#167)
     - unit 3: dp-aux, burst
   - `dev.py flash` passes `--bus-kind`. Byte mode on dp-aux is switched to burst, by both dev.py and the tool.
4. Sector order (`boot_last`):
   - **Why bank 0 0x5000.. went first:** the old sort key put every banked sector first in index order, so bank 0's banked part (index 5..15) came first.
   - New order: banked sectors of banks 1..; then bank 0's banked part (DDR/startup init, `fw/bank_layout.tsv` region 0); then common of banks 1..; bank 0 common last.
   - A relinked image (214 changed sectors) still won't boot when mixed, because calls cross banks. The budget check before any write is the real guard.

**Replay of 2026-11-13 with the new code (estimate from #71 per-message costs, not run):** byte mode on DP AUX projects about 90 s per sector, so it is re-projected in burst. Burst is about 6 s per sector, roughly 21 min for 214 sectors, which is over 20 min, so the run is refused with rc 8: nothing erased, unit reset onto its old image, still working. `--max-min 25` would have run it in burst.

**Tests (offline, no hardware):** `tests/test_flash_stop.py` (15), using a fake clock with DP AUX message costs:
- budget refusal leaves nothing erased;
- byte is switched to burst;
- the dry page leaves flash unchanged and the corruption check fires;
- no time stop once writing;
- `boot_last` order;
- flash_main sends no reset on a signal stop / error / refusal while mixed, and does reset on refusal while clean and on success;
- byte on dp-aux becomes burst;
- `bus_kind`.

dev.py tests (devices.json write_mode/bus_kind, budget arg) are in `tests/test_dev_tool_hazards.py`. Flash/dev suites: 114 pass, plus the 4 failures that already fail on main.

**Hardware check on unit 2:** see the report (pending the unit lock).

**Unit 3 recovery runbook (needs Dan to recable):** see below.
1. Leave unit 3 on mains. Unplug unit 2's HDMI cable (Intel HDMI-A-2, `card1-HDMI-A-2`, bus 11) from unit 2 and plug it into unit 3's HDMI input. Unit 2 keeps its DP-1 cable. The host may move windows; no layout change is needed.
2. Check the bus: `ddcutil --bus 11 detect` or `python3 scripts/i2cbus.py`. The EDID may be silent because unit 3's firmware is mixed; ISP 0x4A is hardware and answers anyway.
3. From the tree with `tools-flash` (merged main, or /mnt/2tb/git/awto-ddc-flash):
   `./dev.py flash --unit 3 --force --bus 11 --write-mode byte /mnt/2tb/git/awto-ddc-ui/tmp/fw/AWT26110003-wb-p14ui-one1-be.bin`
   - Byte at 1 MHz on i915 is the proven recovery path: 224 sectors in 84 s (#156).
   - From main, the manifest `tmp/fw/AWT26110003-flash-state.json` (source write-in-progress, sectors 5..9 known) drives it. From the worktree there is no manifest, so all sectors are written.
   - Expect `UNIT STATE: new image verified, reset sent`. If it ends `UNIT STATE: MIXED`, rerun the same command and do not power-cycle.
4. Check: `./dev.py health --unit 3 --force` (unit 3 is found on bus 11 by EDID).
5. Cables back: unit 2's HDMI cable back into unit 2. Unit 3 goes back on NVIDIA DP-4 when Dan wants it there (the Philips is on DP-4 now). Update the `devices.json` note.
