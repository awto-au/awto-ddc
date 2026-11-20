"""Log / display timestamps by the awto rule: ISO 8601, local offset with a colon (2026-11-15T00:39:14+11:00)."""
from datetime import datetime


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def now_ms() -> str:
    """Same, with milliseconds (2026-11-15T00:39:14.123+11:00): lines matched against a film."""
    return datetime.now().astimezone().isoformat(timespec="milliseconds")
