import re,sys,itertools
import numpy as np
sys.path.insert(0,"scripts")
import osd_vlc as V
exec(open("scripts/qc_osd_patterns.py").read().split("def main")[0].split("import numpy as np")[1].replace("ROOT = Path","ROOT0 = Path").replace("sys.path.insert(0, str(Path(__file__).resolve().parent))\nimport osd_vlc as V  # noqa: E402",""),globals()) if False else None
src=open("/mnt/2tb/git/awto-ddc/scripts/qc_osd_patterns.py").read()
import importlib.util
spec=importlib.util.spec_from_file_location("qp","/mnt/2tb/git/awto-ddc/scripts/qc_osd_patterns.py"); qp=importlib.util.module_from_spec(spec); spec.loader.exec_module(qp)
t=qp.tables(qp.QC.read_text(errors="replace"))
def words(data):
    return [data[i:i+3] for i in range(0,len(data),3)]
def row_pixels(w,bpp,border,lsb,b1swap):
    b0,b1,b2=w
    if b1swap: b1=((b1&0x80)>>7)|((b1&0x7F)<<1)   # rotate left? try
    bs=(b0,b1,b2) if border==0 else (b2,b1,b0)
    W=bs[0]|bs[1]<<8|bs[2]<<16
    bits=format(W,"024b")
    px=[int(bits[i:i+bpp],2) for i in range(0,24,bpp)]
    return px[::-1] if lsb else px
def build(data,cols,rows,gw,gh,bpp,opts):
    wpr=gw*bpp//24                     # words per row
    ws=words(data); unit=gh*wpr
    gl=[]
    for g in range(len(ws)//unit):
        img=[]
        for r in range(gh):
            row=[]
            for k in range(wpr): row+=row_pixels(ws[g*unit+r*wpr+k],bpp,*opts)
            img.append(row)
        gl.append(np.array(img))
    H=gh;Wd=gw
    sheet=np.zeros((rows*H,cols*Wd),int)
    for i,g in enumerate(gl[:cols*rows]):
        r,c=divmod(i,cols); sheet[r*H:(r+1)*H,c*Wd:(c+1)*Wd]=g
    return sheet
def smooth(s):
    return ((s[:,1:]==s[:,:-1]).mean()+(s[1:,:]==s[:-1,:]).mean())/2
for name,cols,rows,bpp in (("tQCFONT_2BITBROOK",8,6,2),("tQCFONT_4BITLUFFY",11,7,4)):
    data=V.decode(t[name]); res=[]
    for opts in itertools.product((0,1),(0,1),(0,1)):
        if bpp==4 and opts[2]: continue
        s=build(data,cols,rows,12,18,bpp,opts); res.append((smooth(s),opts))
    res.sort(reverse=True)
    print(name,[(round(a,3),o) for a,o in res[:5]],"worst",round(res[-1][0],3))

print("--- plane variants")
def row_planar(ws,bpp,order,border,lsb):
    # ws: list of words for one row; split each 24-bit word into 12-bit halves = planes
    planes=[]
    for w in ws:
        b0,b1,b2=w
        bs=(b0,b1,b2) if border==0 else (b2,b1,b0)
        W=bs[0]|bs[1]<<8|bs[2]<<16
        bits=format(W,"024b")
        planes+= [bits[:12],bits[12:]]
    planes=[planes[i] for i in order]
    row=[]
    for x in range(12):
        v=0
        for p in planes: v=(v<<1)|int(p[x])
        row.append(v)
    return row[::-1] if lsb else row
def build_planar(data,cols,rows,bpp,order,border,lsb):
    wpr=bpp//2; ws=words(data); unit=18*wpr
    gl=[]
    for g in range(len(ws)//unit):
        gl.append(np.array([row_planar(ws[g*unit+r*wpr:g*unit+(r+1)*wpr],bpp,order,border,lsb) for r in range(18)]))
    sheet=np.zeros((rows*18,cols*12),int)
    for i,g in enumerate(gl[:cols*rows]):
        r,c=divmod(i,cols); sheet[r*18:(r+1)*18,c*12:(c+1)*12]=g
    return sheet
for name,cols,rows,bpp in (("tQCFONT_2BITBROOK",8,6,2),("tQCFONT_4BITLUFFY",11,7,4)):
    data=V.decode(t[name]); res=[]
    for order in itertools.permutations(range(bpp)):
        for border in (0,1):
            for lsb in (0,1):
                s=build_planar(data,cols,rows,bpp,order,border,lsb); res.append((smooth(s),order,border,lsb))
    res.sort(key=lambda x:-x[0])
    print(name,[(round(a,3),o,b,l) for a,o,b,l in res[:4]],"worst",round(res[-1][0],3))

from PIL import Image
pal=[tuple(qp.tables(qp.QC.read_text(errors="replace"))["tPALETTE_QC"][3*i:3*i+3]) for i in range(64)]
def img(s,bpp):
    out=np.zeros(s.shape+(3,),np.uint8)
    for v in range(1<<bpp): out[s==v]=(70,70,78) if v==0 else pal[v]
    return np.kron(out,np.ones((5,5,1),np.uint8))
d=V.decode(t["tQCFONT_2BITBROOK"])
a=img(build(d,8,6,12,18,2,(0,0,0)),2); b=img(build_planar(d,8,6,2,(0,1),0,0),2); c=img(build_planar(d,8,6,2,(1,0),0,0),2)
Image.fromarray(np.concatenate([a,np.full((a.shape[0],10,3),20,np.uint8),b,np.full((a.shape[0],10,3),20,np.uint8),c],1)).save("tmp/scratch/brook_variants.png")

d4=V.decode(t["tQCFONT_4BITLUFFY"])
ims=[]
for order in ((0,1,2,3),(3,2,1,0),(2,3,0,1),(1,0,3,2)):
    s=build_planar(d4,11,7,4,order,0,0); o=np.zeros(s.shape+(3,),np.uint8)
    for v in range(16): o[s==v]=(70,70,78) if v==0 else pal[v]
    ims.append(np.kron(o,np.ones((3,3,1),np.uint8))); ims.append(np.full((ims[-1].shape[0],8,3),20,np.uint8))
Image.fromarray(np.concatenate(ims[:-1],1)).save("tmp/scratch/luffy_variants.png")
