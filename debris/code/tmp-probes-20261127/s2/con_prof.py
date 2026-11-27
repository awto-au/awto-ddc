import sys; sys.path.insert(0, "scripts")
import fw_sim as S
from pathlib import Path
b = Path("tmp/fw/AWT26110002-wb-p14ui-s2-1-be.bin")
bus = S.SimBus(b, b.with_suffix(".map"), "conprof", None, boot=False, video="1080p60")
m = bus.m
for fn in ("AwtoBootConsole", "AwtoDiagConsole", "AwtoTextOpen", "AwtoConTitleBar", "AwtoConLogInit", "AwtoTextShow", "UserCommonInterfacePanelPowerTick", "ScalerDisplayDPTxLinkSequence", "ScalerDisplayDPTxStreamHanlder", "ScalerDDomainBackgroundEnable", "AwtoDiagT3Mark"):
    if "_" + fn in m.sym:
        m.stub(fn, lambda m_, r, fn=fn: print(f"{bus._t2():6d} {fn}") and None)
    else:
        print("missing", fn)
bus.run_until_mode(2, 160_000_000)
bus.close()
