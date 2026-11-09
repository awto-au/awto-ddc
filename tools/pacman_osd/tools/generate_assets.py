#!/usr/bin/env python3
"""Original 12x18 one-bit OSD assets; no arcade ROMs or third-party artwork.
Python standard library only. Output layout follows awto-ddc's current OSD model.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path

W, H, COLS, ROWS = 12, 18, 28, 36
CW, CH, STEP = 12, 12, 3  # visible cell, stored glyph remains 12x18
PALETTE = [(0, 0, 0), (0, 0, 0), (30, 65, 235), (255, 225, 20),
           (255, 255, 255), (245, 45, 45), (255, 145, 200),
           (40, 230, 245), (255, 160, 30), (60, 75, 255)]
FONT = {
    '0':'01110/10001/10011/10101/11001/10001/01110',
    '1':'00100/01100/00100/00100/00100/00100/01110',
    '2':'01110/10001/00001/00010/00100/01000/11111',
    '3':'11110/00001/00001/01110/00001/00001/11110',
    '4':'00010/00110/01010/10010/11111/00010/00010',
    '5':'11111/10000/10000/11110/00001/00001/11110',
    '6':'01110/10000/10000/11110/10001/10001/01110',
    '7':'11111/00001/00010/00100/01000/01000/01000',
    '8':'01110/10001/10001/01110/10001/10001/01110',
    '9':'01110/10001/10001/01111/00001/00001/01110',
    'A':'01110/10001/10001/11111/10001/10001/10001',
    'C':'01111/10000/10000/10000/10000/10000/01111',
    'D':'11110/10001/10001/10001/10001/10001/11110',
    'E':'11111/10000/10000/11110/10000/10000/11111',
    'M':'10001/11011/10101/10101/10001/10001/10001',
    'N':'10001/11001/10101/10011/10001/10001/10001',
    'O':'01110/10001/10001/10001/10001/10001/01110',
    'P':'11110/10001/10001/11110/10000/10000/10000',
    'R':'11110/10001/10001/11110/10100/10010/10001',
    'S':'01111/10000/10000/01110/00001/00001/11110',
    'T':'11111/00100/00100/00100/00100/00100/00100',
    'U':'10001/10001/10001/10001/10001/10001/01110',
    'V':'10001/10001/10001/10001/10001/01010/00100',
    'Y':'10001/10001/01010/00100/00100/00100/00100',
}

def pack(tile):
    """Two 12-bit rows per 24-bit word; word bytes LOW, MIDDLE, HIGH."""
    if len(tile) != H or any(len(r) != W for r in tile):
        raise ValueError('expected 12x18 tile')
    out = bytearray()
    for y in range(0, H, 2):
        n = 0
        for row in tile[y:y+2]:
            for b in row:
                if b not in (0, 1): raise ValueError('not monochrome')
                n = n * 2 + b
        out.extend(n.to_bytes(3, 'little'))
    return bytes(out)

def unpack(data):
    if len(data) != 27: raise ValueError('expected 27 bytes')
    bits = ''.join(f'{int.from_bytes(data[i:i+3], "little"):024b}' for i in range(0, 27, 3))
    return [[int(c) for c in bits[y*W:(y+1)*W]] for y in range(H)]

def picture(fn): return [[int(bool(fn(x, y))) for x in range(W)] for y in range(H)]

def make_assets():
    tiles, names, colors, ids = [], [], [], {}
    def add(name, tile, fg):
        if name in ids: raise ValueError('duplicate name')
        ids[name] = len(tiles); names.append(name); tiles.append(tile); colors.append(fg)
        return ids[name]
    add('BLANK', picture(lambda x,y: False), 4)
    add('DOT', picture(lambda x,y: x in (5,6) and y in (5,6)), 4)
    add('POWER', picture(lambda x,y: ((x-5.5)/3)**2 + ((y-5.5)/3)**2 <= 1), 4)
    # Solid maze regions represented by their boundary; each adjacency mask has
    # a precomputed outline. Bits: left=1, right=2, up=4, down=8.
    for mask in range(16):
        add(f'WALL_{mask}', picture(lambda x,y,m=mask:
            y<CH and ((not m&1 and x in (0,1)) or (not m&2 and x in (10,11)) or
            (not m&4 and y in (0,1)) or (not m&8 and y in (10,11)))), 2)
    for d, angle in enumerate((0, math.pi/2, math.pi, -math.pi/2)):
        for f, opening in enumerate((0, .20, .45, .70, .90)):
            def pac(x,y,a=angle,o=opening):
                dx,dy=(x-5.5)/5.4,(y-5.5)/5.4
                delta=(math.atan2(dy,dx)-a+math.pi)%(2*math.pi)-math.pi
                return dx*dx+dy*dy<=1 and (o==0 or abs(delta)>o)
            add(f'PAC_{d}_{f}', picture(pac), 3)
    for d in range(4):
        for f in range(2):
            def ghost(x,y,d=d,f=f):
                body = (3<=y<=10 and 1<=x<=10) or (((x-5.5)/4.6)**2+((y-4)/3)**2<=1 and y<=4)
                if y>=9 and ((x+f*2)//2)%2: body=False
                ex,ey=((1,0),(0,1),(-1,0),(0,-1))[d]
                if 4+ey<=y<=5+ey and (3+ex<=x<=4+ex or 7+ex<=x<=8+ex): body=False
                return body
            add(f'GHOST_{d}_{f}', picture(ghost), 5)
    for f in range(12):
        # Precomputed death animation, included even though the graphics demo
        # does not run game rules or trigger a death sequence.
        add(f'DEATH_{f}', picture(lambda x,y,f=f:
            ((x-5.5)/5.4)**2+((y-5.5)/5.4)**2<=1 and
            abs(math.atan2((y-5.5)/5.4,(x-5.5)/5.4))>f*math.pi/11), 3)
    for c, rows in FONT.items():
        rows=rows.split('/')
        add(f'TEXT_{c}', picture(lambda x,y,r=rows: 3<=x<8 and 2<=y<9 and r[y-2][x-3]=='1'), 4)
    if len(tiles)>256: raise ValueError('background map stores eight-bit asset IDs')
    # Original demonstration maze, not an extracted arcade map.
    wall=[[False]*COLS for _ in range(ROWS)]
    for y in range(3,35):
        for x in range(COLS): wall[y][x]=x in (0,27) or y in (3,34)
    for x0,y0,x1,y1 in ((3,6,7,9),(10,6,12,9),(3,12,7,15),
                         (10,12,12,18),(3,18,7,21),(3,24,7,27),
                         (10,21,12,24),(10,27,12,30),(3,30,7,31)):
        for y in range(y0,y1+1):
            for x in range(x0,x1+1): wall[y][x]=wall[y][27-x]=True
    grid=[]
    for y in range(ROWS):
        for x in range(COLS):
            if wall[y][x]:
                mask=sum(bit for dx,dy,bit in ((-1,0,1),(1,0,2),(0,-1,4),(0,1,8))
                         if 0<=x+dx<COLS and 0<=y+dy<ROWS and wall[y+dy][x+dx])
                grid.append(ids[f'WALL_{mask}'])
            else: grid.append(ids['DOT'] if 3<y<34 else ids['BLANK'])
    for x,y in ((1,4),(26,4),(1,33),(26,33)): grid[y*COLS+x]=ids['POWER']
    for text,x0,y in (('PACMAN OSD',2,0),('SCORE 000000',2,1),('DEMO',22,1)):
        for i,c in enumerate(text): grid[y*COLS+x0+i]=ids['BLANK'] if c==' ' else ids[f'TEXT_{c}']
    return tiles,names,colors,ids,grid

def c_array(name, data):
    body='\n'.join('    '+', '.join(f'0x{n:02X}' for n in data[i:i+16])+',' for i in range(0,len(data),16))
    return f'const PM_CODE uint8_t {name}[{len(data)}] = {{\n{body}\n}};\n'

def build(out):
    tiles,names,fg,ids,grid=make_assets()
    base_count=len(tiles)
    # Cache every 3-pixel phase for two mouth frames in four directions and
    # one ghost pose in four directions. A single shared ghost atlas is tinted
    # per cell for all four ghosts. Deduplicate complete 27-byte fragments.
    phase_frames=[f'PAC_{d}_{f}' for d in range(4) for f in (0,3)]
    phase_frames += [f'GHOST_{d}_0' for d in range(4)]
    packed_ids={}
    for i,t in enumerate(tiles): packed_ids.setdefault(pack(t),i)
    phase=[]
    for name in phase_frames:
        sprite=tiles[ids[name]]
        for dy in range(0,CH,STEP):
            for dx in range(0,CW,STEP):
                for cy in range(2):
                    for cx in range(2):
                        part=picture(lambda x,y,cx=cx,cy=cy,dx=dx,dy=dy:
                            sprite[y+cy*CH-dy][x+cx*CW-dx]
                            if y<CH and 0<=y+cy*CH-dy<CH and 0<=x+cx*CW-dx<CW else 0)
                        key=pack(part)
                        if key not in packed_ids:
                            packed_ids[key]=len(tiles)
                            tiles.append(part); names.append(f'FRAGMENT_{len(tiles)-1}'); fg.append(4)
                        phase.append(packed_ids[key])
    if len(tiles)>512: raise ValueError('preloaded phase atlas exceeds 512 one-bit glyph IDs')
    raw=b''.join(pack(t) for t in tiles)
    words=ROWS+1+COLS*ROWS+9*len(tiles)
    if words>12288: raise ValueError('OSD SRAM overflow')
    out.mkdir(parents=True,exist_ok=True)
    hdr='#ifndef PM_ASSETS_H\n#define PM_ASSETS_H\n#include "pm_osd.h"\n'
    hdr+=f'#define PM_GLYPHS {len(tiles)}\n#define PM_SRAM_WORDS {words}\n'
    hdr+=f'#define PM_BASE_GLYPHS {base_count}\n#define PM_PHASE_FRAMES {len(phase_frames)}\n#define PM_PHASES 16\n'
    hdr+=''.join(f'#define PM_G_{n} {i}\n' for i,n in enumerate(names))
    hdr+=f'extern const PM_CODE uint8_t pm_glyph_bytes[{len(raw)}];\n'
    hdr+=f'extern const PM_CODE uint8_t pm_asset_fg[{len(fg)}];\n'
    hdr+='extern const PM_CODE uint8_t pm_initial_map[PM_CELLS];\n#endif\n'
    hdr=hdr.replace('#endif\n',f'extern const PM_CODE uint16_t pm_phase_glyph[{len(phase)}];\n#endif\n')
    (out/'pm_assets.h').write_text(hdr)
    phase_c='const PM_CODE uint16_t pm_phase_glyph['+str(len(phase))+'] = {\n'
    phase_c+='\n'.join('    '+', '.join(str(n) for n in phase[i:i+16])+',' for i in range(0,len(phase),16))+'\n};\n'
    (out/'pm_assets.c').write_text('#include "pm_assets.h"\n'+c_array('pm_glyph_bytes',raw)+c_array('pm_asset_fg',fg)+c_array('pm_initial_map',grid)+phase_c)
    (out/'glyphs.bin').write_bytes(raw)
    manifest={'format':'RTD2795T 12x18 1bpp, 24-bit words little-endian',
              'cols':COLS,'rows':ROWS,'glyph_count':len(tiles),'glyph_ids':ids,
              'glyph_fg':fg,'palette':PALETTE,'initial_map':grid,
              'base_glyph_count':base_count,'cell_width':CW,'cell_height':CH,
              'phase_step_px':STEP,'phase_frames':phase_frames,
              'phase_glyphs':phase,'phase_order':'frame, yphase(0..3), xphase(0..3), quadrant(TL,TR,BL,BR)',
              'fs_base':ROWS+1,'font_base':ROWS+1+COLS*ROWS,
              'sram_words':words,'sram_bytes':words*3,'sram_capacity_words':12288,
              'glyph_sha256':hashlib.sha256(raw).hexdigest(),
              'status':'offline graphics preparation; cached three-pixel movement; not a complete game'}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(f'{len(tiles)} glyphs; {words}/12288 SRAM words ({words*3} bytes)')
    return manifest

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=Path(__file__).resolve().parents[1]/'generated')
    build(parser.parse_args().out)
