"""Fail-closed financial reconciliation, point-in-time DCF and delisting checks."""
import numpy as np
import pandas as pd
from dcf import DCFInputs, value_dcf

KEYS=['cik','original_accession','filing_period_end','gaap_tag','fiscal_context']
AUDIT=KEYS+['source_sha256','source_url','auditor','audited_at','publicly_available_at',
             'financial_value','reconciled_to_original']

def reconcile_financial_records(facts,audit):
    missing=set(AUDIT)-set(audit)
    if missing:raise ValueError(f'Audit ledger missing {sorted(missing)}')
    if set(KEYS)-set(facts):raise ValueError('Extracted facts missing provenance keys')
    if audit.duplicated(KEYS).any():raise ValueError('Duplicate audit records')
    d=facts.merge(audit,on=KEYS,how='left',validate='many_to_one',indicator=True)
    valid=(d['_merge']=='both') & d.reconciled_to_original.astype(str).str.lower().eq('true')
    valid &= d.source_sha256.notna() & d.source_url.notna() & d.auditor.notna()
    valid &= pd.to_datetime(d.publicly_available_at,errors='coerce').notna()
    valid &= np.isclose(pd.to_numeric(d.value,errors='coerce'),
                        pd.to_numeric(d.financial_value,errors='coerce'),rtol=1e-8,atol=0)
    d['validation_status']=np.where(valid,'AUDITED_SOURCE_RECONCILED','REJECTED_UNVERIFIED')
    return d.drop(columns=['_merge'])

def audited_dcf(row, assumptions):
    required=['revenue','operating_income','tax_rate','depreciation_amortization',
              'capital_expenditure','change_nwc','cash','total_debt','diluted_shares','market_price']
    if any(str(row.get(k+'_verified','')).lower()!='true' for k in required):
        raise ValueError('DCF blocked: original data not verified')
    if not assumptions.get('assumptions_verified'):
        raise ValueError('DCF blocked: assumptions not verified')
    asof=pd.Timestamp(assumptions['asof_date'])
    if pd.Timestamp(assumptions['available_at'])>=asof:
        raise ValueError('DCF assumptions known only after decision time')
    if any(pd.Timestamp(row[k+'_available_at'])>=asof for k in required):
        raise ValueError('DCF contains future data')
    rev=float(row['revenue'])
    x=DCFInputs(ticker=str(row['ticker']),asof_date=str(asof.date()),revenue=rev,
      ebit_margin=float(row['operating_income'])/rev,tax_rate=float(row['tax_rate']),
      depreciation_amortization=float(row['depreciation_amortization']),
      capital_expenditure=float(row['capital_expenditure']),
      change_nwc=float(row['change_nwc']),cash=float(row['cash']),
      total_debt=float(row['total_debt']),diluted_shares=float(row['diluted_shares']),
      market_price=float(row['market_price']),wacc=float(assumptions['wacc']),
      terminal_growth=float(assumptions['terminal_growth']),
      revenue_growth=float(assumptions['revenue_growth']))
    result=value_dcf(x);result['validation_status']='INPUTS_AUDITED_ASSUMPTIONS_REVIEWED'
    return result

def delisting_aware_backtest(prices,signals,horizons=(1,5,21)):
    """CRSP-style input with stable security ID. User must supply licensed returns.
    ret and dlret compound on an applicable delisting date.
    """
    required={'permno','date','ret','dlret','delisting_event'}
    if not required.issubset(prices):raise ValueError(f'Missing prices: {required-set(prices)}')
    if not {'permno','asof_date','signal'}.issubset(signals):
        raise ValueError('Missing signal fields')
    p=prices.copy();s=signals.copy()
    p['date']=pd.to_datetime(p['date']);s['asof_date']=pd.to_datetime(s['asof_date'])
    if p.duplicated(['permno','date']).any():raise ValueError('Duplicate security/date')
    p['ret']=pd.to_numeric(p.ret,errors='coerce');p['dlret']=pd.to_numeric(p.dlret,errors='coerce')
    p['delisting_event']=p.delisting_event.astype(str).str.lower().isin(['true','1','yes'])
    p['missing_dlret']=p.delisting_event&p.dlret.isna()
    p['combined_return']=(1+p.ret.fillna(0))*(1+p.dlret.fillna(0))-1
    p.loc[p.ret.isna()&p.dlret.isna(),'combined_return']=np.nan
    out=[]
    for record in s.to_dict('records'):
        hist=p[(p.permno==record['permno'])&(p.date>record['asof_date'])].sort_values('date')
        for h in horizons:
            window=hist.head(h)
            valid=(len(window)==h and not window.missing_dlret.any()
                   and window.combined_return.notna().all()
                   and not (window.delisting_event.iloc[:-1].any() if len(window)>1 else False))
            out.append({'permno':record['permno'],'asof_date':record['asof_date'],
                        'horizon':h,'return':float(np.prod(1+window.combined_return)-1) if valid else np.nan,
                        'status':'COMPUTED' if valid else 'ABSTAIN_MISSING_OR_DELISTED'})
    return pd.DataFrame(out)
