#!/usr/bin/env python3
"""OSD cleanup ledger: flash bytes (from the build map) and source lines (from the definitions) per cleanup item, label osd-cleanup.

usage: osd_cleanup_report.py MAP [--out DIR] [--tree DIR]
  MAP: an image map (tmp/fw/<tag>.map). Bytes = sum of the CH_<name> areas an item owns; LOC = lines of the matching function /
  array definitions in the ported SDK (--tree, default awto-ddc-ui: tmp/sdcc-port/src, a build must have run) and our fw/sdcc/*.inc.
  Items are the ITEMS table below (one per issue). Re-run after each cleanup: the numbers are what is left.
Writes OUT/report.md and OUT/report.tsv (default tmp/osd_cleanup/). Log: tmp/logs/osd_cleanup_report.log
"""
import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UI = Path("/mnt/2tb/git/awto-ddc-ui")
LOG = ROOT / "tmp/logs/osd_cleanup_report.log"
CARD_ICONS = r"tFONT1_ICON_(NO_SUPPORT|NO_CABLE|NO_SIGNAL|NO_SIGANL|POWER_SAVIN|AUTO_ADJUST_TEXT|AUTO_COLOR_TEXT|TURN_OFF_PANEL_UN)"
FREEZE_ICONS = r"tFONT1_ICON_FREEZE"
LANG_ICONS = r"tFONT1_ICON_(ENGLISH|CHINESE_T)"
KEEP_ICONS = r"tFONT1_ICON_(INFORMATION|DDCCI|ON|OFF)$"
SRC_ICONS = r"tFONT1_ICON_(INPUT|AUTOSELECT|VGA|DVI|HDMI|DP|MHL|NO_PORT)$"
HOTKEY_ICONS = r"tFONT1_ICON_(D\d|1_DOT_\d)$"           # DP-version hot-key menu (#122); was counted under source-selector

# id, title, areas (regex on map area names, full match), exclude regex, source definitions (regex on names) for LOC
ITEMS = [
    ("logo-stubs", "Remove the 2-byte Realtek logo stubs", [r"tiOSD_REALTEK_1BIT_LOGO\d"], None, [r"tiOSD_REALTEK_1BIT_LOGO\d"]),
    ("card-icons", "Drop the SDK message-card icons (our cards replace those bodies)", [CARD_ICONS + r".*"], None, [CARD_ICONS + r"\w*"]),
    ("freeze-icons", "Drop the freeze icons (_FREEZE_SUPPORT is off)", [FREEZE_ICONS + r".*"], None, [FREEZE_ICONS + r"\w*"]),
    ("chinese-font", "Chinese menu font: optional asset file behind a build flag", [r"tsFontCBodyChinese", r"tsFontWidthChinese", LANG_ICONS + r".*"],
     None, [r"tsFontCBodyChinese", r"tsFontWidthChinese", LANG_ICONS]),
    ("realtek-menu", "Realtek SDK menu: optional (icons + menu code) behind a build flag",
     [r"tFONT1_ICON_.*", r"Menu[A-Z]\w*", r"OsdDispMainMenu\w*", r"tOSD_iREALTEK", r"tOSD_iKEY_\w+", r"OsdDispSliderAndNumber",
      r"OsdDispClear\w*", r"OsdDispAdvance\w*", r"OsdDispSixColor\w*", r"OsdDispMainSubString", r"OsdDispMainOptionIcon"],
     "|".join([CARD_ICONS, FREEZE_ICONS, LANG_ICONS, KEEP_ICONS, SRC_ICONS, HOTKEY_ICONS, r"MenuHotKey\w*"]),
     [r"Menu[A-Z]\w*", r"OsdDispMainMenu\w*", r"OsdDispSliderAndNumber", r"OsdDispAdvance\w*", r"OsdDispSixColor\w*", r"tFONT1_ICON_\w+"]),
    ("factory-menu", "Factory menu: optional behind a build flag", [r"RTDFactory\w*", r"tFONT_FACTORY\w*", r"OperationFactory\w*", r"tFactory\w*"],
     None, [r"RTDFactory\w*", r"tFONT_FACTORY\w*"]),
    ("hotkey-menus", "SDK DDC/CI and DP-version hot-key menus: port or remove",
     [r"OsdDispHotKeyOption\w*", r"MenuHotKey\w*", HOTKEY_ICONS[:-1], r"tFONT1_MAIN_ICON_TABLE_\d"], None,
     [r"OsdDispHotKey\w*", r"MenuHotKey\w*"]),
    ("diag-fonts", "Diagnostic-only fonts (5 of 7): keep, or optional behind a build flag",
     [r"font_blob_(spleen6|spleen5|tamzen5|tamzen6|tamzen7)"], None, []),
    ("sdk-cards", "Port the message cards to the text layer (drop SDK card bodies, proportional font, card windows)",
     [r"OsdDispOsdMessage", r"tsFontCBody0", r"tsFontWidth0", r"OsdPropPutString\w*", r"OsdFontVLC\w*"], None,
     [r"OsdDispOsdMessage", r"OsdPropPutString\w*", r"AwtoCard\w*"]),
    ("prop-strings", "SDK proportional-string helpers behind the info pop-up and cards (go with sdk-cards)",
     [r"OsdPropGet\w*", r"OsdPropSet\w*", r"OsdPropFontDataToSram", r"OsdPropVideoResolution", r"tFONT1_GLOBAL"], None,
     [r"OsdPropGet\w*", r"OsdPropSet\w*", r"OsdPropFontDataToSram", r"OsdPropVideoResolution"]),
    ("source-selector", "Source selector still drawn by the SDK hot-key source menu + port icons",
     [r"OsdDispHotKeySourceMenu\w*", SRC_ICONS[:-1], r"OsdFontVLCLoadInputIcon", r"tFONT1_INPUT_ICON_TABLE"], None,
     [r"OsdDispHotKeySourceMenu\w*"]),
    ("diag-code", "Diagnostics / test code (console, probe, key test, delay cal, test commands)",
     [r"AwtoDiag\w*", r"AwtoProbe\w*", r"AwtoKey(Show|Letter|Log)\w*", r"AwtoOsd(Debug|Key|Gpio)Lines"], None,
     [r"AwtoDiag\w*", r"AwtoProbe\w*", r"AwtoKey(Show|Letter|Log)\w*", r"AwtoOsd(Debug|Key|Gpio)Lines"]),
    ("boot-logo", "Boot logo (our art, SDK names tICON_REALTEK_*)", [r"tICON_REALTEK_1BIT_LOGO\d", r"tAWTO_LOGO_RUNS", r"AwtoLogoDraw", r"OsdDispShowLogo"],
     None, [r"AwtoLogoDraw", r"OsdDispShowLogo"]),
]


def log(s):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def map_areas(path):
    """area name (without CH_) -> bytes."""
    out = {}
    for m in re.finditer(r"^CH_(\S+)\s+[0-9A-F]{8}\s+([0-9A-F]{8}) =", path.read_text(errors="replace"), re.M):
        out[m.group(1)] = int(m.group(2), 16)
    return out


def sources(tree: Path):
    files = []
    for d in (tree / "tmp/sdcc-port/src/User/RTD Series/RTD2014Osd/Code", tree / "tmp/sdcc-port/src/User/RTD Factory/Code"):
        files += sorted(d.glob("*.c"))
    files += sorted((tree / "fw/sdcc").glob("*.inc"))
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import fw_dirs
    files += fw_dirs.our_files(tree)
    return [(f, f.read_text(errors="replace").splitlines()) for f in files if f.exists()]


DEF_RE = re.compile(r"^\s*(?:static\s+)?(?:const\s+)?[A-Za-z_][\w\s\*]*?\b([A-Za-z_]\w*)\s*(\(|\[)")


def definitions(src, pats):
    """(file, name, lines) for every function / array definition whose name fully matches one of pats."""
    rx = re.compile("|".join(f"(?:{p})" for p in pats)) if pats else None
    found = []
    if rx is None:
        return found
    for f, lines in src:
        i = 0
        while i < len(lines):
            m = DEF_RE.match(lines[i])
            if not m or not rx.fullmatch(m.group(1)) or lines[i].rstrip().endswith(";"):
                i += 1
                continue
            depth, j, opened = 0, i, False
            while j < len(lines):
                depth += lines[j].count("{") - lines[j].count("}")
                opened = opened or "{" in lines[j]
                if opened and depth <= 0:
                    break
                j += 1
            found.append((f, m.group(1), j - i + 1))
            i = j + 1
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("map", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "tmp/osd_cleanup")
    ap.add_argument("--tree", type=Path, default=UI, help="firmware tree whose ported SDK + fw/sdcc the LOC come from")
    a = ap.parse_args()
    areas = map_areas(a.map)
    src = sources(a.tree)
    a.out.mkdir(parents=True, exist_ok=True)
    rows, detail = [], []
    for iid, title, pats, excl, defs in ITEMS:
        rx = re.compile("|".join(f"(?:{p})" for p in pats))
        ex = re.compile(excl) if excl else None
        hit = {n: b for n, b in areas.items() if rx.fullmatch(n) and not (ex and ex.match(n))}
        d = definitions(src, defs)
        loc = sum(n for _, _, n in d)
        rows.append((iid, title, sum(hit.values()), len(hit), loc, len(d)))
        detail.append((iid, sorted(hit.items(), key=lambda x: -x[1]), d))
    total = sum(areas.values())
    md = [f"# OSD cleanup ledger ({a.map.name})", "",
          f"Image areas total {total} B. Bytes = flash areas the item owns (map); LOC = definition lines in the ported SDK + fw/sdcc.", "",
          "| item | bytes | areas | LOC | defs | what |", "|---|---:|---:|---:|---:|---|"]
    md += [f"| {i} | {b} | {n} | {l} | {nd} | {t} |" for i, t, b, n, l, nd in rows]
    for iid, hits, d in detail:
        md += ["", f"## {iid}", "", "areas: " + (", ".join(f"{n} {b}" for n, b in hits[:40]) + (" ..." if len(hits) > 40 else "") if hits else "none")]
        if d:
            md += ["definitions: " + ", ".join(f"{n} ({f.name}, {c})" for f, n, c in d[:30]) + (" ..." if len(d) > 30 else "")]
    (a.out / "report.md").write_text("\n".join(md) + "\n")
    (a.out / "report.tsv").write_text("item\tbytes\tareas\tloc\tdefs\ttitle\n" + "".join(f"{i}\t{b}\t{n}\t{l}\t{nd}\t{t}\n" for i, t, b, n, l, nd in rows))
    for i, t, b, n, l, nd in rows:
        log(f"{i:14s} {b:7d} B in {n:3d} areas  {l:5d} LOC in {nd:3d} defs  {t}")
    log(f"-> {a.out / 'report.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
