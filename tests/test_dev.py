"""Contract tests for dev.py — copy into <repo>/tests/ alongside dev.py.

These enforce the awto dev.py contract (see docs/coding/orchestration.md
and dev.py-template/README.md) so a drifting dev.py fails CI rather than
silently confusing an agent.

Run: pytest tests/test_dev.py -q
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

# dev.py lives at the repo root when logic is inline, or is a shim to
# scripts/dev.py. Either way, resolve it from the repo root.
REPO = Path(__file__).resolve().parents[1]
DEV = REPO / "dev.py"

pytestmark = pytest.mark.skipif(not DEV.exists(), reason="no dev.py in this repo")


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(DEV), *args],
                          capture_output=True, text=True, cwd=REPO)


@pytest.fixture(scope="module")
def described() -> dict:
    r = run("describe")
    assert r.returncode == 0, f"describe must exit 0, got {r.returncode}"
    return json.loads(r.stdout)


# --- the machine-readable contract -----------------------------------------

def test_describe_is_valid_json(described):
    assert isinstance(described, dict)


def test_describe_has_required_keys(described):
    assert {"project", "commands"} <= described.keys()
    assert described["project"], "project must not be empty"


def test_describe_project_is_filled_in(described):
    assert described["project"] != "<PROJECT>", \
        "scaffold placeholder left in place — set PROJECT"


def test_every_command_has_a_summary(described):
    for name, meta in described["commands"].items():
        assert meta.get("summary"), f"{name} has no summary"


def test_standard_commands_present(described):
    # The floor every awto repo must expose.
    required = {"describe", "test", "gate"}
    missing = required - described["commands"].keys()
    assert not missing, f"missing standard commands: {sorted(missing)}"


# --- human help and exit codes ---------------------------------------------

def test_help_exits_2_and_lists_every_command(described):
    r = run("--help")
    assert r.returncode == 2, "usage must exit 2"
    for name in described["commands"]:
        assert name in r.stdout, f"{name} missing from --help"


def test_bare_invocation_is_usage():
    assert run().returncode == 2


def test_unknown_command_exits_2():
    r = run("definitely-not-a-command")
    assert r.returncode == 2
    assert "unknown command" in (r.stdout + r.stderr).lower()


# --- logging conventions (Tier A) ------------------------------------------

LINE = re.compile(
    r"^\d{2}:\d{2}:\d{2}\.\d{6}[+-]\d{4}\s+"     # local time WITH offset
    r"(FATAL|ERROR|WARN|INFO|DEBUG|ALERT)\s+"    # level
    r"\[[^\]]+\]\s"                              # [origin]
)


def test_log_lines_are_timestamped_local_with_offset():
    r = run("doctor")
    lines = [l for l in r.stderr.splitlines() if l.strip()]
    assert lines, "doctor produced no log output"
    bad = [l for l in lines if not LINE.match(l)]
    assert not bad, f"log lines not in awto format: {bad[:3]}"


def test_log_is_not_utc():
    r = run("doctor")
    assert " UTC" not in r.stderr, \
        "Tier A logs must be local time (AEST/AEDT), not UTC"


def test_log_file_is_written_and_plain():
    run("doctor")
    log = REPO / "tmp" / "logs" / "dev.log"
    assert log.exists(), "tmp/logs/dev.log must be written"
    assert "\033[" not in log.read_text(encoding="utf-8"), \
        "ANSI colour must never be written to the log file"


def test_colour_suppressed_when_not_a_tty():
    # subprocess pipes are not TTYs, so output must already be plain.
    r = run("doctor")
    assert "\033[" not in r.stderr
