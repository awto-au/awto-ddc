#!/usr/bin/env python3
"""Join ISP reg dumps (tmp/regs/*.json) with regdb + SDK names. Read-only; writes TSVs to tmp/scratch/regclass_*.tsv"""
import json, glob, gzip, re, csv, os, sys, collections, datetime
R = '/mnt/2tb/git/awto-ddc/'
OUT = R + 'tmp/scratch/'
H = R + 'fw/sdk/Kernel/Scaler/RL6449_Series_Common/Header/RL6449_Series_Common_RegCommonInclude.h'
PORT_DATA = {0x0025,0x002B,0x0031,0x0034,0x005D,0x0061,0x0065,0x008E,0x07CF,0x07D3,0x15A4,0x2AAD,0x2AFC,0x4025,0x68AD,0x68FC,0x713A,0x723A,0x71CA,0x72CA,0xB7C4,0xBAC4}
PORT_ADDR = {0x24,0x2A,0x30,0x33,0x5C,0x60,0x64,0x8D,0x7CE,0x7D2,0x15A3,0x2AAC,0x2AFB,0x4024,0x68AC,0x68FB,0x7139,0x7239,0x71C9,0x72C9,0xB7C1,0xB7C2,0xB7C3,0xBAC1,0xBAC2,0xBAC3}
# other known data-port/FIFO-ish pages: OSD RAM 0x92/0x99/0x9D, bg 0x6D, dither 0x69, DCC 7CA, DCR 7D9, HDCP 71C4/72C4
EXTRA_RISK = {0x92,0x99,0x9D,0x6D,0x69,0x7CA,0x7D9,0x71C4,0x72C4}
SKIP_ADDR = PORT_ADDR | {a for a in []}
DATA_ADDRS = PORT_DATA | EXTRA_RISK | PORT_ADDR

# regdb
db = {}   # addr -> dict(reg names, fields[(name,hi,lo,access,reset)], reset)
rows_by_addr = collections.defaultdict(list)
with gzip.open(R + 're/regdb/RTD2795T-CG.tsv.gz', 'rt') as f:
    for r in csv.DictReader(f, delimiter='\t'):
        a = (int(r['page'], 16) << 8) | int(r['address'], 0) & 0xFF if False else int(r['address'], 0)
        rows_by_addr[a].append(r)
def dbinfo(a):
    rs = rows_by_addr.get(a)
    if not rs: return 'norow', '', None, []
    reg = [r for r in rs if r['kind'] == 'REG']
    fl = [r for r in rs if r['kind'] == 'FIELD']
    rn = reg[0]['register'] if reg else ''
    rst = reg[0]['reset'] if reg else ''
    named = [r for r in fl if r['field'].strip() and not re.match(r'^(reserved|dummy|rsvd|res|resv|reserve|unused)\w*$', r['field'].strip(), re.I)]
    if named: return 'doc', rn, rst, [(r['field'], r['bit_high'], r['bit_low'], r['access'], r['reset']) for r in named]
    return 'blank', rn, rst, []
# SDK
sdk = {}
for l in open(H, errors='replace'):
    m = re.match(r'#define\s+P([0-9A-F]+)_([0-9A-F]{2})_(\w+)\s+0x([0-9A-F]{4})\b', l)
    if m: sdk[int(m.group(4), 16)] = m.group(3)

dumps = []
for fn in sorted(glob.glob(R + 'tmp/regs/*.json')):
    d = json.load(open(fn))
    if 'pages' not in d: continue
    b = os.path.basename(fn)[:-5]
    m = re.match(r'(AWT\d+)-(?:(.*?)-)?(\d{8})-(\d{6})(?:-(.*))?$', b)
    unit, l1, dt, tm, l2 = m.groups()
    label = '-'.join(x for x in (l1, l2) if x) or '(none)'
    ts = datetime.datetime.strptime(dt + tm, '%Y%m%d%H%M%S')
    dumps.append(dict(fn=b, unit=unit, label=label, ts=ts, pages={int(k, 16): [int(x,16) if isinstance(x,str) else x for x in v] for k, v in d['pages'].items()}, ports=d.get('ports') or {}))
print('dumps with pages:', len(dumps), file=sys.stderr)
# per addr values
vals = collections.defaultdict(list)  # addr -> [(dumpidx, v)]
for i, d in enumerate(dumps):
    for p, arr in d['pages'].items():
        for r, v in enumerate(arr): vals[(p << 8) | r].append((i, v))
pages_read = sorted({a >> 8 for a in vals})

def groups(a):
    """(changes_same_group, changes_close(<=20min), cross_only)"""
    byg = collections.defaultdict(list)
    for i, v in vals[a]: byg[(dumps[i]['unit'], dumps[i]['label'])].append((dumps[i]['ts'], v))
    sg = close = False
    for g, l in byg.items():
        if len({v for _, v in l}) > 1:
            sg = True
            l.sort()
            for x, y in zip(l, l[1:]):
                if x[1] != y[1] and (y[0] - x[0]).total_seconds() <= 1200: close = True
    allv = {v for _, v in vals[a]}
    return sg, close, len(allv) > 1

rows = []
for a in sorted(vals):
    st, rn, rst, fl = dbinfo(a)
    vs = [v for _, v in vals[a]]
    nz = any(vs); uniq = sorted(set(vs))
    sg, close, vary = groups(a)
    p = a >> 8
    rows.append(dict(a=a, page=p, addr=f'{a:04X}', st=st, reg=rn, rst=rst, fields=';'.join(f'{x[0]}[{x[1]}:{x[2]}]{x[3]}' for x in fl),
                     sdk=sdk.get(a, ''), n=len(vs), nz=nz, uniq=uniq, sg=sg, close=close, vary=vary,
                     isport=(a in DATA_ADDRS), vals=vals[a]))
import pickle
def hx(l): return ' '.join(f'{v:02X}' for v in l)
with open(OUT + 'regclass_all.tsv', 'w') as f:
    f.write('page_addr\tregdb\treg\tfields\tsdk_name\tn_dumps\tnonzero\tall_identical\tvaries_same_unit_label\tvaries_same_unit_label_le20min\tvaries_cross_only\tis_port_or_risky\tdistinct_values\tregdb_reset\n')
    for r in rows:
        f.write('\t'.join(map(str, [r['addr'], r['st'], r['reg'], r['fields'], r['sdk'], r['n'], int(r['nz']), int(not r['vary']), int(r['sg']), int(r['close']), int(r['vary'] and not r['sg']), int(r['isport']), hx(r['uniq']), r['rst']])) + '\n')
# per-dump values for interesting regs
def per_dump(r):
    return ' | '.join(f"{dumps[i]['unit'][-1]}:{dumps[i]['label']}:{dumps[i]['ts']:%m%d-%H%M}={v:02X}" for i, v in r['vals'])
undoc = [r for r in rows if r['st'] in ('norow', 'blank')]
def wr(name, rs, extra=True):
    with open(OUT + name, 'w') as f:
        f.write('page_addr\tregdb\treg\tsdk_name\tdistinct_values\tn\tper_dump_values\n')
        for r in rs: f.write('\t'.join([r['addr'], r['st'], r['reg'], r['sdk'], hx(r['uniq']), str(r['n']), per_dump(r)]) + '\n')
a_ = [r for r in undoc if r['nz']]
b_ = [r for r in undoc if r['sg'] and not r['isport']]
wr('regclass_a_undoc_nonzero.tsv', a_)
wr('regclass_b_undoc_changing_same_state.tsv', b_)
# c: documented with value mismatching reset
def parse_int(s):
    try: return int(s, 0)
    except: return None
cs = []
for r in rows:
    if r['st'] != 'doc' or r['isport']: continue
    rr = parse_int(r['rst'] or '')
    if rr is None: continue
    if any(v != rr for v in r['uniq']):
        cs.append(r)
with open(OUT + 'regclass_c_doc_vs_reset.tsv', 'w') as f:
    f.write('page_addr\treg\tfields\tregdb_reset\tdistinct_values\tvaries_same_state\tn\n')
    for r in cs: f.write('\t'.join([r['addr'], r['reg'], r['fields'], r['rst'], hx(r['uniq']), str(int(r['sg'])), str(r['n'])]) + '\n')
# d: no-row pages
rowpages = {a >> 8 for a in rows_by_addr}
d_pages = [p for p in pages_read if p not in rowpages]
with open(OUT + 'regclass_d_norow_pages.tsv', 'w') as f:
    f.write('page_addr\tsdk_name\tdistinct_values\tn\tvaries_same_state\tper_dump_values\n')
    for r in rows:
        if r['page'] in d_pages and r['nz']:
            f.write('\t'.join([r['addr'], r['sdk'], hx(r['uniq']), str(r['n']), str(int(r['sg'])), per_dump(r)]) + '\n')
# e: all 00/FF
cnt = collections.Counter(); tot = collections.Counter()
allz = collections.Counter(); allff = collections.Counter(); mixed0F = collections.Counter()
for r in rows:
    tot[r['page']] += 1
    u = set(r['uniq'])
    if u == {0}: allz[r['page']] += 1
    elif u == {0xFF}: allff[r['page']] += 1
    elif u <= {0, 0xFF}: mixed0F[r['page']] += 1
with open(OUT + 'regclass_pagesummary.tsv', 'w') as f:
    f.write('page\tn_dumps\tregs\tnorow_or_blank\tundoc_nonzero\tundoc_changing_same_state\tdoc_changing_same_state\tall00\tallFF\tonly00_FF_mix\thas_regdb_rows\tsdk_names\n')
    for p in pages_read:
        rs = [r for r in rows if r['page'] == p]
        f.write('\t'.join(map(str, [f'{p:02X}', max(r['n'] for r in rs), len(rs), sum(r['st'] in ('norow','blank') for r in rs),
            sum(r['st'] in ('norow','blank') and r['nz'] for r in rs), sum(r['st'] in ('norow','blank') and r['sg'] and not r['isport'] for r in rs),
            sum(r['st']=='doc' and r['sg'] and not r['isport'] for r in rs), allz[p], allff[p], mixed0F[p], int(p in rowpages), sum(1 for r in rs if r['sdk'])])) + '\n')
# summary
S = dict(dumps=len(dumps), pages=len(pages_read), regs=len(rows), regs_reads=sum(r['n'] for r in rows),
 undoc=len(undoc), undoc_norow=sum(r['st']=='norow' for r in rows), undoc_blank=sum(r['st']=='blank' for r in rows), doc=sum(r['st']=='doc' for r in rows),
 undoc_nz=len(a_), undoc_chg_same=len(b_), undoc_chg_close=sum(1 for r in b_ if r['close']), undoc_chg_cross_only=sum(1 for r in undoc if r['vary'] and not r['sg'] and not r['isport']),
 doc_chg_same=sum(1 for r in rows if r['st']=='doc' and r['sg'] and not r['isport']),
 allzero=sum(allz.values()), allFF=sum(allff.values()), only_00_FF_mix=sum(mixed0F.values()), d_pages=d_pages, c=len(cs),
 undoc_nz_sdk_named=sum(1 for r in a_ if r['sdk']), undoc_nz_in_sdk_not_db=sum(1 for r in a_ if r['sdk'] and r['st']=='norow'))
print(json.dumps(S, default=str))
pickle.dump(dict(rows=[{k: v for k, v in r.items()} for r in rows], dumps=[{k: v for k, v in d.items() if k != 'pages'} for d in dumps]), open(OUT + 'regclass.pkl', 'wb'))
