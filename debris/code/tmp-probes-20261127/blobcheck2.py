import re,sys
sys.path.insert(0,'scripts'); sys.path.insert(0,'/mnt/2tb/git/awto-rtdfw-ui/tools')
import glyph_decode as GD, osd_vlc
t=open('/mnt/2tb/git/awto-rtdfw-ui/awto/osd/font_data.inc').read()
for name in ('spleen','tamzen','spleen6','spleen5','tamzen5','tamzen6','tamzen7'):
    m=re.search(r'font_blob_%s\[\d+\] = \{(.*?)\};'%name,t,re.S)
    b=bytes(int(x,16) for x in re.findall(r'0x(..)',m.group(1)))
    o=0;i=0
    while o<len(b):
        n=b[o+8]<<8|b[o+9]; blob=b[o:o+10+n]
        ref=osd_vlc.decode(blob)
        try:
            _,_,tiles=GD.decode_blob(blob,0)
            tb=tiles.tobytes() if hasattr(tiles,'tobytes') else bytes(tiles)
            print(name,'chunk',i,'stream',n,'B -> host',len(ref),'GD',len(tb),'equal',tb==ref)
        except Exception as e: print(name,'chunk',i,'GD error',e)
        o+=10+n;i+=1
