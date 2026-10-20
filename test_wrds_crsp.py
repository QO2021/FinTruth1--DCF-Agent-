import pandas as pd
import pytest
from wrds_crsp import normalize_ciz_daily,daily_forward_returns,review_ticker_linkage

def test_ciz_returns_already_include_delisting():
    data=pd.DataFrame({'permno':[10,10], 'dlycaldt':['2020-01-02','2020-01-03'],
       'dlyret':[0.10,-0.50], 'dlydelflg':['N','Y']})
    out=normalize_ciz_daily(data)
    assert out.total_return.iloc[1]==-.5
    signal=pd.DataFrame([{'permno':10,'asof_date':'2020-01-01','signal':.6}])
    result=daily_forward_returns(data,signal,horizons=(2,))
    assert result.iloc[0].realized_total_return==pytest.approx((1.1*.5)-1)

def test_abstain_if_no_complete_horizon():
    prices=pd.DataFrame({'permno':[10],'dlycaldt':['2020-01-02'],'dlyret':[-.50]})
    s=pd.DataFrame([{'permno':10,'asof_date':'2020-01-01','signal':.6}])
    out=daily_forward_returns(prices,s,horizons=(5,))
    assert out.iloc[0].status=='INCOMPLETE_WINDOW_REVIEW'

def test_invalid_returns_rejected():
    with pytest.raises(ValueError):
        normalize_ciz_daily(pd.DataFrame({'permno':[10],'dlycaldt':['2020-01-02'],'dlyret':[-1.2]}))

def test_historical_linkage_not_autoverified():
    identities=pd.DataFrame({'permno':[10],'ticker':['ABC'],
       'namedt':['2000-01-01'],'nameenddt':['2020-12-31']})
    pilot=pd.DataFrame({'ticker_candidate':['ABC']})
    result=review_ticker_linkage(identities,pilot)
    assert result.iloc[0].verified == False
