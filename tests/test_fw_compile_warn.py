"""fw_compile compile_one: cpp and compiler stderr never interleave, so the warn gate sees whole lines (#51.7, #47).
The fake compiler behaves like sdcc: one run (no -E / --c1mode) writes cpp and compiler stderr interleaved mid-line;
-E and --c1mode runs write only their own stage's lines."""
import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fw_compile as K  # noqa: E402

FAKE = r'''#!/usr/bin/env python3
import sys
a = sys.argv[1:]
src = a[-1]
out = a[a.index("-o") + 1]
CPP = f"{src}:7:3: warning: object in read-only code space should be const\n"
CC = f"{src}:9: warning 158: overflow in implicit constant conversion\n"
if "-E" in a:
    open(out, "w").write(f'#line 1 "{src}"\n'); sys.stderr.write(CPP)
elif "--c1mode" in a:
    src = sys.stdin.read().split('"')[1]            # source path from the #line the cpp stage wrote
    CC = f"{src}:9: warning 158: overflow in implicit constant conversion\n"
    open(out, "w").write("asm\n"); sys.stderr.write(CC)
else:                                   # single run: concurrent writers, cpp line cut by a compiler line
    open(out, "w").write("asm\n")
    sys.stderr.write(CPP[:30]); sys.stderr.flush(); sys.stderr.write(CC); sys.stderr.write(CPP[30:])
'''

POLICY = ("^object in read-only code space should be const$\t*\t*\tok\tt\n"
          "^overflow in implicit constant conversion$\t*\t*\tok\tt\n")


@pytest.fixture
def env(tmp_path, monkeypatch):
    fake = tmp_path / "fakesdcc"
    fake.write_text(FAKE)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    src = tmp_path / "work/src"
    (src / "d").mkdir(parents=True)
    (src / "d/x.c").write_text("int x;\n")
    (tmp_path / "fw").mkdir()
    (tmp_path / "fw/warn_policy.tsv").write_text(POLICY)
    for k, v in (("SDCC", str(fake)), ("SRC", src), ("WORK", tmp_path / "work"), ("ROOT", tmp_path), ("ASM_MODE", True)):
        monkeypatch.setattr(K, k, v)
    monkeypatch.setattr(K, "_KC", [])         # the fake compiler has no --keil-compat to probe
    return src


def test_warnings_not_interleaved_and_gate_passes(env):
    f, rc, msg = K.compile_one(env / "d/x.c", env / "d", [], [], 2)
    assert rc == 0
    lines = msg.splitlines()
    assert f"{env}/d/x.c:7:3: warning: object in read-only code space should be const" in lines
    assert f"{env}/d/x.c:9: warning 158: overflow in implicit constant conversion" in lines
    assert K.warn_gate([(f, rc, msg)]) == []


def test_intermediate_pp_file_removed_and_output_written(env):
    K.compile_one(env / "d/x.c", env / "d", [], [], 2)
    out = K.WORK / "asm/d"
    assert (out / "x.asm").read_text() == "asm\n" and not list(out.glob("*.i"))


def test_no_jobs_env_hack():
    assert "K2S_JOBS" not in Path(K.__file__).read_text()
