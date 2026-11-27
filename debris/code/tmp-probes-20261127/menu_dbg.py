import sys; sys.path.insert(0,'scripts')
import menu_cli as M, settings_cli as C, fw_sim as S
from pathlib import Path
b=Path('tmp/fw/AWT26110003-wb-osd67g-be.bin'); mt=b.with_suffix('.map').read_text()
bus=S.SimBus(b,b.with_suffix('.map')); box=C.Box(bus,mt,True); m=M.Menu(box,mt,True)
m.cmd('open',0xFE)
for k,e in enumerate(M.entries(0xFE)):
    m.cmd('select',e); s=box.xrd(m.addr,17); print(k,hex(e), s.hex(), M.Menu.show(m.state()))
bus.close()
