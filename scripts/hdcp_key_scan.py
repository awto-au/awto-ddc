#!/usr/bin/env python3
"""Locate HDCP 1.4 / 2.2 key records in flash dumps; prints offsets, lengths, hashes only (never key bytes).

usage: hdcp_key_scan.py diff DUMP...         4 KiB sectors that differ between dumps (vs the first)
       hdcp_key_scan.py scan DUMP...         HDCP2 certrx candidates per dump (RxID popcount 20, e = 65537)
       hdcp_key_scan.py sdk DUMP...          where the SDK HdcpRxKey.h tables (customer / errata branch) occur
Log: tmp/logs/hdcp_key_scan.log, offsets and lengths only; key hashes go to stdout only (awto-ddc#44).
"""
import hashlib
import os
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).parent,
                             capture_output=True, text=True, check=True).stdout.strip()
        return Path(out)
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


LOG = repo_root() / "tmp" / "logs" / "hdcp_key_scan.log"
SECTOR = 4096
BANK = 0x10000


def log(msg: str, sha: str = "") -> None:
    """Key hashes go to stdout only, never the log file (awto-ddc#44: no key material in logs)."""
    print(msg + (f" sha {sha}" if sha else ""))
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(msg + "\n")


def h(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def runs(offsets):
    """Merge sorted offsets into [start, end) runs."""
    out = []
    for o in offsets:
        if out and o == out[-1][1]:
            out[-1][1] = o + 1
        else:
            out.append([o, o + 1])
    return out


def cmd_diff(paths):
    ref = Path(paths[0]).read_bytes()
    log(f"diff ref {Path(paths[0]).name}", h(ref))
    for p in paths[1:]:
        d = Path(p).read_bytes()
        secs = [s for s in range(0, len(ref), SECTOR) if ref[s:s + SECTOR] != d[s:s + SECTOR]]
        log(f"  {Path(p).name}: {len(secs)} sectors differ")
        for s in secs:
            byte_runs = runs([i for i in range(s, s + SECTOR) if ref[i] != d[i]])
            span = f"{byte_runs[0][0]:#07x}..{byte_runs[-1][1]:#07x}"
            log(f"    sector {s:#07x} bank {s // BANK} +{s % BANK:#06x}: {sum(e - b for b, e in byte_runs)} bytes"
                f" in {len(byte_runs)} runs, span {span}")


def popcount(b: bytes) -> int:
    return sum(bin(x).count("1") for x in b)


def cmd_scan(paths):
    for p in paths:
        d = Path(p).read_bytes()
        log(f"scan {Path(p).name}")
        # HDCP2 certrx: RxID(5) n(128) e=0x010001(3) ver(2) sig(384) = 522 B; e sits at +133.
        cert = [i - 133 for i in range(133, len(d) - 389) if d[i:i + 3] == b"\x01\x00\x01"
                and d[i + 3:i + 5] in (b"\x00\x00", b"\x10\x00", b"\x20\x00", b"\x00\x01")
                and popcount(d[i - 133:i - 128]) == 20]
        for c in cert:
            log(f"  hdcp2 certrx candidate @ {c:#07x} bank {c // BANK} +{c % BANK:#06x} len 522"
                " rxid-popcount 20", h(d[c:c + 522]))
        if not cert:
            log("  hdcp2 certrx: none")


SDK_KEYS = repo_root() / "fw" / "sdk" / "Kernel" / "User Common Function" / "Header" / "HdcpRxKey.h"


def sdk_tables(errata: int) -> dict:
    """SDK HdcpRxKey.h arrays as bytes (RX, RSA1024 branch), via the host C preprocessor."""
    import re
    cpp = subprocess.run(["cpp", "-P", "-D_ON=1", "-D_OFF=0", "-D_HDCP_2_2_SUPPORT=1",
                          f"-D_HDCP_2_2_ERRATA_TEST_SUPPORT={errata}", "-D_HDCP_2_2_TX_RSA3072_MODE=0",
                          "-D_HDCP_2_2_TX_RRMODN_BY_HW=0", str(SDK_KEYS)],
                         capture_output=True, text=True, check=True).stdout
    return {m.group(1): bytes(int(x, 16) for x in re.findall(r"0x([0-9A-Fa-f]{2})", m.group(2)))
            for m in re.finditer(r"(\w+)\[\]\s*=\s*\{(.*?)\};", cpp, re.S)}


def find_all(d: bytes, needle: bytes):
    out, i = [], d.find(needle)
    while i >= 0:
        out.append(i)
        i = d.find(needle, i + 1)
    return out


def cmd_sdk(paths):
    """Is any SDK sample key table (customer or errata branch) present in the dump?"""
    for errata in (0, 1):
        for name, t in sdk_tables(errata).items():
            for p in paths:
                d = Path(p).read_bytes()
                hits = find_all(d, t)
                log(f"sdk errata={errata} {name} len {len(t)} in {Path(p).name}: "
                    f"{', '.join(f'{o:#07x}' for o in hits) or 'absent'}", h(t))


def cmd_main(argv):
    {"diff": cmd_diff, "scan": cmd_scan, "sdk": cmd_sdk}[argv[0]](argv[1:])


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    cmd_main(sys.argv[1:])


if __name__ == "__main__":
    main()
