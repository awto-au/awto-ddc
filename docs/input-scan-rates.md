# Input scan rates (D7, `fw/awto/inputs.tsv` column `rate`)

Decided 2026-11-18 (Dan): keys every pass, the rest every `AWTO_IN_SLOW_MS`, selector pulse counts checked first. Moved here from the former saver-mode doc.

- `rate` per row, generated into `tAwtoInFast` / `tAwtoInSlow` (`scripts/gen_awto_inputs.py`); poll in `fw/input/inputs.c` `AwtoInScan`.
- Slow rows: a share per pass (elapsed ms x slow rows / `AWTO_IN_SLOW_MS`), not one burst: a burst pass (+3 ms) widens the gap between DPS17 reads.
- XDATA +5 B (last tick, cursor, carry).

| class | rows | consumer | min rate from its own arithmetic | chosen | reason |
|---|---|---|---|---|---|
| keys | ADC0, ADC1, POWER, SOURCE MENU DOWN UP AUTO | `AwtoKeyPoll` (`keys.c`): samples every `AWTO_KEY_SAMPLE_MS` 10 ms, 2 equal samples = 20 ms min press | one fresh read per 10 ms sample (idle pass 2.9 ms) | pass | Dan: keys every pass; ADC rows also feed the key rows (order) |
| pulse counter | DPS17 | `AWTO_PS_COUNT` -> selector `p17` edges/s (`console.c` `AwtoPsValue`) | sample gap <= pulse width 4 ms (#110) | pass | slower reads miss pulses; even per pass 40-50 % of 4 ms pulses are counted (sim, 200 phases: 81 before, 99 after) |
| diagnostics | 35 other rows: GPIO pads, ADC2, VGA regs, IR, HPSEL, HPD, cable, DPS15/16, power outputs | ring (host timestamps), console GPIO page, selector signal lines | no decision reads them (SDK cable / wake poll read the pins themselves) | 20 ms | = `AWTO_GPIO_REFRESH_MS` (console redraw) = shortest panel step (T5, T3 own pattern: 20 ms, `docs/delays.md`) so the ring still resolves a power sequence |

- Slow row: a pulse is seen when wider than the worst read gap: sim 28 ms (20 ms + one pass jitter), before 19.5 ms. Shorter pulses and cable-plug bounce are not logged any more (host `gpio_diag.py` ring).
- Pass rows: worst gap 19.8 ms (one heavy pass).
- Test: `scripts/input_rate_sim.py` (gate `inputrate`): calibrates the worst read gap per row, then pulses of exactly that width at 40 start phases: all seen (pass rows and slow row).
- Cost, idle ACTIVE pass (sim, 3 s, same image otherwise): `AwtoGpioPoll` 3106 instr / 473 us -> 1575 / 391 us; pass 8493 -> 6937 instr, 3017 -> 2917 us (-3.3 %).
- Not done: a second slow class (80 ms for the non-power rows) would save ~30 us more; not worth a class.
- DPS17 at 4 ms is already under-counted at pass rate; a reliable count needs a timer / hardware edge counter, not the main loop.
