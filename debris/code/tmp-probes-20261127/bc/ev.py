import sys
sys.path.insert(0,'scripts')
import fw_sim as F
from pathlib import Path
b=Path('tmp/fw/AWT26110003-wb-sc1-be.bin'); nb=14
d=Path('tmp/bc/AWT26110003-wb-sc1-be')
s=F.Sim(None,open('tmp/bc/log','w'))
s.send(f"memory create chip flash 0x{nb*F.BANK:x} 8")
s.send("memory create banker xram 0xffff 0x0f rom 0x0000 0xffff")
for k in range(nb): s.send(f"memory create bank rom 0x0000 {k} flash 0x{k*F.BANK:x}")
for k in range(nb):
    s.send(f"set memory xram 0xffff {k}"); s.send(f'file "{d/f"bank{k}.ihx"}"')
    s.read_until(rb"Loading from[^\n]*bank%d\.ihx"%k,30)
s.send("set memory xram 0xffff 0"); s.send("reset")
s.send("break xram r 0xff7b"); s.send("break xram w 0xff7a")
s.send("step 20000000")
print(s.read_until(rb"Simulated \d+ ticks[^\n]*\n",120))
s.send("step 20000000")
print(s.read_until(rb"Simulated \d+ ticks[^\n]*\n",120))
s.send("quit")
