import sys; sys.path.insert(0,'scripts')
import ddc_sim as D, fw_sim as S
from pathlib import Path
b=Path('tmp/fw/AWT26110003-wb-osd67g-be.bin')
eng=D.DdcEngine(); bus=S.SimBus(b,b.with_suffix('.map'),devs=[eng],video='1080p60')
m=bus.m
hits={'n':0}
m.watch('AwtoDdcciPoll') if False else None
m.stub('AwtoDdcciPoll', lambda m_,r: hits.__setitem__('n',hits['n']+1))
bus.wait(0.3)
print('on', m.rd(m.addr('g_ucAwtoDdcciOn'),1), 'regs', m.rd(0xFE86,10).hex(), 'polls', hits)
d=D.Mccs(bus,eng); print(d.get(0x10), 'polls', hits, 'tx', eng.tx.hex(), 'regs', m.rd(0xFE86,10).hex())
bus.close()
