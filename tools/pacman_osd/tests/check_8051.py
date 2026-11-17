#!/usr/bin/env python3
"""Compare every 8051-emitted OSD SRAM word with the native C renderer.
Negative control removes the MOVX data write; this MUST fail the comparison.
"""
import json
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def words(path):
    frames={};frame=-2;addr=0;hi=0;wopt=0;pending=[]
    for line in path.read_text().splitlines():
        kind,*args=line.split()
        if kind=='F':
            assert not pending,'partial OSD word at frame boundary'
            frame=int(args[0]);frames[frame]=[]
        elif kind=='R':
            r,v=map(int,args)
            if r==0x94:wopt=v;pending=[]
            elif r==0x90:hi=v;pending=[]
            elif r==0x91:addr=hi*256+v;pending=[]
            elif r==0x92:
                assert wopt==0xE8,'unexpected SRAM plane selection'
                pending.append(v)
                if len(pending)==3:
                    assert 0<=addr<12288
                    frames.setdefault(frame,[]).append((addr,*pending));pending=[];addr+=1
    assert not pending,'truncated word'
    return frames

def main():
    native=words(ROOT/'build/trace.txt');actual=words(ROOT/'build/8051-trace.txt')
    assert native==actual,'8051 OSD words differ from native C'
    meta=json.loads((ROOT/'build/app-build.json').read_text())
    data=bytearray((ROOT/'build/patch-app.bin').read_bytes());at=meta['labels']['data_write']
    assert data[at]==0xF0;data[at]=0 # NOP replaces MOVX @DPTR,A
    bad=ROOT/'build/negative-app.bin';bad.write_bytes(data)
    subprocess.run([str(ROOT/'build/emu-runner'),str(bad),str(ROOT/'build/negative-trace.txt')],check=True,capture_output=True)
    assert words(ROOT/'build/negative-trace.txt')!=native,'negative control was not detected'
    result={'frames':len(native)-1,'startup_words':len(native[-1]),'all_word_writes_match_native':True,
            'missing_MOVX_negative_control_detected':True,
            'limit':'8051 display-list player; portable C renderer has not been compiled with SDCC here'}
    (ROOT/'build/emulator-validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'8051 comparison passed: {len(native)-1} frames and startup, every SRAM word exact; negative control detected')

if __name__=='__main__':main()
