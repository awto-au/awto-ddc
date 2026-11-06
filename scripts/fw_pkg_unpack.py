#!/usr/bin/env python3
"""Recursive, never-executing unpacker for firmware update packages.

usage: fw_pkg_unpack.py <vendor> <package|*> [file ...] [--depth 6] [--force]
- Input default: every file in ~/vendors/<vendor>/sources/<package>/.
- Output: ~/vendors/<vendor>/analysis/<package>/unpacked/ (fresh; refuses a non-empty dir unless --force).
  Every container gets its own child dir "<name>.x/"; leaves stay as extracted.
- Identifies containers by magic/structure (zip, 7z, rar, cab, InstallShield cab, MSI/OLE, gz/xz/bz2/tar,
  NSIS/Inno/SFX PE via `7z l`/innoextract), runs the matching extractor (7z, innoextract, unshield,
  cabextract, msiextract), recurses until nothing new unpacks.
- Plain PE exe/dll with no archive structure is a leaf. Nothing is ever run.
- Logs: tmp/logs/fw_pkg_unpack-<package>.log; tree: <analysis>/<package>/unpack_tree.tsv
  (depth, path, size, kind, tool, result, children).
- Backstop per extractor call: 120 s (largest seen package 80 MB unpacks in < 10 s; stall guard rule).
"""
import os, shutil, subprocess, sys, time
from pathlib import Path

MAX_DEPTH = 6
CALL_TIMEOUT = 120


def repo_root():
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                            cwd=Path(__file__).parent, text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


def run(cmd):
    p = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=CALL_TIMEOUT)
    return p.returncode, (p.stdout + p.stderr)


SKIP_NAMES = ("wdfcoinstaller", "wsusscan", "windows6.0-kb", "microsoft kernel-mode", "vcredist", "vc_redist",
              "dotnetfx", "ndp4", "dpinst", "libusb")  # runtime/driver payloads: never contain scaler images


def sniff(path):
    """Return container kind or None (leaf)."""
    if any(k in path.name.lower() for k in SKIP_NAMES):
        return None
    with open(path, "rb") as f:
        head = f.read(4096)
    if head[:4] == b"PK\x03\x04" or head[:4] == b"PK\x05\x06":
        return "zip"
    if head[:6] == b"7z\xbc\xaf\x27\x1c":
        return "7z"
    if head[:4] == b"Rar!":
        return "rar"
    if head[:4] == b"ISc(":
        return "installshield-cab"
    if head[:4] == b"MSCF":
        return "cab"
    if head[:8] == bytes.fromhex("d0cf11e0a1b11ae1"):
        return "msi-ole" if path.suffix.lower() in (".msi", ".msp") else "ole"
    if head[:4] == b"xar!":
        return "xar"
    if head[:6] in (b"070701", b"070707", b"070702"):
        return "cpio"
    if head[:2] == b"\x1f\x8b":
        return "gzip"
    if head[:6] == b"\xfd7zXZ\x00":
        return "xz"
    if head[:3] == b"BZh":
        return "bzip2"
    if head[257:262] == b"ustar":
        return "tar"
    if head[:2] == b"MZ":
        rc, o = run(["7z", "l", "-slt", "-bd", str(path)])
        types = [l.split("=", 1)[1].strip() for l in o.splitlines() if l.startswith("Type = ")]
        # PE-only listings are plain executables; anything else is an SFX/installer 7z understands
        extra = [t for t in types if t != "PE"]
        if extra:  # overlay/resource archive found by 7z (e.g. SFX 7z appended to a PE)
            return "pe-sfx:" + extra[0]
        # Inno Setup is not understood by 7z
        with open(path, "rb") as f:
            blob = f.read(os.path.getsize(path))
        if b"NullsoftInst" in blob:
            return "nsis"
        if b"Inno Setup Setup Data" in blob:
            return "inno"
        if b"InstallShield" in blob[-2_000_000:] and b"ISSetupStream" in blob:
            return "installshield-pe"
        return None
    return None


def extract(kind, src, dst):
    dst.mkdir(parents=True)
    if kind == "installshield-cab":
        return "unshield", run(["unshield", "-d", str(dst), "x", str(src)])
    if kind == "inno":
        return "innoextract", run(["innoextract", "-d", str(dst), str(src)])
    if kind == "msi-ole":
        return "msiextract", run(["msiextract", "-C", str(dst), str(src)])
    if kind == "cab":
        return "cabextract", run(["cabextract", "-d", str(dst), str(src)])
    return "7z", run(["7z", "x", "-y", "-bd", f"-o{dst}", str(src)])


def main():
    a = sys.argv[1:]
    force = "--force" in a
    depth_max = int(a[a.index("--depth") + 1]) if "--depth" in a else MAX_DEPTH
    pos = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or a[i - 1] != "--depth")]
    if len(pos) < 2:
        print(__doc__); return 2
    vendor, pkg, files = pos[0], pos[1], pos[2:]
    if pkg == "*":  # every package of the vendor, skipping ones already unpacked
        rc = 0
        for d in sorted((Path.home() / "vendors" / vendor / "sources").iterdir()):
            if d.is_dir() and (force or not (Path.home() / "vendors" / vendor / "analysis" / d.name / "unpacked").exists()):
                rc |= subprocess.call([sys.executable, "-I", __file__, vendor, d.name] + (["--force"] if force else []))
        return rc
    vroot = Path.home() / "vendors" / vendor
    base = vroot / "analysis" / pkg
    udir = base / "unpacked"
    if udir.exists() and any(udir.iterdir()):
        if not force:
            print(f"{udir} not empty (use --force)"); return 2
        shutil.rmtree(udir)
    udir.mkdir(parents=True, exist_ok=True)
    srcs = [Path(f) for f in files] or sorted(p for p in (vroot / "sources" / pkg).iterdir() if p.is_file())
    root = repo_root()
    (root / "tmp/logs").mkdir(parents=True, exist_ok=True)
    log = (root / f"tmp/logs/fw_pkg_unpack-{pkg}.log").open("w")
    tree = []

    def out(s):
        log.write(s + "\n"); log.flush()

    def walk(path, depth, out_parent):
        kind = sniff(path) if path.is_file() and path.stat().st_size > 0 else None
        size = path.stat().st_size if path.is_file() else 0
        if kind is None or depth >= depth_max:
            if depth == 0 and path.is_file():  # raw image shipped as-is: copy so the scan sees it
                shutil.copy2(path, out_parent / path.name)
            tree.append((depth, str(path), size, kind or "leaf", "", "leaf" if kind is None else "depth-limit", 0))
            return
        dst = out_parent / (path.name + ".x")
        if dst.exists():
            dst = out_parent / (path.name + f".{depth}.x")
        t0 = time.time()
        try:
            tool, (rc, o) = extract(kind, path, dst)
        except subprocess.TimeoutExpired:
            out(f"TIMEOUT {CALL_TIMEOUT}s {kind} {path}")
            tree.append((depth, str(path), size, kind, "?", "timeout", 0)); return
        kids = sorted(p for p in dst.rglob("*") if p.is_file()) if dst.exists() else []
        out(f"[{depth}] {kind} {path.name} via {tool} rc={rc} files={len(kids)} {time.time()-t0:.1f}s")
        if rc != 0:
            out("  " + " | ".join(o.strip().splitlines()[-3:]))
        tree.append((depth, str(path), size, kind, tool, f"rc={rc}", len(kids)))
        for k in kids:
            walk(k, depth + 1, k.parent)

    for s in srcs:
        # copy-free: extract straight from the source file, output under unpacked/
        walk(s, 0, udir)
    tp = base / "unpack_tree.tsv"
    with tp.open("w") as f:
        f.write("depth\tpath\tsize\tkind\ttool\tresult\tchildren\n")
        for r in tree:
            f.write("\t".join(str(x) for x in r) + "\n")
    out(f"tree {tp} rows={len(tree)}")
    print(f"{vendor}/{pkg}: {len(tree)} entries, {sum(1 for r in tree if r[3] != 'leaf')} containers -> {udir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
