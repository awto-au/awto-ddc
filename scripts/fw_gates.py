#!/usr/bin/env python3
"""Offline gates for one firmware image (sims in parallel): boot-check, isr-check, link check, health --sim 1080p60 + 2160p60,
menu, ddc, keys, crash, wdt, sync, bootsim, wake, panel, delays, sysm, pokes, htime, magic, regs, regmap, nvlog, monitor.

usage: fw_gates.py IMAGE_STEM [--tier normal|extensive] [--build-inputs] [--tree WORKTREE] [--speed LABEL] [--only boot,isr,link,h1080,h2160,menu,ddc,keys,crash,wdt,sync,bootsim,wake,pokes,htime,magic,regs]
  menu, ddc: only for images with the settings registry (#67): menu_cli walk + ddc_sim (MCCS) in fw_sim.
  keys: key_sim_test (#129). crash: crash_sim_test --header TREE/... (#131, #138). wdt: wdt_test --sim, all cases.
  htime: host_time_sim (#157: DDC/CI host time, console title row, ring lines).
  conmode: console_mode_sim (#218: console Off / Until signal closes 3 s after ACTIVE or on a key / Always).
  conkeep: con_keep_sim (awto-ddc log-keep: console close / reopen / new episode / flood keep the ring lines on screen; a watchdog reset keeps the previous boot's lines).
  conwrap: con_wrap_sim (#162: console lines whole, a wide line on two rows; widest lines + map end, no watchdog bite).
  condelta (extensive): con_delta_sim (console real time + delta from 32-bit ms, red episode starts, joined rows; a 131 s gap after a host sync).
  nvlog: nv_test --sim flushlog (#151: NVRAM flush line per close / power off, "wrote N B ..." vs "nothing changed").
  sync: sync_sim (#139). bootsim: boot_sim (#144, #29, #216: Until signal = console after the picture; bootsim_always: console at power-on; `boot` is the fw_sim --boot-check). wake: wake_sim (#144 task 4). pokes: poke_loops TREE (static, #138).
  panel: panel_sim (#162 step 2): panel VDD / backlight pin / PWM / DPTx link only from the panel machine; no blink; backlight
    pin at eDP stream on, >= backlight_on_delay after VDD on (Dan 2026-11-27); T4..T6 kept.
  osdfit: osd_fit.py --check (static: fw/osd/osd_fit.tsv worst-case rows vs their box; also a build step). osdfitsim (extensive):
    osd_fit_sim.py, every card_shot shot at 1080p60 + 2160p60, no firmware fit-guard line (ED 7E). infocard: info_card_sim.py
    (the info card after boot stays _AWTO_INFO_POPUP_SEC, one open + one timeout close line).
  sysm: sysm_sim (#162 step 3): power status / mode state only from the system machine; transition chain + request lines; --tree lint.
  delays: delay_sim.py (docs/delay-audit.md): panel_sim scenario at the image's clock (+ the sibling `<stem>-clk87` image of `-D AWTO_CLOCK_MHZ=87` when built): class A waits vs
    wall ms, Timer2 / wall = 1, every executed DELAY_5US / DELAY_XUS loop >= nominal, loop counts = AWTO_DELAY_CNT, DDC debounce wall time equal at both clocks; --audit:
    delay_audit.py --check (every linked delay site is in docs/delay-audit.tsv, no FIX / UNKNOWN row).
  flashclk: flash_clk_sim.py (FF6C read tune / FFE9 F2 order at boot, flash write sessions F2 5 and back, only proven (F2, tune) pairs on the M2PLL).
  rxports: dp_rx_port_cutline.py --check (#326: Rx1 globals classified in docs/dp-rx-port-state.tsv, link-training state through NAME_P accessors).
  magic: magic_lint.py TREE (#161: no raw register address / palette value in our code; allow-list scripts/magic_allow.tsv).
  regs: gen_regnames.py --check (AwtoRegs.h matches the names our code uses).
  regmap: regmap_build.py --check (re/regmap register knowledge base current, hand columns valid; ~4 s; re/regmap/README.md).
  IMAGE_STEM = tmp/fw/<tag> (.bin + .map beside it). link: 0 findings (#66, no baseline).
  --speed LABEL: also append a speed_bench row (docs/speed-bench.tsv) for the image.
  Each gate's output -> tmp/logs/fw_gates/<stem>.<gate>.log; one PASS/FAIL/SKIP line per gate; exit 1 if any fails.
SKIP (counted, printed): the image lacks the feature (SKIP_IF_MISSING: map symbols), or the gate needs a tree (--tree, default this repo) without the file.
  wdt cases the image does not implement report SKIP inside wdt_test; they are counted in the gate's note.
Tiers: normal (default) skips the EXTENSIVE gates (table in this file); --tier extensive runs all. Record: tier + complete.
  A complete normal record is what `dev.py flash` needs; `dev.py merge-check` (merge to main) needs tier extensive.
Record: tmp/fw/<stem>.gates.json = image SHA-256, date, tier, per-gate result + seconds, fw_gates git commit, complete (no --only), red (FAIL gates), new_red (red now, not in the previous
  complete record of the tier; logged as NEW RED).
  `dev.py flash` refuses an image without a record whose SHA-256 matches, complete, and with no FAIL (--force-ungated overrides).
Stall guard (awto-dan#53): waits for a gate's next output line or CPU progress of its process tree; expected: output at least
  every few s, 3x margin at 60 s (STALL_S). A gate with neither for STALL_S is hung: killed. Backstop LIMIT_S per gate (3x the cold
  run) times the load factor (1 + 1-min loadavg / cores, 1..LOAD_CAP) since a starved gate is slow, not hung. A guard kill is rerun
  once (second log `<gate>.rerun.log`, both runs in fw_gates.log); two kills = FAIL. Every kill logs gate, reason, elapsed,
  last line, loadavg, CPU seconds. Logic: guard_verdict(), tests/test_fw_gates_guard.py.
Log: ./tmp/logs/fw_gates.log
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

import image_variant as IV
import isostamp

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root

ROOT = repo_root()
STALL_S = 60          # no output line and no CPU progress for 60 s = hung (awto-dan#53)
LOAD_CAP = 4.0        # backstop limit scales with load / cores up to 4x: the box has been seen at load 45 on 28 cores = 1.6x
LIMIT_OF = {"keys": 150, "deadport": 80, "wdt": 60, "rules": 30, "delays": 150, "inputrate": 90, "canary": 90, "monitor": 90}   # 3x the cold run (keys 50 s in a full gate run with the #132 switch cases 2026-11-12, wdt 18 s; fast core); table of all gates: commit message
LIMIT_S = 30          # 3x the cold run of the rest (all <= 9 s), 30 s = interpreter start + a loaded box; `speed` is the exception
SPEED_LIMIT_S = 900   # speed_bench: not measured
PY = [sys.executable, "-u"]
# Tiers (Dan 2026-11-19): normal = every build / flash (a complete normal record is the flash gate); extensive = normal + these long
# scenario sweeps (on request, before a merge to main, nightly). A gate not listed here is normal. Move a gate by editing this set.
WDT_NORMAL_CASES = "stall,pass,reason,t0_timing"
EXTENSIVE = {
    "menu_full": "16 pages, all 133 entries, a PNG per page (normal: every page, one entry per class)",
    "keys_full": "80 checks, ~250 simulated s of OSD timeouts and holds (normal: the selector section)",
    "deadport": "4 cases, up to 40 simulated s each",
    "inputrate": "40 start phases x 3 rows",
    "monitor_full": "heartbeat (30 samples) at period / 10 (normal: --no-beat, same scale)",
    "monitor_real": "production period, 300 simulated s",
    "wdt_full": "21 watchdog cases (normal: stall, pass, reason, t0_timing)",
    "wake_full": "all wake paths incl. UP+DOWN, DPCD, TMDS clock, burst (normal: --quick)",
    "crash_full": "workload / stall / hw / probe (normal: stall)",
    "conwrap_full": "real power off / on / saving / wake phases 1-5 (normal: injected lines)",
    "canary": "stack canary, long boot + fatal path",
    "delays_sim": "panel scenario at the image's clock: class A waits, Timer2 / wall, DELAY loops, loop counts (~10 s CPU)",
    "delays_full": "both clocks (350 + the sibling -clk87 image); clock matrix: scripts/gate_matrix.py",
    "bootsim_always": "second boot_sim variant (console at power-on)",
    # Dan 2026-11-19: a normal gate is ~1 s, a few s at most. These cost 9-20 s CPU even as minimal variants (measured 2026-11-19):
    # their quick variants (keys --only switch, monitor --no-beat, wake --quick, crash --tests stall, conwrap --scope inject) run
    # with --only and in the extensive tier only until a test-timing scale cuts their simulated seconds.
    "keys": "quick variant, ~20 s CPU (OSD-timeout / hold simulated seconds)",
    "wake": "quick variant, ~9 s CPU",
    "crash": "stall variant, ~10 s CPU",
    "conwrap": "inject variant, ~9 s CPU (boot + NVRAM flush wait + console redraws)",
    "condelta": "~6 s CPU (boot, wake, host sync + 131 s clock jump: console real time / delta / joined rows vs sync_log.con_rows)",
    "conmode": "~9 s CPU (3 s console timers x 3 modes)",
    "conkeep": "~6 s CPU (marks in the ring: console close / reopen keeps them, flood, watchdog reset keeps the previous boot)",
    "sysm": "~10 s CPU (power / mode machine chain)",
    "sync": "~11 s CPU (sync-log sim boots)",
    "dramlog": "~40 s CPU (DRAM log image: boot, two 34000-line fills = wrap + stamps above 65 s, watchdog reset keeps the history)",
    "osdfitsim": "~21 s CPU (23 OSD shots x 2 timings, fit guard watched; the static half osdfit is normal)",
}
SIM_CPU = os.environ.get("AWTO_SIM_CPU", "dw8051")   # fast-core CPU model of the sims (#162 step 1); results are comparable only at the same model
CPU_OF = {}      # per-gate CPU model override; wdt runs on dw8051 since the Timer0 cases use wall ms (the 8052 model has no clock: the 350.8 MHz boot never reaches stage 8 in wdt_test)
NO_SIM = {"link", "xlayout", "pokes", "speed", "magic", "regs", "regmap", "rules", "edid", "conhost", "osdfit"}   # every other gate runs a sim on the in-process DW8051 core (fw_sim default; ucsim is a cross-check only)
SKIP_IF_MISSING = {      # gate -> map symbols the image must define, else SKIP (the script would FAIL on an older image)
    "keys": ("_AwtoSourceOpen",),
    "crash": ("_AwtoWdtHang",),
    "wdt": ("_AwtoWdtHang",),
    "sync": ("_g_stAwtoSync",),
    "bootsim": ("_g_stAwtoSync",),
    "bootsim_always": ("_g_stAwtoSync",),
    "wake": ("_AwtoPsWakeFire",),
    "htime": ("_g_stAwtoHt",),
    "conmode": ("_g_ucAwtoConAuto",),
    "conwrap": ("_AwtoConWrapLine",),
    "condelta": ("_g_stAwtoHt", "_AwtoConWrapLine"),
    "conkeep": ("_g_stAwtoSync", "_AwtoConWrapLine"),
    "deadport": ("_AwtoDeadPortPoll",),
    "portcfg": ("_isr_g_ucAwtoPortOff",),
    "portmon": ("_g_pucAwtoPortSt",),
    "inputrate": ("_g_pucAwtoInCnt", "_AwtoInRow"),
    "monitor": ("_g_stAwtoMon",),
    "panel": ("_g_ucAwtoPanelOwn",),
    "sysm": ("_g_ucAwtoSysOwn",),
    "pacewake": ("_g_stAwtoHead", "_g_stAwtoSync", "_AwtoWakePoll"),
    "memreinit": ("_g_stAwtoSync", "_SysMachineMemReinit"),
    "nvlog": ("_g_stAwtoNv", "_AwtoNvLog"),
    "dramlog": ("_AwtoDlFlush",),
    "osdfitsim": ("_g_ucAwtoCardUp",),
    "infocard": ("_g_ucAwtoCardUp", "_g_ucAwtoSelWhy"),
}


for _k in ("keys", "wdt", "wake", "crash", "monitor", "conwrap"):       # the extensive twin of a gate has its limit and its image requirements
    SKIP_IF_MISSING[_k + "_full"] = SKIP_IF_MISSING.get(_k, ())
    LIMIT_OF[_k + "_full"] = LIMIT_OF.get(_k, LIMIT_S)
LIMIT_OF["crash"] = LIMIT_OF["crash_full"] = 60
SKIP_IF_MISSING["monitor_real"] = SKIP_IF_MISSING["monitor"]
LIMIT_OF["monitor_real"] = 90
LIMIT_OF["monitor"] = LIMIT_OF["monitor_full"] = 30
LIMIT_OF["delays_full"] = LIMIT_OF["delays_sim"] = LIMIT_OF["delays"]
SKIP_IF_MISSING = {k: v for k, v in SKIP_IF_MISSING.items() if v}


SIBLINGS = {"t0ev": ["_AWTO_T0EV_TEST"], "clk87": ["AWTO_CLOCK_MHZ=87"]}     # extensive-tier inputs: image tag suffix -> build -D defines


def sibling(b: Path, kind: str) -> Path:
    return b.with_name(b.name.replace("-be.bin", f"-{kind}-be.bin"))


def build_inputs(b: Path, log) -> None:
    """Build the sibling images the extensive tier measures (one dev.py build at a time; a missing one is a SKIP / narrower gate otherwise).
    Every build rewrites tmp/sdcc-port (the link / iram gates read its asm of the LAST build): the base image is rebuilt last."""
    serial, rest = b.name.split("-", 1)
    tag = rest[:-len("-be.bin")]
    bj = b.with_name(b.stem + ".build.json")
    base_defs = json.loads(bj.read_text()).get("defines", []) if bj.is_file() else []

    def build(name, defs):
        cmd = [sys.executable, str(ROOT / "dev.py"), "build", "--serial", serial, "--tag", name, *[x for d in defs for x in ("-D", str(d).removeprefix("-D"))]]
        log(f"build input {name}: {' '.join(cmd[2:])}")
        rc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)
        if rc.returncode:
            log(f"build input {name} FAILED rc={rc.returncode}: {(rc.stdout.strip().splitlines() or rc.stderr.strip().splitlines() or [''])[-1][:200]}")
        return rc.returncode == 0

    built = [k for k, d in SIBLINGS.items() if not sibling(b, k).is_file() and build(f"{tag}-{k}", d)]
    if built:
        build(tag, base_defs)


def header(tree):
    h = Path(tree) / "fw/sdk/Project/Header/RL6449_Project.h" if tree else None
    return h if h and h.is_file() else None


def skips(b: Path, m: Path, tree) -> dict:
    """Gates that cannot run on this image: name -> reason (SKIP, not FAIL)."""
    mt = m.read_text(errors="replace")

    def has(sym):                                  # global ' _X' or, for a static, its area 'CH_X' (no global symbol)
        return f" {sym}" in mt or f"CH_{sym.lstrip('_')} " in mt
    sk = {k: f"image lacks {', '.join(x for x in v if not has(x))}"
          for k, v in SKIP_IF_MISSING.items() if not all(has(x) for x in v)}
    if not header(tree):
        sk.setdefault("crash", "needs --tree with fw/sdk/Project/Header/RL6449_Project.h")
        sk.setdefault("crash_full", sk["crash"])
    if not (tree and Path(tree).is_dir()):
        sk["pokes"] = "needs --tree (static check of the worktree's sources)"
        sk["magic"] = sk["regs"] = sk["rules"] = "needs --tree (static check of the worktree's sources)"
    if tree and Path(tree).is_dir() and not (Path(tree) / "scripts/sdk_rules_lint.py").is_file():
        sk["rules"] = "tree has no scripts/sdk_rules_lint.py (SDK not yet our source, #162)"
    return sk


def gates(b: Path, m: Path, ref, tree):
    s = str(ROOT / "scripts")
    link = [*PY, f"{s}/fw_link_check.py", "--bin", b, "--map", m,
            "--save", ROOT / "tmp/logs/fw_gates" / f"{b.stem}.link-findings.txt"]
    if tree:
        link += ["--asm", Path(tree) / "tmp/sdcc-port/asm_bank"]
        if (lay := b.with_name(b.stem + ".bank_layout.tsv")).is_file():       # the layout this image was linked with (#44)
            link += ["--layout", lay]
    g = {}
    V = IV.of_image(b)
    mt = Path(m).read_text(errors="replace")
    if " _menu_diag" in mt:                    # #67 images: menu walk + MCCS over the spare DDC engine
        # with video (osd_render session, 1080p60 ACTIVE): without it the main loop sits in the SDK's DP RX PHY CTS routine (sim: the
        # PHY registers read 0) and the mailbox goes silent after a few seconds (#88); earlier images only passed because the
        # sim image was powered off by a phantom POWER key (ADC 0 under the old decode)
        g["menu_full"] = [*PY, f"{s}/menu_cli.py", "--sim", b, "--map", m, "walk", "--png", ROOT / "tmp/osd67/gate" / b.stem]    # extensive: every entry + a PNG per page
        g["menu"] = [*PY, f"{s}/menu_cli.py", "--sim", b, "--map", m, "--video", "walk", "--quick"]         # NORMAL: every page, one entry per class + first / last
    if " _vcp_box" in mt and " _AwtoDdcciPoll" in mt:
        g["ddc"] = [*PY, f"{s}/ddc_sim.py", b, "--map", m]
        if " _AwtoWaitPump" in mt:                 # #216: Get-VCP answered inside a blocking wait, Set left to the main loop
            g["pump"] = [*PY, f"{s}/pump_sim.py", b, "--map", m]
    out = ROOT / "tmp/fw_gates" / b.stem             # own PNG/json dir per image (gates run in parallel)
    g["keys"] = [*PY, f"{s}/key_sim_test.py", b, m, "--only", "switch"]             # NORMAL: the selector takes another input; keys_full = every screen (extensive)
    g["keys_full"] = [*PY, f"{s}/key_sim_test.py", b, m]
    t0 = sibling(b, "t0ev")                                                           # the Timer0 event cases need the test hooks (-D _AWTO_T0EV_TEST)
    wb = t0 if t0.is_file() and t0 != b else b
    g["wdt_full"] = [*PY, f"{s}/wdt_test.py", "--sim", wb, wb.with_suffix(".map"), *(["--header", hdr] if (hdr := header(tree)) else [])]
    g["wdt"] = [*g["wdt_full"], "--cases", WDT_NORMAL_CASES]                          # NORMAL: bite + no false reset + reason line + Timer0 timing
    g["sync"] = [*PY, f"{s}/sync_sim.py", b, m, "--out", out / "sync"]
    g["bootsim"] = [*PY, f"{s}/boot_sim.py", b, m, "--out", out / "boot"]
    g["bootsim_always"] = [*PY, f"{s}/boot_sim.py", b, m, "--console", "always", "--no-bite", "--out", out / "boot_always"]   # #144: console at power-on
    g["wake_full"] = [*PY, f"{s}/wake_sim.py", b, m, "--out", out / "wake"]
    g["wake"] = [*g["wake_full"], "--quick"]                                          # NORMAL: cable / EDID / AUX / SOURCE-key wakes
    g["panel"] = [*PY, f"{s}/panel_sim.py", b, m, *(["--tree", tree] if tree else [])]
    g["osdfitsim"] = [*PY, f"{s}/osd_fit_sim.py", b, m]                         # every card / selector / menu shot: no cut row (firmware fit guard)
    g["infocard"] = [*PY, f"{s}/info_card_sim.py", b, m, "--out", out / "info_card"]   # info card after boot: on-screen time, Found by
    g["sysm"] = [*PY, f"{s}/sysm_sim.py", b, m, *(["--tree", tree] if tree else [])]
    g["pacewake"] = [*PY, f"{s}/pacing_wake_sim.py", b, m, "--case", "fast", "--after", "13"]    # #313: the busy hook is off 12 s after a fast wake (~5 s CPU)
    g["memreinit"] = [*PY, f"{s}/mem_reinit_sim.py", b, m]                           # #353: memory power cycle after 2 failed frame-buffer set-ups (~3 s CPU)
    fast = sibling(b, "clk87")                                        # `--build-inputs`: dev.py build --tag <tag>-clk87 -D AWTO_CLOCK_MHZ=87 (stock clock): measured too when present
    base = [*PY, f"{s}/delay_sim.py", b, m, *(["--tree", tree, "--audit", *(["--variant", "hwtest"] if V["hwtest"] else [])] if tree else [])]
    if tree:
        g["delays"] = [*PY, f"{s}/delay_audit.py", "--check", "--tree", tree, "--map", m,
                       *(["--variant", "hwtest"] if V["hwtest"] else [])]      # NORMAL: every linked delay site is in docs/delay-audit.tsv (+ -hwtest.tsv for the test image) (~1 s)
    g["delays_sim"] = base                                                            # extensive: panel_sim scenario at the image's clock vs wall ms
    if fast.is_file() and fast != b:                                                  # extensive: + the sibling -clk87 image, DDC debounce equal at both clocks
        g["delays_full"] = [*base, "--other", fast, fast.with_suffix(".map")]
    g["nvlog"] = [*PY, f"{s}/nv_test.py", "--sim", b, "--map", m, "--cases", "flushlog"]   # #151: flush lines say what was written
    if " _AwtoFlashWrBegin" in mt:                          # flash clock default: FF6C / F2 order at boot, write sessions at F2 5
        g["flashclk"] = [*PY, f"{s}/flash_clk_sim.py", b, "--map", m]
    g["deadport"] = [*PY, f"{s}/deadport_sim.py", b, m]       # #84: VCP 0x60 / selector refuse a port with no cable, guard back to auto
    g["portcfg"] = [*PY, f"{s}/portcfg_sim.py", b, m]         # #81: disabled port: HPD never high, never searched, selector re-enables
    g["portmon"] = [*PY, f"{s}/portmon_sim.py", b, m]         # #323 / #324: per-port status word follows the cable pins, search order skips dead ports
    g["inputrate"] = [*PY, f"{s}/input_rate_sim.py", b, m]    # D7: pass / slow input rows: a pulse of the worst read gap is never missed
    g["monitor_real"] = [*PY, f"{s}/mon_sim_test.py", b, m]     # health monitor at the production period: rows, change steps, registry switch, heartbeat (300 simulated s)
    g["monitor_full"] = [*g["monitor_real"], "--scale", "10"]   # extensive: the same with the sample period / 10 (sim_time_scale.py), heartbeat included
    g["monitor"] = [*g["monitor_full"], "--no-beat"]            # NORMAL: all but the 30-sample heartbeat, period / 10
    g["htime"] = [*PY, f"{s}/host_time_sim.py", b, "--map", m]
    if " _isr_g_ucTMDSRxPhyPend" in mt:                     # #256: TMDS PHY set-up deferred out of EXINT0 (flag handshake)
        g["tmdsphy"] = [*PY, f"{s}/tmds_phy_defer_test.py", b, m]
    g["conmode"] = [*PY, f"{s}/console_mode_sim.py", b, m]    # #218: Off / Until signal (3 s close, key dismiss) / Always
    if " _g_ucAwtoStackFatal" in mt:                       # #203 stack canary: quiet at ACTIVE, fatal + halt on 0x3F
        g["canary"] = [*PY, f"{s}/stack_canary_sim.py", b, m]
    g["dramlog"] = [*PY, f"{s}/dram_log_sim.py", b, m]         # DRAM log: DDR ring format, wrap, warm reset keeps the history
    g["conkeep"] = [*PY, f"{s}/con_keep_sim.py", b, "--map", m]       # log keeping: the console is a view of the ring, a warm reset keeps it
    if tree:
        g["conhost"] = [*PY, f"{s}/con_wrap_host.py"]                                 # NORMAL: the real wrap decision (fw/osd/conwrap.c) compiled on the host, ~0.1 s
    g["conwrap_full"] = [*PY, f"{s}/con_wrap_sim.py", b, "--map", m, "--out", out / "conwrap_full", *(["--tree", tree] if tree else [])]   # no line clipped, real events
    g["conwrap"] = [*PY, f"{s}/con_wrap_sim.py", b, "--map", m, "--out", out / "conwrap", "--scope", "inject", *(["--tree", tree] if tree else [])]    # NORMAL: injected widest lines
    g["condelta"] = [*PY, f"{s}/con_delta_sim.py", b, "--map", m, "--out", out / "condelta"]   # console time columns + joined rows (awto-ddc#354)
    if header(tree):
        g["crash_full"] = [*PY, f"{s}/crash_sim_test.py", "--header", header(tree), "--out", out / "wdt", b, m]
        g["crash"] = [*g["crash_full"], "--tests", "stall"]                            # NORMAL: the 0x4C stall -> bite -> record
    if tree and Path(tree).is_dir():
        g["pokes"] = [*PY, f"{s}/poke_loops.py", tree, "--out", out / "poke_loops.tsv"]
        g["magic"] = [*PY, f"{s}/magic_lint.py", "--tree", tree]
        g["rxports"] = [*PY, f"{s}/dp_rx_port_cutline.py", "--check", "--tree", tree]     # #326: every Rx1 global classified, lt-hot state only through the per-port accessors
        g["regs"] = [*PY, f"{s}/gen_regnames.py", "--tree", tree, "--check"]
        if (Path(tree) / "scripts/regmap_build.py").is_file():                       # register knowledge base (re/regmap)
            g["regmap"] = [*PY, f"{tree}/scripts/regmap_build.py", "--check"]
        if (Path(tree) / "scripts/iram_names.py").is_file():                       # #189: d_ / i_ names match IRAM placement
            g["iram"] = [*PY, f"{tree}/scripts/iram_names.py", "check", "--asm", Path(tree) / "tmp/sdcc-port/asm_ovl", "--map", m]
        if (Path(tree) / "scripts/xdata_layout.py").is_file():                        # pinned XDATA slots match the linked map
            g["xlayout"] = [*PY, f"{tree}/scripts/xdata_layout.py", "check", "--tree", tree, "--map", m,
                            *(["--layout", V["layout"]] if V["layout"] else [])]   # a variant never promotes the tracked layout (#268): its own
        g["rules"] = [*PY, f"{tree}/scripts/sdk_rules_lint.py", "--tree", tree]     # #162: no build step patches the SDK
        if (Path(tree) / "scripts/osd_fit.py").is_file():                            # OSD rows fit their boxes, static (fw/osd/osd_fit.tsv)
            g["osdfit"] = [*PY, f"{tree}/scripts/osd_fit.py", "--check", "--tree", tree]
        for nm, sc in (("gensync", "gen_awto_sync.py"), ("geninputs", "gen_awto_inputs.py"), ("gensavers", "gen_awto_savers.py")):      # #162: generated C tables current
            if (Path(tree) / "scripts" / sc).is_file():
                g[nm] = [*PY, f"{tree}/scripts/{sc}", "--check"]
    g["edid"] = [*PY, f"{s}/edid_gate.py"]                                             # #321: edid-decode -c on the 3 tables, warnings only from scripts/edid_allow.txt
    g["dwmodel"] = [*PY, f"{s}/dw8051_model.py", "--check"]                            # #162: CPU timing tables current
    return {
        **g,
        "boot": [*PY, f"{s}/fw_sim.py", "--boot-check", b, m],
        "isr": [*PY, f"{s}/fw_sim.py", "--isr-check", b, m],
        "link": link,
        "h1080": [*PY, f"{s}/unit_health.py", "--sim", b, m, "--host-mode", "1920x1080@60"],
        "h2160": [*PY, f"{s}/unit_health.py", "--sim", b, m, "--host-mode", "3840x2160@60"],
    }


def load_factor() -> float:
    """1 + 1-minute loadavg / cores, clamped to [1, LOAD_CAP]: a gate sharing every core with another job runs ~2x slower."""
    return max(1.0, min(LOAD_CAP, 1.0 + os.getloadavg()[0] / (os.cpu_count() or 1)))


def cpu_ticks(pid: int) -> float:
    """CPU seconds used so far by the process tree under pid (0 if gone)."""
    try:
        import psutil
    except ImportError:
        return 0.0
    try:
        ps = psutil.Process(pid)
        return sum(sum(x.cpu_times()[:2]) for x in [ps, *ps.children(recursive=True)] if _alive(x))
    except psutil.Error:
        return 0.0


def _alive(x) -> bool:
    import psutil
    try:
        return x.is_running()
    except psutil.Error:
        return False


def guard_verdict(now, t0, last_out, last_cpu, limit, stall=None, factor=1.0):
    stall = STALL_S if stall is None else stall
    """None while fine, else ("stall" | "limit", text). Stall = no output line AND no CPU progress for `stall` s
    (a child starved of CPU on a loaded box still advances its CPU clock; a deadlock / sleep does not).
    The backstop `limit` is scaled by `factor` (load / cores, capped)."""
    quiet = now - max(last_out, last_cpu)
    if quiet > stall:
        return "stall", f"silent {now - last_out:.0f}s, no CPU progress for {now - last_cpu:.0f}s > {stall}s"
    if now - t0 > limit * factor:
        return "limit", f"{now - t0:.0f}s > {limit}s x load factor {factor:.2f}"
    return None


def run(name, cmd, out: Path, res: dict, log):
    """One gate, at most two attempts: a guard kill (stall / limit) is rerun once, both runs logged; two kills = real failure.
    A gate that fails by its own exit code is not rerun."""
    for attempt in (1, 2):
        rc, dt, last, killed = run_once(name, cmd, out if attempt == 1 else out.with_suffix(".rerun.log"), log)
        if not killed:
            break
        log(f"{name}: guard kill on attempt {attempt}" + (", rerunning once" if attempt == 1 else ", failing"))
    res[name] = (rc, dt, last)


def run_once(name, cmd, out: Path, log):
    t0 = time.monotonic()
    last = [t0, ""]
    cpu = [t0, 0.0]                              # [time of last CPU progress, CPU seconds seen]
    killed = [False]
    limit = LIMIT_OF.get(name, SPEED_LIMIT_S if name == "speed" else LIMIT_S)
    with out.open("w") as f:
        p = subprocess.Popen(list(map(str, cmd)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT,
                             env=dict(os.environ, PYTHONHASHSEED="0", **({"AWTO_SIM_CORE": "fast", "AWTO_SIM_CPU": CPU_OF.get(name, SIM_CPU)} if name not in NO_SIM else {})))

        def watch():
            while p.poll() is None:
                now = time.monotonic()
                c = cpu_ticks(p.pid)
                if c > cpu[1]:
                    cpu[0], cpu[1] = now, c
                v = guard_verdict(now, t0, last[0], cpu[0], limit, factor=load_factor())
                if v:
                    log(f"{name}: KILL ({v[0]}) after {now - t0:.0f}s: {v[1]}, last: {last[1][:160]!r}, "
                        f"loadavg {os.getloadavg()[0]:.1f} on {os.cpu_count()} cores, cpu {cpu[1]:.1f}s")
                    killed[0] = True
                    p.kill()
                    return
                try:
                    p.wait(timeout=1)            # 1 s watchdog tick; returns at once when the gate exits
                except subprocess.TimeoutExpired:
                    pass

        threading.Thread(target=watch, daemon=True).start()
        for line in p.stdout:
            f.write(line); f.flush()
            last[0], last[1] = time.monotonic(), line.strip()
        rc = p.wait()
    return rc, time.monotonic() - t0, last[1], killed[0] and rc != 0     # a gate that finished cleanly as the guard fired is a pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stem")
    ap.add_argument("--against", default="", help="ignored (#66: link findings must be 0, no baseline)")
    ap.add_argument("--speed", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--tier", choices=("normal", "extensive"), default="normal",
                    help="normal (default, the flash gate): all gates but EXTENSIVE; extensive: every gate (normal + the long sweeps)")
    ap.add_argument("--build-inputs", action="store_true", help="extensive tier: build the missing sibling images first (-t0ev for wdt_full, -clk87 for delays_full)")
    # default = this repo: without a tree, wdt / conwrap use stale built-in constants and the static gates drop out
    ap.add_argument("--tree", default=str(ROOT), help="worktree the image was built in (its asm_bank); default this repo")
    a = ap.parse_args()
    (ROOT / "tmp/logs/fw_gates").mkdir(parents=True, exist_ok=True)
    lf = (ROOT / "tmp/logs/fw_gates.log").open("a", buffering=1)

    def log(s):
        line = f"{isostamp.now()} {s}"
        print(line, flush=True); lf.write(line + "\n")

    stem = Path(a.stem)
    b = stem.with_suffix(".bin") if stem.suffix != ".bin" else stem
    m = b.with_suffix(".map")
    bjf = b.with_name(b.stem + ".build.json")
    xf = json.loads(bjf.read_text()).get("extra_fw", "") if bjf.is_file() else ""
    if xf:                                              # an --extra-fw image: the static gates read the same extra sources (scripts/fw_dirs.py)
        os.environ["AWTO_EXTRA_FW"] = xf
        log(f"extra source root {xf}")
    else:
        os.environ.pop("AWTO_EXTRA_FW", None)
    st = b.with_name(b.stem + ".settings_table.py")    # the image's own registry (dev.py build); else scripts/settings_table.py
    if st.is_file():
        os.environ["AWTO_SETTINGS_TABLE"] = str(st.resolve())
        log(f"settings table {st.name}")
    else:
        log("settings table: none beside the image, scripts/settings_table.py (main's registry) is used")
    if a.build_inputs and a.tier == "extensive":
        build_inputs(b, log)
    g = gates(b, m, a.against, a.tree)
    sk = skips(b, m, a.tree)
    if a.only:
        g = {k: v for k, v in g.items() if k in a.only.split(",")}
    elif a.tier == "normal":
        g = {k: v for k, v in g.items() if k not in EXTENSIVE}
    else:                                           # extensive: a full twin replaces its quick variant
        g = {k: v for k, v in g.items() if k + "_full" not in g}
    sk = {k: v for k, v in sk.items() if k in g}
    g = {k: v for k, v in g.items() if k not in sk}
    if a.speed:
        g["speed"] = [*PY, str(ROOT / "scripts/speed_bench.py"), b.with_suffix(""), "--label", a.speed]
    log(f"=== gates {b.name}: {', '.join(g)}{'; SKIP ' + ', '.join(sk) if sk else ''}; sim cpu {SIM_CPU}"
        f"{' (' + ', '.join(f'{k}: {v}' for k, v in CPU_OF.items() if k in g) + ')' if any(k in g for k in CPU_OF) else ''} ===")
    res = {}
    # boot/isr/link first, one at a time: boot-check shares tmp/fwsim/<stem>/ with the health sims (a parallel run FAILed at
    # gsinit, 2026-11-07); then the rest (separate SimBus machines) in parallel
    for group in ([k for k in g if k in ("boot", "isr", "link")], [k for k in g if k not in ("boot", "isr", "link")]):
        th = []
        for k in group:
            t = threading.Thread(target=run, args=(k, g[k], ROOT / "tmp/logs/fw_gates" / f"{b.stem}.{k}.log", res, log))
            t.start(); th.append(t)
            if k in ("boot", "isr", "link"):
                t.join()                 # short ones in turn; the sims run in parallel (per-process sim dir, fw_sim)
        for t in th:
            t.join()
    bad, rec = 0, {}
    for k in g:
        rc, dt, last = res[k]
        ok = rc == 0
        bad += not ok
        note = last[:150]
        if k in ("wdt", "wdt_full"):
            n = sum(1 for ln in (ROOT / "tmp/logs/fw_gates" / f"{b.stem}.{k}.log").read_text(errors="replace").splitlines()
                    if re.match(r"\s+SKIP\s", ln))
            note = f"{n} case(s) SKIP; {note}" if n else note
        rec[k] = {"result": "PASS" if ok else "FAIL", "rc": rc, "seconds": round(dt, 1), "note": note}
        log(f"{rec[k]['result']} {k:6s} rc={rc} {dt:5.0f}s  {note}")
    for k, why in sk.items():
        rec[k] = {"result": "SKIP", "rc": None, "seconds": 0, "note": why}
        log(f"SKIP {k:6s} {why}")
    write_record(b, rec, a.tree, complete=not a.only, tier=a.tier)
    nr = json.loads(b.with_suffix(".gates.json").read_text()).get("new_red")
    if nr:
        log(f"NEW RED vs {json.loads(b.with_suffix('.gates.json').read_text())['prev_record']}: {', '.join(nr)}")
    log(f"=== {b.name}: {'ALL PASS' if not bad else f'{bad} FAIL'}, {len(sk)} SKIP ===")
    return 1 if bad else 0


def previous_red(b: Path, tier: str):
    """(record name, red gates) of the newest other record of the same tier, else (None, set())."""
    cands = sorted((p for p in b.parent.glob("*.gates.json") if p != b.with_suffix(".gates.json")), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in cands:
        try:
            d = json.loads(p.read_text())
        except ValueError:
            continue
        if d.get("tier") == tier and d.get("complete"):
            return p.name, set(d.get("red") or [k for k, v in d["gates"].items() if v.get("result") == "FAIL"])
    return None, set()


def common_record(b: Path):
    """Common-region numbers of this image (scripts/common_metrics.py); None without a map. No threshold."""
    import common_metrics
    m = b.with_suffix(".map")
    return common_metrics.measure(m, b.with_name(b.stem + ".bank_layout.tsv")) if m.is_file() else None


def write_record(b: Path, rec: dict, tree, complete: bool, tier: str = "normal") -> None:
    """tmp/fw/<stem>.gates.json: what `dev.py flash` checks (SHA-256 of the .bin, complete, no FAIL); red = FAIL gates, new_red = red and not red in the previous record of the tier."""
    red = sorted(k for k, v in rec.items() if v["result"] == "FAIL")
    prev, prev_red = previous_red(b, tier)
    def git(*x):
        return subprocess.run(["git", "-C", str(ROOT), *x], capture_output=True, text=True, check=False).stdout.strip()
    doc = {"image": b.name, "sha256": hashlib.sha256(b.read_bytes()).hexdigest(),
           "date": isostamp.now(), "complete": complete, "tier": tier, "tree": str(tree or ""),
           "fw_gates_commit": git("rev-parse", "HEAD") + ("+dirty" if git("status", "--porcelain", "--", "scripts/fw_gates.py") else ""),
           "xdata": (json.loads(xj.read_text()) if (xj := b.with_suffix(".xdata.json")).is_file() else None),
           "common": common_record(b), "red": red, "prev_record": prev, "new_red": sorted(set(red) - prev_red) if prev else red, "gates": rec}
    out = b.with_suffix(".gates.json")
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1) + "\n")
    tmp.replace(out)


if __name__ == "__main__":
    sys.exit(main())
