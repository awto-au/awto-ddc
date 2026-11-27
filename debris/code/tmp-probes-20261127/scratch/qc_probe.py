import re,sys
sys.path.insert(0,"scripts")
import osd_vlc as V
src=open("/mnt/2tb/git_mirror/Kingdomwhisky/RTD-Scaler-TEST/Kernel/Scaler/RL6449_Series_Scaler/Code/RL6449_Series_QC_OSD.c",errors="replace").read()
tabs={}
for m in re.finditer(r"BYTE code (\w+)\[\]\s*=\s*\{(.*?)\};",src,re.S):
    body=m.group(2)
    if "ICON_" in body or "_NEXT_" in body or "_CLEAR" in body: continue
    nums=re.findall(r"0x[0-9a-fA-F]+",body)
    tabs[m.group(1)]=bytes(int(x,16) for x in nums)
for n in ("tQCDRAW_MAP","tQCFONT_GLOBAL","tQCFONT_2BITBROOK","tQCFONT_4BITLUFFY","tQCFONT_24_36_1BIT","tQCFONT_24_36_2BIT","tQCFONT_24_36_4BIT"):
    b=tabs[n]; off=0; k=0
    print(n,len(b),"bytes")
    while off<len(b)-10:
        N=int.from_bytes(b[off+8:off+10],"big")
        try:
            d=V.decode(b,off); print(f"   blob {k} at {off}: N={N} -> {len(d)} bytes ({len(d)/27:.1f} x27, {len(d)/54:.1f} x54, {len(d)/108:.1f} x108)")
        except Exception as e:
            print(f"   blob {k} at {off}: N={N} FAIL {e}"); break
        off+=10+N; k+=1
