#!/usr/bin/env python3
"""Typed inventory of every delay / wait / poll / timeout in the linked firmware, and the gate that keeps it complete (docs/delay-audit.md).

usage: delay_audit.py --write [--tree DIR] [--map MAP]   regenerate docs/delay-audit.tsv from the tree's last build (hand columns kept by key)
       delay_audit.py --check [--tree DIR] [--map MAP]   FAIL on a linked site that is not in the TSV, a TSV verdict FIX / UNKNOWN, a stale count formula
       delay_audit.py --counts                            the loop-count formula (AWTO_DELAY_CNT) at every clock state (350.8 default, 175.4, 87.7, XTAL, IOSC), from the header text
Source of the sites: scripts/delay_inventory.py (post-link: the SDCC listing of the tree's build, so "linked" is exact).
Classes: A timer wait (Timer2 ms) | B micro-delay (DELAY_5US / DELAY_XUS loop count, per clock state) | C spin loop / counted loop |
  D hardware-spec minimum (datasheet value - 10 %) | E our own timing constant.
Verdicts: OK (wall time equal at 87.7 and 175.4 MHz by construction + sim gate) | NOCLOCK (hardware-bound, no timed bound) | SCALES-BENIGN (halves at 2x, harmless: stated why)
  | FIXED (was wrong at 2x, fixed: note) | FIX | UNKNOWN (both fail the gate).
Key = file | function | kind | normalised statement | ordinal (no line numbers: lines move). Log: ./tmp/logs/delay_audit.log
"""
import argparse
import collections
import csv
import os
import re
import sys
from pathlib import Path

import isostamp

sys.path.insert(0, str(Path(__file__).resolve().parent))
ROOT = Path(__file__).resolve().parents[1]
TSV = ROOT / "docs/delay-audit.tsv"
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
    ("RL6449_Series_Power.c", "ScalerPowerGroupD0PowerCut"): ("B", "50 passes x DELAY_5US (250 us bound)", "no", "OK", "as ADI"),
    ("RL6449_Series_Power.c", "ScalerPowerGroupD1PowerCut"): ("B", "50 passes x DELAY_5US (250 us bound)", "no", "OK", "as ADI"),
    ("RL6449_Series_Power.c", "ScalerPowerGroupD2PowerCut"): ("B", "50 passes x DELAY_5US (250 us bound)", "no", "OK", "as ADI"),
    ("RL6449_Series_Power.c", "ScalerPowerGroupD3PowerCut"): ("B", "50 passes x DELAY_5US (250 us bound)", "no", "OK", "as ADI"),
    ("ScalerCommonDebug.c", "ScalerDebugMessage"): ("C", "5 reads of the debug I2C FIFO count, no delay in the pass", "yes", "SCALES-BENIGN",
                                                   "a give-up after ~5 reads (about 5 us at 87.7 MHz, half at 175.4), not a wait: the host drains at I2C rate; debug-message path, not our log"),
    ("ScalerCommonDebug.c", "ScalerDebug"): ("C", "<= 5 reads (counted) or the host release flag", "yes", "SCALES-BENIGN", "as ScalerDebugMessage; ucHalt = host release, no timed bound"),
    ("ScalerCommonDebug.c", "ScalerDebugIntProc_EXINT1"): ("C", "I2C status bit, no bound", "no", "NOCLOCK", "host I2C rate"),
    ("ScalerCommonTimerFunction.c", "ScalerTimerPollingFlagProc"): ("A", "timeout + 1 Timer2 ticks", "no", "OK", "Timer2 ticks"),
    ("ScalerAudio.c", "ScalerAudioDVCVolumeMute"): ("A", "<= _DVC_VOLUME_MUTE_TIMER x ScalerTimerDelayXms(1)", "no", "OK", "Timer2 ms"),
    ("ScalerDisplayDPTx.c", "ScalerDisplayDPTx1LinkTraining"): ("C", "link-training state machine, each state has its own timed wait", "no", "NOCLOCK", "result flags; the waits inside are class A"),
    ("ScalerDisplayDPTx.c", "ScalerDisplayDPTx1AuxRead"): ("C", "7 retries, each ended by the AUX hardware reply timeout", "no", "NOCLOCK", "retry count, the time is the AUX hardware's"),
    ("ScalerIDomain.c", "ScalerIDomainVgipIVDelayIVstStepAdjust"): ("C", "<= counter passes, each a double-buffer apply poll", "no", "NOCLOCK", "polls the apply flag (class A inside)"),
    ("ScalerTMDSRx2_SeptPhy.c", "ScalerTMDSRx2HdmiWaitDeepColorPllLock"): ("A", "lock polls with ScalerTimerDelayXms in the pass", "no", "OK", "Timer2 ms"),
    ("ScalerTMDSRx3_SeptPhy.c", "ScalerTMDSRx3HdmiWaitDeepColorPllLock"): ("A", "lock polls with ScalerTimerDelayXms in the pass", "no", "OK", "Timer2 ms"),
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
PARAM_D = re.compile(r"PANEL|VCCK|DDR_POWER|DEPOP|HPD|ZCD|AUX_REPLY|_POWER_OFF|WAITING_FOR_PANEL")
PARAM_E = re.compile(r"AWTO|OSD_TIMEOUT|DDCCI_TIMEOUT|SEARCH_TIME|WAIT_TIME_TO_ACTIVE|_SOURCE_")


def say(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(isostamp.now() + " " + s + "\n")
    print(s, flush=True)


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


def load_tsv():
    if not TSV.exists():
        return {}
    return {r["key"]: r for r in csv.DictReader(TSV.open(), delimiter="\t")}


def write(tree, mapp):
    old = load_tsv()
    out = []
    nxt = max((int(r["id"][1:]) for r in old.values()), default=0) + 1       # ids of existing rows stay; new rows append
    for k, r in rows_all(tree, mapp):
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
    TSV.parent.mkdir(parents=True, exist_ok=True)
    with TSV.open("w", newline="") as f:
        w = csv.DictWriter(f, COLS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(out)
    summary(out)
    say(f"wrote {TSV} ({len(out)} rows)")
    return 0


def summary(rows):
    c = collections.Counter((r["class"], r["verdict"]) for r in rows)
    for (cl, ver), n in sorted(c.items()):
        say(f"  class {cl or '-'} {ver}: {n}")


def check(tree, mapp):
    old = load_tsv()
    rr = rows_all(tree, mapp)
    keys = {k for k, _ in rr}
    new = [k for k in keys if k not in old]
    stale = [k for k in old if k not in keys]
    bad = [k for k, r in old.items() if r["verdict"] in ("FIX", "UNKNOWN", "")]
    fails = 0
    for n, (ok, what, det) in enumerate([
        (not new, f"{len(rr)} linked delay sites, none missing from docs/delay-audit.tsv", "; ".join(sorted(new)[:5])),
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


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--counts", action="store_true")
    ap.add_argument("--tree", type=Path, default=ROOT)
    ap.add_argument("--map", type=Path)
    a = ap.parse_args()
    if a.counts:
        for name, khz in clock_states():
            say(f"{name} MHz: DELAY_5US count {counts(khz)[0]}, 4 us base count {counts(khz)[1]}")
        return 0
    mapp = a.map or sorted((a.tree / "tmp/fw").glob("*-be.map"), key=lambda p: p.stat().st_mtime)[-1]
    say(f"delay_audit tree {a.tree} map {mapp.name}")
    return write(a.tree, mapp) if a.write else check(a.tree, mapp)


if __name__ == "__main__":
    sys.exit(main())
