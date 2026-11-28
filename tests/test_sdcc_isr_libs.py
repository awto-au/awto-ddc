"""sdcc_isr_libs.src_of: asm helper symbol -> library source, old (`__X`) and new (`___X`, sdcc 3e1e3c3dde) helper names."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import sdcc_isr_libs as L


class _Log:
    def __init__(self):
        self.lines = []

    def say(self, s):
        self.lines.append(s)


def _lib(tmp_path, monkeypatch):
    (tmp_path / "_mullong.c").write_text("long _mullong(long a, long b) { return a * b; }\n")
    (tmp_path / "__memcpy.c").write_text("void *__memcpy(void *d, const void *s, int n) { return d; }\n")
    (tmp_path / "_divulong_keil.s").write_text("\t.area CSEG (CODE)\n___divulong_keil::\n\tret\n")
    monkeypatch.setattr(L, "DIRS", [tmp_path])
    monkeypatch.setattr(L, "LOG", _Log())


def test_stems():
    assert L.lib_stems("___mullong") == ["__mullong", "_mullong"]
    assert L.lib_stems("__gptrget") == ["_gptrget"]


def test_new_and_old_helper_names_find_the_same_source(tmp_path, monkeypatch):
    _lib(tmp_path, monkeypatch)
    assert L.src_of("___mullong") == tmp_path / "_mullong.c"       # new name
    assert L.src_of("__mullong") == tmp_path / "_mullong.c"        # old name
    assert L.src_of("___memcpy") == tmp_path / "__memcpy.c"        # C name with two underscores


def test_stateless_asm_and_missing_helper_are_logged(tmp_path, monkeypatch):
    _lib(tmp_path, monkeypatch)
    assert L.src_of("___divulong_keil") is None
    assert L.src_of("___nosuch") is None
    assert any("_divulong_keil.s (asm, no RAM state)" in s for s in L.LOG.lines)
    assert any("___nosuch: no library source found" in s for s in L.LOG.lines)
