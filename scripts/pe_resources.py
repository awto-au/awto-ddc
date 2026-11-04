#!/usr/bin/env python3
"""Static PE resource extractor: dialogs, menus, string tables, accelerators, DLGINIT, version strings.

Pure stdlib; parses the PE resource directory directly (no execution of the binaries).
Usage: pe_resources.py <root-dir> <out.tsv>
Output TSV columns: source, restype, id, control_class, text
Log: ./tmp/logs/pe_resources.log (workspace-relative)
"""
import struct
import sys
from pathlib import Path

TYPES = {1: "CURSOR", 2: "BITMAP", 3: "ICON", 4: "MENU", 5: "DIALOG", 6: "STRING", 9: "ACCEL",
         14: "GROUP_ICON", 16: "VERSION", 240: "DLGINIT"}
CLASSES = {0x80: "Button", 0x81: "Edit", 0x82: "Static", 0x83: "ListBox", 0x84: "ScrollBar", 0x85: "ComboBox"}


def u16(d, o): return struct.unpack_from("<H", d, o)[0]
def u32(d, o): return struct.unpack_from("<I", d, o)[0]


def walk_resources(d):
    """Yield (type, name, lang, bytes)."""
    pe = u32(d, 0x3C)
    nsec = u16(d, pe + 6)
    optsz = u16(d, pe + 20)
    opt = pe + 24
    magic = u16(d, opt)
    ddoff = opt + (96 if magic == 0x10B else 112)
    rva, size = struct.unpack_from("<II", d, ddoff + 16)
    if not rva:
        return
    secs = []
    so = opt + optsz
    for i in range(nsec):
        vsz, va, rsz, rptr = struct.unpack_from("<IIII", d, so + 40 * i + 8)
        secs.append((va, max(vsz, rsz), rptr))

    def r2o(r):
        for va, sz, ptr in secs:
            if va <= r < va + sz:
                return r - va + ptr
        raise ValueError(hex(r))
    base = r2o(rva)

    def ident(v):
        if v & 0x80000000:
            o = base + (v & 0x7FFFFFFF)
            n = u16(d, o)
            return d[o + 2:o + 2 + 2 * n].decode("utf-16le")
        return v

    def entries(off):
        nn, ni = u16(d, off + 12), u16(d, off + 14)
        for i in range(nn + ni):
            nm, of = struct.unpack_from("<II", d, off + 16 + 8 * i)
            yield ident(nm), of

    for t, o1 in entries(base):
        for n, o2 in entries(base + (o1 & 0x7FFFFFFF)):
            for lang, o3 in entries(base + (o2 & 0x7FFFFFFF)):
                dr, ds = struct.unpack_from("<II", d, base + o3)
                yield t, n, lang, d[r2o(dr):r2o(dr) + ds]


def wstr(d, o):
    """NUL-terminated UTF-16 at o -> (str, next_offset)."""
    e = o
    while u16(d, e):
        e += 2
    return d[o:e].decode("utf-16le", "replace"), e + 2


def parse_dialog(d):
    """Return list of (id, class, text); first row is the dialog caption (id='DLG')."""
    rows = []
    ex = u16(d, 0) == 1 and u16(d, 2) == 0xFFFF
    if ex:
        style = u32(d, 12)
        cnt = u16(d, 16)
        o = 26
    else:
        style = u32(d, 0)
        cnt = u16(d, 8)
        o = 18

    def skip_sz_or_ord(o):
        if u16(d, o) == 0x0000:
            return "", o + 2
        if u16(d, o) == 0xFFFF:
            return "#%d" % u16(d, o + 2), o + 4
        return wstr(d, o)
    _, o = skip_sz_or_ord(o)       # menu
    cls, o = skip_sz_or_ord(o)     # class
    title, o = wstr(d, o)
    if style & 0x40:               # DS_SETFONT
        o += 6 if ex else 2
        _, o = wstr(d, o)
    rows.append(("DLG", cls or "Dialog", title))
    for _ in range(cnt):
        o = (o + 3) & ~3
        if ex:
            cid = u32(d, o + 20)
            o += 24
        else:
            cid = u16(d, o + 16)
            o += 18
        if cid > 0x7FFFFFFF or (not ex and cid == 0xFFFF):
            cid = -1
        if u16(d, o) == 0xFFFF:
            c = CLASSES.get(u16(d, o + 2), "0x%x" % u16(d, o + 2))
            o += 4
        else:
            c, o = wstr(d, o)
        if u16(d, o) == 0xFFFF:
            txt = "#res%d" % u16(d, o + 2)
            o += 4
        else:
            txt, o = wstr(d, o)
        o += 2 + u16(d, o)         # extra data
        rows.append((str(cid), c, txt))
    return rows


def parse_menu(d):
    rows = []
    ver = u16(d, 0)
    if ver == 0:
        o = 4 + u16(d, 2)

        def items(o, path):
            while True:
                fl = u16(d, o)
                o += 2
                if fl & 0x10:      # POPUP
                    txt, o = wstr(d, o)
                    rows.append(("POPUP", "Popup", path + txt))
                    o = items(o, path + txt + ">")
                else:
                    cid = u16(d, o)
                    o += 2
                    txt, o = wstr(d, o)
                    rows.append((str(cid), "Separator" if not cid and not txt else "MenuItem", path + txt))
                if fl & 0x80:      # END
                    return o
        items(o, "")
    else:  # MENUEX
        o = 4 + u16(d, 2)

        def items(o, path):
            while True:
                o = (o + 3) & ~3
                typ, st, cid = struct.unpack_from("<III", d, o)
                fl = u16(d, o + 12)
                o += 14
                txt, o = wstr(d, o)
                o = (o + 3) & ~3
                if fl & 1:
                    o += 4         # help id
                    rows.append(("POPUP", "Popup", path + txt))
                    o = items(o, path + txt + ">")
                else:
                    rows.append((str(cid), "MenuItem", path + txt))
                if fl & 0x80:
                    return o
        items(o, "")
    return rows


def parse_strings(name, d):
    rows = []
    o = 0
    base = (name - 1) * 16 if isinstance(name, int) else 0
    for i in range(16):
        if o + 2 > len(d):
            break
        n = u16(d, o)
        o += 2
        if n:
            rows.append((str(base + i), "String", d[o:o + 2 * n].decode("utf-16le", "replace")))
        o += 2 * n
    return rows


def parse_accel(d):
    rows = []
    for o in range(0, len(d) - 7, 8):
        fl, key, cid = struct.unpack_from("<HHH", d, o)
        rows.append((str(cid), "Accel", "key=0x%x flags=0x%x" % (key, fl)))
        if fl & 0x80:
            break
    return rows


def parse_dlginit(d):
    rows = []
    o = 0
    while o + 6 <= len(d):
        cid, msg = struct.unpack_from("<HH", d, o)
        if cid == 0:
            break
        ln = u32(d, o + 4)
        data = d[o + 8:o + 8 + ln]
        o += 8 + ln
        rows.append((str(cid), "DlgInit0x%x" % msg, data.split(b"\0")[0].decode("latin-1")))
    return rows


def parse_version(d):
    """Cheap: pull all UTF-16 key/value-ish strings."""
    rows = []
    s = d.decode("utf-16le", "ignore").split("\0")
    s = [x for x in s if len(x) > 2 and x.isprintable()]
    for i, x in enumerate(s):
        if x in ("FileDescription", "InternalName", "OriginalFilename", "ProductName", "FileVersion",
                 "ProductVersion", "CompanyName", "LegalCopyright", "Comments") and i + 1 < len(s):
            rows.append((x, "Version", s[i + 1]))
    return rows


def process(path, root, out, log):
    d = path.read_bytes()
    src = str(path.relative_to(root))
    counts = {}
    try:
        res = list(walk_resources(d))
    except Exception as e:
        log("%s: resource walk failed: %r" % (src, e))
        return {}
    for t, n, lang, data in res:
        tn = TYPES.get(t, str(t)) if isinstance(t, int) else str(t)
        try:
            if t == 5:
                rows = parse_dialog(data)
                rid = "dlg:%s" % n
                for cid, c, txt in rows:
                    out.append((src, "DIALOG", "%s/%s" % (rid, cid), c, txt))
                counts["dialogs"] = counts.get("dialogs", 0) + 1
                counts["controls"] = counts.get("controls", 0) + len(rows) - 1
                continue
            if t == 4:
                rows = parse_menu(data)
                counts["menus"] = counts.get("menus", 0) + 1
                for cid, c, txt in rows:
                    out.append((src, "MENU", "menu:%s/%s" % (n, cid), c, txt))
                continue
            if t == 6:
                rows = parse_strings(n, data)
                counts["strings"] = counts.get("strings", 0) + len(rows)
                for cid, c, txt in rows:
                    out.append((src, "STRING", cid, c, txt))
                continue
            if t == 9:
                for cid, c, txt in parse_accel(data):
                    out.append((src, "ACCEL", "accel:%s/%s" % (n, cid), c, txt))
                continue
            if t == 240:
                for cid, c, txt in parse_dlginit(data):
                    out.append((src, "DLGINIT", "dlg:%s/%s" % (n, cid), c, txt))
                continue
            if t == 16:
                for k, c, v in parse_version(data):
                    out.append((src, "VERSION", k, c, v))
        except Exception as e:
            log("%s: %s %s parse error %r" % (src, tn, n, e))
    return counts


def main():
    root = Path(sys.argv[1])
    outp = Path(sys.argv[2])
    logf = Path("tmp/logs/pe_resources.log")
    logf.parent.mkdir(parents=True, exist_ok=True)
    lf = logf.open("w")

    def log(m):
        print(m)
        lf.write(m + "\n")
    files = [p for p in sorted(root.rglob("*")) if p.suffix.lower() in (".dll", ".exe", ".ocx")]
    out = []
    for p in files:
        c = process(p, root, out, log)
        log("%s: %s" % (p.relative_to(root), c))
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as f:
        for r in out:
            f.write("\t".join(x.replace("\t", " ").replace("\n", "\\n").replace("\r", "") for x in r) + "\n")
    log("rows: %d -> %s" % (len(out), outp))


if __name__ == "__main__":
    main()
