"""Best-effort diagnostics during ISP; recovery manifests remain mandatory (#82).

Logging must never interrupt a page program, sector verification or exit reset.
Keep the first failure per sink in memory and report it through surviving output.
"""
from __future__ import annotations

import sys
from contextlib import contextmanager


class Diagnostics:
    def __init__(self):
        self.failures: dict[str, str] = {}

    def failed(self, name, error):
        self.failures.setdefault(name, str(error))

    def stream(self, stream, name):
        return BestEffortStream(stream, name, self)

    def open(self, path):
        return self.stream(path.open("a"), str(path))

    @contextmanager
    def output(self):
        stdout, stderr = sys.stdout, sys.stderr
        sys.stdout = self.stream(stdout, "stdout")
        sys.stderr = self.stream(stderr, "stderr")
        try:
            yield
        finally:
            # Buffered ENOSPC/EPIPE must be observed before computing the result.
            sys.stdout.flush()
            sys.stderr.flush()
            sys.stdout, sys.stderr = stdout, stderr

    def report(self):
        if self.failures:
            message = "WARNING: flash diagnostics incomplete: " + "; ".join(
                f"{name}: {error}" for name, error in self.failures.items()) + "\n"
            for name, stream in (("stdout", sys.stdout), ("stderr", sys.stderr)):
                out = self.stream(stream, name)
                out.write(message)
                out.flush()


class BestEffortStream:
    def __init__(self, stream, name, diagnostics):
        self.stream, self.name, self.diagnostics = stream, name, diagnostics

    def write(self, text):
        try:
            self.stream.write(text)
        except (OSError, ValueError) as error:
            self.diagnostics.failed(self.name, error)
        return len(text)

    def flush(self):
        try:
            self.stream.flush()
        except (OSError, ValueError) as error:
            self.diagnostics.failed(self.name, error)

    def close(self):
        self.flush()
        try:
            self.stream.close()
        except (OSError, ValueError) as error:
            self.diagnostics.failed(self.name, error)

    def __getattr__(self, name):
        return getattr(self.stream, name)
