#!/usr/bin/env python3
"""Worst-case hardware stack depth for the banked SDCC firmware (main tree + deepest ISR on top).

usage: fw_stack.py [--asm DIR] [--limit BYTES]
  --asm   banked asm tree (default tmp/sdcc-port/asm_bank, output of sdcc_bank.py)
  --limit fail if main + worst ISR exceeds this (default: stack_bytes from tmp/fw/*/build.json if given)
Model (awto-ddc#8): lcall = 2 B; call via __bs_<fn> stub = 2 (ret) + 2 (restore entry) persistent, +2 transient
inside __bs_call (fw/sdcc/bank.asm); per fn: peak of a linear push/pop balance (pushes live across its calls);
ISR entry = 2 (PC) + its pushes. Indirect calls (__sdcc_call_dptr) -> any address-taken fn (stub, 5 B).
Recursion/cycles reported, not followed. Log: tmp/logs/fw_stack.log
"""
import argparse, json, re, sys, time
import isostamp  # noqa: E402
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402

ROOT = repo_root()
FUNC = re.compile(r"^;\s+function (\w+)\s*$")
CALL = re.compile(r"^\s+(lcall|ljmp)\s+(\w+)\s*$")
TRAMP = 2                                       # caller-bank restore entry kept while the callee runs (bank.asm)
TRANSIENT = 2                                   # target address inside __bs_call, once at the deepest point
ISR_ENTRY = 2                                   # PC pushed by the interrupt
HIGH = ("_SysEXINT0", "_SysTimerIntProc2")      # IP 0x81 / 0xA0: each is high in one IP state


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asm", default=str(ROOT / "tmp/sdcc-port/asm_bank"))
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (ROOT / "tmp/logs/fw_stack.log").open("a")
    calls, pushes, isr, addr, live = defaultdict(list), defaultdict(int), set(), set(), {}
    for p in sorted(Path(a.asm).glob("*.asm")):
        cur = None
        for l in p.read_text(errors="replace").split("\n"):
            m = FUNC.match(l)
            if m:
                cur = "_" + m.group(1); continue
            if l.startswith("__bs_") and l.endswith(":"):
                cur = None; continue                     # stub bodies: modelled by TRAMP
            if not cur or l.lstrip().startswith(";"):
                continue
            c = CALL.match(l)
            if c:
                t = c.group(2)
                if t.startswith("__bs_") and t not in ("__bs_call", "__bs_ret"):
                    calls[cur].append((t[4:], TRAMP + (2 if c.group(1) == "lcall" else 0)))
                elif t in ("__sdcc_call_dptr", "sdcc_call_dptr"):          # <= 4.6 / trunk name
                    calls[cur].append(("*indirect*", 2 + TRAMP))
                elif t == "sdcc_atomic_maybe_rollback":
                    isr.add(cur)
                else:
                    calls[cur].append((t, 2 if c.group(1) == "lcall" else 0))
                continue
            if re.match(r"^\s+push\s", l):
                live[cur] = live.get(cur, 0) + 1
                pushes[cur] = max(pushes[cur], live[cur])
            elif re.match(r"^\s+pop\s", l):
                live[cur] = max(0, live.get(cur, 0) - 1)
            if re.match(r"^\s+reti\b", l):
                isr.add(cur)
            for s in re.findall(r"#\(?(__bs_\w+)", l):
                addr.add(s[4:])
    memo, cyc = {}, set()

    def depth(f, stack=()):
        if f in memo:
            return memo[f]
        if f in stack:
            cyc.add(f); return 0, []                     # #174: was a bare 0
        best, path = 0, []
        targets = calls.get(f, [])
        for t, cost in targets:
            if t == "*indirect*":
                for g in addr:
                    d, p = depth(g, stack + (f,))
                    if cost + d > best:
                        best, path = cost + d, [f"{g}(+{cost})"] + p
                continue
            d, p = depth(t, stack + (f,))
            if cost + d > best:
                best, path = cost + d, [f"{t}(+{cost},p{pushes.get(t, 0)})"] + p
        memo[f] = (pushes.get(f, 0) + best, path)
        return memo[f]

    main_d, main_p = depth("_main")
    isr_d = {f: depth(f) for f in isr}
    worst_isr = max(isr_d.items(), key=lambda kv: kv[1][0]) if isr_d else ("-", (0, []))
    # two levels: in each IP state one of HIGH is high and may interrupt any other (low) handler (sdcc_isr_libs PRIO_CLASS)
    nest = max([(isr_d[h][0] + max([isr_d[l][0] for l in isr_d if l != h] or [0]) + ISR_ENTRY, h)
                for h in HIGH if h in isr_d] or [(worst_isr[1][0], worst_isr[0])])
    total = main_d + ISR_ENTRY + nest[0] + TRANSIENT       # nested interrupts at the deepest main point, mid-trampoline
    res = {"main": main_d, "main_path": main_p[:40], "isr": {k: v[0] for k, v in isr_d.items()},
           "worst_isr": worst_isr[0], "worst_isr_path": worst_isr[1][1][:40], "nested_high": nest[1],
           "isr_nested": nest[0], "total": total,
           "cycles": sorted(cyc)[:20], "limit": a.limit}
    txt = json.dumps(res, indent=1)
    print(txt); log.write(f"{isostamp.now()}\n{txt}\n")
    return 1 if a.limit and total > a.limit else 0


if __name__ == "__main__":
    sys.exit(main())
