import sys, runpy
sys.path.insert(0, "/mnt/2tb/git/awto-ddc/scripts")
import wdt_test as W
orig = W.Runner.hang_case if hasattr(W, "Runner") else None
cls = [c for c in vars(W).values() if isinstance(c, type) and hasattr(c, "hang_case")][0]
o = cls.hang_case
def hc(self, *a, **k):
    bad, r, dl = o(self, *a, **k)
    if r:
        print("DBG", a[0], "dl", dl, "before", r[0], "after", r[1], "dt", r[2], flush=True)
    return bad, r, dl
cls.hang_case = hc
sys.argv = ["wdt_test.py"] + sys.argv[1:]
W.main()
