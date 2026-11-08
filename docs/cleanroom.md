# Clean-room process (awto-ddc#65)

Goal: replace every Realtek SDK line our firmware links with code written from specs by people (agents) who never saw the SDK.
Plan, inventory and step list: #65 (scoping comment). Dan's decisions: #65 comments of 2026-11-07.

## Trees
| Tree | Side | Holds |
|---|---|---|
| `/mnt/2tb/git/awto-rtdfw` | clean | `awto/include` (interfaces), `awto/<mod>/` (code), `facts/` (generated). LOCAL git only: no remote, no push until Dan says so |
| awto-ddc (this repo, private) | spec | SDK port, keil2sdcc, overlay, regdb, RE, traces, `specs/`, tooling, `fw/awto/<mod>/rules.py`, the boundary shim |

## Modules (wave A specs/briefs)
| Module | Step | Spec | Source of truth | Status |
|---|---|---|---|---|
| reg (16/32-bit, n-byte, burst engine) | 2 | `specs/reg.md` + `reg.equiv` | facts + reference behaviour | draft, brief ready |
| dataport | 2 | `specs/dataport.md` | facts + reference behaviour | draft, brief ready |
| arith (mul/div) | 2 | `specs/arith.md` + `vectors/arith.tsv` | maths, checked vs reference | draft, brief ready |
| settings registry | 5-7 | `specs/settings.md` | OUR design (not ported): one registry -> menus, VCP, NVRAM, docs | to write |
| factory menu | 5 | `specs/osd-ui.md` | `sdk-ui` facts (vendor image walk); part of our OSD UI | to write |
| OSD UI menus | 5 | `specs/osd-ui.md` | `sdk-ui` facts; assets redrawn | to write |
| gamma LUTs | 8 | `specs/gamma.md` | maths (`derived`); vendor tables only as a check | to write |
| flash part table | 6 | `specs/flashtable.md` | flash datasheets (`derived`) | to write |
| DP PHY CTS | 12 | `specs/dpphycts.md` | public DP spec (`derived`) + facts | to write |
- Plan change (Dan, 2026-11-07): factory menu, gamma LUTs, flash table and DP PHY CTS are KEPT and ported clean-room;
  step 1 is no longer "drops". The wb-drops switches stay as a mechanism only (default = keep). VGA/ADC remnants: still drops.
- Settings registry (Dan, 2026-11-07): ONE table `awto-rtdfw/settings/registry.tsv` (name/type/range/default/unit/NVRAM slot/
  VCP/apply fn/group) generates the OSD pages, DDC/CI VCP map, NVRAM layout + schema version, dev.py settings and
  docs/settings.md. Recovery: boot key combination + VCP 0x04 / debug command -> defaults. Interfaces: `settings.h`,
  `osd.h` (pages), `nvram.h` (settings record).
- Interfaces: `awto/include/{reg,dataport,arith,settings,timer,event,mode,osd,nvram,input}.h`; reg/dataport/arith final for wave B,
  the rest DRAFT (their spec writer proposes changes to the process owner).

## Roles and models
| Role | Model | Reads | Writes |
|---|---|---|---|
| Process owner | Opus (once) | everything | this doc, `awto/include`, `scripts/facts_regs.py`, `specs/names.tsv`, gates |
| Spec writer | Sonnet; Opus for DP RX, HDMI PHY, eDP TX, HDCP, DDR, DPLL fine-tune | SDK, regdb, traces, RE notes | `specs/<mod>.md`, `specs/<mod>.equiv`, `specs/vectors/*` |
| Leak reviewer | Sonnet + `cleanroom_lint.py` | spec, clean diff, lint report | verdict per spec and per merge |
| Implementer | Haiku (leaves), Sonnet (drivers) | its brief + awto-rtdfw only | `awto/<mod>/`, host tests in `tests/host/` |
| Verifier | Haiku (gates), Sonnet (triage) | both sides | results; feedback to the implementer as facts only |
| Integrator | Sonnet, one at a time | both sides | merges, `fw/awto/<mod>/rules.py`, `fw/awto/awto_shim/` |
| Subsystem final review | Opus | both sides | sign-off per subsystem |
- A tainted spec poisons every implementation built from it: discard both, rewrite the spec.
- Interface changes go through the process owner (one owner for `awto/include`).

## Spec format: `specs/<mod>.md`
Template: `specs/SPEC_TEMPLATE.md`. Sections, in order:
1. **Interface**: which `awto/include/*.h` functions, plus semantics per argument and return value.
2. **Register sequences**: tables `step | reg (facts or our name) | mask | value | condition | wait`.
3. **Barriers and commutative groups**: which steps must stay in order; which sets may be reordered.
4. **Timing**: every delay/timeout with its source and provenance tag; minimums are minimums.
5. **Decision tables / state machines**: inputs -> outputs, states, transitions, timeouts.
6. **Data**: tables and constants, each with a provenance tag.
7. **Oracle**: vectors (`specs/vectors/*`), expected bus sequences, `specs/<mod>.equiv` rules, sims and hardware checks.
8. **Implementer task**: files to create, functions required, size/speed budget, host test to write.
9. **Q&A**: implementer questions and spec answers, appended; never removed.
- No pseudo-C, no code blocks of C, no SDK identifiers (function, macro, variable, type, enum names), no copied comments.
- Register names: facts names (`P31_A0_B7`) or our names (`specs/names.tsv` -> `facts/names.h`).
- Describe what the hardware must see and what the caller gets; never how the SDK code is structured.
- Every spec is linted before review: `python3 scripts/cleanroom_lint.py --tree specs` must pass.

## Contamination rules
- **Implementers never open** (any copy, mirror or worktree):
  - the SDK: `/mnt/2tb/git_mirror/**`, any `RTD-Scaler*` tree, GitHub `Kingdomwhisky/*`
  - awto-ddc: `/mnt/2tb/git/awto-ddc*/**` (all worktrees), its GitHub repo, issues and PRs
  - `~/vendors/realtek/**` (also via `/mnt/2tb/vendors/realtek/**`): dumps, Ghidra, tool data, regdb sources
  - the asmlib branch (`worktree-agent-a2e2a42cc8a983a00`, `fw/asmlib/`): written against the Realtek C
  - awto-sdcc trees and issues (Keil/SDK test cases): `/mnt/2tb/git/awto-sdcc*/**`; the compiler binary is fine
  - spec-side session data: `~/.claude/projects/-mnt-2tb-git-awto-ddc*/**`, `/tmp/claude-*/-mnt-2tb-git-awto-ddc*/**`
  - the web (SDK copies are public on GitHub): no WebFetch, WebSearch, playwrong, gh, curl, wget
- **Launch**: a separate headless session in awto-rtdfw with the implementer settings below. Never an Agent-tool subagent of a
  spec-side session: it shares that session's permissions, so nothing blocks a read.
- **Brief** = `specs/BRIEF_TEMPLATE.md` + `specs/<mod>.md` + its vectors, assembled by `scripts/cleanroom_brief.py <mod>`.
  Nothing else crosses: no file paths into awto-ddc, no SDK names, no "look at X".
- **Questions**: implementer stops and writes `QUESTION:` lines in its report; the spec writer answers in the spec Q&A;
  a new brief is issued.
- **Feedback** from verifiers: pass/fail, register address + expected/actual value, timing numbers. Never SDK text or names.
- **Boundary shim rule**:
  - SDK symbols our code needs, and our symbols SDK code calls, are bridged ONLY in `fw/awto/awto_shim/sdk_boundary.c`
    (+ `.h`) in awto-ddc, written by the integrator.
  - Clean code never names an SDK symbol; the shim never enters awto-rtdfw; it shrinks per step and is deleted at step 15.
- **Spec-side people** may read anything, but write specs in their own words; the process owner and spec writers never
  write clean code.

## regdb facts-only rule
- `facts/` is generated by `scripts/facts_regs.py` from `re/regdb/RTD2795T-CG.tsv.gz`; never hand-edited.
- Kept: page, address, port index, bit range, reset, access (R/RW/RW4/W/W1C), wide-value bit range.
- Dropped: every vendor register name, field name and description text. Names are positional
  (`P31_A0`, `P31_A0_B7`, `P31_A0_B6_4` + `_SH`, index `P00_25_I1A`, bytes at one index `_N0.._Nk`).
- Our names: `specs/names.tsv` (our_name, target, our note) -> `facts/names.h`. The generator refuses a name equal to a
  vendor register/field name, a target that is not a fact, and non-UPPER_SNAKE names.
- Regenerate after a names change: `python3 scripts/facts_regs.py`; drift check: `--check`.
- Publishing `facts/` needs Dan's sign-off (#65).

## Provenance tags
Every number in a spec (and its code comment) carries one:
- `derived`: follows from facts, maths, a public standard (HDMI, DP, VESA), or our own design.
- `measured`: our measurement (reference image in fw_sim, trace, scope, hardware unit); cite what, when (date/commit), conditions.
- `vendor-value`: a number taken from the SDK or Realtek tool data with no derivation of ours. Allowed now (Dan, 2026-11-07),
  stays private; each one is replaced by a `measured` value before anything is published. Track them in the spec's Data table.
- `sdk-ui`: a Realtek SDK menu fact: a functional fact about the Realtek SDK menu's user interface (menu tree, items,
  ranges, defaults, key behaviour), observed by running the vendor image (below). Facts only: the vendor's code, fonts, icons and graphics are
  their copyright. Private builds may use the assets; the clean tree redraws them and implements from the spec.
- HDCP 1.4 keys: Realtek's table now; public tree option = keys generated from the public master key (#65 decision).

## Trace equivalence (`scripts/trace_equiv.py`)
- Primary oracle: today's known-good SDK image (our SDCC build); the vendor image is secondary.
- Traces: `scripts/fw_sim_trace.py ours BIN MAP --mode <m>` for the reference and for the mixed build, same mode and source.
- Must match: phase order (boot, search, ds, active); final shadow state per phase (regdb reset as start value);
  barrier order; indexed-port bursts (ordered index/value data writes); action-register write sequences;
  every `delay` rule (>= the spec minimum, in OURS); DS -> ACTIVE time <= reference (+ `--ds-slack-ms`).
- May differ: order within a phase outside barriers, redundant writes, RMW splits, poll counts (reads are not traced),
  W1C registers, port index registers, timer/interrupt SFRs, absolute times.
- Rules per module: `specs/<mod>.equiv` (`barrier`, `action`, `ignore`, `port-final`, `port-autoinc`, `delay`; format in the
  script docstring). The spec's Barriers section and the `.equiv` file say the same thing; the `.equiv` is what runs.

## OSD oracle: vendor walk and side-by-side render
- Vendor walk (spec side): `fw_sim_vendor.py` + `osd_render.py` (osd_model hooks) on the vendor image; a key script visits
  every menu page (incl. factory) -> `tmp/osd/vendor/<page>.png` + JSON state (page, items, selection, values).
  The spec writer derives the menu tree, items, ranges and key behaviour from these (`sdk-ui` facts); this is the
  menu list #65 asked Dan for.
- Gap: key injection into the vendor image (it has no Awto test byte): needs a keypad input model in fw_sim (follow-up issue).
- Check: the same key script on the vendor image and on ours; per page the two PNGs side by side (`tmp/osd/sbs/<page>.png`)
  and the JSON states diffed on menu facts. Pass = same facts at every step; pixels may differ (our assets).

## Hardware unit locks
- `tmp/locks/<serial>`; `scripts/unit_lock.py acquire|release|status`; checked by `rtd_flash_image.py` and `unit_health.py`
  (hardware path only, not `--sim`).
- One work stream per unit. A stream: `export AWTO_UNIT_OWNER=<stream>`, `unit_lock.py acquire <serial> --owner <stream>`,
  run tools, `release`. A tool run without a stream lock takes and drops a per-run lock.
- Held by another live owner -> the tool refuses and names the holder. Dead PID on this host -> stale, cleared and logged.
- Order per change: unit 3 (AWT26110003, flash freely), then 1 and 2. Wave D: one RX/TX stream per unit.

## Merge / integrator flow
1. Spec writer: `specs/<mod>.md` + `.equiv` + vectors; lint the spec; leak reviewer verdict.
2. Process owner (or delegate) issues the brief; implementer works on branch `mod/<mod>` in awto-rtdfw, host tests pass.
3. Verifier (spec side): `cleanroom_lint.py` on the branch; vectors; mixed build; `trace_equiv.py` vs the reference trace;
   `fw_profile` / speed bench; `unit_health.py --sim`. Failures go back as facts.
4. Leak reviewer: diff + lint report + structural notes (`--structural`).
5. Integrator, serial: merge `mod/<mod>` into awto-rtdfw `main`; in awto-ddc add `fw/awto/<mod>/rules.py`
   (WRAPS compile-out under `_AWTO_NEW_<MOD>`, INSERTS/SUBS as needed) and shim entries; build; `fw_gates`;
   flash unit 3 under its lock; health; then units 1 and 2.
6. Subsystem done: Opus final review; tick the step on #65.
- Gap: `fw_build.py` does not compile awto-rtdfw sources yet; the mixed-build hook (sources list per `fw/awto/<mod>/`) is the
  integrator's first task (follow-up issue).
- FunctionLib modules drop out of the link by themselves once our code defines the symbol (`fw_build.py` `select_lib`).
- Last step: SDK-free build gate (`RTD_SDK=/nonexistent`).

## Gates
- `scripts/cleanroom_lint.py [--tree PATH]`: SDK identifiers, 6-token code n-grams, 8-word comment/string n-grams;
  exempt `facts/` (and facts-defined names) and `awto_shim/`; allowlist `specs/lint_allow.tsv` (reviewed hits only, with reason).
- `scripts/cleanroom_audit.py`: implementer transcripts (`~/.claude/projects/*awto-rtdfw*`) for forbidden paths, tools, gh/curl/wget.
- `scripts/cleanroom_brief.py MOD`: assembles a brief; refuses unwritten specs and briefs that fail the lint.
- `scripts/spec_vectors.py`: oracle vectors from the spec maths (`specs/vectors/`).
- `scripts/fw_inventory.py MAP`: what is still SDK, by origin and plan step.

## Implementer session settings
Save as `/mnt/2tb/git/awto-rtdfw/.claude/settings.json` (Dan; agents do not edit settings files). Deny rules beat every
allow and every permission mode, including auto mode.
```json
{
  "permissions": {
    "allow": [
      "Read(//mnt/2tb/git/awto-rtdfw/**)", "Edit(//mnt/2tb/git/awto-rtdfw/**)", "Write(//mnt/2tb/git/awto-rtdfw/**)",
      "Bash(git status)", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git add:*)", "Bash(git commit:*)",
      "Bash(git switch:*)", "Bash(git branch:*)",
      "Bash(/home/dan/opt/awto-sdcc/bin/sdcc:*)", "Bash(gcc:*)", "Bash(make:*)", "Bash(python3 tests/host/:*)"
    ],
    "deny": [
      "Read(//mnt/2tb/git_mirror/**)", "Edit(//mnt/2tb/git_mirror/**)",
      "Read(//mnt/2tb/git/awto-ddc*/**)", "Edit(//mnt/2tb/git/awto-ddc*/**)",
      "Read(//mnt/2tb/git/awto-sdcc*/**)",
      "Read(~/vendors/**)", "Read(//mnt/2tb/vendors/**)",
      "Read(~/.claude/projects/-mnt-2tb-git-awto-ddc*/**)", "Read(//tmp/claude-*/-mnt-2tb-git-awto-ddc*/**)",
      "Read(//mnt/2tb/git_debris/**)", "Read(//mnt/2tb/wastebasket/**)",
      "WebFetch", "WebSearch", "mcp__playwrong", "mcp__codex", "Agent",
      "Bash(gh:*)", "Bash(curl:*)", "Bash(wget:*)", "Bash(git clone:*)", "Bash(git fetch:*)", "Bash(git pull:*)",
      "Bash(git push:*)", "Bash(git remote:*)", "Bash(git worktree:*)", "Bash(git -C:*)", "Bash(git show:*)",
      "Bash(cd:*)", "Bash(cat:*)", "Bash(grep:*)", "Bash(rg:*)", "Bash(find:*)", "Bash(ls:*)", "Bash(head:*)",
      "Bash(tail:*)", "Bash(less:*)", "Bash(strings:*)", "Bash(python3 -c:*)", "Bash(python3 /:*)"
    ]
  }
}
```
- Bash rules match command prefixes only: a compound command can slip past. Backstops: the transcript audit and running
  headless with only the allow list (`claude -p` cannot approve anything else).
- Launch (spec side assembles the brief; the session starts in the clean tree):
  `python3 /mnt/2tb/git/awto-ddc/scripts/cleanroom_brief.py <mod> > /mnt/2tb/git/awto-rtdfw/.brief-<mod>.md`, then in
  `/mnt/2tb/git/awto-rtdfw`: `claude -p --model haiku "Read .brief-<mod>.md and do the task in it."`
  (`.brief-*.md` is gitignored in awto-rtdfw).
