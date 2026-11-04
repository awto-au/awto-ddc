#!/usr/bin/env python3
"""Parse Realtek RTDCustomerTool's SPI-flash parameter table into JSON, and diff tool versions.

usage:
  rtd_flashdb_parse.py <FlashSet.dat|Flash.dat> <out.json> [--swren SWREN.dat] [--tool-version 3.8]
  rtd_flashdb_parse.py --scalers <RTDScaler dir> <out.json> [--tool-version 3.8]
  rtd_flashdb_parse.py --diff <a.json> <b.json>      (chips or scalers; exit 1 if different)

Static analysis of vendor data only (no device access). Format + evidence: docs/reversing/realtek-rtd/db-bin-format.md
Log: ./tmp/logs/rtd_flashdb_parse.log under the repo root (stdout+stderr mirrored).

FlashSet.dat ("v2", loaded by PlugIn_ISP.dll) [fw]:
  header 10 B : u32 magic 0x07020509, u16 version (2), u16 chip_count, u16 swren_count
  chips       : chip_count x 72 B records (layout in CHIP_FIELDS below)
  swren blob  : swren_count x { u32 len, len bytes } = register-level "software write enable" scripts
Flash.dat (legacy, loaded by RTDTool/PlugIn_Flash for the Flash plugin) [fw/guess]:
  header 8 B  : u32 magic, u16 version (2), u16 chip_count
  chips       : variable-length records (NUL-terminated name, ASCII-hex SWREN script embedded)
"""
import argparse
import hashlib
import json
import logging
import os
import re
import struct
import subprocess
import sys

MAGIC = 0x07020509
REC = 72
HDR = 10
SWREN_NONE = 0xFFFF
# fields skipped by --diff (padding is MSVC uninitialised-stack fill 0xCC or leftovers; index shifts when chips are inserted)
DIFF_IGNORE = {"index", "raw", "pad", "swren_offset"}


def repo_root():
    """3-tier: $AWTO_DDC_REPO -> git toplevel -> file-relative."""
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return env
    here = os.path.dirname(os.path.abspath(__file__))
    try:
        out = subprocess.run(["git", "-C", here, "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except Exception:
        return os.path.dirname(here)


def setup_log():
    logdir = os.path.join(repo_root(), "tmp", "logs")
    os.makedirs(logdir, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(os.path.join(logdir, "rtd_flashdb_parse.log")),
                  logging.StreamHandler(sys.stdout)])


def h8(b):
    return "0x%02x" % b


def cstr(b):
    return b.split(b"\0", 1)[0].decode("latin1")


# ---- SWREN script bytecode ---------------------------------------------------------------
# Ops seen in all 6 V3.8 scripts. Registers are the scaler ISP SPI-engine regs (0x60 cmd/ctl, 0x61 opcode,
# 0x64..0x66 write bytes); same engine as scripts/rtd_flash_sector.py. [fw]
def decode_script(s):
    """06 rr vv = write reg; 0d rr mm vv + 4 B = poll reg&mm==vv; anything else is left in 'unparsed'."""
    ops, i = [], 0
    while i < len(s):
        if s[i] == 0x06 and i + 3 <= len(s):
            ops.append("wr %02x=%02x" % (s[i + 1], s[i + 2])); i += 3
        elif s[i] == 0x0D and i + 8 <= len(s):
            ops.append("poll %02x&%02x==%02x args=%s" % (s[i + 1], s[i + 2], s[i + 3], s[i + 4:i + 8].hex()))
            i += 8
        else:
            break
    return ops, s[i:].hex()


def load_swren_names(path):
    """SWREN.dat: 50 B records { u16 offset into the script blob, wchar_t name[24] } (tail = uninitialised fill) [fw]."""
    out = {}
    d = open(path, "rb").read()
    for p in range(0, len(d) - 49, 50):
        off = struct.unpack_from("<H", d, p)[0]
        raw = d[p + 2:p + 50]
        name = raw.decode("utf-16-le", "ignore").split("\0", 1)[0]
        out[off] = name
    return out


# ---- FlashSet.dat (v2) -------------------------------------------------------------------
def parse_chip_v2(i, r, swren_names):
    """72 B record; offsets relative to record start. Evidence: PlugIn_ISP.dll (V3.7) FUN_10009630 (dialog load),
    FUN_1001c750 (ID match), FUN_10018f30 (WRSR), FUN_10038310 (WP enable/disable), save routine at 0x1000d9xx."""
    swoff = struct.unpack_from("<H", r, 0x36)[0]
    c = {
        "index": i,
        "name": cstr(r[0x0C:0x24]),                                   # [fw] char[24]
        "jedec": r[4:7].hex(),                                        # [fw] RDID 0x9F: mfr, type, capacity
        "dev_id": h8(r[7]),                                           # [fw] 4th ID byte: RES 0xAB / REMS 0x90 device id
        "id_bytes": r[4:12].hex(),                                    # [fw] 8 B compared by FUN_1001c750
        "id_type": struct.unpack_from("<I", r, 0)[0],                 # [fw] must equal the tool's ID-type setting to match
        "bank_count": struct.unpack_from("<H", r, 0x24)[0],           # [fw] dialog "Bank Count" = 64 KiB banks
        "size_bytes": struct.unpack_from("<H", r, 0x24)[0] * 65536,   # [fw] derived
        "sr_byte_count": r[0x26],                                     # [fw] dialog "SR Byte Count" (1..4)
        "autodetect": struct.unpack_from("<I", r, 0x28)[0],           # [fw] 0 = never matched by ID, 1/2 = matched (1 vs 2 [?])
        "sr2_read_op": h8(r[0x2C]),                                   # [fw] dialog "Read High SR OP"
        "sr3_read_op": h8(r[0x2D]),                                   # [fw]
        "sr3_write_op": h8(r[0x2E]),                                  # [fw]
        "sr4_read_op": h8(r[0x2F]),                                   # [fw]
        "sr4_write_op": h8(r[0x30]),                                  # [fw]
        "reserved_31": r[0x31:0x35].hex(),                            # [?] always 0; written to FlashSet_dos.dat
        "swren_offset": None if swoff == SWREN_NONE else swoff,       # [fw] byte offset into the script blob
        "swren_name": "None" if swoff == SWREN_NONE else swren_names.get(swoff),
        "enable_wp_sr": [h8(x) for x in r[0x38:0x3C]],                # [fw] SR1..SR4 values that turn write-protect ON
        "reserved_3c": r[0x3C:0x3E].hex(),                            # [?] always 0
        "disable_wp_sr": [h8(x) for x in r[0x3E:0x42]],               # [fw] SR1..SR4 values that turn write-protect OFF
        "reserved_42": r[0x42:0x44].hex(),                            # [?] always 0
        "swren_every_page": bool(r[0x44]),                            # [fw] dialog "Send SWREN Every Page"
        "pad": {"27": h8(r[0x27]), "35": h8(r[0x35]), "45": r[0x45:0x48].hex()},  # [guess] alignment padding, junk
        "raw": r.hex(),
    }
    return c


def parse_flashset_v2(d, swren_names):
    magic, ver, count, nsw = struct.unpack_from("<IHHH", d, 0)
    if magic != MAGIC:
        raise ValueError("bad magic 0x%08x" % magic)
    p = HDR
    chips = [parse_chip_v2(i, d[p + i * REC:p + (i + 1) * REC], swren_names) for i in range(count)]
    p += count * REC
    scripts, off = [], 0
    for k in range(nsw):
        n = struct.unpack_from("<I", d, p)[0]
        body = d[p + 4:p + 4 + n]
        if len(body) != n:
            raise ValueError("swren script %d truncated" % k)
        ops, unparsed = decode_script(body)
        scripts.append({"index": k, "offset": off, "name": swren_names.get(off), "length": n,
                        "ops": ops, "unparsed": unparsed, "raw": body.hex()})
        off += 4 + n
        p += 4 + n
    if p != len(d):
        raise ValueError("%d trailing bytes after swren blob" % (len(d) - p))
    # offsets in chip records point at the u32 length prefix of a script (cross-check)
    known = {s["offset"] for s in scripts}
    for c in chips:
        if c["swren_offset"] is not None and c["swren_offset"] not in known:
            logging.warning("chip %s: swren_offset %d matches no script", c["name"], c["swren_offset"])
    hdr = {"magic": "0x%08x" % magic, "format_version": ver, "chip_count": count, "swren_count": nsw,
           "format": "FlashSet.dat v2 (72 B records)"}
    return hdr, chips, scripts


# ---- Flash.dat (legacy) ------------------------------------------------------------------
def parse_flash_legacy(d):
    """Variable-length records: id_type u32, id[8], name\\0, then 28 B fixed fields + ASCII-hex script + 12 B trailer.
    Same field order as v2 minus the pad/reserved gaps. [fw] for the fields below; script semantics as in v2."""
    magic, ver, count = struct.unpack_from("<IHH", d, 0)
    if magic != MAGIC:
        raise ValueError("bad magic 0x%08x" % magic)
    p, chips = 8, []
    for i in range(count):
        start = p
        id_type = struct.unpack_from("<I", d, p)[0]
        idb = d[p + 4:p + 12]
        ne = d.index(b"\0", p + 12)
        name = d[p + 12:ne].decode("latin1")
        q = ne + 1
        bank, srn, flag = struct.unpack_from("<HBI", d, q)
        ops = d[q + 7:q + 12]
        en, dis = d[q + 12:q + 16], d[q + 16:q + 20]
        # two slots follow: { u32 present, u32 flag, ASCII-hex script\0 }, then bytes up to a 0x06 terminator [guess]
        slots, r = [], q + 20
        for si in range(2):
            present, flag2 = struct.unpack_from("<II", d, r)
            te = d.index(b"\0", r + 8)
            text = d[r + 8:te].decode("latin1")
            slots.append({"present": present, "flag": flag2, "text": text,
                          "bytes": bytes(int(x, 16) for x in text.split(",") if x).hex()})
            r = te + 1
            if si == 0 and d[r:r + 11] == b"\0" * 10 + b"\x06":
                slots.append({"present": 0, "flag": 0, "text": "", "bytes": ""})
                r += 11
                break
        end = d.index(b"\x06", r - 1) + 1 if d[r - 1] != 6 else r
        rec = d[start:end]
        chips.append({
            "index": i, "name": name, "jedec": idb[:3].hex(), "dev_id": h8(idb[3]), "id_bytes": idb.hex(),
            "id_type": id_type, "bank_count": bank, "size_bytes": bank * 65536, "sr_byte_count": srn,
            "autodetect": flag, "sr2_read_op": h8(ops[0]), "sr3_read_op": h8(ops[1]), "sr3_write_op": h8(ops[2]),
            "sr4_read_op": h8(ops[3]), "sr4_write_op": h8(ops[4]),
            "enable_wp_sr": [h8(x) for x in en], "disable_wp_sr": [h8(x) for x in dis],
            "swren_slots": slots, "raw": rec.hex()})
        p = end
    if p != len(d):
        raise ValueError("record parse ended at %d, file is %d bytes" % (p, len(d)))
    hdr = {"magic": "0x%08x" % magic, "format_version": ver, "chip_count": count,
           "format": "Flash.dat legacy (variable-length records, ASCII-hex SWREN script per chip)"}
    return hdr, chips, []


def infer_version(path):
    m = re.search(r"[Vv](\d+\.\d+)", os.path.realpath(path))
    return m.group(1) if m else "unknown"


def cmd_parse(src, out, swren_path, tool_version):
    d = open(src, "rb").read()
    sha = hashlib.sha256(d).hexdigest()
    base = os.path.basename(src)
    swren_names = {}
    sp = swren_path or os.path.join(os.path.dirname(os.path.abspath(src)), "SWREN.dat")
    if os.path.exists(sp):
        swren_names = load_swren_names(sp)
    try:
        hdr, chips, scripts = parse_flashset_v2(d, swren_names)
    except (ValueError, struct.error):
        logging.info("not FlashSet v2 layout, trying Flash.dat legacy layout")
        hdr, chips, scripts = parse_flash_legacy(d)
    hdr.update({"tool_version": tool_version or infer_version(src), "source_file": base,
                "source_size": len(d), "sha256": sha, "record_count": len(chips),
                "swren_dat": os.path.basename(sp) if swren_names else None})
    doc = {"header": hdr, "chips": chips}
    if scripts:
        doc["swren_scripts"] = scripts
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    logging.info("%s: %d chips, %d swren scripts, sha256 %s -> %s", base, len(chips), len(scripts), sha[:16], out)
    return 0


# ---- scaler list -------------------------------------------------------------------------
def cmd_scalers(root, out, tool_version):
    import configparser
    scalers = []
    for name in sorted(os.listdir(root)):
        dp = os.path.join(root, name)
        if not os.path.isdir(dp):
            continue
        files = {}
        for fn in sorted(os.listdir(dp)):
            b = open(os.path.join(dp, fn), "rb").read()
            files[fn] = {"size": len(b), "sha256": hashlib.sha256(b).hexdigest()}
        info, ver = {}, {}
        ra = os.path.join(dp, "ReadAll.txt")
        if os.path.exists(ra):
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            cp.optionxform = str
            cp.read_string(open(ra, encoding="latin1").read())
            if cp.has_section("ScalerInfor"):
                info = dict(cp["ScalerInfor"])
        for fn in files:
            if fn.lower() == "version.txt":
                cp = configparser.ConfigParser(interpolation=None, strict=False)
                cp.optionxform = str
                cp.read_string(open(os.path.join(dp, fn), encoding="latin1").read())
                ver = {k: dict(cp[k]) for k in cp.sections()}
        scalers.append({"dir": name, "scaler_name": info.get("ScalerName"),
                        "scaler_id": int(info["ScalerID"]) if "ScalerID" in info else None,
                        "scaler_file_version": info.get("ScalerFileVersion"), "ic_type": info.get("IcType"),
                        "version_txt": ver, "files": files})
    ids = {}
    for s in scalers:
        ids.setdefault(s["scaler_id"], []).append(s["scaler_name"])
    dup = {str(k): v for k, v in ids.items() if len(v) > 1}
    doc = {"header": {"tool_version": tool_version or infer_version(root), "source_dir": os.path.basename(root.rstrip("/")),
                      "scaler_count": len(scalers),
                      "duplicate_ids": dup,
                      "note": "tool ignores scalers sharing a name or ID ('More then one scaler has same ID. Ignore it!')"},
           "scalers": scalers}
    with open(out, "w") as f:
        json.dump(doc, f, indent=1)
        f.write("\n")
    logging.info("%d scalers, duplicate ids %s -> %s", len(scalers), dup, out)
    return 0


# ---- diff --------------------------------------------------------------------------------
def _keyed(doc):
    if "chips" in doc:
        seen, out = {}, {}
        for c in doc["chips"]:
            k = c["name"]
            n = seen.get(k, 0); seen[k] = n + 1
            out[k if n == 0 else "%s#%d" % (k, n + 1)] = {x: y for x, y in c.items() if x not in DIFF_IGNORE}
        return "chip", out
    if "scalers" in doc:
        return "scaler", {s["dir"]: {x: y for x, y in s.items() if x != "files"} | {"files": {k: v["sha256"] for k, v in s["files"].items()}}
                          for s in doc["scalers"]}
    raise ValueError("neither chips nor scalers in JSON")


def cmd_diff(a, b):
    da, db = json.load(open(a)), json.load(open(b))
    kind, ka = _keyed(da)
    kind2, kb = _keyed(db)
    if kind != kind2:
        raise ValueError("cannot diff %s against %s" % (kind, kind2))
    ha, hb = da["header"], db["header"]
    lines = ["# %s diff: %s (%s, %s) -> %s (%s, %s)" % (kind, os.path.basename(a), ha.get("tool_version"), ha.get("sha256", "")[:12],
                                                      os.path.basename(b), hb.get("tool_version"), hb.get("sha256", "")[:12])]
    added = [k for k in kb if k not in ka]
    removed = [k for k in ka if k not in kb]
    changed = [k for k in ka if k in kb and ka[k] != kb[k]]
    for k in added:
        jid = kb[k].get("jedec", kb[k].get("scaler_id", ""))
        lines.append("+ added   %s (%s)" % (k, jid))
    for k in removed:
        jid = ka[k].get("jedec", ka[k].get("scaler_id", ""))
        lines.append("- removed %s (%s)" % (k, jid))
    for k in changed:
        for f in sorted(set(ka[k]) | set(kb[k])):
            if ka[k].get(f) != kb[k].get(f):
                lines.append("~ changed %s.%s: %s -> %s" % (k, f, json.dumps(ka[k].get(f)), json.dumps(kb[k].get(f))))
    if kind == "chip":
        sa = {s["offset"]: s["raw"] for s in da.get("swren_scripts", [])}
        sb = {s["offset"]: s["raw"] for s in db.get("swren_scripts", [])}
        if [s["raw"] for s in da.get("swren_scripts", [])] != [s["raw"] for s in db.get("swren_scripts", [])]:
            lines.append("~ changed swren_scripts (%d -> %d scripts)" % (len(sa), len(sb)))
    lines.append("# %d added, %d removed, %d changed" % (len(added), len(removed), len(changed)))
    print("\n".join(lines))
    logging.info("diff %s %s: %d added, %d removed, %d changed", a, b, len(added), len(removed), len(changed))
    return 1 if (added or removed or changed or len(lines) > len(added) + len(removed) + len(changed) + 2) else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="*")
    ap.add_argument("--diff", action="store_true", help="paths = a.json b.json")
    ap.add_argument("--scalers", action="store_true", help="paths = RTDScaler_dir out.json")
    ap.add_argument("--swren", help="SWREN.dat (default: next to the input)")
    ap.add_argument("--tool-version", help="default: V<x.y> taken from the input path")
    a = ap.parse_args()
    setup_log()
    if len(a.paths) != 2:
        ap.error("need exactly two paths")
    if a.diff:
        return cmd_diff(*a.paths)
    if a.scalers:
        return cmd_scalers(a.paths[0], a.paths[1], a.tool_version)
    return cmd_parse(a.paths[0], a.paths[1], a.swren, a.tool_version)


if __name__ == "__main__":
    sys.exit(main())
