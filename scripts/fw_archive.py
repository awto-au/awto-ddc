#!/usr/bin/env python3
"""Keep every firmware image we build: tmp/fw/<name>.bin (+ .map, ids) -> build-debris/images/<name>.* (gitignored, Dan 2026-11-12:
  image commits made git log too noisy; fw/images/ held them until then and stays in history)

usage: fw_archive.py [--commit] [image.bin ...]
  No images: scan tmp/fw/ of this repo and of every git worktree.
  Same name, same bytes: skipped. Same name, different bytes: kept as <name>@<branch>.bin.
  build-debris/images/index.tsv: name, sha256/12, size, ISO mtime, source path, worktree branch@commit.
  --commit: retired (accepted, ignored). dev.py flash calls this after every successful flash.
Log: ./tmp/logs/fw_archive.log
"""
import argparse, hashlib, os, shutil, subprocess, sys
from datetime import datetime
from pathlib import Path

REPO = Path(os.environ.get("AWTO_DDC_REPO") or Path(__file__).resolve().parent.parent)
DEST = REPO / "build-debris/images"
INDEX = DEST / "index.tsv"
COMPANIONS = (".map", ".ids.tsv", "-trace_ids.tsv")
LOG = REPO / "tmp/logs/fw_archive.log"


def log(msg: str) -> None:
    line = f"{datetime.now().astimezone().isoformat(timespec='seconds')} {msg}"
    print(msg)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def git(*a: str, cwd: Path = REPO) -> str:
    return subprocess.run(["git", "-C", str(cwd), *a], capture_output=True, text=True, check=True).stdout


def worktrees() -> list[tuple[Path, str]]:
    out, wt, br = [], None, ""
    for ln in git("worktree", "list", "--porcelain").splitlines() + [""]:
        if ln.startswith("worktree "):
            wt = Path(ln[9:])
        elif ln.startswith("HEAD "):
            br = ln[5:13]
        elif ln.startswith("branch "):
            br = ln.removeprefix("branch refs/heads/") + "@" + br
        elif not ln and wt:
            out.append((wt, br))
            wt, br = None, ""
    return out


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def companions(img: Path) -> list[Path]:
    stem = img.with_suffix("")
    return [Path(f"{stem}{s}") for s in COMPANIONS if Path(f"{stem}{s}").is_file()]


def load_index() -> dict[str, str]:
    if not INDEX.is_file():
        return {}
    rows = INDEX.read_text().splitlines()[1:]
    return {r.split("\t")[0]: r for r in rows if r}


def archive(img: Path, origin: str, index: dict[str, str]) -> str | None:
    """-> archived name, or None if already present with the same bytes."""
    h = sha(img)
    name = img.stem
    for cand in (name, f"{name}@{origin.split('@')[0]}"):
        tgt = DEST / f"{cand}.bin"
        if tgt.is_file() and sha(tgt) == h:
            return None
        if not tgt.is_file():
            name = cand
            break
    else:
        log(f"SKIP {img}: {name}.bin and {name}@<branch>.bin both exist with other bytes")
        return None
    shutil.copy2(img, DEST / f"{name}.bin")
    for c in companions(img):
        shutil.copy2(c, DEST / (name + c.name[len(img.stem):]))
    mt = datetime.fromtimestamp(img.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    index[name] = "\t".join([name, h[:12], str(img.stat().st_size), mt, str(img), origin])
    return name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="*", type=Path)
    ap.add_argument("--commit", action="store_true", help="retired: accepted and ignored (the store is gitignored)")
    a = ap.parse_args()
    DEST.mkdir(parents=True, exist_ok=True)
    index = load_index()
    if a.images:
        srcs = [(p.resolve(), "given") for p in a.images]
    else:
        srcs = [(p, br) for wt, br in worktrees() for p in sorted((wt / "tmp/fw").glob("*.bin"))]
    new = [n for p, br in srcs if (n := archive(p, br, index))]
    INDEX.write_text("name\tsha256\tbytes\tmtime\tsource\tworktree\n" + "".join(index[k] + "\n" for k in sorted(index)))
    log(f"DONE: {len(new)} new image(s) of {len(srcs)} scanned -> {DEST.relative_to(REPO)}/ ({len(index)} kept)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
