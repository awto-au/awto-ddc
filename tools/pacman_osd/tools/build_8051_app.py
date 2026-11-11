#!/usr/bin/env python3
"""Build a real 8051 diagnostic display-list player from the tested C trace.
This checks MOVC/MOVX execution and OSD writes, NOT SDCC code generation or game
logic on the 8051. The portable C renderer is tested separately on the host.
No compiler/assembler dependency: all emitted instructions are listed below.
"""
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

class Code:
    def __init__(self):self.b=bytearray();self.labels={};self.fix=[];self.listing=[]
    def label(self,n):self.labels[n]=len(self.b);self.listing.append(f'{n}:')
    def ins(self,text,*bs):self.listing.append('    '+text);self.b.extend(bs)
    def target(self,text,opcode,label,relative=False,*args):
        self.listing.append('    '+text);self.b.append(opcode);self.b.extend(args)
        self.fix.append((len(self.b),label,relative));self.b.extend(bytes(1 if relative else 2))
    def finish(self):
        for at,label,rel in self.fix:
            n=self.labels[label]
            if rel:
                delta=n-at-1
                if not -128<=delta<=127:raise ValueError('relative branch overflow')
                self.b[at]=delta&255
            else:self.b[at:at+2]=n.to_bytes(2,'big')
        return self.b

def program():
    c=Code();c.target('LJMP start',0x02,'start')
    c.b.extend(bytes(0x30-len(c.b)));c.listing.append('    ORG 0030h')
    c.label('start');c.ins('MOV SP,#60h',0x75,0x81,0x60)
    c.ins('MOV R6,#02h',0x7E,2);c.ins('MOV R7,#00h',0x7F,0)
    c.label('next');c.target('LCALL getbyte',0x12,'getbyte')
    for n,lab,fun in ((1,'check_frame','block'),(2,'check_reg','frame'),(3,'halt','reg')):
        c.target(f'CJNE A,#{n},{lab}',0xB4,lab,True,n)
        c.target(f'LCALL {fun}',0x12,fun);c.target('LJMP next',0x02,'next');c.label(lab)
    c.ins('MOV DPTR,#0F002h',0x90,0xF0,2);c.ins('MOV A,#0FFh',0x74,255)
    c.ins('MOVX @DPTR,A',0xF0);c.label('idle');c.target('SJMP idle',0x80,'idle',True)
    c.label('getbyte');c.ins('MOV DPL,R7',0x8F,0x82);c.ins('MOV DPH,R6',0x8E,0x83)
    c.ins('CLR A',0xE4);c.ins('MOVC A,@A+DPTR',0x93);c.ins('INC DPTR',0xA3)
    c.ins('MOV R7,DPL',0xAF,0x82);c.ins('MOV R6,DPH',0xAE,0x83);c.ins('RET',0x22)
    c.label('block')
    for r in (4,5,2,3):c.target('LCALL getbyte',0x12,'getbyte');c.ins(f'MOV R{r},A',0xF8+r)
    c.ins('MOV DPTR,#0094h',0x90,0,0x94);c.ins('MOV A,#0E8h',0x74,0xE8);c.ins('MOVX @DPTR,A',0xF0)
    c.ins('MOV DPTR,#0090h',0x90,0,0x90);c.ins('MOV A,R4',0xEC);c.ins('MOVX @DPTR,A',0xF0)
    c.ins('INC DPTR',0xA3);c.ins('MOV A,R5',0xED);c.ins('MOVX @DPTR,A',0xF0)
    c.label('copy');c.target('LCALL getbyte',0x12,'getbyte');c.ins('MOV DPTR,#0092h',0x90,0,0x92)
    c.label('data_write');c.ins('MOVX @DPTR,A',0xF0)
    c.ins('MOV A,R3',0xEB);c.target('JNZ dec_low',0x70,'dec_low',True)
    c.ins('DEC R2',0x1A);c.label('dec_low');c.ins('DEC R3',0x1B)
    c.ins('MOV A,R2',0xEA);c.ins('ORL A,R3',0x4B);c.target('JNZ copy',0x70,'copy',True);c.ins('RET',0x22)
    c.label('frame')
    for addr in (0xF000,0xF001):
        c.target('LCALL getbyte',0x12,'getbyte');c.ins(f'MOV DPTR,#{addr:04X}h',0x90,addr>>8,addr&255);c.ins('MOVX @DPTR,A',0xF0)
    c.ins('RET',0x22);c.label('reg')
    for r in (4,5):c.target('LCALL getbyte',0x12,'getbyte');c.ins(f'MOV R{r},A',0xF8+r)
    c.target('LCALL getbyte',0x12,'getbyte');c.ins('MOV DPL,R5',0x8D,0x82);c.ins('MOV DPH,R4',0x8C,0x83)
    c.ins('MOVX @DPTR,A',0xF0);c.ins('RET',0x22)
    b=c.finish()
    if len(b)>512:raise ValueError('code overlaps stream')
    b.extend(bytes(512-len(b)))
    return b,c

def stream():
    m=json.loads((ROOT/'generated/manifest.json').read_text())
    fs,fb=m['fs_base'],m['font_base'];out=bytearray()
    regs=[(0x94,0),(0x3A02,0),(0x3A17,0),(0x3A0B,0),(0x3A18,0),(0x3A41,0),(0x3A43,0),
          (0x3A33,0),(0x3A0C,fs&255),(0x3A0D,(fs>>8)<<4|fb&15),(0x3A0E,fb>>4),
          (0x3A19,0),(0x3A0A,0),(0x3AC0,128),(0x6C,1)]
    for i,rgb in enumerate(m['palette']):regs.extend([(0x6E,128|i)]+[(0x6F,v)for v in rgb])
    regs.append((0x3A02,1))
    for a,v in regs:out.extend([3,a>>8,a&255,v])
    lines=(ROOT/'build/trace.txt').read_text().splitlines();i=0;pending=[]
    def flush():
        if not pending:return
        a=pending[0][0];data=bytes(v for _,triple in pending for v in triple)
        out.extend([1,a>>8,a&255,len(data)>>8,len(data)&255]);out.extend(data);pending.clear()
    while i<len(lines):
        if lines[i].startswith('F '):
            flush();frame=int(lines[i][2:])&65535;out.extend([2,frame>>8,frame&255]);i+=1;continue
        chunk=[list(map(int,l.split()[1:]))for l in lines[i:i+6]]
        if len(chunk)!=6 or [a for a,v in chunk]!=[0x94,0x90,0x91,0x92,0x92,0x92] or chunk[0][1]!=0xE8:
            raise ValueError('unexpected C port-write sequence')
        a=chunk[1][1]*256+chunk[2][1];triple=[v for _,v in chunk[3:]]
        if pending and a!=pending[-1][0]+1:flush()
        pending.append((a,triple));i+=6
    flush();out.append(255);return out

def main():
    b,c=program();b.extend(stream())
    if len(b)>65536:raise ValueError('diagnostic app exceeds one 8051 code bank')
    (ROOT/'build/patch-app.bin').write_bytes(b)
    (ROOT/'build/patch-app.asm').write_text('; Diagnostic stream player. Standalone emulator app, not a monitor flash image.\n'+'\n'.join(c.listing)+'\n; Packed stream begins at ORG 0200h; build_8051_app.py emits its bytes.\n')
    records=[]
    for a in range(0,len(b),16):
        rec=bytes([len(b[a:a+16]),a>>8,a&255,0])+b[a:a+16]
        records.append(':'+rec.hex().upper()+f'{-sum(rec)&255:02X}')
    (ROOT/'build/patch-app.ihx').write_text('\n'.join(records+[':00000001FF'])+'\n')
    (ROOT/'build/app-build.json').write_text(json.dumps({'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),
        'labels':c.labels,'status':'8051 display-list diagnostic, NOT an SDCC build of the C renderer'},indent=2)+'\n')
    print(f'Built {len(b)}-byte 8051 diagnostic app')

if __name__=='__main__':main()
