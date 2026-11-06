#!/usr/bin/env python3
"""Resolve LG OnScreen Control firmware endpoints into a fw_pkg_fetch source list.

usage: python3 -I fw_lmu_manifest.py <lmu_urls.txt> <out.tsv>
- lmu_urls.txt: URLs grepped from the OSC binary (lmu.lge.com/ExternalService/onscreencontrol/fw/<MODEL>/FWLatestVersion.txt).
- Each *LatestVersion.txt holds the newest zip name; the zip sits next to it. Fetched via awto-play (playwrong).
- Output TSV (vendor, package, url, notes) feeds `fw_pkg_fetch.py <out.tsv> --playwrong`.
Log: tmp/logs/fw_lmu_manifest.log
"""
import os, sys, time
from pathlib import Path

sys.path.insert(0, "/mnt/2tb/git/awto-play")
from engine import connect  # noqa: E402

STALL = 30  # s: one small text file; connect.download has its own socket timeouts


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    root = Path(os.environ.get("AWTO_DDC_REPO", Path(__file__).resolve().parent.parent))
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (root / "tmp/logs/fw_lmu_manifest.log").open("a")
    scratch = root / "tmp/lmu"; scratch.mkdir(parents=True, exist_ok=True)
    rows = ["vendor\tpackage\turl\tnotes"]
    for url in sorted(set(l.strip() for l in src.read_text().splitlines() if "LatestVersion.txt" in l and "/fw/" in l)):
        base, fn = url.rsplit("/", 1)
        model = base.rsplit("/", 1)[1]
        pre = "tbt_" if fn.startswith("TBT") else ""
        f = scratch / f"{pre}{model}.txt"
        try:
            connect.download(url, path=str(f))
            z = f.read_text(errors="replace").strip().splitlines()[0].strip()
        except Exception as e:
            msg = f"FAIL {url}: {str(e)[:120]}"; print(msg); log.write(msg + "\n"); continue
        if not z or "<" in z or " " in z or not z.lower().endswith(".zip"):
            msg = f"BAD {url}: {z[:80]!r}"; print(msg); log.write(msg + "\n"); continue
        pkg = (pre + model + "_" + z.rsplit(".", 1)[0]).lower()
        rows.append(f"lg\t{pkg}\t{base}/{z}\tLG OSC fw endpoint {url}")
        print(f"{model}\t{z}"); log.write(f"{time.strftime('%FT%T%z')} {model} {z}\n"); log.flush()
    out.write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
