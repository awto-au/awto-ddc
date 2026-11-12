"""Clean-room tooling (#65): facts_regs, cleanroom_lint, trace_equiv, fw_inventory, keil2sdcc module rules, unit_lock. Offline."""
from __future__ import annotations

import gzip
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cleanroom_lint as CL  # noqa: E402
import facts_regs as FR  # noqa: E402
import fw_inventory as INV  # noqa: E402
import trace_equiv as TE  # noqa: E402
import unit_lock as UL  # noqa: E402


# ---------------- facts_regs ----------------
def test_facts_generate_real_regdb(tmp_path):
    names = tmp_path / "names.tsv"
    names.write_text("HB_CTRL\tPFF_F3\tours\nHB_CTRL_NOINC\tPFF_F3_B5\t\n")
    FR.generate("RTD2795T-CG", tmp_path / "facts", names)
    pff = (tmp_path / "facts/regs/pff.h").read_text()
    assert "#define PFF_F3                       0xFFF3u" in pff
    assert "#define PFF_F3_B5                    0x20u" in pff
    assert "#define PFF_F3_RST                   0x80u" in pff
    p00 = (tmp_path / "facts/regs/p00.h").read_text()
    assert "P00_25_I01_B4_0_SH" in p00 and "P00_92_I0100_N1" in p00
    # facts only: no vendor register or field names anywhere in the generated headers
    allh = "".join(p.read_text() for p in (tmp_path / "facts").rglob("*.h"))
    for vendor in ("SCA_INF_CONTROL", "reg_burcmd_wr", "BANK_SWICH_CONTROL", "WIN0_ADR0_LSB", "Reserved"):
        assert vendor not in allh
    assert "#define HB_CTRL_NOINC" in (tmp_path / "facts/names.h").read_text()


def test_facts_names_refused(tmp_path):
    for bad in ("SCA_INF_CONTROL\tPFF_F3\t\n", "HB_X\tPFF_F3_B9\t\n", "hb_lower\tPFF_F3\t\n"):
        names = tmp_path / "names.tsv"
        names.write_text(bad)
        with pytest.raises(SystemExit):
            FR.generate("RTD2795T-CG", tmp_path / "facts", names)


# ---------------- cleanroom_lint ----------------
SDK_C = """
// Description  : Write one value through the indexed access port of the scaler block
void VendorPortWriteThing(WORD usAddr, BYTE ucIndex, BYTE ucData)
{
    VendorSetByte(usAddr, ucIndex);
    VendorSetByte(usAddr + 1, ucData);
}
"""


@pytest.fixture
def lintenv(tmp_path, monkeypatch):
    sdk = tmp_path / "sdk"; sdk.mkdir()
    (sdk / "v.c").write_text(SDK_C)
    monkeypatch.setattr(CL, "SDK", sdk)
    monkeypatch.setattr(CL, "TAINTED", [])
    monkeypatch.setattr(CL, "CACHE", tmp_path / "idx.npz")
    monkeypatch.setattr(CL, "ALLOW", tmp_path / "allow.tsv")
    tree = tmp_path / "tree"; (tree / "awto/x").mkdir(parents=True); (tree / "facts").mkdir()
    return CL.build_index(True), tree, tmp_path


def test_lint_clean_code_passes(lintenv):
    idx, tree, _ = lintenv
    (tree / "awto/x/ok.c").write_text("void dp_wr(uint16_t port, uint8_t i, uint8_t v)\n{\n    REG8(port) = i;\n    REG8(port + 1) = v;\n}\n")
    (tree / "README.md").write_text("Our own words about the data port.\n")
    assert CL.lint(tree, idx, False, False) == []


def test_lint_catches_ident_code_and_prose(lintenv):
    idx, tree, _ = lintenv
    (tree / "awto/x/bad.c").write_text("/* Write one value through the indexed access port of the scaler block */\n"
                                       "void f(uint16_t a)\n{\n    VendorSetByte(usAddr + 1, ucData);\n}\n")
    hits = CL.lint(tree, idx, False, False)
    kinds = {h.split(": ")[1].split()[0] for h in hits}
    assert {"ident", "code", "prose"} <= kinds
    assert any("VendorSetByte" in h for h in hits)


def test_lint_exemptions(lintenv):
    idx, tree, tmp = lintenv
    (tree / "facts/regs.h").write_text("#define VendorSetByte 1\n")      # facts-defined names are exempt...
    (tree / "awto/x/a.c").write_text("int g(void) { return VendorSetByte + ucIndex; }\n")
    hits = CL.lint(tree, idx, False, False)
    assert [h for h in hits if "ident" in h] == ["awto/x/a.c:1: ident ucIndex"]
    (tmp / "allow.tsv").write_text("ident\tucIndex\treviewed: generic\n")
    assert [h for h in CL.lint(tree, idx, False, False) if "ident" in h] == []
    (tree / "awto_shim").mkdir(); (tree / "awto_shim/s.c").write_text(SDK_C)  # the shim is exempt
    assert not [h for h in CL.lint(tree, idx, False, False) if "awto_shim" in h]


# ---------------- trace_equiv ----------------
def trace(path: Path, rows):
    """rows: (kind, addr, idx, value, phase_state_or_None, instr)"""
    lines = ["seq\tinstr\tfw_ms\tbank\tpc\tfunc\tkind\taddr\treg\tidx\tvalue\tphase"]
    for i, (kind, addr, idx, val, instr) in enumerate(rows):
        reg = val if kind == "STATE" else f"R{addr:04X}"
        v = "00" if kind == "STATE" else f"{val:02x}"
        lines.append(f"{i}\t{instr}\t{instr / 12600:.1f}\t0\t0000\tf+0\t{kind}\t{addr:04x}\t{reg}\t{idx}\t{v}\tx")
    with gzip.open(path, "wt") as f:
        f.write("\n".join(lines) + "\n")
    return path


BASE = [("STATE", 0, "", "INITIAL", 0), ("W", 0x3100, "", 0x11, 10), ("W", 0x3101, "", 0x22, 20),
        ("STATE", 0, "", "SEARCH", 30), ("W", 0x3102, "", 0x33, 40),
        ("STATE", 0, "", "DISPLAY_SETTING", 50), ("W", 0x0025, "05", 0x01, 60), ("W", 0x0025, "06", 0x02, 70),
        ("W", 0x3103, "", 0x44, 80), ("STATE", 0, "", "ACTIVE", 12600 * 5)]


def equiv(tmp_path, ours, rules_text="", slack=0.0, ref=BASE):
    r = trace(tmp_path / "ref.tsv.gz", ref)
    o = trace(tmp_path / "ours.tsv.gz", ours)
    rules = TE.Rules()
    if rules_text:
        (tmp_path / "r.equiv").write_text(rules_text)
        rules.load(tmp_path / "r.equiv")
    (_, a), (_, b) = TE.load(r), TE.load(o)
    return TE.compare(a, b, rules, slack, False)


def test_equiv_identical_and_may_differ(tmp_path):
    assert equiv(tmp_path, BASE)[1] == 0
    reordered = BASE[:1] + [BASE[2], BASE[1]] + BASE[3:]                  # order inside a phase
    assert equiv(tmp_path, reordered)[1] == 0
    redundant = BASE[:2] + [("W", 0x3100, "", 0x00, 11), ("W", 0x3100, "", 0x11, 12)] + BASE[2:]   # RMW split / redundant
    assert equiv(tmp_path, redundant)[1] == 0


def test_equiv_must_match(tmp_path):
    wrong = [r if r[1] != 0x3103 else ("W", 0x3103, "", 0x45, 80) for r in BASE]
    L, f = equiv(tmp_path, wrong)
    assert f == 1 and any("3103" in x for x in L)
    swapped = BASE[:6] + [BASE[7], BASE[6]] + BASE[8:]                     # indexed-port burst order
    assert equiv(tmp_path, swapped)[1] >= 1
    moved = BASE[:3] + BASE[4:5] + BASE[3:4] + BASE[5:]                   # write moved to another phase
    assert equiv(tmp_path, moved)[1] >= 1


def test_equiv_barrier_delay_ds(tmp_path):
    ref = BASE[:1] + [("W", 0x31A0, "", 0x80, 5)] + BASE[1:]
    ours = BASE[:3] + [("W", 0x31A0, "", 0x80, 25)] + BASE[3:]            # barrier moved after the 3100/3101 writes
    assert equiv(tmp_path, ours, ref=ref)[1] == 0                         # no barrier rule: order free
    assert equiv(tmp_path, ours, "barrier 31A0=80\n", ref=ref)[1] == 0    # same barrier sequence
    ours2 = BASE[:3] + [("W", 0x31A0, "", 0x80, 25), ("W", 0x31A0, "", 0x00, 26), ("W", 0x31A0, "", 0x80, 27)] + BASE[3:]
    assert equiv(tmp_path, ours2, "barrier 31A0\n", ref=ref)[1] >= 1
    # delay: 3100 -> 3101 must be >= 1000 us; BASE has 10 instr (< 1 us)
    L, f = equiv(tmp_path, BASE, "delay 3100 3101 1000\n")
    assert f == 1 and any("delay" in x for x in L)
    slow = BASE[:-1] + [("STATE", 0, "", "ACTIVE", 12600 * 9)]
    assert equiv(tmp_path, slow)[1] == 1
    assert equiv(tmp_path, slow, slack=5.0)[1] == 0


def test_equiv_w1c_ignored(tmp_path):
    _, w1c = TE.regdb_facts()
    a = sorted(w1c)[0]
    ours = BASE[:2] + [("W", a, "", 0xFF, 15)] + BASE[2:]
    assert equiv(tmp_path, ours)[1] == 0


# ---------------- fw_inventory ----------------
MAP = """Area                                    Addr        Size        Decimal Bytes (Attributes)
--------------------------------        ----        ----        ------- ----- ------------
CH_ScalerFooSetThing                00055B38    0000008A =         138. bytes (REL,CON,CODE)

         Value  Global                             Global Defined In Module
         -----  --------------------------------   ------------------------
C:   00055B38  _ScalerFooSetThing                 ScalerFooModuleWithALongNam

Area                                    Addr        Size        Decimal Bytes (Attributes)
--------------------------------        ----        ----        ------- ----- ------------
CH_tFOO_TABLE                       00055000    00000080 =         128. bytes (REL,CON,CODE)

         Value  Global                             Global Defined In Module
         -----  --------------------------------   ------------------------
C:   00055000  _tFOO_TABLE                        ScalerFooModuleWithALongNam

Area                                    Addr        Size        Decimal Bytes (Attributes)
--------------------------------        ----        ----        ------- ----- ------------
CH_AwtoThing                        00045BF0    00000010 =          16. bytes (REL,CON,CODE)

         Value  Global                             Global Defined In Module
         -----  --------------------------------   ------------------------
C:   00045BF0  _AwtoThing                         SysMain

Files Linked                              [ module(s) ]

/x/asm_bank/ScalerFooModuleWithALongName.rel
/x/asm_bank/SysMain.rel
"""


def test_inventory(tmp_path):
    sdk = tmp_path / "sdk"
    (sdk / "Kernel/Scaler/ScalerFunction/Code").mkdir(parents=True)
    (sdk / "Kernel/Scaler/ScalerFunction/Code/ScalerFooModuleWithALongName.c").write_text("")
    (sdk / "Kernel/System/Code").mkdir(parents=True)
    (sdk / "Kernel/System/Code/SysMain.c").write_text("")
    (tmp_path / "a.map").write_text(MAP)
    rows, mods = INV.inventory(tmp_path / "a.map", sdk)
    by = {r[5]: r for r in rows}
    assert mods == ["ScalerFooModuleWithALongName", "SysMain"]
    assert by["ScalerFooSetThing"][:2] == ("Kernel/Scaler drivers", "? unassigned") and by["ScalerFooSetThing"][4] == "fn"
    assert by["tFOO_TABLE"][4] == "const" and by["tFOO_TABLE"][6] == 128
    assert by["AwtoThing"][0] == "Ours: Awto* inserts" and by["AwtoThing"][1] == "15 Awto* port"


# ---------------- keil2sdcc per-module rules ----------------
def test_keil2sdcc_module_rules(tmp_path):
    import keil2sdcc as K
    (tmp_path / "reg").mkdir()
    (tmp_path / "reg/rules.py").write_text(
        'WRAPS = [("A/b.c", r"^x", r"^y", "_AWTO_NEW_REG")]\nSUBS = [("A/b.c", r"\\bold\\(", "new(")]\n')
    n_w = len(K.WRAPS)
    K.load_module_rules(tmp_path)
    try:
        assert K.WRAPS[-1][3] == "_AWTO_NEW_REG" and len(K.WRAPS) == n_w + 1
        from collections import Counter
        st = Counter()
        assert K.apply_subs("A/b.c", "old(1); old(2);", st) == "new(1); new(2);" and st["subs"] == 2
        with pytest.raises(SystemExit):
            K.apply_subs("A/b.c", "nothing here", Counter())
    finally:
        del K.WRAPS[n_w:]; K.SUBS.clear()


# ---------------- unit_lock ----------------
def test_unit_lock(tmp_path, monkeypatch):
    monkeypatch.setattr(UL, "LOCKS", tmp_path / "locks")
    monkeypatch.setattr(UL, "ROOT", tmp_path)
    monkeypatch.delenv("AWTO_UNIT_OWNER", raising=False)
    UL.acquire("U1", "alice", os.getpid())
    UL.acquire("U1", "alice", os.getpid())                      # re-acquire by the owner: ok
    with pytest.raises(SystemExit):
        UL.acquire("U1", "bob", os.getpid())
    with pytest.raises(SystemExit):
        with UL.held("U1", "tool"):                             # tool run without the owner's stream id
            pass
    monkeypatch.setenv("AWTO_UNIT_OWNER", "alice")
    with UL.held("U1", "tool"):                                 # the stream's own lock
        pass
    assert UL.read("U1")["owner"] == "alice"
    with pytest.raises(SystemExit):
        UL.release("U1", "bob")
    UL.release("U1", "alice")
    assert UL.read("U1") is None
    monkeypatch.delenv("AWTO_UNIT_OWNER")
    with UL.held("U2", "tool"):                                 # per-run lock, released after
        assert UL.read("U2")["tool"] == "tool"
    assert UL.read("U2") is None
    UL._create("U3", "ghost", 2 ** 22 + 12345, "x")             # dead pid -> stale, cleared on acquire
    UL.acquire("U3", "carol", os.getpid())
    assert UL.read("U3")["owner"] == "carol"


# ---------------- brief, audit, vectors ----------------
def test_brief_assembles():
    import cleanroom_brief as B
    t = B.assemble("arith")
    assert "Spec: arith" in t and "muldiv\t" in t and "specs/vectors" not in t and "{spec}" not in t
    with pytest.raises(SystemExit):
        B.assemble("gamma")                                          # TO WRITE


def test_audit(tmp_path):
    import json
    import cleanroom_audit as A
    rec = lambda c: json.dumps({"message": {"content": [c]}})
    f = tmp_path / "s.jsonl"
    f.write_text("\n".join([
        rec({"type": "tool_use", "name": "Read", "input": {"file_path": "/mnt/2tb/git/awto-rtdfw/awto/x.c"}}),
        rec({"type": "tool_use", "name": "Read", "input": {"file_path": "/mnt/2tb/git_mirror/K/a.c"}}),
        rec({"type": "tool_use", "name": "WebFetch", "input": {"url": "https://example.com"}}),
        rec({"type": "tool_use", "name": "Bash", "input": {"command": "cd x && curl http://a"}}),
    ]))
    hits = A.audit([f])
    assert len(hits) == 3 and not any(":1:" in h for h in hits)


def test_spec_vectors_maths():
    import spec_vectors as V
    assert V.shldiv(1, 1, 3) == 1 and V.shldiv(1, 0, 2) == 1 and V.shldiv(1, 0, 3) == 0
    assert V.muldiv(10, 10, 3) == 33                                  # fast regime truncates
    assert V.muldiv(0xFFFFFFFF, 1, 1) == 0xFFFFFFFF                   # boundary a = (2^32-1)/b: slow regime
    assert V.osd_gap(594000, 0) == 0x12 and V.osd_gap(0, 0) == 0xFF and V.osd_gap(6054000, 1) == 2
