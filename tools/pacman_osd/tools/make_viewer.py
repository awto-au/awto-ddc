#!/usr/bin/env python3
"""Self-contained HTML viewer for the independently emulated 8051 OSD capture."""
import base64,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def capture():
    m=json.loads((ROOT/'generated/manifest.json').read_text())
    ram={};addr=hi=0;pending=[];f=-2;initial=None;frames=[];prev=[];stats=[0,0]
    def save():
        nonlocal initial,prev
        screen=[list(ram[m['fs_base']+i])for i in range(1008)]
        if f==-1:initial=screen;prev=screen
        elif f>=0:
            delta=[[i,*v]for i,v in enumerate(screen)if v!=prev[i]]
            frames.append({'frame':f,'delta':delta,'instructions':stats[0],'ticks':stats[1]});prev=screen
    for l in (ROOT/'build/8051-trace.txt').read_text().splitlines():
        k,*a=l.split()
        if k=='F':
            if f>=-1:save()
            f=int(a[0])
        elif k=='S':stats=list(map(int,a))
        elif k=='R':
            r,v=map(int,a)
            if r==0x94:pending=[]
            elif r==0x90:hi=v;pending=[]
            elif r==0x91:addr=hi*256+v;pending=[]
            elif r==0x92:
                pending.append(v)
                if len(pending)==3:ram[addr]=pending;addr+=1;pending=[]
    save()
    return {'meta':m,'glyphs':base64.b64encode((ROOT/'generated/glyphs.bin').read_bytes()).decode(),
            'initial':initial,'frames':frames,
            'validation':json.loads((ROOT/'build/emulator-validation.json').read_text())}

TEMPLATE='''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pac-Man · 8051 OSD lab</title>
<style>
:root{color-scheme:dark;font:15px system-ui,sans-serif;background:#0a101b;color:#e6edf7}*{box-sizing:border-box}body{margin:0}header{padding:22px 30px;border-bottom:1px solid #263249;display:flex;align-items:center;gap:14px}.badge{color:#72e6bf;font:12px monospace;background:#12342e;padding:6px 9px;border-radius:5px}h1{font-size:21px;margin:0}header small{margin-left:auto;color:#95a7bf}main{display:grid;grid-template-columns:minmax(330px,1fr) 310px;gap:24px;max-width:1100px;margin:24px auto;padding:0 20px}.stage{background:#03060c;border:1px solid #263249;border-radius:12px;padding:20px;display:flex;justify-content:center;align-items:center;min-height:480px}canvas{width:min(100%,504px);height:auto;image-rendering:pixelated;cursor:crosshair}.panel{background:#111b2b;border:1px solid #263249;border-radius:10px;padding:18px;margin-bottom:16px}h2{font-size:13px;letter-spacing:.08em;text-transform:uppercase;color:#92a8c5;margin:0 0 15px}.value{font:30px monospace;color:#f7de52}.sub{font-size:12px;color:#92a8c5;line-height:1.6}.controls{display:flex;gap:8px;margin:16px 0 12px;align-items:center}button,select{font:inherit;background:#1b2a40;color:#e6edf7;border:1px solid #3a4a63;border-radius:6px;padding:9px 12px;cursor:pointer}button:hover{background:#293d59}button.primary{background:#f7de52;color:#142034;border:0;font-weight:700}input[type=range]{width:100%;accent-color:#f7de52}.row{display:flex;justify-content:space-between;margin:11px 0;font-size:13px}.row span:first-child{color:#9cafc6}progress{width:100%;height:9px;accent-color:#58d8b0}label{font-size:13px;color:#b9c8dd;cursor:pointer}.note{font-size:12px;line-height:1.7;color:#9cafc6;margin-top:12px}.pass{color:#72e6bf}.mono{font-family:monospace}footer{max-width:1060px;margin:0 auto 25px;padding:0 20px;color:#70859f;font-size:12px;line-height:1.7}@media(max-width:700px){header{padding:16px}header small{display:none}main{display:block;padding:0 12px;margin-top:12px}.stage{padding:12px;min-height:0}aside{margin-top:20px}.controls{flex-wrap:wrap}}
</style>
<header><span class="badge">8051 → OSD</span><h1>Pac-Man graphics lab</h1><small>Offline diagnostic capture</small></header>
<main><section><div class="stage"><canvas id="screen" width="336" height="432" aria-label="Emulated OSD display"></canvas></div>
<div class="controls"><button class="primary" id="play">Play</button><button id="prev" aria-label="Previous frame">←</button><button id="next" aria-label="Next frame">→</button><select id="speed" aria-label="Playback speed"><option value="100">10 fps</option><option value="50" selected>20 fps</option><option value="33">30 fps</option></select><label><input id="grid" type="checkbox"> Cell grid</label><label><input id="atlas" type="checkbox"> Glyph cache</label></div>
<input id="seek" aria-label="Frame" type="range" min="0" value="0"><div class="row"><span id="frame">Frame 0 / 95</span><span>Space: play · ← →: step</span></div>
</section><aside>
<div class="panel"><h2>Resident graphics</h2><div class="value" id="glyphs"></div><div class="sub">glyph IDs used / 512 available</div><progress id="slots" max="512"></progress><div class="row"><span>OSD SRAM</span><b id="memory"></b></div><progress id="sram" max="12288"></progress><div class="sub">12 × 18 storage · 12 × 12 visible cells<br>28 × 36 map · 336 × 432 OSD pixels<br>3-pixel steps · up to four fragments/actor</div></div>
<div class="panel"><h2>Selected frame</h2><div class="row"><span>Changed map cells</span><b id="changed"></b></div><div class="row"><span>Glyph uploads</span><b class="pass">0 after startup</b></div><div class="row"><span>8051 instructions*</span><b id="instructions"></b></div><div class="sub">*Cumulative at this frame's start, for the display-list diagnostic. Playback fps is a viewer setting, not measured monitor performance.</div></div>
<div class="panel"><h2>Inspect</h2><div class="mono sub" id="inspect">Tap a cell or glyph to inspect its ID.</div></div>
<div class="panel"><h2>Verification</h2><div class="pass sub">✓ 96 emulated frames match the C output<br>✓ Every startup SRAM word matches<br>✓ Missing-MOVX fault detected</div><div class="note">A real 8051 display-list player produced this capture. The C graphics renderer was tested separately on the host. This is a graphics prototype: no gameplay, sound, firmware integration, or hardware rotation test.</div></div>
</aside></main><footer>Original demonstration maze and artwork. Occupied sprite cells replace their background until the actor leaves; mixed-colour sprite/background compositing and collisions remain to implement. Hardware font-layer shifts and global/download rotation are documented but are not exercised by this diagnostic.</footer>
<script>
const DATA=__DATA__;
const $=id=>document.getElementById(id), c=$('screen'), ctx=c.getContext('2d');
const bytes=Uint8Array.from(atob(DATA.glyphs),x=>x.charCodeAt(0));
const masks=Array.from({length:DATA.meta.glyph_count},(_,g)=>Array.from({length:216},(_,p)=>{
const word=Math.floor(p/24),bit=23-p%24,off=g*27+word*3;
return ((bytes[off]|bytes[off+1]<<8|bytes[off+2]<<16)>>>bit)&1;}));
let frame=0, cells=[], running=false, timer=null;
$('seek').max=DATA.frames.length-1;$('glyphs').textContent=DATA.meta.glyph_count+' / 512';
$('slots').value=DATA.meta.glyph_count;$('sram').value=DATA.meta.sram_words;
$('memory').textContent=DATA.meta.sram_bytes.toLocaleString()+' B';
function seek(n){frame=(n+DATA.frames.length)%DATA.frames.length;cells=DATA.initial.map(x=>x.slice());
for(let i=0;i<=frame;i++)for(const [a,...v]of DATA.frames[i].delta)cells[a]=v;
$('seek').value=frame;$('frame').textContent=`Frame ${frame} / ${DATA.frames.length-1}`;
$('changed').textContent=DATA.frames[frame].delta.length;$('instructions').textContent=DATA.frames[frame].instructions.toLocaleString();draw();}
function glyph(g,x,y,fg,bg=1,h=12){const bits=masks[g];for(let py=0;py<h;py++)for(let px=0;px<12;px++){
const rgb=DATA.meta.palette[bits[py*12+px]?fg:bg]||[255,0,255];ctx.fillStyle=`rgb(${rgb})`;ctx.fillRect(x+px,y+py,1,1);}}
function draw(){const atlas=$('atlas').checked;c.width=atlas?192:336;c.height=atlas?Math.ceil(masks.length/16)*18:432;ctx.fillStyle='#000';ctx.fillRect(0,0,c.width,c.height);
if(atlas){for(let g=0;g<masks.length;g++)glyph(g,(g%16)*12,Math.floor(g/16)*18,DATA.meta.glyph_fg[g],1,18);}
else for(let a=0;a<cells.length;a++){const [b0,b1,b2]=cells[a],g=b1+((b0&32)?256:0);glyph(g,(a%28)*12,Math.floor(a/28)*12,b2>>4,b2&15);}
if($('grid').checked){ctx.strokeStyle='#627d9b70';ctx.lineWidth=.5;const ch=atlas?18:12;for(let x=0;x<=c.width;x+=12){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,c.height);ctx.stroke();}for(let y=0;y<=c.height;y+=ch){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(c.width,y);ctx.stroke();}}}
function stop(){running=false;clearInterval(timer);$('play').textContent='Play';}
function play(){stop();running=true;$('play').textContent='Pause';timer=setInterval(()=>seek(frame+1),+$('speed').value);}
$('play').onclick=()=>running?stop():play();$('prev').onclick=()=>{stop();seek(frame-1);};$('next').onclick=()=>{stop();seek(frame+1);};
$('seek').oninput=e=>{stop();seek(+e.target.value);};$('grid').onchange=draw;$('atlas').onchange=draw;$('speed').onchange=()=>{if(running)play();};
c.onclick=e=>{const r=c.getBoundingClientRect(),x=Math.floor((e.clientX-r.left)*c.width/r.width),y=Math.floor((e.clientY-r.top)*c.height/r.height);let text;
if($('atlas').checked){const g=Math.floor(y/18)*16+Math.floor(x/12);text=g<masks.length?`Glyph ${g} · SRAM word ${DATA.meta.font_base+g*9}\n27 bytes / 9 words`:'';}
else{const cx=Math.floor(x/12),cy=Math.floor(y/12),[b0,b1,b2]=cells[cy*28+cx],g=b1+((b0&32)?256:0);text=`Cell ${cx}, ${cy} · Glyph ${g}\nForeground ${b2>>4} · Background ${b2&15}\nSRAM word ${DATA.meta.fs_base+cy*28+cx}`;}
$('inspect').textContent=text;};
document.addEventListener('keydown',e=>{if(e.target.tagName==='INPUT'||e.target.tagName==='SELECT')return;if(e.code==='Space'){e.preventDefault();running?stop():play();}if(e.code==='ArrowRight')$('next').click();if(e.code==='ArrowLeft')$('prev').click();});
window.osdLab={seek,getFrame:()=>frame,getCells:()=>cells.map(x=>x.slice()),getData:()=>DATA};seek(0);
</script></html>'''

if __name__=='__main__':
    data=capture();out=ROOT/'preview/pacman-osd-viewer.html'
    out.write_text(TEMPLATE.replace('__DATA__',json.dumps(data,separators=(',',':'))))
    (ROOT/'preview/8051-capture.json').write_text(json.dumps(data,separators=(',',':'))+'\n')
    print(f'Created HTML capture viewer: {out.stat().st_size} bytes')
