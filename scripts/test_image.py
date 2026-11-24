"""Firmware image for the offline tests: no fixed serial, tag or stem (awto-ddc#339).

Resolution (`base()`): 1. $AWTO_TEST_IMAGE (stem, .bin or .map accepted)  2. newest build of THIS tree at HEAD
  (`commit` / `dirty` in tmp/fw/<stem>.build.json, no defines, dev layout; gated records first)
  3. one `./dev.py build --tag testimg` into this tree's tmp (serialised by build_guard; cached by commit).
Variants by capability: `variant("clk87")`, `variant("t0ev")`, `variant("nofrc")`, `cpu_suite(87)` or any `-D` list;
  found by (commit, defines set), else built beside the base as `<base tag>-<slug>` (same names as fw_gates --build-inputs).
Opt out of builds: AWTO_TEST_NO_BUILD=1 (the fixture then skips, naming itself).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root

ROOT = repo_root()
FW = ROOT / "tmp/fw"
TAG = "testimg"
NAMED = {"clk87": ["AWTO_CLOCK_MHZ=87"], "t0ev": ["_AWTO_T0EV_TEST"], "nofrc": ["_AWTO_FRC=_OFF"]}   # clk87 / t0ev = fw_gates.SIBLINGS
BUILD_LIMIT_S = 1800     # build_guard queue wait 600 s + a cold build 180 s, x2; on expiry the fixture fails with the build log path


class ImageUnavailable(Exception):
    pass


def _git(*a) -> str:
    r = subprocess.run(["git", "-C", str(ROOT), *a], capture_output=True, text=True, check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def _norm(defs) -> frozenset:
    return frozenset(str(d).removeprefix("-D") for d in defs)


class Image:
    def __init__(self, stem: Path):
        self.stem = Path(stem)
        self.bin = self.stem.with_suffix(".bin")
        self.map = self.stem.with_suffix(".map")
        self.build_json = self.stem.with_suffix(".build.json")
        self.settings_table = self.stem.with_suffix(".settings_table.py")
        self.name = self.stem.name

    def __fspath__(self):
        return str(self.stem)

    def __str__(self):
        return str(self.stem)

    @property
    def serial(self) -> str:
        return self.name.split("-", 1)[0]

    @property
    def tag(self) -> str:
        return self.name.split("-", 1)[1].removesuffix("-be")

    def meta(self) -> dict:
        try:
            return json.loads(self.build_json.read_text())
        except (OSError, ValueError):
            return {}

    def exists(self) -> bool:
        return self.bin.is_file() and self.map.is_file()

    def has_symbol(self, sym: str) -> bool:
        t = self.map.read_text(errors="replace")
        return f" {sym}" in t or f"CH_{sym.lstrip('_')} " in t


def _at_head(img: Image, defs: frozenset | None) -> bool:
    m = img.meta()
    if not img.exists() or m.get("commit") != _git("rev-parse", "--short", "HEAD"):
        return False
    if _git("status", "--porcelain", "--untracked-files=no") == "" and m.get("dirty"):
        return False                                    # clean tree: a dirty build is not this tree's HEAD
    if m.get("layout_mode") not in (None, "dev"):
        return False
    return _norm(m.get("defines", [])) == (defs if defs is not None else frozenset())


def _find(defs: frozenset | None) -> Image | None:
    cands = [Image(p.with_suffix("")) for p in FW.glob("*-be.bin")]
    cands = [i for i in cands if _at_head(i, defs)]
    cands.sort(key=lambda i: (i.stem.with_suffix(".gates.json").is_file(), i.bin.stat().st_mtime))
    return cands[-1] if cands else None


def _build(tag: str, defs: list[str], serial: str | None) -> Image:
    if os.environ.get("AWTO_TEST_NO_BUILD") == "1":
        raise ImageUnavailable("AWTO_TEST_NO_BUILD=1 and no image of this tree at HEAD")
    log = ROOT / "tmp/logs/test_image_build.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(ROOT / "dev.py"), "build", "--tag", tag, *(["--serial", serial] if serial else []),
           *[x for d in defs for x in ("-D", d)]]
    with log.open("a") as fh:
        fh.write(f"+ {' '.join(cmd)}\n")
        fh.flush()
        try:
            rc = subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT, timeout=BUILD_LIMIT_S, check=False).returncode
        except subprocess.TimeoutExpired:
            raise ImageUnavailable(f"build {tag} exceeded {BUILD_LIMIT_S} s; see {log}") from None
    if rc:
        raise ImageUnavailable(f"build {tag} failed rc={rc}; see {log}")
    img = _find(_norm(defs))
    if img is None:
        raise ImageUnavailable(f"build {tag} done but no image at HEAD with defines {defs} in {FW}")
    return img


def base(build: bool = True) -> Image:
    env = os.environ.get("AWTO_TEST_IMAGE")
    if env:
        p = Path(env)
        p = p if p.is_absolute() else ROOT / p
        img = Image(p.with_suffix("") if p.suffix in (".bin", ".map") else p)
        if not img.exists():
            raise ImageUnavailable(f"AWTO_TEST_IMAGE={env}: {img.bin.name} / {img.map.name} not found")
        return img
    img = _find(None)
    if img:
        return img
    if not build:
        raise ImageUnavailable("no image of this tree at HEAD in tmp/fw and no build requested")
    return _build(TAG, [], None)


def variant(kind, *defs: str) -> Image:
    """Image with the base's source state plus `defs` (a NAMED capability or -D strings); built when absent."""
    names = [kind] if kind in NAMED else []
    d = [*(x for n in names for x in NAMED[n]), *([kind] if kind and not names else []), *defs]
    b = base()
    want = _norm(b.meta().get("defines", [])) | _norm(d)
    if _norm(b.meta().get("defines", [])) == want:
        return b
    if (img := _find(want)) and img.serial == b.serial:
        return img
    slug = "-".join(names) if names else "-".join(sorted(x.lower().replace("=", "") for x in _norm(d)))
    return _build(f"{b.tag}-{slug}", [*b.meta().get("defines", []), *d], b.serial)


def cpu_suite(clock: int) -> Image:
    """CPU-suite image at `clock` MHz (fw/test/cpu_suite.c, no monitor); same names as `dev.py cpu-suite --sim --build`."""
    b = base()
    defs = ["_AWTO_CPU_SUITE", f"AWTO_CLOCK_MHZ={clock}"]
    if (img := _find(_norm(defs))) and img.serial == b.serial:
        return img
    return _build(f"cpusuite-{clock}", defs, b.serial)


def restore_port() -> None:
    """tmp/sdcc-port holds the asm of the LAST build (a variant, or a failed one, rewrites it): newer than the base .bin = rebuild the base."""
    b = base()
    port = ROOT / "tmp/sdcc-port/asm_bank/bank.asm"
    if not port.is_file() or port.stat().st_mtime > b.bin.stat().st_mtime:
        _build(b.tag, b.meta().get("defines", []), b.serial)
