"""fw_compile.obj_name: one rule for the .rel/.asm/.rst stem of a source (san_names matches statics by it)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import fw_compile as K


def test_plain_source_is_stem():
    c = K.SRC / "Kernel" / "Foo" / "bar.c"
    assert K.obj_name(c) == "bar"


def test_shim():
    assert K.SHIM_C.exists()
    assert K.obj_name(K.SHIM_C) == "awto_shim_sdk_boundary"


def test_awto_sources_match_job_names():
    srcs = K.awto_sources()
    assert srcs
    for mod, cs in srcs.items():
        for c in cs:
            assert K.obj_name(c) == f"awto_{mod}_{c.stem}"
