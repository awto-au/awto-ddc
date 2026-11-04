#!/usr/bin/env python3
"""Decode a live RL6449 pin-share dump (page 0x10) against an SDK *_PINSHARE.h board header.

usage: rtd_pinshare_decode.py <rtd_scaler.log> <PINSHARE.h> [--out docs/.../pinshare.tsv]
       rtd_pinshare_decode.py <rtd_scaler.log> --score <PINSHARE.h> [...]   rank headers by match
       rtd_pinshare_decode.py <rtd_scaler.log> <PINSHARE.h> --emit <new.h>  header with live values
  log:    rtd_scaler.py output with `r 0xNN = 0xVV` lines after `w 0x9f <- 0x10` (last session used)
  header: per-pin `#define _156PIN_PIN_N (v & 0x0F) // Page 10-0xRR[2:0]` + `// 0 ~ k (0: ...)` options
Prints pin | reg | live | reference value | live meaning.
Paired regs (value 8 = dedicated function): DDC pairs select DDC with bit7=0, IIC/UART pairs with bit7=1
(Kernel RL6449_Series_Pinshare.c ScalerPinshareInitial). Log: ./tmp/logs/rtd_pinshare_decode.log
"""
import argparse, os, re, subprocess, sys
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parent
    try:
        out = subprocess.run(["git", "-C", str(here), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True)
        return Path(out.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return here.parent


def parse_log(path: Path) -> dict:
    """Register values from the LAST page-0x10 session in the log."""
    regs, on = {}, False
    for line in path.read_text().splitlines():
        if "w 0x9f <- 0x10" in line:
            regs, on = {}, True
        elif on and (m := re.search(r"r 0x([0-9a-f]{2}) = 0x([0-9a-f]{2})", line)):
            regs[int(m[1], 16)] = int(m[2], 16)
        elif "reset scaler" in line:
            on = False
    return regs


def parse_header(path: Path) -> list:
    pins, cur, name = [], None, ""
    for line in path.read_text(errors="replace").splitlines():
        m = re.match(r"#define\s+_(?:156PIN_)?PIN_(\w+)\s+\((\d+)\s*&\s*0x0F\)\s*//\s*Page\s*10-0x([0-9A-Fa-f]+)", line)
        if m:
            cur = {"pin": m[1], "ref": int(m[2]), "reg": int(m[3], 16), "name": name, "opts": ""}
            pins.append(cur); continue
        c = re.match(r"//\s*(.*)", line.strip())
        if not line.strip():
            cur = None                      # blank line ends a pin's option comments
        elif c and cur is not None:
            cur["opts"] += " " + c[1]
        elif c and not c[1].startswith("-"):
            name = c[1]                     # comment before a #define = signal name
    return pins


DDC_PAIR = {0x02: 0x03, 0x49: 0x4A, 0x4B: 0x4C}          # bit7=0 -> DDC
FN_PAIR = {0x20: 0x21, 0x24: 0x28, 0x3E: 0x3F, 0x40: 0x41, 0x47: 0x48}  # bit7=1 -> IIC/UART
PAIR_SECOND = {0x03: 0x02, 0x4A: 0x49, 0x4C: 0x4B, 0x21: 0x20, 0x25: 0x24, 0x26: 0x24,
               0x27: 0x24, 0x28: 0x24, 0x3F: 0x3E, 0x41: 0x40, 0x48: 0x47}


def effective(regs: dict, reg: int):
    """Live pin selection as the header encodes it (8 = dedicated function of a pair)."""
    v = regs.get(reg)
    if v is None:
        return None
    first = PAIR_SECOND.get(reg, reg)
    f = regs.get(first, 0)
    if first in DDC_PAIR and not f & 0x80:
        return 8
    if first in FN_PAIR and f & 0x80:
        return 8
    return v & 0x07


def score(regs: dict, pins: list) -> tuple:
    hit = sum(1 for p in pins if effective(regs, p["reg"]) == p["ref"])
    return hit, len(pins)


def meaning(opts: str, v: int) -> str:
    m = re.search(rf"(?<![\d])\b{v}:\s*([^,)]+)", opts)
    return m[1].strip() if m else "?"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("log"); ap.add_argument("header", nargs="?"); ap.add_argument("--out")
    ap.add_argument("--score", nargs="+", metavar="HEADER")
    ap.add_argument("--emit", metavar="NEW_H")
    a = ap.parse_args()
    root = repo_root(); (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    logf = (root / "tmp/logs/rtd_pinshare_decode.log").open("a")
    regs = parse_log(Path(a.log))
    if a.score:
        res = sorted(((score(regs, parse_header(Path(h))), Path(h).name) for h in a.score), reverse=True)
        text = "".join(f"{hit:3d}/{n:3d}  {hit / n:5.1%}  {name}\n" for (hit, n), name in res)
        sys.stdout.write(text); logf.write(text)
        return 0
    pins = parse_header(Path(a.header))
    if a.emit:
        live = {p["pin"]: effective(regs, p["reg"]) for p in pins}
        pat = re.compile(r"(#define\s+_(?:156PIN_)?PIN_(\w+)\s+\()(\d+)(\s*&\s*0x0F\))")
        def sub(m):
            v = live.get(m[2])
            return m[0] if v is None else f"{m[1]}{v}{m[4]}"
        src = Path(a.header).read_text(errors="replace")
        Path(a.emit).write_text(pat.sub(sub, src))
        logf.write(f"emit {a.emit} from {a.header} + {a.log}: {len(live)} pins\n")
        print(f"wrote {a.emit} ({len(live)} pins from live dump)")
        return 0
    rows = ["pin\tsignal(ref board)\treg\tlive\tref\tlive_meaning\tref_meaning"]
    for p in pins:
        live = regs.get(p["reg"])
        lv = effective(regs, p["reg"])
        rows.append(f"{p['pin']}\t{p['name']}\tP10_{p['reg']:02X}\t{'' if live is None else f'0x{live:02x}'}"
                    f"\t{p['ref']}\t{'' if lv is None else meaning(p['opts'], lv)}\t{meaning(p['opts'], p['ref'])}")
    text = "\n".join(rows) + "\n"
    sys.stdout.write(text); logf.write(text)
    if a.out:
        Path(a.out).write_text(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
