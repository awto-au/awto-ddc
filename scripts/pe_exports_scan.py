#!/usr/bin/env python3
"""Static PE scan of an unpacked RTDCustomerTool tree: exports, CodeView PDB path, imports of interest.

usage: python3 -I pe_exports_scan.py <tool-tree> <out.tsv> [--version V]
  rows: version, relpath, kind (export|pdb|import-dll), value
Static only (never loads/executes the files). Log: ./tmp/logs/pe_exports_scan.log
"""
import argparse
import os
import struct
import sys


def rva2off(secs, rva):
    for va, vs, ro, rs in secs:
        if va <= rva < va + max(vs, rs):
            return rva - va + ro
    return None


def cstr(d, o):
    e = d.find(b"\0", o)
    return d[o:e].decode("latin1") if o is not None and e > o else ""


def scan(path):
    d = open(path, "rb").read()
    if d[:2] != b"MZ":
        return
    pe = struct.unpack_from("<I", d, 0x3C)[0]
    if d[pe:pe + 4] != b"PE\0\0":
        return
    nsec, = struct.unpack_from("<H", d, pe + 6)
    osz, = struct.unpack_from("<H", d, pe + 20)
    opt = pe + 24
    magic, = struct.unpack_from("<H", d, opt)
    dd = opt + (96 if magic == 0x10B else 112)
    secs = []
    so = opt + osz
    for i in range(nsec):
        vs, va, rs, ro = struct.unpack_from("<IIII", d, so + 40 * i + 8)
        secs.append((va, vs, ro, rs))

    def dirent(i):
        return struct.unpack_from("<II", d, dd + 8 * i)

    rva, size = dirent(0)
    if rva:
        o = rva2off(secs, rva)
        if o:
            nn, = struct.unpack_from("<I", d, o + 24)
            an, = struct.unpack_from("<I", d, o + 32)
            for i in range(nn):
                nr, = struct.unpack_from("<I", d, rva2off(secs, an) + 4 * i)
                yield "export", cstr(d, rva2off(secs, nr))
    rva, size = dirent(1)
    if rva:
        o = rva2off(secs, rva)
        while o:
            name_rva = struct.unpack_from("<I", d, o + 12)[0]
            if not name_rva:
                break
            yield "import-dll", cstr(d, rva2off(secs, name_rva)).lower()
            o += 20
    rva, size = dirent(6)
    if rva:
        o = rva2off(secs, rva)
        for i in range(size // 28):
            typ, = struct.unpack_from("<I", d, o + 28 * i + 12)
            fo, = struct.unpack_from("<I", d, o + 28 * i + 24)
            sz, = struct.unpack_from("<I", d, o + 28 * i + 16)
            if typ == 2 and d[fo:fo + 4] == b"RSDS":
                yield "pdb", cstr(d, fo + 24)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tree")
    ap.add_argument("out")
    ap.add_argument("--version", default="")
    a = ap.parse_args()
    rows = []
    for root, _, fs in os.walk(a.tree):
        for f in sorted(fs):
            if f.lower().endswith((".dll", ".exe", ".ocx")):
                p = os.path.join(root, f)
                rel = os.path.relpath(p, a.tree)
                try:
                    for k, v in scan(p):
                        rows.append((a.version, rel, k, v))
                except Exception as e:  # malformed PE: record and continue
                    rows.append((a.version, rel, "error", repr(e)))
    with open(a.out, "w") as fh:
        for r in sorted(rows):
            fh.write("\t".join(r) + "\n")
    os.makedirs("tmp/logs", exist_ok=True)
    with open("tmp/logs/pe_exports_scan.log", "a") as lg:
        lg.write(f"{a.version} {a.tree}: {len(rows)} rows -> {a.out}\n")
    print(len(rows), "rows")


if __name__ == "__main__":
    sys.exit(main())
