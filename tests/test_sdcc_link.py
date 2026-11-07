"""sdcc_link library line + linker gate (awto-sdcc#20). Run: python3 -m pytest tests/test_sdcc_link.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sdcc_link as SL  # noqa: E402
import sdcc_tools as T  # noqa: E402

DUP = "?ASlink-Warning-Definition of public symbol '_abs' found more than once:"


def _lk(tmp_path, libs):
    ihx = tmp_path / "fw.ihx"
    ihx.with_suffix(".lk").write_text("-muwx\n-i fw.ihx\n-C 0x100000\n" + "".join(libs) + "x.rel\n-e\n")
    return ihx


def test_one_lib_dir_and_lib():
    cmd = SL.with_libs(["sdcc", "-mmcs51", "-L/other/install/lib", "-lfoo", "-o", "x.ihx", "a.rel"])
    assert [c for c in cmd if c.startswith(("-L", "-l", "--nostdlib"))] == T.LINK_LIBS
    assert cmd.index("--nostdlib") < cmd.index("-o")


def test_lk_with_second_install_refused(tmp_path):
    ok = _lk(tmp_path, [f"-k {T.LIB}\n", "-l mcs51\n"])
    assert SL.check_lk(ok.with_suffix(".lk")) == ""
    bad = _lk(tmp_path, [f"-k {T.LIB}\n", "-k /x/rc-be-install/share/sdcc/lib/large-be-sc1\n", "-l mcs51\n"])
    assert "library dirs" in SL.check_lk(bad.with_suffix(".lk"))


def test_any_linker_warning_fails(tmp_path):
    ihx = _lk(tmp_path, [f"-k {T.LIB}\n", "-l mcs51\n"])
    r = SL._sdld([sys.executable, "-c", f"print({DUP!r})"], ihx)
    assert r.returncode and "link: " + DUP in r.stdout
    r = SL._sdld([sys.executable, "-c", "print('ok')"], ihx)
    assert r.returncode == 0


def test_banked_rom_proof(tmp_path):
    lk = _lk(tmp_path, []).with_suffix(".lk")
    m = tmp_path / "fw.map"
    m.write_text("CH_a                                00045000    00000100 =         256. bytes (REL,CON,CODE)\n")
    assert SL.banked_rom_ok(lk, m) == ""
    m.write_text("CH_a                                0004FF80    00000100 =         256. bytes (REL,CON,CODE)\n")
    assert "across a bank" in SL.banked_rom_ok(lk, m)
