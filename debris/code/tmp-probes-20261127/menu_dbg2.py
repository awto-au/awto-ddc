import sys; sys.path.insert(0,'scripts')
import menu_cli as M, settings_cli as C, fw_sim as S
from pathlib import Path
b=Path('tmp/fw/AWT26110003-wb-osd67g-be.bin'); mt=b.with_suffix('.map').read_text()
bus=S.SimBus(b,b.with_suffix('.map')); box=C.Box(bus,mt,True); m=M.Menu(box,mt,True)
mode=sys.argv[1]
if mode=='direct':
    box.wr=lambda off,v: bus.m.wr(box.base+off, bytes([v&255]))
    box.rd=lambda off: (bus.wait(0.003), bus.m.rd(box.base+off,1)[0])[1]
m.cmd('open',0xFE)
bad=0
for rep in range(2):
  for k,e in enumerate(M.entries(0xFE)):
    m.cmd('select',e); s=m.state()
    if s['item_page']!=e&0x7f: bad+=1; print('BAD',k,hex(e),M.Menu.show(s))
print(mode,'bad',bad)
bus.close()
