import sys; sys.path.insert(0,'scripts')
import fw_sim_vendor as V
m,h=V.vendor_machine(V.VENDOR_IMG,'2160p60')
calls=[]
names=['ScalerMeasureInputInfo','SysSourceJudge','ScalerMDomainControl','ScalerMDomainMemorySettings','ScalerMDomainSetDisplayFormat','ScalerFRCControl','ScalerFmtCnvFinalSetting','ScalerMemoryReset','ScalerDPLLFineTuneFrameSyncLineBuffer','ScalerMeasureUpdateOnlineMeasureResult','ScalerMDomainMemoryConfig','ScalerMDomainCalculateDclkDVtotal','ScalerDisplayTimingGen' ]
for n in names:
    if '_'+n in m.sym: m.stub(n, lambda m_,r,n=n: calls.append((m_.instr,n)))
last=None; ev=[]
for i in range(70):
    m.run(100_000) if False else None
    m.run(1_000_000)
    ms=m.rd(0xe22e)[0]
    if ms!=last: ev.append((m.instr,hex(ms))); last=ms
print(ev)
for c in calls:
    if c[0]>44_000_000 and c[1] not in ('SysSourceJudge',): print(c)
