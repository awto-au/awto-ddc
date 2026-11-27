import sys; sys.path.insert(0,'scripts')
import ddc_sim as D, fw_sim as S
from pathlib import Path
b=Path('tmp/fw/AWT26110003-wb-osd67i-be.bin')
eng=D.DdcEngine(); bus=S.SimBus(b,b.with_suffix('.map'),devs=[eng],video='1080p60'); d=D.Mccs(bus,eng)
bus.wait(0.3)
for c in (0xDF,0xE0,0xE1,0xE0):
    r=d.tx(bytes([0x01,c])); print(hex(c), r.hex() if r else None, 'raw', eng.tx.hex())
bus.close()
