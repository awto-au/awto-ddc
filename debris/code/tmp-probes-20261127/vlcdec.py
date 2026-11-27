import sys
d=open('/home/dan/vendors/realtek/analysis/dumps/jxc-4k-flash-bus20.bin','rb').read()
codes=["0","100","1010","1011","1100","11010","11011","11100","111010","111011","111100","111101","1111100","1111101","1111110","11111110"]
def dec(off):
    m=d[off:off+8]; L=(d[off+8]<<8)|d[off+9]
    vals=[]
    for b in m: vals+= [b>>4,b&15]
    tab={c:v for c,v in zip(codes,vals)}
    nibs=[];code="";end=None
    for bi,b in enumerate(d[off+10:off+10+L+8]):
        for k in range(8):
            code+=str((b>>k)&1)
            if code in tab: nibs.append(tab[code]);code=""
            elif code=="11111111": end=(bi,k);break
            elif len(code)>8: return None
        if end: break
    return L,end,nibs
for off in (0x228C6,0x22BED,0x231AB,0x23B41):
    r=dec(off)
    if not r: print(hex(off),"fail");continue
    L,end,nibs=r
    nb=len(nibs)//2
    print(hex(off),"hdrlen",L,"end at byte",end,"nibbles",len(nibs),"bytes",nb,"triplets",nb/3,"glyphs12x18",nb/27)

def render(off,cols):
    from PIL import Image
    L,end,nibs=dec(off)
    by=[(nibs[i]<<4)|nibs[i+1] for i in range(0,len(nibs)-1,2)]
    bits=[]
    for i in range(0,len(by)-2,3):
        for b in (by[i+2],by[i+1],by[i]):
            bits+=[(b>>k)&1 for k in range(7,-1,-1)]
    g=len(bits)//216
    rows=(g+cols-1)//cols
    im=Image.new("L",(cols*13,rows*19),128)
    for n in range(g):
        for p in range(216):
            x=n%cols*13+p%12; y=n//cols*19+p//12
            im.putpixel((x,y),0 if bits[n*216+p] else 255)
    im=im.resize((im.width*3,im.height*3),Image.NEAREST)
    out=f"/home/dan/vendors/realtek/analysis/logo/glyphdec/hdr_{off:06x}.png"
    im.save(out);print(out,g)
if len(sys.argv)>1:
    for off in (0x228C6,0x22BED,0x231AB,0x23B41): render(off,20)
