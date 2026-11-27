import sys,re
sys.path.insert(0,'scripts')
import fw_sim as F
from pathlib import Path
b=Path(sys.argv[1]); img=b.read_bytes(); nb=len(img)//F.BANK
d=Path('tmp/bc/'+b.stem); d.mkdir(exist_ok=True)
for k in range(nb): F.write_ihx(img[k*F.BANK:(k+1)*F.BANK], d/f"bank{k}.ihx")
log=open('tmp/bc/log','w')
s=F.Sim(None,log)
s.send(f"memory create chip flash 0x{nb*F.BANK:x} 8")
s.send("memory create banker xram 0xffff 0x0f rom 0x0000 0xffff")
for k in range(nb): s.send(f"memory create bank rom 0x0000 {k} flash 0x{k*F.BANK:x}")
for k in range(nb):
    s.send(f"set memory xram 0xffff {k}"); s.send(f'file "{d/f"bank{k}.ihx"}"')
    s.read_until(rb"Loading from[^\n]*bank%d\.ihx"%k,30)
s.send("set memory xram 0xffff 0"); s.send("reset")
s.send("step 20000000")
o=s.read_until(rb"Simulated \d+ ticks[^\n]*\n",120)
print(o[-600:])
s.send("dump xram 0xf6d0 0xf6ff"); print(s.read_until(rb"0xf6f8 [^\n]*\n",20))
s.send("quit")
