import sys, time
sys.path.insert(0, "/mnt/2tb/git/awto-ddc-dpflash/scripts")
import i2cbus, rtd_flash_sector as F
from rtd_flash_sector import Rtd, ENGINE_OPS, PAGE
F.LOG = sys.stdout
i2cbus.require_unit(15, "AWT26110002", None)
isp = Rtd(15)
run = lambda ops, addr=0x4A: i2cbus.run_ops(isp._xfer, addr, ops)
isp.write(0x6F, 0x80)
h = lambda: hex(isp.read(0x6F))
try:
    for o in ENGINE_OPS: isp.write(*o)
    isp.program_setup()
    addr = 0xE0000 - PAGE
    a2, a1 = addr >> 16, (addr >> 8) & 255
    print("idle", h())
    for k in range(4):
        v = isp.read(0x6F)
        t = time.monotonic()
        r = run([(0x4B, bytes([0x64, a2, a1])), bytes([0x70]) + b"\xff" * 256, bytes([0x6F, v | 0x20]), bytes([0x6F]), 1])[0][0]
        t1 = time.monotonic() - t
        rs = []
        for _ in range(6):
            rs.append(hex(isp.read(0x6F)))
        print(f"page {k}: v={v:#x} ioctl {t1*1e3:.1f} ms r={r:#x} then {rs}")
    # same but data+start as separate ioctls
    for k in range(3):
        v = isp.read(0x6F)
        run([(0x4B, bytes([0x64, a2, a1]))]); run([bytes([0x70]) + b"\xff" * 256])
        run([bytes([0x6F, v | 0x20])])
        print(f"sep {k}: v={v:#x}", [hex(isp.read(0x6F)) for _ in range(4)])
finally:
    try: isp.write(0xEE, 0x02)
    except OSError: pass
