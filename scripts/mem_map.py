#!/usr/bin/env python3
"""Flash memory map of a firmware image as one readable HTML page.

usage: mem_map.py STEM [--out FILE]      STEM = tmp/fw/<serial>-<tag>-be (reads STEM.bin, STEM.build.json)
- One bar per 64 KiB bank image: 20 KiB common copy, then the 44 KiB banked window split into code (non-0xFF),
  padding inside the used range (sticky-layout slot gaps), free tail.
- Duplication table: the common copy repeated per bank, plus the documented ISR / main twins (docs/duplicate-code.md).
Log: tmp/logs/mem_map.log
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

from _log import log_line
from _repo import repo_root

ROOT = repo_root()
LOG = ROOT / "tmp" / "logs" / "mem_map.log"
BANK = 0x10000          # one bank image in the flash (64 KiB)
COMMON = 0x5000         # common copy at the start of every bank image (fw/bank_layout.tsv '#common 0x5000')

# Documented duplicates (docs/duplicate-code.md, #44 comments); sizes as recorded there, not re-measured here.
TWINS = [
    ("DpRx1 ISR / main twins (DFECheck, AdjustLaneFLDBand, SetDFEInitial ...)", "15 pairs, 1.1 KB (up to 5 KB)",
     "functions reachable from an interrupt and the main loop keep separate copies (_EXINT0 / _WDINT suffix); locals are overlaid, not reentrant (#281)"),
    ("ScalerTimerCancelTimerEvent vs _EXINT0", "70 B", "same reason, intentional ISR twin"),
    ("HDCP 2.2 main-loop crypto twins (stage 2, not in the shipped image)", "5.6 KB of 22 KB", "DP AKE_NO_STORED_KM RSA / Dkey / H' in the main loop, plain copies of the _EXINT0 crypto (#44)"),
    ("HDCP 2.2 Timer0 (_WDINT) SKE twin (stage 2)", "not measured", "third context: SKE_SEND_EKS 4 ms after the request (#44)"),
]


STYLE = ("<style>body{font:14px system-ui;margin:24px;max-width:1100px}table{border-collapse:collapse;width:100%}"
         "td,th{padding:4px 8px;border-bottom:1px solid #ddd;text-align:left;vertical-align:middle}"
         ".bar{display:flex;height:16px;width:420px;border:1px solid #888}.u{background:#2a6fdb}.p{background:#e0a030}.f{background:#e8e8e8}"
         ".c{background:#7a4fb5}h2{margin-top:28px}.n{text-align:right;font-variant-numeric:tabular-nums}small{color:#555}</style>")
LEGEND = ("Legend: <span class=u>&nbsp;&nbsp;&nbsp;</span> code, <span class=p>&nbsp;&nbsp;&nbsp;</span> padding inside the used range, "
          "<span class=f>&nbsp;&nbsp;&nbsp;</span> free tail.</p>")


def log(msg: str) -> None:
    log_line(msg, LOG)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("stem")
    ap.add_argument("--out", default=str(ROOT / "tmp" / "memory-map.html"))
    a = ap.parse_args()
    stem = Path(a.stem)
    if not stem.is_absolute():
        stem = ROOT / stem
    img = stem.with_suffix(".bin").read_bytes() if stem.suffix != ".bin" else stem.read_bytes()
    n = len(img) // BANK
    rows, copies = [], set()
    tot_used = tot_pad = tot_free = 0
    for i in range(n):
        base = i * BANK
        copies.add(hashlib.md5(img[base:base + COMMON]).hexdigest())
        win = img[base + COMMON:base + BANK]
        used = sum(1 for x in win if x != 0xFF)
        hw = max((j for j, x in enumerate(win) if x != 0xFF), default=-1) + 1
        pad, free = hw - used, len(win) - hw
        tot_used, tot_pad, tot_free = tot_used + used, tot_pad + pad, tot_free + free
        rows.append((i, used, pad, free, len(win)))
    com0 = img[:COMMON]
    com_used = sum(1 for x in com0 if x != 0xFF)
    com_hw = max(j for j, x in enumerate(com0) if x != 0xFF) + 1
    dup = (n - 1) * com_used
    meta = {}
    bj = stem.parent / (stem.name.removesuffix(".bin").removesuffix("-be") + "-be.build.json")
    if bj.exists():
        meta = json.loads(bj.read_text())

    def bar(used, pad, free, total, extra=""):
        w = lambda v: f"{100 * v / total:.2f}%"
        return (f'<div class="bar"><span class="u" style="width:{w(used)}"></span><span class="p" style="width:{w(pad)}"></span>'
                f'<span class="f" style="width:{w(free)}"></span></div>{extra}')

    out = ["<!doctype html><meta charset=utf-8><title>Flash memory map</title>",
           STYLE,
           f"<h1>Flash memory map: {html.escape(stem.name)}</h1>",
           f"<p>{len(img)} B = {n} bank images x 64 KiB (each: {COMMON // 1024} KiB common copy + {(BANK - COMMON) // 1024} KiB banked window). " + LEGEND,
           "<h2>Banked window per bank (44 KiB each)</h2><table><tr><th>bank</th><th>map</th><th class=n>code</th><th class=n>padding</th><th class=n>free tail</th></tr>"]
    for i, used, pad, free, total in rows:
        out.append(f"<tr><td>{i}</td><td>{bar(used, pad, free, total)}</td><td class=n>{used}</td><td class=n>{pad}</td><td class=n>{free}</td></tr>")
    out.append(f"<tr><th>total</th><td></td><th class=n>{tot_used}</th><th class=n>{tot_pad}</th><th class=n>{tot_free}</th></tr></table>")
    out.append("<h2>Common copy (same bytes in every bank image)</h2>")
    out.append("<table><tr><td>one copy</td><td>" + bar(com_used, com_hw - com_used, COMMON - com_hw, COMMON) +
               f"</td><td class=n>{com_used} B code, {com_hw - com_used} B padding, {COMMON - com_hw} B free of {COMMON}</td></tr>"
               f"<tr><td>copies in the image</td><td class=n>{n}</td><td>{'all identical' if len(copies) == 1 else str(len(copies)) + ' distinct'}</td></tr>"
               f"<tr><td>redundant copies</td><td class=n>{dup}</td><td>{n - 1} extra copies x {com_used} B = {100 * dup / len(img):.1f}% of the image</td></tr></table>")
    out.append("<h2>What is duplicated, and why</h2><table><tr><th>block</th><th>size</th><th>why</th></tr>")
    out.append(f"<tr><td>Common copy x {n} banks</td><td class=n>{dup} B redundant ({n * COMMON} B reserved)</td>"
               "<td>each bank image carries its own copy of the always-visible code (ISRs, timer / wait primitives, cross-bank stubs, "
               "startup); a common edit rewrites one sector per bank (docs/flash-layout.md). The hardware reason is not re-checked here.</td></tr>")
    for name, size, why in TWINS:
        out.append(f"<tr><td>{html.escape(name)}</td><td>{html.escape(size)}</td><td>{html.escape(why)}</td></tr>")
    out.append("</table><p><small>Sizes of the twins are from docs/duplicate-code.md and the #44 comments, not measured by this script. "
               f"Build record keys: {html.escape(', '.join(sorted(meta)[:12]))}</small></p>")
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text("\n".join(out))
    log(f"{stem.name}: {n} banks, code {tot_used} B, padding {tot_pad} B, free tail {tot_free} B, common {com_used} B x {n}; wrote {a.out}")
    print(a.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
