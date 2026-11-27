import re,sys
sys.path.insert(0,'scripts'); sys.path.insert(0,'/mnt/2tb/git/awto-rtdfw-ui/tools')
import glyph_decode as GD, osd_vlc
t=open('/mnt/2tb/git/awto-rtdfw-ui/awto/osd/font_data.inc').read()
m=re.search(r'font_blob_spleen\[\d+\] = \{(.*?)\};',t,re.S)
b=bytes(int(x,16) for x in re.findall(r'0x(..)',m.group(1)))
print(len(b))
# split chunks: 8 map + 2 len + n
o=0;i=0
while o<len(b):
    n=b[o+8]<<8|b[o+9]; blob=b[o:o+10+n]
    ref=osd_vlc.decode(blob)
    try:
        _,_,tiles=GD.decode_blob(blob,0)
        print('chunk',i,'len',n,'host',len(ref),'GD',len(tiles),'equal',bytes(tiles)==ref if not hasattr(tiles,'tobytes') else tiles.tobytes()==ref)
    except Exception as e: print('chunk',i,'GD err',e, type(tiles) if 'tiles' in dir() else '')
    o+=10+n;i+=1
