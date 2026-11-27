import sys,json,re,subprocess,glob
iss=json.load(open('/mnt/2tb/git/awto-ddc/tmp/scratch/issues.json'))
M='/home/dan/.claude/projects/-mnt-2tb-git-awto-ddc/memory/'
for pat in sys.argv[1:]:
    r=re.compile(pat,re.I)
    ti=[];bo=[]
    for i in iss:
        if r.search(i['title']): ti.append(i['number'])
        else:
            n=len(r.findall((i['body'] or '')+' '.join(c['body'] for c in i['comments'])))
            if n: bo.append((i['number'],n))
    bo.sort(key=lambda x:-x[1])
    d=subprocess.run(['git','grep','-l','-i','-E',pat,'origin/main','--','docs','re/*.md','CLAUDE.md'],capture_output=True,text=True).stdout.split()
    d=[x.replace('origin/main:','') for x in d][:6]
    mm=[f.split('/')[-1] for f in glob.glob(M+'*.md') if r.search(open(f).read())][:5]
    print(f'## {pat}\n title:{ti[:8]} body:{bo[:8]}\n docs:{d}\n mem:{mm}')
