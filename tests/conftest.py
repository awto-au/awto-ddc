"""Shared test setup.
- `slow`: full simulator runs (> ~10 s), skipped unless `pytest --slow` (`./dev.py gate` passes it).
- `hw`: real hardware, skipped unless `pytest --hw` / AWTO_TEST_HW=1; the unit comes from AWTO_TEST_UNIT (docs/gates.md).
- `fw_image` / `fw_variant`: firmware image, resolution in scripts/test_image.py. Image absent = skip naming the
  fixture; with AWTO_TEST_STRICT=1 (`./dev.py gate`) it is a failure.
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import test_image as TI

STRICT_ENV = "AWTO_TEST_STRICT"
SKIP_TAG = "fixture fw_image"
_image_skips = []


def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", help="run tests marked slow")
    parser.addoption("--hw", action="store_true", help="run tests marked hw (real hardware; unit from AWTO_TEST_UNIT)")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: long simulator run, only with --slow")
    config.addinivalue_line("markers", "hw: needs real hardware, only with --hw or AWTO_TEST_HW=1")


def pytest_collection_modifyitems(config, items):
    hw_on = config.getoption("--hw") or os.environ.get("AWTO_TEST_HW") == "1"
    for it in items:
        if "slow" in it.keywords and not config.getoption("--slow"):
            it.add_marker(pytest.mark.skip(reason="slow: run with --slow"))
        if "hw" in it.keywords and not hw_on:
            it.add_marker(pytest.mark.skip(reason="hw: real hardware, run with --hw (AWTO_TEST_UNIT)"))


def _unavailable(e):
    msg = f"{SKIP_TAG}: {e}"
    if os.environ.get(STRICT_ENV) == "1":
        pytest.fail(msg + f" ({STRICT_ENV}=1: an absent image is a failure)", pytrace=False)
    pytest.skip(msg)


@pytest.fixture(scope="session")
def fw_image():
    """The tree's firmware image (.stem / .bin / .map / .build_json / .settings_table paths)."""
    try:
        return TI.base()
    except TI.ImageUnavailable as e:
        _unavailable(e)


@pytest.fixture(scope="session")
def fw_variant(fw_image):
    """fw_variant("clk87" | "t0ev" | "nofrc" | "<-D entry>", ...): the base source state plus those defines."""
    def get(kind, *defs):
        try:
            return TI.variant(kind, *defs)
        except TI.ImageUnavailable as e:
            _unavailable(e)
    return get


@pytest.fixture(scope="session")
def fw_build_tree(fw_image):
    """This tree, with the asm / sources of the last build (tmp/sdcc-port) for the static delay analysis."""
    try:
        TI.restore_port()
    except TI.ImageUnavailable as e:
        _unavailable(e)
    if not (TI.ROOT / "tmp/sdcc-port/asm_bank").is_dir():
        _unavailable("tmp/sdcc-port/asm_bank of this tree absent (no build here)")
    return TI.ROOT


def pytest_runtest_logreport(report):
    if (report.skipped or report.failed) and SKIP_TAG in str(report.longrepr):
        _image_skips.append(report.nodeid)


def pytest_terminal_summary(terminalreporter):
    strict = os.environ.get(STRICT_ENV) == "1"
    terminalreporter.write_line(f"image tests skipped (no firmware image): {len(_image_skips)}" + (" [strict: failures]" if strict else ""))
