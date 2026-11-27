"""Per-build size history (internal; used by ./dev.py build, size-graph, size-backfill). Doc: docs/size-log.md.

- Row per image in <main checkout>/tmp/size/size-history.tsv (shared by every worktree; untracked).
- Function sizes per image: tmp/size/funcs/<crc>.tsv.gz (map CH_ chunk areas, else map symbol spacing).
- Numbers from the image's .map + .bin (+ the tree's build.json when the build just ran); no thresholds.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import subprocess
import zlib
from datetime import datetime
from pathlib import Path

import chip_mem as CM

COLS = ["time", "tree", "branch", "commit", "dirty", "diff_hash", "serial", "tag", "variant", "layout", "compiler", "src",
        "common_b", "banked_b", "bank_used", "bank_free", "min_bank_free", "direct_used", "direct_free", "iram_src", "idata", "stack",
        "stack_static", "bseg_bits", "xdata_used", "xdata_free", "image_crc", "image"]
NUM = ["common_b", "banked_b", "direct_used", "direct_free", "idata", "stack", "stack_static", "bseg_bits", "xdata_used", "xdata_free"]
AREA = re.compile(r"^(\S+)\s+([0-9A-F]{8})\s+([0-9A-F]{8}) =\s+(\d+)\. bytes \(([^)]*)\)", re.MULTILINE)
CSYM = re.compile(r"^C:\s+([0-9A-F]{8})\s+(_[A-Za-z]\w*)\b", re.MULTILINE)
BSEG = re.compile(r"^C:\s+([0-9A-F]{8})\s+l_BSEG\s*$", re.MULTILINE)
STEM = re.compile(r"^(AWT\d+)-(.+)-be$")
TAG_COMMIT = re.compile(r"^([0-9a-f]{7,12})(\+)?(?:-|$)")
TAG_DEFS = {"freeze": "_AWTO_FREEZE=_ON", "nofrc": "_AWTO_FRC=_OFF", "audio-test": "_AWTO_AUDIO_TEST"}
LEGACY_MSG = (0xDA000, 0x6000)   # message block before it moved to bank 9 (667be730 placed it here)
TOP_N = 5          # functions listed per direction in the report
SMALLEST_N = 3     # banks listed by smallest free


def main_root() -> Path:
    """$AWTO_DDC_REPO, else the main checkout (git common dir's parent), so all worktrees share one history."""
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    import unit_lock
    return unit_lock.lock_root()


def size_dir(root: Path | None = None) -> Path:
    return (root or main_root()) / "tmp/size"


def _git(tree: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(tree), *args], capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def tree_state(tree: Path) -> dict:
    """commit (12 hex), branch, dirty + diff_hash (8 hex of `git diff HEAD`, tracked files only)."""
    diff = subprocess.run(["git", "-C", str(tree), "diff", "HEAD", "--binary"], capture_output=True, check=False).stdout
    return {"commit": _git(tree, "rev-parse", "--short=12", "HEAD"), "branch": _git(tree, "rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": int(bool(diff)), "diff_hash": hashlib.sha256(diff).hexdigest()[:8] if diff else ""}


def variant_of(defines: list[str]) -> str:
    d = sorted({str(x).removeprefix("-D") for x in defines})
    return "+".join(d) or "default"


def parse_map(text: str) -> dict:
    """Unique areas {(name, addr): (size, attrs)}: the map repeats the area table once per page."""
    out = {}
    for m in AREA.finditer(text):
        if int(m.group(4)):
            out[(m.group(1), int(m.group(2), 16))] = (int(m.group(4)), m.group(5))
    return out


def infer_common_end(areas: dict) -> int:
    """Lowest bank offset of any code area above bank 0, down to 1 KiB (0x5000 before 2026-11-23, 0x2800 since)."""
    offs = [a % CM.BANK_SIZE for (_n, a), (_s, at) in areas.items() if "CODE" in at and a >= CM.BANK_SIZE]
    return (min(offs) & ~0x3FF) if offs else CM.COMMON_END


def func_sizes(areas: dict, text: str) -> dict:
    """{function: bytes}: CH_ chunk areas (one per function) when present, else spacing of C: globals inside code areas."""
    ch = {}
    for (n, _a), (s, at) in areas.items():
        if n.startswith("CH_") and "CODE" in at:
            ch[n[3:]] = ch.get(n[3:], 0) + s
    if ch:
        return ch
    ext = sorted((a, a + s) for (_n, a), (s, at) in areas.items() if "CODE" in at)
    syms = sorted({(int(a, 16), n) for a, n in CSYM.findall(text)})
    out = {}
    for i, (a, n) in enumerate(syms):
        end = next((e for b, e in ext if b <= a < e), None)
        if end is None:
            continue
        nxt = syms[i + 1][0] if i + 1 < len(syms) else end
        out[n.removeprefix("_")] = out.get(n.removeprefix("_"), 0) + min(nxt, end) - a
    return out


def measure(bin_path: Path, map_path: Path, tree_bj: dict | None = None, stem_bj: dict | None = None) -> tuple[dict, dict]:
    """(row numbers, function sizes) of one image; tree_bj = tmp/fw/<serial>/build.json of the build (IRAM, XDATA pool)."""
    text = map_path.read_text(errors="replace")
    img = bin_path.read_bytes()
    areas = parse_map(text)
    tb, sb = tree_bj or {}, stem_bj or {}
    ce = tb.get("common_max") or infer_common_end(areas)
    common, banked = 0, {}
    for (_n, a), (s, at) in areas.items():
        if "CODE" not in at:
            continue
        if a < ce:
            common += s
        else:
            banked[a // CM.BANK_SIZE] = banked.get(a // CM.BANK_SIZE, 0) + s
    for b in tb.get("banks") or []:
        banked.setdefault(b, 0)
    res = {}
    for a, n in {*CM.RESERVED.values(), LEGACY_MSG}:      # a reserved block in this image: not code space
        if any(not (x + s <= a or x >= a + n) for (_n, x), (s, at) in areas.items() if "CODE" in at):
            continue
        if img[a:a + n].strip(b"\xff"):
            res[a // CM.BANK_SIZE] = res.get(a // CM.BANK_SIZE, 0) + n
    free = {b: CM.BANK_SIZE - ce - u - res.get(b, 0) for b, u in banked.items()}
    size = {n: s for (n, _a), (s, _at) in areas.items()}
    iram = tb.get("iram") or {}
    if iram.get("free_direct") is not None:
        dfree = sum(n for _a, n in iram["free_direct"])
        dused, isrc = CM.DIRECT_END - dfree, "link"
    else:
        dused = size.get("DSEG", 0) + size.get("OSEG", 0) + sum(s for n, s in size.items() if re.fullmatch(r"DDOVL\d+", n))
        dfree, isrc = CM.DIRECT_END - dused, "map"
    xused = sum(s for (_n, _a), (s, at) in areas.items() if "XDATA" in at)
    m = BSEG.search(text)
    xf = tb.get("xdata_free", sb.get("xdata_free"))
    smallest = sorted(free.items(), key=lambda kv: kv[1])[:1]
    row = {"common_b": common, "banked_b": sum(banked.values()),
           "bank_used": ",".join(f"{b}:{banked[b]}" for b in sorted(banked)),
           "bank_free": ",".join(f"{b}:{free[b]}" for b in sorted(free)),
           "min_bank_free": ",".join(f"{b}:{f}" for b, f in smallest),
           "direct_used": dused, "direct_free": dfree, "iram_src": isrc, "idata": size.get("ISEG", 0),
           "stack": iram.get("stack_bytes", size.get("SSEG", "")), "bseg_bits": int(m.group(1), 16) if m else "",
           "xdata_used": xused, "xdata_free": "" if xf is None else xf,
           "compiler": ((tb.get("compiler") or {}).get("commit") or "")[:10],
           "image_crc": f"{zlib.crc32(img):08x}"}
    return row, func_sizes(areas, text)


def bank_map(s: str) -> dict:
    return {int(b): int(v) for b, v in (x.split(":") for x in s.split(",") if x)} if s else {}


def read_history(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    lines = path.read_text().splitlines()
    hdr = lines[0].split("\t") if lines else COLS
    return [dict(zip(hdr, ln.split("\t"), strict=False)) for ln in lines[1:] if ln]


def append_row(path: Path, row: dict, funcs: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.is_file() or not path.stat().st_size
    with path.open("a") as f:
        if new:
            f.write("\t".join(COLS) + "\n")
        f.write("\t".join(str(row.get(c, "")).replace("\t", " ") for c in COLS) + "\n")
    if funcs is not None:
        fp = path.parent / "funcs" / f"{row['image_crc']}.tsv.gz"
        fp.parent.mkdir(exist_ok=True)
        if not fp.is_file():
            fp.write_bytes(gzip.compress("".join(f"{n}\t{s}\n" for n, s in sorted(funcs.items())).encode(), mtime=0))


def read_funcs(size_root: Path, crc: str) -> dict | None:
    fp = size_root / "funcs" / f"{crc}.tsv.gz"
    if not fp.is_file():
        return None
    return {n: int(s) for n, s in (ln.split("\t") for ln in gzip.decompress(fp.read_bytes()).decode().splitlines() if ln)}


def first_parent(tree: Path, ref: str = "origin/main") -> list[str]:
    """main's first-parent commits, newest first, as 12-hex short hashes."""
    return [c[:12] for c in _git(tree, "rev-list", "--first-parent", ref).split()]


def same_kind(a: dict, b: dict) -> bool:
    return a.get("serial") == b.get("serial") and a.get("variant") == b.get("variant") and a.get("layout") == b.get("layout")


def pick_refs(rows: list[dict], row: dict, main_fp: list[str]) -> tuple[dict | None, dict | None]:
    """(previous build of the same serial + variant + layout, newest clean build of origin/main's newest built commit)."""
    prev = next((r for r in reversed(rows) if same_kind(r, row)), None)
    pos = {c: i for i, c in enumerate(main_fp)}
    cand = [r for r in rows if r.get("dirty") in ("0", 0) and r.get("commit", "")[:12] in pos and r.get("variant") == row.get("variant")
            and r.get("layout") == row.get("layout")]
    cand.sort(key=lambda r: (pos[r["commit"][:12]], r.get("serial") != row.get("serial"), r.get("time", "")[::-1]))
    return prev, (cand[0] if cand else None)


def label(r: dict) -> str:
    return f"{r.get('commit', '')[:8]}{'*' + r.get('diff_hash', '') if str(r.get('dirty')) == '1' else ''}"


def _delta(a, b) -> str:
    try:
        a, b = int(a), int(b)
    except (TypeError, ValueError):
        return "-"
    d = a - b
    return f"{d:+d} ({100 * d / b:+.2f} %)" if b else f"{d:+d}"


def _cell(row: dict, ref: dict, c: str) -> str:
    """Delta, or the reference's IRAM source when link holes and the map sum would be compared (backfill rows)."""
    if c.startswith("direct_") and ref.get("iram_src") != row.get("iram_src"):
        return f"({ref.get('iram_src') or '?'} source)"
    return _delta(row.get(c), ref.get(c))


def top_changes(new: dict, old: dict, n: int = TOP_N) -> tuple[list, list]:
    d = [(new.get(k, 0) - old.get(k, 0), k) for k in set(new) | set(old) if new.get(k, 0) != old.get(k, 0)]
    grew = sorted((x for x in d if x[0] > 0), key=lambda x: (-x[0], x[1]))[:n]
    shrank = sorted((x for x in d if x[0] < 0), key=lambda x: (x[0], x[1]))[:n]
    return grew, shrank


def report(row: dict, funcs: dict | None, prev: dict | None, main: dict | None, size_root: Path) -> list[str]:
    """Short text report: this build vs prev (same serial + variant) and vs origin/main; no thresholds."""
    out = [f"size {row.get('serial')} {row.get('variant')} {row.get('layout')} {label(row)} crc {row.get('image_crc')}"]
    refs = [(k, r) for k, r in (("prev", prev), ("main", main)) if r]
    out.append(f"  {'':12} {'this':>8}" + "".join(f"  {k + ' ' + label(r):>26}" for k, r in refs))
    for c in NUM:
        out.append(f"  {c:12} {row.get(c, ''):>8}" + "".join(f"  {_cell(row, r, c):>26}" for _k, r in refs))
    free = bank_map(row.get("bank_free", ""))
    for k, r in refs:
        old = bank_map(r.get("bank_free", ""))
        ch = [f"b{b} {free.get(b, 0) - old.get(b, 0):+d}" for b in sorted(set(free) | set(old)) if free.get(b, 0) != old.get(b, 0)]
        out.append(f"  bank free vs {k}: {', '.join(ch) or 'no change'}")
    out.append("  smallest bank free: " + ", ".join(f"b{b} {f} B" for b, f in sorted(free.items(), key=lambda kv: kv[1])[:SMALLEST_N]))
    for k, r in refs:
        old = read_funcs(size_root, r.get("image_crc", "")) if funcs is not None else None
        if old is None:
            out.append(f"  functions vs {k}: no function sizes stored for {r.get('image_crc')}")
            continue
        g, s = top_changes(funcs, old)
        out.append(f"  grew vs {k}: " + (", ".join(f"{n} {d:+d}" for d, n in g) or "none"))
        out.append(f"  shrank vs {k}: " + (", ".join(f"{n} {d:+d}" for d, n in s) or "none"))
    return out


def static_stack(tree: Path):
    """Static worst case main + nested ISRs, both IP states (scripts/fw_stack.py on this build's asm_bank, ~0.5 s); '' if unavailable."""
    import stats
    sk = stats.stack(tree)
    return max(sk[1], sk[2]) if sk else ""


def record_build(tree: Path, stem: Path, defines: list[str], *, say=print, root: Path | None = None) -> dict:
    """Called by fwimage after a good build: measure, compare, append, report. stem = <root>/tmp/fw/<serial>-<tag>-be."""
    sd = size_dir(root)
    m = STEM.match(stem.name)
    serial, tag = (m.group(1), m.group(2)) if m else ("", stem.name)
    tree_bj = json.loads((tree / f"tmp/fw/{serial}/build.json").read_text())
    sbj_p = stem.with_name(stem.name + ".build.json")
    sbj = json.loads(sbj_p.read_text()) if sbj_p.is_file() else {}
    nums, funcs = measure(stem.with_name(stem.name + ".bin"), stem.with_name(stem.name + ".map"), tree_bj, sbj)
    row = {"time": datetime.now().astimezone().isoformat(timespec="seconds"), "tree": str(tree), **tree_state(tree),
           "serial": serial, "tag": tag, "variant": variant_of(defines), "layout": tree_bj.get("layout_mode", ""), "src": "build",
           "image": stem.name, **nums, "stack_static": static_stack(tree)}
    hist = sd / "size-history.tsv"
    rows = read_history(hist)
    prev, main = pick_refs(rows, row, first_parent(tree))
    append_row(hist, row, funcs)
    if sbj_p.is_file():
        sbj["size"] = {c: row[c] for c in COLS if c not in ("tree", "image")}
        sbj_p.write_text(json.dumps(sbj) + "\n")
    for ln in report(row, funcs, prev, main, sd):
        say(ln)
    say(f"size history {hist} ({len(rows) + 1} rows)")
    return row


# ---- backfill + graph ------------------------------------------------------------------------------------------------

def image_sources(root: Path) -> list[Path]:
    """.bin files with a .map beside them: build-debris/images, tmp/flashed/images/*, tmp/fw of the main checkout + worktrees."""
    dirs = [root / "build-debris/images", *sorted((root / "tmp/flashed/images").glob("*")), root / "tmp/fw"]
    for ln in _git(root, "worktree", "list", "--porcelain").splitlines():
        if ln.startswith("worktree ") and Path(ln[9:]) != root:
            dirs.append(Path(ln[9:]) / "tmp/fw")
    return [b for d in dirs if d.is_dir() for b in sorted(d.glob("AWT*-be.bin")) if b.with_suffix(".map").is_file()]


def merged_same_tree(tree: Path, ref: str = "origin/main") -> dict:
    """{second parent: merge}: a branch tip whose tree is the first-parent merge's tree built the same image as the merge."""
    pairs = [ln.split() for ln in _git(tree, "rev-list", "--first-parent", "--parents", ref).splitlines()]
    pairs = [(p[0], p[2]) for p in pairs if len(p) >= 3]
    trees = dict(ln.split() for ln in _git(tree, "log", "--no-walk=unsorted", "--format=%H %T", *{c for pr in pairs for c in pr}).splitlines()) if pairs else {}
    return {b[:12]: m[:12] for m, b in pairs if trees.get(m) and trees.get(m) == trees.get(b)}


def backfill(root: Path, tree: Path, *, say=print) -> int:
    """Rows for archived images of main's first-parent commits (no rebuild); skips CRCs already in the history."""
    sd = size_dir(root)
    hist = sd / "size-history.tsv"
    seen = {r.get("image_crc") for r in read_history(hist)}
    fp = first_parent(tree)
    full = {c: c for c in fp} | merged_same_tree(tree)
    full = {k[:n]: v for k, v in full.items() for n in (7, 8, 12)}
    added = 0
    for b in image_sources(root):
        m = STEM.match(b.stem)
        if not m:
            continue
        bj_p = b.with_name(b.stem + ".build.json")
        bj = json.loads(bj_p.read_text()) if bj_p.is_file() else {}
        tm = TAG_COMMIT.match(m.group(2))
        commit = bj.get("commit") or (tm.group(1) if tm else "")
        commit = full.get(commit[:12]) or full.get(commit[:8]) or full.get(commit[:7]) or ""
        if not commit:
            continue
        dirty = int(bool(bj.get("dirty"))) if "dirty" in bj else int(bool(tm and tm.group(2)))
        defs = bj.get("defines")
        if defs is None:
            rest = m.group(2)[tm.end():] if tm else ""
            parts = [p for p in rest.split("-") if p and p != "rel"]
            if any(p not in TAG_DEFS and p != "audio" and p != "test" for p in parts):
                continue                                  # unknown tag suffix: variant not recoverable
            defs = [TAG_DEFS[p] for p in parts if p in TAG_DEFS] + (["_AWTO_AUDIO_TEST"] if "audio" in parts else [])
        crc = f"{zlib.crc32(b.read_bytes()):08x}"
        if crc in seen:
            continue
        nums, funcs = measure(b, b.with_suffix(".map"), None, bj)
        layout = bj.get("layout_mode") or ("release" if "-rel" in m.group(2) else "dev")
        row = {"time": datetime.fromtimestamp(b.stat().st_mtime).astimezone().isoformat(timespec="seconds"), "tree": str(b.parent),
               "branch": "main" if not dirty else "", "commit": commit, "dirty": dirty, "diff_hash": "?" if dirty else "",
               "serial": m.group(1), "tag": m.group(2), "variant": variant_of(defs), "layout": layout, "src": "backfill",
               "image": b.stem, **nums}
        append_row(hist, row, funcs)
        seen.add(crc)
        added += 1
    say(f"backfill: {added} rows added to {hist}")
    return added


def select(rows: list[dict], main_fp: list[str], *, serial=None, variant="default", branch=None, dirty_n=5, everything=False) -> list[dict]:
    """Graph rows: one per main first-parent commit (oldest first; newest clean row), then the newest dirty / branch rows."""
    rows = [r for r in rows if (not serial or r.get("serial") == serial) and (everything or r.get("variant") == variant)]
    pos = {c: i for i, c in enumerate(main_fp)}
    per = {}
    for r in rows:
        c = r.get("commit", "")[:12]
        if str(r.get("dirty")) != "1" and c in pos and (c not in per or r.get("time", "") >= per[c].get("time", "")):
            per[c] = r
    out = sorted(per.values(), key=lambda r: -pos[r["commit"][:12]])
    extra = [r for r in rows if r.get("commit", "")[:12] not in per or str(r.get("dirty")) == "1"]
    if branch:
        extra = [r for r in extra if r.get("branch") == branch]
    else:
        extra = [r for r in extra if str(r.get("dirty")) == "1"][-dirty_n:] if dirty_n else []
    return out + sorted(extra, key=lambda r: r.get("time", ""))


GRAPH = [("common_b", "flash common B"), ("banked_b", "flash banked total B"), ("bank_free", "free per bank B"),
         ("direct_free", "direct IRAM free B"), ("xdata_free", "XDATA free B"), ("bseg_bits", "BSEG bits")]
JUMPS_N = 3        # largest steps labelled per metric (display only)


def _num(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def graph(rows: list[dict], out: Path, title: str) -> tuple[Path, Path]:
    """PNG + HTML (inline SVG + table) of the selected rows; x = build order labelled by commit (* = dirty)."""
    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out.mkdir(parents=True, exist_ok=True)
    xs = list(range(len(rows)))
    labels = [label(r).split("*")[0] + ("*" if str(r.get("dirty")) == "1" else "") for r in rows]
    fig, axs = plt.subplots(len(GRAPH), 1, figsize=(max(10, 0.18 * len(rows) + 4), 3 * len(GRAPH)), sharex=True)
    for ax, (col, name) in zip(axs, GRAPH, strict=True):
        series = {}
        if col == "bank_free":
            for i, r in enumerate(rows):
                for b, f in bank_map(r.get(col, "")).items():
                    series.setdefault(f"b{b}", [None] * len(rows))[i] = f
        else:
            series[name] = [_num(r.get(col)) for r in rows]
        for k, ys in sorted(series.items(), key=lambda kv: int(kv[0][1:]) if kv[0][1:].isdigit() else 0):
            ax.plot(xs, [y if y is not None else float("nan") for y in ys], marker=".", linewidth=1, label=k)
            steps = [(abs(ys[i] - ys[i - 1]), i, ys[i] - ys[i - 1]) for i in range(1, len(ys))
                     if ys[i] is not None and ys[i - 1] is not None and ys[i] != ys[i - 1]]
            for _m, i, d in sorted(steps, reverse=True)[:JUMPS_N if col != "bank_free" else 1]:
                ax.annotate(f"{d:+d}", (i, ys[i]), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=7)
        ax.set_ylabel(name, fontsize=8)
        ax.grid(True, alpha=0.3)
        if col == "bank_free":
            ax.legend(fontsize=6, ncol=8, loc="upper left")
    axs[-1].set_xticks(xs, labels, rotation=90, fontsize=6)
    axs[0].set_title(title, fontsize=9)
    fig.tight_layout()
    png = out / "size-graph.png"
    fig.savefig(png, dpi=110)
    svg = io.StringIO()
    fig.savefig(svg, format="svg")
    plt.close(fig)
    cols = ["time", "commit", "dirty", "diff_hash", "serial", "variant", "layout", "src", *NUM, "min_bank_free", "image_crc", "image"]
    tab = "".join("<tr>" + "".join(f"<td>{r.get(c, '')}</td>" for c in cols) + "</tr>" for r in reversed(rows))
    html = out / "size-graph.html"
    html.write_text("<!doctype html><meta charset=utf-8><title>Size history</title>"
                    "<style>body{font:12px sans-serif;background:#fff;color:#111}table{border-collapse:collapse}"
                    "td,th{border:1px solid #ccc;padding:1px 4px}svg{max-width:100%;height:auto}</style>"
                    f"<h3>{title}</h3>{svg.getvalue()[svg.getvalue().index('<svg'):]}"
                    "<table><tr>" + "".join(f"<th>{c}</th>" for c in cols) + f"</tr>{tab}</table>")
    return png, html


def graph_main(argv: list[str], *, say=print) -> int:
    """./dev.py size-graph: [--backfill] [--serial S] [--variant V | --all] [--branch B] [--dirty N] [--out DIR]."""
    import argparse
    ap = argparse.ArgumentParser(prog="dev.py size-graph")
    ap.add_argument("--backfill", action="store_true", help="first add rows for archived images of main's first-parent commits")
    ap.add_argument("--serial")
    ap.add_argument("--variant", default="default")
    ap.add_argument("--all", action="store_true", help="every variant")
    ap.add_argument("--branch", help="instead of the newest dirty builds: every build of this branch")
    ap.add_argument("--dirty", type=int, default=5, help="newest dirty builds appended (default 5)")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    root = main_root()
    tree = Path(_git(Path.cwd(), "rev-parse", "--show-toplevel") or root)
    if a.backfill:
        backfill(root, tree, say=say)
    rows = read_history(size_dir(root) / "size-history.tsv")
    fp = first_parent(tree)
    sel = select(rows, fp, serial=a.serial, variant=a.variant, branch=a.branch, dirty_n=a.dirty, everything=a.all)
    if not sel:
        say(f"size-graph: no rows match (history {len(rows)} rows); nothing drawn")
        return 1
    on_main = [r for r in sel if r.get("commit", "")[:12] in set(fp)]
    oldest = max(on_main, key=lambda r: fp.index(r["commit"][:12]), default=None)
    title = (f"size history: {len(sel)} builds, serial {a.serial or 'any'}, variant {'any' if a.all else a.variant}"
             f"{', oldest main commit ' + label(oldest) + ' ' + oldest.get('time', '')[:10] if oldest else ''}")
    png, html = graph(sel, a.out or size_dir(root), title)
    say(title)
    say(f"graph {png}")
    say(f"page  {html}")
    return 0
