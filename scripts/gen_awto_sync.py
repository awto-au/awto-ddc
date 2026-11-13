#!/usr/bin/env python3
"""Generate the #139 C tables: sync log (fw/awto/sync.tsv) and selector port signals (fw/awto/portsig.tsv).

usage: gen_awto_sync.py [--check]
  Rewrites the blocks between `GENERATED-BEGIN <name>` / `GENERATED-END <name>` markers in:
    fw/sdcc/awto_sync.inc     awto_sync_rows: event filter / row lookup (id, arg) -> row (SysMain translation unit)
    fw/sdcc/awto_osdcard.inc  awto_sync_text: per-row format + text, one table + one reader (awto-sdcc#39: same bank)
                              awto_port_sigs: one row per port signal (source, columns, labels)
    RL6449_Project.h          awto_port_cnt: edge counters the input monitor keeps for `cnt` signals
  The sync.tsv texts are also read by the host decoder (scripts/sync_log.py in awto-ddc main).
  Texts may hold {NAME} / {NAME/DIV}: the integer #define in RL6449_Project.h (resolve(); wb_build.py copies the resolved tsv for the host).
  --check: exit 1 when any block is out of date.
  Line width (every run): each row's worst-case console line (longest name / value at every %, port prefix, time column)
    must fit 2 rows of the main-page log (AWTO_LOG_W_MAIN cells, continuation at AWTO_LOG_TXT0: awto_dbgpop.inc); exit 1 if not.
Log: tmp/logs/gen_awto_sync.log
"""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).resolve().parent, capture_output=True, text=True)
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else Path(__file__).resolve().parents[1]


ROOT = repo_root()
TSV = ROOT / "fw/awto/sync.tsv"
LOG = ROOT / "tmp/logs/gen_awto_sync.log"
FMTS = {"-": 0, "vport": 1, "res": 2, "mhz1": 3, "hz1": 4, "hz3": 5, "mhz3": 6, "dp": 7, "src": 8, "harg": 9, "pc": 10, "ms": 11, "n": 12, "x": 13, "htime": 14, "sms": 15, "wdt": 16, "sys": 17, "sysreq": 18, "ms2": 19, "pby": 20, "sname": 21, "nvw": 22}
PORT_FLAG = 0x80                                     # fmt bit7: "Dn " prefix from arg


def log(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def parse_fmt(f: str) -> int:
    if f == "port":
        return PORT_FLAG
    if f.startswith("port"):
        return PORT_FLAG | FMTS[f[4:]]
    return FMTS[f]


HEADER = ROOT / "fw/sdk/Project/Header/RL6449_Project.h"
TOKEN = re.compile(r"\{([A-Za-z0-9_]+)(?:/(\d+))?\}")


def define_value(name: str, header: Path = HEADER) -> int:
    m = re.search(rf"^#define\s+{re.escape(name)}\s+\(?(0x[0-9A-Fa-f]+|\d+)", header.read_text(), re.M)
    if not m:
        raise SystemExit(f"sync.tsv: {{{name}}} is not an integer #define in {header.name}")
    return int(m.group(1), 0)


def resolve(text: str, header: Path = HEADER) -> str:
    """{NAME} / {NAME/DIV} in a text -> the integer #define of NAME (/ DIV) in the project header: a number the firmware
    knows is never typed into a log text."""
    return TOKEN.sub(lambda m: str(define_value(m.group(1), header) // int(m.group(2) or 1)), text)


def rows(path: Path = TSV):
    out = []
    for ln in path.read_text().splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        i, a, f, t = ln.split("\t")
        out.append(dict(id=int(i, 16), arg=0xFF if a == "*" else int(a, 16), a=a, f=f, fmt=parse_fmt(f), text=resolve(t)))
    out = [x for x in out if x["id"] not in NAME_IDS] + [x for x in out if x["id"] in NAME_IDS]   # logged rows first, names after
    n = logged(out)
    assert n < 255 and len(out) - n < 255, "row index is one byte per part (0 = no row): logged rows, name rows"
    for t in out:                                    # one value per line; ms2 has two
        n, two = t["text"].count("%"), (t["fmt"] & 0x7F) == FMTS["ms2"]
        assert (n == 2) if two else (n <= 1), f"{t['id']:02X} {t['arg']:02X}: {n} % marks"
    return out


def logged(r) -> int:
    """rows the ring logs (AWTO_SYNC_ROWS); the name-table rows follow them, indexed from there (tAwtoSyncNameRow)"""
    return sum(x["id"] not in NAME_IDS for x in r)


def arr(name, vals, per=16):
    body = ",\n    ".join(", ".join(vals[i:i + per]) for i in range(0, len(vals), per))
    return f"static const __code BYTE {name}[{len(vals)}] = {{\n    {body}}};"


def rows_block(r):
    n = logged(r)
    r = r[:n]
    ids = [x["id"] for x in r]
    assert all(ids.index(i) + ids.count(i) == len(ids) - ids[::-1].index(i) for i in set(ids)), "rows of one id must be adjacent"
    first = [0] * 256                                 # #162 step 3: row + 1 of the id's first row, so a lookup scans only that id
    for k, i in enumerate(ids):
        if first[i] == 0:
            first[i] = k + 1
    return "\n".join([
        f"#define AWTO_SYNC_ROWS {n}",
        arr("tAwtoSyncRowId", [f"0x{x['id']:02X}" for x in r]),
        arr("tAwtoSyncRowArg", [f"0x{x['arg']:02X}" for x in r]),
        arr("tAwtoSyncIdRow", [str(v) for v in first], 32),
        "BYTE AwtoSyncRow(BYTE ucId, BYTE ucArg)           // row + 1 of the first match (arg 0xFF = any), 0 = not logged",
        "{",
        "    BYTE ucI = tAwtoSyncIdRow[ucId];",
        "",
        "    if(ucI == 0)",
        "    {",
        "        return 0;",
        "    }",
        "    for(ucI--; (ucI < AWTO_SYNC_ROWS) && (tAwtoSyncRowId[ucI] == ucId); ucI++)",
        "    {",
        "        if((tAwtoSyncRowArg[ucI] == 0xFF) || (tAwtoSyncRowArg[ucI] == ucArg))",
        "        {",
        "            return ucI + 1;",
        "        }",
        "    }",
        "    return 0;",
        "}"])


NAME_IDS = range(0x15, 0x1C)                         # #162 step 3 name tables (state, who / why, request, outcome, separators,
                                                     # s3b: 1A mode text per state, 1B panel requester)
NAME_ARGS = 64                                       # args per name table: direct row index, no row scan per name (console draws in PS)


def names_block(r):
    tab = [0] * (len(NAME_IDS) * NAME_ARGS)
    n = logged(r)
    for k, x in enumerate(r):
        if x["id"] in NAME_IDS:
            assert x["arg"] < NAME_ARGS, f"name table {x['id']:02X}: arg {x['arg']:02X} >= {NAME_ARGS}"
            tab[(x["id"] - NAME_IDS.start) * NAME_ARGS + x["arg"]] = k - n + 1    # + AWTO_SYNC_NAME_ROW0 - 1 = text row
    return "\n".join([
        f"#define AWTO_SYNC_NAME_FIRST 0x{NAME_IDS.start:02X}",
        f"#define AWTO_SYNC_NAME_ROW0 {n}                 // text row of name row 0 (= the logged rows)",
        f"#define AWTO_SYNC_NAME_IDS {len(NAME_IDS)}",
        f"#define AWTO_SYNC_NAME_ARGS {NAME_ARGS}",
        arr("tAwtoSyncNameRow", [str(v) for v in tab], 32)])


def text_block(r):
    blob = ""
    for x in r:
        blob += x["text"].replace('"', '\\"').replace("%", '\\x01" "') + '\\0" "'   # literal splits end the escapes
    real, pos = [], 0                                # offsets in bytes: \x01 and \0 are one byte each
    for x in r:
        real.append(pos)
        pos += len(x["text"]) + 1
    assert pos < 65536
    return "\n".join([
        arr("tAwtoSyncFmt", [f"0x{x['fmt']:02X}" for x in r]),
        f'static const __code char tAwtoSyncTxtS[] = "{blob}";',
        f"static const __code WORD tAwtoSyncTxtOff[{len(r)}] = {{" + ", ".join(str(o) for o in real) + "};",
        "static BYTE AwtoSyncTxt(WORD usRow, BYTE ucPart)   // text after ucPart (0..2) value marks, 0xFF = none; returns the fmt",
        "{                                                  // usRow: logged row, or AWTO_SYNC_NAME_ROW0 + name row",
        "    const __code char *pc = &tAwtoSyncTxtS[tAwtoSyncTxtOff[usRow]];",
        "",
        "    if(ucPart == 0xFF)",
        "    {",
        "        return tAwtoSyncFmt[usRow];",
        "    }",
        "    if(ucPart != 0)                             // at most two marks (ms2); ucPart is not written (no XDATA copy)",
        "    {",
        "        while((*pc != 0) && (*pc != 1))",
        "        {",
        "            pc++;",
        "        }",
        "        if(*pc == 0)",
        "        {",
        "            return tAwtoSyncFmt[usRow];",
        "        }",
        "        pc++;",
        "        if(ucPart == 2)",
        "        {",
        "            while((*pc != 0) && (*pc != 1))",
        "            {",
        "                pc++;",
        "            }",
        "            if(*pc == 0)",
        "            {",
        "                return tAwtoSyncFmt[usRow];",
        "            }",
        "            pc++;",
        "        }",
        "    }",
        "    while((*pc != 0) && (*pc != 1))             // AwtoPutChar inlined: no call, so the packer keeps the table in this bank",
        "    {",
        "        if(s_bAwtoSkip != 0)",
        "        {",
        "            if(--s_ucLogI == 0)                 // second pass of a wrapped console line: dropped",
        "            {",
        "                s_bAwtoSkip = 0;",
        "            }",
        "        }",
        "        else if(s_ucAwtoLen < s_ucAwtoCols)",
        "        {",
        "            s_pcAwtoRow[s_ucAwtoLen++] = *pc;",
        "        }",
        "        else if(s_bAwtoWrap != 0)",
        "        {",
        "            s_bAwtoOver = 1;                    // main-page log: the line takes two rows (AwtoConWrapLine)",
        "        }",
        "        pc++;",
        "    }",
        "    return tAwtoSyncFmt[usRow];",
        "}",
        names_block(r)])


PS_TSV = ROOT / "fw/awto/portsig.tsv"
IN_TSV = ROOT / "fw/awto/inputs.tsv"
PS_SRC = {"in": 0, "cnt": 1, "xreg": 2, "cable": 3, "ddc": 4, "tmds": 5}
PS_COL0 = 3                                          # signal line: first field column (under the port name)
PS_W = {"cnt": 5}                                    # value width: "255/s"; bit signals one char (+ / -)


def port_sigs(path: Path = PS_TSV):
    names = [ln.split("\t")[0] for ln in IN_TSV.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    out, col, cnts = [], {}, []
    for ln in path.read_text().splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        p, lab, src, a, b, _desc = ln.split("\t")
        assert len(lab) <= 4 and p in ("D1", "D2", "D3"), ln
        pi = int(p[1]) - 1
        if src in ("in", "cnt"):
            ia = names.index(a)
            if src == "cnt":
                cnts.append(ia)
                ia = len(cnts) - 1                    # counter number
        else:
            ia = int(a, 0)
        c = col.get(pi, PS_COL0)
        sep = 1 if src in PS_W else 0                 # "p17 12/s", but "hpd+"
        out.append(dict(port=pi, label=lab, src=PS_SRC[src], a=ia, b=int(b, 0), lcol=c, col=c + len(lab) + sep))
        col[pi] = c + len(lab) + sep + PS_W.get(src, 1) + 1
    assert max(col.values()) <= 46, "signal line wider than the selector (AWTO_SRC_COLS)"
    return out, cnts


def ps_block(s):
    lbl = "".join(x["label"] + '\\0" "' for x in s)            # literal split: "\0" before a digit would be an octal escape
    offs, pos = [], 0
    for x in s:
        offs.append(pos)
        pos += len(x["label"]) + 1
    return "\n".join([
        f"#define AWTO_PS_N {len(s)}",
        arr("tAwtoPsPort", [str(x["port"]) for x in s]),
        arr("tAwtoPsSrc", [str(x["src"]) for x in s]),
        f"static const __code WORD tAwtoPsA[{len(s)}] = {{" + ", ".join(f"0x{x['a']:04X}" for x in s) + "};",
        arr("tAwtoPsB", [f"0x{x['b']:02X}" for x in s]),
        arr("tAwtoPsCol", [str(x["col"]) for x in s]),
        arr("tAwtoPsLblCol", [str(x["lcol"]) for x in s]),
        f'static const __code char tAwtoPsLblS[] = "{lbl}";',
        arr("tAwtoPsLblOff", [str(o) for o in offs]),
        "static void AwtoPsLbl(BYTE ucRow)                  // signal label (one table + its reader, awto-sdcc#39)",
        "{",
        "    const __code char *pc = &tAwtoPsLblS[tAwtoPsLblOff[ucRow]];",
        "",
        "    while(*pc != 0)",
        "    {",
        "        AwtoPutChar(*pc++);",
        "    }",
        "}"])


def cnt_block(cnts):
    L = [f"#define AWTO_PS_CNT_N                                           {len(cnts)}       // inputs whose rising edges are counted (fw/awto/portsig.tsv cnt rows)"]
    body = " ".join(f"if(i == {ix}) {{ g_pucAwtoInCnt[{k}]++; }}" for k, ix in enumerate(cnts))
    L.append(f"#define AWTO_PS_COUNT(i, v)                                     {{ if((v) != 0) {{ {body} }} }}")
    return "\n".join(L)


# ---- console line width (Dan 2026-11-12: no line clipped): worst case per row vs the console log row ---------------------
DBGPOP = ROOT / "fw/sdcc/awto_dbgpop.inc"
OSDCARD = ROOT / "fw/sdcc/awto_osdcard.inc"
GLOBAL_H = ROOT / "fw/sdk/Kernel/Common/Global.h"
DEF_RE = re.compile(r"^#define[ \t]+(\w+)[ \t]+([^/\n]+?)[ \t]*(?://.*)?$", re.M)
DW = 10                                              # digits of a 32-bit ring value (every value field is a DWORD)


def c_int(name: str, path: Path) -> int:
    """integer value of a #define in path (a plain expression of other #defines there)"""
    defs = dict(DEF_RE.findall(path.read_text()))

    def ev(n, depth=0):
        if n not in defs or depth > 8:
            raise SystemExit(f"{n}: no integer #define in {path.name}")
        e = re.sub(r"\b(0x[0-9A-Fa-f]+|\d+)U?L?\b", lambda m: str(int(m.group(1), 0)), defs[n])
        e = re.sub(r"\b[A-Za-z_]\w*\b", lambda m: str(ev(m.group(0), depth + 1)), e)
        if not re.fullmatch(r"[\d\s()+\-*/]+", e):
            raise SystemExit(f"{n} = {defs[n]}: not a plain integer expression")
        return int(eval(e.replace("/", "//")))       # noqa: S307 (digits and + - * / only)
    return ev(name)


def card(name: str) -> str:
    """text AWTO_CT_<name> of tAwtoCardS (port names, units, DP rates the formats print)"""
    t = OSDCARD.read_text()
    lit = t[t.index("tAwtoCardS[] ="):]
    parts = "".join(re.findall(r'"((?:[^"\\]|\\.)*)"', lit[:lit.index(";")])).split("\\0")
    base, _, k = name.partition("+")
    return parts[c_int("AWTO_CT_" + base, OSDCARD) + int(k or 0)]


def names(r: list, ident: int) -> list:
    return [x["text"] for x in r if x["id"] == ident] + ["FF"]      # an arg without a row prints in hex


def sep(r: list, k: int) -> list:
    return [next(x["text"] for x in r if x["id"] == AWTO_SEP and x["arg"] == k)]


AWTO_SEP = 0x19


def value_segs(f: str, r: list, port: list) -> list:
    """segments (each a list of alternative strings) a fmt prints at its %: AwtoSyncLine, every value at its widest"""
    def num(n):
        return ["9" * n]
    hz, mhz = card("HZ"), card("HZ+2")
    return {
        "-": [], "vport": [["auto", *port]], "res": [num(5), ["x"], num(5)],
        "mhz1": [num(DW - 1), ["."], num(1), [mhz]], "hz1": [num(DW - 1), ["."], num(1), [hz]],
        "hz3": [num(DW - 3), ["."], num(3), [hz]], "mhz3": [num(DW - 3), ["."], num(3), [mhz]],
        "dp": [[card("RBR"), card("RBR+1"), card("RBR+2"), card("HBR3"), "FF"], [" x"], num(3)],
        "src": [["HDMI", "DP", "DVI", "9" * DW]], "harg": [num(2)],
        "pc": [["STALL TEST, PC ", "STALL, PC "], ["FF", "C"], [":"], num(4)],
        "ms": [num(DW), [" ms"]], "n": [num(DW)], "x": [num(6)],
        "htime": [["2106-02-07T06:28:15+31:45"]], "sms": [["-", "+"], num(DW), [" ms"]],
        "wdt": [["warning "], num(5), [" ms, reset "], num(5), [" ms"]],
        "sys": [sep(r, 6), names(r, 0x15), sep(r, 7), num(len(str(c_int("AWTO_SYS_MS_MAX", HEADER)))), sep(r, 8), names(r, 0x15),
                sep(r, 9), names(r, 0x16), ["", sep(r, 5)[0]], ["", *names(r, 0x1A)]],
        "sysreq": [names(r, 0x17), sep(r, 4), names(r, 0x16), sep(r, 2), names(r, 0x18), [")"]],
        "pby": [names(r, 0x1B)],
        "sname": [names(r, 0x15)],
        "nvw": [["nothing changed, no flash write (", "wrote "], ["511+", "1023+"], [" ms)", " B"],
                ["", " (system data, OSD data, colour, panel time, awto settings)"], [" in "], ["63+"], [" programs, "],
                ["3+"], [" erases, "], ["511+"], [" ms"]],
    }[f]


def segments(x: dict, r: list, port: list) -> list:
    """a row's console line as segments: leading space + time column, port prefix, text with each % expanded"""
    f = x["f"][4:] if x["f"].startswith("port") else x["f"]
    seg = [[" +99999 ms "]] + ([[p + " " for p in port]] if x["f"].startswith("port") else [])
    parts = x["text"].split("%")
    for k, p in enumerate(parts):
        seg.append([p])
        if k + 1 < len(parts):
            seg += [num5ms()] if f == "ms2" else value_segs(f, r, port)
    return seg


def num5ms():
    return ["99999 ms"]                             # ms2: two 16-bit ms values


def seg_len(seg: list) -> tuple:
    """(longest length, longest run without a space) over every choice of alternatives (upper bounds)"""
    n = run = best = 0
    for alts in seg:
        n += max(len(a) for a in alts)
        nxt = 0
        for a in alts:
            if " " in a:
                best = max(best, run + a.index(" "), max(len(w) for w in a.split(" ")))
                nxt = max(nxt, len(a) - a.rindex(" ") - 1)
            else:
                nxt = max(nxt, run + len(a))
        run = nxt
        best = max(best, run)
    return n, best


def console_rows(n: int, word: int, w: int, txt0: int) -> int:
    """rows a line of n cells takes: AwtoConWrapLine breaks at the last space before the edge (a run of at most word - 1
    cells moves down), the continuation starts at txt0 (under the text); 3 = does not fit in two"""
    if n <= w:
        return 1
    return 2 if txt0 + n - (w - word) - 1 <= w else 3


def line_check(r: list, wraps: bool = False) -> int:
    """every row's worst-case line in at most 2 rows of the main-page log; the host time line + its fw tail in one row
    (AwtoConLogTail moves cells, no wrap there). Returns the number of failures; widths read from the firmware."""
    w, txt0 = c_int("AWTO_LOG_W_MAIN", DBGPOP), c_int("AWTO_LOG_TXT0", DBGPOP)
    dmax = max(int(n) for n in re.findall(r"^#define\s+_D(\d)_INPUT_PORT\b", GLOBAL_H.read_text(), re.M))
    port = [card("DP"), card("HDMI") + str(dmax), card("PORT") + str(dmax)]
    bad, rep = 0, []
    for x in r:
        if x["id"] in NAME_IDS:
            continue
        n, word = seg_len(segments(x, r, port))
        k = console_rows(n, word, w, txt0)
        rep.append((n, k, x))
        if k > 2:
            bad += 1
            log(f"LINE TOO LONG {x['id']:02X} {x['a']}: worst case {n} cells, more than 2 rows of {w}: {x['text']}")
    host = next(x for x in r if x["id"] == 0xD7)
    for fw in (x for x in r if x["id"] == 0xD8):
        n = seg_len(segments(host, r, port))[0] + 1 + seg_len(segments(fw, r, port)[1:])[0]
        if n > w:
            bad += 1
            log(f"LINE TOO LONG D7 + D8 {fw['a']} (one row, AwtoConLogTail): worst case {n} cells > {w}")
    rep.sort(key=lambda t: -t[0])
    if wraps:                                     # --wraps: list the rows that wrap to two console rows
        for n, k, x in rep:
            if k == 2:
                log(f"WRAP {x['id']:02X} {x['a']} worst case {n} cells: {x['text']}")
    log(f"console log row {w} cells, text at {txt0}: {sum(k == 1 for _, k, _ in rep)} rows fit one row, "
        f"{sum(k == 2 for _, k, _ in rep)} wrap to two, {bad} fail; widest: " +
        ", ".join(f"{x['id']:02X} {x['a']} {n}" for n, _, x in rep[:8]))
    return bad


def patch(path: Path, name: str, block: str):
    b, e = f"GENERATED-BEGIN {name}", f"GENERATED-END {name}"
    t = path.read_text()
    a = t.index("\n", t.index(b)) + 1
    z = t.rindex("\n", 0, t.index(e)) + 1
    return t[:a] + block + "\n" + t[z:], t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--wraps", action="store_true", help="list the rows whose worst-case line wraps to two console rows")
    a = ap.parse_args()
    r = rows()
    s, cnts = port_sigs()
    stale = 0
    for path, name, blk in ((ROOT / "fw/sdcc/awto_sync.inc", "awto_sync_rows", rows_block(r)),
                            (ROOT / "fw/sdcc/awto_osdcard.inc", "awto_sync_text", text_block(r)),
                            (ROOT / "fw/sdcc/awto_osdcard.inc", "awto_port_sigs", ps_block(s)),
                            (ROOT / "fw/sdk/Project/Header/RL6449_Project.h", "awto_port_cnt", cnt_block(cnts))):
        new, old = patch(path, name, blk)
        if new != old:
            stale += 1
            if not a.check:
                path.write_text(new)
            log(f"{path.name} {name}: {'out of date' if a.check else 'rewritten'}")
    log(f"{len(r)} sync rows; {stale} block(s) changed")
    bad = line_check(r, a.wraps)
    return 1 if (a.check and stale) or bad else 0


if __name__ == "__main__":
    sys.exit(main())
