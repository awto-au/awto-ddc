"""Address-in-data fill / read-back (fw/test/ddr_draw.c ops 12-14, scripts/ddr_addr_test.py) on the host model of MCU_DC port A (tests/ddr_draw_host.c).

Fault models: an address bit tied low, a data bit stuck high, a stale first read, a swapped read lane order.
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import ddr_addr_test as A

SRC = (ROOT / "fw/test/ddr_draw.c").read_text()
SEED = 0x1234ABCD
pytestmark = pytest.mark.skipif(shutil.which("gcc") is None, reason="gcc missing")


@pytest.fixture(scope="module")
def exe(tmp_path_factory):
    out = tmp_path_factory.mktemp("addr") / "h"
    r = subprocess.run(["gcc", "-O1", "-Wall", "-Wextra", "-Wno-unused-function", "-o", str(out), str(ROOT / "tests/ddr_draw_host.c")], capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stderr
    return out


def run(exe, script, *model, dump=None):
    inp = script + (f"dump {dump}\n" if dump else "")
    r = subprocess.run([str(exe), *map(str, model)], input=inp, capture_output=True, text=True, timeout=300, check=False)
    assert r.returncode == 0, r.stderr
    return r.stdout.splitlines()


def setp(blk0=0, blocks=0, seed=SEED, stride=0, step=0, inv=0, swap=0, retry=0, samples=0):
    return f"set {blk0} {blocks} {seed} {stride} {step} {inv} {swap} {retry} {samples}\n"


def res(line):
    t = line.split()
    r = {t[i]: int(t[i + 1]) for i in range(0, 16, 2)}
    k = t.index("bits")
    r["bits"] = [int(v) for v in t[k + 1:k + 1 + A.IDX_BITS]]
    return r


def test_c_struct_matches_python_offsets():
    body = re.search(r"typedef struct\s*\{\s*unsigned long ulBlk0;(.*?)\}\s*StAwtoAddr;", SRC, re.DOTALL).group(0)
    sizes = {"unsigned long": 4, "WORD": 2, "BYTE": 1}
    off, names = 0, {}
    for m in re.finditer(r"^\s*(unsigned long|WORD|BYTE)\s+(\w+)((?:\[[^\]]+\])*);", body, re.MULTILINE):
        n = {"AWTO_DRW_IDX_BITS": A.IDX_BITS, "AWTO_DRW_WATCH_N": A.WATCH_N, "AWTO_DRW_REC_N": A.REC_N, "AWTO_DRW_BURST_BYTES": A.BURST_BYTES}
        cnt = 1
        for d in re.findall(r"\[([^\]]+)\]", m.group(3)):
            cnt *= n[d]
        names[m.group(2)] = off
        off += sizes[m.group(1)] * cnt
    assert off == A.SIZE
    assert names["ulChecked"] == A.OFF["checked"] and names["aulBit"] == A.OFF["bits"] and names["aucRec"] == A.OFF["rec"] and names["ucRecN"] == A.OFF["rec_n"]


def test_op_codes_match_c():
    for name, c in (("addrfill", "ADDR_FILL"), ("addrverify", "ADDR_VERIFY"), ("addrwatch", "ADDR_WATCH")):
        import ddr_draw as D
        assert int(re.search(rf"#define AWTO_DRW_OP_{c}\s+(\d+)", SRC).group(1)) == D.OPS[name]


def test_shown_block_numbers():
    assert A.SHOWN_UNITS == 1555200 and A.SHOWN_BURSTS == 777600 and A.SHOWN_BURSTS * A.BURST_BYTES == 12441600 and A.SHOWN_BLOCKS == 6075


@pytest.mark.parametrize("inv", [0, 1])
def test_fill_matches_python_pattern(exe, tmp_path, inv):
    dump = tmp_path / "m.bin"
    run(exe, setp(inv=inv) + "12 0 0 0 0 0 0 0 0\n", dump=dump)
    mem = dump.read_bytes()
    for b in list(range(600)) + list(range(A.SHOWN_BURSTS - 600, A.SHOWN_BURSTS)) + list(range(0, A.SHOWN_BURSTS, 997)):
        assert mem[16 * b:16 * b + 16] == A.burst_bytes(b, SEED, bool(inv)), b
    assert mem[16 * A.SHOWN_BURSTS:16 * A.SHOWN_BURSTS + 64] == bytes(64)       # nothing written past the block


@pytest.mark.parametrize("inv", [0, 1])
def test_clean_readback(exe, inv):
    out = run(exe, setp(inv=inv) + "12 0 0 0 0 0 0 0 0\n" + setp(inv=inv) + "13 0 0 0 0 0 0 0 0\naddr\n")
    r = res(out[2])
    assert r["checked"] == A.SHOWN_BURSTS and r["bad"] == 0 and r["tmo"] == 0 and "hazards 0" in out[1]


def test_address_bit_tied_low_shows_in_bit_table(exe):
    out = run(exe, setp() + "12 0 0 0 0 0 0 0 0\n" + setp() + "13 0 0 0 0 0 0 0 0\naddr\n", 0, 12)
    r = res(out[2])
    assert r["bad"] > 0 and r["bits"][12] > 0 and sum(r["bits"][:12]) == 0 and sum(r["bits"][13:]) == 0
    assert r["bad"] == r["bits"][12]


def test_stuck_data_bit_needs_both_passes(exe):
    one = run(exe, setp() + "12 0 0 0 0 0 0 0 0\n" + setp() + "13 0 0 0 0 0 0 0 0\naddr\n", 0, -1, 5 * 8 + 3)
    inv = run(exe, setp(inv=1) + "12 0 0 0 0 0 0 0 0\n" + setp(inv=1) + "13 0 0 0 0 0 0 0 0\naddr\n", 0, -1, 5 * 8 + 3)
    a, b = res(one[2]), res(inv[2])
    assert a["bad"] + b["bad"] > 0 and a["bad"] != b["bad"]            # lane byte 5 = 0xA5 has bit 3 low or high depending on the pass
    assert a["data"] == a["bad"] and b["data"] == b["bad"]             # index right, data wrong


def test_swapped_read_lanes_and_stale_reads(exe):
    bad_wrong = res(run(exe, setp() + "12 0 0 0 0 0 0 0 0\n" + setp(swap=0) + "13 0 0 0 0 0 0 0 0\naddr\n", 0, -1, -1, 1)[2])
    ok = res(run(exe, setp() + "12 0 0 0 0 0 0 0 0\n" + setp(swap=1) + "13 0 0 0 0 0 0 0 0\naddr\n", 0, -1, -1, 1)[2])
    assert bad_wrong["bad"] == A.SHOWN_BURSTS and ok["bad"] == 0
    single = res(run(exe, setp() + "12 0 0 0 0 0 0 0 0\n" + setp(swap=1) + "13 0 0 0 0 0 0 0 0\naddr\n", 0, -1, -1, 1, 1000)[2])
    double = res(run(exe, setp() + "12 0 0 0 0 0 0 0 0\n" + setp(swap=1, retry=2) + "13 0 0 0 0 0 0 0 0\naddr\n", 0, -1, -1, 1, 1000)[2])
    assert single["bad"] > 0 and single["stale"] == 0 and double["bad"] == 0 and double["stale"] > 0


def test_beyond_block_and_stride(exe):
    out = run(exe, setp(blk0=6075, blocks=6075) + "12 0 0 0 0 0 0 0 0\n" + setp(blk0=6075, blocks=100, stride=50) + "13 0 0 0 0 0 0 0 0\naddr\n")
    r = res(out[2])
    assert r["checked"] == 100 * A.BLOCK_BURSTS and r["bad"] == 0


def test_python_decode_and_bits():
    b = A.burst_bytes(12345, SEED, True)
    assert A.decode_index(b, SEED, True) == 2 * 12345
    assert A.diff_bits(0b1010, 0b0010) == [3] and A.diff_bits(5, 5) == []
    raw = bytearray(A.SIZE)
    raw[A.OFF["bad"] + 3] = 7
    raw[A.OFF["bits"] + 4 * 12 + 3] = 7
    raw[A.OFF["rec_n"]] = 1
    raw[A.OFF["rec_idx"] + 3] = 9
    raw[A.OFF["rec"]:A.OFF["rec"] + 16] = b.ljust(16, b"\0")
    r = A.parse_result(bytes(raw))
    assert r["bad"] == 7 and r["bits"][12] == 7 and r["first"][0][0] == 9 and r["first"][0][1] == b
    assert "bad 7" in A.decode_line(r, SEED, True) and "b12=7" in A.decode_line(r, SEED, True)
