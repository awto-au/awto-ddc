"""dw8051_sweep: .rst function parse, #360 guard-prologue detection, single-bit compare regex."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import dw8051_sweep as D

RST = """\
                                    10 ;	 function Guarded
      0E5EA6                        11 _Guarded:
      0E5EA6 90 E2 53         [24]  12 	mov	dptr,#_g_ucState
      0E5EA9 E0               [24]  13 	movx	a,@dptr
      0E5EAA 70 01            [24]  14 	jnz	00102$
      0E5EAC 22               [24]  15 	ret
      0E5EAD                        16 00102$:
      0E5EAD 12 01 00         [24]  17 	lcall	_Work
      0E5EB0 12 01 00         [24]  18 	lcall	_Work
      0E5EB3 12 01 00         [24]  19 	lcall	_Work
      0E5EB6 22               [24]  20 	ret
      0E5EB7                        21 _ParmOnly:
      0E5EB7 90 E2 53         [24]  22 	mov	dptr,#_ParmOnly_PARM_2
      0E5EBA E0               [24]  23 	movx	a,@dptr
      0E5EBB 70 01            [24]  24 	jnz	00103$
      0E5EBD 22               [24]  25 	ret
      0E5EBE 12 01 00         [24]  26 	lcall	_Work
      0E5EC1 12 01 00         [24]  27 	lcall	_Work
      0E5EC4 22               [24]  28 	ret
      0D0000                        29 _Caller:
      0D0000 12 00 08         [24]  30 	lcall	__bs_Guarded
      0D0003 22               [24]  31 	ret
"""


def test_guard_candidate_and_site(tmp_path):
    (tmp_path / "m.rst").write_text(RST)
    fns = D.rst_functions(tmp_path)
    assert set(fns) == {"_Guarded", "_ParmOnly", "_Caller"}
    c = D.guard_candidates(fns)
    assert list(c) == ["_Guarded"] and c["_Guarded"]["sym"] == "_g_ucState" and c["_Guarded"]["rets"] == [0x0E5EAC]
    assert D.call_sites(fns, set(c)) == [("_Caller", "b13", "_Guarded", "stub lcall")]


def test_single_bit_regex():
    assert D.SINGLE_BIT.search("if((ucX & _BIT3) == _BIT3)")
    assert D.SINGLE_BIT.search("if((ucX & 0x40) != 0x40)")
    assert not D.SINGLE_BIT.search("if((ucX & 0x7F) != 0x7F)")
    assert not D.SINGLE_BIT.search("if((ucX & _BIT3) == _BIT2)")
