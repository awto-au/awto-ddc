#!/usr/bin/env python3
"""Run every RTD parser over an RTDCustomerTool tree, gate-first.

Usage: python -I rtd_extract_all.py <RTDCustomerTool root> [--out re] [--warn-only]
                                    [--gate-only] [--strict] [--tool-version V3.8_20221101]

1. Gate every known file (rtd_gate.py); print a table: file, kind, version, state.
2. Any FAIL (unknown version / layout drift) stops the run and names the file, unless --warn-only.
   UNSUPPORTED (known variant, no parser; e.g. DB.bin v3) is skipped and listed. --strict: WARN also stops.
3. Run parsers; outputs (derived artifacts, regenerated each run):
     <out>/regdb/<chip>.tsv.gz     rtd_db_parse.py
     <out>/gpio/<chip>.gpio.tsv.gz rtd_gpio_parse.py
     <out>/pe/<tool-version>.tsv.gz pe_resources.py
     <out>/flashdb/                rtd_flashdb_parse.py <PlugIn dir> <out.json> (only if the script exists)
     <out>/gate_report.json        the gate table
Log: ./tmp/logs/rtd_extract_all.log under the repo root. Exit: 0 ok, 3 gate refused, 5 parser failed.
Doc: docs/reversing/realtek-rtd/extraction.md
"""
import argparse
import gzip
import json
import logging
import os
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)  # -I drops script dir
import rtd_gate  # noqa: E402

WANT = {"db.bin", "gpio.bin", "dpcddb.bin", "ipdb.bin", "flashset.dat", "flash.dat",
        "swren.dat", "readall.txt", "version.txt"}
PE_EXT = (".dll", ".exe", ".ocx")
# Stall guard (no output change for this long = hung). Parsers finish in seconds; cold worst case
# measured here is the 6 MB RTD2797 DB.bin, so a single parser is capped generously above that.
PARSER_LIMIT_S = 120


def setup_log():
    d = os.path.join(rtd_gate.repo_root(), "tmp", "logs")
    os.makedirs(d, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(os.path.join(d, "rtd_extract_all.log")),
                                  logging.StreamHandler(sys.stdout)])


def find_files(root):
    out = []
    for dp, dn, fn in os.walk(root):
        if "__MACOSX" in dp:
            continue
        for f in sorted(fn):
            if f.lower() in WANT or f.lower().endswith(PE_EXT):
                out.append(os.path.join(dp, f))
    return sorted(out)


def gzip_to(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(src, "rb") as f, open(dst, "wb") as raw, \
            gzip.GzipFile(fileobj=raw, mode="wb", compresslevel=9, mtime=0) as g:
        shutil.copyfileobj(f, g)


def run(cmd, what):
    t = time.time()
    p = subprocess.run([sys.executable, "-I"] + cmd, capture_output=True, text=True, cwd=rtd_gate.repo_root(),
                       timeout=PARSER_LIMIT_S)
    logging.info("%s: rc=%d %.1fs %s", what, p.returncode, time.time() - t,
                 (p.stdout.strip().splitlines() or [""])[-1])
    if p.returncode:
        logging.error("%s FAILED rc=%d\n%s", what, p.returncode, (p.stdout + p.stderr)[-2000:])
    return p.returncode


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("root")
    ap.add_argument("--out", default=os.path.join(rtd_gate.repo_root(), "re"))
    ap.add_argument("--warn-only", action="store_true", help="continue past gate FAIL (parsers get --gate-warn-only)")
    ap.add_argument("--strict", action="store_true", help="stop on gate WARN too")
    ap.add_argument("--gate-only", action="store_true", help="print the gate table and stop")
    ap.add_argument("--tool-version", help="default: parsed from the root dir name")
    a = ap.parse_args()
    setup_log()
    root = os.path.abspath(a.root)
    tv = a.tool_version or rtd_gate.detect_tool_version(root)
    reg = rtd_gate.load_registry()
    logging.info("root=%s tool_version=%s registry validated=%s", root, tv, reg.get("tool_versions_seen"))
    if tv is None:
        logging.warning("tool version not detected (dir name lacks Vx.y_YYYYMMDD); pass --tool-version")
    elif tv not in reg.get("tool_versions_seen", []):
        logging.warning("NEW TOOL VERSION %s: not in registry tool_versions_seen %s - "
                        "every file is checked, expect gate output below to show what changed",
                        tv, reg.get("tool_versions_seen"))

    files = find_files(root)
    rows = []
    for f in files:
        rel = os.path.relpath(f, root)
        try:
            r = rtd_gate.gate(f, warn_only=True, tool_version=tv, reg=reg)
            rows.append(dict(file=rel, kind=r.kind, version=r.version, state=r.state,
                             msg=r.message() if r.state != "ok" else ""))
        except rtd_gate.GateError as e:  # unknown kind
            rows.append(dict(file=rel, kind="?", version="?", state="fail", msg=str(e)))
    w = max(len(r["file"]) for r in rows) if rows else 10
    logging.info("%-*s  %-12s %-13s %s", w, "file", "kind", "version", "state")
    for r in rows:
        logging.info("%-*s  %-12s %-13s %s", w, r["file"], r["kind"], r["version"], r["state"].upper())
    for r in rows:
        if r["msg"]:
            logging.info("  [%s] %s: %s", r["state"].upper(), r["file"], r["msg"])
    counts = {s: sum(1 for r in rows if r["state"] == s) for s in ("ok", "warn", "unsupported", "fail")}
    logging.info("gate summary: %s", counts)
    os.makedirs(a.out, exist_ok=True)
    with open(os.path.join(a.out, "gate_report.json"), "w", encoding="utf-8") as fo:
        json.dump(dict(root=root, tool_version=tv, counts=counts, files=rows), fo, indent=1)
        fo.write("\n")

    bad = [r for r in rows if r["state"] == "fail" or (a.strict and r["state"] == "warn")]
    if bad and not a.warn_only:
        for r in bad:
            logging.error("LAYOUT DRIFT / UNKNOWN VERSION: %s -> %s", r["file"], r["msg"])
        logging.error("STOP: %d file(s) failed the gate. Onboard per docs/reversing/realtek-rtd/"
                      "extraction.md (rtd_gate.py diff <file>), or rerun with --warn-only.", len(bad))
        return rtd_gate.EXIT_REFUSED
    if a.gate_only:
        return 0

    gw = ["--gate-warn-only"] if a.warn_only else []
    fail = 0
    tmp = os.path.join(rtd_gate.repo_root(), "tmp", "rtd_extract")
    os.makedirs(tmp, exist_ok=True)
    for r in rows:
        if r["kind"] != "DB.bin" or r["state"] == "unsupported":
            continue
        chip = os.path.basename(os.path.dirname(r["file"]))
        tsv = os.path.join(tmp, chip + ".tsv")
        rc = run([os.path.join(HERE, "rtd_db_parse.py"), os.path.join(root, r["file"]), tsv] + gw,
                 "regdb " + chip)
        if rc:
            fail += 1
            continue
        gzip_to(tsv, os.path.join(a.out, "regdb", chip + ".tsv.gz"))
        gp = os.path.join(root, os.path.dirname(r["file"]), "GPIO.bin")
        if os.path.exists(gp):
            gtsv = os.path.join(tmp, chip + ".gpio.tsv")
            rc = run([os.path.join(HERE, "rtd_gpio_parse.py"), gp, gtsv, "--regdb", tsv] + gw,
                     "gpio " + chip)
            if rc:
                fail += 1
            else:
                gzip_to(gtsv, os.path.join(a.out, "gpio", chip + ".gpio.tsv.gz"))
    for r in rows:
        if r["kind"] == "DB.bin" and r["state"] == "unsupported":
            logging.info("skip %s: known variant v%s, no parser", r["file"], r["version"])

    flashp = os.path.join(HERE, "rtd_flashdb_parse.py")
    plug = os.path.join(root, "PlugIn")
    if os.path.exists(flashp) and os.path.isdir(plug):
        fout = os.path.join(a.out, "flashdb", (tv or "unknown") + ".json")
        os.makedirs(os.path.dirname(fout), exist_ok=True)
        if run([flashp, plug, fout] + gw, "flashdb"):
            fail += 1
    else:
        logging.info("flashdb: rtd_flashdb_parse.py not present, FlashSet/Flash/SWREN gated only")

    ptsv = os.path.join(tmp, "pe.tsv")
    if run([os.path.join(HERE, "pe_resources.py"), root, ptsv] + gw, "pe_resources"):
        fail += 1
    else:
        gzip_to(ptsv, os.path.join(a.out, "pe", (tv or "unknown") + ".tsv.gz"))
    logging.info("done: %d parser failure(s)", fail)
    return 5 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
