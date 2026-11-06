#!/usr/bin/env python3
"""Cycle profile of the banked firmware main loop in ucsim (offline, #11).

usage: fw_profile.py BIN MAP [--passes 12] [--top 15] [--json OUT]
  Boots like fw_sim --boot-check (stage 8), then single-steps `--passes` main-loop passes (heartbeat writes) and
  accounts every instruction's ticks (1 tick = 1 oscillator clock, 12 per machine cycle; reported as machine cycles) to:
  exclusive / inclusive per function (shadow call stack; LCALL/ACALL/RET/RETI + the banked-call trampoline),
  stub overhead (per-target stub, __bs_call, rtab+__bs_ret), counts of stub entries and interrupts per pass.
  Peripherals are not modelled (XDATA reads return RAM): hardware waits (polls, timer delays) differ from the sim.
Log: tmp/logs/fw_profile.log
"""
import argparse, bisect, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as F  # noqa: E402
import rtd_diag  # noqa: E402

BRANCH = {"LJMP", "AJMP", "SJMP", "JMP", "LCALL", "ACALL", "RET", "RETI", "JZ", "JNZ", "JC", "JNC", "JB", "JNB", "JBC",
          "CJNE", "DJNZ"}
HB = 0xF6D0 + 0x14          # diag block: u16 heartbeat (BE: high byte first)
LINE = re.compile(r"^0x([0-9a-f]+)\s+((?:[0-9a-f]{2} )+)\s*(\w+)", re.M)


def parse_syms(mp: str):
    allsym = {m.group(2): int(m.group(1), 16) for m in re.finditer(r"^C:\s+([0-9A-F]{8})\s+(\w+)", mp, re.M)}
    stubs = sorted((v, k) for k, v in allsym.items() if k.startswith("__bs_") and k not in (
        "__bs_call", "__bs_call_sw", "__bs_ret", "__bs_ret_sw"))
    return allsym, stubs


def boot(img, mapp, be, log):
    sym, where = F.parse_map(mapp.read_text(errors="replace"), img)
    flash = F.FlashPort(img)
    s = F.open_native(img, F.ROOT / "tmp/fwsim" / mapp.stem, log, flash, [])
    hb0 = None
    for _ in range(80):
        out = F.run_chunk(s, flash, 1_000_000)
        blk = F.read_diag(s)
        d = rtd_diag.decode(blk, be) if blk else None
        if d and d["stage"] >= 8:
            hb0 = d["hb"] if hb0 is None else hb0
            if (d["hb"] - hb0) & 0xFFFF >= 5:
                return s, sym, where
    raise RuntimeError("boot did not reach stage 8 + heartbeat")


def profile(binp: Path, mapp: Path, passes: int, be: bool, log):
    img = binp.read_bytes()
    mp = mapp.read_text(errors="replace")
    s, sym, where = boot(img, mapp, be, log)
    allsym, stubs = parse_syms(mp)
    stub_starts = [v for v, _ in stubs]
    ssize = 9 if stubs and img[stubs[0][0]] == 0x78 else 6      # 9 B mov/mov/mov/ljmp stub or 6 B lcall + data
    stub_name = dict(stubs)
    call, call_sw, ret, ret_sw = (allsym[k] for k in ("__bs_call", "__bs_call_sw", "__bs_ret", "__bs_ret_sw"))
    rtab = (ret - 64, ret)

    def region(pc):
        """'' or the trampoline part this pc belongs to"""
        if call <= pc < call_sw + 8:
            return "__bs_call"
        if rtab[0] <= pc < ret_sw + 8:
            return "__bs_ret+rtab"
        i = bisect.bisect_right(stub_starts, pc) - 1
        if i >= 0 and pc < stub_starts[i] + ssize:
            return "stub"
        return ""

    s.send("delete")
    s.send(f"break xram w 0x{HB + (1 if be else 0):x}")
    bank = F.cur_bank(s)

    import os, select
    queue = []                                   # parsed steps not yet consumed
    raw = [b""]
    BATCH = 3000                                 # step commands pipelined per write: one at a time costs ~100 ms each

    def refill():
        s.p.stdin.write(("step 1\n" * BATCH).encode()); s.p.stdin.flush()
        got = 0
        while got < BATCH:
            r, _, _ = select.select([s.p.stdout], [], [], 20)
            if not r:
                raise RuntimeError("ucsim stopped answering")
            raw[0] += os.read(s.p.stdout.fileno(), 1 << 20)
            got = len(re.findall(rb"\nF 0x[0-9a-f]+", raw[0]))
        txt = raw[0].decode(errors="replace")
        blocks = re.split(r"\nStop at 0x", txt)[1:]
        tail = ""
        for blk in blocks:
            m = LINE.search(blk)
            if not m or "\nF 0x" not in blk:
                continue
            tk = re.search(r"stepped (\d+) ticks|Simulated (\d+) ticks", blk)
            acc = re.search(r"ACC= 0x([0-9a-f]{2})", blk)
            queue.append(((int(m.group(1), 16), m.group(3).upper(), len(m.group(2).split())),
                          int(tk.group(1) or tk.group(2)) if tk else 0, "Event break" in blk,
                          int(acc.group(1), 16) if acc else 0))
        raw[0] = b""

    def step():
        if not queue:
            refill()
        return queue.pop(0)

    cur = step()[0]
    excl, incl, reg = Counter(), Counter(), Counter()
    cnt = Counter()
    xcalls, calls, edges = Counter(), Counter(), Counter()   # edges: every call caller -> callee fn, direct or via stub
    r2_ok = lambda a: region(a) == ""          # direct call to a real function (stub entries are counted at the trampoline)
    per_pass = []
    stackf = ["_main"]               # shadow call stack of names (the sampled window starts inside main()'s loop)
    acc = defaultdict(int)           # per-pass accumulators
    hbs, t_pass, n_instr = 0, 0, 0
    pending_total = 0
    passes_done = -1                 # first hb event only marks the start
    while passes_done < passes:
        pc, mn, ln = cur
        nxt, ticks, ev, acc_v = step()
        npc = nxt[0] if nxt else -1
        name = None
        r = region(pc)
        sym_pc = where(bank, pc)
        if passes_done >= 0:
            n_instr += 1
            if mn in ("MOVC", "MOVX"):
                cnt[mn.lower()] += 1
            t_pass += ticks
            nm = r and f"[{r}]" or sym_pc
            if r == "stub":
                nm = "[stub] " + stub_name[stub_starts[bisect.bisect_right(stub_starts, pc) - 1]][5:]
            excl[nm] += ticks
            if r:
                reg[r] += ticks
            seen = set()
            for f in [*stackf, nm]:
                if f not in seen:
                    seen.add(f); incl[f] += ticks
        # control flow
        if mn in ("LCALL", "ACALL"):
            tgt = where(bank, npc)
            if passes_done >= 0 and r2_ok(npc):
                calls[tgt] += 1
            r2 = region(npc)
            stackf.append(f"[stub] {stub_name[npc][5:]}" if r2 == "stub" else tgt)
            if r2 == "stub":
                cnt["stub_entries"] += 1 if passes_done >= 0 else 0
                if passes_done >= 0:
                    xcalls[f"{sym_pc} -> {stub_name[npc][5:]}"] += 1
                    edges[f"{sym_pc} _{stub_name[npc][5:]}"] += 1
            else:
                cnt["direct_calls"] += 1 if passes_done >= 0 else 0
                if passes_done >= 0 and r2_ok(npc):
                    edges[f"{sym_pc} {tgt}"] += 1
        elif mn == "RET":
            if call_sw <= pc < call_sw + 8:
                if passes_done >= 0:
                    calls[where(bank, npc)] += 1
                if stackf:
                    stackf[-1] = where(bank, npc)           # trampoline jumps to the target: top frame becomes the target
            elif rtab[0] <= npc < rtab[1]:
                pass                                         # callee returns into the restore entry
            elif len(stackf) > 1:                            # the base frame (_main) is never popped: the window starts in a callee
                stackf.pop()
        elif mn == "RETI":
            if len(stackf) > 1:
                stackf.pop()
        elif mn not in BRANCH and nxt and npc != pc + ln:    # interrupt entry
            stackf.append(f"ISR@{npc:02x}")
            if passes_done >= 0:
                cnt[f"irq_{npc:02x}"] += 1
        if nxt and npc in (call_sw, ret_sw):
            bank = acc_v & 0x0F                               # ACC = new bank at the movx just executed
        if ev:
            passes_done += 1
            if passes_done > 0:
                per_pass.append(t_pass); cnt["passes"] += 1
            t_pass = 0
            if passes_done == passes:
                break
        cur = nxt
    s.send("quit")
    n = max(len(per_pass), 1)
    return {"image": binp.name, "passes": n, "cycles_per_pass_list": [t // 12 for t in per_pass],
            "cycles_per_pass": sum(per_pass) / 12 / n, "instr_per_pass": n_instr / n,
            "excl": {k: v / 12 / n for k, v in excl.items()}, "incl": {k: v / 12 / n for k, v in incl.items()},
            "region": {k: v / 12 / n for k, v in reg.items()}, "calls": {k: v / n for k, v in calls.most_common(80)}, "xbank_calls": {k: v / n for k, v in xcalls.most_common(40)}, "edges": {k: v / n for k, v in edges.items()}, "counts": {k: v / n for k, v in cnt.items() if k != "passes"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bin"); ap.add_argument("map")
    ap.add_argument("--passes", type=int, default=12)
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--json")
    a = ap.parse_args()
    (F.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (F.ROOT / "tmp/logs/fw_profile.log").open("a", buffering=1)
    b, m = Path(a.bin), Path(a.map)
    r = profile(b, m, a.passes, "-be" in b.name, log)
    if a.json:
        Path(a.json).write_text(json.dumps(r, indent=1))
    print(f"{r['image']}: {r['cycles_per_pass']:.0f} machine cycles/pass over {r['passes']} passes, "
          f"{r['instr_per_pass']:.0f} instr/pass; per-pass {r['cycles_per_pass_list']}")
    wait = r["excl"].get("_ScalerTimerDelayXms", 0)
    print(f"work cycles/pass (total minus _ScalerTimerDelayXms spin {wait:.0f}): {r['cycles_per_pass'] - wait:.0f}")
    print("regions (cycles/pass):", {k: round(v) for k, v in r["region"].items()}, "counts/pass:",
          {k: round(v, 1) for k, v in r["counts"].items()})
    print("top cross-bank call edges (per pass):", {k: round(v, 1) for k, v in list(r["xbank_calls"].items())[:12]})
    print(f"{'excl':>9} {'incl':>9}  function")
    for k, v in sorted(r["excl"].items(), key=lambda kv: -kv[1])[:a.top]:
        print(f"{v:9.0f} {r['incl'].get(k, 0):9.0f}  {k}")


if __name__ == "__main__":
    main()
