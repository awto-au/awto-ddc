#!/usr/bin/env python3
"""Clean-room inventory: every linked function / const of a firmware image by origin and #65 plan step (map + object list).

usage: fw_inventory.py MAP [--tsv OUT.tsv] [--sdk PATH]
  MAP: sdld map of an SDCC build (tmp/fw/<tag>.map or tmp/fw/<serial>/fw.map). Areas CH_<sym> (one per fn / const, sdcc_bank)
  are attributed to their module; the module (from the map's "Files Linked" object list) to its source file in the SDK,
  fw/sdk or fw/sdcc; the source path to an origin; origin + names to a plan step (STEP_RULES, first match wins).
  Other code areas (CSEG lib runtime, HOME, GSINIT, ST_ bank stubs, vectors) are rows of origin "runtime".
  Prints the origin and step tables (markdown); writes one row per symbol to --tsv
  (default tmp/logs/fw_inventory_<tag>.tsv): origin step module source kind symbol bytes addr.
Log: tmp/logs/fw_inventory.log
"""
from __future__ import annotations

import argparse, os, re, subprocess, sys, time
from collections import Counter, defaultdict
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).parent,
                                            text=True, stderr=subprocess.DEVNULL).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


ROOT = repo_root()
SDK = Path(os.environ.get("RTD_SDK", "/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST"))
AREA = re.compile(r"^(\w+)\s+([0-9A-F]{8})\s+([0-9A-F]{8}) =\s+(\d+)\. bytes \(([^)]*)\)", re.M)
GLOBAL = re.compile(r"^C:\s+([0-9A-F]{8})\s+(\S+)\s*(\S*)\s*$", re.M)
LIB_DIR = "/Lib/"
ORIGINS = [      # (origin, regex on the SDK-relative source path), first match wins
    ("FunctionLib (built from source)", r"/Lib/"),
    ("User/RTD2014Osd (demo UI)", r"^User/RTD Series/RTD2014Osd/"),
    ("User/RTD Factory", r"^User/.*Factory"),
    ("User/RTD2014Function (demo user layer)", r"^User/RTD Series/RTD2014Function/"),
    ("User/other", r"^User/"),
    ("Kernel/UserCommon", r"^Kernel/User Common Function/"),
    ("Kernel/System (Sys*)", r"^Kernel/System/"),
    ("Kernel/Scaler drivers", r"^Kernel/"),
    ("Pcb/Panel/Project", r"^(Pcb|Panel|Project)/"),
    ("Ours: fw/sdcc", r"^fw/sdcc/"),
    ("Ours: fw/<subsystem>", r"^fw/(osd|nvram|keys|power|input|log|test|diag|dp|timer|meas|ddcci|net|audio)/"),
]
STEP_RULES = [   # (step, regex on "origin|module|symbol"), first match wins; heuristic: the inventory review fixes misfiles
    ("15 Awto* port", r"\|_?Awto"),
    ("5 factory menu (our OSD)", r"Factory"),
    ("12 DP PHY CTS (public DP spec)", r"CTS|PhyCts|DpTxCts"),
    ("8 gamma LUTs (maths)", r"RTD2014Function.*Gamma|\|tGAMMA|Gamma.*\|t[A-Z]"),
    ("6 flash table (datasheets)", r"\|_?t?FLASH_|Flash(Type|ID|Id|Table|Detect|Identify)|SerialFlash"),
    ("1 drop: VGA/ADC", r"\|.*(VGA|Vga|ADC|Adc|Auto(?:Func|Phase|Clock))"),
    ("13 HDCP", r"HDCP|Hdcp"),
    ("12 DP RX", r"DpRx|DPRx|DP_RX|DpAux|Dpcd|DPCD|_DP\b|ScalerDp[A-Z]|DpMac|DpPhyRx"),
    ("11 HDMI RX", r"TMDS|Tmds|HDMI|Hdmi|MHL|Mhl|Scdc|SCDC"),
    ("9 panel + eDP TX", r"DPTx|DpTx|DPTX|Panel|DisplayDPTx|Backlight|Lvds|LVDS"),
    ("14 DDR/FRC", r"DDR|Ddr|FRC|Frc"),
    ("4 OSD engine", r"FunctionLib.*\|Osd|ScalerOsd"),
    ("5 OSD UI", r"RTD2014Osd|demo UI|demo user layer"),
    ("6 NVRAM/flash", r"NVRam|Nvram|Flash|EEPROM|Eeprom"),
    ("7 DDC/CI + debug", r"Ddcci|DDCCI|Debug|Ddc|DDC|Iic|IIC"),
    ("3 timer/delay", r"Timer|Delay"),
    ("2 helpers", r"ScalerCommonReg|DataPort|BurstWrite|ComputeDword|MultiByte|\|_?Scaler(Set|Get)(Byte|Bit|Word|DWord)"),
    ("8 mode path", r"Measure|Vgip|VGIP|MDomain|Memory|PLL|Pll|Scaling|Color|FmtCnv|FormatConversion|IDomain|DDomain|"
                    r"Mode|Sync|Global|Display|Interlace|Rotation|Audio"),
    ("10 Sys flow", r"System \(Sys|\|Sys|UserCommon|User/other|Pcb|Project|Mcu|Int|Power|Source|Interface"),
]
LOG = None


def log(s: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, file=sys.stderr)
    if LOG:
        LOG.write(line + "\n"); LOG.flush()


def source_index(sdk: Path) -> dict:
    """stem (as compiled: asm/rel name) -> source path relative to its tree root; RL6449 copies preferred."""
    idx = {}
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fw_dirs
    roots = [(sdk, ""), (ROOT / "fw" / "sdk", ""), (ROOT / "fw" / "sdcc", "fw/sdcc/"),
             *((d, f"fw/{d.name}/") for d in fw_dirs.our_dirs(ROOT))]
    for base, prefix in roots:
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if p.suffix.lower() not in (".c", ".asm") or ".git" in p.parts:
                continue
            rel = prefix + str(p.relative_to(base))
            old = idx.get(p.stem)
            if old is None or ("RL6449" in rel and "RL6449" not in old):
                idx[p.stem] = rel
    return idx


def linked_modules(txt: str) -> list[str]:
    return [Path(m).stem for m in re.findall(r"^(/\S+\.rel)\s*$", txt, re.M)]


def areas(txt: str):
    """yield (area, addr, size, attrs, [(sym, module)])"""
    ms = list(AREA.finditer(txt))
    for i, m in enumerate(ms):
        end = ms[i + 1].start() if i + 1 < len(ms) else len(txt)
        syms = [(g.group(2), g.group(3)) for g in GLOBAL.finditer(txt, m.end(), end)]
        yield m.group(1), int(m.group(2), 16), int(m.group(4)), m.group(5), syms


def resolve_module(trunc: str, mods: list[str]) -> str:
    if trunc in mods:
        return trunc
    hits = [m for m in mods if m.startswith(trunc)]
    return hits[0] if len(hits) == 1 else trunc


def origin_of(src: str, sym: str) -> str:
    if sym.lstrip("_").startswith("Awto"):
        return "Ours: Awto* inserts"
    if not src:
        return "runtime (crt/bank/mcs51.lib)"
    return next((o for o, rx in ORIGINS if re.search(rx, src)), "other")


def step_of(origin: str, module: str, sym: str) -> str:
    key = f"{origin}|{module}|{sym}"
    if origin.startswith("runtime"):
        return "- runtime"
    return next((s for s, rx in STEP_RULES if re.search(rx, key)), "? unassigned")


def inventory(map_path: Path, sdk: Path):
    txt = map_path.read_text(errors="replace")
    mods = linked_modules(txt)
    src = source_index(sdk)
    rows = []
    for name, addr, size, attrs, syms in areas(txt):
        if "CODE" not in attrs or size == 0:
            continue
        if name.startswith("CH_"):
            sym, trunc = (syms[0] if syms else ("_" + name[3:], ""))
            mod = resolve_module(trunc, mods)
            s = src.get(mod, "")
            bare = sym.lstrip("_")
            kind = "const" if re.match(r"t[A-Z_]|ti[A-Z_]|c[A-Z_]{2}", bare) else "fn"
            o = origin_of(s, sym)
            rows.append((o, step_of(o, mod, bare), mod, s, kind, bare, size, addr))
        else:
            kind = "stub" if name.startswith("ST_") else "runtime"
            rows.append(("runtime (crt/bank/mcs51.lib)", "- runtime", "", "", kind, name, size, addr))
    return rows, mods


def table(rows, col: int, title: str) -> list[str]:
    agg = defaultdict(lambda: [0, 0, 0])
    for r in rows:
        a = agg[r[col]]
        if r[4] == "fn":
            a[0] += 1; a[1] += r[6]
        elif r[4] == "const":
            a[2] += r[6]
        else:
            a[1] += r[6]
    L = [f"| {title} | fns | code B | const B |", "|---|---|---|---|"]
    for k, (n, c, k2) in sorted(agg.items(), key=lambda kv: -(kv[1][1] + kv[1][2])):
        L.append(f"| {k} | {n} | {c:,} | {k2:,} |")
    tot = [sum(v[i] for v in agg.values()) for i in range(3)]
    L.append(f"| total | {tot[0]} | {tot[1]:,} | {tot[2]:,} |")
    return L


def main() -> int:
    global LOG
    ap = argparse.ArgumentParser()
    ap.add_argument("map", type=Path)
    ap.add_argument("--tsv", type=Path)
    ap.add_argument("--sdk", type=Path, default=SDK)
    a = ap.parse_args()
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/fw_inventory.log").open("a")
    rows, mods = inventory(a.map, a.sdk)
    tag = a.map.stem if a.map.stem != "fw" else a.map.parent.name
    out = a.tsv or ROOT / f"tmp/logs/fw_inventory_{tag}.tsv"
    out.write_text("origin\tstep\tmodule\tsource\tkind\tsymbol\tbytes\taddr\n"
                   + "".join("\t".join(map(str, r[:7])) + f"\t{r[7]:06x}\n" for r in rows))
    print("\n".join(table(rows, 0, "Origin")) + "\n\n" + "\n".join(table(rows, 1, "Plan step")))
    unk = Counter(r[2] for r in rows if r[1] == "? unassigned")
    log(f"{a.map}: {len(mods)} objects linked, {len(rows)} symbols, {sum(unk.values())} unassigned "
        f"(top modules {unk.most_common(5)}) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
