# Parallel HDMI / DP bring-up: interrupt budget (#329, stage 3 of #318)

- Data: `docs/irq-masks-parallel.tsv` (draft per-port rows for `docs/irq-masks.tsv`; not a gate change).
- Measurement: `scripts/phy_budget_sim.py BIN MAP` (DW8051 sim, 350.8 MHz, image of origin/main a2fb396c, 2026-11-23).
- No firmware change, no flash, no hardware run in this study.

## 1. EX0-masked time of a TMDS PHY set-up (sim)
- Call: `ScalerTMDSRx{2,3}PhySetDeferred` alone, pending set, `isr_g_usTMDSRxPhyClk` preset; delay loops are real instructions. `CheckCDRStable_EXINT0`, `MeasureClk_EXINT0`, `CheckDataDFE` are stubbed (hardware waits, MeasureClk <= 9 x 5 us): add <= 0.1 ms.
- Median of 4 reps after a warm-up rep.

| path | Rx2 us | Rx3 us | static (docs/delays.md) | hardware |
|---|---|---|---|---|
| DCDR <= 200 MHz | 1101 | 1123 | ~1200 | - |
| ACDR 200-340 MHz | 2638 | 2608-2656 | - | - |
| ACDR > 340 MHz (4K60), first CDR check passes | 3138 | 3137-3156 | ~4300 | 3-4 ms (M057, 10 locks); longest masked stretch 4475 us (25 locks, `tmds-ex0-shared` arm 4) |

- Sim 3.14 ms matches hardware 3-4 ms for the normal 4K60 lock.
- The 4K60 retry with the 2.9 ms RLE0638 block (9125 us, never seen in 35 hardware locks) was removed: requirement not confirmed (#331). Sim after: 4K60 first try 3136 / 3155 us (Rx2 / Rx3), before 3138 / 3137 us, same image otherwise (2026-11-23).
- Two set-ups back to back (Rx2 then Rx3): `PhySetDeferred` restores EX0 at return and the wrapper runs once per port per main pass, so each is its own masked stretch (1.1-3.2 ms each); a pending request is taken in the gap. The sum (up to 6.3 ms) is time to ready, not a mask. Rule for stage 3: at most one set-up per main pass.
- Other EX0 masks in the inventory: <= 30 us each (`AwtoSdTick` 30), `ScalerDpRx1PhyCTS` 742 us is compliance mode only. ISR-context spins: `Tp2SetPhy_EXINT0` 0.71 ms, `RebuildPhy_WDINT` 0.85 ms (they delay the TMDS clock IRQ, which only sets a pending flag).
- Sim artifact: one Rx3 rep in 4 returned early (33 us); median is unaffected.

## 2. DP AUX during a mask
- Which AUX traffic needs EXINT0: DPCD writes / reads in the firmware-handled ranges (TP set 0x102.., lane set, 0x202-0x207 status, symbol error count). I2C-over-AUX (EDID) and base DPCD are answered by hardware: 0 AUX IRQs in 6600 EDID reads (#256 comment). A trained idle link needs no EXINT0 work: `ScalerDpRx1SetFifoIRQ/WD` are enabled only in `ScalerDpFirstActiveProc` (selected port active), disabled at reset.
- Deadlines: AUX reply 300 us (sink), source reply timeout 400 us (DP CTS 4.2.1.x, quoted in i915); LT status in place within CR 100 us / EQ 400 us of the TP write (we advertise EQ interval 400 us, `RL6449_Series_DPRx1.c:775`).
- Source retry behaviour (Linux mirror, `drivers/gpu/drm/i915/display/intel_dp_aux.c`, `drm_dp_helper.c`, `intel_dp_link_training.c`):
  - i915 SKL-GLK AUX timeout 1.6 ms, ICL+ 4 ms (`TIME_OUT_MAX`); 5 tries per transfer; `drm_dp_dpcd_access` 32 attempts on timeout.
  - LT: CR 5 identical-voltage tries (10 total), EQ 5 tries; failure reduces rate / lanes.
  - Spec-minimum source (400 us timeout, "at least 3 tries" per the i915 comment): not in this repo's sources, not verified against the DP spec text.
- LT cadence [derived]: iteration = AUX write ~0.4 ms + interval (0.1 CR / 0.4 EQ) + status read ~0.4 ms (`docs/flash-dp-aux.md` bare transaction 0.4 ms) = 0.9 (CR) / 1.2 ms (EQ), about 2 transactions per ms.

| mask | transactions arriving | LT iterations with stale / no status | i915 (ICL+, 4 ms timeout) | spec-minimum source |
|---|---|---|---|---|
| 1.1 ms (DCDR) | ~2 | ~1 | no loss | no loss |
| 3.1 ms (4K60 normal) | ~6 | ~3 of 5 | no loss (one 4 ms wait) | exceeds 3 x 400 us: a transaction fails, LT restarts |
| 4.5 ms (hardware max seen) | ~9 | ~4 of 5 | no loss | LT restarts |
| flash erase 200 ms | ~400 | all | 5 x 4 ms = 20 ms per transfer, 32 attempts = 640 ms: survives one transfer, LT fails | fails |

- An established link does not drop: the main link is hardware; AUX is quiet except IRQ_HPD / status polls. The exposure is a link training that overlaps a mask: the training fails or falls back to a lower rate, not a link drop.
- Overlap chance [derived]: one 3.1 ms set-up inside an LT window of ~100 ms (sync log: "120 ms after the loop first saw it training", includes host spread) = ~3 % per set-up. Not measured.
- CEC: byte period 24 ms, bit 2.4 ms, frame handling once per >= 24 ms (`docs/cec.md`): tolerates every mask <= 3.2 ms (HDMI set-up). A 200 ms halt drops frames; the CEC initiator retransmits.

## 3. Flash halts (#308)
- Datasheet maxima: erase 200 ms, WRSR 40 ms, page program 3 ms (`docs/delays.md`, MX25L8006E). Measured: 2 programs in 5 ms (`docs/nvram-settings.md` burst test); an erase happens at the EEPROM-emulation page move, about every 239 item writes. Not modelled in the sim, not measured on hardware; a halt starves EX0, Timer2 and EX1 alike (WDT does not bite, `FFEA[5]`).
- The NV flush gate (`fw/nvram/nv_gate.c` `AwtoNvService`) opens on: ACTIVE on the selected port, power normal, no DDC/CI for 10 s, `usStable` >= 10 s; forced after 60 s with 3 s of ACTIVE. Its inputs are the selected port's state only: an idle-port PHY set-up, DP LT or HPD event does not reset `usStable`.
- A program (3 ms) is comparable to one PHY set-up; an erase (200 ms) fails any DP LT and any HDMI lock in progress (Timer2 ticks lost, `AWTO_NV_STABLE_MS` comment, #151).
- Deferral needed for stage 3:
  - New gate input: idle-port bring-up activity (TMDS PhyPend / set-up running, DP LT status not idle, HPD event on any port, search state not settled) clears `usStable`, as `g_ucAwtoNvSwitch` does for the selected port.
  - The forced path (60 s) also waits for it; bound the wait (one search period, 3 s DP / 2 s HDMI) so a flapping idle port cannot block a save for ever.
  - No idle-port bring-up is started while an erase is pending (an erase is the only halt long enough to matter; programs are not).

## 4. HDCP and PHY power of an unselected port
- HDCP is parked in the shipped image: `_AWTO_HDCP = _OFF` (`RL6449_Project.h:2429`, #44): no key tables, no HDCP DDC slave, DPCD Bcaps not advertised; `_TMDS_HDCP_2_2_SUPPORT` and `_DP_HDCP_2_2_SUPPORT` are `_OFF`. No HDCP state exists on an idle port; sources see a non-HDCP sink on both.
- If HDCP returns: 1.4 is a per-port hardware block (pages 71 / 72, key ports 71C4 / 72C4; DP via DPCD, `ScalerDpRx1HDCPBlockReset`, `ScalerDpRx1CpIRQ` masks EX0 0.3-0.4 us). 2.2 is one shared handler (`ScalerHdcp2IntHandler_EXINT0`): needs a per-port context before parallel ports.
- DP trained with no active stream: the SDK enables FIFO under/overflow IRQ and watchdog only in `ScalerDpFirstActiveProc` (selected port), so a trained idle link raises no stream IRQ. PHY stays powered: link-status IRQ and the AUX IRQ remain (0.3-0.4 us masks, `ScalerDpRx1LinkStatusIRQ`). Display path, measure block and I/M/D domains are single and selected-port only: an idle DP source streams into an unconsumed MAC. Whether the MAC / FIFO tolerates that for minutes is unproven (needs two sources, #330).
- TMDS idle port: `ScalerTMDSRxPowerSavingProc` (freq-detect disable, auto output) is the SDK's low-power state; a port left in normal state keeps its freq-detect IRQ in EXINT0 (per port, pending flag only).

## Go / no-go for #318 stage 3
- GO for stages 1 and 2 (unchanged by this study).
- NO-GO for stage 3 as "fully parallel" (PHY set-up and DP LT allowed to overlap, NV writes unconstrained). GO for stage 3 in a serialised form:
  - One TMDS set-up per main pass, and none while a DP LT is running or within ~20 ms of its last AUX event (defers the HDMI lock by at most the LT time, ~100-120 ms; an HDMI source has no deadline).
  - DP LT already running when a set-up is due: wait. A set-up already running when LT starts: <= 3.2 ms (4.5 ms seen), survivable by i915 on ICL+; a spec-minimum source may restart its LT once.
  - NV flush gate gets the idle-port activity input before any idle-port bring-up ships.
- Expected gain of the serialised form: stage-3 claim was 400-500 ms off the picture time [inference, #318]; the serialisation costs at most ~120 ms of that on a coincident LT, only in the overlap case.
- Not answerable in the sim, needs hardware: (a) DP source live during an HDMI PHY set-up (DP host on D1 + HDMI host on D2 at once; unit 3 has DP-4 disabled in the layout and one HDMI source; two sources = #330, needs Dan); (b) flash erase halt length and its Timer2 deficit (Timer2 count across `ScalerFlashErasePage`); (c) idle DP MAC tolerance with no consumer.
