"""Static checks for the 2026-11-19 production changes: read-behind double read (rotation) and FFF1 default."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SDK = ROOT / "fw/sdk"


def test_rotation_page_size_read_twice():
    src = (SDK / "Kernel/Scaler/ScalerFunction/Code/ScalerRotation.c").read_text()
    body = re.search(r"static BYTE ScalerRotationGetDcSysPageSel\(void\)\s*\{(.*?)\n\}", src, re.S).group(1)
    assert len(re.findall(r"ScalerGetBit\(PA0_05_DC_SYS_MISC", body)) == 2
    assert "switch(ScalerRotationGetDcSysPageSel())" in src
    assert "ScalerGetBit(PA0_05_DC_SYS_MISC" not in src.replace(body, "")


def test_fff1_default_set_at_mcu_init():
    proj = (SDK / "Project/Header/RL6449_Project.h").read_text()
    assert re.search(r"AWTO_SCA_WR_INTRVL_SEL\s+12\b", proj)
    mcu = (SDK / "Kernel/Scaler/ScalerFunction/Code/ScalerMcu.c").read_text()
    assert "MCU_FFF1_SCA_WR_INTRVL = (MCU_FFF1_SCA_WR_INTRVL & ~AWTO_SCA_WR_INTRVL_SEL_MASK) | AWTO_SCA_WR_INTRVL_SEL;" in mcu
    body = mcu.split("void ScalerMcuInitial(void)\n{", 1)[1]
    assert body.lstrip().split("\n", 2)[1].lstrip().startswith("MCU_FFF1_SCA_WR_INTRVL")
    assert "AWTO_NOP8" not in proj
