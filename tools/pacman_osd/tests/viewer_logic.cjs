// JS logic test without a browser: execute our inline viewer with a minimal
// DOM/canvas test double. This does not test browser layout or interactions.
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const html=fs.readFileSync('preview/pacman-osd-viewer.html','utf8');
const code=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const el={},pixels=new Uint8Array(336*432*3);let timer;
const context={fillStyle:'#000',strokeStyle:'',lineWidth:0,beginPath(){},moveTo(){},lineTo(){},stroke(){},
 fillRect(x,y,w,h){
  const rgb=this.fillStyle.startsWith('rgb(')?this.fillStyle.slice(4,-1).split(',').map(Number):[0,0,0];
  if(el.screen.width!==336||el.screen.height!==432)return;
  for(let yy=y;yy<y+h;yy++)for(let xx=x;xx<x+w;xx++)for(let k=0;k<3;k++)pixels[(yy*336+xx)*3+k]=rgb[k];
 }};
function node(id){return el[id]??=(id==='screen'?{width:336,height:432,getContext:()=>context}:{checked:false,value:id==='speed'?'50':'0',textContent:'',click(){this.onclick();}});}
const world={document:{getElementById:node,addEventListener(){}},window:{},
 atob:s=>Buffer.from(s,'base64').toString('binary'),setInterval:f=>(timer=f,1),clearInterval:()=>{timer=null;},console};
vm.createContext(world);vm.runInContext(code,world);
const lab=world.window.osdLab;
assert.equal(lab.getFrame(),0);node('next').click();assert.equal(lab.getFrame(),1);
node('prev').click();assert.equal(lab.getFrame(),0);
node('play').click();timer();assert.equal(lab.getFrame(),1);node('play').click();assert.equal(timer,null);
lab.seek(24);assert.equal(lab.getFrame(),24);assert.equal(lab.getCells().length,1008);
fs.writeFileSync('build/html-pixels.rgb',pixels);
console.log('HTML JS logic passed: initialisation, stepping, playback callback, seek, pixel buffer');
