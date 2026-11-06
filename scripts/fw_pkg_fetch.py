#!/usr/bin/env python3
"""Download firmware packages listed in a TSV into the vendor store (never executes anything).

usage: fw_pkg_fetch.py [list.tsv] [--min-free-gb 100]
- TSV columns: vendor, package, url, notes (default scripts/fw_pkg_sources.tsv).
- Target: ~/vendors/<vendor>/sources/<package>/<basename>; own dir per package.
- Writes <vendor>/sources/manifest.json (url, date, size, sha256, magic) and appends README.md rows.
- Good copy = size > 0, magic matches extension (zip -> PK, exe -> MZ, 7z/rar likewise); HTML = block page.
- Skips packages already present; stops if free space on the vendor store < --min-free-gb.
- Dupes: run awto-dan/scripts/vendor_dupes.py afterwards.
Log: tmp/logs/fw_pkg_fetch.log
Timeouts: connect/read 30 s per socket op (stall guard; downloads are < 50 MB on a LAN-class link).
"""
import hashlib, json, os, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124 Safari/537.36"
MAGIC = {".zip": b"PK", ".exe": b"MZ", ".7z": b"7z\xbc\xaf", ".rar": b"Rar!", ".cab": b"MSCF"}


def repo_root():
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                            cwd=Path(__file__).parent, text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


def main():
    a = sys.argv[1:]
    min_free = float(a[a.index("--min-free-gb") + 1]) if "--min-free-gb" in a else 100.0
    pos = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or a[i - 1] != "--min-free-gb")]
    root = repo_root()
    lst = Path(pos[0]) if pos else root / "scripts/fw_pkg_sources.tsv"
    vroot = Path.home() / "vendors"
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (root / "tmp/logs/fw_pkg_fetch.log").open("a")

    def out(s):
        s = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
        print(s, flush=True); log.write(s + "\n"); log.flush()

    rows = [l.rstrip("\n").split("\t") for l in lst.read_text().splitlines()[1:] if l.strip()]
    for r in rows:
        vendor, pkg, url = r[0], r[1], r[2]
        notes = r[3] if len(r) > 3 else ""
        free = shutil.disk_usage(vroot.resolve()).free / 1e9
        if free < min_free:
            out(f"STOP free space {free:.0f} GB < {min_free} GB"); return 3
        sdir = vroot / vendor / "sources" / pkg
        name = url.rsplit("/", 1)[1].split("?")[0]
        dest = sdir / name
        if dest.exists() and dest.stat().st_size > 0:
            out(f"skip {vendor}/{pkg} (present)"); continue
        sdir.mkdir(parents=True, exist_ok=True)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            h = hashlib.sha256(); n = 0
            with urllib.request.urlopen(req, timeout=30) as resp, dest.open("wb") as f:
                head = b""
                while True:
                    c = resp.read(1 << 20)
                    if not c:
                        break
                    if len(head) < 8:
                        head += c[:8]
                    f.write(c); h.update(c); n += len(c)
        except Exception as e:
            out(f"FAIL {vendor}/{pkg} {url}: {e}"); dest.unlink(missing_ok=True); continue
        ext = dest.suffix.lower()
        ok = n > 0 and (ext not in MAGIC or head.startswith(MAGIC[ext]))
        out(f"{'ok' if ok else 'BAD'} {vendor}/{pkg} {n} B sha256={h.hexdigest()[:12]}")
        if not ok:
            dest.rename(dest.with_suffix(dest.suffix + ".bad")); continue
        mpath = vroot / vendor / "sources" / "manifest.json"
        man = json.loads(mpath.read_text()) if mpath.exists() else []
        man.append(dict(package=pkg, file=name, url=url, fetched=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                        size=n, sha256=h.hexdigest(), magic=head[:4].hex(), notes=notes))
        mpath.write_text(json.dumps(man, indent=1))
        rpath = vroot / vendor / "README.md"
        if not rpath.exists():
            rpath.write_text(f"# {vendor}\n\nFirmware/updater packages (fetched by awto-ddc scripts/fw_pkg_fetch.py). "
                             "Per-file URL/size/SHA-256: `sources/manifest.json`.\n"
                             "Good copy: size matches manifest and magic matches extension.\n\n")
        with rpath.open("a") as f:
            f.write(f"- `sources/{pkg}/{name}` ({n} B) <- {url}  ({time.strftime('%Y-%m-%d')})\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
