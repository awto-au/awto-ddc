#!/usr/bin/env python3
"""One-off migration (awto-ddc#162): turn the keil2sdcc.py behaviour rules + fw/overlay into plain edits of fw/sdk.

usage: sdk_own.py overlay                merge fw/overlay/** into fw/sdk (mechanical rewrite of each overlay file)
       sdk_own.py global                 the global behaviour regexes (audio test, DP version, popup time, T3, host wait, ...)
       sdk_own.py files SUBSTR...        every INSERT / SUB / WRAP of the SDK files whose path contains a SUBSTR
       sdk_own.py check [SUBSTR...]      compare fw/sdk (tokenised, includes expanded, comments dropped) with the baseline port

- Rules come from tag wb-p14ui-ownbase (git archive -> tmp/own-base): the last tree whose build patched the SDK.
- Baseline = tmp/base-src (tmp/sdcc-port/src of that tag's build). Code must match it line for line, comments aside.
- Big inserted blocks (fw/sdcc/*.inc, settings glue) become `#include "x.inc"` lines; the build tag is `@FW_TAG@`.
- Each edit carries `// awto: <what> (#issue)` instead of `[keil2sdcc]`.
Log: tmp/logs/sdk_own.log
"""
import os
import re
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(os.environ.get("AWTO_DDC_REPO") or subprocess.run(
    ["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).parent, capture_output=True, text=True).stdout.strip())
TAG = "wb-p14ui-ownbase"
BASE = ROOT / "tmp" / "own-base"
BASE_SRC = ROOT / "tmp" / "base-src"
FWSDK = ROOT / "fw" / "sdk"
INCDIR = ROOT / "fw" / "sdcc"
LOG = None
sys.path.insert(0, str(Path(__file__).resolve().parent))


def log(s):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {s}"
    print(line)
    LOG.write(line + "\n"); LOG.flush()


def load_old():
    if not (BASE / "scripts" / "keil2sdcc.py").exists():
        BASE.mkdir(parents=True, exist_ok=True)
        tar = subprocess.run(["git", "-C", str(ROOT), "archive", TAG, "scripts", "fw"], capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(BASE)], input=tar, check=True)
    os.environ["AWTO_DDC_REPO"] = str(BASE)
    os.environ["AWTO_FW_TAG"] = "@FW_TAG@"
    os.environ.setdefault("AWTO_RTDFW_REPO", "/mnt/2tb/git/awto-rtdfw-ui")
    sys.path.insert(0, str(BASE / "scripts"))
    import keil2sdcc as old
    old.LOG = open(ROOT / 'tmp' / 'logs' / 'sdk_own_old.log', 'a')
    return old


# ---- inc blocks -> #include lines ----
def inc_blocks():
    """name -> text as the old rules inserted it (longest first so the composite glue wins over its parts)."""
    out = {}
    for p in sorted(INCDIR.glob("*.inc")):
        out[p.name] = p.read_text().rstrip("\n")
    sd = BASE / "fw" / "awto" / "settings"
    gl = (sd / "glue.inc").read_text().rstrip("\n").replace('#include "glue_nv.inc"', (sd / "glue_nv.inc").read_text().rstrip("\n"))
    out["glue.inc"] = gl
    out["glue_key.inc"] = (sd / "glue_key.inc").read_text().rstrip("\n")
    out["glue_nv.inc"] = (sd / "glue_nv.inc").read_text().rstrip("\n")
    return dict(sorted(out.items(), key=lambda kv: -len(kv[1])))


INC = None


def replace_inc(text):
    for name, content in INC.items():
        if content and content in text:
            text = text.replace(content, f'#include "{name}"')
    return text


def expand_inc(text):
    return re.sub(r'^#include "(\w+\.inc)"[^\n]*$', lambda m: INC.get(m.group(1), m.group(0)), text, flags=re.M)


# ---- marker -> `// awto: ...` ----
DESC = [   # (regex on the code part of the line, description, default issue)
    (r"_RL6449_AWTO_JXC4K\b", "our board id 0x4F", "7"),
    (r"RL6449_AWTO_JXC4K\.h", "include our board", "7"),
    (r"_AWTO_LTM270FL01\b", "our panel id 0x3D", "7"),
    (r"AWTO_LTM270FL01\.h", "include our panel", "7"),
    (r"_AWTO_DP_PHYCTS", "size switch: DP PHY compliance test code", "65"),
    (r"_AWTO_FLASH_ALL", "size switch: one flash chip, detection and table dropped", "65"),
    (r"_AWTO_GAMMA_ALL", "size switch: demo gamma tables alias the 2.2 table", "65"),
    (r"_AWTO_FACTORY", "size switch: factory menu", "65"),
    (r"_AWTO_DDCRAM_DEFINER", "DDC RAM arrays defined here, extern hidden (one __at per array)", "8"),
    (r"_AWTO_POPUP_ICON_AWTO == _OFF", "our info mark replaces the SDK bubble", "46"),
    (r"_AWTO_DEBUG_PORT == _OFF\) && \(_AWTO_DDCCI_ENGINES", "DDC port in Realtek debug mode / spare engines", "13"),
    (r"!defined\(_CHECKSUM\)", "NVRAM checksum from RL6449_Project.h (old data reloads defaults)", "8"),
    (r"awto_dbgport\.inc", "debug IIC engine follows the active port", "28"),
    (r"_AWTO_DBG_FOLLOW", "debug IIC engine follows the active port", "28"),
    (r"AwtoMsg\.h", "tokenised message functions live in the debug module", "26"),
    (r"awto_dbgisr\.inc", "debug slave answers in the EXINT1 ISR", "38"),
    (r"awto_delaycal\.inc", "delay calibration", "53"),
    (r"g_ucAwtoCal(5|X)", "M2PLL re-entry keeps the calibrated delay counts", "54"),
    (r"_AWTO_FAST_BOOT == _OFF", "fast boot: no waits for rails this board never switches", "63"),
    (r"_AWTO_SCDC_KEEP", "keep SCDC 0x20 across a TMDS initial (host 1/40 ratio)", "78"),
    (r"AWTO_IDLE_RX_OFF", "idle receivers stay powered (AWTO_IDLE_RX_OFF)", "60"),
    (r"AWTO_IDLE_TMDS_OFF", "idle TMDS MAC stays powered", "60"),
    (r"AWTO_WDT_FEED\(AWTO_WDT_S_HPD", "watchdog feed per ms in the eDP HPD poll", "150"),
    (r"AWTO_WDT_FEED\(AWTO_WDT_S_(WREN|WRDIS|WRPROT)\)", "watchdog feed instead of the SDK flash poke", "138"),
    (r"AWTO_WDT_FEED\(AWTO_WDT_S_(DELAY|POLL|EVENT)\)", "watchdog feed per ms in a bounded wait", "131"),
    (r"AwtoWdtLibPoke", "watchdog poke in a flash loop", "150"),
    (r"AWTO_NV_EV\(", "NVRAM save timing in the sync log", "150"),
    (r"AWTO_NV_ITEM_WR", "NVRAM item write notes the flush gate", "151"),
    (r"AwtoNvFlush", "flush every dirty NVRAM item now", "151"),
    (r"no save here", "no NVRAM save at the first ACTIVE after a switch", "151"),
    (r"AwtoT0EvClock", "restart the pending Timer0 tick at the new clock", "138"),
    (r"AwtoT0EvIsr", "Timer0 event scheduler tick", "138"),
    (r"AWTO_T0EV_EXINT0", "Timer0 event flag test in EXINT0", "138"),
    (r"event table in awto_t0ev", "WD-timer event table replaced by the Timer0 scheduler", "138"),
    (r"awto_t0ev|WD-timer", "WD-timer events on Timer0", "138"),
    (r"AWTO_SYNC_MARK", "boot log clock carried over the WDT counter clear", "29"),
    (r"AWTO_DP_FRAME_SET|AWTO_DP_TWO_FRAMES|awto_dpframe", "DP Rx1 two-frame waits = 2 x the measured frame", "60"),
    (r"AWTO_SW_MARK\((3\d)\)", "DP Rx1 scan step mark", "60"),
    (r"AWTO_SW_MARK", "slow-segment mark", "60"),
    (r"AwtoMeasEvent|AWTO_MEAS_T2ISR|awto_meas4k", "4K60 measurement ring", "26"),
    (r"AwtoFreq|awto_freq\.inc", "exact input frequencies", "34"),
    (r"awto_fastsw_scaler", "fast switch: scaler side", "60"),
    (r"awto_fastsw", "cached fast input switch", "60"),
    (r"AwtoDiagStage\(2\)", "boot stage 2", "34"),
    (r"AwtoDiagStage\((3|4)\)", "boot stage", "63"),
    (r"AwtoDiagStage\((5|7|8)\)", "eDP power-up stage", "63"),
    (r"ucDebounceCnt = 1", "DHtotal fine-tune: one pass, no debounce loop", "26"),
    (r"_LAST_LINE_FINETUNE_ENABLE", "last-line fine-tune off for this function only", "26"),
    (r"_AWTO_PS_WAKE == _ON", "power-saving wake: counted, not returned", "144"),
    (r"_AWTO_PS_WAKE == _OFF", "power-saving wake: SDK predetect wait kept only without _AWTO_PS_WAKE", "144"),
    (r"AWTO_DIAG_EX1ISR|AWTO_DIAG_T2ISR", "diag hook in the ISR", "23"),
    (r"AwtoSwEvent\(AWTO_SW_EV_PROBE, (2[0-3])\)", "switch-log probe: which SysJudgeCheckStatus check failed", "60"),
    (r"AWTO_TMDS_STUCK", "pulse the HDMI HPD of a stuck TMDS port", "78"),
    (r"AwtoSwEvent\(AWTO_SW_EV_PROBE, (24|26|27)\)", "switch-log probe: eDP panel-on phase", "78"),
    (r"AwtoSwEvent\(AWTO_SW_EV_POWER", "switch-log: panel power action", "60"),
    (r"AwtoSwEvent\(AWTO_SW_EV_BLANK", "switch-log: blank", "60"),
    (r"AwtoSwEvent\(AWTO_SW_EV_PROBE", "switch-log probe", "60"),
    (r"AwtoSyncBegin|AwtoSyncDetect|AwtoSyncTiming|AwtoSyncFreq|AwtoSyncInit|awto_sync\.inc", "sync / power-on log", "139"),
    (r"AwtoSwCacheStore", "store the fast-switch cache at the first ACTIVE", "60"),
    (r"AwtoSwPoll|AWTO_SW_FAST_POLL|AWTO_SW_POLL_MARKS|awto_sw\.inc", "switch timeline poll", "60"),
    (r"AWTO_PS_POLL_SITE", "power-saving wake poll between handlers", "144"),
    (r"AWTO_LP\(|awto_loopprof", "main-loop cost profile", "75"),
    (r"awto_loopsplit|AWTO_SLOW_DUE_CABLE", "main-loop split: cable detection every AWTO_SLOW_MS", "75"),
    (r"AWTO_FAST_JUDGE_HOLD|AWTO_SLOW_DUE_JUDGE", "main-loop split + L1/L2 hold in the judge check", "78"),
    (r"awto_led\.inc", "power LED", "23"),
    (r"awto_diag\.inc|AwtoDiagInit|AwtoDiagMainPass|AwtoDiagTestCmd", "boot-stage / timing diagnostics", "23"),
    (r"AwtoMeasInit", "4K60 measurement ring init", "26"),
    (r"awto_wdtpop|awto_wdt\.inc|AwtoWdtInit", "main-loop watchdog", "131"),
    (r"AwtoGpioPoll", "GPIO change poll", "39"),
    (r"AwtoKeyPoll", "one key path", "129"),
    (r"AWTO_SET_LOOP|AwtoSetInit|glue\.inc|glue_key\.inc", "settings registry / menu glue", "67"),
    (r"AWTO_DDCCI_POLL|awto_ddcci\.inc", "KVM input select + DDC/CI engines", "60"),
    (r"AWTO_NET_POLL|awto_net\.inc", "IP over DDC", "80"),
    (r"awto_testcmd|awto_keytest|awto_gpio\.inc|awto_keys\.inc", "key / test / GPIO code", "129"),
    (r"awto_dbgpop|awto_osdcard|awto_keypop|awto_gpiopop", "OSD text layer, cards and panels", "134"),
    (r"AWTO_BL_OFF_OR_BLANK", "backlight off becomes a blank", "60"),
    (r"AWTO_KEY_OSD_RESET", "key panels follow an OSD reset", "129"),
    (r"_AWTO_HDMI_HPD_TOGGLE", "no HDMI hot-plug pulse on an input switch", "60"),
    (r"AwtoAudioGain", "volume through our dB table", "93"),
    (r"AWTO_AUDIO_HOLD", "mute while the mode is not ACTIVE / DISPLAY_SETTING", "93"),
    (r"_AUDIO_DAC_OUTPUT_HEADPHONE", "headphone output only", "93"),
    (r"_AWTO_DIAG == _ON", "load the debug-message switch from NVRAM", "74"),
    (r"b1AwtoMsgOn", "spare bit: debug messages switch", "74"),
    (r"#define (_DP_1|_HDMI_1|_HDMI_2)\b", "our ports: D1 DP, D2 / D3 HDMI", "60"),
    (r"AwtoBootConsole", "boot console instead of the logo", "144"),
    (r"AWTO_BOOT_PANEL_ON", "boot panel power-on", "144"),
    (r"AwtoSourceOpen", "our source selector", "134"),
    (r"AWTO_REALTEK_MENU_OPEN", "Realtek menu built out", "120"),
    (r"AWTO_REALTEK_KEYINFO", "Realtek menu key legend built out", "120"),
    (r"AwtoMenuForget", "menu forgets a closed OSD", "67"),
    (r"^\s*\}\s*$", "an OSD hold (debug pop-up) blocks the disable", "28"),
    (r"^\s*#endif\s*$", "early panel VDD (AwtoPanelVddEarly)", "63"),
    (r"AwtoInputSelect", "input select through the fast path", "60"),
    (r"_AWTO_ICON|tAWTO_ICON", "icon table stub", "117"),
    (r"AWTO_PS_CABLE_SDK", "power-saving cable wake is ours", "144"),
    (r"AwtoPsTmdsLive|AwtoPsDdcSeen|AwtoPsAuxSeen", "power-saving wake counted by AwtoPsWakePoll", "144"),
    (r"_AWTO_DIAG_DEFINER", "diag block defined in SysMain.c, extern elsewhere", "23"),
    (r"AwtoHoldBlocksDisable", "an OSD hold blocks the disable", "28"),
]
MISSING = Counter()
MARK = re.compile(r"[ \t]*//\s*\[keil2sdcc\]\s*(insert|sub|wrap|dropped pragma)?\s*(.*)$")


def describe(code, kind, tail):
    iss = re.findall(r"#(\d+)", tail)
    tail_txt = re.sub(r"#\d+", "", tail).strip(" :;,.")
    for rx, d, i in DESC:
        if re.search(rx, code):
            return d, (iss[0] if iss else i)
    if tail_txt:
        return tail_txt, (iss[0] if iss else None)
    MISSING[f"{kind}: {code.strip()[:110]}"] += 1
    return f"{kind} {code.strip()[:50]}", (iss[0] if iss else None)


def convert_markers(text):
    out = []
    for ln in text.split("\n"):
        m = MARK.search(ln)
        if m:
            code = ln[:m.start()]
            if not code.strip() and not re.sub(r"#\d+", "", m.group(2)).strip(" :;,.") and out:                  # marker alone: the line above says what
                prev = re.sub(r"^\s*//\s*awto\s*#?(\d+)?:?\s*", "", out[-1])
                iss = re.findall(r"#(\d+)", m.group(2))
                ln = f"{code}// awto: {prev.strip()}" + (f" (#{iss[0]})" if iss else "")
                out.append(ln)
                continue
            d, iss = describe(code, m.group(1) or "edit", m.group(2))
            ln = f"{code}  // awto: {d}" + (f" (#{iss})" if iss else "")
        out.append(ln)
    return "\n".join(out)


# ---- rules ----
def msg_anchor(rx, ids):
    m = re.search(r"AwtoMsgV\\\((0x[0-9A-Fa-f]{4}),", rx)
    if not m:
        return rx
    txt = ids[int(m.group(1), 16)]
    return rx.replace(m.group(0), r"DebugMessage\w+\(\s*\"" + re.escape(txt) + r"\"")


def msg_texts():
    d = {}
    for ln in (ROOT / "fw" / "msgids.tsv").read_text(encoding="utf-8").splitlines():
        f = ln.split("\t")
        d[int(f[0], 16)] = f[3]
    return d


def prep_rules(old):
    ids = msg_texts()
    old.INSERTS[:] = [(r[0], msg_anchor(r[1], ids), replace_inc(r[2])) + tuple(r[3:]) for r in old.INSERTS]
    new = []
    for f, rx, fn, want in old.SUBS:
        rx = msg_anchor(rx, ids).replace(r"\(\(void\)0\);", r"DebugMessage\w+\([^;]*\);")   # a dropped message was ((void)0)
        if callable(fn):
            fn = (lambda m, fn=fn: replace_inc(fn(m)))
        new.append((f, rx, fn, want))
    old.SUBS[:] = new


GLOBAL_NOTE = {   # pattern part -> what the edit does
    "_INTERNAL_AUDIO_TEST_SUPPORT": "audio test build (-D_AWTO_AUDIO_TEST)",
    "b1OsdDpD1PortVersion": "D1 DP version default _AWTO_DP_D1_VERSION (#28)",
    "_FRC_SUPPORT == _ON": "FRC memory BW also with the CheckMDomain debug messages (#37)",
    "SEC\\(3\\)": "info pop-up time _AWTO_INFO_POPUP_SEC",
    "_PANEL_POWER_ON_T3": "T3 wait with the delay calibration inside (#53)",
    "g_bFwHalt": "host-silence timeout of the debug wait (#56)",
}
GLOBAL = ("_INTERNAL_AUDIO_TEST_SUPPORT", "b1OsdDpD1PortVersion", "_FRC_SUPPORT == _ON", "SEC\\(3\\)", "_PANEL_POWER_ON_T3", "g_bFwHalt")


def global_rules(old):
    return [(rx, rep) for rx, rep in old.RULES if any(g in rx.pattern for g in GLOBAL)]


def rd(p):
    return p.read_bytes().decode("latin-1")


def wr(p, t):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(t.encode("latin-1"))


def rule_files(old):
    fs = set()
    for r in old.WRAPS + old.INSERTS + old.SUBS:
        fs.add(r[0])
    return sorted(fs)


# ---- check ----
def strip(t):
    return [re.sub(r"/\*.*?\*/", "", re.sub(r"//.*$", "", l)).rstrip() for l in t.split("\n")]


def new_port(old, rel):
    return expand_inc(old.tokenise_messages(rd(FWSDK / rel), Counter(), rel))


def check(old, rels):
    bad = []
    for rel in rels:
        b = rd(BASE_SRC / rel)
        n = new_port(old, rel)
        n = re.sub(r'(#define AWTO_FW_TAG )"[^"]*"', r'\1"T"', n)
        b = re.sub(r'(#define AWTO_FW_TAG )"[^"]*"', r'\1"T"', b)
        sb, sn = strip(b), strip(n)
        nz = lambda ls: ["".join(l.split()) for l in ls if l.strip()]
        if nz(sb) != nz(sn):
            import difflib
            d = [l for l in difflib.unified_diff(sb, sn, "base", "new", lineterm="", n=0)][:14]
            bad.append(rel)
            log(f"CHECK DIFF {rel}\n    " + "\n    ".join(d))
        elif len(sb) != len(sn):
            log(f"check {rel}: same code, line count {len(sb)} vs {len(sn)} (blank-line shift)")
    log(f"check: {len(rels) - len(bad)}/{len(rels)} files identical to the baseline port")
    return bad


def setup_old():
    global INC
    old = load_old()
    INC = inc_blocks()
    files = [p for p in old.SDK.rglob("*") if p.is_file() and ".git" not in p.parts]
    ov = [p for p in old.OVERLAY.rglob("*") if p.is_file()]
    old.collect_messages(files, ov)                       # message ids exactly as the baseline build assigned them
    prep_rules(old)
    return old


def main():
    global LOG
    (ROOT / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    LOG = (ROOT / "tmp" / "logs" / "sdk_own.log").open("a")
    cmd, args = sys.argv[1], sys.argv[2:]
    import sdk_import as imp
    old = setup_old()
    if cmd == "overlay":
        idx, sfr, using = imp.scan_mirror()
        for p in sorted((BASE / "fw" / "overlay").rglob("*")):
            if not p.is_file():
                continue
            rel = p.relative_to(BASE / "fw" / "overlay")
            raw = p.read_bytes().decode("latin-1")
            t = imp.rewrite(raw, (imp.SDK / rel).parent, idx, sfr, using, Counter()) if p.suffix in imp.SRC_EXT else raw
            wr(FWSDK / rel, t)
            log(f"overlay: {rel}")
        return 0
    if cmd == "global":
        n = Counter()
        for p in sorted(FWSDK.rglob("*")):
            if p.suffix not in imp.SRC_EXT or not p.is_file():
                continue
            t = rd(p); t0 = t
            for rx, rep in global_rules(old):
                note = next(v for k_, v in GLOBAL_NOTE.items() if k_ in rx.pattern)
                t, k = rx.subn(lambda m, rep=rep, note=note: (rep(m) if callable(rep) else m.expand(rep)) + f" /* awto: {note} */", t)
                n[(rx.pattern[:36], str(p.relative_to(FWSDK)))] += k
            if t != t0:
                wr(p, t)
        for (rx, f), k in sorted(n.items()):
            if k:
                log(f"global {k}x {rx} in {f}")
        return 0
    if cmd == "files":
        done = []
        for rel in rule_files(old):
            if not any(a in rel for a in args):
                continue
            p = FWSDK / rel
            if not p.exists():
                sys.exit(f"{rel}: not in fw/sdk")
            stats = Counter()
            t = rd(p)
            t = old.apply_wraps(rel, t, stats)
            t = old.apply_inserts(rel, t, stats)
            t = old.apply_subs(rel, t, stats)
            t = convert_markers(t)
            wr(p, t)
            done.append(rel)
            log(f"edited {rel}: {dict(stats)}")
        for k, v in MISSING.items():
            log(f"NO DESCRIPTION {v}x {k}")
        if done:
            check(old, done)
        return 0
    if cmd == "check":
        rels = [str(p.relative_to(FWSDK)) for p in sorted(FWSDK.rglob("*"))
                if p.is_file() and p.suffix in imp.SRC_EXT and (not args or any(a in str(p) for a in args))]
        rels = [r for r in rels if (BASE_SRC / r).exists()]
        return 1 if check(old, rels) else 0
    sys.exit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
