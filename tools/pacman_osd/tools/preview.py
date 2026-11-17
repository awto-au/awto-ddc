#!/usr/bin/env python3
"""Render actual native C register-write traces with a separately maintained
awto-ddc OSD model. Reference sources are NOT a firmware simulator.
Usage: preview.py --reference /path/to/awto-ddc/scripts
Requires Pillow, numpy. Does not connect to any device.
"""
import argparse
import importlib
import json
import sys
import types
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reference',type=Path,required=True)
    p.add_argument('--trace',type=Path,default=ROOT/'build/8051-trace.txt')
    args=p.parse_args()
    sys.path.insert(0,str(args.reference.resolve()))
    # osd_model only needs the Dev base type when replaying a register trace.
    # We do NOT run or pretend to simulate the 8051 firmware.
    stub=types.ModuleType('fw_sim');stub.Dev=object
    sys.modules['fw_sim']=stub
    model=importlib.import_module('osd_model')
    m=json.loads((ROOT/'generated/manifest.json').read_text())
    raw=(ROOT/'generated/glyphs.bin').read_bytes()
    model_codec=importlib.import_module('osd_vlc')
    sys.path.insert(0,str(ROOT/'tools'))
    import generate_assets as gen
    tiles,_,_,_,_=gen.make_assets()
    for tile in tiles:
        assert gen.pack(tile)==model_codec.pack_unit(tile,1)
    class Mem:
        def __init__(self):self.b=bytearray(65536)
        def rd(self,a,n=1):return bytes(self.b[a:a+n])
    mem=Mem(); dev=model.OsdModel()
    def wr(a,v):
        mem.b[a]=v
        if a in dev.writes:dev.on_write(mem,a)
    # Deterministic PREVIEW state, not an on-device takeover sequence.
    fs,fb=m['fs_base'],m['font_base']
    for a,v in ((0x3A02,1),(0x3A0C,fs&255),(0x3A0D,(fs>>8)<<4|fb&15),
                (0x3A0E,(fb>>4)&255),(0x3A19,0),(0x006C,1)):
        wr(a,v)
    for i,rgb in enumerate(m['palette']):
        wr(0x6E,128|i)
        for value in rgb:wr(0x6F,value)
    frames=[];counts=[];frame=-1;n=0
    def capture():
        if frame<0:return
        # The reference model knows register/word packing independently of
        # the C code. Crop to the visible 12x12-cell viewport.
        image=model.render(dev.snapshot(mem),W=336,H=432)
        pic=Image.fromarray(image).resize((672,864),Image.Resampling.NEAREST)
        canvas=Image.new('RGB',(712,922),'#111827');canvas.paste(pic,(20,38))
        ImageDraw.Draw(canvas).text((20,13),'PAC-MAN OSD GRAPHICS PROTOTYPE | 8051 DIAGNOSTIC',fill='#d1d5db')
        frames.append(canvas);counts.append(n//3)
    for line in args.trace.read_text().splitlines():
        kind,*rest=line.split()
        if kind=='S':continue
        if kind=='F':capture();frame=int(rest[0]);n=0
        else:
            a,v=map(int,rest)
            if frame>=0 and a==0x92 and dev.addr>=fb:raise AssertionError('runtime glyph upload')
            wr(a,v)
            if a==0x92:n+=1
    capture()
    out=ROOT/'preview';out.mkdir(exist_ok=True)
    frames[24].save(out/'pacman-osd-preview.png')
    frames[0].save(out/'pacman-osd-motion.gif',save_all=True,append_images=frames[1:],duration=50,loop=0)
    (out/'validation.json').write_text(json.dumps({'frames':len(frames),
        'max_map_words_per_frame':max(counts),'mean_map_words_per_frame':sum(counts)/len(counts),
        'glyph_writes_after_load':0,'reference':'awto-ddc ca6b4dc25de155506838e5e503afe387f074628e',
        'note':'OSD replay of a real 8051 display-list diagnostic; C renderer host-tested separately; no hardware validation'},indent=2)+'\n')
    print(f'Rendered {len(frames)} frames; max {max(counts)} changed cells/frame; no runtime glyph uploads')

if __name__=='__main__':main()
