#!/usr/bin/env python3
"""Scan unpacked firmware packages for scaler images, debug symbols and host apps (read-only, never executes).

usage: python3 -I fw_pkg_scan.py <vendor> <package|*> [--copy] [--model NAME]
- Input: ~/vendors/<vendor>/analysis/<package>/unpacked/ (from fw_pkg_unpack.py).
- Appends rows (replacing earlier rows of the same package) to ~/vendors/realtek/analysis/:
    found_images.tsv    vendor model package file size family_guess evidence fw_version build_date model_strings caps edid c51 entropy
    found_symbols.tsv   vendor package file kind family_guess names
    found_hostapps.tsv  vendor package app version transport addresses_opcodes evidence
- --copy puts candidate images in ~/vendors/<vendor>/analysis/<package>/images/ (unique names).
- Image test: 64 KiB..16 MiB, not a known container/PE/text, 8051 signs (LJMP reset, vector spacing,
  MOV DPTR/LCALL/RET density) or Realtek strings; entropy > 7.6 -> "encrypted/compressed?".
- Family guess = strings (RTDnnnn/RL64nn) first; else the register fingerprint: distinct MOV DPTR,#imm16
  targets that are REG addresses of each chip in re/regdb/*.tsv.gz (exclusive addresses weigh the guess;
  weak: RTD2795T vs RTD2797 differ by only a few exclusive hits on our own dump).
- Patterns catalog: scripts/fw_pkg_patterns.json (package layouts); matched pattern id goes in evidence.
Log: tmp/logs/fw_pkg_scan-<package>.log
"""
import collections, fnmatch, gzip, json, math, os, re, shutil, subprocess, sys
from pathlib import Path

HOME = Path.home()
MONTHS = "Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
NAME_HINT = re.compile(r"(?:Scaler|UserCommon|Osd|Sys|RTD|RL6|Ddcci|Flash|Mcu)[A-Za-z0-9_]{4,}")
SYM_EXT = {".m51": "keil-map", ".map": "linker-map", ".lst": "keil-listing", ".omf": "omf", ".abs": "keil-abs",
           ".pdb": "pdb", ".sym": "symbols", ".lin": "keil-link-script", ".elf": "elf", ".so": "elf-so",
           ".lib": "keil-lib", ".h00": "bank-hex", ".hex": "hex"}
KIND_SKIP = (b"MZ", b"PK\x03\x04", b"%PDF", b"\x89PNG", b"GIF8", b"\xff\xd8\xff", b"7z\xbc\xaf", b"\x7fELF", b"Rar!")
TRANSPORT_KEYS = {
    "NvAPI": b"nvapi", "ADL": b"atiadlxx", "IGCL": b"ControlLib", "Intel-IGFX": b"igfx",
    "dxva2-MonitorConfig": b"GetVCPFeatureAndVCPFeatureReply", "dxva2-caps": b"CapabilitiesRequestAndCapabilitiesReply",
    "dxva2-SetVCP": b"SetVCPFeature", "USB-HID": b"HidD_", "hid.dll": b"hid.dll", "libusb": b"libusb",
    "WinUSB": b"winusb", "SetupAPI": b"SetupDiGetClassDevs", "UVC-ext": b"AitUVCExt", "WMI-monitor": b"WmiMonitor",
    "I2C-string": b"i2c", "DDC-string": b"ddc", "DP-AUX": b"aux", "CH341": b"ch341", "FTDI": b"ftd2xx",
    "serial": b"\\\\.\\COM", "Realtek-ISP": b"RFlash", "Realtek-HID": b"RtHIDlib"}
ADDR_RES = {  # (label, regex on ASCII strings)
    "ddcci-0x37/0x6E": re.compile(rb"\b(?:0x)?(?:37|6E|6F|6e|6f)\b[^\n]{0,20}(?:DDC|I2C|slave|addr)", re.I),
    "isp-0x4A": re.compile(rb"\b(?:0x)?4[Aa]\b[^\n]{0,20}(?:ISP|slave|I2C)", re.I),
    "debug-0x35": re.compile(rb"\b(?:0x)?35\b[^\n]{0,20}(?:debug|slave)", re.I)}


def repo_root():
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).parent,
                                            text=True).strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path(__file__).resolve().parent.parent


ROOT = repo_root()


def load_regdb():
    sets = {}
    for p in sorted((ROOT / "re/regdb").glob("*.tsv.gz")):
        s = set()
        for l in gzip.open(p, "rt"):
            f = l.split("\t")
            if len(f) > 5 and f[4] == "REG":
                try:
                    s.add(int(f[1], 16))
                except ValueError:
                    pass
        sets[p.name.split(".")[0]] = s
    return sets


def entropy(b):
    if not b:
        return 0.0
    c = collections.Counter(b); n = len(b)
    return -sum(v / n * math.log2(v / n) for v in c.values())


def ascii_strings(b, n=5):
    return re.findall(rb"[\x20-\x7e]{%d,}" % n, b)


def utf16_strings(b, n=5):
    return [s.decode("utf-16le", "replace") for s in re.findall(rb"(?:[\x20-\x7e]\x00){%d,}" % n, b)]


def mcu8051_score(d):
    """Return (looks_8051, details). Reset LJMP, 8-byte spaced vectors, opcode density."""
    if len(d) < 4096:
        return False, {}
    reset = d[0] == 0x02 and ((d[1] << 8 | d[2]) < len(d))
    vec = sum(1 for a in range(0x03, 0x60, 8) if d[a] in (0x02, 0x32, 0x01, 0x21, 0x22, 0x00))
    samp = d[:min(len(d), 1 << 20)]
    c = collections.Counter(samp); n = len(samp)
    dens = {k: c[v] / n for k, v in (("dptr", 0x90), ("lcall", 0x12), ("ret", 0x22), ("movx", 0xE0))}
    ok = reset and (vec >= 6) and dens["dptr"] > 0.003 and dens["lcall"] > 0.005
    return ok, dict(reset=reset, vec=vec, **{k: round(v, 4) for k, v in dens.items()})


def c51_sig(d):
    """Keil C51 startup: clear IDATA loop `MOV R0,#n; CLR A; MOV @R0,A; DJNZ R0,..`."""
    return len(re.findall(rb"\x78.\xe4\xf6\xd8\xfd", d[:1 << 20])) + len(re.findall(rb"\x78.\xe4\xf6\xd8\xfd", d[1 << 20:]))


def parse_edids(d):
    out = []
    for m in re.finditer(b"\x00\xff\xff\xff\xff\xff\xff\x00", d):
        blk = d[m.start():m.start() + 128]
        if len(blk) < 128 or sum(blk) & 0xFF:
            continue
        mid = (blk[8] << 8) | blk[9]
        mfg = "".join(chr(((mid >> s) & 31) + 64) for s in (10, 5, 0))
        prod = blk[10] | blk[11] << 8
        ser = int.from_bytes(blk[12:16], "little")
        name = ""
        for o in (54, 72, 90, 108):
            if blk[o:o + 3] == b"\x00\x00\x00" and blk[o + 3] == 0xFC:
                name = blk[o + 5:o + 18].split(b"\n")[0].decode("ascii", "replace").strip()
        out.append(f"{mfg}{prod:04X}/{ser}/wk{blk[16]}y{1990 + blk[17]}/{name}")
    return sorted(set(out))


def version_info(d):
    s = [x.decode("latin1") for x in ascii_strings(d, 4)]
    blob = "\n".join(s)
    ver = sorted(set(re.findall(r"(?i)(?:fw|firmware|ver(?:sion)?|sw)[ _.:=-]{0,3}[vr]?\d+(?:\.\d+){1,3}[A-Za-z0-9_-]{0,6}", blob)))[:6]
    dates = sorted(set(re.findall(rf"(?:{MONTHS})\s+\d{{1,2}}\s+20\d\d", blob)
                       + re.findall(r"20\d\d[-/.](?:0[1-9]|1[0-2])[-/.](?:0[1-9]|[12]\d|3[01])", blob)))[:4]
    models = sorted(set(re.findall(r"RTD\d{4}[A-Z]{0,4}|RL6\d{3}|RTS\d{4}|RTL\d{4}[A-Z]?|Realtek[ \w]{0,20}", blob)))[:8]
    caps = sorted(set(re.findall(r"\(prot\(monitor\)[^\n]{0,60}?model\(([^)]*)\)", blob)))[:3]
    hint = collections.Counter(NAME_HINT.findall(blob))
    return ver, dates, models, caps, [k for k, _ in hint.most_common(5)]


def classify_fp(d, regsets):
    hits = set()
    for i in range(len(d) - 2):
        if d[i] == 0x90:
            hits.add(d[i + 1] << 8 | d[i + 2])
    allr = list(regsets.values())
    best = []
    for k, v in regsets.items():
        excl = v - set().union(*[w for kk, w in regsets.items() if kk != k])
        best.append((len(hits & excl) + 0.1 * len(hits & v), k, len(hits & excl), len(hits & v)))
    best.sort(reverse=True)
    return best[:2], len(hits)


REF = HOME / "vendors/realtek/analysis/dumps/jxc-4k-flash-bus20.bin"
_REF = {}


def sim_ours(d, w=32, step=4):
    """Share of w-byte windows (sampled every `step` bytes, non-trivial) found anywhere in our RTD2795T dump."""
    if not REF.exists():
        return ""
    if not _REF:
        r = REF.read_bytes()
        _REF["s"] = {r[i:i + w] for i in range(0, len(r) - w) if len(set(r[i:i + w])) > 6}
    ref = _REF["s"]
    n = hit = 0
    for i in range(0, min(len(d), 4 << 20) - w, step):
        x = d[i:i + w]
        if len(set(x)) > 6:
            n += 1
            hit += x in ref
    return f"{100 * hit / n:.1f}%" if n else ""


def match_pattern(pkg_files, patterns):
    names = [os.path.basename(f) for f in pkg_files]
    out = []
    for p in patterns:
        need = p.get("package_files_all", [])
        if need and all(any(fnmatch.fnmatch(n, g) for n in names) for g in need):
            out.append(p["id"])
    return out


def load_patterns():
    p = Path(__file__).with_name("fw_pkg_patterns.json")
    return json.loads(p.read_text()) if p.exists() else []


def replace_rows(path, header, key_col, key, rows):
    old = []
    if path.exists():
        old = [l for l in path.read_text().splitlines()[1:] if l.split("\t")[key_col] != key]
    path.write_text("\t".join(header) + "\n" + "\n".join(old + ["\t".join(str(x).replace("\t", " ").replace("\n", " ") for x in r) for r in rows]) + "\n")


def scan(vendor, pkg, copy, model, regsets, patterns):
    base = HOME / "vendors" / vendor / "analysis" / pkg
    udir = base / "unpacked"
    files = sorted(p for p in udir.rglob("*") if p.is_file())
    rel = [str(f.relative_to(udir)) for f in files]
    pats = match_pattern(rel, patterns)
    if not model:
        model = re.sub(r"(?i)^(gigabyte_|aorus_|giga_)", "", pkg).upper()
    imgs, syms, apps = [], [], []
    for f in files:
        size = f.stat().st_size
        ext = f.suffix.lower()
        with f.open("rb") as fh:
            head = fh.read(4096)
        if ext in SYM_EXT:
            kind = SYM_EXT[ext]
            if ext in (".hex", ".lin") and size < 2000:
                continue
            blob = f.read_bytes()[:4_000_000]
            names = collections.Counter(NAME_HINT.findall(blob.decode("latin1")))
            if ext in (".hex",) and not names:
                continue
            syms.append((vendor, pkg, str(f.relative_to(udir)), kind, "", ",".join(k for k, _ in names.most_common(6))))
        if head[:2] == b"MZ" and size > 8192:
            d = f.read_bytes()
            lowname = f.name.lower()
            tr = [k for k, v in TRANSPORT_KEYS.items() if v.lower() in d.lower()]
            if (set(tr) - {"I2C-string", "DDC-string", "DP-AUX", "serial"}) or any(w in lowname for w in ("upd", "flash", "isp", "fw")):
                u16 = " ".join(utf16_strings(d, 6))
                fv = re.findall(r"(?:FileVersion|ProductVersion)\W+(\d+(?:\.\d+){1,3})", u16)
                prod = re.findall(r"(?:ProductName|FileDescription)\W+([\w .\-]{3,40})", u16)
                ad = [k for k, rx in ADDR_RES.items() if rx.search(d)]
                pdbs = sorted(set(re.findall(rb"[A-Za-z]:\\[\x20-\x7e]{3,120}?\.pdb", d)))[:2]
                if pdbs:
                    syms.append((vendor, pkg, str(f.relative_to(udir)), "pdb-path", "", b";".join(pdbs).decode("latin1")))
                apps.append((vendor, pkg, f.name, ",".join(sorted(set(fv))[:2]) or "", ",".join(tr), ",".join(ad),
                             f"size={size}; {';'.join(sorted(set(prod))[:2])}"))
            continue
        if size < 65536 or size > 16 << 20 or head.startswith(KIND_SKIP):
            continue
        if ext in (".txt", ".xml", ".ini", ".cfg", ".inf", ".cat", ".lang", ".dat", ".iss", ".sys", ".dll", ".exe"):
            continue
        d = f.read_bytes()
        ent = entropy(d[:1 << 20])
        ok, det = mcu8051_score(d)
        ver, dates, models, caps, hint = version_info(d)
        upd = f.with_name("upd.xml")
        if upd.exists():  # Gigabyte/Realtek updater pack manifest: <model>, <fw>, <fw_ver>
            t = upd.read_text(errors="replace")
            for m in re.finditer(r"<model>([^<]*)</model>.*?<fw>([^<]*)</fw>.*?<fw_ver>([^<]*)</fw_ver>", t, re.S):
                if m.group(2) == f.name:
                    ver.append(f"upd.xml:{m.group(1)}/{m.group(3)}")
        edids = parse_edids(d)
        c51 = c51_sig(d)
        if not (ok or models or caps or ext in (".bin", ".upg", ".img", ".rom")):
            continue
        fam, ev = "", []
        top, nd = classify_fp(d, regsets) if ok else ([], 0)
        rtd = [m for m in models if m.startswith(("RTD", "RL6"))]
        other = sorted(set(re.findall(r"NT6\d{4}|Novatek|MStar|MSTAR|MST\d{4}|MediaTek|MT\d{4}[A-Z]?|Genesis|Pixelworks",
                                      "\n".join(x.decode("latin1") for x in ascii_strings(d, 5)))))[:3]
        if rtd:
            fam = "string:" + "/".join(rtd[:3]) + ("" if ok else " non-8051?")
        elif other:
            fam = "other-vendor:" + "/".join(other)
        elif ok:
            fam = "8051-banked:" + (top[0][1] if top and top[0][2] > 0 else "unknown")
        else:
            fam = "unknown"
        if ent > 7.6:
            fam += " (encrypted/compressed?)"
        ev.append(f"8051={det}" if ok else f"8051=no {det}")
        if top:
            ev.append("regfp=" + ",".join(f"{k}:excl{e}/all{a}" for _, k, e, a in top) + f"/dptr{nd}")
        if pats:
            ev.append("pattern=" + "+".join(pats))
        if size % 65536 == 0:
            ev.append(f"{size // 65536}x64KiB")
        imgs.append((vendor, model, pkg, str(f.relative_to(udir)), size, fam, "; ".join(ev), ",".join(ver),
                     ",".join(dates), ",".join(models + hint[:2]), ",".join(caps), ",".join(edids[:2]), c51, f"{ent:.2f}", sim_ours(d) if ok else ""))
        if copy:
            idir = base / "images"; idir.mkdir(exist_ok=True)
            shutil.copy2(f, idir / f.name)
    return imgs, syms, apps


def main():
    a = sys.argv[1:]
    copy = "--copy" in a
    model = a[a.index("--model") + 1] if "--model" in a else ""
    pos = [x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or a[i - 1] != "--model")]
    if len(pos) < 2:
        print(__doc__); return 2
    vendor, pkg = pos
    pkgs = [pkg]
    if pkg == "*":
        pkgs = sorted(d.name for d in (HOME / "vendors" / vendor / "analysis").iterdir() if (d / "unpacked").is_dir())
    regsets = load_regdb()
    patterns = load_patterns()
    adir = HOME / "vendors/realtek/analysis"
    (ROOT / "tmp/logs").mkdir(parents=True, exist_ok=True)
    for pk in pkgs:
        imgs, syms, apps = scan(vendor, pk, copy, model, regsets, patterns)
        replace_rows(adir / "found_images.tsv", "vendor model package file size family_guess evidence fw_version build_date model_strings caps edid c51_sigs entropy sim_ours_2795t".split(), 2, pk, imgs)
        replace_rows(adir / "found_symbols.tsv", "vendor package file kind family_guess names".split(), 1, pk, syms)
        replace_rows(adir / "found_hostapps.tsv", "vendor package app version transport addresses_opcodes evidence".split(), 1, pk, apps)
        msg = f"{vendor}/{pk}: images={len(imgs)} symbols={len(syms)} hostapps={len(apps)}"
        print(msg)
        with (ROOT / f"tmp/logs/fw_pkg_scan-{pk}.log").open("w") as lf:
            lf.write(msg + "\n" + "\n".join("\t".join(map(str, r)) for r in imgs + syms + apps) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
