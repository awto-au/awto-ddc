"""Sync log colour classes (fw/awto/sync_classes.tsv): the one reader for the firmware generator, the host decoder and the tests."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def _root() -> Path:
    env = os.environ.get("AWTO_DDC_REPO")
    if env:
        return Path(env)
    r = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=Path(__file__).resolve().parent, capture_output=True, text=True, check=False)
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else Path(__file__).resolve().parents[1]


TSV = _root() / "fw/awto/sync_classes.tsv"
DEFAULT = "normal"                                   # a row with no class column
SGR_RESET = "\x1b[0m"


def use_colour() -> bool:
    """colour only on a terminal: this process's stdout, or the terminal dev.py runs under (it pipes the child: AWTO_TTY=1)"""
    return os.environ.get("NO_COLOR") is None and (sys.stdout.isatty() or os.environ.get("AWTO_TTY") == "1")


def load(path: Path = TSV) -> dict[str, dict]:
    """name -> {style: AWTO_T_STYLE_* macro, ansi: SGR code}; file order kept (the first is the default class)"""
    out: dict[str, dict] = {}
    for ln in path.read_text().splitlines():
        if not ln.strip() or ln.startswith("#"):
            continue
        name, style, ansi, _colour = ln.split("\t")
        assert name not in out, f"{path.name}: class {name} twice"
        out[name] = {"style": style, "ansi": int(ansi)}
    assert DEFAULT in out, f"{path.name}: no '{DEFAULT}' class"
    return out


def check(name: str, classes: dict[str, dict] | None = None) -> str:
    """class name of a tsv row ('' = the default); unknown names fail"""
    name = name or DEFAULT
    assert name in (classes or load()), f"sync.tsv: unknown colour class '{name}'"
    return name


def paint(text: str, name: str, tty: bool, classes: dict[str, dict] | None = None) -> str:
    """text in the class colour on a terminal; the default class and a non-TTY stay plain (a log file never holds escapes)"""
    if not tty or (name or DEFAULT) == DEFAULT:
        return text
    return f"\x1b[{(classes or load())[check(name, classes)]['ansi']}m{text}{SGR_RESET}"
