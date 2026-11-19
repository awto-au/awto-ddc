"""fw_link_check const_ptr_*_xbank (#149 c): banked const address passed to a pointer reader in another bank.
Run: python3 -m pytest tests/test_link_xbank.py"""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fw_link_check as L

CALLER = """\
_load:
\tmov\tdptr,#_blob
\tlcall\t__bs_reader
\tret
_local:
\tmov\tdptr,#_tab
\tmovc\ta,@a+dptr
\tlcall\t__bs_reader
\tret
"""
READER = """\
_reader:
\tclr\ta
\tmovc\ta,@a+dptr
\tret
"""


def chunk(area, kind, reg, syms=True):
    name = area[2:] if syms else area                  # map symbol `_x`, or a static's bare area `CH_x`
    return dict(kind=kind, name=name, area=area, reg=reg, addr=0x10000 * (reg if reg != "C" else 0), size=4)


def run(tmp_path, reader_bank, static=False):
    (tmp_path / "a.asm").write_text(CALLER)
    (tmp_path / "b.asm").write_text(READER)
    im = SimpleNamespace(chunks=[chunk("CH_blob", "const", 10, not static), chunk("CH_tab", "const", 3),
                                 chunk("CH_load", "fn", 10), chunk("CH_local", "fn", 3),
                                 chunk("CH_reader", "fn", reader_bank, not static)])
    return L.asm_const_ptr(im, tmp_path)


def test_movc_reader_other_bank(tmp_path):
    f = run(tmp_path, 9)
    assert [(x["kind"], x["src"]) for x in f] == [("const_ptr_code_xbank", "_load")]


def test_same_bank_ok(tmp_path):
    assert run(tmp_path, 10) == []


def test_caller_reads_table_itself_ok(tmp_path):
    assert all(x["src"] != "_local" for x in run(tmp_path, 9))


def test_statics_found_by_area(tmp_path):
    assert [x["src"] for x in run(tmp_path, 9, static=True)] == ["_load"]
