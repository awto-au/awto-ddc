"""fw/test/ddr_draw.c (#267) compiled on the host against a model of MCU_DC port A + the frame buffer (tests/ddr_draw_host.c).

Reference = independent per-pixel spec (3 B per pixel B, G, R; 1440-unit line pitch; screen row = 2 x memory line; halves swapped by the model).
No model of the real DCU: layout truth is the hardware (#255); this checks the firmware's own geometry, clipping, edge masks and CMD / address discipline.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ddr_draw as D  # noqa: E402

SW, SH, LINE_BYTES, UNITS = 3840, 2160, 3840 * 3, 3110400
MEM = UNITS * 8
SRC = (ROOT / "fw/test/ddr_draw.c").read_text()

pytestmark = pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc missing")


@pytest.fixture(scope="module")
def exe(tmp_path_factory):
    out = tmp_path_factory.mktemp("ddr") / "ddr_draw_host"
    r = subprocess.run(["gcc", "-O1", "-Wall", "-Wextra", "-Wno-unused-function", "-o", str(out), str(ROOT / "tests/ddr_draw_host.c")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return out


def run(exe, tmp_path, cmds, busy=2):
    dump = tmp_path / "mem.bin"
    inp = "".join(f"{D.OPS[op]} {x} {y} {w} {h} {rgb[0]} {rgb[1]} {rgb[2]} {n}\n" for op, x, y, w, h, rgb, n in cmds) + f"dump {dump}\n"
    r = subprocess.run([str(exe), str(busy)], input=inp, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    st = [dict(zip(l.split()[::2], map(int, l.split()[1::2]))) for l in r.stdout.splitlines()]
    return bytearray(dump.read_bytes()), st


def cmd(op, x=0, y=0, w=0, h=0, rgb=(0, 0, 0), n=0):
    return (op, x, y, w, h, rgb, n)


def put(ref, x, m, rgb):
    o = m * LINE_BYTES + 3 * x
    ref[o:o + 3] = bytes((rgb[2], rgb[1], rgb[0]))


def rect_ref(ref, x, y, w, h, rgb):
    w, h = min(w, SW - x), min(h, SH - y)
    px = bytes((rgb[2], rgb[1], rgb[0])) * w
    for m in range(y // 2, (y + h - 1) // 2 + 1):
        ref[m * LINE_BYTES + 3 * x:m * LINE_BYTES + 3 * (x + w)] = px


def ring_ref(ref, x, y, d, rgb):
    for j in range(d):
        for i in range(d):
            u, v = 2 * i - (d - 1), 2 * j - (d - 1)
            if (d - 2) ** 2 < u * u + v * v <= d * d:
                put(ref, x + i, (y + j) // 2, rgb)


def pal(i):
    return D_PAL[i]


D_PAL = [(255, 0, 0), (255, 128, 0), (255, 255, 0), (0, 255, 0), (0, 255, 255), (0, 0, 255), (128, 0, 255), (255, 0, 255), (160, 82, 45), (128, 128, 128)]
WHITE = (255, 255, 255)


def grid_ref(ref, x, y, side, n):
    step = side // n
    for k in range(n + 1):
        c = pal(k % 10 if k < n else 9)
        rect_ref(ref, x + (k * step if k < n else side - 1), y, 1, side, c)
    for k in range(n + 1):
        c = pal(k % 10 if k < n else 9)
        rect_ref(ref, x, y + (k * step if k < n else side - 1), side, 1, c)


def check(exe, tmp_path, cmds, ref, busy=2, ok=1):
    mem, st = run(exe, tmp_path, cmds, busy)
    assert all(s["hazards"] == 0 for s in st), st
    assert [s["state"] for s in st] == [2] * len(st) if ok else True, st
    assert mem == ref
    return st


C_NAME = {"fill": "FILL_RECT", "frame": "FILL_FRAME", "gradh": "GRAD_H", "gradv": "GRAD_V"}


def test_op_codes_match_c():
    for name, code in D.OPS.items():
        m = re.search(rf"#define AWTO_DRW_OP_{C_NAME.get(name, name.upper())}\s+(\d+)", SRC)
        assert m and int(m.group(1)) == code, name
    off = 0
    for field, size in (("ucGo", 1), ("ucSeq", 1), ("ucState", 1), ("ucFrozen", 1), ("usX", 2), ("usY", 2), ("usW", 2), ("usH", 2), ("ucR", 1), ("ucG", 1),
                        ("ucB", 1), ("ucN", 1), ("usMs", 2), ("ulBursts", 4), ("ucSlow", 1)):
        assert re.search(rf"\b{field};", SRC)
        assert getattr(D, "O_" + {"ucGo": "GO", "ucSeq": "SEQ", "ucState": "STATE", "ucFrozen": "FROZEN", "usX": "X", "usY": "Y", "usW": "W", "usH": "H", "ucR": "R",
                                 "ucG": "G", "ucB": "B", "ucN": "N", "usMs": "MS", "ulBursts": "BURSTS", "ucSlow": "SLOW"}[field]) == off, field
        off += size


def test_c_layout_constants():
    def c(name):
        return eval(re.search(rf"#define {name}\s+(\(?[^/\n]*?)\s*(?://|$)", SRC, re.M).group(1).strip().rstrip("UL"), {"AWTO_DRW_SCREEN_W": 3840})
    assert c("AWTO_DRW_SCREEN_W") == SW and c("AWTO_DRW_SCREEN_H") == SH and c("AWTO_DRW_BPP") == 3
    assert (D.SCREEN_W, D.SCREEN_H, D.LINE_DOUBLE, D.BPP, D.BURST) == (SW, SH, 2, 3, 16)


@pytest.mark.parametrize("x,y,w,h", [(5, 7, 101, 33), (0, 0, 16, 2), (16, 1, 16, 1), (3830, 2150, 100, 100), (1, 2158, 3838, 5), (2, 4, 1, 1)])
def test_fill_rect(exe, tmp_path, x, y, w, h):
    ref = bytearray(MEM)
    rect_ref(ref, x, y, w, h, (200, 100, 50))
    check(exe, tmp_path, [cmd("fill", x, y, w, h, (200, 100, 50))], ref)


@pytest.mark.parametrize("busy", [0, 1, 7, 300])
def test_cmd_busy_discipline(exe, tmp_path, busy):
    ref = bytearray(MEM)
    rect_ref(ref, 77, 11, 1500, 40, (9, 99, 199))
    st = check(exe, tmp_path, [cmd("fill", 77, 11, 1500, 40, (9, 99, 199))], ref, busy=busy)
    assert (st[0]["slow"] > 0) == (busy > 255)


def test_lines(exe, tmp_path):
    ref = bytearray(MEM)
    rect_ref(ref, 100, 50, 777, 1, (255, 0, 255))
    rect_ref(ref, 900, 20, 1, 333, (0, 255, 0))
    check(exe, tmp_path, [cmd("hline", 100, 50, 777, rgb=(255, 0, 255)), cmd("vline", 900, 20, 0, 333, (0, 255, 0))], ref)


@pytest.mark.parametrize("d", [3, 7, 100, 101, 640])
def test_circle(exe, tmp_path, d):
    ref = bytearray(MEM)
    ring_ref(ref, 1700, 1000, d, WHITE)
    check(exe, tmp_path, [cmd("circle", 1700, 1000, d, rgb=WHITE)], ref)


def test_grid_and_figure(exe, tmp_path):
    ref = bytearray(MEM)
    grid_ref(ref, 1700, 1000, 100, 10)
    ring_ref(ref, 1700, 1000, 100, WHITE)
    check(exe, tmp_path, [cmd("figure", 1700, 1000)], ref)
    ref = bytearray(MEM)
    grid_ref(ref, 33, 61, 97, 4)
    check(exe, tmp_path, [cmd("grid", 33, 61, 97, n=4)], ref)


def test_figure_grid_matches_ddr_grid100(exe, tmp_path):
    import ddr_grid100 as G
    mem, st = run(exe, tmp_path, [cmd("figure", 1700, 1000)])
    for (x, m), c in G.compose(1700, 1000).items():
        if c != G.CIRCLE:                                     # the host script's circle is a 1440-step sampling: lines only
            o = m * LINE_BYTES + 3 * x
            assert tuple(mem[o:o + 3]) == (c[2], c[1], c[0]) or tuple(mem[o:o + 3]) == (255, 255, 255), (x, m)


def test_bars(exe, tmp_path):
    ref = bytearray(MEM)
    bars = [(255, 255, 255), (255, 255, 0), (0, 255, 255), (0, 255, 0), (255, 0, 255), (255, 0, 0), (0, 0, 255), (0, 0, 0)]
    x, y, w, h = 7, 10, 803, 51
    for i, c in enumerate(bars):
        rect_ref(ref, x + w * i // 8, y, (w * (i + 1) // 8) - (w * i // 8), h, c)
    check(exe, tmp_path, [cmd("bars", x, y, w, h)], ref)


def test_frame_and_gradients(exe, tmp_path):
    ref = bytearray(MEM)
    rect_ref(ref, 0, 0, SW, SH, (1, 2, 3))
    st = check(exe, tmp_path, [cmd("frame", rgb=(1, 2, 3))], ref)
    assert st[0]["bursts"] == 1080 * 720
    ref = bytearray(MEM)
    for m in range(1080):
        rect_ref(ref, 0, 2 * m, SW, 2, ((m * 255 // 1079),) * 3)
    check(exe, tmp_path, [cmd("gradv")], ref)
    ref = bytearray(MEM)
    for b in range(240):
        rect_ref(ref, 16 * b, 0, 16, SH, ((b * 255 // 239),) * 3)
    check(exe, tmp_path, [cmd("gradh")], ref)


def test_masktest(exe, tmp_path):
    ref = bytearray(MEM)
    b0 = 3 * (160 // 16)
    base = 20 * LINE_BYTES
    for j in range(16):
        ref[base + 16 * (b0 + j) + j] = 255
    check(exe, tmp_path, [cmd("masktest", 160, 40)], ref)


def test_refused(exe, tmp_path):
    ref = bytearray(MEM)
    mem, st = run(exe, tmp_path, [cmd("fill", 5, 5, 0, 10), cmd("fill", 4000, 5, 10, 10), cmd("circle", 3800, 5, 100), cmd("grid", 0, 0, 5, 0)])
    assert [s["state"] for s in st] == [3, 3, 3, 3] and mem == ref


def test_stall_aborts(exe, tmp_path):
    mem, st = run(exe, tmp_path, [cmd("fill", 0, 0, 3840, 2160, (5, 5, 5))], busy=-1)
    assert st[0]["state"] == 4 and st[0]["bursts"] < 100


def test_script_resolves_map_symbol(tmp_path):
    m = tmp_path / "x.map"
    m.write_text("D:   0000F51A  _g_stAwtoDraw                      ddr_draw\n")
    assert D.SW.sym(m, "g_stAwtoDraw") == 0xF51A
