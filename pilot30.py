"""FinTruth I: reproducible 30-company SEC/AAER candidate registry and audit gates.

AAER index appearances are *leads*, NOT confirmed issuer misconduct or fraud
labels. Comparison firms are unlabeled, NOT confirmed 'clean' controls.
"""
from pathlib import Path
import argparse
import pandas as pd

LEADS=[
 ('CELH','Celsius Holdings','4559','2025-01-17'),
 ('AEP','American Electric Power','4558','2025-01-17'),
 ('SGLY','Singularity Future Technology','4557','2025-01-17'),
 ('DMK','DMK Pharmaceuticals / Adamis','4555','2025-01-14'),
 ('AAR','AAR Corp','4550','2024-12-19'),
 ('BDX','Becton Dickinson','4547','2024-12-16'),
 ('EXPR','Express Inc','4548','2024-12-17'),
 ('HON','Honeywell International','4368','2022-12-19'),
 ('KOP','Koppers Holdings','4360','2022-11-01'),
 ('SNCR','Synchronoss Technologies','4302','2022-06-07'),
 ('ROL','Rollins Inc','4294','2022-04-18'),
 ('BAX','Baxter International','4283','2022-02-22')]
CONTROLS=[
 ('AAPL','Apple'),('MSFT','Microsoft'),('GOOGL','Alphabet'),
 ('AMZN','Amazon'),('JPM','JPMorgan Chase'),('BAC','Bank of America'),
 ('XOM','Exxon Mobil'),('CVX','Chevron'),('JNJ','Johnson & Johnson'),
 ('UNH','UnitedHealth Group'),('PG','Procter & Gamble'),('WMT','Walmart'),
 ('CAT','Caterpillar'),('NEE','NextEra Energy'),('DUK','Duke Energy'),
 ('PLD','Prologis'),('LIN','Linde'),('KO','Coca-Cola')]
AAER_ARCHIVE='https://www.sec.gov/enforcement-litigation/accounting-auditing-enforcement-releases'

def candidate_registry():
    rows=[]
    for ticker,name,num,date in LEADS:
        rows.append({'ticker_candidate':ticker,'name_candidate':name,'cohort_candidate':'AAER_INDEX_LEAD',
           'aaer_number':num,'aaer_release_date':date,'source_url':AAER_ARCHIVE})
    for ticker,name in CONTROLS:
        rows.append({'ticker_candidate':ticker,'name_candidate':name,'cohort_candidate':'UNLABELED_CONTROL_CANDIDATE',
           'aaer_number':'','aaer_release_date':'','source_url':''})
    result=pd.DataFrame(rows)
    for k in ('historical_cik_verified','original_10k_verified','original_aaer_order_verified',
              'misconduct_period_verified','financials_reconciled','delisting_returns_verified'):
        result[k]=False
    result['cik']=''
    result['security_id']=''
    result['reviewer']=''
    result['review_date']=''
    result['validation_status']='CANDIDATE_NOT_VERIFIED'
    assert len(result)==30 and result.ticker_candidate.nunique()==30
    return result

def audit_registry(df):
    if len(df)!=30 or df.ticker_candidate.nunique()!=30:
        raise ValueError('Registry must contain 30 unique candidate firms')
    required=['historical_cik_verified','original_10k_verified','financials_reconciled',
              'delisting_returns_verified']
    for r in required:
        if r not in df:raise ValueError('Missing '+r)
    good=df[required].astype(str).apply(lambda x:x.str.lower().eq('true')).all(axis=1)
    aaer=df.cohort_candidate.eq('AAER_INDEX_LEAD')
    for col in ('original_aaer_order_verified','misconduct_period_verified'):
        if col not in df:raise ValueError('Missing '+col)
        good &= (~aaer | df[col].astype(str).str.lower().eq('true'))
    good &= df['cik'].notna()&df['cik'].astype(str).str.len().gt(0)
    good &= df['reviewer'].notna()&df['reviewer'].astype(str).str.len().gt(0)
    return pd.DataFrame({'ticker_candidate':df.ticker_candidate,
                         'validated':good,'missing_manual_checks':~good})

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',default='pilot30')
    p.add_argument('--audit',help='Audit an edited pilot registry CSV')
    a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    if a.audit:
        result=audit_registry(pd.read_csv(a.audit))
        result.to_csv(out/'pilot_audit_report.csv',index=False)
        print('Validated candidates:',int(result.validated.sum()),'of',len(result))
        if not result.validated.all():raise SystemExit(2)
    else:
        candidate_registry().to_csv(out/'pilot_30_company_candidates.csv',index=False)
        print('Wrote 30 candidate firms; 0 validated')
if __name__=='__main__':main()
