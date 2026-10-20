"""FinTruth I: WRDS CRSP CIZ (v2) research adapter.

Connects using user-owned WRDS credentials on their machine. Does not upload
licensed CRSP observations to GitHub or log credentials. Returns in CIZ dlyret
ALREADY include delisting returns. Never apply legacy DLRET a second time.
"""
from __future__ import annotations
import argparse
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd

VALID_TABLES={'dsf_v2','stocknames_v2','stksecurityinfohist'}
REQUIRED_DAILY={'permno','dlycaldt','dlyret'}

def normalize_ciz_daily(df):
    """Normalize CRSP CIZ daily data and validate return conventions."""
    cols={c.lower():c for c in df.columns}
    missing=REQUIRED_DAILY-set(cols)
    if missing:raise ValueError(f'Missing CIZ daily columns: {sorted(missing)}')
    out=df.rename(columns={cols[k]:k for k in cols}).copy()
    out['date']=pd.to_datetime(out['dlycaldt'],errors='coerce')
    out['permno']=pd.to_numeric(out['permno'],errors='coerce')
    out['total_return']=pd.to_numeric(out['dlyret'],errors='coerce')
    if out[['date','permno']].isna().any().any():
        raise ValueError('Missing or invalid PERMNO or date')
    if out.duplicated(['permno','date']).any():
        raise ValueError('Duplicate PERMNO-date observations')
    # Returns lower than -100% are not meaningful ordinary equity total returns.
    bad=out.total_return.dropna().lt(-1)
    if bad.any():raise ValueError('Return < -100%; investigate CRSP error/sentinel values')
    out['return_status']=np.where(out.total_return.isna(),'MISSING_REVIEW','CIZ_INCLUDED_DELISTING')
    return out.sort_values(['permno','date']).reset_index(drop=True)

def daily_forward_returns(ciz,signals,horizons=(1,5,21)):
    """Enter at next observed security return date after decision date.
    A delisted stock cannot provide a full later h-day holding return.
    Flag truncated windows rather than dropping them from the dataset.
    """
    d=normalize_ciz_daily(ciz)
    if not {'permno','asof_date','signal'}.issubset(signals):
        raise ValueError('Signals require permno, asof_date, signal')
    s=signals.copy()
    s['asof_date']=pd.to_datetime(s.asof_date)
    if s.duplicated(['permno','asof_date']).any():raise ValueError('Duplicate signals')
    dgroup={p:g for p,g in d.groupby('permno')}
    rows=[]
    for x in s.to_dict('records'):
        p=int(x['permno']);grp=dgroup.get(p)
        future=grp.loc[grp.date>x['asof_date']] if grp is not None else pd.DataFrame()
        for h in horizons:
            slice_=future.head(h)
            complete=len(slice_)==h and slice_.total_return.notna().all()
            rows.append({'permno':p,'asof_date':x['asof_date'],
                'signal':x['signal'],'horizon_days':h,
                'realized_total_return':float(np.prod(1+slice_.total_return)-1) if complete else np.nan,
                'entry_date':slice_.date.iloc[0] if len(slice_) else pd.NaT,
                'exit_date':slice_.date.iloc[-1] if complete else pd.NaT,
                'status':'OBSERVED' if complete else 'INCOMPLETE_WINDOW_REVIEW',
                'return_source':'CRSP_CIZ_DLYRET_INCLUDES_DELISTING'})
    return pd.DataFrame(rows)

def review_ticker_linkage(identities,pilot):
    """Candidate linkage only: ticker+overlapping date must be human reviewed."""
    required={'permno','ticker','namedt','nameenddt'}
    if not required.issubset(identities):raise ValueError('Missing CRSP name-history fields')
    if 'ticker_candidate' not in pilot:raise ValueError('Missing pilot ticker candidates')
    x=identities.copy()
    x['ticker']=x.ticker.astype(str).str.upper()
    y=pilot[['ticker_candidate']].drop_duplicates().copy()
    y['ticker_candidate']=y.ticker_candidate.str.upper()
    m=y.merge(x,left_on='ticker_candidate',right_on='ticker',how='left')
    m['identity_status']='HISTORICAL_LINK_MANUAL_REVIEW'
    m['cik']=''
    m['reviewer']=''
    m['verified']=False
    return m

def inspect_wrds(conn):
    """Read-only table/schema discovery. Available names vary by subscription."""
    libraries=conn.list_libraries()
    if 'crsp' not in libraries:raise RuntimeError('No CRSP library found in WRDS account')
    tables=conn.list_tables(library='crsp')
    matches=[t for t in ('dsf_v2','stocknames_v2','stksecurityinfohist') if t in tables]
    desc={}
    for name in matches:
        frame=conn.describe_table(library='crsp',table=name)
        desc[name]=list(frame['name'].astype(str)) if 'name' in frame else []
    return desc

def download_pilot(conn,permnos,start='2005-01-01',end='2025-12-31',chunk_size=20):
    """Query by audited PERMNO; never query current tickers as a history proxy.

    CRSP data are licensed: write downloaded extracts locally only.
    """
    if not permnos:raise ValueError('Verified PERMNO identifiers are required')
    ids=sorted(set(int(p) for p in permnos))
    if not all(0<p<10**9 for p in ids):raise ValueError('Invalid PERMNO')
    start=str(pd.Timestamp(start).date());end=str(pd.Timestamp(end).date())
    if start>end:raise ValueError('Invalid date range')
    table=inspect_wrds(conn)
    if 'dsf_v2' not in table:
        raise RuntimeError('CRSP CIZ dsf_v2 unavailable; inspect your WRDS subscription/schema')
    required={'permno','dlycaldt','dlyret'}
    cols={x.lower():x for x in table['dsf_v2']}
    if not required.issubset(cols):raise RuntimeError('Unexpected CIZ schema')
    wanted=['permno','dlycaldt','dlyret','dlyprc','dlyretmissflg']
    selected=', '.join(cols[c] for c in wanted if c in cols)
    pieces=[]
    for j in range(0,len(ids),chunk_size):
        batch=ids[j:j+chunk_size]
        idlist=','.join(str(v) for v in batch)
        # Only allow metadata-verified column names in SQL construction.
        if not all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',cols[c])
                   for c in wanted if c in cols):
            raise ValueError('Unexpected SQL column identifier')
        sql=(f'SELECT {selected} FROM crsp.dsf_v2 '
             f'WHERE permno IN ({idlist}) AND dlycaldt >= %(start)s '
             f'AND dlycaldt <= %(end)s ORDER BY permno,dlycaldt')
        pieces.append(conn.raw_sql(sql,params={'start':start,'end':end}))
    if not pieces:return pd.DataFrame()
    return normalize_ciz_daily(pd.concat(pieces,ignore_index=True))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--inspect',action='store_true',help='Inspect subscribed CRSP tables')
    p.add_argument('--permnos',help='Comma-separated manually verified CRSP PERMNO values')
    p.add_argument('--out',default='local_crsp_private')
    p.add_argument('--start',default='2005-01-01')
    p.add_argument('--end',default='2025-12-31')
    a=p.parse_args()
    if not a.inspect and not a.permnos:p.error('Use --inspect or --permnos')
    try:import wrds
    except ImportError as e:raise SystemExit('Install optional dependency: pip install wrds') from e
    out=Path(a.out);out.mkdir(exist_ok=True,parents=True)
    with wrds.Connection() as db:
        if a.inspect:
            schema=inspect_wrds(db)
            (out/'crsp_schema.json').write_text(json.dumps(schema,indent=2))
            print('Schema inspected;',out/'crsp_schema.json')
        else:
            identifiers=[int(v.strip()) for v in a.permnos.split(',')]
            data=download_pilot(db,identifiers,a.start,a.end)
            data.to_csv(out/'ciz_daily_private.csv',index=False)
            print(f'Local licensed CRSP extract: {len(data)} rows. Do not publish raw data.')
if __name__=='__main__': main()
