#!/usr/bin/env python3
"""Parse a Realtek RTDCustomerTool scaler GPIO database (RTDScaler/<chip>/GPIO.bin).

Usage: python -I rtd_gpio_parse.py <GPIO.bin> <out.tsv> [--regdb <chip DB.bin TSV>]

Static analysis of vendor data only. Format notes: docs/reversing/realtek-rtd/db-bin-format.md
Log: ./tmp/logs/rtd_gpio_parse.log under the repo root (stdout+stderr mirrored).

File = magic 0x99552277, version 2, UTF-16 chip tag, then a fixed sequence of sections
(raw dumps of C structs; 0xCD = MSVC debug fill). Register refs are (u16 addr, u8 AND-mask,
u8 shift); the bit range is the zero bits of the mask. Section order:
  pins(u16 n, 376 B) | spi_drive(u16 n) | spi_slew(u16 n) | 4 x pair list(u8 n)
  | adc singles(u8 n) | ports(u8 n) | timers(u8 n) | pwm(u16 n)
  | schmitt regs(u8 n, n x u16)
"""
import argparse
import logging
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops script dir
import rtd_gate  # noqa: E402

MAGIC = 0x99552277
PIN_REC = 376
PAD = 0xCD


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
        handlers=[logging.FileHandler(os.path.join(logdir, "rtd_gpio_parse.log")),
                  logging.StreamHandler(sys.stdout)])


class Rd:
    def __init__(self, d):
        self.d, self.p = d, 0

    def u8(self):
        v = self.d[self.p]
        self.p += 1
        return v

    def u16(self):
        v, = struct.unpack_from("<H", self.d, self.p)
        self.p += 2
        return v

    def wstr(self, n=100):
        """Fixed n-byte UTF-16 buffer; text up to the first NUL, rest is garbage."""
        b = self.d[self.p:self.p + n]
        self.p += n
        for i in range(0, len(b) - 1, 2):
            if b[i] == 0 and b[i + 1] == 0:
                b = b[:i]
                break
        return b.decode("utf-16le", "replace")

    def regref(self):
        """(addr, mask, shift) -> (addr, hi, lo) or None when addr==0."""
        a = self.u16()
        m = self.u8()
        s = self.u8()
        return bits(a, m, s)


def bits(addr, mask, shift):
    if addr == 0:
        return None
    fld = (~mask) & 0xFF
    if fld == 0:
        return (addr, 7, 0, False)
    lo = (fld & -fld).bit_length() - 1
    hi = fld.bit_length() - 1
    # whole-byte refs are mask 0/shift 0; otherwise shift must equal the low bit
    ok = (mask == 0 and shift == 0) or lo == shift
    return (addr, hi, lo, not ok)


def fmt_ref(r):
    return ("0x%04X" % r[0], "%d:%d" % (r[1], r[2])) if r else ("", "")


class Db:
    """Optional field lookup from the DB.bin TSV (rtd_db_parse.py output)."""

    def __init__(self, path):
        self.f = {}
        if not path or not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as fh:
            next(fh)
            for ln in fh:
                c = ln.rstrip("\n").split("\t")
                if len(c) < 17 or c[4] != "FIELD":
                    continue
                self.f.setdefault(int(c[1], 16), []).append(
                    (int(c[6]), int(c[7]), c[8], c[5], c[16]))
        logging.info("regdb %s: %d registers", path, len(self.f))

    def regfields(self, addr):
        return [x[2] for x in self.f.get(addr, []) if x[2] != "Reserved"]

    def look(self, r):
        """-> (field name, desc, exact) or ('', '', False)."""
        if not r or not self.f:
            return "", "", False
        for hi, lo, nm, rg, ds in self.f.get(r[0], []):
            if (hi, lo) == (r[1], r[2]):
                return nm, ds, True
        for hi, lo, nm, rg, ds in self.f.get(r[0], []):
            if lo <= r[2] and r[1] <= hi:
                return nm, ds, False
        return "", "", False


def parse(d, db):
    if len(d) < 0x80 or struct.unpack_from("<I", d)[0] != MAGIC:
        raise ValueError("bad magic (expected 0x99552277)")
    ver, = struct.unpack_from("<I", d, 4)
    if ver != 2:
        raise ValueError("unsupported GPIO.bin version %d (only 2 decoded)" % ver)
    r = Rd(d)
    r.p = 8
    chip = r.wstr(100)
    r.p = 0x6C
    hdr_a, hdr_b = struct.unpack_from("<II", d, 0x6C)
    r.p = 0x7C
    rows, warn = [], {"tail": 0, "bits": 0, "db_miss": 0}

    # ---- S1: pin table -----------------------------------------------------
    n = r.u16()
    pins = []
    for i in range(n):
        b = r.p
        name, port, volt = r.wstr(), r.wstr(), r.wstr()
        t = d[b + 300:b + PIN_REC]
        r.p = b + PIN_REC
        if t[3] != PAD or t[75] != PAD or t[72] not in (0, 0xFF):
            warn["tail"] += 1
        p = dict(idx=i, pin=name, port=port, volt=volt, T=t)
        u16 = lambda o: t[o] | t[o + 1] << 8
        p["prio"] = bits(u16(4), t[6], t[7])
        p["prio_sel"] = [j for j in range(9) if t[8 + j]]
        p["caps"] = t[20]
        p["mode"] = bits(u16(24), t[26], t[27])
        p["pp"], p["od"] = t[30], t[31]
        p["pwm"] = [(k, t[32 + 2 * k], t[33 + 2 * k]) for k in range(6) if t[32 + 2 * k] or t[33 + 2 * k]]
        p["slots"] = [(k, t[44 + k]) for k in range(10) if t[44 + k]]
        p["data"] = bits(u16(56), t[58], t[59])
        p["drive"] = bits(u16(60), t[62], t[63])
        p["pull"] = bits(u16(68), t[70], t[71])
        p["pu"], p["pd"] = t[73], t[74]
        for k in ("prio", "mode", "data", "drive", "pull"):
            if p[k] and p[k][3]:
                warn["bits"] += 1
        pins.append(p)
    by_port = {p["port"]: p for p in pins}

    def pin_of(port):
        q = by_port.get(port)
        return q["pin"] if q else ""

    # ---- S2/S3: SPI drive / slew ------------------------------------------
    spi = []
    n = r.u16()
    for i in range(n):
        pn, sg = r.wstr(), r.wstr()
        ref = r.regref()
        extra = d[r.p:r.p + 10].hex(" ")
        r.p += 10
        spi.append(("SPI_DRIVE", i, pn, sg, ref, extra))
    n = r.u16()
    for i in range(n):
        pn, sg = r.wstr(), r.wstr()
        ref = r.regref()
        extra = d[r.p:r.p + 2].hex(" ")
        r.p += 2
        spi.append(("SPI_SLEW", i, pn, sg, ref, extra))

    # ---- S4..S7: pin pair lists, S8: ADC singles ---------------------------
    pairs = []
    for sec in range(4):
        n = r.u8()
        for i in range(n):
            rid, pad = r.u8(), r.u8()
            if pad != PAD:
                warn["tail"] += 1
            pairs.append((sec, rid, r.wstr(), r.wstr()))
    n = r.u8()
    adc = []
    for i in range(n):
        rid, pad = r.u8(), r.u8()
        if pad != PAD:
            warn["tail"] += 1
        adc.append((rid, r.wstr(), r.regref()))

    # ---- S9 ports, S10 timers, S11 pwm --------------------------------------
    ports = []
    n = r.u8()
    for i in range(n):
        nm = r.wstr()
        ref = r.regref()
        ports.append((nm, ref, d[r.p:r.p + 2].hex(" ")))
        r.p += 2
    timers = []
    n = r.u8()
    for i in range(n):
        timers.append((r.wstr(), r.wstr()))
    pwm = []
    n = r.u16()
    for i in range(n):
        rid, pad = r.u8(), r.u8()
        if pad != PAD or rid != i + 1:
            warn["tail"] += 1
        items = []
        for k in range(10):
            ref = r.regref()
            if k < 2:
                r.p += 2  # 00 01 [?]
            items.append(ref)
        r.p += 2  # 01 00 [?]
        pwm.append((rid, items))
    schmitt = []
    if r.p < len(d):
        n = r.u8()
        for i in range(n):
            if r.p + 2 <= len(d):
                schmitt.append(r.u16())
    left = len(d) - r.p
    tail = d[r.p:].hex(' ')
    logging.info("%s tag=%s hdr=(%d,%d) pins=%d spi=%d pairs=%d adc=%d ports=%d timers=%d pwm=%d "
                 "schmitt=%d trailing_bytes=%d (%s) warn=%s", chip, chip, hdr_a, hdr_b, len(pins), len(spi),
                 len(pairs), len(adc), len(ports), len(timers), len(pwm), len(schmitt), left, tail, warn)
    return dict(chip=chip, pins=pins, spi=spi, pairs=pairs, adc=adc, ports=ports,
                timers=timers, pwm=pwm, schmitt=schmitt, by_port=by_port, pin_of=pin_of, warn=warn,
                hdr=(hdr_a, hdr_b), left=left)


COLS = ["table", "idx", "pin", "port", "voltage", "peer", "peer_pin", "signal", "direction",
        "mode_reg", "mode_bits", "mode_field", "pp_code", "od_code", "alt_codes",
        "data_reg", "data_bits", "data_field",
        "drive_reg", "drive_bits", "drive_field",
        "pull_reg", "pull_bits", "pull_field", "pu_code", "pd_code",
        "prio_reg", "prio_bits", "prio_field", "prio_fn", "reg", "bits", "reg_field",
        "raw", "description"]


def esc(t):
    return (t or "").replace("\\", "\\\\").replace("\r\n", "\\n").replace("\r", "\\n") \
        .replace("\n", "\\n").replace("\t", "\\t")


def prio_fn(desc, pin):
    """Function name for the '<Priority>PinN' segment of a priority-override field."""
    for seg in (desc or "").split("<Priority>"):
        if re.match(re.escape(pin) + r"(\\n|\n|$)", seg):
            m = re.search(r"1:\s*([^\\\n]+)", seg)
            return m.group(1).strip() if m else ""
    return ""


def mentions(desc, pin):
    return bool(re.search(r"(?<![A-Za-z0-9_])" + re.escape(pin) + r"(?![A-Za-z0-9])", desc or ""))


def build_rows(g, db):
    out, st = [], dict(n=0, exact=0, said=0, said_n=0)
    for p in g["pins"]:
        row = dict(table="PIN", idx=p["idx"], pin=p["pin"], port=p["port"], voltage=p["volt"])
        c = p["caps"]
        row["direction"] = "/".join(x for x, m in (("I", 1), ("O_PP", 2), ("O_OD", 4)) if c & m)
        row["pp_code"] = p["pp"] if c & 2 else ""
        row["od_code"] = p["od"] if c & 4 else ""
        alt = ["pwm%d=%d/%d" % x for x in p["pwm"]]
        alt += ["s%d=%d" % x for x in p["slots"]]
        row["alt_codes"] = ",".join(alt)
        desc = []
        for key in ("mode", "data", "drive", "pull", "prio"):
            ref = p[key]
            reg, bt = fmt_ref(ref)
            row[key + "_reg"], row[key + "_bits"] = reg, bt
            nm, ds, ex = db.look(ref)
            row[key + "_field"] = nm + ("" if ex or not nm else "~")
            if ref and db.f:
                st["n"] += 1
                st["exact"] += ex
                if key in ("mode", "drive", "pull", "prio"):
                    st["said_n"] += 1
                    st["said"] += mentions(ds, p["pin"])
            if key == "mode" and ds:
                desc.append(ds)
            if key == "prio":
                row["prio_fn"] = prio_fn(ds, p["pin"])
        row["pu_code"] = "" if p["pu"] == 0xFF else p["pu"]
        row["pd_code"] = "" if p["pd"] == 0xFF else p["pd"]
        row["raw"] = "caps=%02x bm=%02x%02x sel=%s tail=%s" % (
            c, p["T"][21], p["T"][22], ",".join(map(str, p["prio_sel"])), p["T"][:4].hex())
        row["description"] = esc(" | ".join(desc))
        out.append(row)
    for tb, i, pn, sg, ref, ex in g["spi"]:
        reg, bt = fmt_ref(ref)
        nm, ds, e = db.look(ref)
        out.append(dict(table=tb, idx=i, pin=pn, port=g["by_port"].get(pn, {}).get("port", ""),
                        signal=sg, reg=reg, bits=bt, reg_field=nm, raw=ex, description=esc(ds)))
    for sec, rid, a, b in g["pairs"]:
        pa = g["by_port"].get(a)
        fn = prio_fn(db.look(pa["prio"])[1], pa["pin"]) if pa and pa["prio"] else ""
        out.append(dict(table="PAIR%d" % (sec + 1), idx=rid, pin=g["pin_of"](a), port=a, peer=b,
                        peer_pin=g["pin_of"](b), signal=fn))
    for rid, a, ref in g["adc"]:
        reg, bt = fmt_ref(ref)
        nm, ds, e = db.look(ref)
        out.append(dict(table="ADC", idx=rid, pin=g["pin_of"](a), port=a, reg=reg, bits=bt,
                        reg_field=nm, description=esc(ds)))
    for i, (nm_, ref, ex) in enumerate(g["ports"]):
        reg, bt = fmt_ref(ref)
        nm, ds, e = db.look(ref)
        out.append(dict(table="PORT", idx=i, port=nm_, reg=reg, bits=bt, reg_field=nm, raw=ex,
                        description=esc(ds)))
    for i, (tn, pn) in enumerate(g["timers"]):
        out.append(dict(table="TIMER", idx=i, pin=g["pin_of"](pn), port=pn, signal=tn))
    for rid, items in g["pwm"]:
        for k, ref in enumerate(items):
            reg, bt = fmt_ref(ref)
            nm, ds, e = db.look(ref)
            out.append(dict(table="PWM", idx=rid - 1, signal=k, reg=reg, bits=bt,
                            reg_field=nm, description=esc(ds)))
    for i, a in enumerate(g["schmitt"]):
        out.append(dict(table="SCHMITT", idx=i, reg="0x%04X" % a, bits="7:0",
                        signal=",".join(db.regfields(a))))
    return out, st


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("gpio")
    ap.add_argument("out")
    ap.add_argument("--regdb", help="DB.bin TSV for the same chip (names/descriptions, "
                    "default: <out dir>/<chip>.tsv, chip = GPIO.bin parent dir name)")
    ap.add_argument("--gate-warn-only", action="store_true", help="downgrade gate refusals to warnings")
    a = ap.parse_args()
    setup_log()
    rtd_gate.gate_or_exit(a.gpio, "GPIO.bin", warn_only=a.gate_warn_only or None, log=logging.info)
    logging.info("parse %s -> %s", a.gpio, a.out)
    chip = os.path.basename(os.path.dirname(os.path.abspath(a.gpio)))
    rdb = a.regdb or os.path.join(os.path.dirname(os.path.abspath(a.out)), chip + ".tsv")
    db = Db(rdb)
    g = parse(open(a.gpio, "rb").read(), db)
    rows, st = build_rows(g, db)
    with open(a.out, "w", encoding="utf-8", newline="") as fo:
        fo.write("\t".join(COLS) + "\n")
        for r in rows:
            fo.write("\t".join(str(r.get(c, "")) for c in COLS) + "\n")
    logging.info("wrote %d rows (%d pins); regdb field match: %s", len(rows), len(g["pins"]), st)
    print("%s pins=%d rows=%d db_exact=%d/%d db_names_pin=%d/%d" % (
        chip, len(g["pins"]), len(rows), st["exact"], st["n"], st["said"], st["said_n"]))


if __name__ == "__main__":
    main()
