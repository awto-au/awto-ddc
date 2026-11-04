#!/usr/bin/env python3
"""Version/layout GATE for Realtek RTDCustomerTool data files (stdlib only, static).

Every parser calls gate()/gate_or_exit() before trusting a file. The registry
(re/formats.json) records, per file kind and format version, the known-good
signature. A file whose magic/version/layout does not match is refused (or warned
with --warn-only). Doc: docs/reversing/realtek-rtd/extraction.md

API
  gate(path, kind=None, warn_only=False, tool_version=None) -> GateResult
      raises GateUnsupported (known variant, no parser) or GateError (drift/unknown)
  gate_or_exit(path, kind=None, ...)   parser helper: logs, exit(3) on refusal
  compute_signature(path, kind=None) -> dict   (what the file IS, independent of registry)
  detect_kind(path), detect_tool_version(path)
CLI
  rtd_gate.py gate <file>... [--kind K] [--tool-version V] [--warn-only]
  rtd_gate.py sig  <file> [--kind K]          print computed signature
  rtd_gate.py diff <file> [--kind K]          computed signature vs registry expectation
  rtd_gate.py register <file> --tool-version V [--reference]   record a passing file as validated
Log: ./tmp/logs/rtd_gate.log under the repo root (CLI only).
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

MAGIC = 0x99552277
REG_NAME = os.path.join("re", "formats.json")
EXIT_REFUSED = 3
EXIT_UNSUPPORTED = 4


class GateError(Exception):
    """Unknown version or layout drift: do not parse."""

    def __init__(self, msg, result=None):
        super().__init__(msg)
        self.result = result


class GateUnsupported(GateError):
    """Registry knows this variant but no parser exists."""


class GateResult:
    def __init__(self, path, kind):
        self.path, self.kind = path, kind
        self.version = None
        self.status = None          # registry status of this version
        self.warnings, self.fatal, self.notes = [], [], []
        self.signature = None
        self.exact_reference = False

    @property
    def ok(self):
        return not self.fatal

    @property
    def state(self):
        if self.status == "known-unsupported":
            return "unsupported"
        if self.fatal:
            return "fail"
        return "warn" if self.warnings else "ok"

    def message(self):
        return "; ".join(self.fatal or self.warnings or ["ok"])


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


def registry_path():
    return os.path.join(repo_root(), REG_NAME)


def load_registry(path=None):
    with open(path or registry_path(), encoding="utf-8") as f:
        return json.load(f)


def save_registry(reg, path=None):
    with open(path or registry_path(), "w", encoding="utf-8", newline="\n") as f:
        json.dump(reg, f, indent=2, sort_keys=False)
        f.write("\n")


# ---------------------------------------------------------------- kind / tool version
PE_EXT = (".dll", ".exe", ".ocx")


def detect_kind(path, reg=None):
    reg = reg or load_registry()
    base = os.path.basename(path).lower()
    for kind, spec in reg["kinds"].items():
        if base in [m.lower() for m in spec.get("match", [])]:
            return kind
        if any(base.endswith(e) for e in spec.get("match_ext", [])):
            return kind
    raise GateError("no registry kind matches %r (known: %s); add it to %s"
                    % (base, ", ".join(reg["kinds"]), REG_NAME))


def detect_tool_version(path):
    """'V3.8_20221101' from any parent dir name like RTDCustomerTool_V3.8_20221101."""
    p = os.path.abspath(path)
    while p and p != os.path.dirname(p):
        m = re.search(r"V\d+\.\d+_\d{8}", os.path.basename(p))
        if m:
            return m.group(0)
        p = os.path.dirname(p)
    return None


# ---------------------------------------------------------------- signature
def _u32(d, o):
    return struct.unpack_from("<I", d, o)[0] if len(d) >= o + 4 else None


def _u16(d, o):
    return struct.unpack_from("<H", d, o)[0] if len(d) >= o + 2 else None


def _ascii_ok(b):
    return len(b) > 0 and all(32 <= c < 127 for c in b)


def _db_v1_derived(d):
    """Walk the register stream exactly like rtd_db_parse, but independently."""
    FL = TL = 36
    out = {"hdr_size": _u32(d, 8)}
    hs = out["hdr_size"]
    if not hs or hs < 0x20 or hs + 0x14 + 2 * FL > len(d):
        out["stream_error"] = "hdr_size %r unusable" % hs
        return out
    t0 = hs + 0x14
    f0 = t0 + TL
    g, o, kt = d[f0 + 10:f0 + 12], d[f0 + 18:f0 + 20], d[f0 + 28:f0 + 32]
    use, s = d[t0 + 20:t0 + 28], d[t0 + 30:t0 + 32]

    def is_field(p):
        return (p + FL <= len(d) and d[p + 10:p + 12] == g and d[p + 18:p + 20] == o
                and d[p + 28:p + 32] == kt)

    def is_tail(p):
        return p + TL <= len(d) and d[p + 20:p + 28] == use and d[p + 30:p + 32] == s

    regs = fields = nf_bad = rng_bad = 0
    pos, tail = t0, t0
    pos += TL
    last_kt = None
    while True:
        nf = _u16(d, tail + 28)
        n = 0
        while is_field(pos):
            lo, hi = d[pos + 8], d[pos + 9]
            if hi < lo or hi > 7:
                rng_bad += 1
            last_kt = _u32(d, pos + 32)
            pos += FL
            n += 1
        regs += 1
        fields += n
        if nf != n:
            nf_bad += 1
        if is_tail(pos):
            tail = pos
            pos += TL
            continue
        break
    out.update(preamble_len=0x14, tail_len=TL, field_len=FL, regs=regs, fields=fields,
               nf_mismatch=nf_bad, field_bitrange_bad=rng_bad, pool_base=pos,
               pool_base_le_size=int(pos <= len(d)),
               post_pool_le_size=int(last_kt is not None and pos + last_kt <= len(d)),
               tag_g=g.hex(), tag_o=o.hex(), tag_kt=kt.hex(), tag_use=use.hex(), tag_s=s.hex())
    return out


def _gpio_derived(d):
    out = {}
    tag = d[8:0x6C]
    for i in range(0, len(tag) - 1, 2):
        if tag[i] == 0 and tag[i + 1] == 0:
            tag = tag[:i]
            break
    out["chip_tag"] = tag.decode("utf-16le", "replace")
    out["pin_count"] = _u16(d, 0x7C)
    out["pin_rec_len"] = 376
    pc = out["pin_count"] or 0
    out["pins_end"] = 0x7E + pc * 376
    out["pins_end_le_size"] = int(out["pins_end"] <= len(d))
    first = d[0x7E:0x7E + 100]
    out["pin0_name_utf16_ok"] = int(first[:3] == b"P\0i" or first[:2] == b"P\0")
    return out


def _flashset_derived(d, name_off):
    out = {"count_u16": _u16(d, 6), "hdr_len": 6, "stride": 0x48}
    body = len(d) - 6
    out["records"] = body // 0x48
    out["size_remainder"] = body % 0x48
    out["records_minus_count"] = out["records"] - (out["count_u16"] or 0)
    bad = 0
    for i in range(out["records"]):
        p = name_off + i * 0x48  # name_off = file offset of record 0's name (0x16)
        nm = d[p:p + 16].split(b"\0")[0]
        if nm and not _ascii_ok(nm):
            bad += 1
    out["name_nonascii_records"] = bad
    return out


def _readall_derived(d):
    t = d.decode("latin1")
    kv = dict(re.findall(r"^(ScalerName|ScalerID|ScalerFileVersion|IcType|PageCount|PageSelect)="
                         r"(.*?)\r?$", t, re.M))
    out = {"has_ScalerInfor": int("[ScalerInfor]" in t), "has_PageInfor": int("[PageInfor]" in t)}
    out.update({k: v for k, v in kv.items()})
    out["page_sections"] = len(re.findall(r"^\[PG[0-9A-Fa-f]{2}\]", t, re.M))
    out["page_name_lines"] = len(re.findall(r"^PG[0-9A-Fa-f]{2}_Name=", t, re.M))
    return out


def _pe_derived(d):
    out = {"mz": int(d[:2] == b"MZ")}
    if not out["mz"] or len(d) < 0x40:
        return out
    pe = _u32(d, 0x3C)
    if pe is None or pe + 24 > len(d):
        out["pe_sig"] = 0
        return out
    out["pe_sig"] = int(d[pe:pe + 4] == b"PE\0\0")
    if not out["pe_sig"]:
        return out
    out["machine"] = "0x%04x" % _u16(d, pe + 4)
    out["nsections"] = _u16(d, pe + 6)
    opt = pe + 24
    magic = _u16(d, opt)
    out["opt_magic"] = "0x%03x" % magic
    ddoff = opt + (96 if magic == 0x10B else 112)
    if ddoff + 24 <= len(d):
        rva, size = struct.unpack_from("<II", d, ddoff + 16)
        out["rsrc_present"] = int(rva != 0 and size != 0)
    return out


def _version_txt_derived(d):
    t = d.decode("latin1")
    kv = dict(re.findall(r"^(SpecRevision|StatusFileRevision)=(\d+)", t, re.M))
    out = {"has_SVNInfo": int("[SVNInfo]" in t)}
    out.update(kv)
    return out


def compute_signature(path, kind=None, reg=None):
    """Facts about the file itself; no registry comparison."""
    reg = reg or load_registry()
    kind = kind or detect_kind(path, reg)
    spec = reg["kinds"][kind]
    with open(path, "rb") as f:
        d = f.read()
    sig = {"kind": kind, "size": len(d), "sha256": hashlib.sha256(d).hexdigest(),
           "container": spec["container"], "magic": None, "version": None, "derived": {}}
    c = spec["container"]
    der = sig["derived"]
    if c == "rtd-magic":
        m = _u32(d, 0)
        sig["magic"] = "0x%08X" % m if m is not None else None
        v = _u32(d, 4)
        sig["version"] = str(v) if v is not None else None
        der["hdr_u32_2"] = _u32(d, 8)
        der["hdr_u32_3"] = _u32(d, 12)
        if m == MAGIC:
            if kind == "DB.bin" and v == 1:
                der.update(_db_v1_derived(d))
            elif kind == "GPIO.bin" and v == 2 and len(d) >= 0x80:
                der.update(_gpio_derived(d))
            elif kind == "DB.bin":
                der["hdr_size"] = _u32(d, 8)
                der["offset_table_entries"] = ((der["hdr_size"] or 8) - 8) // 4
    elif c == "ident":
        n = spec["ident_len"]
        sig["version"] = d[:n].hex()
        if kind == "FlashSet.dat":
            der.update(_flashset_derived(d, spec["name_off"]))
        elif kind == "Flash.dat":
            der["count_u16"] = _u16(d, 6)
            nm = d[spec["name_off"]:spec["name_off"] + 16].split(b"\0")[0]
            der["name0_ascii"] = int(_ascii_ok(nm))
            der["name0"] = nm.decode("latin1")
    elif c == "pe":
        sig["version"] = "-"
        der.update(_pe_derived(d))
    elif c == "text":
        sig["version"] = "-"
        if kind == "ReadAll.txt":
            der.update(_readall_derived(d))
        else:
            der.update(_version_txt_derived(d))
    else:  # "none"
        sig["version"] = "-"
    return sig


# ---------------------------------------------------------------- compare
def _check(val, rule):
    """rule: scalar | list (allowed) | {'min','max'}."""
    if isinstance(rule, dict) and "regex" in rule:
        return val is not None and re.fullmatch(rule["regex"], str(val)) is not None
    if isinstance(rule, dict):
        if val is None:
            return False
        try:
            v = float(val)
        except (TypeError, ValueError):
            return False
        return v >= rule.get("min", float("-inf")) and v <= rule.get("max", float("inf"))
    if isinstance(rule, list):
        return val in rule or (val is not None and str(val) in [str(x) for x in rule])
    return val == rule or (val is not None and str(val) == str(rule))


def compare(sig, vspec, section="expect"):
    """-> list of (key, got, rule, ok) for every rule in vspec[section]."""
    rows = []
    allv = dict(sig["derived"])
    allv["size"] = sig["size"]
    for key, rule in vspec.get(section, {}).items():
        rows.append((key, allv.get(key), rule, _check(allv.get(key), rule)))
    return rows


def gate(path, kind=None, warn_only=False, tool_version=None, reg=None):
    """Check path against the registry. Raises GateUnsupported/GateError unless warn_only."""
    reg = reg or load_registry()
    kind = kind or detect_kind(path, reg)
    spec = reg["kinds"][kind]
    sig = compute_signature(path, kind, reg)
    res = GateResult(path, kind)
    res.signature = sig
    res.version = sig["version"]
    fatal, warn = res.fatal, res.warnings
    c = spec["container"]
    label = "%s %s" % (kind, os.path.basename(os.path.dirname(os.path.abspath(path))))
    if c == "rtd-magic" and sig["magic"] != "0x%08X" % MAGIC:
        fatal.append("%s: bad magic %s (expected 0x%08X); refusing to parse - not an RTD "
                     "container or the format changed" % (kind, sig["magic"], MAGIC))
    vers = spec["versions"]
    vspec = vers.get(sig["version"]) if not fatal else None
    if not fatal and vspec is None:
        known = ",".join(vers)
        fatal.append("%s version %s unknown; registry knows %s; refusing to parse - "
                     "re-validate layout (see docs/reversing/realtek-rtd/extraction.md)"
                     % (kind, sig["version"], known))
    if vspec is not None:
        res.status = vspec["status"]
        if vspec["status"] == "known-unsupported":
            fatal.append("%s version %s is a known variant with no parser (%s)"
                         % (kind, sig["version"], vspec.get("note", "")))
        else:
            if sig["size"] < vspec.get("min_size", 0):
                fatal.append("%s size %d below minimum %d" % (kind, sig["size"], vspec["min_size"]))
            for key, got, rule, ok in compare(sig, vspec):
                if not ok:
                    fatal.append("%s v%s layout drift: %s = %r, registry expects %r; refusing "
                                 "to parse - re-validate layout"
                                 % (kind, sig["version"], key, got, rule))
            for key, got, rule, ok in compare(sig, vspec, "expect_warn"):
                if not ok:
                    warn.append("%s v%s soft-check %s = %r, registry expects %r"
                                % (kind, sig["version"], key, got, rule))
            ref = vspec.get("reference") or {}
            if ref.get("sha256") == sig["sha256"]:
                res.exact_reference = True
                res.notes.append("byte-identical to registry reference")
            validated = vspec.get("validated_tool_versions", [])
            tv = tool_version or detect_tool_version(path)
            if tv and validated and tv not in validated and not fatal:
                warn.append("%s v%s passes layout checks but tool version %s was never "
                            "validated (validated: %s)" % (kind, sig["version"], tv,
                                                           ", ".join(validated)))
            if not tv:
                res.notes.append("tool version not detected")
    if fatal and not warn_only:
        cls = GateUnsupported if res.status == "known-unsupported" else GateError
        raise cls("; ".join(fatal) + " [%s]" % path, res)
    return res


def gate_or_exit(path, kind=None, warn_only=None, tool_version=None, log=print):
    """Parser entry helper. warn_only default: $RTD_GATE_WARN_ONLY=1. Exits 3/4 on refusal."""
    if warn_only is None:
        warn_only = os.environ.get("RTD_GATE_WARN_ONLY") == "1"
    try:
        res = gate(path, kind, warn_only=warn_only, tool_version=tool_version)
    except GateUnsupported as e:
        log("GATE UNSUPPORTED: %s" % e)
        sys.exit(EXIT_UNSUPPORTED)
    except GateError as e:
        log("GATE REFUSED: %s" % e)
        sys.exit(EXIT_REFUSED)
    for w in res.warnings:
        log("GATE WARN: %s" % w)
    for f in res.fatal:
        log("GATE WARN (--warn-only, would refuse): %s" % f)
    log("gate %s %s v%s: %s" % (res.kind, os.path.basename(path), res.version, res.state))
    return res


# ---------------------------------------------------------------- CLI
def _setup_log():
    d = os.path.join(repo_root(), "tmp", "logs")
    os.makedirs(d, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.FileHandler(os.path.join(d, "rtd_gate.log")),
                                  logging.StreamHandler(sys.stdout)])


def _cmd_register(a):
    reg = load_registry()
    kind = a.kind or detect_kind(a.file[0], reg)
    res = gate(a.file[0], kind, tool_version=a.tool_version, reg=reg)
    if res.status != "supported":
        raise GateError("cannot register an unsupported variant")
    vspec = reg["kinds"][kind]["versions"][res.version]
    v = vspec.setdefault("validated_tool_versions", [])
    if a.tool_version not in v:
        v.append(a.tool_version)
    tv = reg.setdefault("tool_versions_seen", [])
    if a.tool_version not in tv:
        tv.append(a.tool_version)
    if a.reference:
        vspec["reference"] = {"path": os.path.basename(os.path.dirname(os.path.abspath(a.file[0])))
                              + "/" + os.path.basename(a.file[0]),
                              "size": res.signature["size"], "sha256": res.signature["sha256"],
                              "tool_version": a.tool_version}
    save_registry(reg)
    logging.info("registered %s v%s validated against %s", kind, res.version, a.tool_version)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("cmd", choices=["gate", "sig", "diff", "register"])
    ap.add_argument("file", nargs="+")
    ap.add_argument("--kind")
    ap.add_argument("--tool-version")
    ap.add_argument("--warn-only", action="store_true")
    ap.add_argument("--reference", action="store_true", help="register: also store as reference")
    a = ap.parse_args()
    _setup_log()
    rc = 0
    if a.cmd == "register":
        _cmd_register(a)
        return 0
    for f in a.file:
        try:
            if a.cmd == "gate":
                try:
                    r = gate(f, a.kind, warn_only=a.warn_only, tool_version=a.tool_version)
                    logging.info("%-6s %s v%s %s", r.state.upper(), r.kind, r.version, f)
                    for m in r.warnings + r.fatal:
                        logging.info("    %s", m)
                    rc = rc or (EXIT_REFUSED if r.fatal else 0)
                except GateUnsupported as e:
                    logging.info("UNSUPPORTED %s", e)
                    rc = rc or EXIT_UNSUPPORTED
            elif a.cmd == "sig":
                logging.info("%s\n%s", f, json.dumps(compute_signature(f, a.kind), indent=2))
            else:
                reg = load_registry()
                sig = compute_signature(f, a.kind, reg)
                spec = reg["kinds"][sig["kind"]]
                logging.info("%s: %s version=%s size=%d sha256=%s", f, sig["kind"],
                             sig["version"], sig["size"], sig["sha256"][:16])
                v = spec["versions"].get(sig["version"])
                if v is None:
                    logging.info("  version %s NOT in registry (%s)", sig["version"],
                                 ",".join(spec["versions"]))
                    logging.info("  computed derived: %s", json.dumps(sig["derived"]))
                    for k, vs in spec["versions"].items():
                        logging.info("  closest known v%s expects: %s", k,
                                     json.dumps(vs.get("expect", {})))
                    rc = EXIT_REFUSED
                    continue
                for key, got, rule, ok in compare(sig, v) + compare(sig, v, "expect_warn"):
                    logging.info("  %-4s %-22s got=%r expect=%r", "ok" if ok else "DIFF",
                                 key, got, rule)
                    rc = rc or (0 if ok else EXIT_REFUSED)
                extra = {k: x for k, x in sig["derived"].items() if k not in v.get("expect", {})
                             and k not in v.get("expect_warn", {})}
                logging.info("  unconstrained derived: %s", json.dumps(extra))
        except GateError as e:
            logging.info("REFUSED %s", e)
            rc = rc or EXIT_REFUSED
    return rc


if __name__ == "__main__":
    sys.exit(main())
