import os,sys
os.environ["AWTO_SIM_CORE"]="fast"
sys.path.insert(0,"scripts")
import osd_render as R, pacman_sim as P
tag,out=sys.argv[1],sys.argv[2]
s=R.Session(R.ROOT/f"tmp/fw/AWT26110003-{tag}-be.bin",R.ROOT/f"tmp/fw/AWT26110003-{tag}-be.map","1080p60")
s.boot()
P.send(s,0xB4); s.bus.wait(3.0)
P.send(s,0xB5); s.bus.wait(3.0)
R.render_snap(s.snap(),"black",2).save(out)
