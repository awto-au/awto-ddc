#!/usr/bin/env python3
"""List every NVRAM setting: (a) Realtek SDK EEPROM-emulation items, (b) our registry record (awto-ddc#151).

usage: nvram_list.py [--unit N --map MAP] [--doc docs/nvram-settings.md] [--no-doc]
  Offline: fields, types, bits, defaults parsed from the SDK headers / .c initialisers and settings/registry.tsv.
  --unit N --map MAP: read-only live values from the running unit (devices.json unit N, bus found by EDID serial):
    (a) RAM copies g_stSystemData / g_stOSDUserData / g_stBriConData / g_stColorProcData / g_stSixColorData /
        g_stPanelTimeData by XDATA byte reads over debug slave 0x35 (needs the debug link: dev.py link --unit N on).
    (b) registry values through the firmware VCP mailbox: the same GET a DDC/CI host does (no set, no save).
    Flash contents are NOT read: no firmware read path over the debug slave, ISP resets the unit, and the archived
    images are code only (0x00000-0xDFFFF).
  Sources: $AWTO_SDK_SRC (default awto-ddc-ui/tmp/sdcc-port/src), $AWTO_RTDFW_UI (default awto-rtdfw-ui).
  Bitfield layout rule (SDCC, checked against the live bytes): LSB first, never straddling a byte, a non-bitfield
  member starts a new byte, WORD members big-endian in a --big-endian build.
Log: ./tmp/logs/nvram_list.log
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


def repo_root() -> Path:
    return Path(os.environ.get("AWTO_DDC_REPO") or HERE.parent)


ROOT = repo_root()
SDK = Path(os.environ.get("AWTO_SDK_SRC") or ROOT.parent / "awto-ddc-ui/tmp/sdcc-port/src")
UI = Path(os.environ.get("AWTO_RTDFW_UI") or ROOT.parent / "awto-rtdfw-ui")
LOG = ROOT / "tmp/logs/nvram_list.log"

OSD_H = SDK / "User/RTD Series/RTD2014Osd/Header/RTD2014NVRamOsd.h"
OSD_C = SDK / "User/RTD Series/RTD2014Osd/Code/RTD2014NVRamOsd.c"
SYS_H = SDK / "Kernel/User Common Function/Header/UserCommonInclude.h"
SYS_C = SDK / "Kernel/User Common Function/Code/UserCommonNVRamSystem.c"
CT_H = SDK / "Panel/RTDColorDefaultTable/ColorTempDefault.h"
ITEM_H = SDK / "User/RTD Series/RTD2014Function/Header/RTD2014UserInclude.h"

# preprocessor view of this build: every optional block OFF (the 24 B OSD struct matches the map); 8-bit PWM
FLAGS = {"_OSD_TYPE": "_REALTEK_2014_OSD", "_SYSTEM_EEPROM_EMULATION_SUPPORT": "_ON", "_PWM_DUT_RESOLUTION": "_PWM_8BIT", "_CTS_TYPE": "_CTS_GEN_1_12BIT", "_BRI_TYPE": "_BRI_GEN_1_10BIT"}
CONST = {"_ON": 1, "_OFF": 0, "_TRUE": 1, "_FALSE": 0}


def say(s: str = "", out: list | None = None) -> None:
    if out is not None:
        out.append(s)
    print(s, flush=True)


# ---------------------------------------------------------------------------------------------- C parsing
def cond(expr: str) -> bool:
    e = expr.strip()
    e = re.sub(r"defined\s*\(\s*\w+\s*\)", "False", e)
    e = re.sub(r"(\w+)\s*==\s*(\w+)", lambda m: f"(F({m[1]!r})=={m[2]!r})", e)
    e = re.sub(r"(\w+)\s*!=\s*(\w+)", lambda m: f"(F({m[1]!r})!={m[2]!r})", e)
    e = e.replace("&&", " and ").replace("||", " or ")
    e = re.sub(r"!(?!=)", " not ", e)
    try:
        return bool(eval(e, {"F": lambda k: FLAGS.get(k, "_OFF")}))
    except Exception:
        return False


def preprocess(text: str) -> str:
    """Active lines only (#if / #ifdef / #else / #elif / #endif); #define lines kept for the caller."""
    out, stack = [], []          # stack of (parent_active, this_branch_taken, active)
    for ln in text.splitlines():
        s = ln.strip()
        m = re.match(r"#\s*(ifdef|ifndef|if|elif|else|endif)\b\s*(.*)", s)
        if m:
            d, rest = m[1], m[2]
            par = stack[-1][2] if stack else True
            if d == "if":
                c = cond(rest)
                stack.append((par, c, par and c))
            elif d == "ifdef":
                stack.append((par, False, False))      # nothing is defined here: no _CUSTOM_* overrides
            elif d == "ifndef":
                stack.append((par, True, par))
            elif d == "elif":
                p, taken, _ = stack.pop()
                c = (not taken) and cond(rest)
                stack.append((p, taken or c, p and c))
            elif d == "else":
                p, taken, _ = stack.pop()
                stack.append((p, True, p and not taken))
            elif d == "endif":
                stack.pop()
            continue
        if not stack or stack[-1][2]:
            out.append(ln)
    return "\n".join(out)


def defines(text: str) -> dict:
    d = {}
    for m in re.finditer(r"^\s*#define\s+(\w+)\s+(.+?)\s*(?://.*)?$", text, re.M):
        d.setdefault(m[1], m[2].strip())
    return d


def resolve(v: str, defs: dict, depth: int = 0):
    """Number if the expression reduces to one, else the symbol text."""
    v = v.strip()
    if v in CONST:
        return CONST[v]
    if v in defs and depth < 6:
        return resolve(defs[v], defs, depth + 1)
    e = v.strip("()")
    if re.fullmatch(r"[0-9a-fA-Fx<>\s()+\-*/|]+", v) and re.search(r"\d", v):
        try:
            return int(eval(v, {"__builtins__": {}}))
        except Exception:
            pass
    return v


def struct_fields(h_text: str, name: str) -> list[dict]:
    end = re.search(r"\}\s*" + name + r"\s*;", h_text)
    if not end:
        raise SystemExit(f"{name} not found")
    start = h_text.rfind("typedef struct", 0, end.start())
    body = preprocess(h_text[start:end.start()])
    fields = []
    for ln in body.splitlines():
        code, _, cm = ln.partition("//")
        m = re.match(r"\s*(\w+)\s+(\w+)\s*(?::\s*(\d+))?\s*;", code)
        if not m or m[1] == "struct":
            continue
        cm = cm.strip().rstrip(";").strip()
        fields.append(dict(ctype=m[1], name=m[2], width=int(m[3]) if m[3] else None,
                           comment="" if cm.startswith("--") else cm))
    pos, open_, used = 0, False, 0
    for f in fields:
        if f["width"]:
            if open_ and used + f["width"] <= 8:
                f["byte"], f["shift"] = pos, used
                used += f["width"]
            else:
                if open_:
                    pos += 1
                f["byte"], f["shift"], used, open_ = pos, 0, f["width"], True
        else:
            if open_:
                pos += 1
                open_ = False
            f["byte"], f["shift"] = pos, 0
            f["size"] = 2 if f["ctype"] == "WORD" else 1
            pos += f["size"]
    f_size = pos + (1 if open_ else 0)
    for f in fields:
        f["bits"] = f["width"] or 8 * f["size"]
    return fields, f_size


def initialiser(c_text: str, name: str, defs: dict) -> list:
    """[(value, comment name)] in positional order (C initialisers are positional)."""
    pp = preprocess(c_text)
    m = re.search(name + r"\s*=\s*\{(.*?)\n\};", pp, re.S)
    if not m:
        return []
    vals = []
    for ln in m[1].splitlines():
        code, _, cm = ln.partition("//")
        code = code.strip()
        if not code or code.startswith("{"):
            continue
        parts = [p for p in re.split(r",(?![^(]*\))", code) if p.strip()]
        for part in parts:
            vals.append((resolve(part.strip(), defs), (re.findall(r"\w+", re.sub(r":\s*\d+", "", cm)) or [""])[-1] if len(parts) == 1 else ""))
    return vals


def fmt_default(v) -> str:
    if isinstance(v, int):
        return f"{v} (0x{v:X})" if v > 9 else str(v)
    return str(v)


# ------------------------------------------------------------------------------------------ SDK field set
MEANING = {
    "usBackLight": "backlight PWM duty (8-bit PWM build: 0x80 = 50 %)",
    "ucOsdHPos": "SDK menu horizontal position, %", "ucOsdVPos": "SDK menu vertical position, %",
    "ucOsdTimeout": "SDK menu auto-close, s", "ucAspectOriginRatio": "aspect 'Original' sub-ratio",
    "ucTransparency": "SDK menu transparency", "b4Language": "SDK menu language",
    "b4ColorEffect": "colour effect (Standard / Game / Movie / Photo / Vivid / User)",
    "b4ColorTempType": "colour temperature preset (9300 / 7500 / 6500 / 5800 / sRGB / User)",
    "b3VGARGBYUV": "VGA colour space RGB / YUV", "b3DVIRGBYUV": "DVI colour space RGB / YUV",
    "b3Sharpness": "scaler sharpness step", "b2OsdRotate": "SDK menu rotation",
    "b2DispRotationSizeType": "display rotation size mode", "b1OverScan": "overscan (video timings)",
    "b3Gamma": "gamma table select", "b3AspectRatio": "aspect ratio mode", "b1DDCCIStatus": "DDC/CI enabled",
    "b1OsdDcrStatus": "dynamic contrast ratio", "ucODGain": "overdrive gain", "ucHue": "hue",
    "ucSaturation": "saturation", "ucHLWinType": "highlight window type", "b3PCMStatus": "PCM user / native",
    "b2UltraVividStatus": "ultra vivid level", "b1VolumeMute": "audio mute",
    "b1AudioStandAloneStatus": "audio stand-alone mode", "b1AudioSourceStatus": "audio source (digital / analog)",
    "ucVolume": "audio volume", "b1ODStatus": "overdrive on / off", "b33DConvergenceMode": "3D convergence mode",
    "b1FactoryAutoColorType": "factory auto-colour type (external / internal)",
    "b1PanelUniformity": "panel uniformity on / off", "b1PCMSoftProftMode": "PCM soft-proof mode",
    "ucOsdInputPort": "selected input port (source selector)",
    "b2OsdDpD0PortVersion": "DP D0 version", "b2OsdDpD1PortVersion": "DP D1 version (EDID capability)",
    "b3OsdDispRotate": "display rotation", "b1OsdDpVersionHotKeyDisp": "DP version hot-key shown",
    "b1PreShowDpHotKeyVersion": "DP version pre-show flag", "b3PanelUniformityType": "panel uniformity type",
    "b2OsdDpD6PortVersion": "DP D6 version", "b2OsdDpD2PortVersion": "DP D2 version",
    "b1FreeSyncStatus": "FreeSync on / off", "b1CloneMode": "clone (DP TX) mode",
    "b2LatencyStatus": "latency mode (Low / Mid / High)", "b1OsdDoubleSize": "SDK menu 2x size",
    "b3OsdDpMST": "DP MST mode", "b1AwtoMsgOn": "awto debug messages on (our field, not Realtek)",
    "ucModeSlotIndex": "VGA mode slot round-robin index", "ucSSC": "dot-clock spread-spectrum range",
    "ucDPEDIDSelect": "DP EDID resolution list (1080p / 1440p / 2160p60)",
    "b3HDMIHotPlugSupportTime": "HDMI hot-plug pulse, x100 ms", "b1HDMIHotPlugSupport": "HDMI hot-plug on exit from power saving",
    "b1SourceHPAutoSearch": "auto source search on hot-plug", "b3SourceHPDefaultSearchIndex": "search start index on hot-plug",
    "b1DPHotPlugDCOffHigh": "DP HPD level in DC-off", "b1DPAuxDiffMode": "DP AUX differential mode",
    "b3D0DpLanes": "DP D0 lane count", "b3D1DpLanes": "DP D1 lane count", "b3D2DpLanes": "DP D2 lane count",
    "b3D6DpLanes": "DP D6 lane count", "b1PowerStatus": "monitor power on / off (resume on power key)",
    "b1ColorSeamlessChange": "colorimetry seamless change", "b4SearchPort": "source search priority port",
    "b3EdidD0": "EDID table index D0", "b3EdidD1": "EDID table index D1", "b3EdidD2": "EDID table index D2",
    "b3EdidD3": "EDID table index D3", "b3EdidD4": "EDID table index D4", "b3EdidD5": "EDID table index D5",
    "b3EdidD6": "EDID table index D6", "b4SourceScanType": "source scan type (auto in group / fixed ...)",
    "b4DPAuxAdjrSetting": "DP AUX adjustment setting", "ucDpIrqTime_10us": "DP IRQ HPD time, x10 us",
    "b1DPIllegalIdlePatternCheck": "DP illegal idle pattern check",
    "usBrightness": "digital brightness offset, per source (10-bit)", "usContrast": "contrast, per source (12-bit)",
    "usColorTempR": "red gain (12-bit)", "usColorTempG": "green gain (12-bit)", "usColorTempB": "blue gain (12-bit)",
    "usHour": "panel backlight used time, hours", "ucMin": "panel backlight used time, minutes",
}

# registry row duplicated by an SDK field: SDK "Struct.field" -> registry name(s)
DUP = {
    "OSD.usBackLight": "brightness", "OSD.ucOsdHPos": "osd_hpos", "OSD.ucOsdVPos": "osd_vpos",
    "OSD.ucOsdTimeout": "osd_timeout", "OSD.ucTransparency": "osd_transparency", "OSD.b4Language": "language",
    "OSD.b4ColorEffect": "colour_effect", "OSD.b4ColorTempType": "colour_temp",
    "OSD.b3VGARGBYUV": "colour_format", "OSD.b3DVIRGBYUV": "colour_format", "OSD.b3Sharpness": "sharpness",
    "OSD.b2OsdRotate": "osd_rotate", "OSD.b1OverScan": "overscan", "OSD.b3Gamma": "gamma",
    "OSD.b3AspectRatio": "aspect", "OSD.b1DDCCIStatus": "ddcci", "OSD.ucHue": "hue",
    "OSD.ucSaturation": "saturation", "OSD.b3PCMStatus": "pcm", "OSD.b1VolumeMute": "mute",
    "OSD.b1AudioStandAloneStatus": "audio_standalone", "OSD.b1AudioSourceStatus": "audio_source",
    "OSD.ucVolume": "volume", "OSD.b1PanelUniformity": "uniformity", "OSD.ucOsdInputPort": "input",
    "OSD.b2OsdDpD1PortVersion": "dp_version", "OSD.b3OsdDispRotate": "disp_rotate", "OSD.b1CloneMode": "clone",
    "OSD.b2LatencyStatus": "latency", "OSD.b1OsdDoubleSize": "osd_scale", "OSD.b1AwtoMsgOn": "debug_msgs",
    "SYS.b3EdidD1": "dp_edid", "SYS.b1PowerStatus": "power_on", "SYS.b3D1DpLanes": "dp_lanes", "SYS.ucDpIrqTime_10us": "dp_irq_10us", "SYS.ucSSC": "ssc", "TIME.usHour": "panel_hours", "TIME.ucMin": "panel_min", "SYS.b1SourceHPAutoSearch": "input_mode", "SYS.b4SourceScanType": "input_mode",
    "SYS.b4SearchPort": "search_order",
    "BRI.usBrightness": "black_level", "BRI.usContrast": "contrast",
    "CT.usColorTempR": "user_red (preset USER only)", "CT.usColorTempG": "user_green (preset USER only)",
    "CT.usColorTempB": "user_blue (preset USER only)",
}
SIXC = ["red", "yellow", "green", "cyan", "blue", "magenta"]
for _i, _c in enumerate(SIXC):
    DUP[f"SIX.ucSixColorHue{'RYGCBM'[_i]}"] = f"sa_{_c}_hue"
    DUP[f"SIX.ucSixColorSaturation{'RYGCBM'[_i]}"] = f"sa_{_c}_sat"

SDK_MENU_OFF = "SDK menu built out (#120): none reachable"
GATE = "gate"          # #151: every SDK item save deferred; written by the flush gate (see Stores)
WRITERS = {
    "SYS": f"{GATE}: registry row / power on / off (H) / factory (J); M boot recovery direct",
    "OSD": f"{GATE}: registry row / factory (J) / 0x28-0x29 (registry debug_msgs); M boot recovery direct",
    "BRI": f"{GATE}: registry black_level / contrast (current source); J factory",
    "CT": f"{GATE}: registry user RGB at colour temp User; J factory",
    "SIX": f"{GATE}: registry six-axis rows",
    "TIME": "rides along with every flush; power off / saving entry; never on its own (was I, every 20 min)",
}
FIELD_WRITERS = {
    "SYS.b4SearchPort": "source selector choice only (KVM / search keep it in RAM: F no longer saves)",
    "SYS.b4SourceScanType": "source selector choice only (as b4SearchPort)",
    "OSD.ucOsdInputPort": "source selector choice only (UP / DOWN / cancel never stored)",
}

ITEMS = [  # id, name, struct key, bytes, note
    (0, "VGA_ADC_DATA", None, 0, "not linked (no VGA input)"),
    (1, "YPBPR_ADC_DATA", None, 0, "not linked (no YPbPr input)"),
    (2, "SYSTEM_DATA", "SYS", 14, "StructSystemDataType"),
    (3, "PANEL_INDEX", None, 1, "1 B panel index (single panel: fixed)"),
    (4, "OSD_DATA_0", "OSD", 14, "StructOsdUserDataType bytes 0-13"),
    (5, "OSD_DATA_1", "OSD", 10, "StructOsdUserDataType bytes 14-23"),
    (6, "BRICON_SRC0_VGA", "BRI", 4, "per-source brightness / contrast"),
    (7, "BRICON_SRC1_VIDEO", "BRI", 4, ""), (8, "BRICON_SRC2_DVI", "BRI", 4, ""),
    (9, "BRICON_SRC3_HDMI", "BRI", 4, ""), (10, "BRICON_SRC4_DP", "BRI", 4, ""),
    (11, "COLORPROC0_9300", "CT", 6, "RGB gains per colour-temperature preset"),
    (12, "COLORPROC1_7500", "CT", 6, ""), (13, "COLORPROC2_6500", "CT", 6, ""),
    (14, "COLORPROC3_5800", "CT", 6, ""), (15, "COLORPROC4_SRGB", "CT", 6, ""),
    (16, "COLORPROC5_USER", "CT", 6, ""),
    (17, "SIXCOLOR_DATA", "SIX", 12, "six-axis hue / saturation"),
    (18, "PANEL_DATA", "TIME", 3, "panel used time"),
    (19, "MODE_USER_DATA 0..15", None, 0, "VGA mode slots: not linked (no VGA input)"),
]


def norm(n: str) -> str:
    return re.sub(r"^(b\d+|uc|us|c)", "", n).lower().replace("esstatus", "dcrstatus")


def sdk_fields(map_text: str | None) -> tuple[list[dict], dict]:
    osd_h, osd_c = OSD_H.read_text(errors="replace"), OSD_C.read_text(errors="replace")
    sys_h, sys_c = SYS_H.read_text(errors="replace"), SYS_C.read_text(errors="replace")
    odefs = defines(preprocess(osd_c))
    sdefs = defines(preprocess(sys_c))
    ctdefs = defines(CT_H.read_text(errors="replace"))
    rows, sizes = [], {}

    def add(key, struct, item, fields, defaults, comments=True):
        for i, f in enumerate(fields):
            d, cn = defaults[i] if i < len(defaults) else (0, "")      # positional init: missing tail = 0
            if isinstance(d, str) and d == "?":
                d = 0
            if cn and norm(cn) != norm(f["name"]) and not f["comment"]:
                f["comment"] = f"init comment names {cn}"
            rows.append(dict(key=f"{key}.{f['name']}", struct=struct, **f, default=d))

    of, osz = struct_fields(osd_h, "StructOsdUserDataType")
    od = initialiser(osd_c, "g_stOSDDefaultData", odefs)
    if len(od) > len(of):
        raise SystemExit(f"OSD default entries {len(od)} > fields {len(of)}")
    for f in of:
        f["item"] = "4" if f["byte"] < 14 else "5"
    sizes["OSD"] = osz
    sf, ssz = struct_fields(sys_h, "StructSystemDataType")
    sd = initialiser(sys_c, "g_stSystemDefaultData", sdefs)
    if len(sd) > len(sf):
        raise SystemExit(f"SYS default entries {len(sd)} > fields {len(sf)}")
    sizes["SYS"] = ssz
    for f in sf:
        f["item"] = "2"
    bf, bsz = struct_fields(osd_h, "StructBriConDataType")
    cf, csz = struct_fields(osd_h, "StructColorProcDataType")
    xf, xsz = struct_fields(osd_h, "StructSixColorDataType")
    tf, tsz = struct_fields(osd_h, "StructTimeType")
    sizes.update(BRI=bsz, CT=csz, SIX=xsz, TIME=tsz)
    xd = initialiser(osd_c, "g_stSixColorDefaultData", odefs)
    bri_d = [f"VGA {odefs.get('_BRIGHTNESS_VGA')} / others {odefs.get('_BRIGHTNESS_DVI')}",
             str(odefs.get("_CONTRAST_VGA"))]
    bri_d = [fmt_default(resolve(odefs["_BRIGHTNESS_DVI"], odefs)), fmt_default(resolve(odefs["_CONTRAST_DVI"], odefs))]
    bri_d[0] = f"VGA {fmt_default(resolve(odefs['_BRIGHTNESS_VGA'], odefs))}; others {bri_d[0]}"
    ct_d = [fmt_default(resolve(ctdefs[f"_CT6500_{c}"], ctdefs)) for c in ("RED", "GREEN", "BLUE")]
    for f in bf:
        f["item"] = "6-10"
    for f in cf:
        f["item"] = "11-16"
    for f in xf:
        f["item"] = "17"
    for f in tf:
        f["item"] = "18"
    add("SYS", "StructSystemDataType", None, sf, sd)
    add("OSD", "StructOsdUserDataType", None, of, od)
    add("BRI", "StructBriConDataType", None, bf, [(x, "") for x in bri_d])
    add("CT", "StructColorProcDataType", None, cf, [(x, "") for x in ct_d])
    add("SIX", "StructSixColorDataType", None, xf, xd)
    add("TIME", "StructTimeType", None, tf, [(0, ""), (0, "")])
    for r in rows:
        r["meaning"] = MEANING.get(r["name"], "")
        r["range"] = f"0..{(1 << r['bits']) - 1}"
        r["written_by"] = FIELD_WRITERS.get(r["key"], WRITERS[r["key"].split(".")[0]])
        r["dup"] = DUP.get(r["key"], "")
    return rows, sizes


# -------------------------------------------------------------------------------------------- registry
def registry() -> list[dict]:
    p = UI / "settings/registry.tsv"
    cols, rows = None, []
    for ln in p.read_text().splitlines():
        if ln.startswith("# id\t"):
            cols = ln[2:].split("\t")
        elif ln and not ln.startswith("#"):
            r = dict(zip(cols, ln.split("\t")))
            for c in cols:
                r.setdefault(c, "-")
            r["id"] = int(r["id"])
            r["flags"] = [x for x in r["flags"].split(",") if x and x != "-"]
            r["opts"] = []
            if r["options"] != "-":
                for i, o in enumerate(r["options"].split("|")):
                    lab, _, n = o.partition("=")
                    r["opts"].append((int(n, 0) if n else i, lab))
            rows.append(r)
    pages = {}
    for ln in (UI / "settings/pages.tsv").read_text().splitlines():
        if ln and not ln.startswith("#"):
            g, t, *_ = ln.split("\t")
            pages[g] = t
    for r in rows:
        r["page"] = pages.get(r["group"], r["group"])
    return rows


REG_DUP_REV = {}
for _k, _v in DUP.items():
    REG_DUP_REV.setdefault(_v.split(" ")[0], []).append(_k)
REG_STORE = lambda r: "SDK field" if "sdk" in r["flags"] else f"AUX item 0x40-0x43"   # #151


# ------------------------------------------------------------------------------------------------ live
def find_bus(unit: int) -> tuple[int, str]:
    import kvm
    devs = json.loads((HERE / "devices.json").read_text())["units"]
    u = devs[str(unit)]
    if not u.get("test"):
        raise SystemExit(f"unit {unit} is not a test unit (devices.json test flag): refused")
    b = kvm.find_bus(u)
    if b is None:
        raise SystemExit(f"unit {unit}: no bus answers (serial {u['serial']})")
    return b, u["serial"]


def sym(map_text: str, name: str) -> int:
    m = re.search(rf"^D:\s+([0-9A-F]{{8}})\s+_{name}\b", map_text, re.M)
    if not m:
        raise SystemExit(f"_{name} not in the map")
    return int(m[1], 16) & 0xFFFF


def live_sdk(bus: int, map_text: str, sdk: list[dict], sizes: dict, be: bool) -> dict:
    import dbg_xdata as X
    import rtd_i2c_bridge as B
    io = B.Real(bus, allow_write=False, regread=True)      # debug-slave read commands only
    raw = {}
    try:
        for key, var in (("SYS", "g_stSystemData"), ("OSD", "g_stOSDUserData"), ("BRI", "g_stBriConData"),
                         ("CT", "g_stColorProcData"), ("SIX", "g_stSixColorData"), ("TIME", "g_stPanelTimeData")):
            b = X.read_bytes(io, sym(map_text, var), sizes[key])
            if b is None:
                raise SystemExit(f"debug read of {var} failed (debug link on? dev.py link --unit N on)")
            raw[key] = b
    finally:
        io.close()
    for r in sdk:
        k = r["key"].split(".")[0]
        b = raw[k]
        if r["width"]:
            v = (b[r["byte"]] >> r["shift"]) & ((1 << r["width"]) - 1)
        else:
            seg = b[r["byte"]:r["byte"] + r["size"]]
            v = int.from_bytes(seg, "big" if be else "little")
        r["live"] = v
    return raw


def live_registry(bus: int, serial: str, map_text: str, rows: list[dict]) -> dict:
    import settings_cli as C
    from rtd_i2c_bridge import Real
    import i2cbus
    i2cbus.require_unit(bus, serial)
    io = Real(bus, allow_write=True)                      # the mailbox GET is 4 XDATA byte writes + reads per row
    box = C.Box(io, map_text)
    out = {}
    try:
        for r in rows:
            if r["type"] == "action":
                continue
            try:
                out[r["id"]] = box.get_row({"id": r["id"]})
            except SystemExit as e:
                out[r["id"]] = f"? ({e})"
    finally:
        io.close()
    return out


def reg_live_text(r: dict, v) -> str:
    if v is None or isinstance(v, str):
        return "" if v is None else v
    if r["type"] == "bool":
        return f"{'on' if v else 'off'}"
    for n, lab in r["opts"]:
        if n == v:
            return str(v) if lab == str(v) else f"{lab} ({v})"
    return str(v)


# ----------------------------------------------------------------------------------------------- output
def md(s) -> str:
    return str(s).replace("|", "/").replace("\n", " ")


def reg_range(r: dict) -> str:
    unit = "" if r["unit"] == "none" else f" {r['unit']}"
    if r["type"] == "action":
        return "action"
    d = r["default"]
    for n, lab in r["opts"]:
        if str(n) == d and lab != d:
            d = f"{lab} ({d})"
    return f"{r['min']}..{r['max']}{unit}; def {d}"


def aux_bytes(nv) -> int:
    return 1 + sum(2 if r["type"] == "int" else 1 for r in nv if "sdk" not in r["flags"])


def build(sdk, sizes, reg, live_s, live_r, hdr_extra: str) -> tuple[str, str]:
    nv = [r for r in reg if "nv" in r["flags"]]
    inert_nv = [r for r in nv if "inert" in r["flags"]]
    inert_all = [r for r in reg if "inert" in r["flags"]]
    sdk_dups = [r for r in sdk if r["dup"]]
    reg_dups = sorted({r["dup"].split(" ")[0] for r in sdk_dups})
    reg_names = {r["name"] for r in reg}
    stale = [d for d in reg_dups if d not in reg_names]
    counts = (f"SDK fields {len(sdk)} in {len({r['struct'] for r in sdk})} structs ({len(ITEMS)} item ids, "
              f"{sum(1 for i in ITEMS if i[2])} used); registry rows {len(reg)} ({len(nv)} nv: "
              f"{sum(1 for r in nv if 'sdk' in r['flags'])} on SDK fields, aux block {aux_bytes(nv)} B); "
              f"duplicates: {len(sdk_dups)} SDK fields <-> "
              f"{len(reg_dups)} registry rows; inert: {len(inert_all)} rows ({len(inert_nv)} of them nv)")
    today = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    # ---- markdown
    m = [f"# NVRAM settings: every stored field\n",
         f"- Generated by `scripts/nvram_list.py` on {today}; regenerate with the script, do not edit.",
         f"- Sources: SDK `{SDK}` (RTD2014NVRamOsd.h/.c, UserCommonInclude.h, UserCommonNVRamSystem.c), "
         f"registry `{UI}/settings/registry.tsv` (+ `pages.tsv`), nvram.c / settings.c.",
         f"- Counts: {counts}.",
         hdr_extra,
         "- SDK defaults are positional (C initialiser): the OSD initialiser lists MST before DispRotate, so from byte 20.4 "
         "each default lands one field late; 'init comment names X' marks the value written for X.",
         "- Letters A-M: the write triggers of awto-au/awto-ddc#151. Since wb-p14ui-nv (#151): one store (SDK), every save "
         "through the flush gate; F (input switch), F2 (input row), G (selector steps), I (panel timer), K (dp_edid "
         "duplicate) gone; B/C (VCP save / defaults) are flags.",
         "",
         "## Stores",
         "",
         "| store | where | format | writers |", "|---|---|---|---|",
         "| SDK | bank 15 pages 11-12, flash 0xFB000-0xFCFFF | 16 B items (14 B payload), EEPROM emulation, "
         "unchanged items not written (SDK compare), page move every ~239 item writes | the flush gate only |",
         f"| AUX | SDK items 0x40-0x43 (same store) | aux block: check byte + {sum(1 for r in nv if 'sdk' not in r['flags'])} "
         f"registry rows without an SDK field (bool / enum 1 B, int 2 B LE), {aux_bytes(nv)} B | the flush gate only |",
         "| REG (retired) | flash 0xFD000-0xFEFFF | old registry record: read once at the first boot of the #151 layout, "
         "never written | - |",
         "",
         "- Gate (glue_nv.inc, RL6449_Project.h AWTO_NV_*): write when ACTIVE stable 3 s, no DDC/CI for 500 ms and 2 s since "
         "the last change (no debounce after a menu / selector close: 'Saving to memory' card), forced after 30 s dirty, at "
         "once at power off / power-saving entry. DDC/CI handlers only mark dirty. Counters: g_stAwtoNv (scripts/nv_test.py).",
         "", "## SDK item ids (store SDK)", "", "| id | item | struct | payload | note |", "|---|---|---|---|---|"]
    for i, n, k, ln, note in ITEMS:
        m.append(f"| {i} | {n} | {k or '-'} | {ln} B | {note} |")
    m += ["", "## SDK fields (store SDK)", "",
          "| id | field | struct byte.bit (width) | meaning | range / default | live | written by | duplicate-of |",
          "|---|---|---|---|---|---|---|---|"]
    for r in sdk:
        lv = "" if "live" not in r else (f"{r['live']} (0x{r['live']:X})" if r["live"] > 9 else str(r["live"]))
        pos = f"{r['byte']}" + (f".{r['shift']} ({r['width']} b)" if r["width"] else f" ({r['bits']} b)")
        c = f" [SDK: {r['comment']}]" if r["comment"] and r["comment"].lower() != (r["meaning"] or "").lower() else ""
        m.append(f"| {r['item']} | {md(r['key'])} | {r['struct'].replace('Struct', '').replace('DataType', '')} "
                 f"{pos} | {md(r['meaning'])}{md(c)} | {r['range']}; def {md(fmt_default(r['default']))} | {lv} | "
                 f"{md(r['written_by'])} | {md(r['dup'])} |")
    m += ["", "## Registry rows with the nv flag (stored)", "",
          "| id | name | page | meaning | range / default | live | VCP | inert | store | SDK field |",
          "|---|---|---|---|---|---|---|---|---|---|"]
    for r in nv:
        dups = ", ".join(REG_DUP_REV.get(r["name"], []))
        note = r["note"] if r["note"] != "-" else ""
        m.append(f"| {r['id']} | {r['name']} | {md(r['page'])} | {md(r['label'])}{' - ' + md(note) if note else ''} | "
                 f"{md(reg_range(r))} | {md(reg_live_text(r, (live_r or {}).get(r['id'])))} | "
                 f"{'' if r['vcp'] == '-' else r['vcp']} | {'inert' if 'inert' in r['flags'] else ''} | "
                 f"{REG_STORE(r)} | {md(dups)} |")
    m += ["", "## Registry rows without nv (not stored)", "", "| id | name | type | flags | note |", "|---|---|---|---|---|"]
    for r in reg:
        if "nv" not in r["flags"]:
            m.append(f"| {r['id']} | {r['name']} | {r['type']} | {','.join(r['flags'])} | "
                     f"{md(r['note'] if r['note'] != '-' else '')} |")
    m += ["", "## Registry rows on SDK fields (one RAM copy since #151; registry live = the field in registry units)", "",
          "| registry row | SDK field(s) | registry inert | SDK live | registry live |", "|---|---|---|---|---|"]
    by_reg = {}
    for r in sdk_dups:
        by_reg.setdefault(r["dup"].split(" ")[0], []).append(r)
    rmap = {r["name"]: r for r in reg}
    for name in sorted(by_reg, key=lambda n: rmap[n]["id"] if n in rmap else 999):
        rr = rmap.get(name)
        sl = ", ".join(f"{x['key']}={x.get('live', '')}" for x in by_reg[name])
        m.append(f"| {name} | {', '.join(x['key'] for x in by_reg[name])} | "
                 f"{'inert' if rr and 'inert' in rr['flags'] else ''} | {md(sl)} | "
                 f"{md(reg_live_text(rr, (live_r or {}).get(rr['id']))) if rr else ''} |")
    if stale:
        m.append(f"\nDUP table names missing from the registry: {', '.join(stale)}")
    doc = "\n".join(m) + "\n"

    # ---- plain text
    t = [f"nvram_list {today}", counts, hdr_extra, "",
         f"{'store':5} {'id':>6} {'name':34} {'range / default':52} {'live':14} {'dup-of'}"]
    for r in sdk:
        lv = "" if "live" not in r else str(r["live"])
        t.append(f"{'SDK':5} {r['item']:>6} {r['key']:34} {r['range'] + '; def ' + fmt_default(r['default']):52.52} "
                 f"{lv:14} {r['dup']}")
    for r in nv:
        t.append(f"{'REG':5} {r['id']:>6} {r['name'] + (' [inert]' if 'inert' in r['flags'] else ''):34} "
                 f"{reg_range(r):52.52} {reg_live_text(r, (live_r or {}).get(r['id'])):14.14} "
                 f"{', '.join(REG_DUP_REV.get(r['name'], []))}")
    return doc, "\n".join(t)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--unit", type=int)
    ap.add_argument("--map")
    ap.add_argument("--doc", default=str(ROOT / "docs/nvram-settings.md"))
    ap.add_argument("--no-doc", action="store_true")
    ap.add_argument("--be", action="store_true", help="--big-endian image (default: map name ends in -be.map)")
    a = ap.parse_args()
    if bool(a.unit) != bool(a.map):
        ap.error("--unit and --map go together")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    sdk, sizes = sdk_fields(None)
    reg = registry()
    live_r, extra = None, "- Live values: not read (offline run)."
    if a.unit:
        mp = Path(a.map)
        map_text = mp.read_text(errors="replace")
        be = a.be or mp.name.endswith("-be.map")
        osd_delta = sym(map_text, "g_stBriConData") - sym(map_text, "g_stOSDUserData")
        if osd_delta != sizes["OSD"]:
            raise SystemExit(f"OSD struct size {sizes['OSD']} != map {osd_delta}: layout model is off")
        bus, serial = find_bus(a.unit)
        live_sdk(bus, map_text, sdk, sizes, be)
        live_r = live_registry(bus, serial, map_text, reg)
        extra = (f"- Live values: unit {a.unit} ({serial}, bus {bus}), image `{mp.name}`, read {time.strftime('%Y-%m-%dT%H:%M:%S%z')}. "
                 "SDK = RAM copies (loaded from flash at boot, plus runtime changes); BriCon / ColorProc show only the "
                 "copy of the current source / last colour temperature. REG = registry value over the VCP mailbox. "
                 "Flash contents were not read (no read-only path).")
    doc, text = build(sdk, sizes, reg, None, live_r, extra)
    LOG.write_text(text + "\n")
    print(text)
    if not a.no_doc:
        Path(a.doc).write_text(doc)
        print(f"\nwrote {a.doc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
