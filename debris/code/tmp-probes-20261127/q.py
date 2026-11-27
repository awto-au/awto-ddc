import csv,gzip,re,sys
rows=list(csv.DictReader(gzip.open('re/regdb/RTD2795T-CG.tsv.gz','rt',newline=''),delimiter='\t'))
mode=sys.argv[1]; rx=re.compile(sys.argv[2],re.I)
seen=set()
for r in rows:
    if r['kind']!='FIELD': continue
    txt=r['description'].replace('\\n',' / ')
    if mode=='desc' and rx.search(txt+' '+r['field']):
        k=(r['page'],r['address'],r['register'],r['bit_high'],r['bit_low'])
        if k in seen: continue
        seen.add(k)
        print(f"{r['page']}:{r['address']} {r['register']}[{r['bit_high']}:{r['bit_low']}] {r['field']} {r['access']} :: {txt[:200]}")
    if mode=='reg' and rx.fullmatch(r['register']):
        k=(r['page'],r['address'],r['register'],r['bit_high'],r['bit_low'])
        if k in seen: continue
        seen.add(k)
        print(f"{r['page']}:{r['address']} {r['register']}[{r['bit_high']}:{r['bit_low']}] {r['field']} {r['access']} rst={r['reset']} :: {txt[:300]}")
