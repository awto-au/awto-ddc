"""Shared code of the register knowledge base (re/regmap/README.md): paths, TSV io, regdb / SDK / our-header readers, observation store, validation.

Used by regmap_build.py, regmap_import.py, regmap_query.py. Log: ./tmp/logs/regmap.log
"""
import collections
import csv
import functools
import gzip
import os
import re
import subprocess
import sys
from pathlib import Path

from _log import shared
from _repo import ROOT

REGMAP = ROOT / "re/regmap"
REGS = REGMAP / "regs.tsv"
FIELDS = REGMAP / "fields.tsv"
TESTS = REGMAP / "tests.tsv"
I2C = REGMAP / "i2c.tsv"
OBS = REGMAP / "obs"
LOG = ROOT / "tmp/logs/regmap.log"
REGDB = ROOT / "re/regdb"
PRIMARY = "RTD2795T-CG"
OTHER_CHIPS = ["RTD2776B-CG", "RTD2785TM-CG", "RTD2775TM-CG", "RTD2797UPM-CG", "RTD2537T-CG", "RTD2525AR-CG"]
SDK_HDR = ROOT / "fw/sdk/Kernel/Scaler/RL6449_Series_Common/Header/RL6449_Series_Common_RegCommonInclude.h"
SDK_MCU = ROOT / "fw/sdk/Kernel/Scaler/RL6449_Series_Scaler/Header"
OUR_HDR = ROOT / "fw/sdk/Project/Header/AwtoRegs.h"
SDK_DIR = ROOT / "fw/sdk"

GEN_REG = ["key", "page", "addr", "regdb_name", "regdb_status", "regdb_reset", "regdb_fields", "access", "sdk_name", "sdk_status", "sdk_uses",
           "our_name", "other_chips", "obs_n", "obs_distinct", "obs_min", "obs_max", "obs_const", "obs_nonzero", "obs_vary_state",
           "obs_first", "obs_last", "obs_units", "obs_hist"]
HAND_REG = ["class", "role", "side_effects", "status", "test_id", "result", "evidence", "notes", "issue"]
REG_COLS = GEN_REG + HAND_REG
GEN_FLD = ["fkey", "key", "hi", "lo", "regdb_field", "regdb_access", "regdb_reset", "regdb_text"]
HAND_FLD = ["name", "role", "status", "test_id", "result", "evidence", "notes", "issue"]
FLD_COLS = GEN_FLD + HAND_FLD
I2C_COLS = ["key", "role", "status", "test_id", "result", "evidence", "source", "notes", "issue"]
I2C_KEY_RE = re.compile(r"^(I2C|SCDC|CMD):[0-9A-F]{2}$")
TEST_COLS = ["id", "question", "method", "doc", "state", "issue"]

CLASSES = {"config", "status", "counter", "sensor", "test", "port", "unused", "reserved"}
STATUSES = {"known", "candidate", "unknown", "ignore"}
TAGS = {"hw", "databook", "spec", "regdb-other", "source-code", "re", "spec-model", "emu", "sdk-hypothesis", "guess", "unknown"}
REGDB_STATUS = {"documented", "blank-reserved", "no-row"}
SDK_STATUS = {"none", "defined", "used"}
TEST_STATES = {"done", "pending", "proposed"}
KEY_RE = re.compile(r"^[0-9A-F]{4}(:[0-9A-F]{2,3})?$")
FKEY_RE = re.compile(r"^[0-9A-F]{4}(:[0-9A-F]{2,3})?\[[0-7]:[0-7]\]$")
ISSUE_RE = re.compile(r"^#\d+(,#\d+)*$")
TEST_DOCS = ["docs/osd/open-items.md", "docs/saver-fps-hw.md", "docs/osd-hw-tests.md"]
RESERVED = re.compile(r"^(reserved|dummy|rsvd|res|resv|reserve|unused)\w*$", re.IGNORECASE)

# keys that never enter the store: HDCP key / HDCP port registers (secret material)
EXCLUDE_KEYS = {"71C4", "72C4", "71C9", "71CA", "72C9", "72CA"}
READ_BEHIND = REGMAP / "read_behind.tsv"
READ_BEHIND_COLS = ["page", "live", "isp", "live_byte", "live_block", "isp_byte", "wrong_by_lane", "tool", "date"]


def log(msg):
    shared(LOG, stamp_echo=False).say(msg)


def git_sha():
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=False).stdout.strip()
    except OSError:
        return ""


# ---------- TSV ----------
def read_tsv(path):
    """-> (cols, [dict]) ; missing file -> ([], [])"""
    p = Path(path)
    if not p.is_file():
        return [], []
    lines = p.read_text().split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    if not lines:
        return [], []
    cols = lines[0].split("\t")
    rows = []
    for ln in lines[1:]:
        v = ln.split("\t")
        v += [""] * (len(cols) - len(v))
        rows.append(dict(zip(cols, v)))
    return cols, rows


def tsv_text(cols, rows):
    out = ["\t".join(cols)]
    for r in rows:
        for c in cols:
            if "\t" in r.get(c, "") or "\n" in r.get(c, ""):
                raise ValueError(f"tab/newline in column {c} of {r.get('key') or r.get('fkey') or r.get('id')}")
        out.append("\t".join(r.get(c, "") for c in cols))
    return "\n".join(out) + "\n"


def sort_key(k):
    """PPAA[:II] -> sortable tuple"""
    base, _, idx = k.partition(":")
    return (base, idx.zfill(3))


# ---------- regdb ----------
def chip_short(chip):
    return chip.replace("RTD", "").replace("-CG", "")


def load_regdb(chip):
    """-> (regs, ports): regs[addr] = {name, reset, fields[(hi,lo,name,access,reset,text)]}; ports[(addr,idx)] = name"""
    regs, ports = {}, {}
    with gzip.open(REGDB / f"{chip}.tsv.gz", "rt") as f:
        rd = csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        for r in rd:
            try:
                a = int(r["address"], 0)
            except ValueError:
                continue
            if r["port_idx"]:
                if r["kind"] == "REG":
                    ports[(a, int(r["port_idx"], 0))] = r["register"]
                continue
            e = regs.setdefault(a, {"name": "", "reset": "", "fields": []})
            if r["kind"] == "REG":
                if not e["name"]:
                    e["name"], e["reset"] = r["register"], r["reset"]
            else:
                e["fields"].append((int(r["bit_high"]), int(r["bit_low"]), r["field"].strip(), r["access"], r["reset"], r["description"]))
                if not e["name"]:
                    e["name"] = r["register"]
    return regs, ports


def named_fields(e):
    return [f for f in e["fields"] if f[2] and not RESERVED.match(f[2])]


def regdb_status(e):
    if e is None:
        return "no-row"
    return "documented" if named_fields(e) else "blank-reserved"


def field_summary(e):
    nf = sorted(named_fields(e), key=lambda f: (-f[0], f[1]))
    return ";".join(f"{f[2]}[{f[0]}:{f[1]}]{f[3]}" if f[0] != f[1] else f"{f[2]}[{f[0]}]{f[3]}" for f in nf)


def access_summary(e):
    return "/".join(sorted({f[3] for f in named_fields(e) if f[3]}))


def text_line(s, n=110):
    s = s.replace("\\n", " / ").replace("\t", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "~"


# ---------- SDK / our header ----------
def load_sdk():
    """-> (names{addr:[sym]}, uses{sym:count}); P<page>_<AA>_NAME and MCU_<AAAA>_NAME (__at) symbols"""
    names = collections.defaultdict(list)
    pat = re.compile(r"#define\s+(P[0-9A-F]+_[0-9A-F]{2}_\w+)\s+0x([0-9A-F]{4})\b")
    for ln in SDK_HDR.read_text(errors="replace").splitlines():
        m = pat.match(ln)
        if m:
            names[int(m.group(2), 16)].append(m.group(1))
    for h in sorted(SDK_MCU.glob("RL6449_Series_Mcu*.h")):
        for ln in h.read_text(errors="replace").splitlines():
            m = re.search(r"__at\(0x([0-9A-Fa-f]+)\).*?\b(MCU_\w+)\s*;", ln)
            if m and m.group(2) not in names[int(m.group(1), 16)]:
                names[int(m.group(1), 16)].append(m.group(2))
    known = {s for v in names.values() for s in v}
    uses = collections.Counter()
    sp = re.compile(r"\b(P[0-9A-F]+_[0-9A-F]{2}_\w+|MCU_\w+)\b")
    for root, _, fs in os.walk(SDK_DIR):
        for fn in fs:
            if not fn.endswith(".c") and not fn.endswith(".h"):
                continue
            if "RegCommonInclude" in fn or fn.startswith("RL6449_Series_Mcu") or fn == "AwtoRegs.h":
                continue
            for m in sp.finditer(Path(root, fn).read_text(errors="replace")):
                if m.group(1) in known:
                    uses[m.group(1)] += 1
    return dict(names), uses


def load_ours():
    """-> {addr: [AWTO_R_ name]}"""
    out = collections.defaultdict(list)
    for ln in OUR_HDR.read_text().splitlines():
        m = re.match(r"#define\s+(AWTO_R_\w+)\s+0x([0-9A-F]{4})\b", ln)
        if m:
            out[int(m.group(2), 16)].append(m.group(1))
    return dict(out)


# ---------- observation store ----------
class Obs:
    """one source file: meta dict + {key: value}; key PPAA or PPAA:II (port index)"""

    def __init__(self, path, meta, vals):
        self.path, self.meta, self.vals = path, meta, vals

    @property
    def sid(self):
        return Path(self.path).name.split(".")[0]


ISP_LATCH_OTHER = {"8F", "CF"}       # isp verdict 'other', but 13 of 28 wrong reads are the latch: treated as affected


@functools.cache
def read_behind_pages(col):
    """Pages whose `live` (debug slave) / `isp` verdict contains the read-behind latch (yes, yes+other; isp also 8F / CF)."""
    if not READ_BEHIND.exists():
        return set()
    _, rows = read_tsv(READ_BEHIND)
    return {int(r["page"], 16) for r in rows
            if r[col] in ("yes", "yes+other") or (col == "isp" and r["page"] in ISP_LATCH_OTHER and r[col] == "other")}


def behind_drop(meta, key):
    """True if the value comes from an old (unfixed) read of a read-behind page: the whole page is dropped (README Read-behind).
    Lanes 1-3 are right in the probe, but old scans also read page windows (offsets C0..FF of 88 / 8A / 8B / 8E) that fixed scans
    do not reproduce; the old values cannot be sorted into right and wrong. Port keys never; live / regdump use the live set, isp the isp set."""
    if meta.get("read_fix") or ":" in key:
        return False
    page = int(key[:2], 16)
    if f"{page:02X}" in stripped_pages(meta):
        return False
    return page in read_behind_pages("isp" if meta.get("method") == "isp" else "live")


def stripped_pages(meta):
    """Pages a file's #read_behind_stripped= header says were handled (`pages=88,8A,..; N values ...`)."""
    h = meta.get("read_behind_stripped", "")
    return set(h.split("pages=")[1].split(";")[0].split(",")) if "pages=" in h else set()


def strip_behind(meta, vals):
    """-> (vals without the known-wrong read-behind values, count); stamps meta['read_behind_stripped'] when anything went."""
    drop = [k for k in vals if behind_drop(meta, k)]
    if not drop:
        return vals, 0
    pages = sorted(stripped_pages(meta) | {k[:2] for k in drop})
    meta["read_behind_stripped"] = f"pages={','.join(pages)}; {len(drop)} values"
    return {k: v for k, v in vals.items() if k not in set(drop)}, len(drop)


def obs_text(meta, vals):
    """vals {key: int}; pages are written as runs: `p<TAB>PPAA<TAB>hex tokens` (.. = not read), ports `q<TAB>PPAA<TAB>hex by index`."""
    lines = [f"#{k}={v}" for k, v in meta.items() if v != ""]
    pages = collections.defaultdict(dict)
    ports = collections.defaultdict(dict)
    for k, v in vals.items():
        if ":" in k:
            b, i = k.split(":")
            ports[b][int(i, 16)] = v
        else:
            pages[k[:2]][int(k[2:], 16)] = v   # noqa: FURB166 (k[:2] is a page byte, not a 0x prefix; int(k, 0) breaks it)
    for p in sorted(pages):
        d = pages[p]
        lo, hi = min(d), max(d)
        lines.append(f"p\t{p}{lo:02X}\t" + " ".join(f"{d[i]:02X}" if i in d else ".." for i in range(lo, hi + 1)))
    for b in sorted(ports):
        d = ports[b]
        lines.append(f"q\t{b}\t" + " ".join(f"{d[i]:02X}" if i in d else ".." for i in range(max(d) + 1)))
    return "\n".join(lines) + "\n"


def parse_obs(path, text):
    meta, vals = {}, {}
    for ln in text.splitlines():
        if ln.startswith("#"):
            k, _, v = ln[1:].partition("=")
            meta[k] = v
        elif ln.startswith("p\t"):
            _, k, toks = ln.split("\t")
            base = int(k, 16)
            for i, t in enumerate(toks.split(" ")):
                if t != "..":
                    vals[f"{base + i:04X}"] = int(t, 16)
        elif ln.startswith("q\t"):
            _, b, toks = ln.split("\t")
            for i, t in enumerate(toks.split(" ")):
                if t != "..":
                    vals[f"{b}:{i:02X}"] = int(t, 16)
    return Obs(path, meta, vals)


def load_obs(directory=None):
    out = []
    for p in sorted(Path(directory or OBS).glob("*.tsv.gz")):
        with gzip.open(p, "rt") as f:
            out.append(parse_obs(p, f.read()))
    return out


def write_obs(path, meta, vals):
    """deterministic gzip (mtime 0, no name)"""
    data = obs_text(meta, vals).encode()
    with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as g:
        g.write(data)


def summarise(obs_list):
    """-> {key: dict of obs_* columns}"""
    per = collections.defaultdict(list)       # key -> [(value, unit, state, time)]
    for o in obs_list:
        unit = o.meta.get("unit", "")
        st = (unit, o.meta.get("label", ""), o.meta.get("state", ""), o.meta.get("method", ""))
        t = o.meta.get("time", "")
        for k, v in o.vals.items():
            per[k].append((v, unit, st, t))
    out = {}
    for k, l in per.items():
        vs = [x[0] for x in l]
        cnt = collections.Counter(vs)
        hist = collections.defaultdict(collections.Counter)
        for v, _, st, _ in l:
            hist[st[3]][v] += 1
        grp = collections.defaultdict(set)
        for v, _, st, _ in l:
            grp[st].add(v)
        times = sorted(x[3] for x in l if x[3])
        out[k] = {
            "obs_n": str(len(vs)), "obs_distinct": str(len(cnt)), "obs_min": f"{min(vs):02X}", "obs_max": f"{max(vs):02X}",
            "obs_const": f"{vs[0]:02X}" if len(cnt) == 1 else "", "obs_nonzero": "1" if any(vs) else "0",
            "obs_vary_state": "1" if any(len(s) > 1 for s in grp.values()) else "0",
            "obs_first": times[0][:10] if times else "", "obs_last": times[-1][:10] if times else "",
            "obs_units": str(len({x[1] for x in l})),
            "obs_hist": " ".join(f"{m[0]}:" + ",".join(f"{v:02X}x{n}" for v, n in sorted(c.items(), key=lambda t: (-t[1], t[0]))[:5])
                                 for m, c in sorted(hist.items())),
        }
    return out


# ---------- tests ----------
def known_test_ids():
    ids = set()
    for d in TEST_DOCS:
        p = ROOT / d
        if p.is_file():
            ids |= set(re.findall(r"^\| (OT-\d+|T-[A-M]|T\d{1,2}) ", p.read_text(), re.MULTILINE))
    ids |= {r["id"] for r in read_tsv(TESTS)[1]}
    return ids


# ---------- validation of the hand columns ----------
def check_hand(row, label, tests):
    err = []
    c = row.get("class", "")
    if c and c not in CLASSES:
        err.append(f"{label}: class {c!r} not in {sorted(CLASSES)}")
    s = row.get("status", "")
    if s and s not in STATUSES:
        err.append(f"{label}: status {s!r} not in {sorted(STATUSES)}")
    if row.get("issue") and not ISSUE_RE.match(row["issue"]):
        err.append(f"{label}: issue {row['issue']!r} is not #N[,#M]")
    for t in [x for x in re.split(r"[,; ]+", row.get("test_id", "")) if x]:
        if t not in tests:
            err.append(f"{label}: test_id {t} unknown (docs/osd/open-items.md ids or re/regmap/tests.tsv)")
    ev = row.get("evidence", "")
    hand = set(HAND_REG) | set(HAND_FLD) | {"obs"}
    for item in [x for x in ev.split(";") if x]:
        claim, eq, tags = item.partition("=")
        if not eq or claim not in hand:
            err.append(f"{label}: evidence item {item!r} is not claim=tag (claim one of the hand columns)")
            continue
        for t in tags.split("+"):
            if t not in TAGS:
                err.append(f"{label}: evidence tag {t!r} not in {sorted(TAGS)}")
    if row.get("status") in ("known", "candidate") and row.get("role") and not ev:
        err.append(f"{label}: status {row['status']} with a role needs evidence")
    return err


if __name__ == "__main__":
    sys.exit("library: use regmap_build.py / regmap_import.py / regmap_query.py")
