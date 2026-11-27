import sys,re
sys.path.insert(0,'scripts')
import fw_sim as F
from pathlib import Path
stem=sys.argv[1]
b=Path(f'tmp/fw/{stem}.bin'); img=b.read_bytes()
sym,where=F.parse_map(Path(f'tmp/fw/{stem}.map').read_text(errors='replace'),img)
fl=F.FlashPort(img)
s=F.open_native(img,Path('tmp/bc/x'),open('tmp/bc/log','w'),fl)
out=F.run_chunk(s,fl,2000000)
print(out[-500:])
s.send("dump iram 0x00 0xff"); print(s.read_until(rb"0xf8 [^\n]*\n",10))
print("bank",F.cur_bank(s))
s.send("dump rom 0x940 0x970"); print(s.read_until(rb"0x0960[^\n]*\n",10))
s.send("quit")
for n in ("__bs_call","__bs_ret","__gptrput","__bs_cur"): print(n,hex(sym.get(n,0)))
