import sys
sys.argv=['x']
exec(open('/mnt/2tb/git/awto-ddc/tmp/vlcdec.py').read().split("for off in (0x228C6")[0])
from PIL import Image
L,end,nibs=dec(0x23B41)
by=[(nibs[i]<<4)|nibs[i+1] for i in range(0,len(nibs)-1,2)]
bits=[]
for i in range(0,len(by)-2,3):
    for b in (by[i+2],by[i+1],by[i]): bits+=[(b>>k)&1 for k in range(7,-1,-1)]
g0=103;cols=23;rows=21
im=Image.new("L",(cols*12,rows*18),255)
for n in range(cols*rows):
    for p in range(216):
        x=n%cols*12+p%12;y=n//cols*18+p//12
        im.putpixel((x,y),0 if bits[(g0+n)*216+p] else 255)
im.save("/home/dan/vendors/realtek/analysis/logo/glyphdec/hdr_023b41_logo_23x21.png")
