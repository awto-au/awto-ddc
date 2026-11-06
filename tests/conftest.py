"""`slow` tests (full simulator runs, > ~10 s each) are skipped unless `pytest --slow`; default suite stays ~30 s."""
import pytest


def pytest_addoption(parser):
    parser.addoption("--slow", action="store_true", help="run tests marked slow")


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: long simulator run, only with --slow")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--slow"):
        return
    skip = pytest.mark.skip(reason="slow: run with --slow")
    for it in items:
        if "slow" in it.keywords:
            it.add_marker(skip)
