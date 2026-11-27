d=open('/home/dan/vendors/realtek/analysis/dumps/jxc-4k-flash-bus20.bin','rb').read()
blobs={0x228C6:'A',0x22BED:'B',0x231AB:'C',0x23B41:'D'}
print("preceding bytes", d[0x228C6-16:0x228C6].hex(), "after D end", hex(0x23B41+10+9867), d[0x23B41+10+9867:0x23B41+10+9867+16].hex())
for off,n in blobs.items():
    lo=off&0xFFFF
    for name,v in (("bank-local",lo),("+0x8000",lo+0x8000 if lo<0x8000 else lo),("full3",off)):
        for pat,fmt in ((v.to_bytes(2,'big') if v<0x10000 else None,'BE16'),(v.to_bytes(2,'little') if v<0x10000 else None,'LE16'),(off.to_bytes(3,'big'),'BE24')):
            if pat is None: continue
            i=-1;hits=[]
            while True:
                i=d.find(pat,i+1)
                if i<0 or len(hits)>12:break
                hits.append(hex(i))
            if hits and len(hits)<=12 and not(fmt=='BE24' and name!='full3'): print(n,name,fmt,pat.hex(),hits)
