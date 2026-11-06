"""delay_inventory.py (#54): listing parser, argument decoding, call-graph contexts, macro evaluation, compiled-out scan. Offline."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import delay_inventory as D  # noqa: E402

SRC = "{b}/tmp/sdcc-port/src/Foo/Bar.c"
RST = """\
                                     10 ;	{s}:10: void Fn(void)
      000100                         11 _Fn:
                                     12 ;	{s}:12: ScalerTimerDelayXms(20);
      000100 90 00 14         [24]   13 	mov	dptr,#0x0014
      000103 12 29 D3         [24]   14 	lcall	_ScalerTimerDelayXms
                                     15 ;	{s}:14: if(ScalerTimerPollingFlagProc(45, P71_A4_TMDS_CTRL, _BIT3, _TRUE) == _FALSE)
      000106 90 EF AE         [24]   16 	mov	dptr,#_ScalerTimerPollingFlagProc_PARM_3
      000109 74 08            [12]   17 	mov	a,#0x08
      00010B F0               [24]   18 	movx	@dptr,a
      00010C D2 30            [12]   19 	setb	(__bovl + 0x4)
      00010E 7F A4            [12]   20 	mov	r7, #0xa4
      000110 7E 71            [12]   21 	mov	r6, #0x71
      000112 90 00 2D         [24]   22 	mov	dptr,#0x002d
      000115 12 2A 34         [24]   23 	lcall	_ScalerTimerPollingFlagProc
                                     24 ;	{s}:16: ScalerTimerActiveTimerEvent(SEC(1), _EV_X);
      000118 7F 18            [12]   25 	mov	r7, #0x18
      00011A 90 03 E8         [24]   26 	mov	dptr,#0x03e8
      00011D 12 C9 34         [24]   27 	lcall	_ScalerTimerActiveTimerEvent
                                     28 ;	{s}:18: DELAY_30US_EXINT();
      000120 05 82            [12]   29 	inc	a
                                     30 ;	{s}:20: while((MCU_FF29_IIC_STATUS2 & _BIT1) == 0)
      000122 E5 82            [12]   31 	mov	a,r3
                                     32 ;	{s}:22: ScalerTimerDelayXms(x);
      000124 12 29 D3         [24]   33 	lcall	_ScalerTimerDelayXms
      000127 22               [24]   34 	ret
                                     40 ;	{s}:30: void Isr(void)
      000200                         41 _Isr:
                                     42 ;	{s}:32: Fn();
      000200 12 01 00         [24]   43 	lcall	_Fn
      000203 32               [24]   44 	reti
                                     50 ;	{s}:40: void Dead(void)
      000300                         51 _Dead:
      000300 22               [24]   52 	ret
"""
MAP = """\
C:   00000100  _Fn                                Bar
C:   00000200  _Isr                               Bar
C:   00000300  _Dead                              Bar
C:   000029D3  _ScalerTimerDelayXms               T
C:   00002A34  _ScalerTimerPollingFlagProc        T
C:   0000C934  _ScalerTimerActiveTimerEvent       T
"""


@pytest.fixture()
def build(tmp_path):
    b = tmp_path / "b"
    (b / "tmp/sdcc-port/asm_bank").mkdir(parents=True)
    (b / "tmp/sdcc-port/src/Foo").mkdir(parents=True)
    (b / "tmp/sdcc-port/asm_bank/Bar.rst").write_text(RST.format(s=SRC.format(b=b)))
    (b / "tmp/sdcc-port/src/Foo/Bar.c").write_text("\n" * 24 + "    ScalerTimerDelayXms(5);   // dead branch\n\n" + "void Dead2(void)\n{\n    DELAY_XUS(100);\n}\n")
    (tmp_path / "m.map").write_text(MAP)
    return b, tmp_path / "m.map"


def rows_of(build):
    b, m = build
    syms = D.parse_map(m)
    fns = D.parse_rst(b, syms)
    g = D.build_graph(fns)
    ctx, live = D.contexts(fns, g)
    ev = D.Eval({"SEC(x)": "((WORD)(1000U * (x)))"})
    return fns, ctx, live, ev, D.extract_sites(fns, ctx, live, ev, b)


def test_functions_stubs_and_graph(build):
    fns, ctx, live, ev, rows = rows_of(build)
    assert set(fns) == {"_Fn", "_Isr", "_Dead"} and fns["_Fn"].addr == 0x100
    assert "_Isr" in live and "_Fn" in live and "_Dead" not in live      # reti function = ISR root; Fn reached from it
    assert ctx["_Fn"] == ["isr"]


def test_delay_poll_event_arguments_come_from_the_instructions(build):
    *_, rows = rows_of(build)
    by = {(r["kind"], r["line"]): r for r in rows}
    d = by[("delay_ms", 12)]
    assert (d["value"], d["units"], d["mode"], d["function"], d["addr"]) == (20, "ms", "blind", "Fn", "0x103")
    p = by[("poll", 14)]
    assert p["value"] == 45 and "reg=0x71A4" in p["args"] and "mask=0x08" in p["args"] and "wait_for=1" in p["args"]
    assert "caller tests the result" in p["expiry"]
    e = by[("timer_event", 16)]
    assert (e["value"], e["mode"]) == (1000, "deferred") and "id=0x18" in e["args"]
    assert by[("delay_ms", 22)]["value"] == "variable"                   # argument not set just before the call


def test_us_loop_and_status_loop_rows(build):
    *_, rows = rows_of(build)
    us = next(r for r in rows if r["kind"] == "delay_us")
    assert (us["value"], us["units"], us["line"]) == (30, "us", 18)
    sl = next(r for r in rows if r["kind"] == "status_loop")
    assert sl["line"] == 20 and sl["mode"] == "polled" and "none in statement" in sl["bound"]


def test_macro_evaluator():
    ev = D.Eval({"SEC(x)": "((WORD)(1000U * (x)))", "_A": "SEC(2)", "_B": "(_A / 4)", "_C": "(BYTE)0x10 + 1"})
    assert ev.value("_A") == 2000 and ev.value("_B") == 500 and ev.value("SEC(0.1)") == 100.0 and ev.value("_C") == 17
    assert ev.value("g_ucVar + 1") is None


def test_compiled_out_rows(build):
    b, _ = build
    fns, ctx, live, ev, rows = rows_of(build)
    out = D.compiled_out(fns, b, ev, ctx)
    kinds = {(r["kind"], r["line"], r["value"]) for r in out}
    assert ("delay_ms", 25, 5) in kinds and all(r["linked"].startswith("no") for r in out)
    assert any(r["kind"] == "delay_us" and r["value"] == 100 for r in out)


def test_reasons_and_classification():
    rows = [dict(kind="delay_ms", file="a/B.c", line=7, function="F", value=10, args=""),
            dict(kind="timer_event", file="a/B.c", line=9, function="F", value=5, args=""),
            dict(kind="param", file="", line=0, function="", value=550, args="_PANEL_POWER_ON_T3")]
    reasons = [("delay_ms@B.c:7#10", "removable", "why", "cite", "", ""), ("_PANEL_POWER_ON_T3", "required", "spec", "ds", "", "")]
    out = D.classify(rows, reasons)
    assert [r["cls"] for r in out] == ["removable", "non-blocking", "required"]


ROOT_BUILD = ROOT.parent / "awto-ddc-stepB"
real = pytest.mark.skipif(not (ROOT_BUILD / "tmp/sdcc-port/asm_bank").exists() or not (ROOT / "tmp/fw/AWT26110003-wb-stepB-be.map").exists(),
                          reason="stepB build tree / map absent")


@real
def test_real_build_rows():
    syms = D.parse_map(ROOT / "tmp/fw/AWT26110003-wb-stepB-be.map")
    fns = D.parse_rst(ROOT_BUILD, syms)
    g = D.build_graph(fns)
    ctx, live = D.contexts(fns, g)
    rows = D.extract_sites(fns, ctx, live, D.Eval({}), ROOT_BUILD)
    pre = [r for r in rows if r["kind"] == "delay_ms" and r["function"] == "ScalerTMDSRx2TMDSNormalPreDetect"]
    assert [r["value"] for r in pre] == [6] and pre[0]["reachable"] == "yes" and pre[0]["context"] == "search"
    assert any(r["kind"] == "poll" and r["function"] == "ScalerTimerWaitForEvent" or r["kind"] == "wait_event" for r in rows)
    assert "_SysPowerHandler" in live and "_main" in live
