"""CEC message layer (fw/cec/cec_msg.c) compiled on the host, name tables, registry rows, sync decoder (docs/cec.md)."""
from __future__ import annotations

import ctypes
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

pytestmark = pytest.mark.skipif(shutil.which("gcc") is None, reason="no host C compiler")

TV, BCAST, UNKNOWN = 0, 15, 0x10
PA_TV, ON, STANDBY = 0x0000, 0, 1


class Reply(ctypes.Structure):
    _fields_ = [("dest", ctypes.c_ubyte), ("len", ctypes.c_ubyte), ("db", ctypes.c_ubyte * 16), ("hook", ctypes.c_ubyte)]


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    so = tmp_path_factory.mktemp("cec") / "cec_msg.so"
    subprocess.run(["gcc", "-shared", "-fPIC", "-Wall", "-Wextra", "-Werror", "-DCEC_CODE=", "-o", str(so), str(ROOT / "fw/cec/cec_msg.c")], check=True)
    d = ctypes.CDLL(str(so))
    d.CecMsgRx.restype = ctypes.c_ubyte
    d.CecMsgRx.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_char_p, ctypes.c_ubyte, ctypes.c_ushort, ctypes.c_ubyte, ctypes.POINTER(Reply)]
    return d


def rx(lib, init, db: bytes, dest=UNKNOWN, power=ON):
    r = Reply()
    n = lib.CecMsgRx(init, dest, db, len(db), PA_TV, power, ctypes.byref(r))
    assert n == r.len
    return r.dest, bytes(r.db[:r.len]), r.hook


def test_physical_address_is_a_broadcast_with_device_type_tv(lib):
    assert rx(lib, 4, b"\x83") == (BCAST, b"\x84\x00\x00\x00", 0)


def test_vendor_id_is_the_awto_oui(lib):
    assert rx(lib, 4, b"\x8c") == (BCAST, b"\x87\xa7\x70\xd0", 0)
    assert "AWTO_OUI = 0xA770D0" in (ROOT / "scripts/make_edid.py").read_text()


def test_version_name_power(lib):
    assert rx(lib, 4, b"\x9f") == (4, b"\x9e\x05", 0)
    assert rx(lib, 8, b"\x46") == (8, b"\x47awto-mon", 0)
    assert rx(lib, 4, b"\x8f", power=ON)[1] == b"\x90\x00"
    assert rx(lib, 4, b"\x8f", power=STANDBY)[1] == b"\x90\x01"


def test_osd_name_matches_the_edid_name(lib):
    assert "awto-mon" in (ROOT / "scripts/make_edid.py").read_text()


@pytest.mark.parametrize("op,hook", [(0x36, 1), (0x04, 2), (0x0D, 2), (0x82, 3), (0x86, 3), (0x81, 3), (0x80, 3), (0x44, 4), (0x45, 4)])
def test_hooks_are_reported_never_answered(lib, op, hook):
    assert rx(lib, 4, bytes([op, 0x10, 0x00])) == (4, b"", hook)


def test_unsupported_directed_opcode_is_aborted(lib):
    assert rx(lib, 4, b"\x1a", dest=TV) == (4, b"\x00\x1a\x00", 0)
    assert rx(lib, 4, b"\x1a") == (4, b"\x00\x1a\x00", 0)


def test_broadcast_opcodes_are_not_aborted_with_unknown_destination(lib):
    for op in (0x32, 0x89, 0x8A, 0xA0):
        assert rx(lib, 4, bytes([op, 0x01]))[1] == b""
    assert rx(lib, 4, b"\x89\x01", dest=TV)[1] == b"\x00\x89\x00"       # known directed: abort


def test_abort_message_is_refused(lib):
    assert rx(lib, 4, b"\xff") == (4, b"\x00\xff\x04", 0)


def test_no_reply_to_a_broadcast_or_a_poll_or_an_abort(lib):
    assert rx(lib, 4, b"\x83", dest=BCAST)[1] == b""
    assert rx(lib, 4, b"")[1] == b""
    assert rx(lib, 4, b"\x00\x8f\x04")[1] == b""
    assert rx(lib, BCAST, b"\x83")[1] == b""                           # a frame from the broadcast address is invalid


def test_announcements_from_others_get_no_reply(lib):
    for db in (b"\x84\x10\x00\x04", b"\x87\x00\x80\x45", b"\x90\x00", b"\x9e\x05", b"\x47hi", b"\x85", b"\x9d\x10\x00"):
        assert rx(lib, 4, db)[1] == b""


def test_opcode_name_table_matches_the_firmware_console():
    tsv = [ln.split("\t") for ln in (ROOT / "fw/cec/opcodes.tsv").read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    src = (ROOT / "fw/osd/console.c").read_text()
    ops = re.search(r"tAwtoCecOp\[\] = \{([^}]*)\}", src).group(1)
    assert [int(x, 16) for x in re.findall(r"0x[0-9A-Fa-f]+", ops)] == [int(o, 16) for o, _ in tsv]
    names = re.search(r"tAwtoCecNameS\[\] =(.*?);", src, re.DOTALL).group(1)
    names = "".join(re.findall(r'"([^"]*)"', names)).split("\\0")
    assert names[:len(tsv)] == [n for _, n in tsv]
    assert names[len(tsv):len(tsv) + 4] == ["acked", "line error", "no ack (header)", "no ack (data)"]
    assert names[27:31] == ["hook:Standby", "hook:wake", "hook:Active Source", "hook:User Control"]
    assert names[31].startswith("dropped")


def test_host_decoder_lines():
    import sync_log as SL
    hdr = 0x40 << 24
    assert SL.cec_line(0x80 | 1 << 3 | 0, hdr | 0x83 << 16) == "rx 4>? Give Physical Address"
    assert SL.cec_line(4 << 3 | 1, 0x0F << 24 | 0x84 << 16) == "tx 0>F Report Physical Address 00 00+"
    assert SL.cec_line(0, hdr) == "rx 4>0 poll"
    assert SL.cec_line(2, 1) == "tx result:acked"
    assert SL.cec_line(3, 1) == "block on"
    assert SL.cec_line(0x80 | 1 << 3, 0x40 << 24 | 0x1A << 16) == "rx 4>? op 1A"


def test_registry_rows():
    cols = ["id", "name", "type", "unit", "group", "flags", "min", "max", "step", "default", "nv_slot", "vcp", "apply", "label", "options", "note"]
    rows = {f[1]: dict(zip(cols, f)) for f in (ln.split("\t") for ln in (ROOT / "fw/rtdfw/settings/registry.tsv").read_text().splitlines()
                                              if ln.strip() and not ln.startswith("#"))}
    assert rows["cec_en"]["default"] == "1" and rows["cec_en"]["type"] == "bool"      # Dan 2026-11-19: CEC on
    assert rows["cec_ctl"]["default"] == "0"                                        # hooks logged only
    assert {"nv", "live"} <= set(rows["cec_en"]["flags"].split(","))


def test_edid_physical_addresses_per_hdmi_port():
    import make_edid as E
    for port, pa in (("hdmi", b"\x10\x00"), ("hdmi-d3", b"\x20\x00")):
        cta = E.build(port)[128:]
        i = cta.index(bytes([(3 << 5) | 7, 0x03, 0x0C, 0x00]))
        assert cta[i + 4:i + 6] == pa, port
        assert sum(cta) & 0xFF == 0
    assert b"\x03\x0c\x00" not in E.build("dp")[128:]


def test_firmware_cec_sim_when_an_image_exists():
    img = sorted((ROOT / "tmp/fw").glob("AWT*-be.bin"), key=lambda p: p.stat().st_mtime)
    if not img:
        pytest.skip("no firmware image in tmp/fw")
    mp = img[-1].with_suffix(".map")
    if "_SysCecHandler" not in mp.read_text(errors="replace"):
        pytest.skip("newest image has no CEC code")
    r = subprocess.run([sys.executable, str(ROOT / "scripts/cec_sim.py"), str(img[-1]), str(mp)], capture_output=True, text=True, timeout=240,
                       env={**__import__("os").environ, "AWTO_SIM_CORE": "fast"})
    assert r.returncode == 0 and "FAIL" not in r.stdout, r.stdout[-2000:]
