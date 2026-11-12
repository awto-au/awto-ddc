#!/usr/bin/env python3
"""Generate the #139 C tables: sync log (fw/awto/sync.tsv) and selector port signals (fw/awto/portsig.tsv).

usage: gen_awto_sync.py [--check]
  Rewrites the blocks between `GENERATED-BEGIN <name>` / `GENERATED-END <name>` markers in:
    fw/sdcc/awto_sync.inc     awto_sync_rows: event filter / row lookup (id, arg) -> row (SysMain translation unit)
    fw/sdcc/awto_osdcard.inc  awto_sync_text: per-row format + text, one table + one reader (awto-sdcc#39: same bank)
                              awto_port_sigs: one row per port signal (source, columns, labels)
    RL6449_Project.h          awto_port_cnt: edge counters the input monitor keeps for `cnt` signals
  The sync.tsv texts are also read by the host decoder (scripts/sync_log.py in awto-ddc main).
  --check: exit 1 when any block is out of date.
Log: tmp/logs/gen_awto_sync.log
"""
import argparse
import os
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
FMTS = {"-": 0, "vport": 1, "res": 2, "mhz1": 3, "hz1": 4, "hz3": 5, "mhz3": 6, "dp": 7, "src": 8, "harg": 9, "pc": 10, "ms": 11, "n": 12, "x": 13, "htime": 14, "sms": 15}
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


def rows(path: Path = TSV):
    out = []
    for ln in path.read_text().splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        i, a, f, t = ln.split("\t")
        out.append(dict(id=int(i, 16), arg=0xFF if a == "*" else int(a, 16), fmt=parse_fmt(f), text=t))
    assert len(out) < 255, "row index is one byte (0 = no row)"
    assert all(t["text"].count("%") <= 1 for t in out), "one value per line"
    return out


def arr(name, vals, per=16):
    body = ",\n    ".join(", ".join(vals[i:i + per]) for i in range(0, len(vals), per))
    return f"static const __code BYTE {name}[{len(vals)}] = {{\n    {body}}};"


def rows_block(r):
    n = len(r)
    return "\n".join([
        f"#define AWTO_SYNC_ROWS {n}",
        arr("tAwtoSyncRowId", [f"0x{x['id']:02X}" for x in r]),
        arr("tAwtoSyncRowArg", [f"0x{x['arg']:02X}" for x in r]),
        "BYTE AwtoSyncRow(BYTE ucId, BYTE ucArg)           // row + 1 of the first match (arg 0xFF = any), 0 = not logged",
        "{",
        "    BYTE ucI;",
        "",
        "    for(ucI = 0; ucI < AWTO_SYNC_ROWS; ucI++)",
        "    {",
        "        if((tAwtoSyncRowId[ucI] == ucId) && ((tAwtoSyncRowArg[ucI] == 0xFF) || (tAwtoSyncRowArg[ucI] == ucArg)))",
        "        {",
        "            return ucI + 1;",
        "        }",
        "    }",
        "    return 0;",
        "}"])


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
        "static BYTE AwtoSyncTxt(BYTE ucRow, BYTE ucPart)   // text before (0) / after (1) the value mark, 2 = none; returns the fmt",
        "{",
        "    const __code char *pc = &tAwtoSyncTxtS[tAwtoSyncTxtOff[ucRow]];",
        "",
        "    if(ucPart == 2)",
        "    {",
        "        return tAwtoSyncFmt[ucRow];",
        "    }",
        "    if(ucPart != 0)",
        "    {",
        "        while((*pc != 0) && (*pc != 1))",
        "        {",
        "            pc++;",
        "        }",
        "        if(*pc == 0)",
        "        {",
        "            return tAwtoSyncFmt[ucRow];",
        "        }",
        "        pc++;",
        "    }",
        "    while((*pc != 0) && (*pc != 1))             // AwtoPutChar inlined: no call, so the packer keeps the table in this bank",
        "    {",
        "        if(s_ucAwtoLen < s_ucAwtoCols)",
        "        {",
        "            s_pcAwtoRow[s_ucAwtoLen++] = *pc;",
        "        }",
        "        pc++;",
        "    }",
        "    return tAwtoSyncFmt[ucRow];",
        "}"])


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


def patch(path: Path, name: str, block: str):
    b, e = f"GENERATED-BEGIN {name}", f"GENERATED-END {name}"
    t = path.read_text()
    a = t.index("\n", t.index(b)) + 1
    z = t.rindex("\n", 0, t.index(e)) + 1
    return t[:a] + block + "\n" + t[z:], t


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
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
    return 1 if (a.check and stale) else 0


if __name__ == "__main__":
    sys.exit(main())
