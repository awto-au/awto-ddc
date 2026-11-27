import sys, time
sys.path.insert(0, "/mnt/2tb/git/awto-ddc-dpflash/scripts")
import i2cbus, rtd_flash_sector as F
from rtd_flash_sector import Rtd, ENGINE_OPS, PAGE
F.LOG = sys.stdout
i2cbus.require_unit(15, "AWT26110002", None)
isp = Rtd(15)
run = lambda ops, addr=0x4A: i2cbus.run_ops(isp._xfer, addr, ops)
isp.write(0x6F, 0x80)
assert isp.read(0x6F) & 0x80
h = lambda: hex(isp.read(0x6F))
try:
    for o in ENGINE_OPS: isp.write(*o)
    isp.program_setup()
    addr = 0xE0000 - PAGE
    a2, a1 = addr >> 16, (addr >> 8) & 255
    def page(how):
        if how == "4A":
            isp.write(0x64, a2); isp.write(0x65, a1)
        else:
            run([bytes([0x64, a2, a1])], 0x4B)
        print(how, "addr staged:", h(), end="; ")
        run([bytes([0x70]) + b"\xff" * 256]); print("data:", h(), end="; ")
        isp.write(0x6F, isp.read(0x6F) | 0x20); print("start:", h(), h(), h(), h())
    page("4A"); page("4A"); page("4B"); page("4B"); page("4A")
    print("final", h(), h())
    isp.write(0x64, a2); print("only 64:", h())
    isp.write(0x65, a1); print("then 65:", h())
    run([bytes([0x64, a2, a1])], 0x4B); print("4B:", h())
finally:
    try: isp.write(0xEE, 0x02)
    except OSError: pass
