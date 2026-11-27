import sys; sys.path.insert(0,'scripts')
import ddc_sim as D, fw_sim as S
from pathlib import Path
b=Path('tmp/fw/AWT26110003-wb-osd67i-be.bin')
eng=D.DdcEngine(); bus=S.SimBus(b,b.with_suffix('.map'),devs=[eng],video='1080p60'); d=D.Mccs(bus,eng)
bus.wait(0.3); t0=bus.now()
for i in range(160):
    r=d.tx(bytes([0x01,0xDF]))
    if r is None: print('miss at %.3f s fw' % (bus.now()-t0), 'mode', bus.mode_state())
bus.close()
