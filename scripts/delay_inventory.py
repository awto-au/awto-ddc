#!/usr/bin/env python3
"""Inventory of every delay, wait, poll and timer-event step in the built firmware (#54, #40, #53.6/12/13). Offline.

usage: delay_inventory.py [--build DIR] [--map MAP] [--bin BIN] [--sim] [--out re/delays.tsv] [--doc docs/delays.md]
  --build  worktree holding the build's tmp/sdcc-port/{asm_bank/*.rst,src} (default $AWTO_DDC_BUILD or ../awto-ddc-stepB)
  --map    linker map of the image (default tmp/fw/AWT26110003-wb-stepB-be.map)
  --sim    run the image in ucsim (HdmiInput 1080p60 on D2) from reset to ACTIVE and count every blocking site
           -> re/delays_sim.json (committed; later runs without --sim merge it)
Sources (all post-link, so "linked" is exact):
  asm_bank/*.rst = SDCC listing with final addresses: every compiled statement (file:line + text) and every
  call/jump instruction; arguments are read from the instruction constants (macros already resolved by the compiler).
  Source lines of compiled files that match but have no code = compiled out (linked=no).
Kinds: delay_ms (blind, Timer2 spin) | delay_us (blind, calibrated loop) | poll (ScalerTimerPollingFlagProc, bounded ms) |
  wait_event (ScalerTimerWaitFor*, bounded) | timer_event (deferred, non-blocking period) | status_loop (while on a status
  bit) | busy_loop (empty for) | nop (nop chain) | param (named timing constant, resolved with sdcc -dM).
Contexts come from reachability in the static call graph (stub calls resolved; function pointers are not followed).
Hand classification: re/delays_reasons.tsv (match, class, reason, citation, vendor_value).
Log: tmp/logs/delay_inventory.log
"""
from __future__ import annotations

import argparse
import bisect
import collections
import glob
import json
import os
import re
import subprocess
import sys
import time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).parent,
                                            text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


ROOT = repo_root()
LOGF = None
ACTIVE_MS = 1000       # steady-state window after ACTIVE: ~300 main-loop passes at the measured 300+/s (#11), enough to rank per-pass waits


def log(s: str):
    line = f"{isostamp.now()} {s}"
    print(line)
    if LOGF:
        LOGF.write(line + "\n")
        LOGF.flush()


# ---------------------------------------------------------------- map + listing
def parse_map(path: Path) -> dict[str, tuple[int, str]]:
    """code symbols: '_name' -> (address incl. bank<<16, module)"""
    syms = {}
    for l in path.read_text(errors="replace").splitlines():
        m = re.match(r"^C:\s+([0-9A-F]{8})\s+(_\w+)\s*(\S*)", l)
        if m:
            syms[m.group(2)] = (int(m.group(1), 16), m.group(3))
    return syms


ASM = re.compile(r"^\s+([0-9A-F]{6})\s+((?:[0-9A-F]{2}\s)+)\s*\[\d+\]\s*(\d+)\s(.*)$")
SRC = re.compile(r"^\s+\d+ ;\t(.+?):(\d+): (.*)$")
LAB = re.compile(r"^\s+([0-9A-F]{6})\s+\d+ (_\w+|\d+\$):\s*$")


class Fn:
    __slots__ = ("name", "addr", "module", "stmts", "ins", "calls", "reti", "labels")

    def __init__(self, name, addr, module):
        self.name, self.addr, self.module = name, addr, module
        self.stmts = []          # [file, line, text, [(addr, asm)]]
        self.ins = []            # [(addr, asm)]
        self.calls = []          # callee raw names
        self.reti = False
        self.labels = {}


def parse_rst(build: Path, syms) -> dict[str, Fn]:
    fns: dict[str, Fn] = {}
    parse_rst.stubs = {}                                  # bank stub address -> function name (for tail calls seen in the sim)
    for f in sorted(glob.glob(str(build / "tmp/sdcc-port/asm_bank/*.rst"))):
        cur, st, labels = None, None, {}
        for l in open(f, errors="replace"):
            m = LAB.match(l)
            if m:
                if m.group(2).startswith("__bs_"):
                    parse_rst.stubs[int(m.group(1), 16)] = "_" + m.group(2)[5:]
                    cur, st = None, None
                elif m.group(2)[:32] in syms and not m.group(2)[0].isdigit():     # the map cuts names at 32 characters
                    cur = fns.setdefault(m.group(2), Fn(m.group(2), int(m.group(1), 16), syms[m.group(2)[:32]][1]))
                    st = None
                elif cur:
                    cur.labels[m.group(2)] = int(m.group(1), 16)
                continue
            m = SRC.match(l)
            if m:
                if cur:
                    st = [m.group(1), int(m.group(2)), m.group(3).strip(), []]
                    cur.stmts.append(st)
                continue
            m = ASM.match(l)
            if m and cur:
                t = m.group(4).strip()
                a = int(m.group(1), 16)
                cur.ins.append((a, t))
                if st is None:
                    st = ["", 0, "", []]
                    cur.stmts.append(st)
                st[3].append((a, t))
                mm = re.match(r"(lcall|ljmp|acall|ajmp)\s+([A-Za-z_]\w*)", t)
                if mm:
                    cur.calls.append(mm.group(2))
                elif t.startswith("reti"):
                    cur.reti = True
    return {k: v for k, v in fns.items() if not k.startswith("__bs_")}


def resolve_callee(raw: str, names: set[str], stub_idx: dict[str, list[str]]) -> list[str]:
    if raw.startswith("__bs_"):
        return stub_idx.get(raw, [])
    return [raw] if raw in names else []


def build_graph(fns):
    names = set(fns)
    stub_idx = collections.defaultdict(list)
    for n in names:
        stub_idx["__bs_" + n[1:]].append(n)
    g = {n: set() for n in names}
    for n, f in fns.items():
        for c in f.calls:
            for t in resolve_callee(c, names, stub_idx):
                g[n].add(t)
    return g


def reach(g, roots):
    seen, todo = set(), list(roots)
    while todo:
        n = todo.pop()
        if n in seen or n not in g:
            continue
        seen.add(n)
        todo.extend(g[n])
    return seen


SEEDS = [   # (context, root functions); primary context of a function = the narrowest of these call trees that contains it (isr first)
    ("isr", None),
    ("boot", ["_AwtoDiagInit", "_SysMainSystemInitial", "_SysMainSytemPowerDetect"]),
    ("display_setup", ["_SysModeDisplaySetting"]),
    ("power", ["_SysPowerHandler"]),
    ("search", ["_SysSourceHandler", "_SysTMDSRxHandler", "_SysDpRxHandler"]),
    ("mode_change", ["_SysModeHandler", "_SysJudgeHandler"]),
    ("osd", ["_UserCommonInterfaceOsdHandler", "_UserInterfaceKeyHandler", "_AwtoKeyPoll", "_SysColorHandler"]),   # #129: AwtoKeyPoll replaced the SDK key handler
    ("ddcci", ["_UserCommonDdcciHandler"]),
    ("timer_event", ["_SysTimerHandler"]),
    ("debug", ["_ScalerDebug", "_AwtoDiagMainPass", "_AwtoDiagTestCmd"]),
]


def contexts(fns, g):
    isr_roots = [n for n, f in fns.items() if f.reti]
    ctx = collections.defaultdict(list)
    sets = [(c, reach(g, isr_roots if roots is None else roots)) for c, roots in SEEDS]
    for c, rs in sorted(sets, key=lambda x: (x[0] != "isr", len(x[1]))):     # isr first, then the narrowest tree = most specific
        for n in rs:
            ctx[n].append(c)
    live = reach(g, ["_main", *isr_roots])
    return ctx, live


# ---------------------------------------------------------------- macros / constants
def macro_dump(build: Path, cache: Path) -> dict[str, str]:
    """#define table of the project target (sdcc -E -dM over a few translation units, union)."""
    if not cache.exists():
        os.environ["AWTO_DDC_REPO"] = str(build)
        import importlib
        k = importlib.import_module("fw_compile")
        uv2 = k.SRC / "STD_FW_1P.Uv2"
        files, defines, incs, model = k.parse_uv2(uv2, "RL6449_Project")
        out = []
        for key in ("SysMain", "RTD2014UserInterface", "RL6449_Series_Power", "SysPower", "SysSource", "ScalerCommonTimerFunction",
                    "RL6449_Series_DisplayDPTx", "RL6449_Series_TMDSRx2"):
            c = next(((uv2.parent / f).resolve() for f in files if Path(f).stem == key), None)
            if not c:
                continue
            r = subprocess.run(k.sdcc_cmd(c, uv2.parent, defines, incs, model) + ["-Wp-dM", "-E", str(c)], capture_output=True,
                               text=True, errors="replace", timeout=200)
            out.append(r.stdout)
            log(f"macro dump {key}: {len(r.stdout)} chars")
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text("\n".join(out))
    defs = {}
    for l in cache.read_text(errors="replace").splitlines():
        m = re.match(r"#define\s+(\w+)(\([^)]*\))?\s*(.*)$", l)
        if m:
            defs.setdefault(m.group(1) + (m.group(2) or ""), m.group(3).strip())
    return defs


class Eval:
    """evaluate numeric C constant expressions from the #define table (casts, suffixes, SEC(x))"""
    TYPES = r"(?:BYTE|WORD|DWORD|SBYTE|SWORD|UINT|UCHAR|unsigned\s+\w+|int|long|char)"

    def __init__(self, defs):
        self.obj = {k: v for k, v in defs.items() if "(" not in k}
        self.fn = {k.split("(")[0]: (re.findall(r"\w+", k.split("(", 1)[1]), v) for k, v in defs.items() if "(" in k}

    def expand(self, s: str, depth=0) -> str:
        if depth > 12:
            return s
        def sub(m):
            name = m.group(0)
            return self.obj.get(name, name)
        prev = None
        for _ in range(12):
            if prev == s:
                break
            prev = s
            for name, (params, body) in self.fn.items():
                s = re.sub(rf"\b{name}\s*\(([^()]*)\)", lambda m, p=params, b=body: self._call(p, b, m.group(1)), s)
            s = re.sub(r"\b[A-Za-z_]\w*\b", sub, s)
        return s

    @staticmethod
    def _call(params, body, args):
        a = [x.strip() for x in args.split(",")]
        for p, v in zip(params, a):
            body = re.sub(rf"\b{p}\b", f"({v})", body)
        return f"({body})"

    def value(self, expr: str):
        s = self.expand(expr)
        s = re.sub(rf"\(\s*{self.TYPES}\s*\)", "", s)
        s = re.sub(r"\b(0[xX][0-9A-Fa-f]+|\d+(?:\.\d+)?)[uUlL]+\b", r"\1", s)
        if not re.fullmatch(r"[0-9a-fA-FxX+\-*/%()<>&|^~.\s]*", s) or not s.strip():
            return None
        try:
            v = eval(s.replace("/", "//") if "." not in s else s, {"__builtins__": {}}, {})
            return float(v) if isinstance(v, float) else int(v)
        except Exception:
            return None


# ---------------------------------------------------------------- sites
PRIM = [   # (kind, regex on callee name)
    ("delay_ms", r"_ScalerTimerDelayXms"),
    ("poll", r"_ScalerTimerPollingFlagProc\w*"),
    ("timer_event", r"_ScalerTimer(?:WD)?(?:Active|Reactive|Activate)\w*TimerEvent\w*"),
    ("wait_event", r"_ScalerTimerWaitFor\w+"),
]
US_RE = re.compile(r"\b(DELAY_(\d+)US(_EXINT)?|ScalerDelay5us|DELAY_XUS(_EXINT)?)\s*\(([^)]*)\)")
STATUS_TOK = re.compile(r"ScalerGet\w*Bit|MCU_F[0-9A-F]{3}|\bP[0-9A-F]{1,2}_[0-9A-F]{2}_|GET_\w+\(\)|d_isr_g_usTimerCounter|\bT[FH]2\b|"
                        r"usTimeElapsed|TimeOut|_DATA_OUT_COUNT|ScalerVgipGet\w*|ucHalt|ucPhyCtsAutoMode")
COUNT_TOK = re.compile(r"(\w+\[?\d*\]?)\s*(?:--|\+\+)?\s*(?:>|<=|<|>=)\s*(\w+)|--\s*(\w+)\s*>\s*0|\((\w+)--\s*>\s*0\)")


LOOP_MACRO = re.compile(r"(POLLING_VCCK_OFF_STATUS)\s*\(")


def split_args(text: str, name: str) -> list[str]:
    i = text.find(name + "(")
    if i < 0:
        return []
    i += len(name) + 1
    depth, cur, out = 1, "", []
    for ch in text[i:]:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                out.append(cur.strip())
                return out
        if ch == "," and depth == 1:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    return out


def interp(ins, upto: int) -> tuple[dict, dict]:
    """tiny constant tracker over the statement's instructions before `upto`: registers + xdata parameter stores"""
    st: dict = {}
    parm: dict = {}
    bits: dict = {}
    for a, t in ins[:upto]:
        m = re.match(r"mov\s+dptr,#(.+)$", t)
        if m:
            v = m.group(1)
            st["dptr"] = int(v, 16) if re.fullmatch(r"0x[0-9a-fA-F]+", v) else v
            if isinstance(st["dptr"], int):
                st["dph"], st["dpl"] = st["dptr"] >> 8, st["dptr"] & 255
            else:
                st.pop("dph", None); st.pop("dpl", None)
            continue
        if t == "inc\tdpl" or t == "inc dpl":
            if "dpl" in st:
                st["dpl"] = (st["dpl"] + 1) & 255
                st["dptr"] = st["dph"] << 8 | st["dpl"] if "dph" in st else "?"
            continue
        if t == "inc\tdptr" or t == "inc dptr":
            if isinstance(st.get("dptr"), int):
                st["dptr"] = (st["dptr"] + 1) & 0xFFFF
                st["dph"], st["dpl"] = st["dptr"] >> 8, st["dptr"] & 255
            continue
        m = re.match(r"mov\s+(dph|dpl),\s*#(0x[0-9a-fA-F]+|\d+)$", t)
        if m:
            st[m.group(1)] = int(m.group(2), 0)
            if "dph" in st and "dpl" in st:
                st["dptr"] = st["dph"] << 8 | st["dpl"]
            continue
        m = re.match(r"mov\s+(a|r\d),\s*#(0x[0-9a-fA-F]+|\d+)$", t)
        if m:
            st[m.group(1)] = int(m.group(2), 0)
            continue
        if t == "clr\ta" or t == "clr a":
            st["a"] = 0
            continue
        m = re.match(r"mov\s+(a|r\d),\s*(a|r\d)$", t)
        if m:
            st[m.group(1)] = st.get(m.group(2))
            continue
        m = re.match(r"mov\s+(r\d|a),\s*dp([lh])$", t)
        if m:
            continue
        if t.startswith("movx\t@dptr,a") or t.startswith("movx @dptr,a"):
            d = st.get("dptr")
            if isinstance(d, str):
                parm[d] = st.get("a")
            continue
        m = re.match(r"(setb|clr)\s+\(?__bovl", t)
        if m:
            bits["last"] = 1 if m.group(1) == "setb" else 0
    return st, {**parm, **{"_bit": bits.get("last")}}


def dptr_val(st):
    if isinstance(st.get("dptr"), int):
        return st["dptr"]
    return None


def stated_reason(src: Path, line: int) -> str:
    """nearest comment: trailing // on the line, else the comment block directly above"""
    try:
        L = src.read_text(errors="replace").splitlines()
    except OSError:
        return ""
    if not (0 < line <= len(L)):
        return ""
    m = re.search(r"//\s*(.+)$", L[line - 1])
    if m and not re.search(r"keil2sdcc", m.group(1)):
        return m.group(1).strip()[:160]
    out, i = [], line - 2
    while i >= 0 and re.match(r"\s*(//|/\*|\*)", L[i]):
        t = re.sub(r"^\s*(//|/\*+|\*+/?)\s*", "", L[i]).strip()
        if t and not re.fullmatch(r"[-=*/ ]+", t):
            out.append(t)
        i -= 1
    return " ".join(reversed(out))[:160]


def in_loop(f: Fn, addr: int) -> bool:
    for a, t in f.ins:
        m = re.match(r"(?:sjmp|ljmp|ajmp|j\w+|djnz\s+\w+,|cjne\s+[^,]+,[^,]+,)\s*(?:.*,)?(\d+\$)$", t)
        if m and m.group(1) in f.labels:
            tgt = f.labels[m.group(1)]
            if tgt <= addr <= a and tgt < a:
                return True
    return False


def rel(p: str) -> str:
    return p.split("/tmp/sdcc-port/src/", 1)[-1]


def extract_sites(fns, ctx, live, defs: Eval, build: Path):
    rows = []
    names = set(fns)
    stub_idx = collections.defaultdict(list)
    for n in names:
        stub_idx["__bs_" + n[1:]].append(n)
    for fn in fns.values():
        nops = 0
        for file, line, text, ins in fn.stmts:
            base = dict(file=rel(file), line=line, function=fn.name[1:], module=fn.module, stmt=text[:140],
                        context=(ctx.get(fn.name) or ["unreachable"])[0], ctx_all=",".join(ctx.get(fn.name, [])),
                        linked="yes", reachable="yes" if fn.name in live else "no")
            for i, (a, t) in enumerate(ins):
                m = re.match(r"(lcall|ljmp|acall|ajmp)\s+([A-Za-z_]\w*)", t)
                if not m:
                    continue
                for tgt in resolve_callee(m.group(2), names, stub_idx) or [m.group(2)]:
                    for kind, rx in PRIM:
                        if re.fullmatch(rx, tgt):
                            rows.append(site_row(kind, tgt, fn, base, text, ins, i, a, build))
            ml = LOOP_MACRO.match(text)
            if ml:
                a0 = split_args(text, ml.group(1))
                v = defs.value(a0[0]) if a0 else None
                rows.append(dict(base, kind="status_loop", addr=f"0x{ins[0][0]:x}" if ins else "", value=v if v is not None else "", units="ms",
                                 mode="polled", bound=f"{v} iterations x ScalerTimerDelayXms(1)" if v is not None else "counted",
                                 expiry="falls through after the bound (no error)", args=text[:100], in_loop=""))
            m = US_RE.search(text)
            if m:
                nm = m.group(1)
                if nm.startswith("DELAY_XUS"):
                    v = defs.value(m.group(5))
                elif nm == "ScalerDelay5us":
                    v = 5
                else:
                    v = int(m.group(2))
                rows.append(dict(base, kind="delay_us", addr=f"0x{ins[0][0]:x}" if ins else "", value=v if v is not None else "",
                                 units="us", mode="blind", bound="", expiry="none: counted loop, nominal (d_isr_g_ucDelay5usN_Base calibrated)",
                                 args=m.group(0), in_loop=("yes" if ins and in_loop(fn, ins[0][0]) else "no")))
            elif re.match(r"(?:while|for)\s*\(", text) or re.match(r"while\s*\(", text):
                row = loop_row(fn, base, text, ins)
                if row:
                    rows.append(row)
            if re.search(r"\b_nop_\s*\(\s*\)", text):
                nops += 1
        if nops:
            rows.append(dict(kind="nop", file=rel(fn.stmts[0][0]), line=0, function=fn.name[1:], module=fn.module, stmt=f"{nops} x _nop_()",
                             context=(ctx.get(fn.name) or ["unreachable"])[0], ctx_all=",".join(ctx.get(fn.name, [])), linked="yes",
                             reachable="yes" if fn.name in live else "no", addr=f"0x{fn.addr:x}", value=nops, units="nop",
                             mode="blind", bound="", expiry="none", args="", in_loop=""))
    return rows


def loop_row(fn, base, text, ins):
    if re.search(r"\)\s*\{\s*\}\s*;?\s*$", text) or re.search(r"for\s*\(.*\)\s*;\s*$", text):
        return dict(base, kind="busy_loop", addr=f"0x{ins[0][0]:x}" if ins else "", value="", units="iterations", mode="blind", bound="",
                    expiry="none", args=text[:100], in_loop="")
    if STATUS_TOK.search(text):
        cnt = re.search(r"(--ucTimeOut\s*>\s*0|\w+--\s*>\s*0|\(\w+\+\+\)\s*<\s*\w+|\w+\s*<\s*\d+\)|usTimeElapsed\s*<=\s*\w+|\w+\s*<=?\s*_\w+)", text)
        return dict(base, kind="status_loop", addr=f"0x{ins[0][0]:x}" if ins else "", value="", units="", mode="polled",
                    bound=("counted: " + cnt.group(1)) if cnt else "none in statement (check body)", expiry="loop exits; no error raised unless the body checks",
                    args=text[:100], in_loop="")
    return None


def site_row(kind, tgt, fn, base, text, ins, i, a, build):
    k = next((j for j, (aa, _) in enumerate(fn.ins) if aa == a), 0)
    ins, i = fn.ins[max(0, k - 14):k + 1], min(k, 14)           # arguments may be set up under the previous source line
    last_call = max((j for j, (_, t) in enumerate(ins[:i]) if re.match(r"(lcall|acall)\b", t)), default=-1)
    ins, i = ins[last_call + 1:], i - last_call - 1               # a call clobbers dptr and the argument registers
    st, parm = interp(ins, i)
    d = dptr_val(st)
    recent = [t for _, t in ins[max(0, i - 6):i] if not re.match(r"(push|pop)\b", t)][-4:]
    if not any(re.match(r"(mov\s+dptr,#|inc\s+dpl|inc\s+dptr|mov\s+dp[hl],)", t) for t in recent):
        d = None                                    # argument not set just before the call: computed at run time
    row = dict(base, kind=kind, addr=f"0x{a:x}", args="", value="", units="ms", mode="", bound="", expiry="",
               in_loop="yes" if in_loop(fn, a) else "no", callee=tgt[1:])
    shown = text
    nm = tgt[1:]
    if kind == "delay_ms":
        row.update(value=d if d is not None else "variable", mode="blind", expiry="none (returns at once if Timer2 is off)",
                   args=",".join(split_args(shown, "ScalerTimerDelayXms")[:1]) or "(macro)")
    elif kind == "poll":
        reg = (st.get("r6", 0) << 8 | st.get("r7", 0)) if "r7" in st and "r6" in st else None
        mask = next((v for k, v in parm.items() if "_PARM_3" in str(k)), None)
        suc = parm.get("_bit")
        res_used = bool(re.match(r"(if|while|return)\b|.*[=!]=|\w+\s*=|.*&&|.*\|\|", shown)) and "ScalerTimerPollingFlagProc" in shown and not shown.startswith("ScalerTimerPollingFlagProc")
        row.update(value=d if d is not None else "variable", mode="polled", bound=f"{d} ms" if d is not None else "variable",
                   expiry="returns _FALSE after the bound; " + ("caller tests the result" if res_used else "result ignored, sequence continues"),
                   args=(f"reg=0x{reg:04X} " if reg is not None else "") + (f"mask=0x{mask:02X} " if isinstance(mask, int) else "") +
                        ("wait_for=" + ("1" if suc else "0") if suc is not None else ""))
    elif kind == "timer_event":
        ev = split_args(shown, nm)
        evn = (ev[1] if len(ev) > 1 else "").strip()
        evid = f"id=0x{st['r7']:02x}" if isinstance(st.get("r7"), int) else ""
        row.update(value=d if d is not None else "variable", mode="deferred", expiry="non-blocking: handler runs from SysTimerHandler",
                   args=(f"{evn} {evid}").strip())
    elif kind == "wait_event":
        ev = split_args(shown, nm)
        bound = 90 if "WaitForEvent" in nm else ""
        row.update(value=bound, mode="polled", bound=f"{bound} ms (_TIMER_WAIT_EVENT_TIMEOUT)" if bound else "event period",
                   expiry="returns _FALSE after the bound" if bound else "waits for the deferred event (see timer_event row)",
                   args=ev[0] if ev else "")
    return row


# ---------------------------------------------------------------- compiled-out source scan
SRC_PATS = [("delay_ms", re.compile(r"\bScalerTimerDelayXms\s*\(")),
            ("poll", re.compile(r"\bScalerTimerPollingFlagProc\w*\s*\(")),
            ("timer_event", re.compile(r"\bScalerTimer(?:WD)?(?:Active|Reactive|Activate)\w*TimerEvent\w*\s*\(")),
            ("wait_event", re.compile(r"\bScalerTimerWaitFor\w+\s*\(")),
            ("delay_us", US_RE)]
FN_DEF = re.compile(r"^[A-Za-z_][\w \t\*]*?\b(\w+)\s*\([^;]*\)\s*$")


def compiled_out(fns, build: Path, ev: Eval, ctx) -> list[dict]:
    have = {(rel(s[0]), s[1]) for f in fns.values() for s in f.stmts}
    files = sorted({f for f, _ in have if f.endswith(".c")})
    rows = []
    for f in files:
        p = build / "tmp/sdcc-port/src" / f
        try:
            L = p.read_text(errors="replace").splitlines()
        except OSError:
            continue
        cur = ""
        for n, l in enumerate(L, 1):
            if FN_DEF.match(l) and not l.startswith(("#", " ", "\t", "//")) and "=" not in l:
                cur = FN_DEF.match(l).group(1)
            if (f, n) in have or l.lstrip().startswith(("//", "*", "/*")):
                continue
            for kind, rx in SRC_PATS:
                m = rx.search(l)
                if not m:
                    continue
                if kind == "delay_us":
                    nm = m.group(1)
                    v = 5 if nm == "ScalerDelay5us" else (ev.value(m.group(5)) if nm.startswith("DELAY_XUS") else int(m.group(2)))
                    units = "us"
                else:
                    a = split_args(l, m.group(0).rstrip("( ").strip())
                    v = ev.value(a[0]) if a else None
                    units = "ms"
                rows.append(dict(kind=kind, file=f, line=n, function=cur, module=Path(f).stem, stmt=l.strip()[:140], context="n/a",
                                 ctx_all="", linked="no (compiled out: #if / unreferenced)", reachable="no", addr="",
                                 value=v if v is not None else "", units=units, mode={"delay_ms": "blind", "delay_us": "blind", "poll": "polled",
                                 "timer_event": "deferred", "wait_event": "polled"}[kind], bound="", expiry="", args="", in_loop=""))
                break
    return rows


# ---------------------------------------------------------------- named timing constants
PARAM_RE = re.compile(r"^(_PANEL_POWER_(ON|OFF)_T\d|_PANEL_POW_SEQ_\w+|_SOURCE_\w*(SEARCH|TIME|DELAY)\w*|_WAIT_TIME_TO_ACTIVE_\w+|_WAITING_FOR_\w+|"
                      r"_POWER_\w*TIME\w*|_\w*HPD\w*(TIME|DELAY)\w*|_\w*(TIMEOUT|TIME_OUT)\w*|_VCCK\w*TIME\w*|_DDR_POWER_\w+|_DAC_DEPOP\w*|_DP_\w*MUTE_TIMER|"
                      r"_DVC_VOLUME_MUTE_TIMER|_USER_AC_ON\w*(DELAY|SEC)\w*|_OSD_\w*(TIME|TIMEOUT)\w*|_\w*SEC)$")


def param_rows(ev: Eval, build: Path) -> list[dict]:
    where = {}
    root = build / "tmp/sdcc-port/src"
    pref = ["Project", "Panel", "Pcb/RL6449", "User", "Kernel/Common/RL6449", "Kernel"]
    names = {k for k in ev.obj if PARAM_RE.match(k) and not re.search(r"_SUPPORT|_MODE$|_EN$|_TYPE|WIDTH|ADDR|_REG|_BIT", k)}
    for p in root.rglob("*.h"):
        r = str(p.relative_to(root))
        if any(x in r for x in ("RL6410", "RL6432", "RL6492", "RL6369", "RL6193", "RL6463")):
            continue
        for n, l in enumerate(p.read_text(errors="replace").splitlines(), 1):
            m = re.match(r"\s*#\s*define\s+(\w+)\b", l)
            if m and m.group(1) in names:
                score = next((i for i, x in enumerate(pref) if r.startswith(x)), 9)
                if m.group(1) not in where or score < where[m.group(1)][0]:
                    where[m.group(1)] = (score, r, n)
    rows = []
    for k in sorted(names):
        v = ev.value(ev.obj[k])
        if v is None or (isinstance(v, int) and v in (0, 1) and not re.search(r"_T\d|TIME|DELAY|SEC", k)):
            continue
        if not isinstance(v, (int, float)) or v == 0:
            continue
        s = where.get(k, (0, "", 0))
        rows.append(dict(kind="param", file=s[1], line=s[2], function="", module="", stmt=f"#define {k} {ev.obj[k]}"[:140], context="config",
                         ctx_all="", linked="yes", reachable="", addr="", value=int(v) if float(v).is_integer() else v, units="ms",
                         mode="constant", bound="", expiry="", args=k, in_loop=""))
    return rows


# ---------------------------------------------------------------- reasons + classification
def load_reasons(path: Path):
    out = []
    if path.exists():
        for l in path.read_text().splitlines()[1:]:
            c = l.split("\t")
            if len(c) >= 3 and c[0] and not c[0].startswith("#"):
                out.append((c + [""] * 6)[:6])
    return out


def classify(rows, reasons):
    """reasons keys: basename:line | kind@basename:line | kind@function | any of these + #value (exact value of the row)"""
    for r in rows:
        r.setdefault("vendor", ""); r.setdefault("cls", "unknown"); r.setdefault("why", ""); r.setdefault("cite", "")
        b = f"{Path(r['file']).name}:{r['line']}"
        keys = {b, f"{r['kind']}@{b}", f"{r['kind']}@{r['function']}"}
        keys |= {f"{k}#{r['value']}" for k in set(keys)}
        if r["kind"] == "param":
            keys = {r.get("args", "")}
        for pat, cls, why, cite, vend, _ in reasons:
            if pat in keys:
                r["cls"], r["why"], r["cite"], r["vendor"] = cls, why, cite, vend or r["vendor"]
                break
        if r["kind"] == "timer_event" and r["cls"] == "unknown":
            r["cls"], r["why"] = "non-blocking", "deferred event: costs no CPU time; the period is a latency, not a wait"
        if r["kind"] == "nop" and r["cls"] == "unknown":
            r["cls"], r["why"] = "required", "nop chain: pin/bus setup, a few machine cycles"
    return rows


def vms(r):
    try:
        v = float(r["value"])
    except (TypeError, ValueError):
        return 0.0
    if r["kind"] in ("delay_ms", "poll", "wait_event", "param"):
        return v
    if r["units"] == "us":
        return v / 1000.0
    return 0.0


# ---------------------------------------------------------------- simulator cross-check
def sim_measure(binp: Path, mapp: Path, rows, out: Path, stub_names: dict, fn_names: dict, mode="1080p60", max_instr=300_000_000):
    """reset -> ACTIVE in ucsim with a 1080p60 source on D2; counts + fw-time of every blocking call site (common-area callees)."""
    import fw_sim as F
    syms = parse_map(mapp)
    be = "-be" in binp.name
    b = F.SimBus(binp, mapp, video=mode, boot=False)
    m = b.m
    cend = getattr(m.where, "cend", 0x5000)
    base = b.diag_base
    last = {"t": None, "abs": 0}

    def t2():
        raw = int.from_bytes(m.rd(base + 0x16, 2), "big" if be else "little")
        if last["t"] is not None:
            last["abs"] += (raw - last["t"]) & 0xFFFF
        last["t"] = raw
        return last["abs"]

    sites: dict[str, dict] = {}
    hits: list = []                                    # blocking calls before ACTIVE: (fw ms at entry, ms spent, site)
    pend: dict[str, tuple] = {}
    phase = {"p": ""}                                  # "" = reset to ACTIVE, "act_" = steady state after ACTIVE
    targets = {"delay_ms": "ScalerTimerDelayXms", "poll": "ScalerTimerPollingFlagProc", "wait_event": "ScalerTimerWaitForEvent"}

    rtab_lo = syms["__bs_ret"][0] - 64
    rtab_hi = rtab_lo + 64                             # 16 restore entries x 4 B (fw/sdcc/bank.asm __bs_rtab)
    img = b.img
    by_fk = collections.defaultdict(list)
    for r in rows:
        if r.get("addr") and r["linked"] == "yes":
            by_fk[(r["function"], r["kind"])].append(r)

    def code(bank, a_):
        return img[(bank << 16 | a_) if a_ >= cend else a_]

    prim = {"delay_ms": syms["_ScalerTimerDelayXms"][0], "poll": syms["_ScalerTimerPollingFlagProc"][0],
            "wait_event": syms["_ScalerTimerWaitForEvent"][0]}

    def locate(kind, arg):
        """-> (site key, return pc to hook, bank of that pc). The stack top is the return address into the caller of the
        primitive. When the instruction before it is `lcall primitive` that is the site. Otherwise the primitive was reached by a
        tail call (ljmp) from the function that instruction called: a direct function, or a bank stub (then the top is a __bs_rtab
        slot, slot number = caller bank, and the caller's own return address lies below it)."""
        sp = m.rd(0x81, 1, "sfr")[0]
        st = m.rd(sp - 3, 4, "iram")
        ret = st[3] << 8 | st[2]
        bank = m.rd(0xFFFF)[0] & 15
        cret, k = ret, bank
        if rtab_lo <= ret < rtab_hi:
            k, cret = (ret - rtab_lo) // 4, st[1] << 8 | st[0]
        lc = [code(k, cret - 3 + i) for i in range(3)]
        tgt = lc[1] << 8 | lc[2] if lc[0] == 0x12 else None
        if tgt == prim.get(kind) and not rtab_lo <= ret < rtab_hi:
            return f"0x{cret - 3 if cret < cend else (k << 16 | (cret - 3)):x}", cret, k
        fname = None
        if tgt is not None:
            fname = stub_names.get(tgt) or fn_names.get(tgt if tgt < cend else (k << 16 | tgt))
        cand = by_fk.get((fname[1:], kind), []) if fname else []
        if len(cand) > 1:
            cand = [c for c in cand if c["value"] == arg] or cand
        key = cand[0]["addr"] if cand else f"unresolved:{fname or hex(cret)}"
        return key, cret, k

    def on_entry(kind):
        def fn(mm, regs):
            arg = regs["a1"]
            key, pc, bank = locate(kind, arg)
            now = t2()
            s = sites.setdefault(key, dict(kind=kind, calls=0, nominal_ms=0, ms=0.0, first_ms=now, expired=0, args=[],
                                           act_calls=0, act_ms=0.0, act_expired=0))
            ph = phase["p"]
            s[ph + "calls"] += 1
            if kind == "delay_ms" and not ph:
                s["nominal_ms"] += arg
            s["args"] = sorted(set(s["args"]) | {arg})[:4]
            pend[key] = (now, kind, arg, ph)
            if not s.get("hooked"):
                s["hooked"] = True
                m.stubs.setdefault(pc, []).append((None if pc < cend else bank, "ret:" + key, on_exit(key)))
                m.s.send(f"break 0x{pc:x}")
            return None
        return fn

    def on_exit(key):
        def fn(mm, regs):
            if key in pend:
                t0, kind, arg, ph = pend.pop(key)
                s = sites[key]
                s[ph + "ms"] += t2() - t0
                if not ph:
                    hits.append((t0, t2() - t0, key))
                if kind != "delay_ms" and not (mm.rd(0xD0, 1, "sfr")[0] & 0x80):
                    s[ph + "expired"] += 1
            return None
        return fn

    events: list = []                                  # deferred timer events armed: (fw ms, period ms, event id, reactive)

    def on_event(react):
        def fn(mm, regs):
            events.append((t2(), regs["a1"], regs["a2"], react, phase["p"] == "act_"))
            return None
        return fn

    for kind, nm in targets.items():
        if "_" + nm in syms:
            m.stub(nm, on_entry(kind))
    m.stub("ScalerTimerActiveTimerEvent", on_event(False))
    m.stub("ScalerTimerReactiveTimerEvent", on_event(True))
    timeline, t_start = [], time.time()
    prev, used = None, 0
    mode_state = b.mode_state
    while used < max_instr:
        m.run(200_000); used += 200_000
        st = mode_state()
        if st != prev:
            timeline.append((t2(), st)); prev = st
            log(f"sim: fw {last['abs']} ms, mode state {st}, {used} instr, wall {time.time() - t_start:.0f} s")
        if st == 3:
            break
    t_active = t2()
    if prev == 3:                                      # steady state: what the main loop still waits for with a picture up
        phase["p"] = "act_"
        while t2() - t_active < ACTIVE_MS:
            m.run(200_000); used += 200_000
    d = b.diag()
    res = dict(image=binp.name, reached_active=prev == 3, fw_ms_at_active=t_active, active_window_ms=t2() - t_active, fw_ms_at_end=t2(),
               instr=used, timeline=timeline, events=events, hits=hits, stub_hits=dict(m.stub_hits),
               stages={k: v for k, v in d.items() if k not in ("raw",)}, sites=sites)
    out.write_text(json.dumps(res, indent=1, default=str))
    b.close()
    return res


def mode_at(timeline, t):
    names = ["INITIAL", "SEARCH", "DISPLAY_SETTING", "ACTIVE", "NOSUPPORT", "NOSIGNAL", "POWER_SAVING", "POWER_OFF", "FACTORY"]
    st = None
    for tt, s in timeline:
        if tt <= t:
            st = s
    return names[st] if st is not None and st < len(names) else "pre-boot"


def merge_sim(rows, sim):
    by = {r["addr"]: r for r in rows if r.get("addr")}
    for r in rows:
        r.update(sim_calls="", sim_ms="", sim_expired="", sim_first_ms="", sim_mode="", act_calls="", act_ms="")
    for k, s in sim["sites"].items():
        r = by.get(k)
        if not r:
            continue
        r["sim_calls"], r["sim_ms"], r["sim_expired"], r["sim_first_ms"] = s["calls"], round(s["ms"], 1), s["expired"], s["first_ms"]
        r["sim_mode"] = mode_at(sim["timeline"], s["first_ms"])
        r["act_calls"], r["act_ms"] = s["act_calls"], round(s["act_ms"], 1)
    return rows


COLS = ["id", "kind", "file", "line", "function", "module", "addr", "value", "units", "value_ms", "mode", "bound", "expiry", "context", "ctx_all",
        "in_loop", "reachable", "linked", "stated_reason", "vendor", "class", "class_reason", "citation", "sim_calls", "sim_ms",
        "sim_expired", "sim_first_ms", "sim_mode", "act_calls", "act_ms", "args", "stmt"]


def write_tsv(rows, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w") as f:
        f.write("\t".join(COLS) + "\n")
        for r in rows:
            out = []
            for c in COLS:
                v = {"class": r.get("cls", ""), "class_reason": r.get("why", ""), "citation": r.get("cite", ""),
                     "stated_reason": r.get("stated", ""), "value_ms": ("%g" % vms(r)) if vms(r) else ""}.get(c, r.get(c, ""))
                out.append(str(v).replace("\t", " ").replace("\n", " "))
            f.write("\t".join(out) + "\n")


def build_rows(a):
    build = Path(a.build)
    syms = parse_map(Path(a.map))
    fns = parse_rst(build, syms)
    g = build_graph(fns)
    ctx, live = contexts(fns, g)
    log(f"{len(fns)} linked functions from the listing, {sum(len(v) for v in g.values())} call edges, {len(live)} reachable from main/ISRs")
    defs = Eval(macro_dump(build, ROOT / "tmp/delay_inventory/macros.txt"))
    rows = extract_sites(fns, ctx, live, defs, build)
    rows += compiled_out(fns, build, defs, ctx)
    rows += param_rows(defs, build)
    for r in rows:
        if r["kind"] != "param" and r["file"]:
            r["stated"] = stated_reason(build / "tmp/sdcc-port/src" / r["file"], int(r["line"] or 0)) if r["line"] else ""
    rows = classify(rows, load_reasons(ROOT / "re/delays_reasons.tsv"))
    order = {k: i for i, k in enumerate(["delay_ms", "poll", "wait_event", "timer_event", "delay_us", "status_loop", "busy_loop", "nop", "param"])}
    rows.sort(key=lambda r: (order.get(r["kind"], 9), r["linked"] != "yes", r["file"], int(r["line"] or 0), r["addr"]))
    for i, r in enumerate(rows, 1):
        r["id"] = f"D{i:03d}"
    return rows, fns, g


def state_windows(sim):
    names = ["INITIAL", "SEARCH", "DISPLAY_SETTING", "ACTIVE", "NOSUPPORT", "NOSIGNAL", "POWER_SAVING", "POWER_OFF", "FACTORY"]
    tl = sim["timeline"]
    out = []
    for i, (t, st) in enumerate(tl):
        end = tl[i + 1][0] if i + 1 < len(tl) else sim["fw_ms_at_active"]
        out.append((names[st] if st < len(names) else str(st), t if i else 0, end))
    return out


def doc(rows, sim, path: Path, a):
    lin = [r for r in rows if r["linked"] == "yes" and r["kind"] != "param"]
    blk = [r for r in lin if r["kind"] in ("delay_ms", "poll", "wait_event", "delay_us", "busy_loop")]
    by = {r["addr"]: r for r in rows if r.get("addr")}
    L = ["# Delay inventory", "",
         f"- Generated by `scripts/delay_inventory.py` from `{Path(a.map).name}` (listing of the same build + map). Table: `re/delays.tsv`; hand reasons: `re/delays_reasons.tsv`.",
         "- Build tree: the `wb-stepB` worktree at 1100f24 (image sha1 identical to `tmp/fw/AWT26110003-wb-stepB-be.bin`).",
         "- Issues: #54 (inventory), #40 (time to picture), #53 items 6/12/13.",
         "- Hand findings: the section at the end (`re/delays_notes.md`).",
         "- Linked = code present in the final link; reachable = reachable from `main` or an interrupt vector in the static call graph (function pointers not followed).",
         "- Compiled-out rows (`linked=no`) are source lines of compiled files that produced no code (`#if`, unreferenced); other chip families' sources are not scanned.", "",
         "## Counts", ""]
    c = collections.Counter((r["kind"], r["linked"].split()[0]) for r in rows)
    L += ["| kind | linked | compiled out |", "|---|---|---|"]
    for k in dict.fromkeys(r["kind"] for r in rows):
        L.append(f"| {k} | {c[(k, 'yes')]} | {c[(k, 'no')]} |")
    cls = collections.Counter(r["cls"] for r in lin if r["reachable"] == "yes")
    L += ["", "Classes of the linked, reachable sites: " + ", ".join(f"{k} {v}" for k, v in cls.most_common()) + ".",
          "- required = spec or datasheet minimum cited; shortenable = no stated need, measure; interrupt-or-poll = fixed wait where a flag or interrupt exists;",
          "  removable = no effect found; non-blocking = deferred timer event (no CPU time); unknown = not yet justified."]
    if sim:
        wins = state_windows(sim)
        hits = sim["hits"]
        tot_ms = sim["fw_ms_at_active"]
        blk_ms = sum(h[1] for h in hits)
        L += ["", "## Boot to ACTIVE budget (simulator)", "",
              f"- Image {sim['image']}, 1080p60 HDMI stub on D2, reset to mode ACTIVE: **{tot_ms} ms** firmware time (Timer2 ms), {sim['instr']} instr.",
              f"- Blocking waits measured on that path (delay_ms, poll, wait_event): **{blk_ms:.0f} ms** in {len(hits)} calls = {100 * blk_ms / tot_ms:.0f} % of the path; the rest is main-loop compute and waiting for timer events / state-machine timers.",
              "- Sim limits: the HDMI Rx PHY, HPD and PLL lock flags are not modelled, so some polls run to their bound in the sim (expired column) and the stubbed TMDS pre-detect/scan/stable functions cost nothing; "
              "Timer2 is dilated x3 to keep fw time = instr / 12.6 k per ms.", "",
              "### Time per mode state (fw ms) and blocking ms inside it", "", "| state | from ms | to ms | length ms | blocking ms | blocking calls |", "|---|---|---|---|---|---|"]
        for nm, t0, t1 in wins:
            hh = [h for h in hits if t0 <= h[0] < t1]
            L.append(f"| {nm} | {t0} | {t1} | {t1 - t0} | {sum(h[1] for h in hh):.0f} | {len(hh)} |")
        ts = sim["stages"].get("ts")
        if ts:
            L += ["", "Boot stage timestamps from the firmware's own diag block (fw ms; docs/diag-block.md): " +
                  ", ".join(f"stage {i + 1} = {v}" for i, v in enumerate(ts)) + ".",
                  "- Stage 4 to 5 (pin-share done to first main-loop pass) is compute in the sim (no blocking site fires in that window except the ones below); "
                  "stage 6 to 7 includes the panel T1 (10 ms) and the T2 HPD poll, which runs to its 250 ms bound in the sim because HPD is not modelled."]
        L += ["", "### Top 20 blocking sites by measured ms on the boot to ACTIVE path", "",
              "| id | kind | file:line | function | calls | ms total | ms/call | expired | class | stated reason |", "|---|---|---|---|---|---|---|---|---|---|"]
        top = sorted(sim["sites"].items(), key=lambda kv: -kv[1]["ms"])[:20]
        for k, s_ in top:
            r = by.get(k, {})
            L.append(f"| {r.get('id', '?')} | {s_['kind']} | {Path(r.get('file', '?')).name}:{r.get('line', '?')} | {r.get('function', '?')} | {s_['calls']} | "
                     f"{s_['ms']:.0f} | {s_['ms'] / max(s_['calls'], 1):.1f} | {s_['expired']} | {r.get('cls', '')} | {(r.get('why') or r.get('stated') or '')[:70]} |")
        L += ["", "### First-fire order, reset to ACTIVE (blocking sites)", ""]
        for k, s_ in sorted(sim["sites"].items(), key=lambda kv: kv[1]["first_ms"]):
            r = by.get(k, {})
            if s_["ms"] or s_["kind"] == "delay_ms":
                L.append(f"- {s_['first_ms']} ms ({r.get('sim_mode', '')}): {r.get('id', '?')} {r.get('function', '?')} {Path(r.get('file', '?')).name}:{r.get('line', '?')} "
                         f"{s_['kind']} arg {s_['args']}, {s_['calls']}x, {s_['ms']:.0f} ms [{r.get('cls', '')}]")
        zero = [(k, s_) for k, s_ in sim["sites"].items() if not s_["ms"] and s_["kind"] != "delay_ms"]
        L += ["", f"- {len(zero)} further wait_event/poll sites fired with 0 ms spent (event or flag already set): " +
              ", ".join(sorted({by.get(k, {}).get('function', '?') for k, _ in zero})), "",
              f"### Steady state (ACTIVE, {sim['active_window_ms']} ms window, blocking sites)", ""]
        act = sorted(((s_["act_ms"], k, s_) for k, s_ in sim["sites"].items() if s_["act_calls"]), reverse=True)
        tot_a = sum(x[0] for x in act)
        L.append(f"- Blocking time per second with a picture up: **{tot_a * 1000 / sim['active_window_ms']:.0f} ms/s** ({100 * tot_a / sim['active_window_ms']:.1f} % of the loop); "
                 "main-loop pass rate is measured on unit 3 (#11).")
        for ms, k, s_ in act:
            r = by.get(k, {})
            L.append(f"  - {r.get('id', '?')} {r.get('function', '?')} {Path(r.get('file', '?')).name}:{r.get('line', '?')} {s_['kind']}: {s_['act_calls']} calls, {ms:.0f} ms [{r.get('cls', '')}]")
        names = {}
        for r in rows:
            if r["kind"] == "timer_event":
                m = re.match(r"(\w+)\s+id=0x([0-9a-f]+)", r.get("args", ""))
                if m:
                    names[int(m.group(2), 16)] = m.group(1)
        ev = [e for e in sim["events"] if not e[4]]
        agg = collections.OrderedDict()
        for t, per, eid, react, _ in ev:
            e = agg.setdefault(eid, [t, per, 0])
            e[2] += 1
        L += ["", "### Deferred timer events armed on the boot to ACTIVE path (period = latency, no CPU)", "",
              "| first arm ms | event | id | period ms (first) | times armed |", "|---|---|---|---|---|"]
        for eid, (t, per, n) in agg.items():
            L.append(f"| {t} | {names.get(eid, '?')} | 0x{eid:02x} | {per} | {n} |")
        sh = sim.get("stub_hits", {})
        if sh:
            L += ["", "### Functions replaced by sim stubs (their real wait is not in the budget above)", "",
                  "| stub | calls | blocking inside (static) |", "|---|---|---|"]
            inside = {"ScalerTMDSNormalPreDetect": "6 ms blind per call (D081/D086, #40)", "ScalerTMDSScanInputPort": "2 ms PHY stable + HPD/format polls",
                      "ScalerTMDSStableDetect": "polls up to 45 ms"}
            for k, v in sorted(sh.items(), key=lambda kv: -kv[1]):
                L.append(f"| {k} | {v} | {inside.get(k, '')} |")
    L += ["", "## Static worst case per context (each linked, reachable site once)", "",
          "Primary context = narrowest call tree (from main handlers or an ISR) that contains the function. delay_us rows are nominal us.", "",
          "| context | sites | blind ms (delay_ms + us loops) | poll / wait bounds ms |", "|---|---|---|---|"]
    ctxs = collections.defaultdict(lambda: [0, 0.0, 0.0])
    for r in blk:
        if r["reachable"] != "yes":
            continue
        e = ctxs[r["context"]]
        e[0] += 1
        if r["kind"] in ("delay_ms", "delay_us", "busy_loop"):
            e[1] += vms(r)
        else:
            e[2] += vms(r)
    for k, e in sorted(ctxs.items(), key=lambda kv: -kv[1][1]):
        L.append(f"| {k} | {e[0]} | {e[1]:.1f} | {e[2]:.0f} |")
    isr = [r for r in blk if r["context"] == "isr" and r["reachable"] == "yes" and r["kind"] == "delay_us"]
    byf = collections.defaultdict(float)
    for r in isr:
        byf[r["function"]] += vms(r) * 1000
    L += ["", "### Blind us delays inside interrupt handlers (nominal us per call, sum of the function's sites)", ""]
    L += [f"- {f}: {v:.0f} us" for f, v in sorted(byf.items(), key=lambda kv: -kv[1])[:10]]
    L += ["", "## Candidates (linked, reachable, not required), by blind ms per call", "",
          "| id | kind | file:line | function | ms | class | reason |", "|---|---|---|---|---|---|---|"]
    cand = sorted((r for r in blk if r["reachable"] == "yes" and r["cls"] in ("shortenable", "interrupt-or-poll", "removable")), key=lambda r: -vms(r))[:25]
    for r in cand:
        L.append(f"| {r['id']} | {r['kind']} | {Path(r['file']).name}:{r['line']} | {r['function']} | {vms(r):g} | {r['cls']} | {r['why'][:80]} |")
    L += ["", "## Panel and source-search constants (resolved with sdcc -dM)", "", "| constant | value ms | class | citation |", "|---|---|---|---|"]
    for r in rows:
        if r["kind"] == "param" and r["cls"] != "unknown":
            L.append(f"| {r['args']} | {r['value']} | {r['cls']} | {r['cite'][:80]} |")
    notes = ROOT / "re/delays_notes.md"
    if notes.exists():
        L += ["", notes.read_text().rstrip()]
    path.write_text("\n".join(L) + "\n")


def main():
    global LOGF
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", default=os.environ.get("AWTO_DDC_BUILD", str(ROOT.parent / "awto-ddc-stepB")))
    ap.add_argument("--map", default=str(ROOT / "tmp/fw/AWT26110003-wb-stepB-be.map"))
    ap.add_argument("--bin", default=None)
    ap.add_argument("--sim", action="store_true")
    ap.add_argument("--out", default=str(ROOT / "re/delays.tsv"))
    ap.add_argument("--doc", default=str(ROOT / "docs/delays.md"))
    ap.add_argument("--sim-json", default=str(ROOT / "re/delays_sim.json"))
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOGF = (ROOT / "tmp/logs/delay_inventory.log").open("a")
    rows, fns, g = build_rows(a)
    sim = None
    sj = Path(a.sim_json)
    if a.sim:
        binp = Path(a.bin or a.map.replace(".map", ".bin"))
        sim = sim_measure(binp, Path(a.map), rows, sj, parse_rst.stubs, {f.addr: n for n, f in fns.items()})
    elif sj.exists():
        sim = json.loads(sj.read_text())
    if sim:
        rows = merge_sim(rows, sim)
    write_tsv(rows, Path(a.out))
    doc(rows, sim, Path(a.doc), a)
    log(f"{len(rows)} rows -> {a.out}; doc {a.doc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
