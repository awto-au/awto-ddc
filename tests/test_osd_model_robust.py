"""OSD model: random register images must not crash, render time budget, SRAM read-back port, coverage table consistency
(docs/osd/sim-coverage.tsv), every demo renders."""
from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import osd_demo as D  # noqa: E402
import osd_model as M  # noqa: E402

ALL_OPTS = M.Opt(osd_offsets=True, area_clip=True, row_total=True, su_region=True, win_rotate=True, round_circle=False, pg_toggle="invert")


def random_state(seed: int) -> M.OsdState:
    rng = np.random.default_rng(seed)
    regs = bytearray(rng.integers(0, 256, 0x100, dtype=np.uint8).tobytes())
    regs[2] |= 1                                                     # OSD on
    regs[0x41] &= 0xFE if seed % 3 else 0xFF
    win = {a: [int(v) for v in rng.integers(0, 256, 3)] for a in range(0x100, 0x110)}
    for i in range(26):
        for k in range(4):
            win[M.win_base(i) + k] = [int(v) for v in rng.integers(0, 256, 3)]
            win[M.win_base(i) + k][2] |= 1 if k == 3 and rng.random() < 0.7 else 0
    for a in list(range(330, 460)) + list(range(660, 760)):
        win[a] = [int(v) for v in rng.integers(0, 256, 3)]
    font = {a: [int(v) for v in rng.integers(0, 256, 3)] for a in range(0, 3000)}
    for a in range(0, 40):
        font[a][0] |= 0x80
        font[a][2] = int(rng.integers(0, 40))
    pal = [tuple(int(v) for v in rng.integers(0, 256, 3)) for _ in range(64)]
    return M.OsdState(win, font, pal, bytes(regs), (int(rng.integers(0, 256)) | 1, int(rng.integers(0, 256))), 0.0, 0, bytes(rng.integers(0, 256, 16, dtype=np.uint8).tobytes()))


def test_random_register_images_do_not_crash():
    t0 = time.time()
    for seed in range(40):
        st = random_state(seed)
        for opt in (None, ALL_OPTS):
            a = M.render(st, 320, 180, bg=(90, 90, 90), opt=opt)
            assert a.shape == (180, 320, 3) and a.dtype == np.uint8
    assert time.time() - t0 < 60                                      # 80 renders; measured ~10 s on the dev box


def test_random_images_other_canvas_sizes():
    for seed, (w, h) in enumerate(((1, 1), (7, 5), (64, 2000), (2000, 8))):
        a = M.render(random_state(100 + seed), w, h, bg=(1, 2, 3), opt=ALL_OPTS)
        assert a.shape == (h, w, 3)


def test_full_panel_render_time_budget():
    """Saver sims render hundreds of frames: a busy 4K image (windows + a full text map + highlight + blend) must stay under 2.5 s (2.1 s before the glyph memo, ~1.2 s now on the dev box)."""
    i = D.Img().window(0, 100, 100, 3000, 1500, 2, gradient=dict(dir=0, pol=(1, 1, 1), en=(1, 1, 1), step=1))
    i.window(10, 200, 200, 3000, 1400, 3, adr4=(0x80, 1, 4)).window(2, 300, 300, 3500, 1800, 4)
    i.text_boxes(100, 255, 1, 4).place(0, 0)
    i.reg(0x0A, 0x08, 0x0C).reg(0x2A, 0x42).ovl.__setitem__(0, 0x09)
    st = i.state()
    M.render(st, 3840, 2160, bg=(100, 100, 100))
    t0 = time.time()
    for _ in range(3):
        M.render(st, 3840, 2160, bg=(100, 100, 100))
    dt = (time.time() - t0) / 3
    print(f"4K busy render {dt:.2f} s")
    assert dt < 2.5


def test_font_glyph_decode_memo_matches():
    """Same glyph id repeated: memoised bitmaps give the same picture as a map of distinct copies of that glyph."""
    a, b = D.Img(), D.Img()
    a.map([(18, [a.c1(1, 1, 4)] * 30)])
    b.map([(18, [b.c1(1, 1, 4) for _ in range(30)])])
    assert np.array_equal(a.render(), b.render())


class Bus:
    """Minimal XRAM stand-in for the OSD port: rd / put / flush."""

    def __init__(self):
        self.x = {}

    def rd(self, a, n=1, space="xram"):
        return bytes(self.x.get(a + i, 0) for i in range(n))

    def put(self, cmd: str):
        m = re.match(r"set memory xram 0x([0-9a-f]+) 0x([0-9a-f]+)", cmd)
        self.x[int(m.group(1), 16)] = int(m.group(2), 16)

    def flush(self):
        pass


def _w(m, o, a, v):
    m.x[a] = v
    o.on_write(m, a)


def _addr(m, o, addr, sel, bytesel=7):
    _w(m, o, M.WOPT, bytesel << 5 | sel << 2)
    _w(m, o, M.ADR_MSB, addr >> 8)
    _w(m, o, M.ADR_LSB, addr & 255)


def _read(m, o, n):
    out = []
    for _ in range(n):
        out.append(m.x[M.DATA])
        o.on_read(m, M.DATA)
    return out


def test_sram_read_back_conditions():
    m, o = Bus(), M.OsdModel()
    _addr(m, o, 0x10, 0)
    for v in (1, 2, 3, 4, 5, 6):
        _w(m, o, M.DATA, v)                                            # words 0x10 = 1,2,3 and 0x11 = 4,5,6 (window SRAM)
    m.x[0x3A33], m.x[0x3A02], m.x[0x3AC0], m.x[0x6C] = 0x10, 0, 0, 0     # sram_read_en, circuit off, scale-up off, overlay off
    _addr(m, o, 0x10, 0)
    assert _read(m, o, 6) == [0, 0, 0, 1, 2, 3]                           # first pass = stale, second pass = the word
    assert _read(m, o, 6) == [1, 2, 3, 4, 5, 6]                           # next word (auto increment): stale = the word read before
    m.x[0x3A02] = 1                                                      # circuit on: the scan engine owns the SRAM -> junk
    _addr(m, o, 0x10, 0)
    assert _read(m, o, 6)[3:] == [0x48, 0x11, 0x30]
    m.x[0x3A02], m.x[0x3AC0] = 0, 0x80                                   # scale-up on: junk too
    _addr(m, o, 0x10, 0)
    assert _read(m, o, 6)[3:] == [0x48, 0x11, 0x30]
    m.x[0x3AC0], m.x[0x3A33] = 0, 0x00                                   # read function off: nothing queued, the cell keeps the last write
    _addr(m, o, 0x10, 0)
    assert o.rdq == []


def test_sram_read_back_single_byte_select():
    m, o = Bus(), M.OsdModel()
    _addr(m, o, 0x20, 2)
    for v in (7, 8, 9):
        _w(m, o, M.DATA, v)
    m.x[0x3A33], m.x[0x3A02], m.x[0x3AC0], m.x[0x6C] = 0x10, 0, 0, 0
    _addr(m, o, 0x20, 2, bytesel=2)                                       # byte 1 only
    assert _read(m, o, 2) == [0, 8]


# --- coverage table ---------------------------------------------------------------------------------------------------
COVER = ROOT / "docs/osd/sim-coverage.tsv"
STATUS = {"modelled", "spec-model", "unmodelled", "not-visible"}
EVID = {"hw", "databook", "spec", "sdk-hypothesis", "unknown"}


def _rows():
    with COVER.open() as f:
        return list(csv.DictReader(f, delimiter="\t"))


def test_coverage_table_columns_and_values():
    rows = _rows()
    assert len(rows) >= 60
    ids = [r["feature"] for r in rows]
    assert len(ids) == len(set(ids))
    for r in rows:
        assert r["status"] in STATUS, r
        assert r["evidence"].split("+")[0] in EVID, r
        assert r["registers"] and r["note"], r
        if r["status"] == "spec-model":
            assert r["settle_test"], f"{r['feature']}: spec-model needs the test that settles it"
        if r["status"] == "unmodelled":
            assert r["settle_test"] or r["note"], r


def test_coverage_table_tests_exist():
    names = set()
    for p in (ROOT / "tests").glob("test_*.py"):
        names |= set(re.findall(r"^def (test_\w+)", p.read_text(), re.M))
    for r in _rows():
        for t in filter(None, r["test"].split(",")):
            assert t.strip() in names, f"{r['feature']}: test {t} missing"
        if r["status"] in ("modelled", "spec-model"):
            assert r["test"], f"{r['feature']}: modelled without a test"


def test_coverage_table_demos_and_regdb_registers_exist():
    for r in _rows():
        if r["demo"]:
            assert r["demo"] in D.DEMOS, r
    import gzip
    with gzip.open(ROOT / "re/regdb/RTD2795T-CG.tsv.gz", "rt") as f:
        regs = {x["register"] for x in csv.DictReader(f, delimiter="\t") if x["kind"] == "REG"}
    for r in _rows():
        for reg in re.findall(r"\b(FRAME_CTRL_[0-9A-F]{2}|OSD_SU_\w+|OSD_ADR_PORT_\w+|OSD_DATA_PORT|OSD_WRITE_OPTION|DISP_PG_\w+)\b", r["registers"]):
            assert reg in regs, f"{r['feature']}: {reg} not in the regdb"


def test_every_demo_renders_and_is_deterministic():
    for n, d in D.DEMOS.items():
        a, b = d.build().render(), d.build().render()
        assert np.array_equal(a, b) and a.shape == (360, 640, 3), n
        assert d.tag in ("hw", "databook", "spec-model") and d.caption, n


def test_conform_cases_build_and_render():
    import osd_conform as C
    assert len(C.CASES) >= 20
    for n, c in C.CASES.items():
        a = C.sim(c)
        assert a.shape == (360, 640, 3), n
        assert c.question.strip(), n


def test_conform_diff_hook(tmp_path):
    import osd_conform as C
    from PIL import Image
    c = C.CASES["C-GRID"]
    p = tmp_path / "cap.png"
    Image.fromarray(C.sim(c)).save(p)
    assert C.conform(c, p, 10, None) == 1.0                              # the model against itself
    Image.fromarray(np.zeros((360, 640, 3), np.uint8)).save(p)
    assert C.conform(c, p, 10, None) < C.MATCH
