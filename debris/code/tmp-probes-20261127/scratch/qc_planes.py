import sys,itertools
import numpy as np
sys.path.insert(0,"scripts")
import osd_vlc as V
import importlib.util
spec=importlib.util.spec_from_file_location("qp","/mnt/2tb/git/awto-ddc/scripts/qc_osd_patterns.py"); qp=importlib.util.module_from_spec(spec); spec.loader.exec_module(qp)
from PIL import Image
t=qp.tables(qp.QC.read_text(errors="replace"))
pr=t["tPALETTE_QC"]; pal=[tuple(pr[3*i:3*i+3]) for i in range(64)]
def planes_glyph(data,bpp,order):
    pl=[np.array(V.unpack_unit(data[p*27:(p+1)*27],12,18,1)) for p in range(bpp)]
    pl=[pl[i] for i in order]
    v=np.zeros((18,12),int)
    for p in pl: v=(v<<1)|p
    return v
def sheet(data,cols,rows,bpp,order):
    unit=27*bpp; n=len(data)//unit
    s=np.zeros((rows*18,cols*12),int)
    for i in range(min(n,cols*rows)):
        r,c=divmod(i,cols); s[r*18:(r+1)*18,c*12:(c+1)*12]=planes_glyph(data[i*unit:(i+1)*unit],bpp,order)
    return s
def smooth(s): return ((s[:,1:]==s[:,:-1]).mean()+(s[1:,:]==s[:-1,:]).mean())/2
def img(s,bpp,k):
    o=np.zeros(s.shape+(3,),np.uint8)
    for v in range(1<<bpp): o[s==v]=(70,70,78) if v==0 else pal[v]
    return np.kron(o,np.ones((k,k,1),np.uint8))
b=V.decode(t["tQCFONT_2BITBROOK"]); l=V.decode(t["tQCFONT_4BITLUFFY"])
res=[(smooth(sheet(b,8,6,2,o)),o) for o in itertools.permutations(range(2))]; print("brook",[(round(a,3),o) for a,o in res])
res=[(smooth(sheet(l,11,7,4,o)),o) for o in itertools.permutations(range(4))]; res.sort(key=lambda x:-x[0]); print("luffy",[(round(a,3),o) for a,o in res[:6]],"worst",round(res[-1][0],3))
bi=[img(sheet(b,8,6,2,o),2,4) for o in ((0,1),(1,0))]
Image.fromarray(np.concatenate([bi[0],np.full((bi[0].shape[0],8,3),20,np.uint8),bi[1]],1)).save("tmp/scratch/brook_planes.png")
li=[img(sheet(l,11,7,4,res[i][1]),4,3) for i in range(3)]
Image.fromarray(np.concatenate([li[0],np.full((li[0].shape[0],8,3),20,np.uint8),li[1],np.full((li[0].shape[0],8,3),20,np.uint8),li[2]],1)).save("tmp/scratch/luffy_planes.png")
