"""CPU suite (docs/cpu-suite.md): host logic, firmware / host case table agreement, generated tables, and a sim run when the suite images exist."""
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import cpu_suite as C

FW = ROOT / "fw/test/cpu_suite.c"


def fw_cases() -> dict:
    return {m.group(1): int(m.group(2)) for m in re.finditer(r"#define AWTO_CPU_C_(\w+)\s+(\d+)", FW.read_text())}


def fw_offsets() -> dict:
    """Mailbox field offsets of StAwtoCpu summed from the C declaration (sizes by type)."""
    text = FW.read_text()
    body = text[text.index("typedef struct\n{\n    BYTE ucGo;"):]
    body = body[:body.index("} StAwtoCpu;")]
    size = {"BYTE": 1, "WORD": 2, "unsigned long": 4}
    off, out = 0, {}
    for m in re.finditer(r"^\s+(BYTE|WORD|unsigned long)\s+(\w+);", body, re.MULTILINE):
        out[m.group(2)] = off
        off += size[m.group(1)]
    out["_end"] = off
    return out


def test_case_ids_match_firmware():
    fw = fw_cases()
    host = {c.name: c.cid for c in C.CASES}
    assert host == fw, "host case table and AWTO_CPU_C_* ids differ"
    assert len({c.cid for c in C.CASES}) == len(C.CASES)


def test_mailbox_offsets_match_firmware():
    o = fw_offsets()
    mine = {"ucGo": C.O_GO, "ucSeq": C.O_SEQ, "ucState": C.O_STATE, "ucPass": C.O_PASS, "ucStretch": C.O_STRETCH, "ucFlags": C.O_FLAGS, "usArg": C.O_ARG,
            "usArg2": C.O_ARG2, "usBad": C.O_BAD, "ulV0": C.O_V0, "ulV1": C.O_V1, "ulV2": C.O_V2, "usMs": C.O_MS, "ucCkcon": C.O_CKCON, "ucReady": C.O_READY,
            "usRcap": C.O_RCAP, "usBeat": C.O_BEAT, "ucStackHigh": C.O_STACK, "ucSpMax": C.O_SPMAX, "usBufAt": C.O_BUFAT, "usBufN": C.O_BUFN, "_end": C.O_END}
    assert mine == o


def test_every_case_has_a_reference_and_bound():
    for c in C.CASES:
        assert c.ref and c.what and c.bound_ms > 0 and c.runs, c.name


def test_crc16_check_value():
    assert C.crc16(b"123456789") == 0x29B1            # CRC-16/CCITT-FALSE


def fake(**kw):
    r = dict(done=True, state=C.ST_DONE, fwpass=1, bad=0, v0=0, v1=0, v2=0, ms=1, flags=0, ckcon=0, rcap=0, sp=0, stack=0)
    r.update(kw)
    return r


def test_judge_flags_bound_limit_and_crc():
    c = C.BY_NAME["M_CRC"]
    assert C.judge(c, C.Run(), fake(v0=0x1234), {"crc": 0x1234})[0]
    assert not C.judge(c, C.Run(), fake(v0=0x1234), {"crc": 0x4321})[0]          # CRC differs from the image bytes
    assert not C.judge(c, C.Run(), fake(ms=c.bound_ms + 1), {})[0]
    assert not C.judge(c, C.Run(), fake(flags=C.F_LIMIT), {})[0]
    assert not C.judge(c, C.Run(), fake(fwpass=0, bad=2), {})[0]
    assert not C.judge(c, C.Run(), fake(done=False), {})[0]
    assert C.judge(C.BY_NAME["R_WRITE"], C.Run(), fake(state=C.ST_REFUSED), {})[0]


def test_register_tables_are_current():
    r = subprocess.run([sys.executable, str(ROOT / "scripts/cpu_suite_regs.py"), "--check"])
    assert r.returncode == 0, "fw/test/cpu_suite_regs.inc is stale: run scripts/cpu_suite_regs.py"


def test_register_tables_exclude_ports():
    import cpu_suite_regs as G
    import reg_live_scan as L
    rd, wr = G.build()
    assert rd and wr
    assert not [a for a, _ in rd + [(w, 0) for w in wr] if L.excluded(a) or (a >> 8) > G.MAX_PAGE]


@pytest.mark.parametrize("clock", [87, 175, 350])
def test_sim_run(clock):
    img = ROOT / f"tmp/fw/AWT26110003-cpusuite-{clock}-be.bin"
    if not img.exists():
        pytest.skip(f"{img.name} not built (./dev.py cpu-suite --sim --build)")
    r = subprocess.run([sys.executable, str(ROOT / "scripts/cpu_suite.py"), "--sim", "--clocks", str(clock), "--bin", str(img)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-3000:]
