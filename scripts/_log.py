"""Shared script log line: append to the script's log file and echo (#302). stdlib only.

- File line: ISO 8601 stamp with local offset + message; log directory created on demand.
- Echo to stdout, flushed; `stamp_stdout=False` keeps the plain message on the terminal.
"""
import sys
from datetime import datetime
from pathlib import Path
from typing import Self


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def log_line(msg: str, log: Path, *, stamp_stdout: bool = True) -> None:
    line = f"{stamp()} {msg}"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line if stamp_stdout else msg, flush=True)


_SHARED: dict[Path, "Logger"] = {}


def shared(path: Path, **kw) -> "Logger":
    """Lazily opened Logger per path, for scripts without a main() that owns the handle."""
    path = Path(path)
    if path not in _SHARED:
        _SHARED[path] = Logger(path, **kw)
    return _SHARED[path]


class Logger:
    """Open-once log file (#302): `say` = stamped line to the file and the echo stream, line-buffered.

    - `Logger(path)` appends (`mode="w"` truncates); `./tmp/logs` etc. created on demand.
    - `echo`: "stdout" (default), "stderr" or None (file only); `stamp_echo=False` echoes the plain message.
    - File-like `write`/`flush`/`close` for callers that also write raw text; context manager closes.
    """

    def __init__(self, path: Path, *, mode: str = "a", echo: str | None = "stdout", stamp_echo: bool = True,
                 ms: bool = False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._f = self.path.open(mode, encoding="utf-8", buffering=1)
        self.echo = echo
        self.stamp_echo = stamp_echo
        self.ms = ms

    def stamp(self) -> str:
        return datetime.now().astimezone().isoformat(timespec="milliseconds" if self.ms else "seconds")

    def say(self, msg: str = "") -> None:
        line = f"{self.stamp()} {msg}"
        self._f.write(line + "\n")
        if self.echo:
            print(line if self.stamp_echo else msg, file=sys.stderr if self.echo == "stderr" else sys.stdout, flush=True)

    def write(self, text: str) -> int:
        return self._f.write(text)

    def flush(self) -> None:
        self._f.flush()

    def close(self) -> None:
        self._f.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc) -> None:
        self.close()
