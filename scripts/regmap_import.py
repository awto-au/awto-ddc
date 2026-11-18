#!/usr/bin/env python3
"""Import register dumps into the observation store re/regmap/obs (README: re/regmap/README.md, "Add an observation").

usage: regmap_import.py FILE.json ... [--label L] [--method isp|live|regdump] [--state S] [--uptime SECONDS] [--force] [--dry-run] [--out DIR]
Formats (detected):
  isp     {"serial","time","pages":{"PP":[256 ints]},"ports":{"PPAA":{idx:val} | "AA:DD":[vals]}}   tmp/regs/<serial>-[label-]<date>-<time>[-label].json
  dict    pages {"PP":{"OFF":"hh hh ..."}} (partial reads, e.g. audio_test.py rd)
  live    scripts/reg_live_scan.py output: {"serial","unit","label","start","pages":{"PP":[256 ints|null]},"excluded":[...],"link_off":..}
Skipped with a message: gpio / power-state / DPCD JSON (no register pages).
Defaults: isp dump -> state halted+reset; live scan -> state running; a dump carrying a "note" (debug-link read) -> method regdump, state running.
Never stored: HDCP key / port registers (regmap_lib.EXCLUDE_KEYS). Existing (serial,label,time) files are kept unless --force.
Log: ./tmp/logs/regmap.log
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regmap_lib as L  # noqa: E402


def iso(t):
    """'2026-11-05T12:13:55+1100' -> '2026-11-05T12:13:55+11:00'"""
    m = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)([+-]\d\d):?(\d\d)$", t or "")
    return f"{m.group(1)}{m.group(2)}:{m.group(3)}" if m else (t or "")


def label_from_name(name, serial):
    m = re.match(rf"^{serial}-(?:(.*?)-)?(\d{{8}})-(\d{{6}})(?:-(.*))?$", Path(name).stem)
    if not m:
        return "none"
    return "-".join(x for x in (m.group(1), m.group(4)) if x) or "none"


def to_vals(d):
    """-> {key: int} from the pages / ports of one JSON document (HDCP keys dropped)"""
    vals = {}
    for p, v in (d.get("pages") or {}).items():
        p = p.upper().zfill(2)
        if isinstance(v, list):
            for i, x in enumerate(v):
                if x is not None:
                    vals[f"{p}{i:02X}"] = int(x, 16) if isinstance(x, str) else int(x)
        else:
            for off, hexs in v.items():
                for i, t in enumerate(hexs.split()):
                    vals[f"{p}{int(off, 16) + i:02X}"] = int(t, 16)
    for k, v in (d.get("ports") or {}).items():
        base = "00" + k.split(":")[1].zfill(2).upper() if ":" in k else k.upper().zfill(4)
        items = v.items() if isinstance(v, dict) else enumerate(v)
        for i, x in items:
            if x is not None:
                vals[f"{base}:{int(i):02X}"] = int(x)
    return {k: x for k, x in vals.items() if k.partition(":")[0] not in L.EXCLUDE_KEYS}


def convert(path, a):
    d = json.loads(Path(path).read_text())
    if not isinstance(d, dict) or "serial" not in d or not isinstance(d.get("pages"), dict):
        return None, "no register pages"
    vals = to_vals(d)
    if not vals:
        return None, "no values"
    serial = d["serial"]
    live = "diag_header" in d or "excluded" in d
    t = iso(d.get("start") or d.get("time"))
    note = d.get("note") or ""
    method = a.method or ("live" if live else ("regdump" if note else "isp"))
    state = a.state or ("halted+reset" if method == "isp" else ("frozen" if "frozen" in Path(path).name else "running"))
    label = a.label or d.get("label") or label_from_name(path, serial)
    meta = {"source": Path(path).name, "serial": serial, "unit": str(d.get("unit") or serial[-1]), "label": re.sub(r"[^A-Za-z0-9+_.-]", "_", label),
            "state": state, "method": method, "time": t, "uptime_s": a.uptime or "", "bus": str(d.get("bus", "")),
            "image": d.get("image", ""), "note": note.replace("\t", " ").replace("\n", " ")}
    stamp = re.sub(r"[^0-9T]", "", t[:19]).replace("T", "-")
    return (f"{serial}-{meta['label']}-{stamp}", meta, vals), ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--label")
    ap.add_argument("--method", choices=["isp", "live", "regdump"])
    ap.add_argument("--state")
    ap.add_argument("--uptime")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=str(L.OBS))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in a.files:
        try:
            res, why = convert(f, a)
        except (OSError, ValueError, KeyError) as e:
            L.log(f"import {f}: skipped ({e})")
            continue
        if res is None:
            L.log(f"import {Path(f).name}: skipped ({why})")
            continue
        stem, meta, vals = res
        dst = out / f"{stem}.tsv.gz"
        if dst.exists() and not a.force:
            L.log(f"import {Path(f).name}: exists {dst.name}")
            continue
        if not a.dry_run:
            L.write_obs(dst, meta, vals)
        n += 1
        L.log(f"import {Path(f).name}: {len(vals)} values -> {dst.name} ({meta['method']}, {meta['state']})")
    L.log(f"regmap_import: {n} file(s) written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
