#!/usr/bin/env python3
"""Typed inventory of every delay / wait / poll / timeout in the linked firmware, and the gate that keeps it complete (docs/delay-audit.md).

usage: delay_audit.py --write [--tree DIR] [--map MAP] [--variant hwtest]   regenerate docs/delay-audit.tsv from the tree's last build (hand columns kept by key)
       delay_audit.py --check [--tree DIR] [--map MAP] [--variant hwtest]   FAIL on a linked site that is not in the TSV, a TSV verdict FIX / UNKNOWN, a stale count formula
       delay_audit.py --check also judges the interrupt-masked sections (scripts/irq_masks.py: every one in docs/irq-masks.tsv, EX0 / EA masked <= 100 us unless a reasoned budget_us)
       delay_audit.py --check also judges the blocking budget (per function, per ISR handler tree; docs/delay-budget.tsv rows with a reason raise a cap); --write-budget adds rows
       delay_audit.py --counts                            the loop-count formula (AWTO_DELAY_CNT) at every clock state (350.8 default, 175.4, 87.7, XTAL, IOSC), from the header text
Source of the sites: scripts/delay_inventory.py (post-link: the SDCC listing of the tree's build, so "linked" is exact).
Classes: A timer wait (Timer2 ms) | B micro-delay (DELAY_5US / DELAY_XUS loop count, per clock state) | C spin loop / counted loop |
  D hardware-spec minimum (datasheet value - 10 %) | E our own timing constant.
Verdicts: OK (wall time equal at 87.7 and 175.4 MHz by construction + sim gate) | NOCLOCK (hardware-bound, no timed bound) | SCALES-BENIGN (halves at 2x, harmless: stated why)
  | FIXED (was wrong at 2x, fixed: note) | FIX | UNKNOWN (both fail the gate).
--variant hwtest|freeze: the image's sites must be in docs/delay-audit.tsv or docs/delay-audit-<variant>.tsv (write: the second file holds only the sites the first lacks);
  a default image still needs every site in the first file. hwtest skips the blocking budget + masked sections (test ops block on purpose); freeze runs them.
Key = file | function | kind | normalised statement | ordinal (no line numbers: lines move). Log: ./tmp/logs/delay_audit.log
"""
import argparse
import collections
import csv
import os
import re
import sys
from pathlib import Path

from _log import log_line as _log_line

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _repo import ROOT

TSV = ROOT / "docs/delay-audit.tsv"
VARIANT_TSV = {"hwtest": ROOT / "docs/delay-audit-hwtest.tsv",     # sites only in that variant's image (-D _AWTO_OSD_HWTEST test ops); same columns + verdict rule
               "freeze": ROOT / "docs/delay-audit-freeze.tsv"}     # -D _AWTO_FREEZE=_ON (#349: a --write on the default image dropped its row from the main file)
BLOCKS_ON_PURPOSE = {"hwtest"}     # test ops: no blocking budget / masked-section check
LOG = ROOT / "tmp/logs/delay_audit.log"
COLS = ["key", "id", "class", "file", "line", "function", "kind", "value", "unit", "derivation", "scales_2x", "wall_87_7", "wall_350_8",
        "spec", "evidence", "verdict", "note", "stmt"]
CLKS = (87.7, 175.4)

# ---- hand verdicts of the loops the inventory cannot classify by kind: (file basename, function) -> (class, derivation, scales_2x, verdict, note)
HAND = {
    ("dbgisr.c", "AwtoDbgIsrCmd_EXINT1"): ("C", "I2C FIFO status bit, bounded by the byte count", "no", "NOCLOCK", "host I2C rate, no timed bound"),
    ("diag.c", "AwtoDiagStage"): ("A", "wait for the next Timer2 tick (<= 1 ms)", "no", "OK", "Timer2 edge"),
    ("diag.c", "AwtoDiagMainPass"): ("A", "wait for the next Timer2 tick (<= 1 ms)", "no", "OK", "Timer2 edge"),
    ("wdt.c", "AwtoWdtProbe"): ("A", "wait for the next Timer2 tick (<= 1 ms)", "no", "OK", "Timer2 edge"),
    ("t0ev.c", "AwtoT0EvTestIsr"): ("A", "3 Timer2 ticks (test only)", "no", "OK", "Timer2 ticks"),
    ("RL6449_Series_DPRx1.c", "ScalerDpRx1StreamClkRegenerate"): ("A", "<= 10 passes x ScalerTimerDelayXms(frame time)", "no", "OK", "pass count x Timer2 ms"),
    ("RL6449_Series_DPRx1.c", "ScalerDpRx1PhyCTS"): ("C", "PHY compliance test state flags, no bound", "no", "NOCLOCK", "CTS mode only (_AWTO_DP_PHYCTS), host driven"),
    ("RL6449_Series_Mcu.c", "ScalerMcuGpioInitial"): ("A", "20 x ScalerTimerDelayXms(1), POLLING_VCCK_OFF_STATUS", "no", "OK", "Timer2 ms"),
    ("RL6449_Series_Power.c", "ScalerPowerGroupAIsolation"): ("A", "20 x ScalerTimerDelayXms(1), POLLING_VCCK_OFF_STATUS", "no", "OK", "Timer2 ms"),
    ("RL6449_Series_Power.c", "ScalerPowerGroupADIPowerCut"): ("B", "50 passes x DELAY_5US (250 us bound)", "no", "OK", "pass count x class B loop (count derived from the clock)"),
    ("RL6449_Series_Power.c", "ScalerPowerGroupDPowerCut"): ("B", "50 passes x DELAY_5US (250 us bound)", "no", "OK", "as ADI"),
    ("ScalerCommonDebug.c", "ScalerDebugMessage"): ("C", "5 reads of the debug I2C FIFO count, no delay in the pass", "yes", "SCALES-BENIGN",
                                                   "a give-up after ~5 reads (about 5 us at 87.7 MHz, half at 175.4), not a wait: the host drains at I2C rate; debug-message path, not our log"),
    ("ScalerCommonDebug.c", "ScalerDebug"): ("C", "<= 5 reads (counted) or the host release flag", "yes", "SCALES-BENIGN", "as ScalerDebugMessage; ucHalt = host release, no timed bound"),
    ("ScalerCommonDebug.c", "ScalerDebugIntProc_EXINT1"): ("C", "I2C status bit, no bound", "no", "NOCLOCK", "host I2C rate"),
    ("ScalerCommonTimerFunction.c", "ScalerTimerPollingFlagProc"): ("A", "timeout + 1 Timer2 ticks", "no", "OK", "Timer2 ticks"),
    ("ScalerAudio.c", "ScalerAudioDVCVolumeMute"): ("A", "<= _DVC_VOLUME_MUTE_TIMER x ScalerTimerDelayXms(1)", "no", "OK", "Timer2 ms"),
    ("ScalerDisplayDPTx.c", "ScalerDisplayDPTx1LinkTraining"): ("C", "link-training state machine, each state has its own timed wait", "no", "NOCLOCK", "result flags; the waits inside are class A"),
    ("ScalerDisplayDPTx.c", "ScalerDisplayDPTx1AuxRead"): ("C", "7 retries, each ended by the AUX hardware reply timeout", "no", "NOCLOCK", "retry count, the time is the AUX hardware's"),
    ("ScalerIDomain.c", "ScalerIDomainVgipIVDelayIVstStepAdjust"): ("C", "<= counter passes, each a double-buffer apply poll", "no", "NOCLOCK", "polls the apply flag (class A inside)"),
    ("ScalerTMDSRx2_SeptPhy.c", "ScalerTMDSRxHdmiWaitDeepColorPllLock"): ("A", "lock polls with ScalerTimerDelayXms in the pass", "no", "OK", "Timer2 ms"),
    ("ScalerTimerFunction.c", "ScalerTimerWaitForEvent"): ("A", "_TIMER_WAIT_EVENT_TIMEOUT + 1 Timer2 ticks", "no", "OK", "Timer2 ticks"),
    ("ScalerCommonSync.c", "ScalerSyncDdcDetectDebounce_EXINT1"): ("C", "counted for loop: _TMDS_DDC_DEBOUNCE_NORMAL passes of 100.5 clk", "yes, count follows the clock", "OK",
                                                                 "count = AWTO_CPU_KHZ_M2PLL / 381: 263.6 us at both clocks [emu] (SDK comment says 300 us [sdk-hypothesis]); _PS = 55 unchanged"),
}
# HWTEST-only loops (fw/test/testcmd.c, -D _AWTO_OSD_HWTEST / clock sweep): the inventory attributes them to one function, so keyed by (file, statement)
HAND_STMT = {
    ("audio.c", "while((ScalerGetBit(AWTO_R_DVC_GAIN_DONE, AWTO_F_DVC_GAIN_DONE_DVC_DONE) == 0) && (ucPolls"): ("A", "DVC_GAIN_DONE poll, <= AWTO_DVC_RAMP_POLLS x ScalerTimerDelayXms(AWTO_DVC_RAMP_POLL_MS)", "no", "OK", "Timer2 ms; 2 ms = 1.25 x the 1.4 ms ramp worst case (docs/audio.md)"),
    ("testcmd.c", "while(ucH != TH2);"): ("C", "re-read of Timer2 high byte, at most 2 passes (rollover between the two reads)", "no", "NOCLOCK", "test op; bounded by the counter, not a wait"),
    ("testcmd.c", "while((TF2 == 0) && (usSpin > 0))"): ("C", "wait for Timer2 overflow, bound AWTO_CLK_TICK_SPIN passes", "yes", "SCALES-BENIGN",
                                                       "clock-sweep test op: the bound only ends a dead timer; the caller reports the tick missing; production unaffected"),
    ("testcmd.c", "while(((MCU_FFF3_SCA_INF_CONTROL & _BIT3) != 0) && (--ucLeft > 0))"): ("C", "burst-write restart, at most AWTO_OSW_BURST_RESTARTS passes, each ended by the hardware", "no", "NOCLOCK",
                                                                                          "OSD write-sweep test op: the hardware ends the burst; the restart count is reported to the host"),
}
BUDGET_TSV = ROOT / "docs/delay-budget.tsv"
BUDGET_COLS = ["function", "context", "budget_us", "extra_us", "reason", "review"]
DEFAULT_BUDGET_US = {"isr": 100, "masked": 100, "main": 1000}      # per function (isr path: per handler root); masked = clears EX0 / EA in its body
MASKED_RE = re.compile(r"\b(?:EX0|EA)\s*=\s*(?:0|_FALSE|_DISABLE)\b")
WAIT_KINDS_MS = ("delay_ms", "poll", "wait_event")
PARAM_D = re.compile(r"PANEL|VCCK|DDR_POWER|DEPOP|HPD|ZCD|AUX_REPLY|_POWER_OFF|WAITING_FOR_PANEL")
PARAM_E = re.compile(r"AWTO|OSD_TIMEOUT|DDCCI_TIMEOUT|SEARCH_TIME|WAIT_TIME_TO_ACTIVE|_SOURCE_")


def say(s):
    _log_line(s, LOG, stamp_stdout=False)


def tree_matches_image(tree: Path, mapp: Path) -> bool:
    """The listing tree (tmp/sdcc-port) must be the image's own build: the inventory reads the tree's .rst with the image's --map,
    so a tree built with different -D flags folds its extra (static) functions' sites into the preceding map symbol -> false sites,
    false budget / masked-section hits (awto-ddc #365/#392 merge: a leftover hwtest tree did exactly this). fwimage freezes the
    build's bank layout next to the image (scripts/fwimage.py); the tree keeps the live one. Equal layout = same build. Only --check
    needs this; --write regenerates against whatever tree is present on purpose."""
    live = tree / "tmp/sdcc-port/bank_layout.new.tsv"
    frozen = mapp.parent / (mapp.name[:-4] + ".bank_layout.tsv")       # <stem>-be.map -> <stem>-be.bank_layout.tsv
    if not live.is_file() or not frozen.is_file():
        say(f"  info bank-layout match skipped (missing {live if not live.is_file() else frozen}); tree/image correspondence unchecked")
        return True
    if live.read_bytes() == frozen.read_bytes():
        return True
    say(f"  FAIL listing tree {tree}/tmp/sdcc-port is not {mapp.name}'s build: {live.name} != the image's frozen {frozen.name}. "
        f"The .rst was built with different -D flags than the image (a stale / variant tmp/sdcc-port); its sites would misattribute. "
        f"Rebuild the tree for THIS image (./dev.py build with the image's flags, or ./dev.py gate which rebuilds the base).")
    return False


# ---------------------------------------------------------------- the loop-count formula (python twin of AWTO_DELAY_CNT, tied to the header text)
def header_consts():
    t = (ROOT / "fw/sdk/Kernel/Scaler/ScalerCommonFunction/Header/ScalerCommonPLLInclude.h").read_text()
    g = lambda n: int(re.search(rf"#define\s+{n}\s+(\d+)UL", t).group(1))
    return g("AWTO_DELAY_CLK_PER_CNT"), g("AWTO_DELAY5US_OVH_CLK"), g("AWTO_DELAYXUS_OVH_CLK")


def delay_cnt(khz: int, t_us: int, ovh: int) -> int:
    per, _, _ = header_consts()
    return (khz * t_us + 1000 * (per - 1 - ovh)) // (1000 * per)


def counts(khz: int):
    _, o5, ox = header_consts()
    return delay_cnt(khz, 5, o5), delay_cnt(khz, 4, ox)


def clock_states():
    """(name, kHz) per clock state as the SDK constants give it: M2PLL = 350791 / (flash div x MCU div), XTAL 14318, IOSC 28000 / PS dividers."""
    return [("M2PLL 350.8 (default)", 350791), ("M2PLL 175.4", 350791 // 2), ("M2PLL 87.7 (stock)", 350791 // 4), ("XTAL 14.318", 14318), ("IOSC 28", 28000)]


# ---------------------------------------------------------------- inventory
def norm(stmt: str) -> str:
    return re.sub(r"\s+", " ", stmt).strip()[:90]


def build_rows(tree: Path, mapp: Path):
    import types

    import delay_inventory as DI
    a = types.SimpleNamespace(build=str(tree), map=str(mapp))
    rows, _, _ = DI.build_rows(a)
    out, seen = [], collections.Counter()
    for r in rows:
        if r["linked"] != "yes":
            continue
        r = dict(r, file=os.path.relpath(r["file"], tree) if os.path.isabs(r["file"]) else r["file"])   # keys must not depend on the checkout path
        base = f"{r['file']}|{r['function']}|{r['kind']}|{norm(r['stmt'])}"
        seen[base] += 1
        out.append((f"{base}|{seen[base]}", r))
    return out


def classify(key: str, r: dict) -> dict:
    kind, name = r["kind"], r["file"].split("/")[-1]
    d = {"class": "", "derivation": "", "scales_2x": "no", "wall_87_7": "", "wall_350_8": "", "spec": "", "evidence": "[emu]", "verdict": "UNKNOWN", "note": ""}
    v = r["value"] if r["units"] in ("ms", "us") else ""
    if (name, norm(r["stmt"])) in HAND_STMT:
        c, der, sc, ver, note = HAND_STMT[(name, norm(r["stmt"]))]
        d.update({"class": c, "derivation": der, "scales_2x": sc, "verdict": ver, "note": note, "evidence": "[sdk-hypothesis]" if ver == "SCALES-BENIGN" else "[?]"})
        return d
    if (name, r["function"]) in HAND:
        c, der, sc, ver, note = HAND[(name, r["function"])]
        d.update({"class": c, "derivation": der, "scales_2x": sc, "verdict": ver, "note": note, "evidence": "[emu]" if ver == "OK" else "[?]"})
        if ver == "SCALES-BENIGN":
            d["evidence"] = "[sdk-hypothesis]"
        return d
    if kind in ("delay_ms", "poll", "wait_event", "timer_event"):
        d.update({"class": "A", "derivation": {"delay_ms": "Timer2 ms deadline (AwtoMs)", "poll": "Timer2 ticks (timeout + 1)", "wait_event": "Timer2 ticks (event bound + 1)",
                                               "timer_event": "Timer2 ms event"}[kind], "wall_87_7": v, "wall_350_8": v, "verdict": "OK",
                  "note": "Timer2 reload is compile time from the clock; sim gate: Timer2 ms per wall ms = 1 at both clocks"})
    elif kind == "delay_us":
        c5, cx, c3 = counts(350791 // 4), counts(350791 // 2), counts(350791)
        d.update({"class": "B", "derivation": "counted loop, count AWTO_DELAY_CNT per clock state", "wall_87_7": v, "wall_350_8": v, "verdict": "OK",
                  "note": f"counts 5us/4us: 350.8 MHz {c3[0]}/{c3[1]}, 175.4 {cx[0]}/{cx[1]}, 87.7 {c5[0]}/{c5[1]}; hot loop >= nominal in the sim at every clock"})
    elif kind == "param":
        cls = "D" if PARAM_D.search(r["stmt"]) else "E" if PARAM_E.search(r["stmt"]) else "A"
        d.update({"class": cls, "derivation": "named ms constant, run on Timer2", "wall_87_7": v, "wall_350_8": v, "verdict": "OK", "note": "value and source: docs/delays.md"})
    elif kind in ("status_loop", "busy_loop", "nop"):
        d.update({"class": "C", "verdict": "UNKNOWN", "note": "no hand verdict in delay_audit.HAND: classify it"})
    return d


def our_constants():
    """Class E: #define ..._MS style constants in our own code (fw/, not the SDK)."""
    pat = re.compile(r"^\s*#define\s+(\w*(?:_MS|_SEC|_TIME_MS|DEBOUNCE\w*|_TICK_MS|_PERIOD)\w*)\s+\(?(\d+)u?U?L?\b", re.MULTILINE)
    out = []
    for f in sorted((ROOT / "fw").rglob("*")):
        if f.suffix not in (".c", ".h", ".inc") or any(x in f.parts for x in ("sdk", "sdk-parked", "third_party", "tests", "simtests")):
            continue
        for m in pat.finditer(f.read_text(errors="replace")):
            if m.group(1).startswith(("SET_ID_", "AP_")):
                continue
            ln = f.read_text(errors="replace")[:m.start()].count("\n") + 1
            out.append((f"{f.relative_to(ROOT)}|-|const|{m.group(1)}|1", {"file": str(f.relative_to(ROOT)), "line": ln, "function": "-", "kind": "const", "value": m.group(2),
                                                                           "units": "ms", "stmt": m.group(1)}))
    return out


def rows_all(tree, mapp):
    rr = build_rows(tree, mapp)
    for k, r in our_constants():
        rr.append((k, r))
    return rr


def load_tsv(path=TSV):
    if not path.exists():
        return {}
    return {r["key"]: r for r in csv.DictReader(path.open(), delimiter="\t")}


def load_all(variant=""):
    """Main rows + the variant's extra rows."""
    return {**load_tsv(VARIANT_TSV[variant]), **load_tsv()} if variant else load_tsv()


def write(tree, mapp, variant=""):
    base = load_tsv()
    dst = VARIANT_TSV[variant] if variant else TSV
    old = load_tsv(dst)
    out = []
    nxt = max((int(r["id"][1:]) for r in {**base, **old}.values()), default=0) + 1       # ids of existing rows stay; new rows append
    for k, r in rows_all(tree, mapp):
        if variant and k in base:                                            # the main file already holds it
            continue
        if k in old:
            i = int(old[k]["id"][1:])
        else:
            i, nxt = nxt, nxt + 1
        if r["kind"] == "const":
            d = {"class": "E", "derivation": "AwtoMs() deadline / pass budget in Timer2 ms", "scales_2x": "no", "wall_87_7": r["value"], "wall_350_8": r["value"], "spec": "ours",
                 "evidence": "[emu]", "verdict": "OK", "note": ""}
        else:
            d = classify(k, r)
        row = {"key": k, "id": f"W{i:04d}", "file": r["file"], "line": r["line"], "function": r["function"], "kind": r["kind"], "value": r.get("value", ""),
               "unit": r.get("units", ""), "stmt": norm(r["stmt"]), **d}
        if k in old and old[k]["verdict"] not in ("UNKNOWN", ""):            # hand-reviewed columns survive a regeneration
            for c in ("class", "derivation", "scales_2x", "spec", "evidence", "verdict", "note"):
                row[c] = old[k][c]
        out.append(row)
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open("w", newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    summary(out)
    say(f"wrote {dst} ({len(out)} rows)")
    return 0


def summary(rows):
    c = collections.Counter((r["class"], r["verdict"]) for r in rows)
    for (cl, ver), n in sorted(c.items()):
        say(f"  class {cl or '-'} {ver}: {n}")


def check(tree, mapp, variant=""):
    if not tree_matches_image(Path(tree), Path(mapp)):      # also guards the delay_sim.py --audit caller; main() short-circuits before here
        return 1
    old = load_all(variant)
    rr = rows_all(tree, mapp)
    keys = {k for k, _ in rr}
    new = [k for k in keys if k not in old]
    stale = [k for k in old if k not in keys]
    bad = [k for k, r in old.items() if r["verdict"] in ("FIX", "UNKNOWN", "")]
    fails = 0
    for n, (ok, what, det) in enumerate([
        (not new, f"{len(rr)} linked delay sites, none missing from docs/delay-audit.tsv{'' if not variant else ' / delay-audit-' + variant + '.tsv'}", "; ".join(sorted(new)[:5])),
        (not bad, "no inventory row with verdict FIX / UNKNOWN", "; ".join(sorted(bad)[:5])),
    ]):
        say(f"  {'PASS' if ok else 'FAIL'} {what}{(': ' + det) if det else ''}")
        fails += 0 if ok else 1
    if stale:
        say(f"  info {len(stale)} TSV rows no longer linked (run --write to drop): {'; '.join(sorted(stale)[:3])}")
    # formula: >= nominal at the clock it is derived for, at every state
    per, o5, ox = header_consts()
    for name, khz in clock_states():
        c5, cx = counts(khz)
        w5, wx = (per * c5 + o5) * 1000.0 / khz, (per * cx + ox) * 1000.0 / khz
        ok = w5 >= 5.0 and wx >= 4.0 and w5 <= 5.0 + 2 * per * 1000.0 / khz and wx <= 4.0 + 2 * per * 1000.0 / khz
        say(f"  {'PASS' if ok else 'FAIL'} loop counts {name} MHz: DELAY_5US {c5} -> {w5:.2f} us (5), base 4 us {cx} -> {wx:.2f} us (4)")
        fails += 0 if ok else 1
    return 1 if fails else 0


# ---------------------------------------------------------------- blocking budget (docs/delay-budget.tsv)
def wait_us(r: dict) -> float:
    """worst case of one row in us: micro-delays as written, ms waits / poll timeouts / event bounds at their bound, others 0 (non-blocking or not a wait)"""
    try:
        v = float(r["value"])
    except (TypeError, ValueError):
        return 0.0
    if r["kind"] in WAIT_KINDS_MS or (r["kind"] == "status_loop" and r["units"] == "ms"):
        return v * 1000.0
    if r["kind"] == "delay_us":
        return v
    return 0.0


def load_budget() -> dict:
    if not BUDGET_TSV.exists():
        return {}
    return {(r["function"], r["context"]): r for r in csv.DictReader(BUDGET_TSV.open(), delimiter="\t") if not r["function"].startswith("#")}


def blocking(tree: Path, mapp: Path) -> list:
    """per function: own blocking (sum of its wait rows, branch-unaware upper bound) + declared extras, context, and per ISR handler root the sum over its call tree.
    [{function, context, own_us, extra_us, total_us, rows, loop_rows, variable}]"""
    import types

    import delay_inventory as DI
    rows, fns, g = DI.build_rows(types.SimpleNamespace(build=str(tree), map=str(mapp)))
    extra = {k[0]: float(v["extra_us"] or 0) for k, v in load_budget().items() if v["extra_us"]}
    per = collections.defaultdict(lambda: {"own": 0.0, "rows": 0, "loops": 0, "variable": 0, "ctx": ""})
    for r in rows:
        if r["linked"] != "yes" or r["reachable"] != "yes":
            continue
        e = per[r["function"]]
        e["ctx"] = e["ctx"] or r["ctx_all"]
        w = wait_us(r)
        if r["kind"] in WAIT_KINDS_MS + ("delay_us",) and r["value"] in ("variable", "", None):
            e["variable"] += 1
        if w:
            e["own"] += w
            e["rows"] += 1
            e["loops"] += r["in_loop"] == "yes"
    out = []
    masked = {n[1:] for n, f in fns.items() if any(MASKED_RE.search(t) for _, _, t, _ in f.stmts)}
    for name in sorted(set(per) | set(extra)):
        e = per[name]
        ctx = "isr" if "isr" in e["ctx"].split(",") else "masked" if name in masked else "main"
        out.append({"function": name, "context": ctx, "own_us": e["own"], "extra_us": extra.get(name, 0.0), "total_us": e["own"] + extra.get(name, 0.0),
                    "rows": e["rows"], "loop_rows": e["loops"], "variable": e["variable"]})
    own = {o["function"]: o["total_us"] for o in out}
    for n, f in sorted(fns.items()):
        if f.reti:                                                       # handler root: sum over everything it can call (union, branch-unaware)
            tree_us = sum(own.get(c[1:], 0.0) for c in DI.reach(g, [n]))
            out.append({"function": n[1:], "context": "isr-path", "own_us": tree_us, "extra_us": 0.0, "total_us": tree_us, "rows": 0, "loop_rows": 0, "variable": 0})
    return out


def check_budget(tree: Path, mapp: Path) -> int:
    allow = load_budget()
    bad, unused = [], set(allow)
    for b in blocking(tree, mapp):
        key = (b["function"], b["context"] if b["context"] != "isr" else "isr")
        cap = DEFAULT_BUDGET_US.get(b["context"], DEFAULT_BUDGET_US["isr"])
        a = allow.get(key)
        if a:
            unused.discard(key)
            cap = float(a["budget_us"])
            if not a["reason"].strip():
                bad.append(f"{b['function']} ({b['context']}): allow row without a reason")
        if round(b["total_us"]) > cap:
            bad.append(f"{b['function']} ({b['context']}) {b['total_us']:.0f} us > budget {cap:.0f} us ({b['rows']} waits)")
    for k in sorted(unused):
        if allow[k]["context"] != "isr-path":
            say(f"  info budget row for {k[0]} ({k[1]}) matches no linked function with waits (run --write-budget to drop)")
    ok = not bad
    say(f"  {'PASS' if ok else 'FAIL'} blocking budget (isr / masked {DEFAULT_BUDGET_US['isr']} us, main {DEFAULT_BUDGET_US['main']} us, docs/delay-budget.tsv): "
        f"{len(bad)} over{(': ' + '; '.join(bad[:6])) if bad else ''}")
    return 0 if ok else 1


def write_budget(tree: Path, mapp: Path) -> int:
    """add a row (budget = today's worst case, review = unreviewed) for every function over its default; hand rows and their reasons are kept"""
    allow = load_budget()
    rows = {k: dict(v) for k, v in allow.items()}
    for b in blocking(tree, mapp):
        cap = DEFAULT_BUDGET_US.get(b["context"], DEFAULT_BUDGET_US["isr"])
        key = (b["function"], b["context"])
        if b["total_us"] > cap and key not in rows:
            rows[key] = {"function": b["function"], "context": b["context"], "budget_us": f"{b['total_us']:.0f}", "extra_us": f"{b['extra_us']:.0f}" if b["extra_us"] else "",
                         "reason": f"{b['rows']} wait(s) of the SDK / our sequence at their bound; value source docs/delays.md", "review": "unreviewed"}
    with BUDGET_TSV.open("w", newline="") as f:
        w = csv.DictWriter(f, BUDGET_COLS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows[k] for k in sorted(rows))
    say(f"wrote {BUDGET_TSV} ({len(rows)} rows, {sum(r['review'] == 'unreviewed' for r in rows.values())} unreviewed)")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--counts", action="store_true")
    ap.add_argument("--write-budget", action="store_true", help="add docs/delay-budget.tsv rows for functions over their default budget")
    ap.add_argument("--tree", type=Path, default=ROOT)
    ap.add_argument("--map", type=Path)
    ap.add_argument("--variant", choices=sorted(VARIANT_TSV), default="")
    a = ap.parse_args()
    if a.counts:
        for name, khz in clock_states():
            say(f"{name} MHz: DELAY_5US count {counts(khz)[0]}, 4 us base count {counts(khz)[1]}")
        return 0
    mapp = a.map or max((a.tree / "tmp/fw").glob("*-be.map"), key=lambda p: p.stat().st_mtime)
    say(f"delay_audit tree {a.tree} map {mapp.name}")
    if a.write_budget:
        return write_budget(a.tree, mapp)
    if a.write:
        return write(a.tree, mapp, a.variant)
    if not tree_matches_image(a.tree, mapp):     # a mismatched tree makes every result below meaningless (false sites); fail with the cause, not the symptom
        return 1
    if a.variant in BLOCKS_ON_PURPOSE:
        return check(a.tree, mapp, a.variant)
    import irq_masks
    return check(a.tree, mapp, a.variant) | check_budget(a.tree, mapp) | irq_masks.check(a.tree, mapp)      # masked sections: docs/irq-masks.tsv


if __name__ == "__main__":
    sys.exit(main())
