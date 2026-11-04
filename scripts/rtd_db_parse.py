#!/usr/bin/env python3
"""Parse a Realtek RTDCustomerTool scaler register database (RTDScaler/<chip>/DB.bin).

Usage: python -I rtd_db_parse.py <DB.bin> <out.tsv> [--readall ReadAll.txt]

Static analysis of vendor data only. Format notes: docs/reversing/realtek-rtd/db-bin-format.md
Log: ./tmp/logs/rtd_db_parse.log under the repo root (stdout+stderr mirrored).

File layout (all little-endian), see the doc for evidence tags:
  header   : u32 magic 0x99552277, u32 1, u32 hdr_size(0x400), offset table
  stream   : one linear chain of registers; each register = N field records (36 B each)
             followed by a 36 B "tail" describing the NEXT register
  pool     : NUL-terminated strings; every pointer is (pool_base + value)
  pool_base: file offset right after the last field record of the chain
"""
import argparse
import logging
import os
import re
import struct
import subprocess
import sys

MAGIC = 0x99552277
FIELD_LEN = 36
TAIL_LEN = 36
ACCESS = {1: "R", 2: "W", 3: "RW", 4: "RW4"}  # 4 = RW, double-buffered? [guess]


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
        handlers=[logging.FileHandler(os.path.join(logdir, "rtd_db_parse.log")),
                  logging.StreamHandler(sys.stdout)])


class Db:
    def __init__(self, data):
        self.d = data
        if len(data) < 0x20 or struct.unpack_from("<I", data)[0] != MAGIC:
            raise ValueError("bad magic (expected 0x99552277)")
        self.version, self.hdr_size = struct.unpack_from("<II", data, 4)
        if self.version != 1:
            raise ValueError("unsupported DB version %d (only v1 decoded; RTD2172/RTD2186 are v3)"
                             % self.version)
        n = (self.hdr_size - 8) // 4
        self.table = struct.unpack_from("<%dI" % n, data, 8)
        self.pool = None

    # -- record recognisers -------------------------------------------------
    # Tag/filler words are constants that differ per chip (2795: g,o,k,t,"\\Use",s;
    # 2785: B,n,n,f,"\\row",i); they are learned from the first tail+field.
    def is_field(self, p):
        d, t = self.d, self.tags
        return (p + FIELD_LEN <= len(d) and d[p + 10:p + 12] == t["g"]
                and d[p + 18:p + 20] == t["o"] and d[p + 28:p + 32] == t["kt"])

    def is_tail(self, p):
        d, t = self.d, self.tags
        return (p + TAIL_LEN <= len(d) and d[p + 20:p + 28] == t["use"]
                and d[p + 30:p + 32] == t["s"])

    def learn_tags(self, t0):
        d = self.d
        f = t0 + TAIL_LEN
        self.tags = dict(g=d[f + 10:f + 12], o=d[f + 18:f + 20], kt=d[f + 28:f + 32],
                         use=d[t0 + 20:t0 + 28], s=d[t0 + 30:t0 + 32], z=d[t0 + 12:t0 + 16])
        logging.info("learned tags: %s", {k: v.hex() for k, v in self.tags.items()})

    def s(self, ptr):
        d, p = self.d, self.pool + ptr
        if not 0 <= ptr < len(d) - self.pool:
            return None
        e = d.index(b"\0", p)
        raw = d[p:e]
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("cp1252", "replace")

    # -- stream parse -------------------------------------------------------
    def parse(self):
        d = self.d
        # first tail sits 0x14 after hdr_size (5 dwords of preamble); else scan
        t0 = self.hdr_size + 0x14
        if d[t0 + 36:t0 + 44] != b"\xff" * 8 and d[t0 + 44:t0 + 46] != b"\xff\xff":
            logging.warning("unexpected first field layout at 0x%x", t0 + 36)
        self.learn_tags(t0)
        self.preamble = struct.unpack_from("<%dI" % ((t0 - self.hdr_size) // 4), d, self.hdr_size)
        regs = []
        pos = t0
        tail = pos
        pos += TAIL_LEN
        while True:
            # tail describes the register whose fields start at pos
            nameptr, addr, addr2, pidx, pidx2, lvl, nf, fptr = self._tail(tail)
            fields = []
            while self.is_field(pos):
                fields.append(pos)
                pos += FIELD_LEN
            reg = dict(nameptr=nameptr, addr=addr, addr2=addr2, pidx=pidx, pidx2=pidx2,
                       lvl=lvl, nf=nf, fptr=fptr, fields=fields, tail=tail)
            regs.append(reg)
            if not fields:
                logging.warning("register at tail 0x%x has no fields", tail)
            if self.is_tail(pos):
                tail = pos
                pos += TAIL_LEN
                continue
            break
        self.pool = pos
        logging.info("stream end / pool base = 0x%x, %d registers", pos, len(regs))
        return regs

    def _tail(self, t):
        d = self.d
        """Tail = describes the register whose field records follow it."""
        nameptr, addr, addr2, pidx, pidx2, _z, lvl = struct.unpack_from("<IHHHHII", d, t)
        nf, = struct.unpack_from("<H", d, t + 28)
        fptr, = struct.unpack_from("<I", d, t + 32)
        return nameptr, addr, addr2, pidx, pidx2, lvl, nf, fptr


def read_readall(path):
    """-> {page:int -> [group names]}"""
    out = {}
    if not path or not os.path.exists(path):
        return out
    for line in open(path, encoding="latin1"):
        m = re.match(r"PG([0-9A-Fa-f]{2})_Name=(.*)", line.rstrip("\r\n"))
        if m:
            out[int(m.group(1), 16)] = [x.strip() for x in m.group(2).split(" / ")]
    return out


def esc(t):
    return (t or "").replace("\\", "\\\\").replace("\r\n", "\\n").replace("\r", "\\n") \
        .replace("\n", "\\n").replace("\t", "\\t")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("out")
    ap.add_argument("--readall", help="ReadAll.txt (default: sibling of DB.bin)")
    a = ap.parse_args()
    setup_log()
    logging.info("parse %s -> %s", a.db, a.out)
    db = Db(open(a.db, "rb").read())
    regs = db.parse()
    d = db.d

    ra_path = a.readall or os.path.join(os.path.dirname(os.path.abspath(a.db)), "ReadAll.txt")
    readall = read_readall(ra_path)

    # ---- resolve names / consistency checks --------------------------------
    warn = {"nf": 0, "name": 0, "addr2": 0, "fname": 0}
    for i, r in enumerate(regs):
        r["name"] = db.s(r["nameptr"])
        if r["addr"] != r["addr2"] or r["pidx"] != r["pidx2"]:
            warn["addr2"] += 1
        if r["nf"] != len(r["fields"]):
            warn["nf"] += 1
        fl = []
        prev_kt = r["fptr"]
        for f in r["fields"]:
            lo, hi = d[f + 8], d[f + 9]
            acc, = struct.unpack_from("<I", d, f + 12)
            rv, = struct.unpack_from("<H", d, f + 16)
            p_desc, p_grp = struct.unpack_from("<II", d, f + 20)
            kt, = struct.unpack_from("<I", d, f + 32)
            w_lo, w_hi = struct.unpack_from("<II", d, f)
            wide = None if (w_lo, w_hi) == (0xFFFFFFFF, 0xFFFFFFFF) else (w_lo, w_hi)
            fl.append(dict(lo=lo, hi=hi, acc=acc, rv=rv, name=db.s(prev_kt),
                           desc=db.s(p_desc), rgrp=db.s(p_grp), wide=wide, kt=kt))
            prev_kt = kt
        r["fl"] = fl
    # last field's kt = group id of the NEXT register; first reg: preamble[-1] [fw]
    for i, r in enumerate(regs):
        r["gid"] = (regs[i - 1]["fl"][-1]["kt"] if i else db.preamble[-1])
    logging.info("consistency warnings: %s", warn)

    # ---- group assignment: runs of gid inside a page, in stream order ------
    # ReadAll group list = ordered runs of group ids [fw: matched on checked pages]
    by_page = {}
    for r in regs:
        by_page.setdefault(r["addr"] >> 8, []).append(r)
    ok_pages = bad_pages = 0
    gmap, conflicts = {}, 0
    page_runs = {}
    for pg, rl in sorted(by_page.items()):
        runs = []
        for r in rl:
            if not runs or runs[-1][0] != r["gid"]:
                runs.append([r["gid"], []])
            runs[-1][1].append(r)
        page_runs[pg] = runs
        names = readall.get(pg)
        if names and len(names) == len(runs):
            ok_pages += 1
            for (gid, rs), nm in zip(runs, names):
                if gmap.setdefault(gid, nm) != nm:
                    conflicts += 1
    # pass 2: pages with unequal counts: anchor runs on already-known gids, then fill
    # unknown runs between two anchors when the ReadAll gap has exactly that many names
    for _ in range(2):
        for pg, runs in page_runs.items():
            names = readall.get(pg)
            if not names or len(names) == len(runs):
                continue
            ptr, pend = 0, []
            for k, (gid, rs) in enumerate(runs + [(None, None)]):
                nm = gmap.get(gid) if gid is not None else None
                hit = None
                if gid is None:
                    hit = len(names)
                elif nm:
                    hit = next((j for j in range(ptr, len(names)) if names[j] == nm), None)
                if hit is None and gid is not None and nm:
                    continue  # anchor not found in order: ignore it
                if gid is not None and not nm:
                    pend.append(gid)
                    continue
                if pend and hit - ptr == len(pend):
                    for g, n2 in zip(pend, names[ptr:hit]):
                        gmap.setdefault(g, n2)
                pend = []
                ptr = hit + 1
    for pg, runs in page_runs.items():
        names = readall.get(pg)
        for gid, rs in runs:
            nm = gmap.get(gid, "")
            if nm and names and nm not in names:
                nm = ""  # learned name not in this page's ReadAll list
            for r in rs:
                r["group"] = nm
        if names and len(names) != len(runs):
            bad_pages += 1
            logging.info("page %02X: %d ReadAll groups vs %d gid runs; groups via gid map",
                         pg, len(names), len(runs))
    logging.info("gid->group map: %d ids, %d conflicts", len(gmap), conflicts)
    logging.info("group mapping: %d pages matched, %d mismatched", ok_pages, bad_pages)

    # ---- write TSV ---------------------------------------------------------
    cols = ["page", "address", "port_idx", "reg_type", "kind", "register", "bit_high", "bit_low",
            "field", "access", "reset", "group", "group_id", "wide_lo", "wide_hi",
            "reset_group", "description"]
    nreg = nfld = 0
    with open(a.out, "w", encoding="utf-8", newline="") as fo:
        fo.write("\t".join(cols) + "\n")
        for r in regs:
            pg = "%02X" % (r["addr"] >> 8)
            adr = "0x%04X" % r["addr"]
            pidx = r["pidx"] if r["lvl"] != 1 else ""
            regreset = 0
            for f in r["fl"]:
                mask = (1 << (f["hi"] - f["lo"] + 1)) - 1
                regreset |= (f["rv"] & mask) << f["lo"]
            fo.write("\t".join(str(x) for x in [
                pg, adr, pidx, r["lvl"], "REG", r["name"], 7 if r["fl"] else "", 0 if r["fl"] else "",
                "", "", "0x%02X" % (regreset & 0xFF), r["group"], r["gid"], "", "", "",
                ""]) + "\n")
            nreg += 1
            for f in r["fl"]:
                acc = ACCESS.get(f["acc"], "?%d" % f["acc"])
                if "write 1 clear" in (f["desc"] or "").lower():
                    acc = "W1C"  # inferred from description text [guess]
                w = f["wide"]
                fo.write("\t".join(str(x) for x in [
                    pg, adr, pidx, r["lvl"], "FIELD", r["name"], f["hi"], f["lo"], f["name"], acc,
                    "0x%02X" % f["rv"], r["group"], r["gid"],
                    w[0] if w else "", w[1] if w else "", esc(f["rgrp"]), esc(f["desc"])]) + "\n")
                nfld += 1
    logging.info("wrote %d register rows, %d field rows, %d pages", nreg, nfld, len(by_page))
    print("registers=%d fields=%d pages=%d" % (nreg, nfld, len(by_page)))


if __name__ == "__main__":
    main()
