import csv,sys,re,os
sys.path.insert(0,'/mnt/2tb/git/awto-ddc/scripts')
os.environ['AWTO_DDC_REPO']=S='/tmp/claude-1000/-mnt-2tb-git-awto-ddc/f7982fc5-907c-4500-a6ef-8f90f4ceaa15/scratchpad/root'
import delay_inventory as D
defs={}
for l in open(S+'/tmp/delay_inventory/macros.txt',errors='replace'):
    m=re.match(r"#define\s+(\w+)(\([^)]*\))?\s*(.*)$",l)
    if m: defs.setdefault(m.group(1)+(m.group(2) or ''),m.group(3).strip())
ev=D.Eval(defs)
rows=list(csv.DictReader(open(S+'/out/delays.tsv'),delimiter='\t'))
def first(stmt,name):
    a=D.split_args(stmt,name)
    return a
for x in rows:
    if x['linked']!='yes': continue
    k=x['kind']; st=x['stmt']
    x['res']=''
    if k=='delay_ms':
        a=first(st,'ScalerTimerDelayXms')
        if a: x['res']=str(ev.value(a[0]))
    elif k=='poll':
        a=first(st,'ScalerTimerPollingFlagProc')
        if a: x['res']=str(ev.value(a[0]))
    elif k=='wait_event':
        x['res']=''
