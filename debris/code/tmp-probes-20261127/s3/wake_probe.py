import sys, runpy
sys.path.insert(0, "/mnt/2tb/git/awto-ddc/scripts")
import wake_sim as W
orig = W.Run.wake_case
def wc(self, name, inject, want, bound):
    if name.startswith("DPCD"):
        self.sleep()
        t_inj = self.t2()
        print("INJECT at", t_inj)
        inject()
        self.until_wake(200)
        self.watch(300)
        for e in self.ring_events()[-40:]:
            print("ev", hex(e[0]), hex(e[1]), (e[2] - t_inj) & 0xFFFF, hex(e[3]) if len(e) > 3 else "")
        for ln in self.lines()[-30:]:
            print("  ", ln)
        raise SystemExit(0)
    return orig(self, name, inject, want, bound)
W.Run.wake_case = wc
sys.argv = ["wake_sim.py"] + sys.argv[1:]
W.main()
