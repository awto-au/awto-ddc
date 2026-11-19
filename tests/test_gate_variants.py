"""Gates on variant images (-D _AWTO_OSD_HWTEST, -D AWTO_CLOCK_MHZ=N): the expectation follows the image's build defines (docs/gates-report.md, Variants)."""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import delay_audit as DA
import fw_gates as G
import image_variant as IV
import xdata_layout as XL


def test_parse_defines():
    assert IV.parse_defines([]) == {"hwtest": False, "clock": IV.DEFAULT_CLOCK_MHZ, "variant": False}
    assert IV.parse_defines(["_AWTO_OSD_HWTEST", "-DAWTO_CLOCK_MHZ=175"]) == {"hwtest": True, "clock": 175, "variant": True}
    assert IV.parse_defines(["AWTO_CLOCK_MHZ=87"])["variant"] and not IV.parse_defines(["AWTO_CLOCK_MHZ=350"])["variant"]
    assert IV.parse_defines(["_AWTO_OSD_HWTEST=_ON"])["hwtest"] is True
    assert IV.parse_defines(["AWTO_CLOCK_MHZ=abc"])["clock"] == IV.DEFAULT_CLOCK_MHZ


def _image(tmp_path, defines=None, sym=""):
    b = tmp_path / "t-be.bin"
    b.write_bytes(b"x")
    b.with_suffix(".map").write_text(f"C: 00000000 {sym}\n")
    if defines is not None:
        (tmp_path / "t-be.build.json").write_text(json.dumps({"defines": defines}))
        (tmp_path / "t-be.xdata_layout.tsv").write_text(XL.HEAD + "\n")
    return b


def test_variant_from_build_json(tmp_path):
    v = IV.of_image(_image(tmp_path, ["_AWTO_OSD_HWTEST", "AWTO_CLOCK_MHZ=87"]))
    assert v["hwtest"] and v["clock"] == 87 and v["layout"].endswith("t-be.xdata_layout.tsv")


def test_clock_variant_uses_its_own_layout(tmp_path):
    v = IV.of_image(_image(tmp_path, ["AWTO_CLOCK_MHZ=175"]))
    assert not v["hwtest"] and v["clock"] == 175 and v["layout"].endswith("t-be.xdata_layout.tsv")


def test_default_image_keeps_the_tracked_layout(tmp_path):
    v = IV.of_image(_image(tmp_path, []))
    assert not v["hwtest"] and v["layout"] == ""


def test_image_without_build_json_falls_back_to_the_map(tmp_path):
    assert IV.of_image(_image(tmp_path, None, " _g_stAwtoOsdHw"))["hwtest"] is True
    assert IV.of_image(_image(tmp_path, None, " _other"))["hwtest"] is False


def _cmd(tmp_path, defines):
    g = G.gates(_image(tmp_path, defines), tmp_path / "t-be.map", None, ROOT)
    return [str(x) for x in g["xlayout"]], [str(x) for x in g["delays"]]


def test_gates_pass_the_variant_to_xlayout_and_delays(tmp_path):
    xl, dl = _cmd(tmp_path, ["_AWTO_OSD_HWTEST"])
    assert "--layout" in xl and xl[xl.index("--layout") + 1].endswith("t-be.xdata_layout.tsv")
    assert dl[dl.index("--variant") + 1] == "hwtest"


def test_default_image_gates_stay_strict(tmp_path):
    xl, dl = _cmd(tmp_path, [])
    assert "--layout" not in xl and "--variant" not in dl


def _synthetic(monkeypatch, tmp_path, in_variant_file):
    key = "fw/test/testcmd.c|F|status_loop|while(x)|1"
    row = {"file": "fw/test/testcmd.c", "line": 1, "function": "F", "kind": "status_loop", "stmt": "while(x)", "linked": "yes"}
    monkeypatch.setattr(DA, "rows_all", lambda tree, mapp: [(key, row)])
    monkeypatch.setattr(DA, "load_tsv", lambda path=DA.TSV: ({key: {"verdict": "OK"}} if path != DA.TSV and in_variant_file else {}))
    monkeypatch.setattr(DA, "VARIANT_TSV", {"hwtest": tmp_path / "v.tsv"})
    monkeypatch.setattr(DA, "header_consts", lambda: (1, 0, 0))
    monkeypatch.setattr(DA, "clock_states", list)


def test_default_image_with_an_unlisted_site_fails(monkeypatch, tmp_path):
    _synthetic(monkeypatch, tmp_path, True)
    assert DA.check(tmp_path, tmp_path / "m.map", "") == 1


def test_hwtest_site_listed_in_the_variant_file_passes(monkeypatch, tmp_path):
    _synthetic(monkeypatch, tmp_path, True)
    assert DA.check(tmp_path, tmp_path / "m.map", "hwtest") == 0


def test_hwtest_site_missing_from_both_files_still_fails(monkeypatch, tmp_path):
    _synthetic(monkeypatch, tmp_path, False)
    assert DA.check(tmp_path, tmp_path / "m.map", "hwtest") == 1


def test_variant_delay_rows_are_typed_and_disjoint_from_the_main_file():
    rows = list(csv.DictReader(DA.VARIANT_TSV["hwtest"].open(), delimiter="\t"))
    main = {r["key"] for r in csv.DictReader(DA.TSV.open(), delimiter="\t")}
    assert rows and list(rows[0].keys()) == DA.COLS
    assert not {r["key"] for r in rows} & main, "a site in both files"
    assert not [r["key"] for r in rows if r["verdict"] in ("FIX", "UNKNOWN", "")]


def test_xlayout_gate_checks_the_variants_own_layout(tmp_path):
    lay = tmp_path / "l.tsv"
    lay.write_text(XL.dump({"m": (0x1000, 0, 8)}))
    good = "XS_m 00001000 00000008 = 8. bytes (REL,CON,XDATA)\n"
    assert XL.check(lay, good) == []
    assert XL.check(lay, good.replace("00001000", "00001010"))          # the map moved: a real mismatch still fails in a variant


def test_xdata_slot_slack_is_reclaimed_by_compaction():
    holes = [(0x1000, 0x1040)]
    old = {"a": (0x1000, 0, 32), "b": (0x1000, 32, 32)}                  # both slots 32 B, the modules only 10 B each
    rows, info = XL.place(old, {"a": 10, "b": 10, "c": 40}, holes, [])
    assert info["compacted"] and sum(v[2] for v in rows.values()) == 60


def test_xdata_over_capacity_names_the_totals():
    with pytest.raises(SystemExit, match=r"modules 80 B, holes - reserved 64 B"):
        XL.place({}, {"a": 40, "b": 40}, [(0x1000, 0x1040)], [])


def test_headroom_busy_limit_scales_with_clock():
    import unit_health as H
    assert H.busy_limit_pct(350) == 50
    assert H.busy_limit_pct(175) == H.HEAD_BUSY_CEIL_PCT       # 100 % scaled, capped
    assert H.busy_limit_pct(700) == 25
    assert H.busy_limit_pct(87) == H.HEAD_BUSY_CEIL_PCT
