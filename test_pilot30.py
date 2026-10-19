import pandas as pd
import pytest
from pilot30 import candidate_registry,audit_registry
from validation import reconcile_financial_records,delisting_aware_backtest,audited_dcf

def test_30_unique_candidates_and_zero_verified():
    df=candidate_registry()
    assert len(df)==30 and df.ticker_candidate.nunique()==30
    assert audit_registry(df).validated.sum()==0

def test_unverified_fundamentals_rejected():
    with pytest.raises(ValueError):
        reconcile_financial_records(pd.DataFrame([{'cik':1}]),pd.DataFrame())

def test_unaudited_dcf_rejected():
    with pytest.raises(ValueError):
        audited_dcf({'ticker':'EXAMPLE'},{})

def test_missing_delisting_return_rejected():
    p=pd.DataFrame([{'permno':1,'date':'2020-01-02','ret':-0.2,'dlret':None,'delisting_event':True}])
    s=pd.DataFrame([{'permno':1,'asof_date':'2020-01-01','signal':.7}])
    r=delisting_aware_backtest(p,s,horizons=(1,))
    assert r.iloc[0]['status']=='ABSTAIN_MISSING_OR_DELISTED'

def test_delisting_compounded():
    p=pd.DataFrame([{'permno':1,'date':'2020-01-02','ret':-.2,'dlret':-.5,'delisting_event':True}])
    s=pd.DataFrame([{'permno':1,'asof_date':'2020-01-01','signal':.7}])
    r=delisting_aware_backtest(p,s,horizons=(1,))
    assert r.iloc[0]['return']==pytest.approx(-.6)
