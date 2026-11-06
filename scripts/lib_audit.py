#!/usr/bin/env python3
"""Size / hotness audit of the SDCC-compiled Realtek FunctionLib vs the vendor Keil build (awto-ddc#11).

usage: lib_audit.py [--min-score N]      (run after a full fw_build; reads the last build's artifacts)
Inputs : tmp/logs/fw_build.log ("lib: N/M modules selected" = linked lib modules), tmp/sdcc-port/asm_bank/*.rst
         (linked asm listing: address, bytes, cycles per instruction, `; function X` markers),
         ~/vendors/realtek/analysis/jxc-4k/bank<N>/disassembly.asm (old vendor firmware, Keil, Ghidra export).
Output : tmp/lib_audit.tsv, one row per linked lib function; tmp/logs/lib_audit.log
Columns: our bytes + static straight-line clocks (12 per machine cycle; listing units); call sites (raw, loop-weighted); ISR/main reachability;
         hot = est. relative calls per main pass (see below); vendor match (bank:addr, name, bytes) and ratio.
Hotness model (static, no profile): site weight = 8^(loop depth) (loop = backward branch span inside the caller);
  caller weight = 1 for main-reachable roots, ISR_W for ISR roots; hot(fn) = sum(site weight * caller hot),
  propagated over the call graph (cycles cut after DEPTH passes). Relative numbers only.
Vendor match: fingerprint = set of 16-bit `mov dptr,#imm` constants >= 0xF700 (scaler/MCU register window; same
  silicon family), score = |common| with ties by Jaccard; needs >= --min-score common constants (default 2).
  Functions with fewer register constants stay unmatched (marked '-'): pure RAM/arith helpers have no fingerprint.
"""
import argparse, bisect, re, sys, time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402

ROOT = repo_root()
VENDOR = Path.home() / "vendors/realtek/analysis/jxc-4k"
RST = ROOT / "tmp/sdcc-port/asm_bank"
ISR_W = 50          # relative ISR firing rate vs one main-loop pass: a timer/DDC ISR runs many times per pass
LOOP_W = 8          # assumed iterations per loop nesting level
DEPTH = 12          # propagation passes over the call graph
REGMIN = 0xF700
AMBIG_MAX = 3       # more equally-good vendor candidates than this = no match (shared register sets)
LOG = None

LINE = re.compile(r"^\s+([0-9A-F]{6})\s+((?:[0-9A-F]{2} ?)+)\s*\[\s*(\d+)\]\s+\d+\s+(.*)$")
FUNC = re.compile(r"^\s+\d+ ;\s+function (\w+)\s*$")
LABEL = re.compile(r"^\s+([0-9A-F]{6})\s+\d+ (\w+):")
BRANCH = re.compile(r"^(sjmp|ljmp|jz|jnz|jc|jnc|jb|jnb|jbc|cjne|djnz)\b")
CALL = re.compile(r"^(lcall|acall|ljmp|ajmp)\s+(\w+)\s*$")


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line); LOG.write(line + "\n"); LOG.flush()


class Fn:
    def __init__(self, name, mod):
        self.name, self.mod = name, mod
        self.bytes = self.cycles = 0
        self.start = None
        self.ins = []              # (addr, text, nbytes, raw bytes)
        self.labels = {}
        self.consts = set()
        self.isr = False


def parse_rst(path: Path):
    fns, cur = {}, None
    for l in path.read_text(errors="replace").split("\n"):
        m = FUNC.match(l)
        if m:
            cur = Fn("_" + m.group(1), path.stem); fns[cur.name] = cur
            continue
        if cur is None:
            continue
        m = LABEL.match(l)
        if m:
            cur.labels[m.group(2)] = int(m.group(1), 16)
            if m.group(2) == cur.name:
                cur.start = int(m.group(1), 16)
            continue
        m = LINE.match(l)
        if m:
            addr, bs, cyc, txt = int(m.group(1), 16), bytes.fromhex(m.group(2).replace(" ", "")), int(m.group(3)), m.group(4).strip()
            if addr < (cur.start or addr):          # CONST tables / next area: not code of this fn
                continue
            cur.bytes += len(bs); cur.cycles += cyc
            cur.ins.append((addr, txt, len(bs), bs))
            if bs[0] == 0x90 and len(bs) == 3 and int.from_bytes(bs[1:], "big") >= REGMIN:
                cur.consts.add(int.from_bytes(bs[1:], "big"))
            if txt.startswith("reti"):
                cur.isr = True
    return fns


def callee(t):
    return "_" + t[5:] if t.startswith("__bs_") else t


def loop_spans(f: Fn):
    sp = []
    for a, t, n, bs in f.ins:
        if BRANCH.match(t):
            tgt = t.split(",")[-1].strip().split()[-1]
            ta = f.labels.get(tgt)
            if ta is not None and ta <= a:
                sp.append((ta, a))
    return sp


def call_sites(f: Fn):
    sp = loop_spans(f)
    out = []
    for a, t, n, bs in f.ins:
        m = CALL.match(t)
        if m and m.group(2) != f.name:
            c = callee(m.group(2))
            if m.group(1) == "ljmp" and c in f.labels:
                continue
            depth = sum(1 for lo, hi in sp if lo <= a <= hi)
            out.append((c, LOOP_W ** depth))
    return out


def vendor_funcs():
    out = []
    for b in range(7):
        txt = (VENDOR / f"bank{b}/disassembly.asm").read_text(errors="replace").split("\n")
        cur, addrs = None, []
        for l in txt:
            if l.startswith("; ==== "):
                m = re.match(r"; ==== (\S+) @ CODE:([0-9a-f]+)", l)
                cur = {"bank": b, "name": m.group(1), "addr": int(m.group(2), 16), "consts": set(), "last": int(m.group(2), 16)}
                out.append(cur)
                continue
            m = re.match(r"CODE:([0-9a-f]{4}):\s+(.*)", l)
            if m and cur:
                cur["last"] = int(m.group(1), 16)
                mm = re.match(r"MOV DPTR,#0x([0-9a-f]+)", m.group(2))
                if mm and int(mm.group(1), 16) >= REGMIN:
                    cur["consts"].add(int(mm.group(1), 16))
    for b in range(7):
        fs = sorted((f for f in out if f["bank"] == b), key=lambda f: f["addr"])
        for i, f in enumerate(fs):
            nxt = fs[i + 1]["addr"] if i + 1 < len(fs) else 0x10000
            f["size"] = min(nxt - f["addr"], f["last"] - f["addr"] + 3)
    return out


def main():
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-score", type=int, default=2)
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/lib_audit.log").open("w")
    sel = [l for l in (ROOT / "tmp/logs/fw_build.log").read_text(errors="replace").split("\n") if " lib: " in l][-1]
    mods = [m.strip() for m in sel.split("selected:")[1].split(",")]
    log(f"{sel.split(' lib: ')[1].split(' selected')[0]} lib modules: {len(mods)} listed")
    allf = {}
    for r in sorted(RST.glob("*.rst")):
        allf.update(parse_rst(r))
    libf = {n: f for n, f in allf.items() if f.mod in mods}
    log(f"functions: {len(allf)} total, {len(libf)} in lib modules")
    # call graph
    sites = {n: call_sites(f) for n, f in allf.items()}
    nsites = defaultdict(int)
    for n, ss in sites.items():
        for c, w in ss:
            nsites[c] += 1
    root_w = {n: (ISR_W if f.isr else 0) for n, f in allf.items()}
    if "_main" in allf:
        root_w["_main"] = 1
    hot = dict(root_w)
    for _ in range(DEPTH):
        new = dict(root_w)
        for n, ss in sites.items():
            for c, w in ss:
                if c in allf and hot.get(n):
                    new[c] = new.get(c, 0) + w * hot[n]
        hot = new
    reach = {}
    for tag, roots in (("main", ["_main"]), ("isr", [n for n, f in allf.items() if f.isr])):
        seen, work = set(roots), list(roots)
        while work:
            n = work.pop()
            for c, _ in sites.get(n, []):
                if c in allf and c not in seen:
                    seen.add(c); work.append(c)
        reach[tag] = seen
    vf = vendor_funcs()
    log(f"vendor functions: {len(vf)}")
    rows = []
    for n, f in sorted(libf.items()):
        best, amb = None, 0
        if len(f.consts) >= 1:
            for v in vf:
                c = len(f.consts & v["consts"])
                if not c:
                    continue
                k = (c, c / len(f.consts | v["consts"]))
                if best is None or k > best[0]:
                    best, amb = (k, v), 1
                elif k == best[0]:
                    amb += 1
        ok = best and best[0][0] >= min(a.min_score, len(f.consts)) and amb <= AMBIG_MAX
        rows.append((f, ok and best[1], ok and best[0], amb))
    hdr = ["module", "func", "our_bytes", "our_clocks", "sites", "wsites", "isr", "main", "hot", "nconst",
           "vendor", "vendor_name", "vendor_bytes", "common", "jaccard", "ambig", "ratio", "cost"]
    outp = ROOT / "tmp/lib_audit.tsv"
    lines = ["\t".join(hdr)]
    for f, v, sc, amb in sorted(rows, key=lambda r: -hot.get(r[0].name, 0) * r[0].cycles):
        n = f.name
        ws = sum(w for ss in sites.values() for c, w in ss if c == n)
        lines.append("\t".join(map(str, [
            f.mod, n, f.bytes, f.cycles, nsites[n], ws, int(n in reach["isr"]), int(n in reach["main"]), hot.get(n, 0), len(f.consts),
            f"{v['bank']}:{v['addr']:04x}" if v else "-", v["name"] if v else "-", v["size"] if v else "-",
            sc[0] if sc else "-", f"{sc[1]:.2f}" if sc else "-", amb if sc else "-",
            f"{f.bytes / v['size']:.2f}" if v and v["size"] else "-", hot.get(n, 0) * f.cycles])))
    outp.write_text("\n".join(lines) + "\n")
    tot = sum(f.bytes for f in libf.values())
    log(f"wrote {outp}: {len(libf)} lib functions, {tot} B code; matched to vendor: {sum(1 for r in rows if r[1])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
