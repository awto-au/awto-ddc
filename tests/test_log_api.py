"""scripts/_log.py Logger + no new local say/log copies (#302)."""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from _log import Logger

ISO = r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d"


def test_logger_stamps_file_and_stdout(tmp_path, capsys):
    p = tmp_path / "a" / "b.log"
    with Logger(p) as lg:
        lg.say("hello")
        lg.write("raw\n")
    out = capsys.readouterr().out
    lines = p.read_text().splitlines()
    assert re.fullmatch(ISO + " hello", lines[0]) and lines[1] == "raw"
    assert out.strip() == lines[0]


def test_logger_modes(tmp_path, capsys):
    p = tmp_path / "m.log"
    Logger(p).say("one")
    with Logger(p, mode="w", echo="stderr", stamp_echo=False, ms=True) as lg:
        lg.say("two")
    cap = capsys.readouterr()
    assert cap.err == "two\n"
    (line,) = p.read_text().splitlines()
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}[+-]\d\d:\d\d two", line)


def test_logger_file_only(tmp_path, capsys):
    with Logger(tmp_path / "f.log", echo=None) as lg:
        lg.say("x")
    assert capsys.readouterr().out == ""


def _copies():
    """say/log functions that own file handling or stamping instead of using _log."""
    out = set()
    for p in sorted((ROOT / "scripts").rglob("*.py")):
        src = p.read_text()
        for n in ast.walk(ast.parse(src)):
            if isinstance(n, ast.FunctionDef) and n.name in ("say", "log"):
                body = ast.get_source_segment(src, n)
                if re.search(r"\.write\(|isostamp|\.open\(|\bopen\(", body):
                    out.add(f"{p.relative_to(ROOT).as_posix()}:{n.name}")
    return out


def test_no_new_local_log_copies():
    allowed = set((ROOT / "tests/log_copies_baseline.txt").read_text().split())
    new = _copies() - allowed
    assert not new, f"use scripts/_log.py (Logger / log_line) instead of a local copy: {sorted(new)}"
