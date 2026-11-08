#!/usr/bin/env python3
"""GPIO pin table of the Dahua firmware (original JXC 4K firmware) compared with our board header.

usage: dahua_gpio_audit.py [--header FILE] [--out FILE]
- Port registers PORTxx_PIN_REG 0xFE00-0xFE37: export regwrites/regreads.tsv of the 7 banks + re/jxc-4k/reg_audit_resolved.tsv
  (pointer writes resolved by dahua_reg_audit.py, e.g. 0xFE2F/0xFE30 via 5:e222).
- SFR bits (P1, P3) are not in the export: SFR_SITES below is curated from the disassembly; every entry is checked against the
  bank bytes (opcode + bit address) so a wrong address fails loudly.
- Header = our board header (fw/overlay/Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h in the awto-ddc-keys checkout, $AWTO_DDC_KEYS_REPO).
Output: re/jxc-4k/gpio_audit.tsv ; log: ./tmp/logs/dahua_gpio_audit.log
"""
import argparse, csv, os, re, sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
SRC = Path("/mnt/2tb/vendors/realtek/analysis/jxc-4k")
BANKS = SRC.parent / "banks"
KEYS = Path(os.environ.get("AWTO_DDC_KEYS_REPO", "/mnt/2tb/git/awto-ddc-keys"))
HDR = KEYS / "fw/overlay/Pcb/RL6449/LQFP_216/RL6449_AWTO_JXC4K.h"
LOG = ROOT / "tmp/logs/dahua_gpio_audit.log"

# port.bit -> pin (docs/monitors/pinshare-live-AWT26110003.tsv, tmp/regs/*gpio*.json)
PIN = {"P1.0": 1, "P1.1": 14, "P3.0": 71, "P3.5": 91, "P3.6": 92, "P4.1": 96, "P4.2": 97, "P4.5": 113, "P7.2": 159, "P7.3": 160,
       "P7.4": 161, "P8.4": 184, "P8.5": 185, "P8.6": 190, "P9.0": 194, "P9.2": 196, "P9.4": 198, "P9.7": 201, "PA.0": 202,
       "PA.2": 204, "PA.3": 206, "PA.4": 207, "PA.5": 208}
PORTCH = "0123456789A"


def reg_port(a):
    """0xFE00 + 8*n + bit  (P4.0 = FE00 ... PA.5 = FE35)"""
    n, bit = divmod(a - 0xFE00, 8)
    port = n + 4
    return f"P{PORTCH[port] if port < 10 else 'A'}.{bit}"


# curated SFR sites: (port.bit, bank, addr, opcode, bit address, kind, function)
SFR_SITES = [
    ("P1.0", 5, 0xD2B6, 0xD2, 0x90, "set", "ScalerMcuGpioInitial"),
    ("P1.1", 5, 0xD2B4, 0xD2, 0x91, "set", "ScalerMcuGpioInitial"),
    ("P1.0", 5, 0xF748, 0xD2, 0x90, "set", "D3 HPD (5:f722)"),
    ("P1.0", 5, 0xF933, 0xC2, 0x90, "clear", "D3 HPD (5:f917)"),
    ("P1.1", 5, 0xF799, 0xD2, 0x91, "set", "D2 HPD (5:f774)"),
    ("P1.1", 5, 0xFA4E, 0xC2, 0x91, "clear", "D2 HPD (5:fa36)"),
    ("P3.5", 5, 0xD311, 0xD2, 0xB5, "set", "ScalerMcuGpioInitial"),
    ("P3.6", 5, 0xD313, 0xC2, 0xB6, "clear", "ScalerMcuGpioInitial"),
    ("P3.5", 1, 0xD6F1, 0xD2, 0xB5, "set", "d6b2 LED switch"),
    ("P3.6", 1, 0xD6F3, 0xC2, 0xB6, "clear", "d6b2 LED switch"),
    ("P3.5", 1, 0xD6F6, 0xC2, 0xB5, "clear", "d6b2 LED switch"),
    ("P3.6", 1, 0xD6F8, 0xD2, 0xB6, "set", "d6b2 LED switch"),
    ("P3.5", 1, 0xD6FB, 0xC2, 0xB5, "clear", "d6b2 LED switch"),
    ("P3.6", 1, 0xD6FD, 0xC2, 0xB6, "clear", "d6b2 LED switch"),
    ("P3.5", 1, 0xD700, 0xD2, 0xB5, "set", "d6b2 LED switch"),
    ("P3.6", 1, 0xD703, 0xD2, 0xB6, "set", "d6b2 LED switch"),
]


def log(msg, fh=[None]):
    if fh[0] is None:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        fh[0] = open(LOG, "w")
    print(msg)
    fh[0].write(msg + "\n")
    fh[0].flush()


def rows(path):
    with open(path, newline="") as f:
        return list(csv.DictReader([l for l in f if not l.startswith("#")], delimiter="\t"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--header", default=str(HDR))
    ap.add_argument("--out", default=str(ROOT / "re/jxc-4k/gpio_audit.tsv"))
    a = ap.parse_args()
    acc = defaultdict(lambda: {"w": set(), "r": set()})
    seen = set()
    for b in range(7):
        for kind, tag in (("regwrites", "w"), ("regreads", "r")):
            for r in rows(SRC / f"bank{b}" / f"{kind}.tsv"):
                if r["reg_addr"] == "?" or not (0xFE00 <= int(r["reg_addr"], 16) <= 0xFE37):
                    continue
                ia = int(r["insn"], 16)
                key = (tag, r["reg_addr"], r["insn"] if ia < 0x2586 else (b, r["insn"]))
                if key in seen:
                    continue
                seen.add(key)
                val = r.get("value") or "?"
                acc[reg_port(int(r["reg_addr"], 16))][tag].add(f'{r["func"]}@{b}:{r["insn"]}' + (f"={val}" if tag == "w" else ""))
    res = ROOT / "re/jxc-4k/reg_audit_resolved.tsv"
    if res.exists():
        for r in rows(res):
            ad = int(r["addr"], 16)
            if 0xFE00 <= ad <= 0xFE37:
                acc[reg_port(ad)]["w" if r["kind"] == "write" else "r"].add(f'{r["func"]}@{r["bank"]}:{r["insn"]} ({r["via"]})')
    for port, bank, ad, op, bit, kind, fn in SFR_SITES:
        img = (BANKS / f"bank{bank}.bin").read_bytes()
        if img[ad] != op or img[ad + 1] != bit:
            sys.exit(f"SFR site {port} {bank}:{ad:04x} does not match the bank bytes ({img[ad]:02x} {img[ad+1]:02x})")
        acc[port]["w"].add(f"{fn}@{bank}:{ad:04x}={kind}")
    acc["P3.0"]["r"].add("key_scan_adc@6:3a61 (JB 0xB0, power key)")
    hdr = Path(a.header).read_text() if Path(a.header).exists() else ""
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(["pin", "port", "dahua_writes", "dahua_reads", "in_our_header", "header_line"])
        for port in sorted(acc, key=lambda p: (PIN.get(p, 999), p)):
            e = acc[port]
            m = re.search(rf"^#define\s+\w+\s+\((?:MCU_FE\w+_PORT{port[1]}{port[3]}_PIN_REG|P{port[1]}_{port[3]})\).*$", hdr, re.M)
            w.writerow([PIN.get(port, "?"), port, "; ".join(sorted(e["w"])), "; ".join(sorted(e["r"])), "yes" if m else "NO", m.group(0).strip() if m else ""])
            log(f"{PIN.get(port, '?'):>4} {port:5} writes {len(e['w']):2} reads {len(e['r']):2} header {'yes' if m else 'NO'}")
    log(f"wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
