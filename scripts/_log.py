"""Shared script log line: append to the script's log file and echo (#302). stdlib only.

- File line: ISO 8601 stamp with local offset + message; log directory created on demand.
- Echo to stdout, flushed; `stamp_stdout=False` keeps the plain message on the terminal.
"""
from datetime import datetime
from pathlib import Path


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def log_line(msg: str, log: Path, *, stamp_stdout: bool = True) -> None:
    line = f"{stamp()} {msg}"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line if stamp_stdout else msg, flush=True)
