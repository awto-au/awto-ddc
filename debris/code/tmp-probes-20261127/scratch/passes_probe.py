import sys
sys.path.insert(0, "scripts")
import fw_sim as S
bus = S.SimBus(sys.argv[1], sys.argv[2], video="1080p60", port="D2", boot=False)
m, base = bus.m, 0xF6D0
last, tl, out = None, 0.0, []
while bus.now() < 0.8:
    hb = int.from_bytes(bytes(m.rd(base + 0x14, 2)), "big")
    t = bus.now() * 1000
    if hb != last:
        if last is not None and t - tl > 8:
            out.append(f"pass ending at {t:6.0f} ms took {t - tl:5.0f} ms (heartbeat {last}->{hb})")
        last, tl = hb, t
    m.run(2000)
print("\n".join(out) if out else "no pass longer than 8 ms")
