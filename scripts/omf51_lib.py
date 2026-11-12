#!/usr/bin/env python3
"""Parser for Keil OMF-51 (Realtek RL6xxx SDK flavour) .LIB files.

Record framing: type(u8) len(u16 LE) body crc(u8, last byte of body).
Record types decoded (empirical, validated against the SDK C sources):
  0x2c LIBHDR  0x28 module-name table  0x26 module offsets  0x2a public dictionary
  0x02 MODHDR  0x04 MODEND
  0x0f SEGDEF*  segid u16, b2 (0 = code), 4 attr bytes, size u16, name(u8 len)
  0x07 CONTENT  segid u16, offset u16, bytes
  0x09 FIXUP*   8-byte entries: off u16 (patch start, relative to the preceding CONTENT record), type u8,
                kind u8, ref u16, addend u16. Applies to the preceding CONTENT.
                type: 0 low byte, 1 byte, 3 high byte, 4 word(2 bytes), 6 bit addr
                kind: 1 = segment ref (ref = segid), 2 = external ref (ref = ext idx)
  0x17 PUBDEF*  entries: segid u16, kind u8, off u16, 0 u8, name(u8 len)
  0x19 EXTDEF*  entries: 02, idx u16, 2 bytes, name(u8 len)
  others (0x10 scope, 0x20/0x23/0x24/0x72 debug) are skipped.
(*) a record may hold several entries.
Usage: omf51_lib.py <lib.LIB> [-v]   (lists modules/functions)
"""
import re
import sys
from dataclasses import dataclass, field

PATCH_LEN = {4: 2}  # fixup type -> bytes patched; others 1


@dataclass
class Seg:
    sid: int
    name: str
    size: int
    b2: int
    data: bytearray = None
    known: bytearray = None  # 1 where a CONTENT byte exists
    reloc: set = field(default_factory=set)  # byte offsets patched at link time
    fixups: list = field(default_factory=list)  # (off, type, kind, ref, addend)

    @property
    def is_code(self):
        return self.name.startswith("?PR?") or self.name.startswith("?CO?") or self.b2 == 0 and not self.name.startswith("?XD")


@dataclass
class Module:
    name: str
    segs: dict = field(default_factory=dict)
    publics: list = field(default_factory=list)  # (name, segid, off, kind)
    externs: dict = field(default_factory=dict)
    unresolved_fixups: int = 0
    casemap: dict = field(default_factory=dict)  # UPPERCASE -> original-case identifier (from debug records)

    def functions(self):
        """Yield (name, seg, off, size) for PUBDEFs in code segments (size = to next public / seg end)."""
        by_seg = {}
        for n, sid, off, kind in self.publics:
            s = self.segs.get(sid)
            if s and s.name.startswith("?PR?") and not n.startswith("?"):
                by_seg.setdefault(sid, []).append((off, n))
        for sid, lst in by_seg.items():
            lst.sort()
            s = self.segs[sid]
            for i, (off, n) in enumerate(lst):
                end = lst[i + 1][0] if i + 1 < len(lst) else s.size
                yield n, s, off, end - off


def _records(d):
    p = 0
    while p < len(d):
        t = d[p]
        l = int.from_bytes(d[p + 1:p + 3], "little")
        yield t, d[p + 3:p + 3 + l - 1]  # body without crc
        p += 3 + l


def _name(b, i):
    n = b[i]
    return b[i + 1:i + 1 + n].decode("latin1"), i + 1 + n


def parse_lib(path):
    d = open(path, "rb").read()
    mods, m, pend = [], None, []
    for t, b in _records(d):
        if t == 0x02:
            m = Module(_name(b, 0)[0]); mods.append(m); pend = []
        elif m is None:
            continue
        elif t in (0x10, 0x23):
            for w in re.findall(rb"[A-Za-z_][A-Za-z0-9_]{2,}", b):
                w = w.decode("latin1")
                if w != w.upper():
                    m.casemap.setdefault(w.upper(), w)
        elif t == 0x0f:
            i = 0
            while i < len(b):
                i0 = i
                sid = int.from_bytes(b[i:i + 2], "little")
                size = int.from_bytes(b[i + 7:i + 9], "little")
                nm, i = _name(b, i + 9)
                m.segs[sid] = Seg(sid, nm, size, b[i0 + 2])
        elif t == 0x07:
            sid = int.from_bytes(b[0:2], "little")
            off = int.from_bytes(b[2:4], "little")
            s = m.segs[sid]
            if s.data is None:
                s.data = bytearray(s.size); s.known = bytearray(s.size)
            data = b[4:]
            s.data[off:off + len(data)] = data
            s.known[off:off + len(data)] = b"\x01" * len(data)
            pend.append((sid, off, len(data)))
        elif t == 0x09:
            for i in range(0, len(b), 8):
                off = int.from_bytes(b[i:i + 2], "little")
                ty, kind = b[i + 2], b[i + 3]
                ref = int.from_bytes(b[i + 4:i + 6], "little")
                add = int.from_bytes(b[i + 6:i + 8], "little")
                if not pend:
                    m.unresolved_fixups += 1
                    continue
                sid, coff, clen = pend[-1]  # off is relative to the preceding CONTENT record
                s = m.segs[sid]
                s.fixups.append((coff + off, ty, kind, ref, add))
                for k in range(PATCH_LEN.get(ty, 1)):
                    s.reloc.add(coff + off + k)
            pend = []
        elif t == 0x17:
            i = 0
            while i < len(b):
                sid = int.from_bytes(b[i:i + 2], "little")
                kind = b[i + 2]
                off = int.from_bytes(b[i + 3:i + 5], "little")
                nm, i = _name(b, i + 6)
                m.publics.append((nm, sid, off, kind))
        elif t == 0x19:
            i = 0
            while i < len(b):
                idx = int.from_bytes(b[i + 1:i + 3], "little")
                nm, i = _name(b, i + 5)
                m.externs[idx] = nm
    return mods


def display_name(m, pub):
    """Original-case C name for an uppercase PUBDEF (leading '_' = register-passed args, dropped)."""
    n = m.casemap.get(pub, pub)
    return n[1:] if n.startswith("_") else n


def main():
    mods = parse_lib(sys.argv[1])
    verbose = "-v" in sys.argv
    nf = bad = 0
    for m in mods:
        fn = list(m.functions())
        nf += len(fn); bad += m.unresolved_fixups
        if verbose:
            print(f"{m.name}: segs={[s.name for s in m.segs.values()]} unresolved={m.unresolved_fixups}")
            for n, s, off, sz in fn:
                print(f"   {display_name(m, n)} {s.name}+{off:#x} size={sz} relocs={sum(1 for r in s.reloc if off <= r < off + sz)}")
    print(f"{len(mods)} modules, {nf} code functions, {bad} unresolved fixups")


if __name__ == "__main__":
    main()
