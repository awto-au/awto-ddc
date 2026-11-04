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

Facts: docs/reversing/realtek-rtd/tech-osd.md (draw sequence, char-word format, button map).
SDK-confirmed char word: byte0=0x4C (1bpp, width=12px), byte1=glyph index, byte2=colour [sdk-rl64xx-reference.md].
Log: ./tmp/logs/rtd_tech_osd.log
"""
import sys, time
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
# Each text line is one font-select "row": a row-command word then one char-word per column, then a
# zero row-command terminates the row list. We lay lines out as consecutive rows in the font-select
# SRAM starting at FS_BASE; glyph bitmaps live from FONT_BASE.
FS_BASE   = 0x000                                # font-select (text map) region; grows with rows*cols
FONT_BASE = 0x600                                # glyph bitmaps; must clear the whole text map
                                                 # (map ~= sum(1+cols) per row + 1; 0x600=1536 words headroom)
CELL_W, CELL_H = FNT.CELL_W, FNT.CELL_H          # 12 x 18
# OSD runs at 2x (firmware boot state db_width/db_height) -> on-screen cell is 24x36 px.
COLS = 44                                        # chars per line (44*12 = 528 cell px = 1056 on-screen)
X_ORG, Y_ORG = 0x20, 0x08                        # OSD origin regs 0x3A01/0x3A00 (approx (128px,64ln))

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
    L.append(("kv", f"RESOLUTION|{res} @ {rr} HZ" if rr else f"RESOLUTION|{res}"))
    pc = t.get("pixel_clock_mhz")
    ht, vt = t.get("h_total"), t.get("v_total")
    if pc and ht and vt:
        hf = pc * 1e6 / ht / 1000.0                 # kHz
        vf = pc * 1e6 / (ht * vt)                    # Hz
        L.append(("kv", f"PIXEL CLOCK|{pc} MHZ"))
        L.append(("kv", f"H / V FREQ|{hf:.1f} KHZ / {vf:.1f} HZ"))
        L.append(("kv", f"TOTALS|{ht} x {vt}"))
    sig = "PRESENT" if res not in (None, "?") else "NONE"
    L.append(("kv", f"SIGNAL|{sig}"))

    L.append(("h", "INPUTS"))
    # VCP 0x60 = input source; mark active. Known RTD/MCCS codes.
    INP = {0x01: "VGA-1", 0x03: "DVI-1", 0x0F: "DP-1", 0x11: "HDMI-1", 0x12: "HDMI-2", 0x13: "DP-2"}
    active = vcp("input_source") if False else None   # input_source not gathered by identify; derive from caps
    cur_in = None
    if "60" in feats:
        cur_in = feats.get("60")
    L.append(("kv", "AVAILABLE|VGA DVI HDMI DP"))
    L.append(("kv", f"ACTIVE|{cur_in or 'SEE VCP 60'}"))

    L.append(("h", "LINK"))
    L.append(("kv", "INTERFACE|eDP 4-LANE (PANEL)"))     # panel-side; host link not exposed over DDC
    L.append(("kv", "HDR|SDR (NO HDR BLOCK)"))

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


def render_rows(lines):
    """Turn (kind,text) lines into fixed-width display rows (padded to COLS) with per-char colour.
    Returns list of rows; each row = list of (char, colour_byte)."""
    rows = []
    for kind, text in lines:
        if kind == "h":
            s = ("== " + text + " ").ljust(COLS, "=")[:COLS]
            rows.append([(c, (PAL_HDR << 4) | PAL_BG) for c in s])
        elif kind == "kv":
            label, _, val = text.partition("|")
            label = label[:18].ljust(18)
            val = val[:COLS - 20]
            s_lab = [(c, (PAL_LABEL << 4) | PAL_BG) for c in label]
            s_sep = [(" ", (PAL_LABEL << 4) | PAL_BG), (" ", (PAL_LABEL << 4) | PAL_BG)]
            s_val = [(c, (PAL_VALUE << 4) | PAL_BG) for c in val]
            row = (s_lab + s_sep + s_val)[:COLS]
            row += [(" ", (PAL_VALUE << 4) | PAL_BG)] * (COLS - len(row))
            rows.append(row)
        else:
            s = text[:COLS].ljust(COLS)
            rows.append([(c, (PAL_VALUE << 4) | PAL_BG) for c in s])
    return rows


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
        """Write the font-select map: each display row = a row-command word + one char-word per column.
        A zero row-command terminates. Row command [oss/osd.md]: (CELL_H, CELL_W, n_chars)."""
        o = self.o
        o.set_opt(SRAM_FONT)
        a = FS_BASE
        for row in rows:
            o.write_word(a, CELL_H, CELL_W, len(row)); a += 1       # row command
            for ch, colour in row:
                gi = self.idx.get(ch, self.idx.get(" ", 0))
                o.write_word(a, CW_BYTE0, gi, colour); a += 1       # char word: 0x4C | glyph | colour
        o.write_word(a, 0, 0, 0)                                    # terminator (notStop=0)
        self.n_rows = len(rows)

    def setup(self, rows):
        o = self.o
        for idx, rgb in COL.items():
            o.set_color(idx, rgb >> 16, (rgb >> 8) & 0xFF, rgb & 0xFF)
        o.wr(0x0093, 0x00)                                   # db_enable off: writes latch immediately
        o.rmw(0x01DC, 0x08, 0x08)                            # osd_clken
        # upload glyphs for everything we will draw
        allchars = FNT.charset("".join(ch for r in rows for ch, _ in r))
        self.upload_charset(allchars)
        # font/fs base pointers (0x3A0C-0E), units = words
        o.wr(FRAME_BASE + 0x0C, FS_BASE & 0xFF)
        o.rmw(FRAME_BASE + 0x0D, 0xF0, ((FS_BASE >> 8) & 0xF) << 4)
        o.rmw(FRAME_BASE + 0x0D, 0x0F, FONT_BASE & 0xF)
        o.wr(FRAME_BASE + 0x0E, FONT_BASE >> 4)
        self.write_rows(rows)
        # WIN0 = panel-fill behind the text. Width = COLS*CELL_W, height = rows*CELL_H (cell units;
        # on-screen is 2x). Colour = PAL_PANEL. Window geometry is 12-bit px.
        w = COLS * CELL_W
        h = (self.n_rows + 1) * CELL_H
        o.win_set(0, 0, 0, w, h, color=PAL_PANEL)
        o.wr(FRAME_BASE + 0, Y_ORG)                          # vert_delay1
        o.wr(FRAME_BASE + 1, X_ORG)                          # hori_delay1
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
        # The blank key row is the LAST row already written by write_rows (rows[n_rows-1]).
        # Rewrite it in place: skip the n_rows-1 info rows (each 1 cmd + COLS chars), land on the
        # key row's command word, overwrite command + char words, then re-terminate.
        a = FS_BASE + (self.n_rows - 1) * (1 + COLS)
        o.write_word(a, CELL_H, CELL_W, len(row)); a += 1
        for ch, c in row:
            o.write_word(a, CW_BYTE0, self.idx[ch], c); a += 1
        o.write_word(a, 0, 0, 0)

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
    P.log("gathered: " + ID.human(info).replace("\n", " | ")[:400])
    return info


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
    cmd = next((a for a in args if not a.startswith("--") and a not in (str(secs),)), "draw")

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
        t.setup(rows)
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
                    "flash": {"jedec": "ef4017", "db": {"name": "W25Q64"}}}}
    rows = render_rows(fmt_lines(info))
    assert all(len(r) == COLS for r in rows), [len(r) for r in rows]
    total_words = sum(1 + len(r) for r in rows) + 1
    print(f"selftest OK: {len(FNT.F)} glyphs, {len(rows)} rows x {COLS} cols, "
          f"{total_words} font-select words, {total_words} <= font_base gap {FONT_BASE - FS_BASE}")
    assert total_words <= FONT_BASE - FS_BASE, "font-select map overruns FONT_BASE"
    return 0


if __name__ == "__main__":
    sys.exit(main())
