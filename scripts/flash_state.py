#!/usr/bin/env python3
"""Per-unit flash-state manifest + incremental diff + drift guard for rtd_flash_image.py (#12). Pure logic, no hardware.

Manifest: tmp/fw/<serial>-flash-state.json
  {version, serial, sector_size, image, image_size, time, git_commit, source, sectors: [sha256-hex | null] x 256}
  - sectors[i] = SHA-256 of what is KNOWN to be in flash sector i; null = unknown (never read, or a write was
    in flight / failed). Entries beyond the last image are kept: those sectors are never touched (banks 14-15, #8).
Writers: after every verified sector (saved every SAVE_EVERY and at exit), after any full flash read.
Hardware CRC8 (FF75, poly 0x07 init 0): docs/flash-crc.md.
"""
import hashlib
import json
import os
import random
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

SECTOR = 4096
FLASH_SECTORS = 256            # 1 MiB (JEDEC c22014)
SAVE_EVERY = 16                # sectors between manifest saves while writing (~2 s of flashing each)
VERSION = 1


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sector_hashes(img: bytes) -> list[str]:
    return [sha(img[i:i + SECTOR]) for i in range(0, len(img), SECTOR)]


def _crc_table():
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = ((c << 1) ^ 0x07) & 0xFF if c & 0x80 else (c << 1) & 0xFF
        t.append(c)
    return t


_CRC = _crc_table()


def crc8(data: bytes, crc: int = 0) -> int:
    """CRC-8 poly 0x07, init 0, no reflection (ATM/SMBus). Same as the RTD266x chip CRC (KunYi/RTD266x crc.c)."""
    for b in data:
        crc = _CRC[crc ^ b]
    return crc


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def git_commit(repo: Path) -> str:
    try:
        c = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=repo, capture_output=True, text=True, timeout=5).stdout.strip()
        d = subprocess.run(["git", "diff", "--quiet"], cwd=repo, timeout=5).returncode
        return c + ("+" if d else "")
    except Exception:
        return "unknown"


@dataclass
class FlashState:
    path: Path
    serial: str
    sectors: list = field(default_factory=lambda: [None] * FLASH_SECTORS)
    image: str = ""
    image_size: int = 0
    source: str = ""
    commit: str = ""
    time: str = ""

    @classmethod
    def load(cls, path: Path, serial: str, log=print):
        """None when missing, unreadable, another unit's, or malformed (caller then takes the full path)."""
        if not path.exists():
            return None
        try:
            d = json.loads(path.read_text())
            ok = (d["version"] == VERSION and d["serial"] == serial and d["sector_size"] == SECTOR
                  and len(d["sectors"]) == FLASH_SECTORS
                  and all(s is None or (isinstance(s, str) and len(s) == 64) for s in d["sectors"]))
            if not ok:
                raise ValueError("version/serial/geometry mismatch")
        except Exception as e:
            log(f"flash-state {path}: unusable ({e}); ignoring it")
            return None
        return cls(path, serial, d["sectors"], d.get("image", ""), d.get("image_size", 0),
                   d.get("source", ""), d.get("git_commit", ""), d.get("time", ""))

    @classmethod
    def empty(cls, path: Path, serial: str):
        return cls(path, serial)

    def save(self, image=None, image_size=None, source=None, commit=None):
        if image is not None: self.image = image
        if image_size is not None: self.image_size = image_size
        if source is not None: self.source = source
        if commit is not None: self.commit = commit
        self.time = now_iso()
        d = {"version": VERSION, "serial": self.serial, "sector_size": SECTOR, "image": self.image,
             "image_size": self.image_size, "time": self.time, "git_commit": self.commit,
             "source": self.source, "sectors": self.sectors}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Persist unknown BEFORE erase. Atomic rename alone does not make data
        # durable across host loss; sync the replacement and its directory.
        fd, name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        tmp = Path(name)
        try:
            with os.fdopen(fd, "w") as out:
                out.write(json.dumps(d, indent=0))
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass  # cleanup must not mask the failed durable checkpoint


@dataclass
class Plan:
    write: list        # sector indexes to erase+program
    unchanged: list    # manifest hash == new hash: skipped, drift-checked
    unknown: list      # manifest lacks them: resolve by readback before deciding


def plan(img_hashes: list[str], state, full: bool) -> Plan:
    n = len(img_hashes)
    if full or state is None:
        return Plan(list(range(n)), [], [])
    w, u, k = [], [], []
    for i, h in enumerate(img_hashes):
        m = state.sectors[i]
        (k if m is None else u if m == h else w).append(i)
    return Plan(w, u, k)


def pick_sample(unchanged: list, rng: random.Random) -> list:
    """First + last + 2 random of the 'unchanged' sectors (all of them when <= 4).
    Count reasoning: first/last catch a wholesale image swap (RTDTool, another tool, a wrong-unit flash) and
    cost 2 sector reads; 2 random catch a partial overwrite of >= ~25% of the image with p >= 0.44 each
    run; more reads (0.4 s each) are dominated by the CRC sweep that covers every unchanged sector."""
    if len(unchanged) <= 4:
        return sorted(unchanged)
    mid = unchanged[1:-1]
    return sorted({unchanged[0], unchanged[-1], *rng.sample(mid, 2)})


def drift_check(isp, img: bytes, state, unchanged: list, rng: random.Random, crc_ok: bool, log=print) -> list:
    """Sectors whose flash content differs from the manifest.
    CRC engine validated: one hardware CRC8 per contiguous run of unchanged sectors (Dan 2026-11-06: cheap, just
    work); a run mismatch is localised per sector. Otherwise readback+SHA of a sample."""
    if crc_ok:
        return _drift_runs(isp, img, unchanged, log)
    bad = []
    sample = pick_sample(unchanged, rng)
    for i in sample:
        a = i * SECTOR
        got = sha(isp.read_flash(a, SECTOR))
        if got != state.sectors[i]:
            log(f"DRIFT: sector {i} (0x{a:06x}) readback sha {got[:12]} != manifest {state.sectors[i][:12]}")
            bad.append(i)
    if crc_ok:
        for i in unchanged:
            if i in sample:
                continue
            a = i * SECTOR
            hw, py = isp.flash_crc(a, SECTOR), crc8(img[a:a + SECTOR])
            if hw != py:
                log(f"DRIFT: sector {i} (0x{a:06x}) hw crc 0x{hw:02x} != manifest-image crc 0x{py:02x}")
                bad.append(i)
    log(f"drift guard: {len(sample)} readback sample(s) {[hex(i * SECTOR) for i in sample]}"
        f"{f' + CRC sweep of {len(unchanged) - len(sample)}' if crc_ok else ' (CRC off)'}: "
        f"{'OK' if not bad else f'{len(bad)} MISMATCH'}")
    return sorted(set(bad))


def _runs(idx: list) -> list:
    """Sorted sector indexes -> [(first, last)] contiguous runs."""
    out = []
    for i in sorted(idx):
        if out and i == out[-1][1] + 1:
            out[-1] = (out[-1][0], i)
        else:
            out.append((i, i))
    return out


def _drift_runs(isp, img: bytes, unchanged: list, log=print) -> list:
    bad = []
    runs = _runs(unchanged)
    for a, b in runs:
        lo, hi = a * SECTOR, (b + 1) * SECTOR
        if isp.flash_crc(lo, hi - lo) == crc8(img[lo:hi]):
            continue
        for i in range(a, b + 1):                    # localise
            s = i * SECTOR
            if isp.flash_crc(s, SECTOR) != crc8(img[s:s + SECTOR]):
                log(f"DRIFT: sector {i} (0x{s:06x}) hw crc != image crc")
                bad.append(i)
    log(f"drift guard: CRC over {len(runs)} run(s) of {len(unchanged)} unchanged sectors: "
        f"{'OK' if not bad else f'{len(bad)} MISMATCH'}")
    return bad


def readback_diff(isp, img: bytes, state, log=print, chunk=16 * SECTOR) -> list:
    """Authoritative diff: read the whole image region, record the ACTUAL flash hashes in the manifest,
    return the sector indexes that differ from img."""
    diff = []
    for off in range(0, len(img), chunk):
        n = min(chunk, len(img) - off)
        data = isp.read_flash(off, n)
        for j in range(0, n, SECTOR):
            i = (off + j) // SECTOR
            state.sectors[i] = sha(data[j:j + SECTOR])
            if data[j:j + SECTOR] != img[off + j:off + j + SECTOR]:
                diff.append(i)
        log(f"readback diff {min(off + n, len(img)) // SECTOR}/{len(img) // SECTOR} sectors")
    return diff


def resolve_unknown(isp, img: bytes, state, unknown: list, log=print) -> list:
    """Manifest lacks these: read each, record the actual hash, return those that differ from img."""
    diff = []
    for i in unknown:
        a = i * SECTOR
        cur = isp.read_flash(a, SECTOR)
        state.sectors[i] = sha(cur)
        if cur != img[a:a + SECTOR]:
            diff.append(i)
    if unknown:
        log(f"{len(unknown)} sector(s) not in the manifest read back: {len(diff)} differ")
    return diff
