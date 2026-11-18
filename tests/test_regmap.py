"""regmap_*: the register knowledge base (re/regmap/README.md): schema, merge keeps hand columns, check mode, importer, query."""
import gzip
import json
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import regmap_build as B  # noqa: E402
import regmap_import as I  # noqa: E402
import regmap_lib as L  # noqa: E402
import regmap_query as Q  # noqa: E402


@pytest.fixture(scope="module")
def committed():
    _, rows = L.read_tsv(L.REGS)
    _, flds = L.read_tsv(L.FIELDS)
    return rows, flds


def test_schema(committed):
    rows, flds = committed
    cols, _ = L.read_tsv(L.REGS)
    assert cols == L.REG_COLS
    assert L.read_tsv(L.FIELDS)[0] == L.FLD_COLS
    keys = [r["key"] for r in rows]
    assert len(set(keys)) == len(keys), "duplicate key"
    assert keys == sorted(keys, key=L.sort_key), "rows are sorted by key"
    assert all(L.KEY_RE.match(k) for k in keys)
    assert all(r["key"][:2] == r["page"] and r["key"][2:4] == r["addr"] for r in rows)
    assert {r["regdb_status"] for r in rows} <= L.REGDB_STATUS
    assert all(L.FKEY_RE.match(f["fkey"]) and f["key"] in set(keys) for f in flds)


def test_seed_answers_the_questions(committed):
    rows, _ = committed
    by = {r["key"]: r for r in rows}
    assert by["06A4"]["class"] == "sensor" and by["06A4"]["status"] == "candidate"
    assert by["FFED"]["regdb_name"] == "MCU_CONTROL" and by["FFED"]["test_id"] == "T-L"
    assert by["FF83"]["regdb_status"] == "no-row" and by["FF83"]["status"] == "candidate"
    assert not any(r["key"] in L.EXCLUDE_KEYS and r["obs_n"] for r in rows), "HDCP ports carry no observations"


def test_committed_files_are_current():
    assert B.main.__module__ == "regmap_build"
    old_regs, old_flds = B.load_old()
    rows, frows, errs = B.build(old_regs, old_flds)
    errs = B.validate(rows, frows, errs)
    assert not errs, errs[:5]
    rt, ft = B.texts(rows, frows)
    assert rt == L.REGS.read_text() and ft == L.FIELDS.read_text(), "run scripts/regmap_build.py --write"


def test_merge_keeps_hand_columns_and_drops_stale_cells():
    old = [{"key": "01E0", "role": "my role", "status": "known", "evidence": "role=spec", "obs_n": "999", "regdb_name": "WRONG"},
           {"key": "0F77", "class": "unused", "notes": "hand-only row, no regdb / sdk / observation"}]
    flds = [{"fkey": "01E1[3:0]", "name": "n", "role": "N-2", "status": "known", "evidence": "role=spec"}]
    rows, frows, errs = B.build(old, flds)
    by = {r["key"]: r for r in rows}
    assert by["01E0"]["role"] == "my role" and by["01E0"]["status"] == "known"
    assert by["01E0"]["regdb_name"] == "M2PLL_M" and by["01E0"]["obs_n"] != "999", "generated cells are recomputed"
    assert by["0F77"]["notes"].startswith("hand-only") and by["0F77"]["regdb_status"] == "no-row"
    assert frows[0]["regdb_field"] == "reg_m2pll_n" and frows[0]["key"] == "01E1" and not errs
    rows2, frows2, _ = B.build(rows, frows)            # idempotent
    assert rows2 == rows and frows2 == frows


def test_validate_rejects_bad_hand_columns(committed):
    rows, _ = committed
    tests = L.known_test_ids()
    assert {"OT-1", "T-A", "T10", "C-PLLHW"} <= tests
    bad = {"key": "0001", "class": "nonsense", "status": "maybe", "test_id": "X-9", "issue": "236", "evidence": "role=spec+bogus;wrong=hw;role", "role": "r"}
    msgs = " | ".join(L.check_hand(bad, "0001", tests))
    for frag in ("class", "status", "test_id X-9", "issue", "bogus", "wrong", "claim=tag"):
        assert frag in msgs, frag
    assert L.check_hand({"status": "known", "role": "r"}, "k", tests), "known + role needs evidence"
    assert not L.check_hand({"status": "known", "role": "r", "evidence": "role=hw", "test_id": "OT-4,T-A", "issue": "#1,#2"}, "k", tests)
    assert B.validate([{**rows[0], "regdb_status": "bogus"}], [], [])


def test_check_mode(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(L, "REGS", tmp_path / "regs.tsv")
    monkeypatch.setattr(L, "FIELDS", tmp_path / "fields.tsv")
    argv = lambda *a: monkeypatch.setattr(sys, "argv", ["regmap_build.py", *a])  # noqa: E731
    argv("--check")
    assert B.main() == 1, "missing files are stale"
    argv("--set", "01E0", "role=pll m", "status=known", "evidence=role=spec")
    assert B.main() == 0
    argv("--check")
    assert B.main() == 0
    text = L.REGS.read_text()
    assert "\tpll m\t" in text
    L.REGS.write_text(text.replace("M2PLL_M\t", "M2PLL_X\t", 1))
    assert B.main() == 1 and "stale" in capsys.readouterr().out
    argv("--set", "01E0", "status=bogus")
    assert B.main() == 1, "--set refuses a bad value and writes nothing"
    argv("--set", "01E0", "obs_n=1")
    with pytest.raises(SystemExit):
        B.main()
    argv("--set-field", "01E7[5:4]", "name=m_msb", "status=known", "role=M[9:8]", "evidence=role=spec")
    assert B.main() == 0
    argv("--set-field", "0F77[7:4]", "name=x", "role=y")
    assert B.main() == 1, "a field row needs its register row"


def test_importer_fixture(tmp_path, capsys):
    pages = {"3A": [0] * 256, "71": [7] * 256}      # page 71 carries the HDCP key port 71C4
    pages["3A"][0x18] = 0x10
    isp = tmp_path / "AWT26110009-fix-20261101-120000.json"
    isp.write_text(json.dumps({"serial": "AWT26110009", "bus": 3, "time": "2026-11-01T12:00:00+1100", "pages": pages,
                               "ports": {"002B": {"0": 15, "1": 156}, "71CA": {"0": 9}, "2A:2B": [15, 156]}}))
    live = tmp_path / "AWT26110009-A-20261102-130000.json"
    live.write_text(json.dumps({"serial": "AWT26110009", "unit": "9", "label": "A", "start": "2026-11-02T13:00:00+11:00", "diag_header": "414402", "excluded": [],
                                "pages": {"3A": [None, 5] + [0] * 254}}))
    part = tmp_path / "AWT26110009-audio-20261103-140000.json"
    part.write_text(json.dumps({"serial": "AWT26110009", "time": "2026-11-03T14:00:00+11:00", "note": "partial", "pages": {"06": {"C0": "db f1 aa"}}}))
    gpio = tmp_path / "AWT26110009-gpio-20261101-120000.json"
    gpio.write_text(json.dumps({"serial": "AWT26110009", "time": "x", "pins": {}}))
    out = tmp_path / "obs"
    assert I.main.__module__ == "regmap_import"
    sys.argv = ["regmap_import.py", str(isp), str(live), str(part), str(gpio), "--out", str(out)]
    assert I.main() == 0
    files = sorted(p.name for p in out.glob("*.tsv.gz"))
    assert files == ["AWT26110009-A-20261102-130000.tsv.gz", "AWT26110009-audio-20261103-140000.tsv.gz", "AWT26110009-fix-20261101-120000.tsv.gz"]
    obs = {o.sid: o for o in L.load_obs(out)}
    o = obs["AWT26110009-fix-20261101-120000"]
    assert o.meta["method"] == "isp" and o.meta["state"] == "halted+reset" and o.meta["time"] == "2026-11-01T12:00:00+11:00" and o.meta["unit"] == "9"
    assert o.vals["3A18"] == 0x10 and o.vals["002B:01"] == 156 and "002B:00" in o.vals
    assert "71C4" not in o.vals and "71CA:00" not in o.vals
    lv = obs["AWT26110009-A-20261102-130000"]
    assert lv.meta["method"] == "live" and lv.meta["state"] == "running" and "3A00" not in lv.vals and lv.vals["3A01"] == 5
    pt = obs["AWT26110009-audio-20261103-140000"]
    assert pt.meta["method"] == "regdump" and pt.vals == {"06C0": 0xDB, "06C1": 0xF1, "06C2": 0xAA}
    sys.argv = ["regmap_import.py", str(isp), "--out", str(out)]
    assert I.main() == 0 and "exists" in capsys.readouterr().out, "an existing (serial, label, time) is kept"
    with gzip.open(out / files[0], "rt") as f:
        assert f.read().startswith("#source=")


def test_summarise():
    mk = lambda unit, label, t, vals: L.Obs("x", {"unit": unit, "label": label, "state": "s", "method": "isp", "time": t}, vals)  # noqa: E731
    s = L.summarise([mk("1", "A", "2026-11-01T00:00:00+11:00", {"0001": 0, "0002": 5, "0003": 0}),
                     mk("1", "A", "2026-11-02T00:00:00+11:00", {"0001": 0, "0002": 6, "0003": 0}),
                     mk("2", "B", "2026-11-03T00:00:00+11:00", {"0001": 0, "0003": 9})])
    assert s["0001"]["obs_nonzero"] == "0" and s["0001"]["obs_const"] == "00" and s["0001"]["obs_vary_state"] == "0"
    assert s["0002"]["obs_vary_state"] == "1" and s["0002"]["obs_distinct"] == "2" and s["0002"]["obs_first"] == "2026-11-01"
    assert s["0003"]["obs_vary_state"] == "0" and s["0003"]["obs_distinct"] == "2" and s["0003"]["obs_units"] == "2"
    assert re.match(r"i:", s["0003"]["obs_hist"])


def test_obs_roundtrip(tmp_path):
    vals = {"3A18": 0x10, "3A19": 0, "3A1B": 7, "002B:00": 15, "002B:02": 8}
    p = tmp_path / "a.tsv.gz"
    L.write_obs(p, {"unit": "1", "label": "x"}, vals)
    assert L.load_obs(tmp_path)[0].vals == vals
    first = p.read_bytes()
    L.write_obs(p, {"unit": "1", "label": "x"}, vals)
    assert p.read_bytes() == first, "deterministic bytes (no mtime)"


def test_obs_store_is_clean_and_small():
    total = 0
    for p in L.OBS.glob("*.tsv.gz"):
        total += p.stat().st_size
    assert total <= B.OBS_BUDGET
    for o in L.load_obs():
        assert not [k for k in o.vals if k.partition(":")[0] in L.EXCLUDE_KEYS], o.sid


def test_query(capsys):
    def run(*a):
        sys.argv = ["regmap_query.py", *a]
        rc = Q.main()
        return rc, capsys.readouterr()
    rc, c = run("06A4")
    assert rc == 0 and "OSC_TRIM_CNT" in c.out and "sensor" in c.out
    rc, c = run("--undocumented-nonzero", "--changing", "--limit", "0")
    assert "21D8" in c.out and "A7E0" in c.out and "06A4" not in c.out, "documented registers are not 'undocumented'"
    rc, c = run("--candidates", "sensor")
    assert "FF0B" in c.out and "06A4" in c.out
    rc, c = run("--tests", "--limit", "0")
    assert "C-IOSC" in c.out and "OT-18" in c.out
    rc, c = run("--page", "FF", "--grep", "i2cs", "--limit", "0")
    assert "FF83" in c.out
    rc, c = run("--obs", "06A4")
    assert "AWT26110003" in c.out
