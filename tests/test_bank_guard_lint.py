"""#360 bank_guard_lint: which function prologues count as a state-byte early return"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import bank_guard_lint as L


def test_state_byte_guard():
    assert L.guard_of("\n    if(g_ucAwtoPanelOwn != 0)\n    {\n        return;\n    }\n", set()) == "g_ucAwtoPanelOwn != 0"
    assert L.guard_of(" BYTE ucI;\n if(GET_TARGET_POWER_STATUS() == _POWER_STATUS_NONE) return _FALSE;", set()) is not None
    assert L.guard_of(" if((s_ucX == 0) && (ucArg == 1)) return;", {"ucArg"}) is not None      # a parameter beside the state


def test_not_a_plain_guard():
    assert L.guard_of(" if(ScalerGetByte(P0_02) == 0) return;", set()) is None                 # a real call
    assert L.guard_of(" if(g_ucX != 0) { AwtoSyncPush(1, 2, 3); return; }", set()) is None       # work before the return
    assert L.guard_of(" BYTE ucV = AwtoMs();\n if(g_ucX) return;", set()) is None                 # a call in the declarations
    assert L.guard_of(" if(ucArg == 0) return;", {"ucArg"}) is None                              # parameter only: no state byte
