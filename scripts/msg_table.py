#!/usr/bin/env python3
"""Debug-message string table in the firmware image (awto-ddc#56): id -> "file:line text" for the ENABLED ids.

usage: msg_table.py build [--tsv fw/msgids.tsv] [--out FILE]   table block from the enabled rows
       msg_table.py show  FILE|IMAGE.bin                       parse a block, or the block inside an image
       msg_table.py read  BUS                                  ISP-read the block from the unit's flash (halts the MCU)
Fixed location: flash 0xDA000..0xDFFFF = top 24 KiB of bank 13 (a code bank, so inside the flashed image length).
- sdcc_bank reserves it (sdcc_layout reserve=), fw_build checks no code byte lands there and pads to 14 banks.
- Rest of flash: bank 8/9 = code consts (EDID/HDCP), bank 14 = gamma, bank 15 = settings/keys: untouched.
Block (big-endian multi-byte, sorted by id; changes only when the enabled set / texts / lines change):
  0  "AMSG" | 4 ver u8 (1) | 5 ncat u8 | 6 count u16 | 8 nfile u16 | 10 idx_off u16 | 12 txt_off u16 | 14 u16 0
  16 total_len u32 | 20 hash 8 B = sha256(block with this field zeroed)[:8] | 28 u32 0
  32 cats (NUL strings) | files (NUL strings, de-duplicated) | index count x 8 B | text (NUL strings, de-duplicated)
  index entry: id u16 | cat u8 | file u8 | line u16 | text offset u16 (from txt_off)
Host lookup order (load_ids): table in the flashed image (tmp/fw/<serial>-flashed.json) -> cache tmp/msgtable/<hash>.bin
-> fw/msgids.tsv. Log: ./tmp/logs/msg_table.log
"""
import argparse, hashlib, json, struct, sys, time
import isostamp  # noqa: E402
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sdcc_overlay import repo_root  # noqa: E402

MSG_ADDR = 0xDA000
MSG_SIZE = 0x6000
MSG_BANK = 13                       # MSG_ADDR // 0x10000
MAGIC, VERSION, HDR = b"AMSG", 1, 32
assert MSG_ADDR + MSG_SIZE == (MSG_BANK + 1) * 0x10000
_ESC = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\"}


def unesc(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s) and s[i + 1] in _ESC:
            out.append(_ESC[s[i + 1]]); i += 2
        else:
            out.append(s[i]); i += 1
    return "".join(out)


def rows_from_tsv(text: str, enabled_only=True):
    """-> sorted [(id, cat, file, line, text)], first site per id."""
    out = {}
    for ln in text.splitlines():
        c = ln.split("\t")
        if len(c) < 4:
            continue
        try:
            mid = int(c[0], 16)
        except ValueError:
            continue
        if enabled_only and (len(c) < 5 or c[4] != "1"):
            continue
        f, _, n = c[2].rpartition(":")
        out.setdefault(mid, (mid, c[1], f, int(n) if n.isdigit() else 0, unesc(c[3])))
    return [out[k] for k in sorted(out)]


def build(rows) -> bytes:
    cats, files = [], []
    for _, c, f, _, _ in rows:
        if c not in cats: cats.append(c)
        if f not in files: files.append(f)
    if len(cats) > 255 or len(files) > 255:
        raise ValueError(f"{len(cats)} categories / {len(files)} files: index fields are u8")
    txt, toff = bytearray(), {}
    for r in rows:
        if r[4] not in toff:
            toff[r[4]] = len(txt)
            txt += r[4].encode("utf-8", "replace") + b"\0"
    if len(txt) > 0xFFFF:
        raise ValueError("text section over 64 KiB")
    sec = b"".join(c.encode() + b"\0" for c in cats) + b"".join(f.encode() + b"\0" for f in files)
    idx_off = HDR + len(sec)
    idx = b"".join(struct.pack(">HBBHH", i, cats.index(c), files.index(f), min(ln, 0xFFFF), toff[t])
                   for i, c, f, ln, t in rows)
    txt_off = idx_off + len(idx)
    total = txt_off + len(txt)
    hdr = bytearray(struct.pack(">4sBBHHHHHI8sI", MAGIC, VERSION, len(cats), len(rows), len(files), idx_off, txt_off,
                                0, total, b"\0" * 8, 0))
    blk = bytes(hdr) + sec + idx + bytes(txt)
    blk = blk[:20] + hashlib.sha256(blk).digest()[:8] + blk[28:]
    if total > MSG_SIZE:
        raise ValueError(f"message table {total} B > reserved {MSG_SIZE} B")
    return blk


def parse(buf: bytes) -> dict:
    """-> {hash, version, count, size, ids: {id: (cat, file:line, text)}}; ValueError when not a valid block."""
    if len(buf) < HDR or buf[:4] != MAGIC:
        raise ValueError("no AMSG magic")
    _, ver, ncat, count, nfile, idx_off, txt_off, _, total, h, _ = struct.unpack(">4sBBHHHHHI8sI", buf[:HDR])
    if ver != VERSION or total > len(buf) or total < txt_off:
        raise ValueError(f"bad version {ver} / length {total}")
    blk = bytes(buf[:total])
    if hashlib.sha256(blk[:20] + b"\0" * 8 + blk[28:]).digest()[:8] != h:
        raise ValueError("hash mismatch")
    names = blk[HDR:idx_off].split(b"\0")
    cats, files = [n.decode() for n in names[:ncat]], [n.decode() for n in names[ncat:ncat + nfile]]
    ids = {}
    for k in range(count):
        mid, c, f, ln, to = struct.unpack(">HBBHH", blk[idx_off + 8 * k:idx_off + 8 * k + 8])
        end = blk.index(b"\0", txt_off + to)
        ids[mid] = (cats[c], f"{files[f]}:{ln}", blk[txt_off + to:end].decode("utf-8", "replace"))
    return {"hash": h.hex(), "version": ver, "count": count, "size": total, "ids": ids}


def block_of(data: bytes) -> bytes:
    """A bare block, or the block inside a firmware image (fixed address)."""
    if data[:4] == MAGIC:
        return data
    return data[MSG_ADDR:MSG_ADDR + MSG_SIZE]


def cache_put(root: Path, blk: bytes, info: dict) -> Path:
    d = root / "tmp/msgtable"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{info['hash']}.bin"
    p.write_bytes(blk[:info["size"]])
    return p


def load_ids(root: Path, serial: str | None = None, table: Path | None = None):
    """-> ({id: (file:line, text)}, source). Order: explicit table (block or image), the unit's flashed image,
    newest cached table, fw/msgids.tsv. Invalid or absent tables fall through."""
    cands = []
    if table:
        cands.append(("table " + str(table), Path(table)))
    elif serial:
        fj = root / f"tmp/fw/{serial}-flashed.json"
        if fj.exists():
            try:
                cands.append(("flashed image", Path(json.loads(fj.read_text())["image"])))
            except (ValueError, KeyError):
                pass
    for what, p in cands:
        try:
            info = parse(block_of(p.read_bytes()))
            return {k: (v[1], v[2]) for k, v in info["ids"].items()}, f"{what} {info['hash']}"
        except (OSError, ValueError):
            continue
    f = root / "fw/msgids.tsv"
    if f.exists():
        return {r[0]: (f"{r[2]}:{r[3]}", r[4]) for r in rows_from_tsv(f.read_text(), enabled_only=False)}, "fw/msgids.tsv"
    return {}, "none"


def read_isp(bus: int, root: Path):
    """ISP read of header, then the table; the MCU stays halted until reset (0xEE <- 0x02). Cached by hash."""
    import rtd_flash_sector as F
    isp = F.Rtd(bus)
    isp.write(0x6F, 0x80)
    if not isp.read(0x6F) & 0x80:
        raise RuntimeError("ISP mode not enabled")
    try:
        head = isp.read_flash(MSG_ADDR, 1024)
        if head[:4] != MAGIC:
            raise ValueError("no message table at 0x%x (image without #56 block)" % MSG_ADDR)
        total = struct.unpack(">I", head[16:20])[0]
        blk = head if total <= 1024 else head + isp.read_flash(MSG_ADDR + 1024, total - 1024)
    finally:
        try:
            isp.write(0xEE, 0x02)
        except OSError:
            pass
    info = parse(blk)
    return cache_put(root, blk, info), info


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build"); b.add_argument("--tsv"); b.add_argument("--out")
    s = sub.add_parser("show"); s.add_argument("file", type=Path)
    r = sub.add_parser("read"); r.add_argument("bus", type=int)
    a = ap.parse_args()
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    lg = (root / "tmp/logs/msg_table.log").open("a")
    say = lambda t: (print(t), lg.write(f"{isostamp.now()} {t}\n"))
    if a.cmd == "build":
        blk = build(rows_from_tsv(Path(a.tsv or root / "fw/msgids.tsv").read_text()))
        info = parse(blk)
        if a.out:
            Path(a.out).write_bytes(blk)
        say(f"table: {info['count']} ids, {info['size']} B of {MSG_SIZE}, hash {info['hash']}")
    elif a.cmd == "show":
        info = parse(block_of(a.file.read_bytes()))
        say(f"table: {info['count']} ids, {info['size']} B, hash {info['hash']}")
        for k, (c, loc, t) in sorted(info["ids"].items())[:20]:
            print(f"  {k:04x} {c:10s} {loc} {t}")
    else:
        p, info = read_isp(a.bus, root)
        say(f"read from flash: {info['count']} ids, {info['size']} B, hash {info['hash']} -> {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
