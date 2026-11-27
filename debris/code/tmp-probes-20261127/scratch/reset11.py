import sys
sys.path.insert(0, "/mnt/2tb/git/awto-ddc-dpflash/scripts")
import i2cbus
from rtd_flash_sector import Rtd
isp = Rtd(11)
print("6F", hex(isp.read(0x6F)), "60", hex(isp.read(0x60)))
try: isp.write(0xEE, 0x02)
except OSError as e: print("reset", e)
