"""No-network tests for SEC/WRDS historical DCF bridge."""
import pandas as pd
import pytest
from dcf_wrds_bridge import (
    compute_wacc, estimate_market_beta, audit_inputs,
    market_snapshot, historical_dcf
)

def data():
    dates=pd.bdate_range('2023-01-02',periods=180)
    mr=pd.DataFrame({'date':dates,'market_return':[.001+(.01 if i%2 else -.01) for i in range(len(dates))]})
    sr=pd.DataFrame({'date':dates,'total_return':2*mr.market_return})
    crsp=pd.DataFrame({'permno': [10001]*len(dates),'dlycaldt':dates,
          'dlyret':sr.total_return,'dlyprc':[20]*len(dates)})
    asof='2023-10-01'
    fin={'ticker':'EXAMPLE','source_accession':'0000000000-23-000001',
         'source_url':'https://www.sec.gov/Archives/edgar/data/1/example',
         'revenue':1000.,'operating_income':180.,'tax_rate':.21,
         'depreciation_amortization':45.,'capital_expenditure':70.,
         'change_nwc':15.,'cash':120.,'total_debt':250.,
         'diluted_shares':100.}
    for k in ('revenue','operating_income','tax_rate','depreciation_amortization',
              'capital_expenditure','change_nwc','cash','total_debt','diluted_shares'):
        fin[k+'_verified']=True
        fin[k+'_available_at']='2023-02-20'
    ass={'risk_free_rate':.04,'equity_risk_premium':.05,
         'cost_of_debt':.06,'target_debt_weight':.20,
         'terminal_growth':.025,'revenue_growth':.06,
         'assumptions_verified':True,'available_at':'2023-09-29',
         'assumption_source':'Illustrative assumptions only'}
    return sr,mr,crsp,asof,fin,ass

def test_wacc_formula():
    z=compute_wacc(.04,.05,1.2,.06,.2,.21)
    assert z['wacc']==pytest.approx(.8*.10+.2*.06*(1-.21))

def test_beta_strictly_before_decision():
    sr,mr,*_=data()
    out=estimate_market_beta(sr,mr,'2023-10-01')
    assert out['beta']==pytest.approx(2)
    assert out['beta_last_date']<'2023-10-01'

def test_strict_historical_price():
    sr,mr,crsp,asof,fin,ass=data()
    price=market_snapshot(crsp,10001,asof)
    assert price['price_date']<'2023-10-01'
    assert price['market_price']==20

def test_reject_unverified_financial():
    *_,fin,ass=data()
    fin['revenue_verified']=False
    with pytest.raises(ValueError):
        audit_inputs(fin,ass,'2023-10-01')

def test_reject_future_assumption():
    *_,fin,ass=data()
    ass['available_at']='2023-10-02'
    with pytest.raises(ValueError):
        audit_inputs(fin,ass,'2023-10-01')

def test_historical_dcf_modeled():
    sr,mr,crsp,asof,fin,ass=data()
    result,grid=historical_dcf(fin,ass,crsp,sr,mr,'EXAMPLE',10001,asof)
    assert result['validation_status']=='AUDITED_INPUTS_MODEL_ESTIMATE'
    assert result['fair_value_per_share']>0
    assert len(grid)>0
