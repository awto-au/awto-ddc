#!/usr/bin/env python3
"""Catalogue of every OSD layout one firmware image draws: pop-ups rendered in fw_sim + menu-page renders.

usage: osd_catalog.py BIN [--menu-dir DIR] [--out DIR] [--mode 1080p60|2160p60]
- Each pop-up = one osd_render.py run (fresh sim), all in parallel. Menu pages: walk_*.png from --menu-dir (menu_cli --png).
- Writes OUT/index.html (contact sheet, opens rendered in code-insiders) and OUT/catalog.tsv (the list).
Log: ./tmp/logs/osd_catalog.log
"""
import argparse, html, os, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    return Path(env) if env else HERE.parent


ROOT = repo_root()
LOG = ROOT / "tmp" / "logs" / "osd_catalog.log"

# (name, osd_render args, what it is): actions are osd_test names (rtd_proto OSD_EVENTS / osd_test CMD_ONLY)
POPUPS = [
    ("logo", ["--at", "logo"], "boot logo"),
    ("idle", ["--at", "1500"], "picture, no OSD (ACTIVE)"),
    ("info", ["--do", "300:info", "--at", "2500"], "input info pop-up"),
    ("debug", ["--do", "300:debug", "--at", "2500"], "debug/tech pop-up (#34), held"),
    ("nosignal", ["--do", "300:nosignal", "--at", "2500"], "no signal message"),
    ("nocable", ["--do", "300:nocable", "--at", "2500"], "no cable message"),
    ("nosupport", ["--do", "300:nosupport", "--at", "2500"], "mode not supported message"),
    ("failsafe", ["--do", "300:failsafe", "--at", "2500"], "fail-safe mode message"),
    ("powersaving", ["--do", "300:powersaving-msg", "--at", "2500"], "power saving message"),
    ("source", ["--do", "300:source-menu", "--at", "2500"], "source (input) menu"),
]
# one osd_render run = sim boot to ACTIVE + actions; limit = 3x cold worst case (tmp/logs/osd_render.log)
# stall = no CPU time used for STALL_S: the sim boot prints nothing, but a live sim always burns CPU
RUN_LIMIT_S = 650
STALL_S = 60
POLL_S = 1.0   # check pace for the parallel runs; no busy loop


def cpu_ticks(pid: int) -> int:
    f = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return int(f[11]) + int(f[12])   # utime + stime (fields 14, 15)


def log(s: str):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def run_all(binp: Path, mapp: Path, out: Path, mode: str) -> dict:
    procs = {}
    for name, extra, _ in POPUPS:
        lp = out / f"{name}.render.log"
        cmd = [sys.executable, str(HERE / "osd_render.py"), str(binp), str(mapp), "--mode", mode,
               "--out", str(out / f"{name}.png"), *extra]
        procs[name] = (subprocess.Popen(cmd, stdout=lp.open("w"), stderr=subprocess.STDOUT), lp, time.monotonic())
    rc, last = {}, {n: (0, time.monotonic()) for n in procs}
    while len(rc) < len(procs):
        for name, (p, lp, t0) in procs.items():
            if name in rc:
                continue
            if p.poll() is not None:
                rc[name] = p.returncode
                log(f"{name}: rc={p.returncode} in {time.monotonic() - t0:.0f} s")
                continue
            ticks, seen = last[name]
            now = time.monotonic()
            try:
                cur = cpu_ticks(p.pid)
            except (FileNotFoundError, ProcessLookupError):
                continue                        # exited between poll() and the read
            if cur != ticks:
                last[name] = (cur, now)
            elif now - seen > STALL_S or now - t0 > RUN_LIMIT_S:
                p.kill()
                rc[name] = -9
                tail = lp.read_text(errors="replace").strip().splitlines()[-1:] or ["<no output>"]
                log(f"{name}: KILLED after {now - t0:.0f} s (no CPU for {now - seen:.0f} s > {STALL_S}, or total > {RUN_LIMIT_S}); "
                    f"last line: {tail[0]}; loadavg {os.getloadavg()[0]:.1f}")
        time.sleep(POLL_S)
    return rc


def pick_png(out: Path, name: str) -> Path | None:
    hits = sorted(out.glob(f"{name}*.png"))
    return next((h for h in hits if "_crop" not in h.name), None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("bin", type=Path)
    ap.add_argument("--menu-dir", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--mode", default="2160p60")
    a = ap.parse_args()
    LOG.parent.mkdir(parents=True, exist_ok=True)
    binp = a.bin.resolve()
    mapp = binp.with_suffix(".map")
    tag = binp.stem
    out = (a.out or ROOT / "tmp" / "osd_catalog" / tag).resolve()
    out.mkdir(parents=True, exist_ok=True)
    log(f"catalog {tag}: {len(POPUPS)} pop-up renders in parallel -> {out}")
    rc = run_all(binp, mapp, out, a.mode)
    rows = []
    for name, _, what in POPUPS:
        png = pick_png(out, name)
        rows.append(("popup", name, what, png if rc[name] == 0 else None))
    if a.menu_dir:
        for p in sorted(a.menu_dir.glob("walk_*.png")):
            page = p.stem.removeprefix("walk_")
            rows.append(("menu", page, f"menu page: {page}", p.resolve()))
    with (out / "catalog.tsv").open("w") as f:
        f.write("kind\tname\twhat\tpng\n")
        for k, n, w, p in rows:
            f.write(f"{k}\t{n}\t{w}\t{p or 'MISSING'}\n")
    cards = "\n".join(
        f'<figure><figcaption><b>{html.escape(n)}</b> <span>{html.escape(k)}</span><br>{html.escape(w)}</figcaption>'
        + (f'<a href="file://{p}"><img src="file://{p}" loading="lazy"></a>' if p else "<div class=miss>render failed</div>")
        + "</figure>" for k, n, w, p in rows)
    (out / "index.html").write_text(f"""<!doctype html><meta charset=utf-8><title>OSD catalogue {html.escape(tag)}</title>
<style>body{{font:14px system-ui;background:#111;color:#ddd;margin:16px}}main{{display:grid;
grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:16px}}figure{{margin:0;background:#1c1c1c;padding:8px;
border-radius:6px}}img{{width:100%;image-rendering:pixelated}}span{{color:#888}}.miss{{color:#e66;padding:40px}}</style>
<h1>OSD catalogue: {html.escape(tag)}</h1><p>{len(rows)} layouts; fw_sim {html.escape(a.mode)}</p><main>{cards}</main>""")
    bad = [n for k, n, _, p in rows if p is None]
    log(f"catalog {tag}: {len(rows) - len(bad)}/{len(rows)} rendered; missing: {', '.join(bad) or 'none'}; {out / 'index.html'}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
