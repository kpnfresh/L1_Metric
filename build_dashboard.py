#!/usr/bin/env python3
"""
KPN Fresh Dashboard — Daily Build Pipeline
===========================================
Reads from sales.duckdb → builds index.html + parquet files.

Usage:
    python3 build_dashboard.py                              # uses sales.duckdb in same folder
    python3 build_dashboard.py --db D:/Reports/sales.duckdb
    python3 build_dashboard.py --db D:/Reports/sales.duckdb --out dashboard.html

Daily workflow:
    1. Drop new sales.duckdb into the folder (or update D:/Reports/sales.duckdb)
    2. Double-click refresh.bat  (or run: python3 build_dashboard.py)
    3. Open index.html in browser  (or push to GitHub Pages)
"""

import argparse, json, os, sys, re
from datetime import datetime, date
import duckdb
import pandas as pd

# ── CLI ───────────────────────────────────────────────────────────────────────
p = argparse.ArgumentParser()
p.add_argument('--db',  default='sales.duckdb')
p.add_argument('--out', default='index.html')
args = p.parse_args()

HERE    = os.path.dirname(os.path.abspath(__file__))
DB_PATH = args.db if os.path.isabs(args.db) else os.path.join(HERE, args.db)
OUT     = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)
PRE     = os.path.join(HERE, '_tmpl_pre.html')
JS      = os.path.join(HERE, '_tmpl_js.html')

for path, label in [(DB_PATH,'sales.duckdb'),(PRE,'_tmpl_pre.html'),(JS,'_tmpl_js.html')]:
    if not os.path.exists(path):
        print(f'❌  Missing: {label}  ({path})')
        sys.exit(1)

print(f'📦  DB   : {DB_PATH}')
print(f'📄  Out  : {OUT}')

# ── CLUSTER MAP ───────────────────────────────────────────────────────────────
CLUSTER = {
    'OCHNADB01':'Ananth',   'OCHNAMB02':'Hinduraj P', 'OCHNANN06':'Alagiri',
    'OCHNCLM01':'Mahesh',   'OCHNCPR01':'Hinduraj P', 'OCHNGKM01':'Alagiri',
    'OCHNKGR01':'Hari Govindan','OCHNKKN02':'Hinduraj P','OCHNKTC01':'Ananth',
    'OCHNKTP01':'Mahesh',   'OCHNMDB01':'Hari Govindan','OCHNMGP02':'Hinduraj P',
    'OCHNMGP04':'Hinduraj P','OCHNMPK01':'Mahesh',   'OCHNMYL01':'Mahesh',
    'OCHNMYL02':'Mahesh',   'OCHNOMR01':'Ananth',    'OCHNPBK01':'Hari Govindan',
    'OCHNPER01':'Ananth',   'OCHNPML01':'Hari Govindan','OCHNPWK01':'Alagiri',
    'OCHNROY01':'Alagiri',  'OCHNSAI01':'Mahesh',    'OCHNSSN01':'Alagiri',
    'OCHNTMB01':'Hari Govindan','OCHNTNG03':'Mahesh', 'OCHNUTH01':'Ananth',
    'OCHNVAL01':'Ananth',   'OCHNVEL02':'Ananth',    'OCHNVEP02':'Alagiri',
}

# L1 categories to INCLUDE (exclude TOTAL, Consumables, etc.)
L1_INCLUDE = {'Fruits','Vegetables','FMCG Food','FMCG Non Food',
               'Staples','Poultry','KPN Cafe','Others'}

# ORDER_SOURCE to include for KSIN/L1/L2 level (transactional rows only)
SRC_TXNAL  = ("'POS','ECOM'")
# ORDER_SOURCE for NOB GRAND TOTAL (POS+ECOM daily overall summaries)
SRC_NOB_GT = ("'POS DAILY OVERALL','ECOM DAILY OVERALL'")

# ── CONNECT ───────────────────────────────────────────────────────────────────
con = duckdb.connect(DB_PATH, read_only=True)

# ── PARSE DATES ───────────────────────────────────────────────────────────────
# DB has two date formats: DD-Mon-YYYY  and  YYYY-MM-DD
# Normalise to date objects
print('🔨  Detecting date range...')
raw_dates = con.execute("SELECT DISTINCT DATE FROM sales_daily ORDER BY DATE").fetchall()

def parse_date(s):
    for fmt in ('%d-%b-%Y','%Y-%m-%d','%d-%B-%Y'):
        try: return datetime.strptime(s.strip(), fmt).date()
        except: pass
    return None

all_dates = sorted(filter(None, [parse_date(r[0]) for r in raw_dates]))
max_date  = max(all_dates)
print(f'   Date range: {min(all_dates)} → {max_date}  ({len(all_dates)} days)')

# ── DYNAMIC PERIOD MAPPING ────────────────────────────────────────────────────
# Periods: mar_full, apr_full, may_full, may_mtd, jun_mtd  (and prev_mtd auto)
# MTD = 1st of month → max_date for that month
# Full = entire calendar month (only if fully completed)

def dates_for_period(period_dates):
    """Return set of raw DATE strings matching the given date objects."""
    date_set = set(period_dates)
    return {r[0] for r in raw_dates if parse_date(r[0]) in date_set}

cur_month = max_date.month   # e.g. 6 = June
cur_year  = max_date.year

# Build period → date-string sets
import calendar

def full_month_dates(year, month):
    _, last = calendar.monthrange(year, month)
    return [date(year, month, d) for d in range(1, last+1)]

def mtd_dates(year, month, up_to_day):
    return [date(year, month, d) for d in range(1, up_to_day+1)]

# Current month MTD (jun_mtd)
period_jun_mtd  = mtd_dates(cur_year, cur_month, max_date.day)
# Previous month MTD same-day cutoff (may_mtd)
prev_month = cur_month - 1 if cur_month > 1 else 12
prev_year  = cur_year if cur_month > 1 else cur_year - 1
period_may_mtd  = mtd_dates(prev_year, prev_month, max_date.day)
# Previous month full
period_may_full = full_month_dates(prev_year, prev_month)
# Two months ago full
pm2 = prev_month - 1 if prev_month > 1 else 12
py2 = prev_year if prev_month > 1 else prev_year - 1
period_apr_full = full_month_dates(py2, pm2)
# Three months ago full
pm3 = pm2 - 1 if pm2 > 1 else 12
py3 = py2 if pm2 > 1 else py2 - 1
period_mar_full = full_month_dates(py3, pm3)

PERIODS = {
    'mar_full': dates_for_period(period_mar_full),
    'apr_full': dates_for_period(period_apr_full),
    'may_full': dates_for_period(period_may_full),
    'may_mtd':  dates_for_period(period_may_mtd),
    'jun_mtd':  dates_for_period(period_jun_mtd),
}

# Month labels for the JS template placeholder
month_names = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
               7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}
CUR_MON_LABEL  = f"{month_names[cur_month]} {cur_year}"
PREV_MON_LABEL = f"{month_names[prev_month]} {prev_year}"

for k, v in PERIODS.items():
    print(f'   {k}: {len(v)} date strings')

# ── HELPER: build SQL IN clause for date strings ──────────────────────────────
def in_clause(date_strs):
    if not date_strs:
        return "('__NONE__')"
    escaped = ["'"+s.replace("'","''")+"'" for s in date_strs]
    return '('+','.join(escaped)+')'

# ── BUILD SITE NAME MAP (clean names) ─────────────────────────────────────────
print('🔨  Building site map...')
sites_df = con.execute("""
    SELECT DISTINCT SITE_ID,
        MIN(CASE WHEN SITE_NAME NOT LIKE '%(DAILY OVERALL)%' THEN SITE_NAME END) as name
    FROM sales_daily
    WHERE SITE_ID != 'ALL SITES DAILY'
    GROUP BY SITE_ID
""").df()

SITE_NAMES = {}
SITE_FN    = {}
for _, row in sites_df.iterrows():
    sid = row['SITE_ID']
    SITE_NAMES[sid] = (row['name'] or sid).replace('KPN Fresh ','KPN ')
    SITE_FN[sid]    = 1000 + list(sites_df['SITE_ID']).index(sid)

# ── BUILD D1: store → channel → L1 → L2 → period → {N,Q,G} ──────────────────
print('🔨  Building D1 (L1/L2 per store)...')

def r2(v):
    if v is None or (isinstance(v, float) and (v != v)): return 0
    v = round(float(v), 2)
    return int(v) if v == int(v) else v

D1 = {}

for period_key, date_strs in PERIODS.items():
    if not date_strs:
        continue
    sql = f"""
        SELECT SITE_ID, ORDER_SOURCE, M1 as l1, M2 as l2,
               SUM(NOB) as N, SUM(QTY) as Q, SUM(GMV) as G
        FROM sales_daily
        WHERE DATE IN {in_clause(date_strs)}
          AND SITE_ID != 'ALL SITES DAILY'
          AND ORDER_SOURCE IN ({SRC_TXNAL})
          AND M1 IN ({','.join("'"+l+"'" for l in L1_INCLUDE)})
          AND M2 IS NOT NULL AND M2 != ''
          AND (KPN_TITLE IS NULL OR UPPER(KPN_TITLE) != 'TOTAL')
        GROUP BY SITE_ID, ORDER_SOURCE, M1, M2
    """
    rows = con.execute(sql).df()
    for _, row in rows.iterrows():
        sid = row['SITE_ID']
        if sid not in CLUSTER: continue
        ch  = row['ORDER_SOURCE']
        l1  = row['l1']
        l2  = row['l2']
        if sid not in D1:
            D1[sid] = {
                'name':    SITE_NAMES.get(sid, sid),
                'fn':      SITE_FN.get(sid, 1000),
                'cluster': CLUSTER[sid],
            }
        D1[sid].setdefault(ch, {}).setdefault(l1, {}).setdefault(l2, {})[period_key] = {
            'N': r2(row['N']), 'Q': r2(row['Q']), 'G': r2(row['G'])
        }

print(f'   D1: {len(D1)} stores')

# ── BUILD D2: store → L1 → L2 → KSIN → {t, m:{N,G}, j:{N,G}} ───────────────
# m = may_mtd, j = jun_mtd
print('🔨  Building D2 (KSIN level)...')

D2 = {}

for period_key, date_strs in [('m', PERIODS['may_mtd']), ('j', PERIODS['jun_mtd'])]:
    if not date_strs: continue
    sql = f"""
        SELECT SITE_ID, M1 as l1, M2 as l2, KSIN, MIN(KPN_TITLE) as title,
               SUM(NOB) as N, SUM(GMV) as G
        FROM sales_daily
        WHERE DATE IN {in_clause(date_strs)}
          AND SITE_ID != 'ALL SITES DAILY'
          AND ORDER_SOURCE IN ({SRC_TXNAL})
          AND M1 IN ({','.join("'"+l+"'" for l in L1_INCLUDE)})
          AND M2 IS NOT NULL AND M2 != ''
          AND KSIN IS NOT NULL AND KSIN != ''
          AND (KPN_TITLE IS NULL OR UPPER(KPN_TITLE) != 'TOTAL')
        GROUP BY SITE_ID, M1, M2, KSIN
    """
    rows = con.execute(sql).df()
    for _, row in rows.iterrows():
        sid  = row['SITE_ID']
        if sid not in CLUSTER: continue
        l1   = row['l1']
        l2   = row['l2']
        ksin = str(row['KSIN'])
        D2.setdefault(sid, {}).setdefault(l1, {}).setdefault(l2, {}).setdefault(ksin, {
            't':'', 'm':{'N':0,'G':0}, 'j':{'N':0,'G':0}
        })
        D2[sid][l1][l2][ksin]['t']           = row['title'] or ''
        D2[sid][l1][l2][ksin][period_key]['N'] = r2(row['N'])
        D2[sid][l1][l2][ksin][period_key]['G'] = r2(row['G'])

print(f'   D2: {len(D2)} stores')

# ── EXPORT PARQUET for DuckDB-WASM ────────────────────────────────────────────
print('🔨  Exporting parquet files...')

sm_rows = []
for sid, sd in D1.items():
    name    = sd['name']
    cluster = sd['cluster']
    for ch in ['POS','ECOM']:
        if ch not in sd: continue
        for l1, l2map in sd[ch].items():
            for l2, permap in l2map.items():
                for period, vals in permap.items():
                    sm_rows.append([sid, name, cluster, ch, l1, l2, period,
                                    vals['N'], vals.get('Q',0), vals['G']])

sm_df = pd.DataFrame(sm_rows, columns=['store_id','store_name','cluster','channel',
                                        'l1','l2','period','nob','qty','gmv'])
sm_df.to_parquet(os.path.join(HERE, 'store_metrics.parquet'), index=False)

km_rows = []
for sid, l1map in D2.items():
    name    = D1.get(sid,{}).get('name', sid)
    cluster = CLUSTER.get(sid,'')
    for l1, l2map in l1map.items():
        for l2, kmap in l2map.items():
            for ksin, kd in kmap.items():
                km_rows.append([sid, name, cluster, l1, l2, ksin, kd['t'],
                                 kd['m']['N'], kd['m']['G'],
                                 kd['j']['N'], kd['j']['G']])

km_df = pd.DataFrame(km_rows, columns=['store_id','store_name','cluster','l1','l2',
                                        'ksin','title','m_nob','m_gmv','j_nob','j_gmv'])
km_df.to_parquet(os.path.join(HERE, 'ksin_metrics.parquet'), index=False)

sm_kb = os.path.getsize(os.path.join(HERE,'store_metrics.parquet'))/1024
km_kb = os.path.getsize(os.path.join(HERE,'ksin_metrics.parquet'))/1024
print(f'   store_metrics.parquet : {sm_kb:.0f} KB')
print(f'   ksin_metrics.parquet  : {km_kb:.0f} KB')

# ── SERIALISE TO JS ───────────────────────────────────────────────────────────
print('🔨  Serialising to JavaScript...')
d1_js = 'const D1='+json.dumps(D1, separators=(',',':'), ensure_ascii=False)+';\n'
d2_js = 'const D2='+json.dumps(D2, separators=(',',':'), ensure_ascii=False)+';\n'

# ── ASSEMBLE ─────────────────────────────────────────────────────────────────
print('🔨  Assembling index.html...')
tmpl_pre = open(PRE, 'r', encoding='utf-8').read()
tmpl_js  = open(JS,  'r', encoding='utf-8').read()



# Patch dynamic labels in JS template
import calendar as _cal

max_date_str = max_date.strftime('%d %b %Y')
cur_last     = max_date.day

# MTD column headers e.g. "May 2026 MTD (1-25)"
prev_mtd_label = f'{PREV_MON_LABEL} MTD (1–{cur_last})'
cur_mtd_label  = f'{CUR_MON_LABEL} MTD (1–{cur_last})'

# Comparison range text e.g. "May 1-25 vs Jun 1-25"
prev_range = f'{month_names[prev_month]} 1–{cur_last}'
cur_range  = f'{month_names[cur_month]} 1–{cur_last}'

# Full months last days
_, mar_last = _cal.monthrange(py3, pm3)
_, apr_last = _cal.monthrange(py2, pm2)
_, may_last = _cal.monthrange(prev_year, prev_month)
periods_label = (
    f'Mar Full (1–{mar_last}) · Apr Full (1–{apr_last}) · '
    f'{PREV_MON_LABEL} Full (1–{may_last}) · '
    f'{prev_mtd_label} · {cur_mtd_label}'
)

# Patch _tmpl_pre placeholders
tmpl_pre = tmpl_pre.replace('{{PREV_MON_LABEL}}', PREV_MON_LABEL)
tmpl_pre = tmpl_pre.replace('{{CUR_MON_LABEL}}',  CUR_MON_LABEL)
tmpl_pre = tmpl_pre.replace('{{MAX_DATE}}',        max_date_str)

# Replace all placeholders
tmpl_js = tmpl_js.replace("'May 2026','may',mayFA,mFT]",
                           f"'{PREV_MON_LABEL}','may',mayFA,mFT]")
tmpl_js = tmpl_js.replace('{{PREV_MON_MTD_LABEL}}', prev_mtd_label)
tmpl_js = tmpl_js.replace('{{CUR_MON_MTD_LABEL}}',  cur_mtd_label)
tmpl_js = tmpl_js.replace('{{PREV_MON_RANGE}}',     prev_range)
tmpl_js = tmpl_js.replace('{{CUR_MON_RANGE}}',      cur_range)
tmpl_js = tmpl_js.replace('{{PERIODS_LABEL}}',      periods_label)
tmpl_js = tmpl_js.replace('{{PREV_MON_LABEL}} MTD', f'{PREV_MON_LABEL} MTD')
tmpl_js = tmpl_js.replace('{{CUR_MON_LABEL}} MTD',  f'{CUR_MON_LABEL} MTD')

# Footer max date
tmpl_js = tmpl_js.replace(
    '<strong>Max Data Date:</strong> 24 Jun 2026',
    f'<strong>Max Data Date:</strong> {max_date_str}'
)

final = tmpl_pre + d1_js + d2_js + tmpl_js

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(final)

out_kb = os.path.getsize(OUT)/1024
print(f'\n✅  Done!')
print(f'   {OUT}  ({out_kb:.0f} KB)')
print(f'   store_metrics.parquet  ({sm_kb:.0f} KB)')
print(f'   ksin_metrics.parquet   ({km_kb:.0f} KB)')
print(f'   Max data date: {max_date_str}')
print(f'\n📂  Push index.html + both .parquet files to GitHub for GitHub Pages.')

con.close()
