"""fw_build.vector_table: required vectors must have a handler, the SDCC asm comment format must still match (#8)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import fw_build as B

REQ = {0: "EXINT0", 1: "Timer0", 2: "EXINT1", 5: "Timer2", 8: "WDT"}
NAMES = {0: "SysEXINT0", 1: "SysTimerIntProc0", 2: "SysEXINT1", 5: "SysTimerIntProc2", 8: "SysTimerWDIntProc"}


def asm(n, name, fmt="; Kernel/System/Code/SysInt.c:{ln}: void {name}(void) __interrupt({n})"):
    return fmt.format(ln=40 + n, name=name, n=n) + "\n_" + name + ":\n\treti\n"


def texts(skip=(), fmt=None):
    return [asm(n, v, *([fmt] if fmt else [])) for n, v in NAMES.items() if n not in skip]


def test_all_present():
    isr, lines = B.vector_table(texts(), REQ)
    assert isr == {n: "_" + v for n, v in NAMES.items()}
    assert "\tljmp _SysEXINT0" in lines and lines.count("\treti") == B.VEC_COUNT - len(NAMES)


def test_required_missing_fails():
    with pytest.raises(ValueError, match=r"4|WDT|8 \(WDT"):
        B.vector_table(texts(skip=(8,)), REQ)


def test_optional_missing_is_reti():
    isr, lines = B.vector_table(texts(), REQ)
    assert 4 not in isr and "\treti" in lines


def test_extra_required_serial_fails_without_handler():
    with pytest.raises(ValueError, match="serial"):
        B.vector_table(texts(), {**REQ, 4: "serial"})


def test_comment_format_changed_fails():
    with pytest.raises(ValueError, match="no `"):
        B.vector_table(texts(fmt="// {name} interrupt {n}"), REQ)


def test_number_outside_table_fails():
    with pytest.raises(ValueError, match="outside the vector table"):
        B.vector_table(texts() + [asm(B.VEC_COUNT + 3, "SysBogus")], REQ)
