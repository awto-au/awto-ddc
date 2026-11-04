#!/usr/bin/env python3
"""Host-driven technical-info OSD for an RTD2795-class (RL6449) monitor, over ISP. Volatile only.

Draws a multi-line tech panel onto the panel via OSD windows + font SRAM, with no flash change
(everything is lost on power-cycle / scaler reset). Content is pulled live from rtd_identify.py.

usage: rtd_tech_osd.py <bus> [options] COMMAND
  draw        gather live info (rtd_identify), then open an ISP session and draw the tech panel.
              Leaves the MCU HALTED with the OSD up (--keep implied) unless --reset is given.
  watch       draw the panel, then keep polling the ADC key regs; on a press, redraw the bottom
              line with the button NAME. Runs for --secs (default 30). MCU stays halted.
  probe       read back OSD enable/window/base regs after a draw would run (diagnostic; no draw).
  selftest    no hardware: font packing + layout sanity.

options:
  --secs N    watch duration (default 30)
  --reset     end by resetting the scaler (monitor reboots, OSD gone). Default: leave OSD up, MCU halted.
  --no-isp-info   skip the scaler/flash ISP read in the info-gather phase (EDID+DDC only; faster, no pre-reset)
  --json      print the gathered info as JSON too
  --scale N   1 = 12x18 px cells (default), 2 = firmware's doubled OSD (0x3A0A[1:0])

Facts: docs/reversing/realtek-rtd/tech-osd.md (draw sequence, char-word format, button map).
SDK-confirmed char word: byte0=0x4C (1bpp, width=12px), byte1=glyph index, byte2=colour [sdk-rl64xx-reference.md].
Log: ./tmp/logs/rtd_tech_osd.log
"""
import re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rtd_isp_probe as P
import rtd_font5x7 as FNT
from rtd_osd import Osd, PAGE_SEL, OSD_WOPT, FRAME_BASE, SRAM_WIN, SRAM_FONT, WIN_BASE, WORDS_PER_GLYPH
import rtd_identify as ID

# ---- char-word format (SDK-confirmed) -----------------------------------------------------------
CW_BYTE0 = 0x4C                 # 1bpp font, low nibble 12 = cell width in px [sdk-rl64xx-reference.md s2]
# colour byte = fg[7:4] | bg[3:0]  (4-bit palette indices; bg 0 = transparent) [osd-font-download.md s6]

# palette indices we load
PAL_BG     = 0                  # transparent (not loaded; index 0)
PAL_PANEL  = 1                  # dark panel fill (window colour)
PAL_LABEL  = 2                  # muted label text
PAL_VALUE  = 3                  # bright value text
PAL_KEY    = 4                  # button-name highlight
PAL_HDR    = 5                  # section header

COL = {                         # 24-bit RRGGBB for each palette slot
    PAL_PANEL: 0x101828,        # near-black navy panel
    PAL_LABEL: 0x8893A8,        # muted grey-blue
    PAL_VALUE: 0xF0F4FF,        # bright
    PAL_KEY:   0xFFD24A,        # amber highlight for pressed key
    PAL_HDR:   0x56C2FF,        # cyan section headers
}

# ---- layout ------------------------------------------------------------------------------------
# Font SRAM: row commands at word 0..n-1 = (0x80 valid, height-1, cols), word n = terminator (B0=0);
# char words at fs_base = n+1, row-major, fixed stride COLS; glyphs at FONT_BASE. [sdk-rl64xx-reference.md]
ROWCMD_BASE = 0x000
FONT_BASE = 0xC00                                # glyphs; above the map, below the 12-bit pointer max 0xFFF
                                                 # (RL6449 OSD SRAM = 12288 words [SDK RL6449_OSD_Gen_Option.h])
CELL_W, CELL_H = FNT.CELL_W, FNT.CELL_H          # 12 x 18
COLS = 80                                        # chars per line (80*12 = 960 px at --scale 1)
COL_W = 39                                       # two section columns of 39 + 2-char gutter
SCREEN_W, SCREEN_H = 3840, 2160                  # fallback when EDID has no preferred timing

# Button band -> name. From docs/reversing/realtek-rtd/buttons.md. [user-pending] = NOT hw-confirmed.
# (mask, source reg, lo, hi, name, confirmed)
KEY_BANDS = [
    (0x02, 0xFF09, 0xC0, 0xE0, "SOURCE?",  False),   # A0 top ladder; SOURCE or AUTO (unconfirmed)
    (0x04, 0xFF09, 0x28, 0x48, "DOWN",     False),   # adjust- (symmetric pair, likely but unconfirmed)
    (0x08, 0xFF0A, 0x28, 0x48, "UP",       False),   # adjust+
    (0x10, 0xFF09, 0x70, 0x90, "MENU",     False),   # sole long-press key -> almost certainly MENU
    (0x20, 0xFF0A, 0x68, 0x88, "AUTO?",    False),   # SOURCE or AUTO (unconfirmed)
]
# POWER = digital P3.0 (SFR 0xB0 bit0, pressed = low). Read via ISP reg 0x25 snapshot per keywatch.


def key_decode(a0, a1):
    for mask, reg, lo, hi, name, _ in KEY_BANDS:
        v = a0 if reg == 0xFF09 else a1
        if lo <= v < hi:
            return name
    return None


# ---- info -> panel lines -----------------------------------------------------------------------
def fmt_lines(info: dict) -> list:
    """Build the panel text lines from an rtd_identify result dict. Returns list of (kind, text):
    kind 'h'=header, 'kv'=label/value (split on first '|'), 't'=plain. Values kept fixed-width-ish."""
    e = info.get("edid", {})
    d = info.get("ddc", {})
    isp = info.get("isp", {})
    t = e.get("timing", {}) if isinstance(e, dict) else {}
    caps = d.get("capabilities", {}) if isinstance(d, dict) else {}
    feats = caps.get("features", {}) if isinstance(caps, dict) else {}

    def vcp(key):
        v = d.get(key, {}) if isinstance(d, dict) else {}
        return v.get("current") if isinstance(v, dict) and "current" in v else None

    L = []
    L.append(("h", "SIGNAL"))
    res = t.get("preferred", "?")
    rr = t.get("refresh_hz")
    L.append(("kv", f"NATIVE (EDID)|{res} @ {rr:g} HZ" if rr else f"NATIVE (EDID)|{res}"))
    pc = t.get("pixel_clock_mhz")
    ht, vt = t.get("h_total"), t.get("v_total")
    if pc and ht and vt:
        hf = pc * 1e6 / ht / 1000.0                 # kHz
        vf = pc * 1e6 / (ht * vt)                    # Hz
        L.append(("kv", f"PIXEL CLOCK|{pc} MHZ"))
        L.append(("kv", f"H / V FREQ|{hf:.1f} KHZ / {vf:.1f} HZ"))
        L.append(("kv", f"TOTALS|{ht} x {vt}"))
    L.append(("h", "INPUT"))
    host = info.get("host", {})
    conn = host.get("connector") or "?"                     # e.g. card2-DP-4
    kind = conn.split("-")[1] if conn.count("-") >= 2 else "?"
    L.append(("kv", f"DRIVEN BY|{kind} <- HOST {conn}"))
    v60 = host.get("vcp60")
    # fw answers a constant 0x02 on DP and HDMI units alike -> not an input indicator
    L.append(("kv", f"VCP 60 (FW)|{v60 if v60 else '?'} (NOT RELIABLE)"))

    modes = host.get("modes") or []
    if modes:
        L.append(("h", "MODES (EDID)"))
        for res_, rates in modes:
            L.append(("kv", f"{res_}|{' '.join(rates)} HZ"))

    L.append(("h", "LINK"))
    L.append(("kv", "INTERFACE|eDP 4-LANE (PANEL)"))     # panel-side; host link not exposed over DDC
    L.append(("kv", "HDR|SDR ONLY (EOTF GAMMA)"))   # EDID HDR block lists traditional gamma only

    L.append(("h", "SYSTEM"))
    fw = d.get("firmware_level", {}) if isinstance(d, dict) else {}
    fwv = fw.get("current") if isinstance(fw, dict) else None
    ct = d.get("controller_type", {}) if isinstance(d, dict) else {}
    ctv = ct.get("current") if isinstance(ct, dict) else None
    L.append(("kv", f"FIRMWARE|{('0X%04X' % fwv) if fwv is not None else '?'}"))
    L.append(("kv", f"CONTROLLER|{('0X%04X' % ctv) if ctv is not None else '?'}"))
    bri = vcp("brightness"); con = vcp("contrast")
    # brightness/contrast not pre-gathered -> show label with VCP hint if absent
    scaler = isp.get("scaler", {}) if isinstance(isp, dict) else {}
    if scaler:
        L.append(("kv", f"SCALER|{scaler.get('name', '?')[:24]}"))
        L.append(("kv", f"PRODUCT|{scaler.get('product_code', '?')} VER {scaler.get('version_nibble', '?')}"))
    fl = isp.get("flash", {}) if isinstance(isp, dict) else {}
    if fl:
        dbn = fl.get("db", {}).get("name") if isinstance(fl.get("db"), dict) else None
        L.append(("kv", f"FLASH|{dbn or fl.get('jedec', '?')}"))

    L.append(("h", "PANEL"))
    L.append(("kv", "MODEL|SAMSUNG LTM270FL01"))
    L.append(("kv", "SIZE|597 x 336 MM / 27.0 IN"))
    L.append(("kv", "TYPE|PLS (IPS-CLASS)"))
    sz = e.get("size_mm") if isinstance(e, dict) else None
    if sz:
        L.append(("kv", f"EDID SIZE|{sz[0]} x {sz[1]} MM"))

    return L


def render_block(lines, width, lab_w=13):
    """(kind,text) lines -> rows of exactly `width` (char, colour_byte)."""
    rows = []
    for kind, text in lines:
        if kind == "h":
            s = ("== " + text + " ").ljust(width, "=")[:width]
            rows.append([(c, (PAL_HDR << 4) | PAL_BG) for c in s])
        elif kind == "kv":
            label, _, val = text.partition("|")
            s_lab = [(c, (PAL_LABEL << 4) | PAL_BG) for c in label[:lab_w].ljust(lab_w + 1)]
            s_val = [(c, (PAL_VALUE << 4) | PAL_BG) for c in val]
            row = (s_lab + s_val)[:width]
            rows.append(row + [(" ", (PAL_VALUE << 4) | PAL_BG)] * (width - len(row)))
        else:
            rows.append([(c, (PAL_VALUE << 4) | PAL_BG) for c in text[:width].ljust(width)])
    return rows


def render_rows(lines):
    """Split lines into sections (at each header), fill left column then right, balanced by height.
    Returns full-width rows of COLS (char, colour_byte)."""
    secs = []
    for ln in lines:
        if ln[0] == "h" or not secs:
            secs.append([])
        secs[-1].append(ln)
    total = sum(len(s) for s in secs)
    left, right, n = [], [], 0
    for s in secs:                                   # keep section order; switch once half is used
        (left if n + len(s) / 2 <= total / 2 else right).append(s)
        n += len(s)
    L = render_block([ln for s in left for ln in s], COL_W)
    R = render_block([ln for s in right for ln in s], COL_W)
    blank = [(" ", (PAL_VALUE << 4) | PAL_BG)]
    gut = blank * (COLS - 2 * COL_W)
    h = max(len(L), len(R))
    L += [blank * COL_W] * (h - len(L)); R += [blank * COL_W] * (h - len(R))
    return [l + gut + r for l, r in zip(L, R)]


# ---- drawing -----------------------------------------------------------------------------------
class TechOsd:
    def __init__(self, bus):
        self.o = Osd(bus)
        self.idx = {}            # char -> glyph index in font SRAM
        self.n_rows = 0

    def enter(self):
        self.o.enter()

    def read_scaler_flash(self):
        """Read scaler ID + SPI-flash JEDEC/status inside THIS already-open ISP session (no extra
        reset). Mirrors rtd_identify.isp_report's reads; returns {'scaler':..., 'flash':...}."""
        o = self.o
        out = {}
        try:
            id_reg = o._rd(0x00); r0f = o._rd(0x0F)
            o.select_page(0)
            code = (id_reg << 4) | (r0f >> 4)
            out["scaler"] = {"reg_0x00": f"0x{id_reg:02x}", "reg_0x0f": f"0x{r0f:02x}",
                             "product_code": f"0x{code:03x}", "version_nibble": r0f & 0xF,
                             "name": ID.SCALER_TABLE.get(code, "unknown")}
        except OSError as ex:
            out["scaler"] = {"error": str(ex)}
        return out

    def reset(self):
        self.o.reset()

    def upload_charset(self, chars: str):
        """Upload one 12x18 glyph per unique char to font SRAM. Returns {char: index}."""
        o = self.o
        o.set_opt(SRAM_FONT)
        self.idx = {}
        for i, ch in enumerate(chars):
            self.idx[ch] = i
            for k, (b0, b1, b2) in enumerate(FNT.glyph_words(ch)):
                o.write_word(FONT_BASE + i * WORDS_PER_GLYPH + k, b0, b1, b2)
        return self.idx

    def write_rows(self, rows):
        """Row commands at ROWCMD_BASE, terminator, then char words at fs_base (stride COLS)."""
        o = self.o
        o.set_opt(SRAM_FONT)
        self.n_rows = len(rows)
        for r in range(self.n_rows):
            o.write_word(ROWCMD_BASE + r, 0x80, CELL_H - 1, COLS)
        o.write_word(ROWCMD_BASE + self.n_rows, 0, 0, 0)            # end of row list
        for r, row in enumerate(rows):
            self.write_row_chars(r, row)

    def fs_base(self):
        return ROWCMD_BASE + self.n_rows + 1

    def write_row_chars(self, r, row):
        a = self.fs_base() + r * COLS
        for ch, colour in row:
            gi = self.idx.get(ch, self.idx.get(" ", 0))
            self.o.write_word(a, CW_BYTE0, gi, colour); a += 1      # char word: 0x4C | glyph | colour

    def set_origin(self, x_px, y_ln):
        """hori_delay1 = 10 bit, 4 px steps (0x3A01=[9:2], 0x3A02[7:6]=[1:0]);
        vert_delay1 = 11 bit, 1 line (0x3A00=[10:3], 0x3A02[5:3]=[2:0]). [spec from regdb]"""
        hx = max(2, min(0x3FF, x_px // 4)); vy = max(0, min(0x7FF, y_ln))
        o = self.o
        o.wr(FRAME_BASE + 1, hx >> 2)
        o.wr(FRAME_BASE + 0, vy >> 3)
        o.rmw(FRAME_BASE + 2, 0xF8, ((hx & 3) << 6) | ((vy & 7) << 3))
        P.log(f"origin {hx * 4} px, {vy} lines")

    def setup(self, rows, scale=1, screen=(SCREEN_W, SCREEN_H)):
        o = self.o
        o.rmw(FRAME_BASE + 0x0A, 0x03, 0x03 if scale == 2 else 0x00)   # db_width|db_height (fw boot = 2x)
        for idx, rgb in COL.items():
            o.set_color(idx, rgb >> 16, (rgb >> 8) & 0xFF, rgb & 0xFF)
        o.wr(0x0093, 0x00)                                   # db_enable off: writes latch immediately
        o.rmw(0x01DC, 0x08, 0x08)                            # osd_clken
        o.rmw(0x006C, 0x01, 0x01)                            # OVERLAY_CTRL.overlay_port_en (fw leaves 0 when no menu)
        # upload glyphs for everything we will draw
        allchars = FNT.charset("".join(ch for r in rows for ch, _ in r))
        self.upload_charset(allchars)
        self.n_rows = len(rows)
        fs = self.fs_base()
        assert fs + self.n_rows * COLS <= FONT_BASE, "text map overruns FONT_BASE"
        # font/fs base pointers (0x3A0C-0E), units = words
        o.wr(FRAME_BASE + 0x0C, fs & 0xFF)
        o.rmw(FRAME_BASE + 0x0D, 0xF0, ((fs >> 8) & 0xF) << 4)
        o.rmw(FRAME_BASE + 0x0D, 0x0F, FONT_BASE & 0xF)
        o.wr(FRAME_BASE + 0x0E, FONT_BASE >> 4)
        self.write_rows(rows)
        # WIN0 = panel-fill behind the text. Width = COLS*CELL_W, height = rows*CELL_H (cell units;
        # on-screen is 2x). Colour = PAL_PANEL. Window geometry is 12-bit px.
        w = COLS * CELL_W
        h = (self.n_rows + 1) * CELL_H
        o.win_set(0, 0, 0, w, h, color=PAL_PANEL)
        sw, sh = screen
        self.set_origin((sw - w * scale) // 2, (sh - h * scale) // 2)
        o.set_opt(SRAM_WIN)
        o.osd_enable(True)

    def readback(self):
        regs = (0x0093, 0x0094, 0x3A00, 0x3A01, 0x3A02, 0x3A0C, 0x3A0D, 0x3A0E, 0x01DC)
        out = {}
        for r in regs:
            out[r] = self.o.rd(r)
        return out

    # ---- button name on the bottom line ----
    def draw_key_row(self, name: str):
        """Overwrite the last-but-one display row with a centred, highlighted button name."""
        o = self.o
        txt = ("[ " + name + " ]").center(COLS)[:COLS]
        colour = (PAL_KEY << 4) | PAL_BG
        row = [(c, colour) for c in txt]
        o.set_opt(SRAM_FONT)
        # upload any missing glyphs for the name
        need = FNT.charset(txt)
        missing = [c for c in need if c not in self.idx]
        if missing:
            base = len(self.idx)
            for j, ch in enumerate(missing):
                self.idx[ch] = base + j
                for k, (b0, b1, b2) in enumerate(FNT.glyph_words(ch)):
                    o.write_word(FONT_BASE + (base + j) * WORDS_PER_GLYPH + k, b0, b1, b2)
        self.write_row_chars(self.n_rows - 1, row)          # key row = last row

    def read_keys(self):
        """Raw ADC key regs (0xFF09/0xFF0A) + P3.0 snapshot, via the running-MCU F4/F5 path.
        NOTE: with the MCU halted (ISP), the firmware key scanner is stopped; these are the raw
        hardware ADC result registers. Whether presses update them while halted is to be confirmed."""
        o = self.o
        a0 = o.rd(0xFF09); a1 = o.rd(0xFF0A)
        p3 = o.rd(0x0025)
        return a0, a1, p3


def gather(bus, isp_info=True, as_json=False):
    """Gather live info BEFORE our OSD session. rtd_identify's ISP phase resets the monitor, so this
    must run first (its reset is harmless; we then open a fresh session to draw)."""
    info = ID.identify(bus, isp=isp_info)
    info["host"] = host_info(bus)
    P.log("gathered: " + ID.human(info).replace("\n", " | ")[:400])
    P.log(f"host: {info['host']}")
    return info


def host_info(bus):
    """Host-side facts: DRM connector driving this bus, EDID mode list, raw VCP 0x60."""
    out = {}
    p = ID.edid_path(bus)
    if p:
        out["connector"] = p.parent.name
        if p.exists():
            rc, txt = ID.run(["edid-decode"], ID.EDID_TIMEOUT, p.read_bytes())
            by_res = {}
            for w, h, hz in re.findall(r"(\d{3,4})x(\d{3,4})\s+([\d.]+) Hz", txt):
                by_res.setdefault((int(w), int(h)), set()).add(round(float(hz)))
            out["modes"] = [(f"{w}x{h}", [str(r) for r in sorted(rs, reverse=True)])
                            for (w, h), rs in sorted(by_res.items(), key=lambda kv: -kv[0][0] * kv[0][1])]
    rc, txt = ID.run(["ddcutil", "--bus", str(bus), "getvcp", "60"], ID.DDC_TIMEOUT)
    m = re.search(r"sl=(0x[0-9a-f]{2})", txt)
    out["vcp60"] = m.group(1) if m else None
    return out


def main():
    root = P.repo_root()
    (root / "tmp" / "logs").mkdir(parents=True, exist_ok=True)
    P.LOG = (root / "tmp" / "logs" / "rtd_tech_osd.log").open("a")
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help"):
        print(__doc__); return 2
    if args[0] == "selftest":
        return selftest()
    bus = int(args.pop(0))
    secs = int(args[args.index("--secs") + 1]) if "--secs" in args else 30
    do_reset = "--reset" in args
    isp_info = "--no-isp-info" not in args
    as_json = "--json" in args
    scale = int(args[args.index("--scale") + 1]) if "--scale" in args else 1
    cmd = next((a for a in args if not a.startswith("--") and a not in (str(secs), str(scale))), "draw")

    P.log(f"=== tech-osd bus={bus} cmd={cmd} secs={secs} reset={do_reset} isp_info={isp_info} ===")
    if cmd == "selftest":
        return selftest()

    # phase 1: gather EDID + DDC (MCU running, NO reset). Scaler ID is read later in the draw session
    # itself, so we avoid rtd_identify's ISP reset (which reboots the monitor and drops the bus).
    info = gather(bus, isp_info=False, as_json=as_json)
    if as_json:
        import json; print(json.dumps(info, indent=2))

    if cmd == "probe":
        t = TechOsd(bus); t.enter()
        try:
            rb = t.readback()
            for r, v in rb.items():
                P.log(f"probe rd 0x{r:04x} = 0x{v:02x}")
        finally:
            t.reset()
        return 0

    # phase 2: open ONE ISP session (halts MCU): read scaler ID, then draw.
    t = TechOsd(bus)
    t.enter()
    try:
        info["isp"] = t.read_scaler_flash()
        lines = fmt_lines(info)
        rows = render_rows(lines)
        rows.append([(" ", (PAL_KEY << 4) | PAL_BG)] * COLS)       # trailing key row (blank initially)
        P.log(f"panel: {len(rows)} rows x {COLS} cols")
        res = info.get("edid", {}).get("timing", {}).get("preferred", "")
        try:
            screen = tuple(int(v) for v in res.split("x"))
        except ValueError:
            screen = (SCREEN_W, SCREEN_H)
        t.setup(rows, scale, screen)
        rb = t.readback()
        for r, v in rb.items():
            P.log(f"readback 0x{r:04x} = 0x{v:02x}")
        osd_en = rb.get(0x3A02, 0) & 1
        win_en = None
        # read WIN0 ADR3 win_en bit back
        t.o.set_opt(SRAM_WIN, 0b100)
        win_en = t.o.read_word(WIN_BASE + 3, 0b100) & 1
        P.log(f"draw complete: osd_en={osd_en} WIN0.win_en={win_en}")
        if cmd == "watch":
            P.log(f"watch: polling ADC key regs for {secs}s (MCU halted). Press buttons now.")
            last = None
            t0 = time.time()
            while time.time() - t0 < secs:
                try:
                    a0, a1, p3 = t.read_keys()
                except OSError as ex:
                    P.log(f"key read error {ex}"); break
                name = key_decode(a0, a1)
                if name is None and not (p3 & 0x01):
                    name = "POWER"
                st = (a0, a1, p3 & 1, name)
                if st != last:
                    P.log(f"A0=0x{a0:02x} A1=0x{a1:02x} P3=0x{p3:02x} -> {name or 'idle'}")
                    if name:
                        t.draw_key_row(name)
                    last = st
            P.log("watch done")
    finally:
        if do_reset:
            t.reset()
        else:
            P.log("OSD left up, MCU halted. Power-cycle the monitor to revert, or run with --reset.")
    return 0


def selftest():
    # font packing round-trips and layout fits
    import make_logo as ML
    for ch in FNT.F:
        w = FNT.glyph_words(ch)
        assert len(w) == FNT.WORDS_PER_GLYPH, ch
        cell = ML.words_to_cell(w, 0)
        assert len(cell) == FNT.CELL_H
    info = {"edid": {"timing": {"preferred": "3840x2160", "refresh_hz": 60.0, "pixel_clock_mhz": 533.0,
                                "h_total": 4400, "v_total": 2020}, "size_mm": [597, 336]},
            "ddc": {"firmware_level": {"current": 0x0101}, "controller_type": {"current": 0x0b05},
                    "capabilities": {"features": {"60": "DP-1"}}},
            "isp": {"scaler": {"name": "RTD2795T-family", "product_code": "0xcf2", "version_nibble": 1},
                    "flash": {"jedec": "ef4017", "db": {"name": "W25Q64"}}},
            "host": {"connector": "card2-DP-4", "vcp60": "0x02",
                     "modes": [("3840x2160", ["60", "50", "30", "25", "24"]), ("2560x1440", ["60"]),
                               ("1920x1080", ["60", "50", "30", "25", "24"]), ("640x480", ["60"])]}}
    rows = render_rows(fmt_lines(info))
    assert all(len(r) == COLS for r in rows), [len(r) for r in rows]
    for r in rows:                                      # text preview of the panel
        print("|" + "".join(c for c, _ in r) + "|")
    n = len(rows) + 1                                   # + key row
    total_words = (n + 1) + n * COLS
    print(f"selftest OK: {len(FNT.F)} glyphs, {n} rows x {COLS} cols, "
          f"{total_words} map words <= FONT_BASE {FONT_BASE}")
    assert total_words <= FONT_BASE - ROWCMD_BASE, "text map overruns FONT_BASE"
    return 0


if __name__ == "__main__":
    sys.exit(main())
