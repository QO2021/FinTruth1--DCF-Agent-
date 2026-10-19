import pandas as pd
import pytest
from dcf import DCFInputs, value_dcf, sensitivity, value_csv
from fintruth import synthetic_example, integrate, Config

def example(**updates):
    row=pd.read_csv('dcf_example.csv').iloc[0].to_dict()
    row.update(updates)
    return DCFInputs(**row)

def test_classifications():
    v=value_dcf(example())['fair_value_per_share']
    assert value_dcf(example(market_price=v/1.3))['judgment']=='Undervalued'
    assert value_dcf(example(market_price=v))['judgment']=='Fairly valued'
    assert value_dcf(example(market_price=v/0.7))['judgment']=='Overvalued'

def test_monotonic_wacc():
    assert value_dcf(example(wacc=0.09))['fair_value_per_share']>value_dcf(example(wacc=0.11))['fair_value_per_share']

def test_bad_assumptions():
    with pytest.raises(ValueError): value_dcf(example(wacc=0.02,terminal_growth=0.03))

def test_integration():
    panel=synthetic_example(n_firms=25,n_dates=28)
    vals,_=value_csv('dcf_example.csv')
    vals['ticker']='DEMO000'; vals['asof_date']='2020-12-31'
    res=integrate(panel,Config(min_train_dates=12),vals)
    assert res.loc[res.ticker=='DEMO000','dcf_score'].notna().all()
    assert res.loc[res.ticker!='DEMO000','valuation_score'].isna().all()
