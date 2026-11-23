#!/usr/bin/env python3
"""Shared flash record: which image each unit runs (docs/flash-record.md). ONE place, shared by every worktree.

usage: flash_registry.py show SERIAL | adopt SERIAL IMAGE.bin | list
  tmp/flashed/<serial>.json   tag, sha256, built, commit, worktree, flashed (ISO), images_dir
  tmp/flashed/images/<sha12>/<tag>.{bin,map,sync.tsv,settings_table.py,build.json,ids.tsv}   content-addressed copies
  Root = main checkout (unit_lock.lock_root), so deleting a worktree loses nothing. No symlinks into worktrees.
API: record() after a successful flash, current() / map_for() for readers, snapshot()/restore() around a flash.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isostamp
import unit_lock

COMPANIONS = (".bin", ".map", ".sync.tsv", ".settings_table.py", ".build.json", ".ids.tsv")
SCAN_MAX = 40            # newest images per serial offered to the layout scan (build-debris holds ~1500)


def base() -> Path:
    return unit_lock.lock_root() / "tmp" / "flashed"


def images_dir() -> Path:
    return base() / "images"


def debris_dir() -> Path:
    return unit_lock.lock_root() / "build-debris" / "images"


def _file(serial: str) -> Path:
    return base() / f"{serial}.json"


def _write(p: Path, d: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    t = p.with_name(p.name + ".new")
    t.write_text(json.dumps(d, indent=1))
    os.replace(t, p)


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _git(cwd: Path, *a: str) -> str:
    r = subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def store(image: Path) -> tuple[str, str]:
    """Copy image + companions into images/<sha12>/ (skipped when already there). -> (sha256, dir name)."""
    sha = _sha(image)
    d = images_dir() / sha[:12]
    d.mkdir(parents=True, exist_ok=True)
    stem = image.name.removesuffix(".bin")
    for ext in COMPANIONS:
        src, dst = image.with_name(stem + ext), d / (stem + ext)
        if src.is_file() and not (dst.is_file() and dst.stat().st_size == src.stat().st_size):
            shutil.copyfile(src, dst)
    return sha, sha[:12]


def record(serial: str, image: Path, **extra) -> dict:
    """A successful flash: copy the image set, write the unit's record. extra (edid_serial, ...) is merged in."""
    image = Path(image)
    sha, dname = store(image)
    root = unit_lock.repo_root()
    here = _git(root, "rev-parse", "--short", "HEAD")
    built = build_commit(image)                     # #285: the image's own commit, not the flashing checkout's
    rec = {"tag": image.name.removesuffix(".bin"), "sha256": sha, "images_dir": dname,
           "built": _iso(image.stat().st_mtime), "commit": built or "unknown", "flasher_commit": here,
           "worktree": str(root), "flashed": isostamp.now(), **extra}
    if built and here and not here.startswith(built[:7]) and not built.startswith(here[:7]):
        print(f"warning: image {rec['tag']} was built from {built}, flashed from a checkout at {here} ({root})")
    _write(_file(serial), rec)
    return rec


def build_commit(image: Path) -> str:
    """Commit the image was built from (fwimage.py writes it into <stem>.build.json); '' for an older image."""
    bj = image.with_name(image.name.removesuffix(".bin") + ".build.json")
    try:
        d = json.loads(bj.read_text())
    except (OSError, ValueError):
        return ""
    c = d.get("commit", "") if isinstance(d, dict) else ""
    return c + ("+dirty" if c and d.get("dirty") else "")


def _iso(t: float) -> str:
    from datetime import datetime
    return datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")


def snapshot(serial: str) -> dict | None:
    f = _file(serial)
    return json.loads(f.read_text()) if f.is_file() else None


def restore(serial: str, snap: dict | None) -> None:
    if snap is None:
        _file(serial).unlink(missing_ok=True)
    else:
        _write(_file(serial), snap)


def invalidate(serial: str, image: Path, attempted: str) -> None:
    """Before the first write of a flash: the unit holds an unknown mix, so no tag/map until record() (#52.12).
    The image stays so `recover` can retry it."""
    _write(_file(serial), {"tag": "", "attempted": attempted, "attempted_image": str(image), "flashed": isostamp.now()})


def update(serial: str, **kv) -> dict:
    rec = snapshot(serial) or {}
    rec.update(kv)
    _write(_file(serial), rec)
    return rec


def _paths(rec: dict) -> dict:
    d = images_dir() / rec["images_dir"]
    out = {}
    for ext in COMPANIONS:
        p = d / (rec["tag"] + ext)
        out[ext.lstrip(".").replace(".", "_")] = p if p.is_file() else None
    return out


def current(serial: str) -> dict:
    """{} when never recorded or invalidated mid-flash; else the record + bin/map/sync_tsv/settings_table_py/build_json/ids_tsv
    (Path or None) + `image` = the stored .bin. A mid-flash record has tag '' and `attempted_image`."""
    rec = snapshot(serial)
    if not rec:
        return {}
    if not rec.get("tag"):
        return {**rec, "image": rec.get("attempted_image", "")}
    p = _paths(rec)
    return {**rec, **p, "image": str(p["bin"] or "")}


def find_tag(tag: str) -> dict | None:
    """Newest stored image with this tag: images/ first, then build-debris/images. -> {tag, bin, map, dir}"""
    for root in (images_dir(), debris_dir()):
        hits = sorted(root.glob(f"*/{tag}.map") if root == images_dir() else root.glob(f"{tag}.map"),
                      key=lambda p: p.stat().st_mtime, reverse=True)
        if hits:
            m = hits[0]
            return {"tag": tag, "map": m, "bin": m.with_suffix(".bin"), "dir": m.parent}
    return None


def candidates(serial: str, limit: int = SCAN_MAX) -> list[dict]:
    """Stored images for this unit, newest first (images/ then build-debris/images), one per tag."""
    seen, out = set(), []
    maps = [*images_dir().glob(f"*/{serial}-*.map"), *debris_dir().glob(f"{serial}-*.map")]
    for m in sorted(maps, key=lambda p: p.stat().st_mtime, reverse=True):
        tag = m.name.removesuffix(".map")
        if tag not in seen:
            seen.add(tag)
            out.append({"tag": tag, "map": m, "bin": m.with_suffix(".bin")})
    return out[:limit]


def known(serial: str) -> list[str]:
    return [c["tag"] for c in candidates(serial)]


def map_for(serial: str, given=None) -> Path:
    """The link map of the image the unit runs (the record); `given` wins. Unknown -> SystemExit listing what is known."""
    if given:
        m = Path(str(given))
        if not m.is_file():
            raise SystemExit(f"map {m} not found; nothing done")
        return m
    cur = current(serial)
    m = cur.get("map")
    if m:
        return m
    why = (f"flash of {cur['attempted']} was not completed" if cur.get("attempted") and not cur.get("tag")
           else f"record names {cur['tag']} but its map is not in {images_dir()}" if cur else "no flash record")
    k = known(serial)
    raise SystemExit(f"{serial}: no map for the image on the unit ({why}). Known images: {', '.join(k[:8]) or 'none'}"
                     f"{' ...' if len(k) > 8 else ''}. Give --map PATH, or `./dev.py flash-record --unit N adopt IMAGE.bin` "
                     f"(after `scan` shows which one answers); nothing done")


def check(serial: str, probe, cands: list[dict] | None = None) -> dict:
    """probe(map_path) -> True when the running firmware answers at that map's addresses (layout check).
    -> {ok, tag (registry), matches: tags of other known maps that answer (only when stale)}."""
    cur = current(serial)
    if cur.get("map") and probe(cur["map"]):
        return {"ok": True, "tag": cur["tag"], "matches": [cur["tag"]]}
    cands = candidates(serial) if cands is None else cands
    matches = [c["tag"] for c in cands if c["map"] != cur.get("map") and probe(c["map"])]
    return {"ok": False, "tag": cur.get("tag", ""), "matches": matches}


def stale_message(serial: str, r: dict) -> str:
    near = f"; maps that answer: {', '.join(r['matches'][:8])}" if r["matches"] else "; no known map answers"
    return (f"registry stale: unit {serial} does not answer at the map of {r['tag'] or 'its record'}{near}. "
            f"Known images: {', '.join(known(serial)[:8]) or 'none'}. `./dev.py flash-record --unit N adopt IMAGE.bin` "
            f"records the one it runs; nothing done")


def main(argv: list[str]) -> int:
    if argv[:1] == ["show"] and len(argv) == 2:
        print(json.dumps(current(argv[1]) or None, indent=1, default=str))
        return 0
    if argv[:1] == ["adopt"] and len(argv) == 3:
        img = Path(argv[2])
        if not img.is_file() or not img.with_suffix(".map").is_file():
            raise SystemExit(f"adopt: {img} and its .map beside it are needed; nothing done")
        wt = _git(img.parent, "rev-parse", "--show-toplevel")      # provenance = the tree the image was built in
        rec = record(argv[1], img, source="adopt (not flashed by this run)", **({"worktree": wt} if wt else {}))
        print(f"{argv[1]}: recorded {rec['tag']} ({rec['sha256'][:12]})")
        return 0
    if argv[:1] == ["list"]:
        for f in sorted(base().glob("*.json")):
            r = json.loads(f.read_text())
            print(f"{f.stem}\t{r.get('tag') or '(mid-flash: ' + r.get('attempted', '') + ')'}\t{r.get('flashed', '')}\t{r.get('worktree', '')}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
