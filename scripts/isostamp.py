"""Log / display timestamps by the awto rule: ISO 8601, local offset with a colon (2026-11-15T00:39:14+11:00)."""
from datetime import datetime


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")
