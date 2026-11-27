🤖 2026-11-12 **Port enable rows wired (d1_enable / d2_enable / d3_enable, ids 36-38): no longer inert.** Image `tmp/fw/AWT26110002-wb-p14ui-portcfg2-be.bin`, 26 gates PASS (new gate `portcfg`). On unit 2 now, **D1 disabled** (Dan's intent: host DP-1 stays off the desktop).

Branches (not merged, not pushed):
- firmware `wb-p14ui-portcfg` ad058fb (on wb-p14ui f311572), `/mnt/2tb/git/awto-ddc-portcfg`
- rtdfw `portcfg` 348d5be (on ui d8d966d), `/mnt/2tb/git/awto-rtdfw-portcfg`; `fw/awto/clean_ref.txt` pins it
- host tools `tools-portcfg` eb703d1 (on main 7788911), `/mnt/2tb/git/awto-ddc-portcfg-tools`

Design:
- Per-port settings block `fw/sdcc/awto_port.inc`: `g_ucAwtoPortOff` (bit n = Dn); `tAwtoPortRow` maps a registry row to (field, port). Next per-port field = a row kind + its bitmask (candidates: `wake_d1..d3`, per-port EDID).
- One owner: `AwtoPortBoot` (AwtoSetInit, right after the settings load) and `AwtoPortSet` (apply `port`). The hardware paths read the mask at their own single choke point; nothing else writes it.
- Flags now `nv` only. Not `risky`: a change that would blank the picture is refused instead of applied and reverted.
- Refused (logged): disabling the input on screen (ACTIVE / display setting); disabling the last enabled one (also settings.c).
- New rtdfw hook `set_veto(id, v)` in `set_put` (integrator refuses and logs).

What a disabled port does (and how each was verified):

| item | where | verified |
|---|---|---|
| HPD held low | `PCB_Dn_HOTPLUG` macro (every SDK / our HPD writer); DP requests above `_DP_HPD_LOW` dropped in `ScalerDpRx1SetHotPlugEvent` (no 700 ms long-HPD wait) | sim: FE02 never written 1 at boot / AUTO / after a live disable; control run with D1 on writes 0, 1. Unit 2: host `card1-DP-1/status` = disconnected, `gdctl show` lists no DP-1 |
| EDID not answered | `ScalerMcuDdcRamEnable` writes DDCn_DDC_ENABLE bit 0 (ddcn_ddc_en) per mask; called again at each change | sim: DDC1_DDC_ENABLE = 0x02 disabled, 0x03 after re-enable. Unit 2: host DP-1 EDID 0 B. [guess] bit 0 = 0 means no EDID reply (regdb "MCU access enable"); not separately probed: with HPD low no source reads it |
| DDC/CI | spare engine follows the active port; a disabled port is never active | by construction |
| receiver off | `ScalerGDIPhyPowerProc`: any power-up action on a disabled port -> `SWITCH_INTERFACE_TO_OFF` | code review only (no PHY model in the sim) |
| not searched / AUTO | `SysSourceHandler` skips the index before any detect; `SysSourceSwitchPort` passes over it (counted as searched); a fixed search on it -> auto | sim: SysSourceScanPortInitial never for D1 (boot, AUTO key); control run scans D2, D1, D3 |
| fast switch / KVM cache | `AwtoSwCacheValid` = 0 | code review |
| wake triggers | `AwtoPsWakeFire` returns 0, line once per trigger per sleep | code review (wake gate passes, D1 on there) |
| dead-port guard | a disabled port is not "another cabled port" | code review (deadport gate passes) |
| selector | row shows `disabled`; taking it enables it through the registry (stored at the gate), line, then the switch. VCP 0x60 / menu Input / test cmds 0x31..0x33 do the same | sim: SOURCE, UP, AUTO -> "D1 enabled by the input selector", mask 0, DDC1 on, HPD high, switched to D1 |
| logs | sync.tsv **E1 01..0B** (`AWTO_SYNC_EV_PORT` 0xE1; was E0, which the input selector owns), one line per boot state / change / refusal / no-op | sim + unit 2 (boot line at +156 ms) |

Control paths: menu Input page; DDC/CI VCP 0xEC / 0xED / 0xEE (and the paged id); `./dev.py settings set d1_enable 0|1 --unit 2`; test cmds 0x06..0x08 off, 0x09..0x0B on (registry path, NVRAM gate). Unit 2: `ddcutil --bus 11 getvcp 0xEC` = 0, 0xED = 1.

Boot order: D1 (DP) is low from GPIO init; the SDK raises it later (DP init / cable detect), after AwtoSetInit, so a stored-off D1 never goes high. HDMI D2 / D3: GPIO init raises HPD before the NVRAM is read; a stored-off HDMI port drops at AwtoSetInit. Open item, not fixed: a disabled HDMI port pulses high from reset to AwtoSetInit (~150 ms).

Unit 2 cold boots (`hass_power.py cycle` via `panel_unit.py --port D2`, ring ms from the power-up, 2026-11-12):

| run | D1 | ACTIVE on D2 | HDMI predetect flaps | desk_layout `layout differed` |
|---|---|---|---|---|
| on-1 (first after flash) | on | 1503 | 0 | no |
| on-2 | on | 5165 | 45 | yes |
| on-3 | on | 4948 | 44 | yes |
| off-1 | off | 1506 | 0 | no |
| off-2 | off | 1504 | 0 | no |
| off-3 | off | 1491 | 0 | no |

- The live disable (22:56:46) caused one mutter re-layout (DP-1 removed); the watcher restored it.
- Seen while testing (not this change): the NVRAM flush line says `flash: type 254 found by the SDK (... 254 = none)`, yet the stored D1 off survived 3 mains cycles.

Remaining inert rows on this issue: `search_order`, `kvm_prefill`, EDID / HDCP / depth rows, power levels, `wake_d1..d3`, `bl_pwm_ms`, `debug_link`, Realtek SDK menu items.

**Integrated** (2026-11-12): `wb-p14ui-int` b38e1e6 (wb-p14ui 094c69a + wb-p14ui-portcfg + wb-p14ui-led), tools `tools-int` 2a17774, rtdfw `ui` fast-forwarded to 348d5be (clean_ref.txt). Image `tmp/fw/AWT26110002-wb-p14ui-int1-be.bin`, 26 gates PASS.
- Event ids: E0 01..0A = input selector (unchanged), **E1 01..0B = port lines** (same args, `AWTO_PORT_WHY_*`), 1C 00..02 = LED. `portcfg_sim.py` EV_PORT 0xE1.
- sync.tsv grew to 262 rows (> one-byte row index): `gen_awto_sync.py` puts the 144 logged rows first (`AWTO_SYNC_ROWS`) and the 118 name-table rows after them (`AWTO_SYNC_NAME_ROW0`); `AwtoSyncTxt` takes a WORD row.
- Unit 2 (int1): after the flash `d1_enable = off`, boot line `D1 disabled by setting (stored)` at +153 / +158 ms; cold boots ACTIVE on D2 at +1503 / +1506 ms, 0 flaps; host DP-1 `disconnected`.
- Selector to a disabled port (`selector_switch_unit.py`, 0 failed): D2 -> D1 logs `D1 enabled by the input selector: HPD up, EDID on, receiver on`, then `switch to D1`; mask bit clear. On hotplug the host drove DP-1 for ~2.3 s (D1 ACTIVE 3840x2160, then L1 hold): with a picture on D1 the debug slave answers on DP-1's bus 15, not 11 (the tool now follows it). End: `set input 1`, `set d1_enable 0` -> `D1 disabled by setting`, NVRAM gate flush; a cold boot after shows `(stored)`; host DP-1 `disconnected`.
