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
try:
    for o in ENGINE_OPS: isp.write(*o)
    isp.program_setup()
    addr = 0xE0000 - PAGE
    h = lambda: hex(isp.read(0x6F))
    print("idle", h(), h())
    isp.write(0x64, addr >> 16); print("after 64:", h())
    isp.write(0x65, (addr >> 8) & 255); print("after 65:", h(), h(), h())
    run([bytes([0x70]) + b"\xff" * 256]); print("after 256B data:", h())
    isp.write(0x6F, isp.read(0x6F) | 0x20); print("after start:", h(), h(), h())
    print("next:", h())
    # 4B address
    run([bytes([0x64, addr >> 16, (addr >> 8) & 255])], 0x4B); print("after 4B addr:", h(), h(), h())
    isp.write(0x64, addr >> 16); isp.write(0x65, (addr >> 8) & 255); print("after sep addr:", h())
    # ready within one ioctl: addr write then reads
    r = run([bytes([0x64, addr >> 16, (addr >> 8) & 255]) ,bytes([0x6F]), 1, bytes([0x6F]), 1], 0x4B)
    print("4B addr then reads(4B):", [x.hex() for x in r])
    r = run([(0x4B, bytes([0x64, addr >> 16, (addr >> 8) & 255])), bytes([0x6F]), 1, bytes([0x6F]), 1])
    print("4B addr + 4A reads:", [x.hex() for x in r])
    # is 6F.4 settable?
    isp.write(0x6F, 0x92); print("wrote 92:", h()); isp.write(0x6F, 0x82); print("wrote 82:", h())
finally:
    try: isp.write(0xEE, 0x02)
    except OSError: pass
