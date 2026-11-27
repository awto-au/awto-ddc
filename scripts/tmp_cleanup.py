#!/usr/bin/env python3
"""Apply a tmp/ cleanup plan (TSV: action, path, dest, why) made from `./dev.py tmp-audit` output. Dry-run by default.

- rm: delete (regenerable). waste: move to /mnt/1tnvme/wastebasket/<slot>-<stamp>/<path under --base>.
- move: to <this tree>/<dest> (durable home: debris/, docs/, re/). vendor: delete once <dest> (under /vendors) has the same SHA-256.
- Re-checks at apply time: a path changed in the last 3 h is skipped (live agent). Log: tmp/logs/tmp_cleanup.log.
"""
import argparse
import hashlib
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _log import Logger
from _repo import ROOT

log = Logger(ROOT / "tmp/logs/tmp_cleanup.log").say
WASTE = Path("/mnt/1tnvme/wastebasket")
VENDORS = Path("/vendors")
RECENT_S = 3 * 3600  # Dan 2026-11-27: changed in the last 3 h = in use


def newest(p: Path) -> float:
    m = p.lstat().st_mtime
    if p.is_dir() and not p.is_symlink():
        for f in p.rglob("*"):
            try:
                m = max(m, f.lstat().st_mtime)
            except OSError:
                pass
    return m


def size(p: Path) -> int:
    if p.is_symlink() or p.is_file():
        return p.lstat().st_size
    return sum(f.lstat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink())


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def in_store(p: Path, dest: str) -> Path | None:
    """dest = the store copy's path (a whole-store walk takes minutes)."""
    q = Path(dest)
    ok = q.is_file() and q.resolve().is_relative_to(VENDORS.resolve()) and sha(q) == sha(p)
    return q if ok else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("plan", type=Path)
    ap.add_argument("--base", type=Path, required=True, help="tmp/ root the plan's paths live under")
    ap.add_argument("--slot", default="awto-ddc-tmp")
    ap.add_argument("--slot-dir", type=Path, help="reuse this wastebasket dir (a resumed run)")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    slot = a.slot_dir or WASTE / f"{a.slot}-{time.strftime('%Y%m%d-%H%M%S')}"
    tally: dict[str, list[int]] = {}
    for ln in a.plan.read_text().splitlines()[1:]:
        action, path, dest, why = (ln.split("\t") + ["", ""])[:4]
        p = Path(path)
        if action == "keep" or not p.exists() and not p.is_symlink():
            continue
        if time.time() - newest(p) < RECENT_S:
            log(f"SKIP {p}: changed < 3 h ago")
            continue
        n = size(p)
        t = tally.setdefault(action, [0, 0])
        t[0] += 1
        t[1] += n
        if not a.apply:
            continue
        if action == "rm":
            shutil.rmtree(p) if p.is_dir() and not p.is_symlink() else p.unlink()
        elif action == "waste":
            q = slot / p.relative_to(a.base)
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), q)
        elif action == "move":
            q = ROOT / dest
            q.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(p), q)
        elif action == "vendor":
            q = in_store(p, dest)
            if not q:
                log(f"KEEP {p}: no same-SHA copy under {VENDORS}")
                continue
            p.unlink()
            why += f" (store copy {q})"
        log(f"{action} {p} {n/1e6:.1f}MB {('-> ' + dest) if dest else ''} : {why}")
    for k, (c, n) in sorted(tally.items()):
        log(f"{'applied' if a.apply else 'would'} {k}: {c} entries, {n/1e9:.2f} GB")
    if a.apply and slot.exists():
        log(f"wastebasket slot {slot}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
