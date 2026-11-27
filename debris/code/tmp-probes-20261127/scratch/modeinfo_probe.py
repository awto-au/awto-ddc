import sys
sys.path.insert(0, "scripts")
import fw_sim as S
b, mp = sys.argv[1], sys.argv[2]
bus = S.SimBus(b, mp, video="1080p60", port="D2", boot=False)
m = bus.m
a = bus.addr("isr_g_stModeInfo")
last, t0 = None, None
while bus.now() < 1.2:
    cur = bytes(m.rd(a, 3))
    if cur != last:
        print(f"{bus.now() * 1000:7.0f} ms  {cur.hex(' ')}  state {cur[0] & 0x1F}  b0 {cur[0]:08b} b1 {cur[1]:08b}")
        last = cur
    bus.wait(0.002)
