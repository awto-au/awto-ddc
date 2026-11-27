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
    A = (0x4B, bytes([0x64, a2, a1]))
    D = bytes([0x70]) + b"\xff" * 256
    S = lambda v: bytes([0x6F, v | 0x20])
    def fix():
        isp.write(0x64, a2); isp.write(0x65, a1)   # re-arm via old path
        print("  rearm:", h())
    def poll(v0=None):
        n=0
        while True:
            r = isp.read(0x6F); n += 1
            if not r & 0x20 or n >= 15: return r, n
    def v1(v):
        r = run([S(v), bytes([0x6F]), 1])[0][0]
        return (hex(r),) + tuple(map(hex, poll()))
    def v2(v):
        run([S(v)]); return tuple(map(hex, poll()))
    variants = {
      "[A,D] | [S,idx,r]": lambda v: (run([A, D]), v1(v))[1],
      "[A,D] | [S] | polls": lambda v: (run([A, D]), v2(v))[1],
      "A | D | S | polls": lambda v: (run([A]), run([D]), v2(v))[2],
    }
    for name, fn in variants.items():
        res = []
        for k in range(4):
            v = isp.read(0x6F)
            t = time.monotonic()
            x = fn(v)
            res.append((hex(v), x, f"{(time.monotonic()-t)*1e3:.1f}ms"))
        print(name, res)
finally:
    try: isp.write(0xEE, 0x02)
    except OSError: pass
