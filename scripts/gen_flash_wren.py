#!/usr/bin/env python3
"""ScalerFlashWREN per-chip table generator + exhaustive host proof (#296).

usage: gen_flash_wren.py apply            replace the function in ScalerCommonNVRam.c by the include
       gen_flash_wren.py gen   [--ref REF]   write ScalerCommonNVRamWren_gen.inc from ScalerFlashWREN at git REF
       gen_flash_wren.py proof [--ref REF]   old function (REF) vs the generated one: every chip 0..255 x bank 0..255 x page 0..255
  gen: the old function is traced with gcc stubs for every (chip, bank, page); a chip whose trace is one status-register call
  (SetWRSR / Set2ByteWRSR / ...onebyone, constant mode) whose arguments depend only on (bank, page) becomes table rows; every
  other chip keeps its original `case` text. The trace must not depend on the flash table values or on ReadSR (three runs).
  proof: one C++ program holding both functions: same stubs, per cell the event lists must be equal (watchdog feed, register
  writes, WRSR calls, order). Prints cells / mismatches; exit 1 on any mismatch.
Log: ./tmp/logs/gen_flash_wren.log
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from _log import shared

ROOT = Path(
    os.environ.get("AWTO_DDC_REPO")
    or subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    or Path(__file__).resolve().parents[1]
)
LOG = ROOT / "tmp/logs/gen_flash_wren.log"
SCRATCH = ROOT / "tmp/scratch/flash_wren"
CODE = "fw/sdk/Kernel/Scaler/ScalerCommonFunction/Code"
SRC = f"{CODE}/ScalerCommonNVRam.c"
GEN = f"{CODE}/ScalerCommonNVRamWren_gen.inc"
HDR = (
    "fw/sdk/Kernel/Scaler/ScalerCommonFunction/Header/ScalerCommonNVRamCommonInclude.h"
)
DEFAULT_REF = "4a08d84c"
SIG = "void ScalerFlashWREN(BYTE ucBank, BYTE ucPage)"
RUNS = (
    (1, 0),
    (2, 1),
    (1, 2),
)  # (flash table seed, ReadSR mode): the trace must not change
MODE_TXT = {0: "_FALSE", 1: "_TRUE", 2: "_WRITE_SR_MODE_SEL"}
FUNCS = {
    10: "ScalerFlashSetWRSR",
    11: "ScalerFlashSet2ByteWRSR",
    12: "ScalerFlashSet2ByteWRSRonebyone",
}


def say(s):
    shared(LOG, stamp_echo=False).say(s)


def git_show(ref, path):
    return subprocess.run(
        ["git", "show", f"{ref}:{path}"],
        capture_output=True,
        text=True,
        check=True,
        cwd=ROOT,
    ).stdout


def blank_comments(t):
    """comments -> spaces (same length), so brace matching ignores them"""
    return re.sub(
        r"//[^\n]*|/\*.*?\*/",
        lambda m: re.sub(r"[^\n]", " ", m.group(0)),
        t,
        flags=re.DOTALL,
    )


def match_brace(t, i):
    d = 0
    for k in range(i, len(t)):
        if t[k] == "{":
            d += 1
        elif t[k] == "}":
            d -= 1
            if d == 0:
                return k
    raise SystemExit("unbalanced braces")


def parse(src):
    """-> (func_start, func_end, preamble, groups[(labels, text)], tail) of ScalerFlashWREN"""
    c = blank_comments(src)
    s = src.index(SIG + "\n{")
    ob = c.index("{", s)
    e = match_brace(c, ob)
    body, cbody = src[ob + 1 : e], c[ob + 1 : e]
    sw = cbody.index("switch(g_ucFlashType)")
    sb = cbody.index("{", sw)
    se = match_brace(cbody, sb)
    wdt = body.index("// Clear watch dog")
    preamble = body[:wdt]
    inner, cinner = body[sb + 1 : se], cbody[sb + 1 : se]
    toks, d = [], 0
    for m in re.finditer(r"[{}]|\b(?:case\s+\w+\s*:|default\s*:)", cinner):
        if m.group(0) == "{":
            d += 1
        elif m.group(0) == "}":
            d -= 1
        elif d == 0:
            lab = (
                "default"
                if m.group(0).startswith("default")
                else re.match(r"case\s+(\w+)", m.group(0)).group(1)
            )
            toks.append((m.start(), m.end(), lab))
    out, i = [], 0
    while i < len(toks):
        labs, start, j = [toks[i][2]], toks[i][0], i
        while j + 1 < len(toks) and not cinner[toks[j][1] : toks[j + 1][0]].strip():
            j += 1
            labs.append(toks[j][2])
        end = toks[j + 1][0] if j + 1 < len(toks) else len(inner)
        out.append((labs, inner[start:end]))
        i = j + 1
    tail = body[se + 1 :]
    return s, e, preamble, out, tail


def chip_values():
    return {
        m.group(1): int(m.group(2))
        for m in re.finditer(
            r"#define (_FLASH_\w+)\s+(\d+)\s*$", git_show("HEAD", HDR), re.MULTILINE
        )
    }


def harness(old_text, new_text, chips, mode):
    regs = sorted(set(re.findall(r"MCU_FF[0-9A-F]{2}_\w+", old_text + new_text)))
    defs = "\n".join(f"#define {k} {v}" for k, v in chips.items())
    reg_objs = "\n".join(
        f"Reg {r}{{{int(re.match(r'MCU_FF([0-9A-F]{2})', r).group(1), 16)}}};"
        for r in regs
    )
    info = "; ".join(
        f"unsigned char {f}"
        for f in [
            "ucIDCheck1OpCode",
            "ucIDCheck1_ID0",
            "ucIDCheck1_ID1",
            "ucIDCheck1_ID2",
            "ucIDCheck2OpCode",
            "ucIDCheck2_ID0",
            "ucIDCheck2_ID1",
            "ucIDCheck2_ID2",
            "ucWRENOpCode",
            "ucWRDisOpCode",
            "ucPageEraseOpCode",
            "ucUnprotectWRSR",
            "ucProtectWRSR",
        ]
    )
    return f"""
#include <cstdio>
#include <cstdint>
#include <vector>
#include <array>
#include <map>
#include <string>
typedef unsigned char BYTE; typedef unsigned char bit; typedef unsigned short WORD;
#define __code
#define _FALSE 0
#define _TRUE 1
#define _RDSR_OPCODE 0x05
#define _RDCR_OPCODE 0x15
#define _BIT0 0x01
#define _BIT1 0x02
#define _BIT2 0x04
#define _BIT3 0x08
#define _BIT4 0x10
#define _BIT5 0x20
#define _BIT6 0x40
#define _BIT7 0x80
#define _WRITE_SR_MODE_SEL 2
#define _CKCON_MCU_SLOW_CYCLE 5
#define AWTO_WDT_S_WREN 6
#define AWTO_WDT_FEED(x) ev(100, x, 0, 0)
{defs}
typedef std::array<int, 4> Ev;
static std::vector<Ev> tr;
static void ev(int a, int b, int c, int d) {{ tr.push_back({{a, b, c, d}}); }}
struct Reg {{ int id; Reg& operator=(unsigned v) {{ ev(1, id, v, 0); return *this; }} }};
{reg_objs}
static void mcu_set(Reg& r, unsigned v, int ck) {{ ev(2, r.id, v, ck); }}
#define MCU_SET_BYTE_WITH_CKCON(addr, x, ck) mcu_set(addr, x, ck)
struct Info {{ {info}; }};
static Info tFlashInformation[256];
static BYTE g_ucFlashType;
#define _AWTO_FLASH_IDX g_ucFlashType
static int rdmode, g_b, g_p;
void ScalerFlashSetWRSR(BYTE a, BYTE s) {{ ev(10, a, s, 0); }}
void ScalerFlashSet2ByteWRSR(BYTE a, BYTE b, BYTE s) {{ ev(11, a, b, s); }}
void ScalerFlashSet2ByteWRSRonebyone(BYTE a, BYTE b, BYTE s) {{ ev(12, a, b, s); }}
void ScalerFlashSet2ndWRSR(BYTE a, BYTE s) {{ ev(13, a, s, 0); }}
void ScalerFlashSet3rdWRSR(BYTE a, BYTE s) {{ ev(14, a, s, 0); }}
void ScalerFlashSet4thWRSR(BYTE a, BYTE s) {{ ev(15, a, s, 0); }}
BYTE ScalerFlashReadSR(BYTE op) {{ ev(20, op, 0, 0); return rdmode == 0 ? (g_b * 7 + g_p * 3 + op) & 255 : (rdmode == 1 ? 0xA5 : 0x5A); }}
static void fill(int seed) {{
    for (int i = 0; i < 256; i++) {{ unsigned char* q = (unsigned char*)&tFlashInformation[i];
        for (unsigned j = 0; j < sizeof(Info); j++) q[j] = (i * 13 + j * 29 + seed * 71) & 255; }}
}}
void old_WREN(BYTE ucBank, BYTE ucPage);
{old_text}
#include "new_wren.inc"
{mode}
"""


MAIN_DUMP = r"""
int main(int argc, char** argv) {
    std::map<std::vector<Ev>, int> intern; std::vector<std::vector<Ev>> traces;
    FILE* f = fopen(argv[1], "wb");
    int runs[3][2] = {{1, 0}, {2, 1}, {1, 2}};
    for (auto& r : runs) {
        fill(r[0]); rdmode = r[1];
        for (int c = 0; c < 256; c++) for (int b = 0; b < 256; b++) for (int p = 0; p < 256; p++) {
            g_ucFlashType = c; g_b = b; g_p = p; tr.clear(); old_WREN(b, p);
            auto it = intern.find(tr); int id;
            if (it == intern.end()) { id = traces.size(); intern[tr] = id; traces.push_back(tr); } else id = it->second;
            uint32_t v = id; fwrite(&v, 4, 1, f);
        }
    }
    fclose(f);
    FILE* t = fopen(argv[2], "w");
    for (size_t i = 0; i < traces.size(); i++) { fprintf(t, "%zu", i); for (auto& e : traces[i]) fprintf(t, " %d,%d,%d,%d", e[0], e[1], e[2], e[3]); fprintf(t, "\n"); }
    fclose(t);
    return 0;
}
"""

MAIN_PROOF = r"""
int main() {
    long cells = 0, bad = 0;
    int runs[3][2] = {{1, 0}, {2, 1}, {1, 2}};
    for (auto& r : runs) {
        fill(r[0]); rdmode = r[1];
        for (int c = 0; c < 256; c++) for (int b = 0; b < 256; b++) for (int p = 0; p < 256; p++) {
            g_ucFlashType = c; g_b = b; g_p = p;
            tr.clear(); old_WREN(b, p); std::vector<Ev> a = tr;
            tr.clear(); ScalerFlashWREN(b, p);
            cells++;
            if (a != tr) { if (bad++ < 5) printf("MISMATCH chip %d bank %d page %d (old %zu ev, new %zu ev)\n", c, b, p, a.size(), tr.size()); }
        }
    }
    printf("cells=%ld mismatches=%ld\n", cells, bad);
    return bad != 0;
}
"""


def build_run(old_func, new_func, mode_main, args, tag):
    SCRATCH.mkdir(parents=True, exist_ok=True)
    chips = chip_values()
    old_text = old_func.replace(SIG, "void old_WREN(BYTE ucBank, BYTE ucPage)", 1)
    (SCRATCH / "new_wren.inc").write_text(new_func)
    cpp = SCRATCH / f"{tag}.cpp"
    cpp.write_text(harness(old_text, new_func, chips, mode_main))
    exe = SCRATCH / tag
    r = subprocess.run(
        ["g++", "-O1", "-w", "-I", str(SCRATCH), "-o", str(exe), str(cpp)],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode:
        raise SystemExit(f"g++ failed ({tag}):\n{r.stderr[:3000]}")
    return subprocess.run(
        [str(exe), *map(str, args)], capture_output=True, text=True, check=False
    )


def generate(ref):
    src = git_show(ref, SRC)
    s, e, preamble, groups, tail = parse(src)
    old_func = src[s : e + 1]
    chips = chip_values()
    dump, txt = SCRATCH / "dump.bin", SCRATCH / "traces.txt"
    SCRATCH.mkdir(parents=True, exist_ok=True)
    stub_new = f"{SIG}\n{{\n}}\n"  # the dump harness needs the symbol only
    r = build_run(old_func, stub_new, MAIN_DUMP, [dump, txt], "dump")
    if r.returncode:
        raise SystemExit(f"dump run failed: {r.stderr[:500]}")
    traces = {}
    for ln in txt.read_text().splitlines():
        a = ln.split()
        traces[int(a[0])] = [tuple(int(x) for x in q.split(",")) for q in a[1:]]
    ids = np.fromfile(dump, dtype=np.uint32).reshape(3, 256, 256, 256)
    same_runs = (ids[0] == ids[1]).all(axis=(1, 2)) & (ids[0] == ids[2]).all(
        axis=(1, 2)
    )
    wdt, tail_ev = (100, 6, 0, 0), None
    table_chips, outlier_labels = {}, []
    for labs, text in groups:
        for lab in labs:
            if lab == "default" or lab not in chips:
                continue
            c = chips[lab]
            ok = bool(same_runs[c])
            uniq = np.unique(ids[0][c]) if ok else []
            mid = {}
            for u in uniq:
                t = traces[int(u)]
                if len(t) != 4 or t[0] != wdt or t[1][0] not in FUNCS:
                    ok = False
                    break
                if tail_ev is None:
                    tail_ev = t[2:]
                if t[2:] != tail_ev:
                    ok = False
                    break
                mid[int(u)] = t[1]
            if not ok:
                outlier_labels.append(lab)
                continue
            kinds = {(m[0], m[3] if m[0] in (11, 12) else m[2]) for m in mid.values()}
            if len(kinds) != 1:
                outlier_labels.append(lab)
                continue
            func, mode = next(iter(kinds))
            w = np.zeros((256, 256), dtype=np.int32)
            w1 = np.zeros((256, 256), dtype=np.int32)
            for u, m in mid.items():
                mask = ids[0][c] == u
                w[mask] = m[1]
                w1[mask] = m[2] if func in (11, 12) else 0
            table_chips[lab] = (c, func, mode, w, w1)
    kinds, tables, chip_kind, chip_first, rows_out = [], {}, {}, {}, []
    for lab, (c, func, mode, w, w1) in sorted(
        table_chips.items(), key=lambda x: x[1][0]
    ):
        k = (func, mode)
        if k not in kinds:
            kinds.append(k)
        key = (func, mode, w.tobytes(), w1.tobytes())
        if key not in tables:
            rows = compress(w, w1)
            tables[key] = len(rows_out)
            rows_out += rows
        chip_kind[c] = kinds.index(k) + 1
        chip_first[c] = tables[key]
    say(
        f"{len(table_chips)} table chips, {len(tables)} distinct tables, {len(rows_out)} rows;"
        f" outlier chips: {len(outlier_labels)}"
    )
    # the outlier switch keeps its original text for every group that holds no table chip, and the labels of
    # mixed groups that stay outliers
    keep = [
        text.rstrip("\n")
        for labs, text in groups
        if all(x == "default" or x in outlier_labels or x not in chips for x in labs)
    ]
    emit(ref, preamble, tail, kinds, rows_out, chip_kind, chip_first, keep, chips)
    return len(table_chips), len(rows_out), outlier_labels


def compress(w, w1):
    """rows (bank_lo, bank_hi, page_lo, page_hi, wrsr, wrsr1) covering bank 0..255 x page 0..255 once"""
    per_bank = []
    for b in range(256):
        runs, p = [], 0
        while p < 256:
            q = p
            while q + 1 < 256 and w[b][q + 1] == w[b][p] and w1[b][q + 1] == w1[b][p]:
                q += 1
            runs.append((p, q, int(w[b][p]), int(w1[b][p])))
            p = q + 1
        per_bank.append(tuple(runs))
    rows, b = [], 0
    while b < 256:
        e = b
        while e + 1 < 256 and per_bank[e + 1] == per_bank[b]:
            e += 1
        rows += [(b, e, *r) for r in per_bank[b]]
        b = e + 1
    return rows


def emit(ref, preamble, tail, kinds, rows, chip_kind, chip_first, keep, chips):
    kind_arr = [chip_kind.get(i, 0) for i in range(chips["_FLASH_TYPE_END"])]
    first_arr = [chip_first.get(i, 0) for i in range(chips["_FLASH_TYPE_END"])]
    lines = [
        f"// generated by scripts/gen_flash_wren.py from ScalerFlashWREN at {ref}: do not edit (#296)",
        "typedef struct",
        "{",
        "    BYTE ucBankLo;",
        "    BYTE ucBankHi;",
        "    BYTE ucPageLo;",
        "    BYTE ucPageHi;",
        "    BYTE ucWRSR;",
        "    BYTE ucWRSR1;",
        "} StructFlashWrenRow;",
        "",
        "static StructFlashWrenRow __code tFlashWrenRow[] =",
        "{",
    ]
    lines += [f"    {{{', '.join(str(x) for x in r)}}}," for r in rows]
    lines += [
        "};",
        "",
        f"static BYTE __code tFlashWrenKind[{chips['_FLASH_TYPE_END']}] =",
        "{",
    ]
    lines += [
        f"    {', '.join(str(x) for x in kind_arr[i : i + 16])},"
        for i in range(0, len(kind_arr), 16)
    ]
    lines += [
        "};",
        "",
        f"static WORD __code tFlashWrenFirst[{chips['_FLASH_TYPE_END']}] =",
        "{",
    ]
    lines += [
        f"    {', '.join(str(x) for x in first_arr[i : i + 16])},"
        for i in range(0, len(first_arr), 16)
    ]
    lines += [
        "};",
        "",
        SIG,
        "{" + preamble.rstrip() + "",
        "    BYTE ucKind = 0;",
        "    WORD usRow = 0;",
        "",
    ]
    lines += ["    // Clear watch dog", "    AWTO_WDT_FEED(AWTO_WDT_S_WREN);", ""]
    lines += [
        "    if(g_ucFlashType < _FLASH_TYPE_END)",
        "    {",
        "        ucKind = tFlashWrenKind[g_ucFlashType];",
        "        usRow = tFlashWrenFirst[g_ucFlashType];",
        "    }",
        "",
        "    if(ucKind != 0)",
        "    {",
        "        while((ucBank < tFlashWrenRow[usRow].ucBankLo) || (ucBank > tFlashWrenRow[usRow].ucBankHi) ||",
        "              (ucPage < tFlashWrenRow[usRow].ucPageLo) || (ucPage > tFlashWrenRow[usRow].ucPageHi))",
        "        {",
        "            usRow++;",
        "        }",
        "",
        "        ucWRSR = tFlashWrenRow[usRow].ucWRSR;",
        "        ucWRSR1 = tFlashWrenRow[usRow].ucWRSR1;",
        "",
        "        switch(ucKind)",
        "        {",
    ]
    for i, (func, mode) in enumerate(kinds, 1):
        args = "ucWRSR" if func == 10 else "ucWRSR, ucWRSR1"
        lines += [
            f"            case {i}:",
            "",
            f"                {FUNCS[func]}({args}, {MODE_TXT[mode]});",
            "                break;",
            "",
        ]
    lines += [
        "            default:",
        "                break;",
        "        }",
        "    }",
        "    else",
        "    {",
        "        switch(g_ucFlashType)",
        "        {",
    ]
    lines += [
        "\n".join(("    " + ln) if ln.strip() else ln for ln in k.split("\n")) + "\n"
        for k in keep
    ]
    lines += ["        }", "    }", ""]
    lines += [tail.strip("\n"), "}", ""]
    out = ROOT / GEN
    out.write_text("\n".join(lines))
    say(
        f"wrote {GEN}: {len(rows)} rows, {len(kinds)} kinds, {sum(1 for x in kind_arr if x)} table chips of {len(kind_arr)}"
    )


def proof(ref):
    src = git_show(ref, SRC)
    s, e, *_ = parse(src)
    old_func = src[s : e + 1]
    new_func = (ROOT / GEN).read_text()
    r = build_run(old_func, new_func, MAIN_PROOF, [], "proof")
    say(r.stdout.strip() or r.stderr[:500])
    return r.returncode


def apply():
    """replace the function in the working tree's ScalerCommonNVRam.c by the include of the generated file"""
    p = ROOT / SRC
    t = p.read_text()
    s, e, *_ = parse(t)
    p.write_text(t[:s] + '#include "ScalerCommonNVRamWren_gen.inc"' + t[e + 1 :])
    say(f"{SRC}: function replaced by the include")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=("gen", "proof", "apply"))
    ap.add_argument("--ref", default=DEFAULT_REF)
    a = ap.parse_args()
    if a.cmd == "apply":
        apply()
        return 0
    if a.cmd == "gen":
        generate(a.ref)
        return 0
    return proof(a.ref)


if __name__ == "__main__":
    sys.exit(main())
