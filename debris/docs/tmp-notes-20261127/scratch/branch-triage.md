# Local branches not merged to origin/main (37), triage 2026-11-24

Columns: ahead = `git rev-list --count origin/main..b`; uniq = `git cherry origin/main b | grep -c '^+'` (patch-id; rebased copies show as unique, so "on main" is proven by subject match plus content/issue state).
WT = worktree path (all under /mnt/2tb/git). P = deliberately parked earlier (flagged, judged on merits).

## MERGE / FINISH (6)

| Branch | Verdict | Tip | Ahead/uniq | Last | Issue | WT | What remains / unique worth keeping |
|---|---|---|---|---|---|---|---|
| ports2 (P, other session) | MERGE after rebase | df9132e5 EDID D3 = D2 + 3 patch pairs | 2/2 | 2026-11-24 | #317, #325 (open, needs-test) | awto-ddc-ports2 (clean) | 29 behind; conflicts: fw/msgids.tsv, fw/warn_policy.tsv, scripts/prefill_sim.py. Needs hardware test (label needs-test). Owned by the other session: do not touch. |
| worktree-agent-a454eddedbbdb8f9f | FINISH (small) | 031a15a7 merge main; real change 87d470f7 conwrap | 2/1 | 2026-11-19 | none (gates-report.md conwrap row asks for it) | none | New fw/osd/conwrap.c (pure break decision), scripts/con_wrap_host.py host gate 0.05 s, tests/test_con_wrap_host.py; none of it on main. Rebase onto main (conflicts: fw/osd/console.c, scripts/fw_gates.py), drop the merge commit, run gate. |
| worktree-agent-a59458149d64f70be | FINISH (small) | 98766c1c OT-8 24x36 cell mode HWTEST op | 1/1 | 2026-11-19 | OT-8 in docs/osd/open-items.md (no issue found; #226 is the OSD umbrella) | none | Test-only: AwtoOhwBig, osd_hw_test ot8/ot8off/ot8full, spec in docs/osd-hw-tests.md. Rebase (conflicts: fw/test/testcmd.c, docs/delay-audit.tsv); hardware run needed to close OT-8. |
| tmds-phy-ex0 (P) | FINISH | 1be36e6c production AWTO_PHY_DELAY opens EX0 | 4/4 | 2026-11-21 | #256 (open) | awto-ddc-tmdsphy (clean) | 176 behind, 11 conflict lines. Production variant: EX0 open only in pure delays, unstable IRQ before set-up, EXINT0/AUX served counters. Not on hardware-gated main; main has the budget study 891c953b (#329 go/no-go for stage 3) which should decide whether this lands. |
| tmds-ex0-shared (P) | FINISH or fold into tmds-phy-ex0 | 16485279 unstable-hit flag EC 0x92 | 6/6 | 2026-11-21 | #256 | awto-ddc-ex0 (clean) | WIP (c2c83529 "not built or gated"): EX0 on the shared Rx2/Rx3 body. Not a descendant of tmds-phy-ex0: two competing designs. Keep tooling (scripts/aux_traffic.py, phy_probe_runs kinds 8/9, EC 0x92/0x93 rows) even if the design is dropped; pick one design, delete the other. |
| hdcp-s2-bank14 (P) | FINISH (keep as the single HDCP stage-2 branch) | 47247a8e resid_end 0xa00 experiment | 4/2 | 2026-11-23 | #44 (open, p3, needs-dan, needs-test) | awto-ddc-s2b14 (dirty: fw/bank_layout.tsv) | Unique: 1c2982f6 WIP stage 2 (HDCP 2.2 sources restored, no RAM key copy, per-function pData_EXINT, ISR-private key readers; does not build) and 47247a8e (links through placement, fails on XDATA). Other 2 commits are on main (66685e3b, ce2cf4e2). Remaining: fix XDATA overflow, make it build, test on unit 3. Low priority per #44: park via issue comment, then branch can stay as the one ref. |

## DELETE (31)

Proof key: SUBJ = identical commit subject on origin/main (rebased/squashed copy); ISSUE = issue closed; SUPER = superseded by named main commit.

| Branch | Tip | Ahead/uniq | Last | Issue | WT | Proof / anything unique |
|---|---|---|---|---|---|---|
| audio-merged | 8699ea14 | 1/1 | 11-19 | #229 closed | .claude/worktrees/agent-a180e6df7cd96ca02 | SUBJ 316327d4. Nothing unique. |
| pacman-sound | a2a607fd | 1/1 | 11-17 | prototype | .claude/worktrees/agent-a794515b82709c327 | SUBJ c8351f97. |
| ddr-draw-267 | 7234e7d2 | 18/2 | 11-19 | #267 open | none | All 17 non-merge commits SUBJ on main (8e648240 ..., 02d10940). The 2 cherry hits are rebased copies. |
| freeze-port-255 | 6c8b7fca | 13/3 | 11-19 | #255 open | .claude/worktrees/agent-a861850b11d091757 (dirty: bank_layout.tsv, generated) | 12 of 13 SUBJ on main. Last commit raises ddr_freeze_test HOLD_MAX_S 600 -> 3600 for a one-off hold approval; main keeps 600 s (right default). |
| worktree-agent-a861850b11d091757 | 028d5345 | 3/2 | 11-19 | #255 | none | host_pattern.py and ddr_frame_test.py both on main, evolved further; 232-file diff is a stale merge base. |
| tmds-isr-diet | 6a45c6fa | 2/2 | 11-19 | #256 | none | SUBJ 21839537, 75b253b8. |
| dp-design | 9bee64fa | 1/0 | 11-23 | #318 | none | cherry 0; SUBJ 63aa4b38. |
| dp-b | bc8e419f | 2/2 | 11-23 | #326 closed | none | Prototype b of per-port DP Rx1 state; main took accessor design 7ef8410b (#326, one port builds to old scalars). |
| dp-b2 (P, dp-*) | 678e1661 | 4/4 | 11-23 | #326 closed | none | Prototype b2 (scalar names via NAME_P accessors) = what landed as 7ef8410b; dp-b is its ancestor. |
| isr-port (P) | defcf9e3 | 2/2 | 11-23 | #326/#328 closed | none | a70882bc SUBJ 1ca13b6d; defcf9e3 = prototype a (port argument), superseded by 7ef8410b. |
| dp-e (P) | ff9b6de6 | 2/2 | 11-23 | #326 closed | none | scripts/dp_rx_port_cutline.py + docs/dp-rx-port-state.tsv already on main (2fdf1026), main version newer. |
| common-shrink-old | fade3731 | 6/4 | 11-23 | #44 | none (awto-ddc-common is branch common-shrink, merged) | 3 SUBJ on main (8247c7d6, c9a4e415, 87b448ed). Remaining 3 are the `--recompact` tool + test; main has no recompact and replaced it with compact packing every build (f5863264). |
| shrink-hdcp-old (P, shrink-hdcp-*) | 9321cc6e | 6/5 | 11-23 | #44 | none (awto-ddc-shrink is shrink-hdcp, merged) | SUBJ b5eac7a6, f5863264; rest = recompact, superseded as above. 9321cc6e (sim/gate tools read image's own bank_layout.tsv) is the only item not matched: check main's gate tools before deleting if worried. |
| shrink-hdcp-stage2 (P) | dd857a7b | 2/2 | 11-23 | #44 | none | Same WIP stage-2 commit as hdcp-s2-bank14 (1c2982f6) plus recompact; keep only hdcp-s2-bank14. |
| hdcp-on-stage2 (P, hdcp-*) | 3f255c8c | 2/2 | 11-23 | #44 | none (awto-ddc-hdcp is hdcp-on, merged) | Same WIP stage-2 commit again; 27476dfc "_AWTO_HDCP defaults _ON" was reverted on main (a74fefa5). |
| wb-biglogo | 95a43d21 | 1/1 | 11-07 | #63 closed | none | SUBJ a0dfcb51. |
| wb-delaycal | 1e99c0f8 | 1/1 | 11-07 | | none | SUBJ f023f711. |
| wb-delaycal-v2 | 02a8c1d3 | 2/2 | 11-07 | | none | 19b73c7c SUBJ f023f711; 02a8c1d3 = bank_layout.tsv of a test image only. |
| wb-dp | 0fd787d9 | 1/1 | 11-07 | | none | SUBJ 5140d40b. |
| wb-p14ui-dead | 494e7b8d | 1/0 | 11-12 | #84 closed | none | cherry 0; SUBJ c957d473. |
| wb-ddrinit | 088a07db | 1/1 | 11-07 | #26 closed | none | One-off DELAY_XUS(500) hypothesis test for the DRAM init; #26 closed, not on main. Idea only, no value kept. |
| wb-p14ui-ddrinit | 8a34f697 | 1/1 | 11-13 | #26 closed | none | Same hypothesis test rebased; delete with wb-ddrinit. |
| wb-p14pf | a04a7f27 | 2/2 | 11-08 | #83 open, #84 closed | none | #83 pre-fill: main has it (kvm_prefill item in nvram-settings.md, scripts/prefill_hw, fastsw); #84 guard = c957d473. docs/history.md names the branch; fix that reference when deleting. |
| wb-p14wk-escape | b2a9aa44 | 1/1 | 11-08 | #78 open | none | "WIP not proven on hardware"; main fw/input/fastsw.c:194 has the cache-based escape. |
| wb-port | a4fd7de7 | 2/1 | 11-07 | | none | bank_layout after merge of wb-mixed-port (merged); 1783 behind. Build snapshot. |
| wb-port-u1 | 2bf6b1a4 | 2/2 | 11-07 | | none | Unit-1 image builds: msg_enable.txt, warn_policy, msgids, bank_layout only. Build artefacts. |
| wb-port-u2 | 650301c4 | 1/1 | 11-07 | | none | Same (u2 image). |
| wb-port13-u1 | 923bc99f | 1/1 | 11-07 | | none | Same. |
| wb-port13-u2 | 4292c79b | 2/2 | 11-07 | | none | Same. |
| wb-edid-u1 | 83f2c14f | 1/1 | 11-07 | #26 closed | none | Same (u1 image, messages off). |
| wip/main-audio-test | 13a482c2 | 1/1 | 11-11 | #94 closed | none | Uncommitted WIP rescued 11-11; audio is permanent on main (#229 316327d4 amp mute, fw/audio). |

Totals: MERGE 1, FINISH 5, DELETE 31 = 37.

## Notes
- No branch was deleted; nothing pushed or written to GitHub.
- Dirty worktrees (not touched): awto-ddc-s2b14, and .claude/worktrees/agent-a861850b11d091757 (bank_layout.tsv, generated), plus others unrelated to unmerged branches (bootmain, delays, gaplog, isrmain, isrtwins-base, live, readbehind, churn-before, agent-a32c, tmp/scratch/qcsim, main checkout).
- Merge-conflict probe (`git merge-tree`) said CONFLICT for every FINISH/MERGE branch; conflicts are small (2 to 11 lines) except none are clean.
- Worktrees on detached HEADs or on merged branches are out of scope here.
