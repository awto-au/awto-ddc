import gzip,re,sys,glob,os
pat=re.compile(r'temperature|thermal|thermo|\btemp\b|temp_|_temp|tsens|ts_|thermometer|diode|bandgap|\bvbe\b|ptat|junction|saradc|lsadc|dvfs|ring.?osc|\bro_|process.?mon|osc.*(cnt|count|measure)|ioscm|iosc|dft|monitor|tsensor|\bsensor\b',re.I)
for f in sorted(glob.glob('re/regdb/*.gz')):
    n=os.path.basename(f)[:-7]
    print('=====',n)
    seen=set()
    for i,l in enumerate(gzip.open(f,'rt')):
        c=l.rstrip('\n').split('\t')
        if i==0 or len(c)<17: continue
        if c[4]!='FIELD': continue
        txt=' '.join([c[5],c[8],c[16]])
        if pat.search(txt):
            print(c[0],c[1],c[5],c[6]+':'+c[7],c[8],c[9],c[10],'|',c[16][:110])
