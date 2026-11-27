import sys; sys.path.insert(0,'scripts')
import menu_cli as M, settings_cli as C, fw_sim as S, settings_table as T
from pathlib import Path
b=Path('tmp/fw/AWT26110003-wb-osd67h-be.bin'); mt=b.with_suffix('.map').read_text()
bus=S.SimBus(b,b.with_suffix('.map')); box=C.Box(bus,mt,True); m=M.Menu(box,mt,True)
m.cmd('open',4)
for e in M.entries(4):
    i=T.ROWS[e]['id']
    try:
        m.cmd('select',i); print(i, M.Menu.show(m.state()))
    except SystemExit as x: print(i,'ERR',x, box.xrd(box.base,12).hex())
bus.close()
