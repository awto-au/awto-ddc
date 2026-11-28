# AWTO DDC/CI compatibility review - issue #388

Review date: 28 November 2026. Initial analysis at ce8e1625; publication reconciled against main cac1c66f7ce73112787040d11f6f5c7903a980e0. Dan approved the follow-up scope and requested publication on 28 November. This documentation change applies no firmware or host-tool implementation and authorizes no merge or flash.

## Published state and approval update

The source tables below retain the initial **ce8e1625** review boundary. This update distinguishes newer merged work from the approved follow-up. Source inspection of current main **cac1c66f7ce73112787040d11f6f5c7903a980e0** confirms:

| Area | Published state at cac1c66f | Remaining recommendation |
|---|---|---|
| Input 60 | Main values unchanged; zero sub-input constant made explicit | Keep the encoding and existing low-byte Set behavior |
| Pacing | The wire handler now silently drops ordinary Set VCP requests less than 110 ms after the last accepted request; audio-test and debug-link writes bypass it | Reconcile this merged policy with host-side, per-monitor pacing. Removing the drop rule would be a separate behavior change, not something this documentation does |
| Firmware string | FE E1 prefix is intercepted before generic Get; ASCII build tag is limited to ten characters by AWTO_DDC_CAP_CHUNK | Track full-client interoperability, exact selector/length handling, and truncation under #385 |
| Gamma | F2 remains the live gamma row, 0=Off through 4=2.4; 72 is still unsupported | Add the translated MCCS 72 adapter, retaining F2 |
| Search | EF remains Auto=0 / Fixed=1; ED remains D2 enable | Synchronize EF with runtime fallback to Auto |
| Inert advertising | Generator still advertises all direct rows, including 87/F7/FB/FC | Filter discovery while preserving explicit legacy storage access |
| RGB371 | The preset early return remains in nv_gate.c. The existing review patch has been archived in the repository, not applied | Recover/rebase that patch; coordinate gamma reload/persistence regressions |

Current sources: [wire handler](https://github.com/awto-au/awto-ddc/blob/cac1c66f7ce73112787040d11f6f5c7903a980e0/fw/ddcci/ddcci.c), [registry](https://github.com/awto-au/awto-ddc/blob/cac1c66f7ce73112787040d11f6f5c7903a980e0/fw/rtdfw/settings/registry.tsv), [VCP adapter](https://github.com/awto-au/awto-ddc/blob/cac1c66f7ce73112787040d11f6f5c7903a980e0/fw/rtdfw/awto/settings/vcp.c), [generator](https://github.com/awto-au/awto-ddc/blob/cac1c66f7ce73112787040d11f6f5c7903a980e0/scripts/settings_gen.py), [RGB gate](https://github.com/awto-au/awto-ddc/blob/cac1c66f7ce73112787040d11f6f5c7903a980e0/fw/nvram/nv_gate.c).

The [latest implementation comment](https://github.com/awto-au/awto-ddc/issues/388#issuecomment-7236890658) records merging and flashing this earlier work to unit 3, health 13/13, and a hardware input read of 0F with sub-input 0. It explicitly limits the 110 ms and FE E1 validation to the 18-check simulator run; neither has recorded wire validation there. These are the other session's results, not new tests performed for this publication. Keep the existing needs-test status and the issue open.

The older implementation note's “no gamma-preset feature” and “not 0xEF” descriptions need correction: the live gamma feature is already at F2 and automatic search is already at EF. Lack of a standard 72 adapter does not mean lack of gamma processing. Likewise, the high/low 60 convention is not exclusive to Philips: the Lenovo model report below also documents it.

The later Dahua account reports a stock-shaped Realtek dispatch path and no deliberate Set VCP rate limiter. Matching function names/structure is useful static evidence but does not, by itself, establish every VCP case or exact pacing behavior on hardware. Preserve that distinction rather than treating the entire Dahua/SDK implementation as byte-for-byte identical.

RGB archive: [review, patch and original validation](https://github.com/awto-au/awto-ddc/blob/e7e2fb622425e950dcf257c9f207ccd76e25b499/docs/archive/2026-11-28-colour-controls-371/README.md), linked from the [371 publication comment](https://github.com/awto-au/awto-ddc/issues/371#issuecomment-7235280456). The prior review's “unpublished” statement below describes its original state, before that archive was added.

**Approval record:** Dan replied “Yes” to the proposed small implementation and explicitly asked to update issue #388 with all findings and add the document. Record the gamma/legacy alias, capabilities, EF readback, focused host changes and simulator plan as approved follow-up. This publication implements documentation only. Merging implementation or flashing still requires separate approval.

## Recommended follow-up

Keep AWTO's identity and existing vendor interface. Add a correctly encoded MCCS gamma adapter at **0x72**, retaining **0xF2 with its existing 0..4 values**. Keep **0x60 unchanged**: both its current registry mapping and fallback handler already produce a zero high byte with the appropriate main-input codes. Keep automatic input search at **0xEF**, not Philips 0xED. Remove inert controls from automatic capability discovery, retaining their legacy storage access with explicit host labels. Do not implement SmartImage, PIP/PBP, Philips power-LED codes or TPV factory commands as part of this change.

First make capabilities truthful and search readback accurate. Gamma is the only worthwhile new public VCP feature in the first implementation. Dan has approved this follow-up scope; implementation, validation, merge and deployment status must still be tracked separately.

## Initial review work and revision boundary (ce8e1625)

- Reviewed main **ce8e1625f5c168f67f0f28145395f2bee448f5f0**, rechecked unchanged at the end of source inspection.
- Listed both pages of branches: **121 remote branches**. Relevant named branches include `philips-re` (2daba5db), `philips-gui` (1bf1181b), `philips-dump` (e422b280), `edge-sweep` (cc80c83f), `gate-fixes` (1a6630d7), and `host-fixes` (a3e12c24). No named RGB branch appears. Generic worktree branches exist; their names do not establish active work or an assigned running agent.
- Seven open PRs were listed: **#344, #207, #190, #103, #99, #98, #97**. None is an RGB or Philips VCP interface PR. A branch listing is not proof that nobody is working in an unpublished checkout.
- [#371 comment](https://github.com/awto-au/awto-ddc/issues/371#issuecomment-7231831452) records Dan's automatic-User policy. Main still contains the early return in `set_sdk_put()`.
- Read the existing **awto-ddc-colour-controls-371-review.zip**. Its README identifies proposed local commit **351d945**, branch **review/371-rgb-user**, base **3326a1d6**; it explicitly says no remote branch/PR was published. It includes the RGB behavior, refusal propagation and pending User-store work, with previously recorded simulator validation. Those logs were inspected as prior evidence, not rerun here. Do not overwrite, reimplement or treat that patch as merged.
- [#388's later comment](https://github.com/awto-au/awto-ddc/issues/388#issuecomment-7234569128) records earlier assent to adoption and a request to inspect Dahua and SDK behavior first. This review supplies that comparison. At the initial review, no approval had yet been given for its specific follow-up interface changes. Dan has since approved that scope; see the publication update above.
- Gamma changes must be layered after/rebased with the RGB patch: gamma application can reload colour data, and the pending User gain snapshot must survive that path.

## Evidence and confidence

AWTO behavior in the baseline matrices below is source-verified against ce8e1625; the publication update above identifies subsequent changes at cac1c66f. It is not a claim of a new hardware measurement. Philips labels distinguish app decoding from actual 288E2 reads. Other brands are examples of particular models, not brand-wide specifications.

| Ref | Primary evidence |
|---|---|
| A1 | [AWTO registry](https://github.com/awto-au/awto-ddc/blob/ce8e1625f5c168f67f0f28145395f2bee448f5f0/fw/rtdfw/settings/registry.tsv) |
| A2 | [Actual VCP adapter](https://github.com/awto-au/awto-ddc/blob/ce8e1625f5c168f67f0f28145395f2bee448f5f0/fw/rtdfw/awto/settings/vcp.c), [settings backend](https://github.com/awto-au/awto-ddc/blob/ce8e1625f5c168f67f0f28145395f2bee448f5f0/fw/rtdfw/awto/settings/settings.c) |
| A3 | [Wire handler](https://github.com/awto-au/awto-ddc/blob/ce8e1625f5c168f67f0f28145395f2bee448f5f0/fw/ddcci/ddcci.c) |
| A4 | [Generator](https://github.com/awto-au/awto-ddc/blob/ce8e1625f5c168f67f0f28145395f2bee448f5f0/scripts/settings_gen.py), [generated table](https://github.com/awto-au/awto-ddc/blob/ce8e1625f5c168f67f0f28145395f2bee448f5f0/fw/rtdfw/awto/settings/set_table.c) |
| A5 | [Settings integration](https://github.com/awto-au/awto-ddc/blob/ce8e1625f5c168f67f0f28145395f2bee448f5f0/fw/settings/settings_glue.c), [SDK store gate](https://github.com/awto-au/awto-ddc/blob/ce8e1625f5c168f67f0f28145395f2bee448f5f0/fw/nvram/nv_gate.c) |
| A6 | [DDC host tool](https://github.com/awto-au/awto-ddc/blob/ce8e1625f5c168f67f0f28145395f2bee448f5f0/scripts/ddc_ctl.py), [wire simulator regression](https://github.com/awto-au/awto-ddc/blob/ce8e1625f5c168f67f0f28145395f2bee448f5f0/scripts/ddc_sim.py) |
| P | [SmartControl protocol analysis](https://github.com/awto-au/awto-ddc/blob/ce8e1625f5c168f67f0f28145395f2bee448f5f0/docs/monitors/smartcontrol-wine.md), especially sections 5, 7, 8 |
| R | Original SDK mirror at [3d38340ec8518a8888fd5d8dbb181c2a7418e11c](https://github.com/Kingdomwhisky/RTD-Scaler-TEST/tree/3d38340ec8518a8888fd5d8dbb181c2a7418e11c): [RTD2014Ddcci.c](https://github.com/Kingdomwhisky/RTD-Scaler-TEST/blob/3d38340ec8518a8888fd5d8dbb181c2a7418e11c/User/RTD%20Series/RTD2014Osd/Code/RTD2014Ddcci.c), [RL6449 project capabilities](https://github.com/Kingdomwhisky/RTD-Scaler-TEST/blob/3d38340ec8518a8888fd5d8dbb181c2a7418e11c/Project/Header/RL6449_Project.h) |
| D | [Recorded original JXC/Dahua DDC measurements](https://github.com/awto-au/awto-ddc/blob/ce8e1625f5c168f67f0f28145395f2bee448f5f0/docs/ddc-control.md), [Dahua input-selector static analysis](https://github.com/awto-au/awto-ddc/blob/ce8e1625f5c168f67f0f28145395f2bee448f5f0/docs/reversing/dahua-fw/source-select.md) |
| M | VESA-authored [MCCS 2.2a](https://files.lunar.fyi/mccs.pdf), printed pp. 43-46 for gamma; [VESA availability](https://vesa.org/vesa-standards/) |
| V | [ddcutil feature reference](https://www.ddcutil.com/vcpinfo_output/) and [Get output formats](https://www.ddcutil.com/command_getvcp/) |

## Compatibility matrix: standard features and encoding

“Keep” means preserve the present interface; it does not assert full MCCS compliance.

| Feature / code | AWTO at ce8e1625 | MCCS / Philips comparison | Recommendation |
|---|---|---|---|
| Backlight 10, contrast 12 | Active, 0..100 | Conventional codes; Philips uses 0..100 | Keep |
| Presets 14 | 08 cool/9300, 06 7500, 05 6500, 04 labeled 5800, 01 sRGB, 0B User | Philips offers additional presets; 04 is conventionally 5000 K | Keep existing values and qualified labels. Do not add unsupported temperatures or claim calibrated white points |
| RGB 16/18/1A | 0..255, active-preset gains read; writes outside User currently discarded | Philips uses 0..100. Reported maximum, not the code alone, determines the continuous scale | Preserve 255 maximum and clients. Apply #371 separately; hosts must scale by returned maximum |
| Main input 60 | 000F DP, 0011 HDMI1, 0012 HDMI2; maximum 0012 | Fits conventional main-input values. Philips adds its own sub-input representation | **No encoding change**. Do not add phantom ports or sub-inputs |
| Gamma 72 / F2 | 72 unsupported; F2 enum 0 Off, 1 1.8, 2 2.0, 3 2.2, 4 2.4 | 72 is gamma with a complex two-byte codec. Philips app names 1.8 through 2.6 | Add a codec at 72, retain F2 exactly. No 2.6 table exists in the AWTO row |
| Volume 62 | Active 0..100, DVC implementation | Same broad meaning as Philips | Keep. Older docs incorrectly call it inert |
| Mute 8D | Off=2, On=1 | Same Philips values | Keep; no new screen-blank behavior |
| Power D6 | Values 1..5 accepted; wire Get normal=1, otherwise=4 | Philips advertises 1/4/5; power states need not round-trip the request | Keep collapse behavior; host verification must compare resulting state, not demand identical requested number |
| Reset 04 / 08 | Factory / colour reset actions | Standard feature roles | Keep. Set has no success-response packet; a readable action probe does not prove execution |
| Identity C8 / C9 / DF | Realtek 0009, firmware level 0100, MCCS 0202 | Philips reports its own controller/version | Keep truthful AWTO values; do not impersonate Philips |
| New-control 02 / active-control 52 | 02 fixed at 1; 52 unsupported | Incomplete change notification | Document limitation; leave general event notification for separate work |
| Display application DC | Unsupported; colour_effect is inert | Standard application feature; Philips brands it SmartImage and has model-specific values | **Do not expose DC** until actual application presets and side effects exist |
| Scaling 86 / FE | 86 unsupported; FE enum Full/16:9/4:3/5:4/Original/User | 86 is a standard scaling control; Philips app contains differing value tables | A possible later adapter, retaining FE. First prove each implemented geometry; do not copy Philips enum indices |
| Language CC | Unsupported directly; language stored through registry | Philips/SDK use a language enum | Later two-language adapter only if the user-visible menu actually changes language; stored SDK fields alone are insufficient |
| C0, AC, AE, B6 | No direct standard adapters; some equivalent information rows exist | Standard usage, frequency and technology queries | Optional later read-only adapters; follow each code's units and byte layout, never copy raw internal values |
| 0B/0C, 05, 6C/6E/70, LUT 73..75 | Not implemented as direct features | Supported by some reference monitors | Leave unsupported; no need to imitate the full reference |
| Auto setup 1E/A2, scan mode DA | No AWTO automatic-search adapter here | These are not a portable Auto Input Search command | Do not repurpose them |

Sources: A1-A6, P, V. Continuous ranges are allowed to differ across monitors; preserve AWTO's existing range. Codes E0..FF are manufacturer space, so reuse by another manufacturer is not itself an MCCS violation. It is a serious compatibility collision for a host applying the wrong profile.

## Vendor extensions and collisions

This covers every currently assigned AWTO vendor code, plus Philips codes that must remain absent. Shared numbers in the command-opcode field and VCP-feature field are different namespaces.

| Code | AWTO meaning | Philips/TPV meaning / evidence | Decision |
|---|---|---|---|
| E0/E1 | Registry select/value | E0 unknown; multi-byte E1 participates in firmware-version command | Preserve AWTO paging |
| E2/E3 | Schema / confirm-save-defaults | No equivalent proven for 288E2 | Preserve |
| E4/E5 | Menu command/state | No equivalent proven | Preserve |
| E6 | Fast switch | PBP-state observation on another Philips model, low confidence | Preserve; no PBP alias |
| E7 | Keep idle receivers | Unknown, possible sharpness | Preserve; unknown is not a mapping |
| E8 | Free direct slot | Unknown/not established | Reserve; no speculative allocation |
| E9 | Host-time table write and drift/sync Get | Resolution notification, 0/2 | Preserve AWTO host time; never alias |
| EA | OSD timeout, 0..120 s | No established 288E2 equivalence | Preserve |
| EB | Screensaver/action selection | Unknown, possible SmartResponse | Preserve; retired values 1..4 remain no-ops and must not be offered as working choices |
| EC | D1 enable | PIP size/location, two packed bytes | Preserve D1 enable. No dual interpretation |
| ED | D2 enable | InputAuto, app-only and absent from 288E2 capabilities | **Do not alias auto search here** |
| EE | D3 enable | No established 288E2 equivalence | Preserve |
| EF | Auto=0 / Fixed=1 | Unknown FF/FF response | Preserve AWTO search; no Philips semantic inferred |
| F0 | Debug messages | Unknown | Preserve |
| F1 | DP version 0..2 | Not established for Philips; original Realtek demo uses F1 as Dell-DDM support | Preserve DP version; do not respond as Dell support |
| F2 | Gamma 0..4 | Philips power LED 0..4, app/other-model evidence, absent from 288E2 caps | Preserve gamma; new standard 72 is a translated alias |
| F3 | Digital black level 0..100 | No established Philips equivalence | Preserve. F3 capabilities-request *opcode* is unrelated |
| F4 | OSD scale 0/1 | No proven Philips mapping; some LG models use it for input switching | Preserve; never dispatch by number without identity/transport profile |
| F5 | Free direct slot | No established mapping | Reserve |
| F6 | L1 backlight-off enable | PIP/PBP swap action; 288E2 Get returns unsupported despite advertising it | Preserve AWTO; never send Philips swap to AWTO |
| F7 | L1 delay, inert | PIP/PBP supported modes, 288E2 42 | Hide AWTO inert row from discovery, retain legacy storage access |
| F8 | L2 enable | HDR label in app, not 288E2 caps; other TPV uses vary | Preserve |
| F9 | L2 delay | No established Philips equivalence | Preserve |
| FA | L3 enable | Unknown | Preserve |
| FB | L3 delay, inert | Unknown | Hide inert advertising, retain legacy access |
| FC | Search order, inert | Unknown | Hide inert advertising, retain legacy access |
| FD | DP EDID mode | Unknown | Preserve |
| FE | Aspect | Unknown simple FE response; FE E1 / FE EF are extended commands | Preserve simple FE; extended parser work is separate |
| FF | Overscan | Unknown | Preserve |
| A5, 95..98 | Unsupported window controls | Philips PIP/PBP mode/geometry | Do not implement: no AWTO multi-window feature |

Source: A1-A5, P, R. “Unknown” deliberately avoids inferring Philips behavior from numerical maxima.

## Gamma: exact proposed adapter

MCCS 72 uses SH for the gamma value and SL for the operation. Absolute white adjustment uses SL=00; SH=100×(gamma−1). Bypass uses SL=05. Its capabilities list includes tolerance, native gamma, a support descriptor and supported gamma values; it is not an ordinary enum list. [M, pp.43-46]

| Current AWTO row / F2 | Proposed 72 Get / Set word | Meaning |
|---|---|---|
| 0 | 0005 | Bypass processing; **not a claim that the physical panel gamma becomes 1.0** |
| 1 | 5000 | 1.8 |
| 2 | 6400 | 2.0 |
| 3 | 7800 | 2.2 |
| 4 | 8C00 | 2.4 |

Proposed caps entry: **72(0B 78 FA 50 64 78 8C)**. Here 0B makes no accuracy-tolerance claim, 78 follows the existing native 2.2 model, and FA identifies discrete absolute presets with bypass. Native 2.2 is an existing modeling assumption in the gamma generator, not new optical validation. If that assumption is withdrawn, revise the metadata before release. [M; AWTO gamma generator]

Keep the registry row, stable ID, NVRAM values, default Off, and F2 values unchanged. Advertise and handle 72 only for builds with the gamma processing path enabled; a compiled-out feature must remain unsupported and absent from capabilities. Add special cases in `vcp_get/set` before generic row dispatch; the generic enum path casts incoming values to uint8_t and cannot carry this codec. Use the existing `set_put` path for application and persistence. Ignore unsupported values without changing the active gamma: 0078, A000, relative-mode requests, RGB-only requests and reserved operations. Bypass may canonicalize readback to 0005 regardless of the ignored SH. Do not clamp unsupported requests to a nearby curve.

Choose non-continuous Get maximum bytes deliberately (a neutral unused value, not a fabricated continuous gamma range); verify complete current/max response bytes against ddcutil during implementation. This response detail remains an implementation validation item, not a reason to change the supported settings.

The Philips document lists decoded gamma enum values but does not by itself prove the serialized Set word for every app path. Confirm the shim trace's **03 72 78 00** before saying Philips hardware was tested. The Lenovo model report independently documents that high-byte usage.

## Input and automatic search

The normal path is `registry.tsv input options -> set_vcp_opt -> vcp_get -> AwtoDdcRegGet`. Each mapped value is below 256 and the wire handler serializes the full 16-bit word, so SH is already zero. The non-registry fallback also maps live input to 0F/11/12 and serializes zero SH. The offline check exercises the real registry adapter and table, with a mock settings backend.

Current Set behavior truncates enum input to the low byte. Thus 2111 selects HDMI1 just like 0011; it does **not** configure a second window. Preserve that existing behavior for compatibility, document the ignored high byte, and advertise only `60(0F 11 12)`. A future decision to reject nonzero high bytes would itself change the interface. The input row is refreshed from live source state each settings-loop pass, rather than synchronously proving a completed switch.

Search is separate:

- EF=0 asks the source scanner to search automatically in the group; EF=1 fixes the current input.
- An accepted 60 selection requests fixed input, follows existing cable/port-enable policy, and uses the fast switch path. A cable-less target may be refused by the input layer; DDC Set has no result reply. Verify actual input after settling.
- EF is volatile and defaults to Auto on boot. Input switches do not add flash writes.
- **Readback gap:** the dead-port recovery path directly changes the scanner to Auto. The settings integration tracks the active input but does not track live scan type back into input_mode. EF can therefore still report Fixed after runtime recovery. Small worthwhile fix: synchronize input_mode from the runtime scan type using `set_track`, or read the live type through the getter. Preserve EF's meanings, default and volatility.
- Do not infer a search order from FC: it is inert. Port enables EC/ED/EE control actual HPD/EDID/receiver/search participation and retain their safeguards.
- Philips ED has no proven on/off numeric encoding in the current analysis and is not advertised by the reference 288E2. Do not label it a standard search code or send it to AWTO.

## Stock Realtek and original Dahua

“Stock Realtek” here means the unmodified RTD2014 demonstration user layer in the publicly mirrored SDK at 3d38340e, **not all Realtek-based monitors**. The current AWTO copy has had its SDK DDC handler stripped, so the upstream file was inspected directly rather than treating the local stub as a reference.

| Area | Original SDK demonstration | Original JXC/Dahua evidence |
|---|---|---|
| 60 Get | Maximum 0003; current comes from source-type helper, with no sub-input packing | Historical probe reports unreliable reads. Exact byte encoding not established |
| 60 Set | Low-byte 01/03/04/0F/10/11/12 dispatch; sets fixed scan and restarts search on chosen input | Existing source-selector RE describes OSD actions, not proof of the DDC Set path |
| Gamma | Header defines code 72, but RTD2014 Get/Set handler has **no gamma case**; RL6449 capabilities omit 72 | No verified gamma VCP mapping or pacing result found in reviewed notes |
| Presets 14 | 08/06/05/04/01/0B map to 9300/7500/6500/5800/sRGB/User. 02 is in table/caps but Set's Off branch is commented out | 14 and RGB respond; exact preset coefficients/transition policy not established by old DDC notes |
| RGB | Reports a 0..100 scale. Outside User, it loads/edits/saves User then restores the original active preset; Get also reads the saved User slot | Recorded as answering, not a verified automatic-User policy |
| Auto input | No Philips ED or separate portable auto-search VCP in the inspected handler. 1E is auto image setup | OSD RE suggests scan-type storage but explicitly marks interpretation unresolved |
| Capabilities | Static strings by interface/project; generic inputs and preset entries can overstate actual board behavior | Recorded original caps advertise only vcp(02), despite several other answering controls |
| Pacing | No 110 ms rejection/sleep gate found in inspected RTD2014 and common dispatch code. This is not a throughput guarantee | 0.1..0.2 s host calls were observed; process timing does not establish a minimum firmware acceptance interval |

Sources R and D. Do not “restore stock” quirks as a compatibility objective: the demo's advertised-but-ineffective entries and saved-User RGB behavior are precisely the kinds of ambiguity AWTO should avoid. No original monitor was written or reprobed during this review.

## LG, HP, Dell and Lenovo comparisons

| Vendor / exact example | Observed convention | Implication for AWTO |
|---|---|---|
| **LG 27UD58**, DisplayPort RE report | Private **FE gamma**: 1/2/3/4 = Gamma0/1/2/Off; picture modes at 15. The report does not establish numeric exponents or reliable input switching | Do not equate LG “Gamma1” to a calibrated exponent or reuse FE, already AWTO aspect. [L1] |
| **LG 38WR85QC-W** and other model reports | Reported F4 input switch with alternate **DDC source byte 50**, e.g. 00D0 DP; model results vary | Host quirk only, never firmware-wide. 50 here is the packet source byte, **not a different monitor slave address or the EDID destination**. [L2] |
| **LG EP950**, manufacturer guide | Documents OSD-lock customization using decimal opcode **177 (B1)** | An official example that OEM controls extend beyond shared MCCS functions; no need to copy its private interface. [L3] |
| **HP X24c**, firsthand ddcutil capture | Advertises 60(0F 11); reads HDMI1=11; RGB maximum 255; 72 unsupported; DC responds; nested capability entries trigger parser errors | AWTO's RGB 255 range is not inherently nonstandard. A gamma OSD does not imply a working 72. [H1] |
| **HP Display Manager**, official documentation | Uses DDC/CI or USB, includes explicit VCP-code/value sending. HP also published a sub-VCP extension design | These do not establish a universal HP gamma or auto-input opcode. Leave unverified HP private controls unknown. [H2,H3] |
| **Dell U3818DW**, firsthand report | Input60: DP0F, HDMI11/12, USB-C1B | Standard input selection plus model extensions; do not advertise USB-C on AWTO hardware. [DE1] |
| **Dell Display Manager**, official CLI documentation | Provides active-input and raw ReadControl/WriteControl operations | Useful host pattern; it does not prove Philips ED or a uniform Dell gamma map. [DE2] |
| **Lenovo Legion R45w-30**, product 67B1 / reported C9=0101 | Reported 72 gamma in SH; 60 low/high selects left/right; USB-C 31; RGB edits select User. Private F2 swaps windows, EC charging, ED KVM status, EF HDR | Strong model-specific support for the proposed gamma codec and #371 policy; a direct warning against copying another vendor's E/F meanings. Its capability mismatches reinforce truthful discovery. [LE] |

These are external documented observations, not tests performed on those monitors in this task. No verified universal automatic-input-search code or common 110 ms requirement was established across these brands.

- L1: [Original LG 27UD58 investigation and subsequent qualifications](https://github.com/ddccontrol/ddccontrol-db/issues/80).
- L2: [ddcutil LG model reports, discussion #331](https://github.com/rockowitz/ddcutil/discussions/331).
- L3: [LG EP950 manufacturer guide](https://gscs-b2c.lge.com/open/downloadFile?fileId=RdyKDSyRMhPCWHmWW4Ck4g), p.15.
- H1: [HP X24c firsthand capture](https://sleeplessbeastie.eu/2022/10/31/how-to-manage-monitor-using-ddc-ci-protocol/).
- H2: [HP Display Manager](https://support.hp.com/au-en/document/ish_3624865-3636931-16). Search-indexed manufacturer text was available; direct retrieval returned403.
- H3: [HP Inc: Extending Custom Virtual Control Panel Commands](https://www.tdcommons.org/dpubs_series/5619/). This is a design disclosure, not evidence of deployment on a particular HP monitor.
- DE1: [Dell U3818DW input capture](https://github.com/rockowitz/ddcutil/issues/70).
- DE2: [Dell CLI documentation](https://www.dell.com/support/kbdoc/es-ec/000060112/que-es-dell-display-manager). Search-indexed manufacturer text available; direct retrieval returned404.
- LE: [Lenovo R45w-30 author's measured register map](https://github.com/andres-valencia/ddc-toolkit/blob/main/REGISTERS.md).

## Capabilities and host-tool changes

The current generator advertises every row with a direct VCP code, without testing SF_INERT. It therefore advertises **87 sharpness, F7 L1 delay, FB L3 delay, FC search order** as usable. Remove those four from generated discovery after approval; keep their direct legacy Get/Set/storage and paged IDs intact, explicitly labeled “stored only / not active” in AWTO host tools. Capability filtering is not removal of old explicit access. Hosts that already know the codes can retain their configuration storage behavior; hosts that discover controls will stop offering inert adjustments.

Also filter retired EB options1..4 out of advertised choices without reassigning their values. Preserve their existing no-op interpretation. Keep unimplemented DC and all absent PIP codes out. Preserve F2 discovery for old clients; host UI may deduplicate it with72 only when the AWTO model/schema confirms the relationship. Add E3 to the supported command list to describe capabilities replies already emitted, while keeping existing cmds and version.

Generate the new 72 descriptor explicitly; generic enum generation is insufficient. Regenerate set_table.c, the host settings table and docs together. Preserve SET_SCHEMA and NVRAM IDs/ranges unless there is a real storage change; an adapter/discovery change alone does not require resetting settings.

Small host work:

1. Add a gamma serializer/decoder for AWTO 72 that preserves both bytes; fall back to F2 only for confirmed AWTO firmware lacking 72. Existing named settings commands may continue using the registry row unchanged.
2. In DDC output parsing, preserve raw current/max bytes for complex controls. `ddc_ctl.py` already parses CNC/NC as 16-bit; SNC intentionally only returns SL. Main-input display is fine that way, but a Philips/Lenovo PBP tool needs a separate full-word read route, not a silent change to all SNC output.
3. Profiles must match exact manufacturer/model and, where needed, firmware/schema. Unidentified monitors get standard controls only; no private-code guessing. Different LG models can share identifiers, so allow an explicit override rather than promising EDID alone proves a profile.
4. Apply TPV pacing in its host write scheduler: at least 110 ms, preferably 120 ms margin, serialized per monitor and shared across CLI/GUI writers. Count all relevant outgoing DDC requests/transactions, including Get request writes if the device needs that, rather than pacing only user Set calls. Keep an explicit override. The analysis combines app sleeps and prior TPV reports; it does not establish a measured exact 288E2 threshold.
5. Prefer host/device-specific pacing to firmware rejection. Current cac1c66f already drops rapid Set VCP requests; this differs from the initial ce8e1625 baseline and from this recommendation. Document it for clients now and track a separate follow-up to remove/reconcile it, rather than quietly changing the merged behavior in a documentation update. No unconditional 110 ms firmware sleep is proposed.
6. Do not report a successful process exit or I2C ACK as proof a setting changed. Use suitable Get verification for gamma/search and compare normalized power states. Existing `--noverify` for power should not suppress useful verification for unrelated features.

No new daemon, broad code relocation or Philips identity emulation is needed.

## Deferred features and parser boundary

Do not implement SmartImage/DC, PIP/PBP A5/geometry/F6/F7, EC size/location, ED auto-search alias, E9 resolution notifier, Philips F2 power LED, unknown E/F controls or TPV update/factory commands.

[#385](https://github.com/awto-au/awto-ddc/issues/385) is now partially implemented at cac1c66f: FE E1 prefix requests bypass generic FE aspect Get and return up to ten ASCII build-tag characters. The initial ce8e1625 review found generic FE misparsing; that specific prefix no longer falls through. Current dispatch tests only the prefix and a minimum length, not the complete E6/06/00 selector. The reference 32-byte response and real SmartControl acceptance of the short reply remain separate interoperability questions. Require exact-selector/length, checksum, truncation, normal FE preservation and real-client regressions before claiming complete compatibility. No additional factory or update command is proposed here.

## Simulator regression cases for the approved implementation

These cases should extend `scripts/ddc_sim.py` and the RGB/NVRAM simulator, not replace firmware execution with a Python reimplementation of VCP logic.

| ID | Stimulus / precondition | Expected result |
|---|---|---|
| I1 | Get 60 with each live port after key/test/auto-search selection | Current 000F/0011/0012, SH 00, no extra advertised inputs |
| I2 | Set 60 to each supported code, repeated with nonzero SH | Existing low-byte compatibility retained; no sub-window state invented |
| I3 | Unsupported low-byte input, no-cable target, disabled target | Existing no-change/cable refusal/enable safeguards preserved; verify actual selected input after settling |
| I4 | Set 60 then query EF | Fixed 1 after accepted selection; no input-selection flash write |
| S1 | Set EF 0/1, then trigger no-cable recovery from Fixed | Scanner and EF readback agree after loop service; Auto after recovery |
| S2 | Reboot after EF 1 and input switches | Boot Auto, existing stored selector/port enables preserved |
| S3 | Write ED 0/1 while observing scan and port state | Only D2-enable semantics, existing refusal safeguards; never an auto-search alias |
| G1 | Write 72=5000/6400/7800/8C00 | Correct row 1..4, correct Get 72 and legacy F2; expected LUT/stage registers applied |
| G2 | Write F2=0..4 and read 72 | Same underlying row; bypass 0005; no duplicate state |
| G3 | Write 72=0005 and FF05 | Gamma stage disabled, read canonical 0005; F2 remains 0 |
| G4 | Write 72=0078, A000, channel-only/relative/reserved forms | Unchanged gamma and LUT, no new dirty/save; requests not clamped or truncated |
| G5 | Compare both alias paths across Save and fresh simulator boot | Existing SDK store restores same gamma row; no schema/default changes |
| C1 | Read full capabilities in 10-byte chunks, EOF and out-of-range offsets | Balanced/complete string, correct offsets/checksum; 72 structured descriptor; no 87/F7/FB/FC/DC/PIP/retired EB options |
| C2 | Explicit legacy access to 87/F7/FB/FC and E0/E1 paging | Previous stored/readback behavior retained; AWTO UI labels inactive |
| R1 | #371 RGB edge sweep from every preset, including equal-value writes | User selected per approved #371 policy; other active channels preserved; gamma aliases do not restore stale User flash |
| R2 | RGB edit -> gamma change -> preset/User -> save/reboot | User triple and selected mode persist per #371 policy; no implicit reset |
| T1 | Bad checksum, unknown code, malformed/extended frame | Existing checksum rejection and unknown result 1; document current FE misparse until separate hardening is approved |
| T2 | Normal fast and spaced traffic, interleaved simulator engines | Current cac1c66f rapid Set drop behavior must be covered; desired host-paced behavior needs a separate approved implementation change and corresponding acceptance tests |
| H1 | Mock host clock for TPV scheduler; two writers, failures, cancellation | Correct per-unit serialization and >= 110 ms relevant transaction gap; AWTO path unaffected |
| H2 | Host parse gamma/current/max, SNC main input and raw two-window input | No byte loss; model-specific decoding; power 4/1 normalization respected |
| H3 | Capability cache/profile with old AWTO, new AWTO, Philips, LG, Lenovo, unknown | F2 fallback only on AWTO; no cross-vendor private write; unsupported/inert controls never offered as functional |

Some invalid-frame and extended-command assertions need a separate hardening patch because present behavior is permissive. Do not mark their desired behavior passing against this baseline.

## Validation performed in this review

**1,580 host checks passed, zero failures at ce8e1625**, compiling the actual unchanged `vcp.c` and generated `set_table.c` using GCC. Only settings value storage/application and the menu were mocked. Checked input values and every high byte, preset mappings, legacy gamma mappings, unsupported 72/DC, EC/ED/EE/EF assignments, and the four inert direct rows. The [original output](reviews/ddcci-388/baseline-results.txt) and [reusable harness](reviews/ddcci-388/README.md) are preserved with this review. These results have not been rerun against the newer wire handler.

This is **not a full-image simulator run**: it does not establish I2C/FIFO timing, LUT writes, hardware input switching, SDK persistence, or optical gamma. The cases above remain the required implementation regressions. Existing `settings_sim.py` explicitly calls its old NVRAM round-trip model stale; use the current SDK-store/RGB simulator rather than accepting its XFAIL as persistence evidence.

Initial source reading verified both 60 reply paths, identified stale EF readback, checked the original SDK versus its stripped AWTO copy, and inspected the prior RGB package. The publication refresh checked the current merged changes and existing #371 archive. No production patch was made in this review/publication.

## Approved follow-up scope

Dan approved the following small implementation on 28 November 2026. This document records the work; it does not claim that it is implemented:

- MCCS 72 adapter with the codec above and unchanged F2 alias/storage.
- Truthful capability filtering for 87/F7/FB/FC and retired EB options, plus the structured 72 entry and E3 command declaration.
- Live EF search-state readback synchronization.
- Focused host codecs/profile/pacing/verification work and the simulator cases above.

Keep 60's current encoding and high-byte-ignore behavior, preserve all existing AWTO vendor meanings, and leave DC/PIP/TPV factory/firmware-string work outside this first change. Coordinate the implementation with #371's existing patch. Approval to implement does not authorize merging or flashing. Reconcile the already-merged pacing/firmware-string work before preparing the follow-up patch.

