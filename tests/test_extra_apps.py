"""Extra source root + app hooks (docs/extra-apps.md): the AWTO_APP scan / generator, the build flag, the fw_dirs lists, the example image.
Run: pytest tests/test_extra_apps.py [--slow]  (--slow builds fw/apps/example, runs fw_gates and the apps_sim on it)"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import fw_build as B
import fw_compile as FC
import fw_dirs as FD
import gen_awto_apps as G
import image_variant as IV

EXAMPLE = ROOT / "fw/apps/example"
TRACKED = ("fw/bank_map.tsv", "fw/xdata_layout.tsv")
LEAKY_ENV = (FD.EXTRA_ENV, "K2S_SDCC_EXTRA")     # fw_build.parse_args writes os.environ directly (#356)


@pytest.fixture(autouse=True)
def restore_build_env():
    """Each test leaves AWTO_EXTRA_FW / K2S_SDCC_EXTRA as it found them: a leak made later variant builds EXTRA_APPS (#356)."""
    saved = {k: os.environ.get(k) for k in LEAKY_ENV}
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def src(tmp_path, text, name="a.c"):
    (tmp_path / name).write_text(text)
    return tmp_path


def test_scan_finds_apps_in_file_order(tmp_path):
    (tmp_path / "sub").mkdir()
    (tmp_path / "b.c").write_text("AWTO_APP(second, i2, s2, AWTO_APP_NONE, 0);\n")
    (tmp_path / "sub/a.c").write_text("AWTO_APP( first ,\ti1, s1, k1, st1 );\n")
    apps = G.scan(tmp_path)
    assert [a["name"] for a in apps] == ["second", "first"]
    assert apps[0]["key"] is None and apps[0]["stop"] is None and apps[1]["key"] == "k1"
    assert apps[1]["line"] == 1


def test_scan_ignores_comments_strings_and_the_macro_definition(tmp_path):
    src(tmp_path, '// AWTO_APP(x, a, b, c, d);\n/* AWTO_APP(y, a, b, c, d); */\n#define AWTO_APP(n, i, s, k, st) extern char g_##n\n'
                  'const char *t = "AWTO_APP(z, a, b, c, d)";\nAWTO_APP(real, a, b, c, d);\n')
    assert [a["name"] for a in G.scan(tmp_path)] == ["real"]


@pytest.mark.parametrize("text,msg", [
    ("AWTO_APP(a, b, c);\n", "takes name, init, step, key, stop"),
    ("AWTO_APP(a, b, c, d, e, f);\n", "takes name, init, step, key, stop"),
    ("AWTO_APP(a, b(), c, d, e);\n", "not an identifier"),
    ("AWTO_APP(0, b, c, d, e);\n", "reserved"),
    ("AWTO_APP(a, b, c, d, e);\nAWTO_APP(a, f, g, h, i);\n", "duplicate"),
])
def test_scan_rejects_malformed(tmp_path, text, msg):
    src(tmp_path, text)
    with pytest.raises(ValueError, match=msg):
        G.scan(tmp_path)


def test_scan_limits_the_table(tmp_path):
    src(tmp_path, "".join(f"AWTO_APP(a{i}, i{i}, s{i}, k{i}, p{i});\n" for i in range(G.APP_MAX + 1)))
    with pytest.raises(ValueError, match="at most"):
        G.scan(tmp_path)


def test_render_dispatch_and_none_hooks(tmp_path):
    src(tmp_path, "AWTO_APP(one, i1, s1, AWTO_APP_NONE, p1);\nAWTO_APP(two, i2, AWTO_APP_NONE, k2, 0);\n")
    out = G.render(G.scan(tmp_path), tmp_path)
    assert "#define AWTO_APP_COUNT 2" in out
    assert "extern void i1(void);" in out and "extern void k2(BYTE ucKey, BYTE ucEv);" in out
    assert "case 0:\n            i1();" in out and "case 1:\n            i2();" in out
    assert "case 1:\n            k2(ucKey, ucEv);" in out and "s2" not in out
    assert "return (ucI == 1);" in out                       # only app 1 has a key hook
    assert "&" not in out.split("AwtoAppDoInit")[1]          # direct calls only: SDCC banking cannot take a function pointer across banks


def test_render_without_key_hooks(tmp_path):
    src(tmp_path, "AWTO_APP(one, i1, s1, AWTO_APP_NONE, AWTO_APP_NONE);\n")
    out = G.render(G.scan(tmp_path), tmp_path)
    assert "AwtoAppHasKey(BYTE ucI)\n{\n    ucI = ucI;\n    return 0;" in out


def test_generate_writes_inc_and_tsv_and_check(tmp_path):
    (tmp_path / "x").mkdir()
    root = src(tmp_path / "x", "AWTO_APP(one, i1, s1, k1, p1);\n")
    out = tmp_path / "gen" / "apps_gen.inc"
    assert G.main([str(root), "--out", str(out), "--check"]) == 1          # missing
    assert G.main([str(root), "--out", str(out)]) == 0
    assert G.main([str(root), "--out", str(out), "--check"]) == 0
    assert out.with_suffix(".tsv").read_text().split("\t")[:2] == ["0", "one"]
    (root / "a.c").write_text("AWTO_APP(one, i1, s1, k1, p9);\n")
    assert G.main([str(root), "--out", str(out), "--check"]) == 1          # stale
    assert G.main([str(tmp_path / "nope")]) == 2


def test_example_app_is_registered():
    apps = G.scan(EXAMPLE)
    assert [a["name"] for a in apps] == ["hello"] and all(apps[0][h] for h in G.HOOKS)


# ---- build flag, source lists ----
def test_fw_dirs_default_has_no_apps_in_the_build(monkeypatch):
    monkeypatch.delenv(FD.EXTRA_ENV, raising=False)
    assert ROOT / "fw/apps" in FD.our_dirs(ROOT)                           # the lints see it
    assert ROOT / "fw/apps" not in FD.build_dirs(ROOT)                     # the default image's command lines do not
    assert not [p for p in FD.build_files(ROOT) if "apps" in p.parts]


def test_fw_dirs_extra_root_joins_the_build(monkeypatch, tmp_path):
    (tmp_path / "game/inc").mkdir(parents=True)
    for n in ("game/g.c", "game/inc/g.h", "game/inc/t.inc", "game/m.asm", "game/readme.txt"):
        (tmp_path / n).write_text("")
    monkeypatch.setenv(FD.EXTRA_ENV, str(tmp_path))
    dirs = FD.extra_dirs()
    assert dirs[0] == tmp_path and tmp_path / "game" in dirs and tmp_path / "game/inc" in dirs      # root first, then every folder with sources / headers
    assert ROOT / "fw/apps" in FD.build_dirs(ROOT)
    assert [p.name for p in FD.build_files(ROOT) if p.is_relative_to(tmp_path)] == ["g.c"]
    assert sorted(p.name for d in dirs for p in d.glob("*.inc")) == ["t.inc"]


def test_fw_build_extra_fw_sets_env_and_define(monkeypatch, tmp_path):
    monkeypatch.delenv(FD.EXTRA_ENV, raising=False)
    monkeypatch.delenv("K2S_SDCC_EXTRA", raising=False)
    a = B.parse_args(["--serial", "AWT00000000", "--extra-fw", str(tmp_path)])
    assert a.extra_fw == str(tmp_path.resolve())
    assert FD.extra_root() == tmp_path.resolve()
    assert "-D_AWTO_EXTRA_APPS=_ON" in B.os.environ["K2S_SDCC_EXTRA"]
    assert IV.parse_defines(B.os.environ["K2S_SDCC_EXTRA"].split())["variant"] is True      # never promotes the tracked layouts
    monkeypatch.delenv(FD.EXTRA_ENV)
    B.parse_args(["--serial", "AWT00000000"])
    assert FD.extra_root() is None


def test_fw_build_extra_fw_must_exist(monkeypatch, tmp_path):
    monkeypatch.delenv(FD.EXTRA_ENV, raising=False)
    with pytest.raises(SystemExit, match="not a directory"):
        B.parse_args(["--serial", "AWT00000000", "--extra-fw", str(tmp_path / "nope")])


def test_variant_flag():
    assert IV.parse_defines(["_AWTO_EXTRA_APPS=_ON"]) == {"hwtest": False, "t0ev": False, "extra": True, "nofrc": False, "freeze": False, "audio": False,
                                                         "nodlog": False, "clock": IV.DEFAULT_CLOCK_MHZ, "variant": True}
    assert IV.parse_defines(["_AWTO_EXTRA_APPS=_OFF"])["variant"] is False


def test_module_name_clash_is_reported():
    assert FC.check_unique([Path("/a/x.c"), Path("/b/y.c")]) == []
    bad = FC.check_unique([Path("/a/x.c"), Path("/b/x.c")])
    assert len(bad) == 1 and "/a/x.c" in bad[0] and "/b/x.c" in bad[0]


def test_dev_build_takes_extra_fw():
    r = subprocess.run([sys.executable, str(ROOT / "dev.py"), "build", "--extra-fw", "/nonexistent-extra-fw", "--tag", "x"], cwd=ROOT,
                       capture_output=True, text=True, check=False, timeout=60)
    assert r.returncode != 0 and "--extra-fw" in (r.stdout + r.stderr) and "not a directory" in (r.stdout + r.stderr)


@pytest.mark.slow
def test_example_image_builds_gates_and_runs():
    before = [(ROOT / f).read_bytes() for f in TRACKED]
    r = subprocess.run([sys.executable, str(ROOT / "dev.py"), "build", "--extra-fw", str(EXAMPLE), "--tag", "apps-ci"], cwd=ROOT,
                       capture_output=True, text=True, check=False)
    assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]
    assert before == [(ROOT / f).read_bytes() for f in TRACKED]            # tracked bank / XDATA maps untouched
    img = max((ROOT / "tmp/fw").glob("*-apps-ci-be.bin"))
    bj = json.loads(img.with_name(img.stem + ".build.json").read_text())
    assert bj["extra_fw"] == str(EXAMPLE) and "_AWTO_EXTRA_APPS=_ON" in bj["defines"]
    g = subprocess.run([sys.executable, str(ROOT / "scripts/fw_gates.py"), str(img.with_suffix(""))], cwd=ROOT, capture_output=True, text=True, check=False)
    assert g.returncode == 0 and "ALL PASS" in g.stdout, g.stdout[-2000:]
    s = subprocess.run([sys.executable, str(ROOT / "scripts/apps_sim.py"), str(img), str(img.with_suffix(".map"))], cwd=ROOT, capture_output=True,
                       text=True, check=False)
    assert s.returncode == 0 and "PASS apps_sim" in s.stdout, s.stdout[-2000:]
