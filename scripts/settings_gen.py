#!/usr/bin/env python3
"""Generate everything that comes from the settings registry (awto-ddc#67): one table, no hand-kept copies.

usage: settings_gen.py [--rtdfw DIR] [--tree DIR] [--check]
  Reads  $RTDFW/settings/registry.tsv + pages.tsv (format: header of registry.tsv).
  Writes $RTDFW/awto/settings/set_gen.h, set_table.c   (clean firmware: rows, labels, pages, VCP map, apply dispatch)
         $TREE/fw/sdk/Project/Header/AwtoSetIds.h   (firmware glue: AWTO_SET_<NAME> ids, only with --tree)
         scripts/settings_table.py                     (host: dev.py settings get|set|list)
         docs/settings.md                              (the list for people)
  --check: write nothing, exit 1 when any output differs from what is on disk (gate).
  --host-out P: only the host table, to P (wb_build: tmp/fw/<stem>.settings_table.py, the image's registry); host tools
  load it instead of scripts/settings_table.py when $AWTO_SETTINGS_TABLE names it (fw_gates sets it per image).
  Schema = CRC-16 of the NV rows' (id, type, min, max): it changes when a stored row changes meaning; the record is
  id-tagged, so rows that still exist keep their values across it.
Log: ./tmp/logs/settings_gen.log
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

TYPES = {"bool": 0, "enum": 1, "int": 2, "action": 3}
UNITS = {"none": 0, "percent": 1, "ms": 2, "s": 3, "step": 4, "hz": 5, "dhz": 6}
UNIT_TXT = {"none": "", "percent": "%", "ms": "ms", "s": "s", "step": "", "hz": "Hz", "dhz": "Hz"}
FLAGS = {"nv": 0x01, "live": 0x02, "factory": 0x04, "risky": 0x08, "ro": 0x10, "inert": 0x20, "reboot": 0x40, "sdk": 0x80}
COLS = ["id", "name", "type", "unit", "group", "flags", "min", "max", "step", "default", "nv_slot", "vcp", "apply",
        "label", "options", "note"]
LABEL_MAX = 22                      # menu: label column width (menu.c LABEL_W)
OPTION_MAX = 14                     # menu: value column width (menu.c VALUE_W)


def repo_root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                       cwd=Path(__file__).parent, check=False)
    return Path(r.stdout.strip()) if r.returncode == 0 else Path(__file__).resolve().parents[1]


ROOT = repo_root()
LOG = ROOT / "tmp/logs/settings_gen.log"


def say(s: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(time.strftime("%Y-%m-%dT%H:%M:%S%z ") + s + "\n")
    print(s, flush=True)


def crc16(data: bytes) -> int:
    c = 0xFFFF
    for b in data:
        c ^= b << 8
        for _ in range(8):
            c = ((c << 1) ^ 0x1021) if c & 0x8000 else c << 1
            c &= 0xFFFF
    return c


def parse(rtdfw: Path):
    rows, pages = [], []
    for ln, line in enumerate((rtdfw / "settings/registry.tsv").read_text().splitlines(), 1):
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split("\t")
        f += [""] * (len(COLS) - len(f))
        r = dict(zip(COLS, f))
        r["line"] = ln
        r["id"] = int(r["id"])
        for k in ("min", "max", "step", "default"):
            r[k] = int(r[k], 0)
        r["flagset"] = [x for x in r["flags"].split(",") if x and x != "-"]
        r["vcpv"] = 0 if r["vcp"] in ("", "-") else int(r["vcp"], 16)
        r["opts"], r["optv"] = [], []
        if r["options"] not in ("", "-"):
            for i, o in enumerate(r["options"].split("|")):
                lab, _, v = o.partition("=")
                r["opts"].append(lab)
                r["optv"].append(int(v, 0) if v else i)
        rows.append(r)
    for line in (rtdfw / "settings/pages.tsv").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        g, title, parent, *_ = line.split("\t") + [""]
        pages.append(dict(group=g, title=title, parent=parent))
    return rows, pages


def validate(rows, pages):
    err = []
    ids, names = set(), set()
    groups = {p["group"] for p in pages}
    for r in rows:
        w = f"registry.tsv:{r['line']} {r['name']}"
        if not 1 <= r["id"] <= 255:
            err.append(f"{w}: id {r['id']} outside 1..255")
        if r["id"] in ids or r["name"] in names:
            err.append(f"{w}: duplicate id or name")
        ids.add(r["id"]); names.add(r["name"])
        if r["type"] not in TYPES or r["unit"] not in UNITS:
            err.append(f"{w}: type/unit")
        bad = [x for x in r["flagset"] if x not in FLAGS]
        if bad:
            err.append(f"{w}: flags {bad}")
        if r["group"] not in groups:
            err.append(f"{w}: group {r['group']} not in pages.tsv")
        if not (r["min"] <= r["default"] <= r["max"]) or r["step"] < 1 or r["min"] < 0 or r["max"] > 32767:
            err.append(f"{w}: range {r['min']}..{r['max']} step {r['step']} default {r['default']}")
        if r["type"] == "enum" and len(r["opts"]) != r["max"] - r["min"] + 1:
            err.append(f"{w}: {len(r['opts'])} options for range {r['min']}..{r['max']}")
        if r["type"] == "bool" and (r["min"], r["max"]) != (0, 1):
            err.append(f"{w}: bool range")
        if len(r["label"]) > LABEL_MAX or any(len(o) > OPTION_MAX for o in r["opts"]):
            err.append(f"{w}: label > {LABEL_MAX} or option > {OPTION_MAX} chars")
        if any(not 0x20 <= ord(c) <= 0x7E for c in r["label"] + "".join(r["opts"])):
            err.append(f"{w}: non-ASCII text (font is ASCII 0x20..0x7E)")
        if "nv" in r["flagset"] and r["type"] == "action":
            err.append(f"{w}: an action is not stored")
        if "sdk" in r["flagset"] and "nv" not in r["flagset"]:
            err.append(f"{w}: sdk (SDK store field) needs nv")
    vcps = [r["vcpv"] for r in rows if r["vcpv"]]
    if len(vcps) != len(set(vcps)):
        err.append("duplicate VCP code")
    if any(0xE0 <= v <= 0xE5 for v in vcps):
        err.append("VCP 0xE0..0xE5 are ours (paged pair, schema, command, menu)")
    return err


def page_tree(rows, pages):
    """entries per page: sub-pages (0x80 | page) then rows in registry order"""
    gi = {p["group"]: i for i, p in enumerate(pages)}
    out = []
    for i, p in enumerate(pages):
        subs = [0x80 | j for j, q in enumerate(pages) if q["parent"] == p["group"]]
        items = [k for k, r in enumerate(rows) if r["group"] == p["group"]]
        out.append(dict(title=p["title"], parent=0xFF if p["parent"] == "-" else gi[p["parent"]], entries=subs + items))
    return out


PROTO_VCP = {0x02: "", 0xC8: "", 0xC9: "", 0xDF: "", 0xE0: "", 0xE1: "", 0xE2: "", 0xE3: "", 0xE4: "", 0xE5: ""}   # vcp.c


def caps_string(rows) -> str:
    """MCCS 2.2 capabilities: every registry VCP code (enum rows with their values) plus the protocol codes of vcp.c."""
    codes = dict(PROTO_VCP)
    for r in rows:
        if r["vcpv"]:
            codes[r["vcpv"]] = "(" + " ".join(f"{v:02X}" for v in r["optv"]) + ")" if r["type"] == "enum" else ""
    vcp = " ".join(f"{k:02X}{v}" for k, v in sorted(codes.items()))
    return f"(prot(monitor)type(LCD)model(awto-mon)cmds(01 02 03 0C F3)vcp({vcp})mccs_ver(2.2))"


def schema(rows) -> int:
    b = bytearray()
    for r in sorted((r for r in rows if "nv" in r["flagset"]), key=lambda r: r["id"]):
        b += bytes([r["id"], TYPES[r["type"]]]) + r["min"].to_bytes(2, "little") + r["max"].to_bytes(2, "little")
    return crc16(bytes(b)) & 0x7FFF


def aux_rows(rows):
    """stored rows without an SDK store field: the integrator keeps them in its own items of the SDK store (#151)"""
    return [r for r in rows if "nv" in r["flagset"] and "sdk" not in r["flagset"]]


def aux_bytes(rows) -> int:
    return 1 + sum(2 if r["type"] == "int" else 1 for r in aux_rows(rows))


def cstr(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '\\0"'


def gen_c(rows, pages, tree, sch):
    applies = sorted({r["apply"] for r in rows if r["apply"] not in ("", "-")})
    ap = {a: i + 1 for i, a in enumerate(applies)}
    text, ofs = [], 0
    lab_ofs, opt_ofs = {}, {}

    def add(s):
        nonlocal ofs
        o = ofs
        text.append(s); ofs += len(s) + 1
        return o
    for r in rows:
        lab_ofs[r["id"]] = add(r["label"])
        opt_ofs[r["id"]] = add(r["opts"][0]) if r["opts"] else 0xFFFF
        for o in r["opts"][1:]:
            add(o)
    title_ofs = [add(p["title"]) for p in tree]
    hdr = ["/* set_gen.h: GENERATED by awto-ddc scripts/settings_gen.py from settings/registry.tsv. Do not edit. */",
           "#ifndef AWTO_SET_GEN_H", "#define AWTO_SET_GEN_H", "#include <stdint.h>", "",
           f"#define SET_COUNT   {len(rows)}u", f"#define SET_PAGES   {len(pages)}u",
           f"#define SET_SCHEMA  0x{sch:04X}u    /* CRC-16 of the NV rows (id, type, min, max) */",
           f"#define SET_NV_COUNT {sum('nv' in r['flagset'] for r in rows)}u", f"#define SET_TEXT_LEN {ofs}u",
           f"#define SET_AUX_MAX {aux_bytes(rows)}u    /* aux block: check byte + stored rows without an SDK field (awto-ddc#151) */", ""]
    hdr += [f"#define SET_ID_{r['name'].upper():<20} {r['id']}u" for r in rows]
    hdr += [""] + [f"#define SET_PAGE_{p['group'].upper():<16} {i}u" for i, p in enumerate(pages)]
    hdr += [""] + [f"#define AP_{a.upper():<20} {i}u" for a, i in ap.items()]
    hdr += ["", "/* apply functions: integrator (firmware side), one per registry 'apply' name */"]
    hdr += [f"void set_ap_{a}(uint8_t id, int16_t v);" for a in applies]
    hdr += ["", "#endif", ""]
    c = ["/* set_table.c: GENERATED by awto-ddc scripts/settings_gen.py from settings/registry.tsv + pages.tsv.",
         " * Do not edit. Const tables are only read in this file (they stay in its bank); callers get copies. */",
         "#include <stdint.h>", '#include "cc.h"', '#include "settings.h"', "",
         "static const struct setting __code tab[SET_COUNT] = {",
         "    /* id type unit group flags min max step def vcp apply label opts */"]
    gi = {p["group"]: i for i, p in enumerate(pages)}
    for r in rows:
        fl = sum(FLAGS[x] for x in r["flagset"])
        c.append(f"    {{{r['id']:3}, {TYPES[r['type']]}, {UNITS[r['unit']]}, {gi[r['group']]:2}, 0x{fl:02X}, {r['min']}, {r['max']}, "
                 f"{r['step']}, {r['default']}, 0x{r['vcpv']:02X}, {ap.get(r['apply'], 0)}, {lab_ofs[r['id']]}u, "
                 f"0x{opt_ofs[r['id']]:04X}u}},  /* {r['name']} */")
    c.append("};\n")
    maxid = max(r["id"] for r in rows)
    idx = [0xFF] * (maxid + 1)
    for k, r in enumerate(rows):
        idx[r["id"]] = k
    c.append(f"static const uint8_t __code id2idx[{maxid + 1}] = {{")
    for i in range(0, len(idx), 16):
        c.append("    " + ", ".join(f"0x{v:02X}" for v in idx[i:i + 16]) + ",")
    c.append("};\n")
    c.append("static const char __code txt[] =")
    line = ""
    for s in text:
        piece = cstr(s)
        if len(line) + len(piece) > 110:
            c.append("    " + line); line = ""
        line += piece
    c.append("    " + line + ";\n")
    vmap = [(k, r) for k, r in enumerate(rows) if r["opts"] and r["optv"] != list(range(len(r["opts"])))]
    c.append("/* enum rows whose VCP values are not the option index: (row, option, vcp value) */")
    c.append(f"static const uint8_t __code vopt[{max(1, sum(len(r['opts']) for _, r in vmap))}][3] = {{")
    for k, r in vmap:
        for i, v in enumerate(r["optv"]):
            c.append(f"    {{{k}, {i}, 0x{v:02X}}},")
    if not vmap:
        c.append("    {0xFF, 0, 0},")
    c.append("};\n")
    vrows = sorted((r["vcpv"], k) for k, r in enumerate(rows) if r["vcpv"])
    caps = caps_string(rows)
    c.append(f"/* DDC/CI capabilities ({len(caps)} chars), from the vcp column; read by set_caps_at only */")
    c.append("static const char __code caps[] =")
    for i in range(0, len(caps), 100):
        c.append("    " + cstr(caps[i:i + 100])[:-3] + '"' + (";" if i + 100 >= len(caps) else ""))
    c.append("")
    c.append(f"static const uint8_t __code vcode[{len(vrows)}][2] = {{")
    c += [f"    {{0x{v:02X}, {k}}}," for v, k in vrows]
    c.append("};\n")
    ents = [e for t in tree for e in t["entries"]]
    c.append(f"static const uint8_t __code pent[{max(1, len(ents))}] = {{")
    for i in range(0, len(ents), 16):
        c.append("    " + ", ".join(f"0x{v:02X}" for v in ents[i:i + 16]) + ",")
    c.append("};")
    c.append("static const uint8_t __code pinfo[SET_PAGES][3] = {    /* first entry, entries, parent */")
    pos = 0
    for t in tree:
        c.append(f"    {{{pos}, {len(t['entries'])}, 0x{t['parent']:02X}}},  /* {t['title']} */")
        pos += len(t["entries"])
    c.append("};")
    c.append(f"static const uint16_t __code ptitle[SET_PAGES] = {{{', '.join(f'{o}u' for o in title_ofs)}}};\n")
    c += ["uint8_t set_idx(uint8_t id)", "{", f"    return id <= {maxid} ? id2idx[id] : 0xFF;", "}", "",
          "void set_row(uint8_t idx, struct setting __xdata *out)    /* field copies: no pointer into tab (banker #16) */",
          "{"] + [f"    out->{f} = tab[idx].{f};" for f in
                  ("id", "type", "unit", "group", "flags", "min", "max", "step", "def", "vcp", "apply", "label", "opts")] + [
          "}", "",
          "/* one reader per const table: the bank layout keeps a table with its only reader (else it must go to common) */",
          "static char tx_at(uint16_t ofs)", "{", "    return txt[ofs];", "}", "",
          "static uint8_t vo_at(uint8_t i, uint8_t k)", "{", "    return vopt[i][k];", "}", "",
          "static uint8_t pi_at(uint8_t page, uint8_t k)", "{", "    return pinfo[page][k];", "}", "",
          "uint8_t set_text(uint16_t ofs, char __xdata *dst, uint8_t max)", "{", "    uint8_t n = 0;", "",
          "    if (ofs >= SET_TEXT_LEN) {", "        dst[0] = 0;", "        return 0;", "    }",
          "    while (n + 1 < max && tx_at(ofs + n) != 0) {", "        dst[n] = tx_at(ofs + n);", "        n++;", "    }",
          "    dst[n] = 0;", "    return n;", "}", "",
          "uint16_t set_opt(uint16_t opts, uint8_t k)", "{",
          "    while (k != 0 && opts < SET_TEXT_LEN) {", "        if (tx_at(opts++) == 0)", "            k--;", "    }",
          "    return opts;", "}", "",
          "uint8_t set_vcp_opt(uint8_t idx, int16_t v)", "{", "    uint8_t i;", "",
          "    for (i = 0; i < sizeof vopt / 3; i++)", "        if (vo_at(i, 0) == idx && vo_at(i, 1) == (uint8_t)v)",
          "            return vo_at(i, 2);", "    return (uint8_t)v;", "}", "",
          "int16_t set_opt_from_vcp(uint8_t idx, uint8_t vcpv)", "{", "    uint8_t i, mapped = 0;", "",
          "    for (i = 0; i < sizeof vopt / 3; i++) {", "        if (vo_at(i, 0) != idx)", "            continue;",
          "        mapped = 1;", "        if (vo_at(i, 2) == vcpv)", "            return vo_at(i, 1);", "    }",
          "    return mapped ? -1 : (int16_t)vcpv;", "}", "",
          f"uint16_t set_caps_len(void)", "{", f"    return {len(caps)}u;", "}", "",
          "char set_caps_at(uint16_t i)", "{", "    return caps[i];", "}", "",
          "uint8_t set_vcp_row(uint8_t vcp)", "{", "    uint8_t i;", "",
          "    for (i = 0; i < sizeof vcode / 2; i++)", "        if (vcode[i][0] == vcp)", "            return vcode[i][1];",
          "    return 0xFF;", "}", "",
          "uint8_t set_page_title(uint8_t page, char __xdata *dst, uint8_t max)", "{",
          "    return set_text(ptitle[page], dst, max);", "}", "",
          "uint8_t set_page_parent(uint8_t page)", "{", "    return pi_at(page, 2);", "}", "",
          "uint8_t set_page_n(uint8_t page)", "{", "    return pi_at(page, 1);", "}", "",
          "uint8_t set_page_entry(uint8_t page, uint8_t k)", "{", "    return pent[pi_at(page, 0) + k];", "}", "",
          "void set_apply_call(uint8_t ap, uint8_t id, int16_t v)", "{", "    switch (ap) {"]
    for a, i in ap.items():
        c += [f"    case AP_{a.upper()}:", f"        set_ap_{a}(id, v);", "        break;"]
    c += ["    default:", "        break;", "    }", "}", ""]
    inc = ["// AwtoSetIds.h: GENERATED by awto-ddc scripts/settings_gen.py from awto-rtdfw settings/registry.tsv. Do not edit.",
           "// Firmware glue (fw/settings/settings_glue.c) and AWTO_SET(NAME) readers name rows by these ids.",
           "#ifndef AWTO_SET_IDS_H", "#define AWTO_SET_IDS_H"]
    inc += [f"#define AWTO_SET_{r['name'].upper():<20} {r['id']}" for r in rows]
    # sdk rows: defaults for the SDK store's power-on table (g_stOSDDefaultData), so the registry stays the one default (#176)
    inc += ["#define AWTO_PCT_TO_255(p)           ((BYTE)(((WORD)(p) * 255) / 100))   // SDK store field of a percent row: 0..255"]
    inc += [f"#define AWTO_SET_DEF_{r['name'].upper():<16} {r['default']}" for r in rows if "sdk" in r["flagset"]]
    inc += [f"#define AWTO_SET_SCHEMA              0x{sch:04X}", f"#define AWTO_SET_AUX_MAX             {aux_bytes(rows)}", "#endif", ""]
    return "\n".join(hdr), "\n".join(c), "\n".join(inc)


REDIRECT = """import os as _os
if _os.environ.get("AWTO_SETTINGS_TABLE"):          # image-matched table (settings_gen --host-out; fw_gates sets it)
    exec(compile(open(_os.environ["AWTO_SETTINGS_TABLE"]).read(), _os.environ["AWTO_SETTINGS_TABLE"], "exec"))
"""


def gen_host(rows, pages, tree, sch, redirect=True):
    gi = {p["group"]: i for i, p in enumerate(pages)}
    out = ['"""settings_table.py: GENERATED by scripts/settings_gen.py from awto-rtdfw settings/registry.tsv. Do not edit."""',
           f"SCHEMA = 0x{sch:04X}", f"CAPS = {caps_string(rows)!r}", "ROWS = ["]
    for r in rows:
        d = dict(id=r["id"], name=r["name"], type=r["type"], unit=r["unit"], group=r["group"], flags=r["flagset"],
                 min=r["min"], max=r["max"], step=r["step"], default=r["default"], vcp=r["vcpv"] or None,
                 apply=None if r["apply"] in ("", "-") else r["apply"], label=r["label"], options=r["opts"],
                 option_vcp=r["optv"], note=r["note"], index=len(out) - 3, page=gi[r["group"]])
        out.append(f"    {d!r},")
    out.append("]")
    out.append("PAGES = [")
    for p, t in zip(pages, tree):
        out.append(f"    {dict(group=p['group'], title=p['title'], parent=t['parent'], entries=t['entries'])!r},")
    out.append("]")
    out.append("BY_NAME = {r['name']: r for r in ROWS}")
    out.append("BY_ID = {r['id']: r for r in ROWS}")
    return "\n".join(out) + "\n" + (REDIRECT if redirect else "")


def fmt_range(r):
    if r["type"] == "bool":
        return "off / on"
    if r["type"] == "enum":
        return " / ".join(f"{o}" + (f" (VCP 0x{v:02X})" if r["optv"] != list(range(len(r["opts"]))) else "")
                          for o, v in zip(r["opts"], r["optv"]))
    if r["type"] == "action":
        return "action"
    u = UNIT_TXT[r["unit"]]
    if r["unit"] == "dhz":
        return f"{r['min'] / 10:g}..{r['max'] / 10:g} {u} (0.1 Hz)"
    return f"{r['min']}..{r['max']}" + (f" step {r['step']}" if r["step"] != 1 else "") + (f" {u}" if u else "")


def fmt_default(r):
    if r["type"] == "action" or "ro" in r["flagset"]:
        return "-"
    if r["type"] == "bool":
        return "on" if r["default"] else "off"
    if r["type"] == "enum":
        return r["opts"][r["default"] - r["min"]]
    return f"{r['default']} {UNIT_TXT[r['unit']]}".strip()


def gen_doc(rows, pages, tree, sch):
    n_inert = sum("inert" in r["flagset"] for r in rows)
    out = ["# Settings (generated)", "",
           "GENERATED by `scripts/settings_gen.py` from `awto-rtdfw/settings/registry.tsv` + `pages.tsv` (awto-ddc#67). "
           "Edit the registry, then regenerate; never edit this file.", "",
           f"- {len(rows)} rows, {sum('nv' in r['flagset'] for r in rows)} stored, {n_inert} inert (stored only, "
           f"no firmware function yet; menu: not active), schema `0x{sch:04X}`.",
           "- Menu (front keys, docs/keys.md): MENU opens it; AUTO = enter / edit / confirm, UP / DOWN = move or change, "
           "MENU = back / revert, SOURCE = close from any page.",
           "- Host: `./dev.py settings list|get NAME|set NAME VALUE [--unit N] [--sim BIN]` (debug slave 0x35 mailbox); "
           "`./dev.py menu state|key K|hold KEYS MS|open PAGE|select NAME|set NAME VALUE|get NAME|back|close|walk` "
           "(menu state struct `_menu_diag`, awto-rtdfw menu.h).",
           "- DDC/CI (when Debug link is off): MCCS code per row (column VCP), plus every row by id: "
           "`0xE0` = select id, `0xE1` = value, `0xE2` = schema (read), `0xE3` = 1 confirm / 2 save / 3 defaults, "
           "`0xE4` = menu command (op << 8 | arg) / state, `0xE5` = cursor item (read).",
           f"- DDC/CI capabilities (generated): `{caps_string(rows)}`",
           "- Recovery (all defaults): VCP 0x04 or debug test command 0x40 (no key recovery, awto-ddc#132).",
           "- Risky rows (`risky`): applied, then reverted after 15 s unless confirmed (Menu, or VCP 0xE3 = 1).",
           "- Flags: `nv` stored, `live` applied while adjusting, `risky` auto-revert, `reboot` after restart, "
           "`ro` status, `inert` stored only: dimmed with `*` after the label, not changed from the menu (DDC/CI still "
           "stores the value).", ""]
    gi = {p["group"]: i for i, p in enumerate(pages)}
    for i, p in enumerate(pages):
        title = p["title"] if p["parent"] == "-" else f"{pages[gi[p['parent']]]['title']} > {p['title']}"
        out += [f"## {title}", "", "| id | name | label | range | default | flags | VCP | apply | note |",
                "|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            if r["group"] != p["group"]:
                continue
            vcp = f"0x{r['vcpv']:02X}" if r["vcpv"] else "-"
            out.append(f"| {r['id']} | `{r['name']}` | {r['label']} | {fmt_range(r)} | {fmt_default(r)} | "
                       f"{','.join(r['flagset']) or '-'} | {vcp} | "
                       f"{r['apply'] if r['apply'] not in ('', '-') else '-'} | {r['note'].replace('|', '/')} |")
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rtdfw", type=Path, default=Path(os.environ.get("AWTO_RTDFW_REPO", "/mnt/2tb/git/awto-rtdfw")),
                    help="clean tree (default $AWTO_RTDFW_REPO or /mnt/2tb/git/awto-rtdfw)")
    ap.add_argument("--tree", type=Path, help="firmware worktree for fw/sdk/Project/Header/AwtoSetIds.h")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--host-out", type=Path, help="write only the host table here (an image's own: tmp/fw/<stem>.settings_table.py)")
    a = ap.parse_args()
    rows, pages = parse(a.rtdfw)
    err = validate(rows, pages)
    if err:
        for e in err:
            say("ERROR " + e)
        return 2
    tree = page_tree(rows, pages)
    sch = schema(rows)
    if a.host_out:
        a.host_out.write_text(gen_host(rows, pages, tree, sch, redirect=False))
        say(f"settings_gen: host table schema 0x{sch:04X} from {a.rtdfw} -> {a.host_out}")
        return 0
    h, c, inc = gen_c(rows, pages, tree, sch)
    outs = {a.rtdfw / "awto/settings/set_gen.h": h, a.rtdfw / "awto/settings/set_table.c": c,
            ROOT / "scripts/settings_table.py": gen_host(rows, pages, tree, sch),
            ROOT / "docs/settings.md": gen_doc(rows, pages, tree, sch)}
    if a.tree:
        outs[a.tree / "fw/sdk/Project/Header/AwtoSetIds.h"] = inc
    diff = [p for p, t in outs.items() if not p.exists() or p.read_text() != t]
    if a.check:
        for p in diff:
            say(f"STALE {p}")
        return 1 if diff else 0
    for p in diff:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(outs[p])
    say(f"settings_gen: {len(rows)} rows, {len(pages)} pages, schema 0x{sch:04X}; wrote {len(diff)} of {len(outs)} "
        f"({', '.join(p.name for p in diff) or 'all current'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
