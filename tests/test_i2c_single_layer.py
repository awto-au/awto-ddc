"""awto-ddc#48: scripts/i2cbus.py is the only code that opens /dev/i2c-N or speaks i2c-dev ioctls.

Fails if any other .py (dev.py, scripts/, tests/) opens an i2c device, imports fcntl, or uses the
i2c-dev ioctl numbers/names. Comments and docstrings are ignored (AST, not grep).
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = {ROOT / "scripts" / "i2cbus.py"}
NAMES = {"I2C_RDWR", "I2C_SLAVE", "I2C_RETRIES", "I2C_TIMEOUT", "I2C_M_RD_RAW", "fcntl"}
CODES = {0x0701, 0x0702, 0x0703, 0x0707}          # I2C_RETRIES, I2C_TIMEOUT, I2C_SLAVE, I2C_RDWR


def sources():
    files = [ROOT / "dev.py", *sorted((ROOT / "scripts").glob("*.py")), *sorted((ROOT / "tests").glob("*.py"))]
    return [f for f in files if f not in ALLOWED and f != Path(__file__).resolve()]


def violations(path: Path) -> list[str]:
    src = path.read_text()
    out = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Import) and any(a.name == "fcntl" for a in n.names):
            out.append(f"{n.lineno}: import fcntl")
        elif isinstance(n, ast.ImportFrom) and n.module == "fcntl":
            out.append(f"{n.lineno}: from fcntl import")
        elif isinstance(n, ast.Name) and n.id in NAMES:
            out.append(f"{n.lineno}: {n.id}")
        elif isinstance(n, ast.Attribute) and n.attr in NAMES - {"fcntl"}:
            out.append(f"{n.lineno}: .{n.attr}")
        elif isinstance(n, ast.Constant) and isinstance(n.value, int) and not isinstance(n.value, bool) \
                and n.value in CODES:
            out.append(f"{n.lineno}: ioctl code {n.value:#06x}")
        elif isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr in ("open", "fdopen") \
                and "/dev/i2c" in (ast.get_source_segment(src, n) or ""):
            out.append(f"{n.lineno}: opens an i2c device")
    return out


def test_only_i2cbus_touches_the_bus():
    bad = {str(p.relative_to(ROOT)): v for p in sources() if (v := violations(p))}
    assert not bad, f"use scripts/i2cbus.py instead: {bad}"


def test_detector_catches_a_violation(tmp_path):
    p = tmp_path / "bad.py"
    p.write_text("import os, fcntl\nfd = os.open('/dev/i2c-3', os.O_RDWR)\nfcntl.ioctl(fd, 0x0707, 0)\n")
    assert len(violations(p)) >= 3
