import re, sys
def load(p):
    ev, res = [], []
    for ln in open(p):
        m = re.match(r"\s+(\d+) (.{13}) (.{22}) +(\d+) (\S)$", ln.rstrip("\n"))
        if m:
            ev.append((int(m.group(1)), m.group(2).strip(), m.group(3).strip(), int(m.group(4))))
        m = re.match(r"\s+(PASS|FAIL) (cold boot: ACTIVE|POWER key: power OFF|POWER key: ACTIVE again|signal back: ACTIVE, backlight on|power saving reached|SOURCE key wake: ACTIVE)(.*)", ln)
        if m:
            res.append(m.group(2) + m.group(3))
    return ev, res
for p in sys.argv[1:]:
    ev, res = load(p)
    print("==", p, "|", "; ".join(res))
    phases = []
    for t, ph, w, v in ev:
        if not phases or phases[-1][0] != ph:
            phases.append((ph, []))
        phases[-1][1].append((t, w, v))
    for ph, es in phases:
        t0 = es[0][0]
        short = []
        for t, w, v in es:
            n = {"VDD pin": "VDD", "BL pin": "BL", "PWM4 duty": "PWM", "DPTx LinkSequence": "LINK", "DPTx StreamHanlder": "STREAM",
                 "DPTx PhyInitial": "PHY", "DPTx AnalogPhyConrol": "APHY", "DPTx SSCSet": "SSC", "BL_EN_N pin": None}.get(w, w)
            if n is None: continue
            short.append(f"{n}{'' if n in ('LINK','PHY') else '=' + str(v)}@{t - t0}")
        print(f"  {ph:13s} (+{t0}) " + " ".join(short))
