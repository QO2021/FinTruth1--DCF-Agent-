import pandas as pd
import pytest
from historical_pipeline import (match_ciks,filing_table,companyfacts_table,aaer_candidates,
                                 point_in_time_facts,audit_ledger,price_backtest)

def test_unknown_ticker_is_unmatched():
    known=pd.DataFrame([{'ticker':'AAA','cik':123,'title':'Example'}])
    matches=match_ciks(known,['AAA','UNKNOWN'])
    assert matches.iloc[0]['cik']==123
    assert pd.isna(matches.iloc[1]['cik'])

def test_filing_and_companyfacts_retain_accession_and_publication():
    filings={'filings':{'recent':{'form':['10-K'],'filingDate':['2020-02-15'],
      'accessionNumber':['000123-20-000001'],'primaryDocument':['report.htm'],
      'acceptanceDateTime':['2020-02-15T16:30:00'],'reportDate':['2019-12-31']}}}
    m=filing_table(filings,123)
    raw={'facts':{'us-gaap':{'NetIncomeLoss':{'units':{'USD':[
      {'form':'10-K','filed':'2020-02-15','accn':'000123-20-000001',
       'end':'2019-12-31','val':100}]}}}}}
    facts=companyfacts_table(raw,123)
    result=point_in_time_facts(facts,m,['2020-02-14','2020-02-16'])
    assert len(result)==1 and result.iloc[0]['value']==100
    assert result.iloc[0]['date']=='2020-02-16'

def test_aaer_is_unverified_candidate():
    html=b'<table><tr><td><a href="/test">Example AAER-4000</a></td></tr></table>'
    r=aaer_candidates(html)
    assert len(r)==1
    assert r.iloc[0]['status']=='CANDIDATE_MANUAL_REVIEW_REQUIRED'
    assert pd.isna(r.iloc[0]['company_cik'])

def test_audit_rejects_unverified():
    ledger=pd.DataFrame([{'cik':1,'accession':'X','filing_date':'2020-01-01',
        'period_end':'2019-12-31','source_url':'https://www.sec.gov/test',
        'checked_by':'Researcher','checked_at':'2026-10-19','reconciled':False,'sha256':'abc'}])
    assert audit_ledger(ledger)['pass'] is False

def test_next_day_backtest():
    sig=pd.DataFrame([{'ticker':'AAA','asof_date':'2020-01-02','signal':.7}])
    prices=pd.DataFrame({'ticker':['AAA']*3,
      'date':['2020-01-02','2020-01-03','2020-01-06'],
      'adjusted_close':[10,11,12]})
    r=price_backtest(sig,prices,horizons=(1,))
    assert r.iloc[0].entry_date==pd.Timestamp('2020-01-03')
    assert r.iloc[0]['forward_1d']==pytest.approx(12/11-1)
