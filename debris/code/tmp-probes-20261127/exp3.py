import sys,time,os,re
sys.path.insert(0,'scripts')
from pathlib import Path
import fw_profile as P, fw_sim as F
b=Path('tmp/fw/AWT26110003-wb-dbg1-be.bin'); m=Path('tmp/fw/AWT26110003-wb-dbg1-be.map')
s,sym,where=P.boot(b.read_bytes(),m,True,open('/dev/null','w'))
s.send('delete')
time.sleep(0.5); s.read_until(rb"zzzz",0.3); s.buf=b""
N=2000
t=time.time()
s.p.stdin.write(("step 1\n"*N).encode()); s.p.stdin.flush()
n=0
while n<N and time.time()-t<30:
    r,_,_=__import__('select').select([s.p.stdout],[],[],0.5)
    if r: s.buf+=os.read(s.p.stdout.fileno(),1<<20)
    n=len(re.findall(rb"stepped",s.buf))
print(n,time.time()-t)
s.send('break xram w 0xf6e5')
s.buf=b""
for k in range(40):
    s.p.stdin.write(("step 1\n"*2000).encode()); s.p.stdin.flush()
    n=0; t=time.time()
    while n<2000 and time.time()-t<30:
        r,_,_=__import__('select').select([s.p.stdout],[],[],0.5)
        if r: s.buf+=os.read(s.p.stdout.fileno(),1<<20)
        n=len(re.findall(rb"F 0x",s.buf))
    i=s.buf.find(b"Event")
    if i>=0:
        print(k,s.buf[max(0,i-700):i+700].decode(errors='replace')); break
    s.buf=b""
