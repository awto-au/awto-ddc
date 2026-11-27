import re,collections,sys
sys.path.insert(0,'.')
from audit_items import ITEMS
um=open('chat-user-messages.md').read().split('\n## ')[1:]
msgs={}
for x in um:
    h,_,b=x.partition('\n'); p=h.split()
    if len(p)>=2 and p[0].isdigit() and re.match(r'20\d\d-',p[1]): msgs[int(p[0])]=(p[1],b)
def q(n):
    ts,b=msgs.get(n,('',''))
    b=re.sub(r'<ide_[a-z_]+>.*?</ide_[a-z_]+>','',b,flags=re.S)
    b=re.sub(r'<pasted_content[^>]*>.*?</pasted_content[^>]*>','[paste]',b,flags=re.S)
    return ts, re.sub(r'\s+',' ',b).strip()[:90].replace('|','/')
cnt=collections.Counter(); rows=[]; used=set()
for (i,ms,typ,where,st,act) in ITEMS:
    ms=sorted(set(ms)); first=ms[0]
    for m in ms: used.add(m)
    ts,t=q(first)
    cnt[st]+=1
    mr=f'm{ms[0]}' if len(ms)==1 else f'm{ms[0]}..m{ms[-1]} ({len(ms)} msgs)'
    rows.append((i,ts[5:16].replace('T',' '),mr,t,typ,where,st,act))
unm=[n for n in sorted(msgs) if n not in used]
# pop-up decisions
P=[
('P1 11-11','nvram: no persist on input switch; flush gate ACTIVE 3 s max 30 s; show all nvram settings','#151 + docs/nvram-settings.md',C:='CAPTURED'),
('P2-3,35-37 11-12..14','key dispatcher: 80 ms combo, wake rules, injected keys, hot-key menus, HOLD, keywatch one table','#132 (9 comments, Dan answers recorded)','CAPTURED'),
('P4 11-12','UP/DOWN = brightness; AUTO; inert menu rows "show, marked"','#132 / docs/keys.md','CAPTURED'),
('P5 11-12','no-support handling; Mindray A/B; delete customer code; _AWTO_FLASH_ALL fix','#162, design-162.md','CAPTURED'),
('P6 11-12','desktop layout: Philips removed from layout','memory display-layout-frozen','CAPTURED'),
('P7 11-12','short log lines (long text in host decoder)','#146','CAPTURED'),
('P8 11-12','plan: picture tuning, rotation+freeze, FreeSync, PIP?','#165 #21 #164','CAPTURED'),
('P9-10 11-12','HDCP 2.2: parked in an issue','#44','CAPTURED'),
('P11 11-12','per-port disable setting in nvram (stop host driving DP-1)','only inside #81/#162 text','PARTIAL'),
('P12 11-12','XDATA phase 2: EDID RAM, legacy buffer, floor, MEAS4K/NET opt-in, options unconditional','#168 #169 #233; floor later removed (memory no-xdata-floor)','CAPTURED'),
('P13 11-12','unit 3 bricked (byte-mode flash)','#177 + flash fixes','CAPTURED'),
('P14-18 11-12','audio/transparency live tests (right only, 30 %, 50 %, other monitor)','#94 #176 docs/audio.md','CAPTURED'),
('P19 11-13','rotation 180 via frame memory, freeze+rotate switchable, mirror = rotation','#165 #219','CAPTURED'),
('P20 11-13','backlight on immediately (ignore T8); tighten Htotal/pclk to Innolux datasheet','memory backlight-immediate; docs/monitors/panel-innolux-m280dca-e3b.md; #26','CAPTURED'),
('P21 11-13','50/30/24 Hz inputs NO SUPPORT: do I need slow rates? what is RPi?','no answer recorded (edid-fix.md only)','PARTIAL'),
('P22-30 11-13','audio test rounds (drop headphone out, 3 freqs, sound-test cmd, scroll bug)','docs/audio.md audio-registers.md, dev.py sound-test','CAPTURED'),
('P31 11-13','delay policy datasheet -10 %','memory delays-datasheet-minus-10 + global rule','CAPTURED'),
('P32 11-13','log demo lines: address in data','#146','CAPTURED'),
('P33 11-13','compiler for builds: new compiler after checks; talk to sdcc','awto-sdcc issues; #148 #179','CAPTURED'),
('P34 11-14','backlight scale reversed? breathing LED not HW PWM?','#95 docs/reversing/dahua-fw/gpio-ir.md','PARTIAL'),
('P38 11-14','keep stripped SDK code in mirror; factory menu strip + own burn-in/calibration issue','#209 #210 memory check-stripped-code','CAPTURED'),
('P39-40 11-15','host-time service; console 136x50, scrollback why; HH:MM:SS.mmm','#157 host-time.service','CAPTURED'),
('P41 11-15','stored settings survive registry changes (record before/after)','#219 (ready-to-close)','CAPTURED'),
('P42-43 11-15','boot console cost; log every wait; keep ring, test warm boot','#216 (warm-boot OSD test not run)','PARTIAL'),
('P44 11-17','qcsim5 harness flash --force-ungated? "explain the error"','#226/#227; no recorded answer','PARTIAL'),
('P45-47 11-18','old SDK cards/hot-key menus removal: Dan asked "what are they replaced with / show me"; 10 s hold reset everything with warning card; selector 60 s; wake unplug; wdt 10','#122 #132 #137 #138 #141 #145 comments; #137 removal still pending Dan review','PARTIAL'),
('P48 11-18','PLL above 350.8: do it first (small steps)','#240 docs/clock-sweep.md','CAPTURED'),
('P49 11-18','read-behind comment on #236/#1; double read in rotation; FFF1=7 default','#236 + docs/read-behind-research.md','CAPTURED'),
('P50-51 11-18','OSD port loss: 24 nops vs sel 12; asteroids overlay; retire Scope 1; merge saver-cmd; FFF1 test + sweep','docs/osd-port-loss.md, decision commit 7bce876; Scope 1 retire on unmerged branch','PARTIAL'),
('P53 11-19','Philips next steps (SmartControl Wine, DPCD i915, ISP 0x49); layout restore once; wake-failure issue; overlay default on ALL savers incl cpu/spi/pll','#136 comment, #252, docs/asteroids.md; overlay on all savers incl CPU/SPI/PLL: no record','PARTIAL'),
('P54 11-19','flash --force-ungated for Scope 1 retire; 25 fps max?; asteroids hi-res options (35x13 vs 24x36 OT-8); selectable savers','docs/asteroids.md saver-fps-plan.md; "25 fps max" and hi-res choice open','PARTIAL'),
('P55-57 11-19','#254 use unit 2; restore 24 nops; DP lock debug on unit 2; #255 freeze build; plain-words post','#254 #255 #239; freeze build branch freeze-port-255 unmerged','PARTIAL'),
('P58-63 11-19','listen/look tests on unit 3 (diag console fine, pacman ok)','docs/gates, audio fix 5fb82d4','CAPTURED'),
('P64 11-19','one more flash pollring2 (DP lock); pause Philips and log all in issue+md','branch a1ded44 (unmerged); #136 comment','PARTIAL'),
]
pc=collections.Counter(p[3] for p in P)
tot=collections.Counter(); 
for r in rows: tot[r[6]]+=1
# write
o=open('chat-audit.md','w')
w=o.write
w('# Chat coverage audit (session f7982fc5, 2026-11-10 .. 2026-11-19)\n\n')
w(f'- Source: genuine human messages = {len(msgs)} (scripts/audit_chat.py; list in tmp/scratch/chat-user-messages.md), 64 pop-up answers (chat-popup-answers.md), 16 compaction summaries used as cross-check (chat-compaction-summaries.md).\n')
w(f'- Method: every message read; grouped into {len(ITEMS)} action items (msg ids per row); issues checked = {len(open("issues.json").read())//1} bytes of gh export of awto-au/awto-ddc (244 issues, #1..#260); docs checked on origin/main (b8dc30a) + branches; memory = 46 files.\n')
w('- Caveat: status for CAPTURED rows is by issue title/keyword + spot reads, not a line-by-line proof that the issue text carries every detail of the ask.\n\n')
w('## Counts\n\n| status | action items | pop-up decisions |\n|---|---|---|\n')
for s in ('CAPTURED','DONE','PARTIAL','MISSING','ACK'): w(f'| {s} | {tot[s]} | {pc.get(s,0)} |\n')
w(f'\nMessages not placed in any item row (treated as acks/chatter after reading): {len(unm)} of {len(msgs)} -> listed in Appendix A.\n\n')
w('## MISSING and PARTIAL, ranked by importance\n\n')
rank=[
('MISSING','Decision records for Dan 2026-11-18 answers (#229 key click, #230 row 11 0B, #231 photos, #137 q3 decimals, #138 q3 wdt guard, #145 q4, #151 G / fix 3) not posted; compaction summary of 11-18 lists them as "needs approval" and #229/#230/#231 still have 0 Dan-answer comments','audit-issues/04'),
('PARTIAL','Photos decision conflict: Dan said full-res photos WITH GPS, not zipped (m528 #12); main has docs/monitors/photos/full with GPS stripped (doc_photos.py --full) and #231 says so','audit-issues/03'),
('PARTIAL','DP input does not lock at 350.8 MHz on unit 2 (m669,m674,P56,P64): newest result (poll fix refuted, ISR DPCD reads wrong) only in unmerged branch worktree-agent-a1ded44cb10f2efb7','audit-issues/01'),
('PARTIAL','Scope 1 retire (m678, P51/P54): lives only on unmerged branches worktree-agent-ab4c2382e531243eb / ab60054; flash blocked by gate kills; no issue','audit-issues/06'),
('PARTIAL','Philips 288E2: no own issue; "pause Philips, log in issue + md" satisfied only by a comment in #136 (port-candidates issue) + docs; probe branch a43699044 unmerged','audit-issues/07'),
('MISSING','Brightness dialog bug at 1 % (m566) and horizontal-line brightness bug (m426): no issue, no doc','audit-issues/02'),
('PARTIAL','Saver overlay (resolution/fps) default: Dan wants it on ALL screen savers incl CPU speed, SPI speed, PLL (P53); no issue/doc','audit-issues/08'),
('MISSING','Rule: Dan is remote, every visual test needs screenshots / VLC captures in chat (m428); not in memory','memory-drafts.md'),
('MISSING','Rule: pop-up answers must be recorded in the issue/open-decisions the same turn (root cause of this audit); not in memory or CLAUDE.md','memory-drafts.md'),
('PARTIAL','Unfiled agent findings (assistant said "not filed, for approval"): OSD-model bugs/HLW border/docstring/CI picture-check gate; live-scan dump follow-ups; sdcc volatile write->read drop + sim gaps; Pac-Man audio (amp P7.4, draw kills sound, one cmd per pass)','audit-issues/09,10,11'),
('PARTIAL','Per-port disable NVRAM setting (P11, m236, m254): only inside #81/#162','audit-issues/12'),
('PARTIAL','Power logging: log sleep requests/ignored requests, wake commands, EDID reads (m395); wake-reason line (m121) only under #29/#145','audit-issues/05'),
('PARTIAL','OSD manual with sim captures / OSD docs merge (m574-577): docs/osd/ exists, no tracking row of completeness','-'),
('PARTIAL','Branch-only work not on main or tracked: audio-popfree (#249 fix), docs/ddcui, freeze-port-255, a3e0d67 pacing prototype (#256), a5641cd Asteroids hi-res, a59458 OT-8, a62a86 OSD app monitor page, aa9c54 flash sector churn, saver_tour.py fix uncommitted','section 5'),
('PARTIAL','m589 (other I2C address for temp sensor seen in old scan) and m591 (trace the codec) have no recorded answer; P21 slow input rates (50/30/24 Hz) never answered; m99 material-style status icons not done','audit-issues/13'),
]
for k,(s,t,a) in enumerate(rank,1): w(f'{k}. **{s}** {t} -> {a}\n')
w('\n## 1. Matrix (action items; msg ids refer to chat-user-messages.md)\n\n| # | date/time | msgs | Dan said (short) | type | captured where | status | action |\n|---|---|---|---|---|---|---|---|\n')
for r in rows: w('| '+' | '.join(str(x) for x in r)+' |\n')
w('\n## 2. Pop-up (AskUserQuestion) decisions\n\n| id | decision | captured where | status |\n|---|---|---|---|\n')
for p in P: w('| '+' | '.join(p)+' |\n')
w('\n## Appendix A. Messages not in a row (read, judged chatter/ack/ide-open notice)\n\n')
w(', '.join(f'm{n}' for n in unm)+'\n')
o.close()
print(tot,pc,len(unm),len(msgs))
