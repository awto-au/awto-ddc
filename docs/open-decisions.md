# Open decisions, pending tests and unfiled findings (2026-11-19)

- One list; nothing here lives only in chat. Each row has its GitHub issue in the last column (filed 2026-11-19: #239..#246 new, comments on #101 #197 #206 #226 #236 #238); add new rows with their issue number.
- Blocking = blocks a firmware change or a hardware step now. Decides: Dan (D) or agent (A, no decision needed, just run).

| # | title | one line | evidence | blocking | decides | issue |
|---|---|---|---|---|---|---|
| 1 | IOSC tolerance | measure PS Timer2 period vs host once; sets IOSC counts 8 / 6 and `_TMDS_DDC_DEBOUNCE_PS` | `docs/delay-audit.md` | no | A runs, D accepts | #243 |
| 2 | PS debounce 55 | gives 197 us vs 263 us normal; SDK says 300 us [sdk-hypothesis] | `docs/delay-audit.md` | no | D | #243 |
| 3 | Delete diag delay measurement (807 B) | after hardware confirms compile-time counts at 350.8 | `docs/delay-audit.md` | no | D | #243 |
| 4 | DPS17 pass-row pulse | counted in only 45 % of phases | `docs/delay-audit.md`, #110 | no | D | #243 (#110) |
| 5 | `AwtoMs` / Timer2 tick loss | EXINT0 handler >= ~1 ms loses ticks (sim 2.0 ms wall = 1.14 ms fw); not fixed | `docs/delay-audit.md` | no | D | #197 |
| 6 | NVRAM write / erase at 350.8 | 9-cycle MOVX wrapper kept; untested above 87.7 (`C-NVWR`) | `docs/clock-sweep.md` | yes, for dropping the wrapper | A runs on unit 3 | #240 |
| 7 | Temperature | DSS three-step sequence; IOSC / ADC proxies; #206 verdict unknown | `docs/temperature.md` | no | A runs, D on calibration | #206 |
| 8 | Other units / HDMI input / audio-PWM at 350.8 | sweep ran DP on unit 3 only | `docs/clock-sweep.md` | no | D approves unit 1 / 2 tests | #240 |
| 9 | M2PLL Phase B | steps past 350.8 (p372..p487, beyond 487 in small steps, stop after ~3 failures); retune table; `01E5[7]` lock untested | `docs/clock-sweep.md` | no | D go per run | #240 |
| 10 | Flash overclock adoption | ceiling 116.9 MHz; hot / cold, boot CRC, margin ~10 % not done; not adopted | `docs/clock-sweep.md` | no | D | #238 / #240 |
| 11 | Dual-output flash read | unusable, cause unknown (SIO1 wiring?) | `docs/clock-sweep.md` | no | D (park or investigate) | #241 |
| 12 | Scope 1 6.3 fps plateau | not CPU-bound up to 175.4; cause not investigated | `docs/clock-sweep.md` | no | A | #240 |
| 13 | OSD port 0.54 us/B unexplained | hardware 1.08 vs sim 0.54 at 350.8; sweep Phase B | `docs/osd-write-sweep.md` | no | A | #242 |
| 14 | DDR clock sweep (Phase C) | after Phase B, separate go; no display PLL / panel timing | `docs/osd-write-sweep.md` | no | D go | #240 |
| 15 | Scope 2 tile garble | display-side, unresolved; T10 verdict (digits 2/3/4 flicker?) not recorded; scale-up-off test planned | `docs/osd/timing.md`, `docs/osd-hw-tests.md` | no | D records verdict | #226 |
| 16 | Run-glyph trace tests T-A, T-C | pending; width field layout | `docs/saver-fps-hw.md` | no | A | #226 |
| 17 | VLC-turn (T-I) | hardware rotate-on-download could replace `AwtoOsdTurn` | `docs/saver-fps-hw.md` | no | A | #226 |
| 18 | Cache size | 2 KB shared vs 4 KB per bank both within 3 % of unit 3; counters `FDB3..FDC6` settle it | `docs/saver-code-placement.md` | no | A | #242 |
| 19 | OSD open tests OT-1..OT-27 | listed; OT-4 read-back disagreement | `docs/osd/open-items.md` | no | A | #226 |
| 20 | Live register scan units 1 / 2 | read-only, running; results to `re/regmap/obs/` | `docs/register-audit.md` | no | A | #236 / #237 |
| 21 | Debris cleanup (#237) | retire docs that only link; list in the session report, not moved | #237 | no | D | #237 |
| 22 | Undocumented registers that vary | 10 listed (`21D8`, `7607[1]`, `A7E0..`, `8F9D..`, `FF88`) | `docs/register-audit.md` | no | A | #236 |
| 23 | Rule changes held in memory only | SDK unreliable; speed-limiting rules need Dan's ask; PS stays on IOSC | `docs/history.md` | no | D confirms wording in agent rules | agent rules (awto-dan) |

- Not in this table, filed 2026-11-19: #239 (350.8 MHz boot failure), #244 (fragile checks), #245 (ADC / GPIO monitor), #246 (live scan policy), #101 (CEC).
