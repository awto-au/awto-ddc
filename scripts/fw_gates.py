#!/usr/bin/env python3
"""Offline gates for one firmware image (sims in parallel): boot-check, isr-check, link check, health --sim 1080p60 + 2160p60,
menu, ddc, keys, crash, wdt, sync, bootsim, wake, panel, sysm, pokes, htime, magic, regs.

usage: fw_gates.py IMAGE_STEM [--tree WORKTREE] [--speed LABEL] [--only boot,isr,link,h1080,h2160,menu,ddc,keys,crash,wdt,sync,bootsim,wake,pokes,htime,magic,regs]
  menu, ddc: only for images with the settings registry (#67): menu_cli walk + ddc_sim (MCCS) in fw_sim.
  keys: key_sim_test (#129). crash: crash_sim_test --header TREE/... (#131, #138). wdt: wdt_test --sim, all cases.
  htime: host_time_sim (#157: DDC/CI host time, console title row, ring lines).
  conwrap: con_wrap_sim (#162: console lines whole, a wide line on two rows; widest lines + map end, no watchdog bite).
  sync: sync_sim (#139). bootsim: boot_sim (#144, #29; `boot` is the fw_sim --boot-check). wake: wake_sim (#144 task 4). pokes: poke_loops TREE (static, #138).
  panel: panel_sim (#162 step 2): panel VDD / backlight pin / PWM / DPTx link only from the panel machine; no blink; T3..T6 kept.
  sysm: sysm_sim (#162 step 3): power status / mode state only from the system machine; transition chain + request lines; --tree lint.
  magic: magic_lint.py TREE (#161: no raw register address / palette value in our code; allow-list scripts/magic_allow.tsv).
  regs: gen_regnames.py --check (AwtoRegs.h matches the names our code uses).
  IMAGE_STEM = tmp/fw/<tag> (.bin + .map beside it). link: 0 findings (#66, no baseline).
  --speed LABEL: also append a speed_bench row (docs/speed-bench.tsv) for the image.
  Each gate's output -> tmp/logs/fw_gates/<stem>.<gate>.log; one PASS/FAIL/SKIP line per gate; exit 1 if any fails.
SKIP (counted, printed): the image lacks the feature (SKIP_IF_MISSING: map symbols), or the gate needs --tree and none was given.
  wdt cases the image does not implement report SKIP inside wdt_test; they are counted in the gate's note.
Record: tmp/fw/<stem>.gates.json = image SHA-256, date, per-gate result + seconds, fw_gates git commit, complete (no --only).
  `dev.py flash` refuses an image without a record whose SHA-256 matches, complete, and with no FAIL (--force-ungated overrides).
Stall guard (awto-dan#53): a gate silent for STALL_S is killed and FAILs; backstop LIMIT_S per gate.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root

ROOT = repo_root()
STALL_S = 60          # no output line for 60 s = hung (awto-dan#53)
LIMIT_OF = {"keys": 100, "wdt": 60, "rules": 30}   # 3x the cold run (keys 33 s with the #132 switch cases 2026-11-12, wdt 18 s; fast core); table of all gates: commit message
LIMIT_S = 30          # 3x the cold run of the rest (all <= 9 s), 30 s = interpreter start + a loaded box; `speed` is the exception
SPEED_LIMIT_S = 900   # speed_bench: not measured
PY = [sys.executable, "-u"]
SIM_CPU = os.environ.get("AWTO_SIM_CPU", "dw8051")   # fast-core CPU model of the sims (#162 step 1); results are comparable only at the same model
CPU_OF = {"wdt": "8052"}      # wdt_test t0_arm_from_isr / prio_t0_vs_exint measure Timer0 events in ucsim cycles (m.ticks); not yet ported to the dw8051 clock (open item #162)
NO_SIM = {"link", "pokes", "speed", "magic", "regs", "rules"}   # every other gate runs a sim: AWTO_SIM_CORE=fast (in-process core; the ucsim default needs ucsim_51 on PATH)
SKIP_IF_MISSING = {      # gate -> map symbols the image must define, else SKIP (the script would FAIL on an older image)
    "keys": ("_AwtoSourceOpen",),
    "crash": ("_AwtoWdtHang",),
    "wdt": ("_AwtoWdtHang",),
    "sync": ("_g_stAwtoSync",),
    "bootsim": ("_g_stAwtoSync",),
    "wake": ("_AwtoPsWakeFire",),
    "htime": ("_g_stAwtoHt",),
    "conwrap": ("_AwtoConWrapLine",),
    "deadport": ("_AwtoDeadPortPoll",),
    "panel": ("_g_ucAwtoPanelOwn",),
    "sysm": ("_g_ucAwtoSysOwn",),
}


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
        link += ["--layout", Path(tree) / "fw/bank_layout.tsv", "--asm", Path(tree) / "tmp/sdcc-port/asm_bank"]
    g = {}
    mt = Path(m).read_text(errors="replace")
    if " _menu_diag" in mt:                    # #67 images: menu walk + MCCS over the spare DDC engine
        # with video (osd_render session, 1080p60 ACTIVE): without it the main loop sits in the SDK's DP RX PHY CTS routine (sim: the
        # PHY registers read 0) and the mailbox goes silent after a few seconds (#88); earlier images only passed because the
        # sim image was powered off by a phantom POWER key (ADC 0 under the old decode)
        g["menu"] = [*PY, f"{s}/menu_cli.py", "--sim", b, "--map", m, "walk", "--png", ROOT / "tmp/osd67/gate" / b.stem]
    if " _vcp_box" in mt and " _AwtoDdcciPoll" in mt:
        g["ddc"] = [*PY, f"{s}/ddc_sim.py", b, "--map", m]
    out = ROOT / "tmp/fw_gates" / b.stem             # own PNG/json dir per image (gates run in parallel)
    g["keys"] = [*PY, f"{s}/key_sim_test.py", b, m]
    g["wdt"] = [*PY, f"{s}/wdt_test.py", "--sim", b, m, *(["--header", hdr] if (hdr := header(tree)) else [])]
    g["sync"] = [*PY, f"{s}/sync_sim.py", b, m, "--out", out / "sync"]
    g["bootsim"] = [*PY, f"{s}/boot_sim.py", b, m, "--out", out / "boot"]
    g["wake"] = [*PY, f"{s}/wake_sim.py", b, m, "--out", out / "wake"]
    g["panel"] = [*PY, f"{s}/panel_sim.py", b, m, *(["--tree", tree] if tree else [])]
    g["sysm"] = [*PY, f"{s}/sysm_sim.py", b, m, *(["--tree", tree] if tree else [])]
    g["deadport"] = [*PY, f"{s}/deadport_sim.py", b, m]       # #84: VCP 0x60 / selector refuse a port with no cable, guard back to auto
    g["htime"] = [*PY, f"{s}/host_time_sim.py", b, "--map", m]
    g["conwrap"] = [*PY, f"{s}/con_wrap_sim.py", b, "--map", m, "--out", out / "conwrap", *(["--tree", tree] if tree else [])]   # no line clipped
    if header(tree):
        g["crash"] = [*PY, f"{s}/crash_sim_test.py", "--header", header(tree), "--out", out / "wdt", b, m]
    if tree and Path(tree).is_dir():
        g["pokes"] = [*PY, f"{s}/poke_loops.py", tree, "--out", out / "poke_loops.tsv"]
        g["magic"] = [*PY, f"{s}/magic_lint.py", "--tree", tree]
        g["regs"] = [*PY, f"{s}/gen_regnames.py", "--tree", tree, "--check"]
        g["rules"] = [*PY, f"{tree}/scripts/sdk_rules_lint.py", "--tree", tree]     # #162: no build step patches the SDK
        for nm, sc in (("gensync", "gen_awto_sync.py"), ("geninputs", "gen_awto_inputs.py")):      # #162: generated C tables current
            if (Path(tree) / "scripts" / sc).is_file():
                g[nm] = [*PY, f"{tree}/scripts/{sc}", "--check"]
    g["dwmodel"] = [*PY, f"{s}/dw8051_model.py", "--check"]                            # #162: CPU timing tables current
    return {
        **g,
        "boot": [*PY, f"{s}/fw_sim.py", "--boot-check", b, m],
        "isr": [*PY, f"{s}/fw_sim.py", "--isr-check", b, m],
        "link": link,
        "h1080": [*PY, f"{s}/unit_health.py", "--sim", b, m, "--host-mode", "1920x1080@60"],
        "h2160": [*PY, f"{s}/unit_health.py", "--sim", b, m, "--host-mode", "3840x2160@60"],
    }


def run(name, cmd, out: Path, res: dict, log):
    t0 = time.monotonic()
    last = [t0, ""]
    with out.open("w") as f:
        p = subprocess.Popen(list(map(str, cmd)), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, cwd=ROOT,
                             env=dict(os.environ, PYTHONHASHSEED="0", **({"AWTO_SIM_CORE": "fast", "AWTO_SIM_CPU": CPU_OF.get(name, SIM_CPU)} if name not in NO_SIM else {})))

        def watch():
            while p.poll() is None:
                now = time.monotonic()
                if now - last[0] > STALL_S or now - t0 > LIMIT_OF.get(name, SPEED_LIMIT_S if name == "speed" else LIMIT_S):
                    why = "stall" if now - last[0] > STALL_S else "limit"
                    log(f"{name}: KILL ({why}) after {now - t0:.0f}s, silent {now - last[0]:.0f}s, last: {last[1][:160]!r}, "
                        f"loadavg {os.getloadavg()[0]:.1f}")
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
    res[name] = (rc, time.monotonic() - t0, last[1])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("stem")
    ap.add_argument("--against", default="", help="ignored (#66: link findings must be 0, no baseline)")
    ap.add_argument("--speed", default="")
    ap.add_argument("--only", default="")
    ap.add_argument("--tree", default="", help="worktree the image was built in (its bank_layout.tsv + asm_bank)")
    a = ap.parse_args()
    (ROOT / "tmp/logs/fw_gates").mkdir(parents=True, exist_ok=True)
    lf = (ROOT / "tmp/logs/fw_gates.log").open("a", buffering=1)

    def log(s):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(line, flush=True); lf.write(line + "\n")

    stem = Path(a.stem)
    b = stem.with_suffix(".bin") if stem.suffix != ".bin" else stem
    m = b.with_suffix(".map")
    st = b.with_name(b.stem + ".settings_table.py")    # the image's own registry (wb_build); else scripts/settings_table.py
    if st.is_file():
        os.environ["AWTO_SETTINGS_TABLE"] = str(st.resolve())
        log(f"settings table {st.name}")
    g = gates(b, m, a.against, a.tree)
    sk = skips(b, m, a.tree)
    if a.only:
        g = {k: v for k, v in g.items() if k in a.only.split(",")}
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
        ok = rc == 0 or (k.startswith("h") and last.endswith("FAIL: delay cal"))   # delay cal needs wb-delaycal (#54)
        bad += not ok
        note = last[:150]
        if k == "wdt":
            n = sum(1 for ln in (ROOT / "tmp/logs/fw_gates" / f"{b.stem}.{k}.log").read_text(errors="replace").splitlines()
                    if re.match(r"\s+SKIP\s", ln))
            note = f"{n} case(s) SKIP; {note}" if n else note
        rec[k] = {"result": "PASS" if ok else "FAIL", "rc": rc, "seconds": round(dt, 1), "note": note}
        log(f"{rec[k]['result']} {k:6s} rc={rc} {dt:5.0f}s  {note}")
    for k, why in sk.items():
        rec[k] = {"result": "SKIP", "rc": None, "seconds": 0, "note": why}
        log(f"SKIP {k:6s} {why}")
    write_record(b, rec, a.tree, complete=not a.only)
    log(f"=== {b.name}: {'ALL PASS' if not bad else f'{bad} FAIL'}, {len(sk)} SKIP ===")
    return 1 if bad else 0


def write_record(b: Path, rec: dict, tree, complete: bool) -> None:
    """tmp/fw/<stem>.gates.json: what `dev.py flash` checks (SHA-256 of the .bin, complete, no FAIL)."""
    def git(*x):
        return subprocess.run(["git", "-C", str(ROOT), *x], capture_output=True, text=True).stdout.strip()
    doc = {"image": b.name, "sha256": hashlib.sha256(b.read_bytes()).hexdigest(),
           "date": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "complete": complete, "tree": str(tree or ""),
           "fw_gates_commit": git("rev-parse", "HEAD") + ("+dirty" if git("status", "--porcelain", "--", "scripts/fw_gates.py") else ""),
           "gates": rec}
    out = b.with_suffix(".gates.json")
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=1) + "\n")
    tmp.replace(out)


if __name__ == "__main__":
    sys.exit(main())
