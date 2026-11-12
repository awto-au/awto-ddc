#!/usr/bin/env python3
"""Park SDK sources that link 0 B: move them from fw/sdk to fw/sdk-parked (same relative path), out of the build (#165).

usage: sdk_park.py list            candidates -> tmp/audit/park.tsv (group, path, why)
       sdk_park.py move [--dry]    git mv the candidates, drop #include lines of parked headers from fw/sdk
- Candidates (from the last build in this tree, tmp/sdcc-port/asm_bank/_size/*.rel):
  module   a compiled module whose areas are all 0 B (REG_BANK_0 / SSEG excepted) -> its .c (unique stem in fw/sdk)
  chip     board headers of another scaler (Pcb/, RL6193 / RL6369 / RL6410 / RL6432 / RL6463 / RL6492 / RLE0779), all under
           #if(_PCB_TYPE == ...); NOT their Kernel/Common *_Default.h / *_Gen_Option.h and Project/Header *_Project.h: those are
           included unconditionally and their #ifndef defaults define 404 macros the RL6449 build reads (#165)
- Groups (README one line each) by path / name pattern: GROUPS, first match wins; `other` = no pattern matched.
- After `move`: the build must give the same image (byte-identical apart from the build tag): check with a rebuild.
Log: ./tmp/logs/sdk_park.log
"""
import re, subprocess, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SDK, PARK = ROOT / "fw/sdk", ROOT / "fw/sdk-parked"
SIZE = ROOT / "tmp/sdcc-port/asm_bank/_size"
CHIP = re.compile(r"RL6(193|369|410|432|463|492)|RLE0779")
KEEP_AREAS = {"REG_BANK_0", "SSEG"}
GROUPS = [                                   # (group, regex on the path): README groups
    ("chip", CHIP), ("mhl", re.compile(r"MHL", re.I)), ("od", re.compile(r"(^|/)(ScalerOD|RL6449_Series_OD|RL6449_Series_QC_OD)")),
    ("uniformity", re.compile(r"Uniformity|DisplayCalibration")), ("dimming", re.compile(r"Dimming")),
    ("dptx", re.compile(r"DPTx|DPRxMST|DpTx")), ("hdcp2", re.compile(r"HDCP2")), ("freesync", re.compile(r"FreeSync")),
    ("typec", re.compile(r"TypeC|Typec|PortController|UsbHub|USB3|Pmic|SeamlessChg")), ("cec", re.compile(r"Cec")),
    ("hdr", re.compile(r"HDR")), ("vga", re.compile(r"VGA|ADC|Auto|ModeSearch|SyncProc|LCTank")),
    ("qc", re.compile(r"_QC_|Autotest")), ("memory", re.compile(r"DDR1|DDR3|SDRAM|ScalerFRC|ScalerMbr|Rotation")),
    ("dvi", re.compile(r"DualLinkDVI|TMDSRx1_|TMDSRx4_|TMDSRx5_|DPRx0")), ("misc", re.compile(r".")),
]
LOG = None


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line); LOG.write(line + "\n"); LOG.flush()


def zero_modules():
    out = []
    for f in sorted(SIZE.glob("*.rel")):
        sizes = [(m.group(1), int(m.group(2), 16)) for m in
                 re.finditer(r"^A (\w+) size ([0-9A-Fa-f]+)", f.read_text(errors="replace"), re.M)]
        if all(n in KEEP_AREAS or s == 0 for n, s in sizes):
            out.append(f.stem)
    return out


def candidates():
    by_stem = {}
    for p in SDK.rglob("*.c"):
        by_stem.setdefault(p.stem, []).append(p)
    rows = []
    for stem in zero_modules():
        ps = by_stem.get(stem, [])
        if len(ps) != 1:
            log(f"module {stem}: {len(ps)} sources in fw/sdk, not parked")
            continue
        rows.append((ps[0].relative_to(SDK).as_posix(), "module: 0 B linked"))
    for p in sorted(SDK.rglob("*")):
        if p.is_file() and CHIP.search(p.name) and p.relative_to(SDK).parts[0] == "Pcb":
            rows.append((p.relative_to(SDK).as_posix(), "chip: another scaler"))
    seen, out = set(), []
    for r, why in rows:
        if r not in seen:
            seen.add(r)
            out.append((next(g for g, rx in GROUPS if rx.search(r)), r, why))
    return sorted(out)


def git(*a):
    r = subprocess.run(["python3", "/mnt/2tb/git/awto-dan/scripts/gh_claudia.py", "git", *a], cwd=ROOT, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"git {' '.join(a[:2])}: {r.stderr.strip()[-300:]}")


def main() -> int:
    global LOG
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    (ROOT / "tmp/audit").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp/logs/sdk_park.log").open("a")
    a = sys.argv[1:]
    if not a or a[0] not in ("list", "move"):
        print(__doc__); return 2
    rows = candidates()
    (ROOT / "tmp/audit/park.tsv").write_text("group\tpath\twhy\n" + "".join(f"{g}\t{p}\t{w}\n" for g, p, w in rows))
    groups = {}
    for g, _, _ in rows:
        groups[g] = groups.get(g, 0) + 1
    log(f"{len(rows)} files: {groups} -> tmp/audit/park.tsv")
    if a[0] == "list" or "--dry" in a:
        return 0
    for _, r, _ in rows:
        if not (SDK / r).exists():
            continue                                 # parked already
        (PARK / r).parent.mkdir(parents=True, exist_ok=True)
        git("mv", str(SDK / r), str(PARK / r))
    names = {Path(r).name for _, r, _ in rows if r.endswith(".h")}
    inc = re.compile(r'^[ \t]*#[ \t]*include[ \t]+"([^"]+)"[^\n]*\n', re.M)
    for p in sorted(SDK.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in (".h", ".c"):
            continue
        t = p.read_text(encoding="latin-1")
        new = inc.sub(lambda m: "" if Path(m.group(1)).name in names else m.group(0), t)
        if new != t:
            p.write_text(new, encoding="latin-1")
            log(f"{p.relative_to(ROOT)}: {t.count(chr(10)) - new.count(chr(10))} #include lines of parked headers removed")
    log(f"moved {len(rows)} files to {PARK.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
