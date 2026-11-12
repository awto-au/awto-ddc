#!/usr/bin/env python3
"""Size / RAM row per firmware image: code bytes, common_end, XDATA/DATA/IDATA used and free, _PARM_ bytes, stack (#11).

usage: fw_ram_report.py --img STEM [--build build.json] [--asm DIR] [--stack fw_stack.txt] [--name NAME] ...
  repeat the group per image (each --img starts a new image). STEM = <stem>.bin with <stem>.map beside it.
  --build: fw_build's build.json (common_end, free direct IRAM); --asm: that build's tmp/sdcc-port/asm_bank (_PARM_ sizes;
  the map cuts names at 32 chars); --stack: fw_stack.txt (worst-case main + ISR).
  XDATA window = firmware RAM 0xE780..0xF6D0 (diag block above, fw_build xdata_holes[0]).
Output: markdown table to stdout. Log: tmp/logs/fw_ram_report.log
"""
import argparse, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fw_sim as F  # noqa: E402

XRAM = (0xE780, 0xF6D0)
AREA = re.compile(r"^(\w+)\s+([0-9A-F]{8})\s+([0-9A-F]{8}) =\s+\d+\. bytes \(([^)]*)\)", re.M)


def areas(mp: str) -> dict:
    out = {}
    for m in AREA.finditer(mp):
        out[m.group(1)] = (int(m.group(2), 16), int(m.group(3), 16), m.group(4))
    return out


def parm_bytes(asm: Path) -> dict:
    """{space: bytes} of _PARM_ slots (bit slots counted in bits) from the post-bank asm."""
    tot = {"xdata": 0, "data": 0, "bit": 0}
    for f in asm.rglob("*.asm"):
        if "_size" in f.relative_to(asm).parts:            # sdcc_bank's size-probe copy, not linked
            continue
        cur, parm = None, False
        for line in f.read_text(errors="replace").splitlines():
            m = re.match(r"\s+\.area\s+(\w+)", line)
            ds = re.match(r"\s+\.ds\s+(\d+)", line)
            if m:
                cur = m.group(1)
            elif ds and parm and cur:
                sp = "bit" if cur.startswith("BSEG") else "xdata" if cur.startswith(("XSEG", "PSEG")) else "data"
                tot[sp] += int(ds.group(1))
            parm = bool(re.match(r"_\w+_PARM_\d+:", line))
    return tot


def row(a) -> dict:
    binp = Path(a["img"]).with_suffix(".bin")
    img, mp = binp.read_bytes(), binp.with_suffix(".map").read_text(errors="replace")
    ar = areas(mp)
    b = json.loads(Path(a["build"]).read_text()) if a.get("build") else {}
    _, where = F.parse_map(mp, img)
    x_used = sum(ar.get(k, (0, 0, ""))[1] for k in ("XSEG", "XISEG", "PSEG"))
    r = {"image": a.get("name") or binp.stem, "code_bytes": sum(1 for v in img if v != 0xFF),
         "common_end": b.get("common_end", where.cend), "xdata_used": x_used, "xdata_free": XRAM[1] - XRAM[0] - x_used,
         "iseg": ar.get("ISEG", (0, 0, ""))[1], "stack_bytes": b.get("iram", {}).get("stack_bytes")}
    if b:
        fd = b["iram"]["free_direct"]
        r["free_direct"] = sum(n for _, n in fd)
        r["data_used"] = 0x80 - r["free_direct"]
    if a.get("asm"):
        p = parm_bytes(Path(a["asm"]))
        r["parm_xdata"], r["parm_data"], r["parm_bits"] = p["xdata"], p["data"], p["bit"]
    if a.get("stack"):
        s = json.loads(Path(a["stack"]).read_text())
        r["stack_main"], r["stack_total"] = s["main"], s["total"]
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", action="append", required=True)
    for k in ("build", "asm", "stack", "name"):
        ap.add_argument("--" + k, action="append", default=[])
    argv, groups, cur = sys.argv[1:], [], None
    for i, t in enumerate(argv):                       # per-image groups: each --img opens one
        if t == "--img":
            cur = {}; groups.append(cur)
        if t.startswith("--") and i + 1 < len(argv) and cur is not None:
            cur[t[2:]] = argv[i + 1]
    ap.parse_args()
    rows = [row(g) for g in groups]
    cols = list(dict.fromkeys(k for r in rows for k in r))
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in rows]
    (F.ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    (F.ROOT / "tmp/logs/fw_ram_report.log").open("a").write("\n".join(out) + "\n")
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
