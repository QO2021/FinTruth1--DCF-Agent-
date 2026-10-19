"""FinTruth I: auditable FCFF discounted-cash-flow valuation module.
All monetary values must use the SAME currency units; share count in corresponding units.
No market-data or SEC retrieval is performed here.
"""
from dataclasses import dataclass, asdict
import math
import pandas as pd

@dataclass(frozen=True)
class DCFInputs:
    ticker: str
    asof_date: str
    revenue: float
    ebit_margin: float
    tax_rate: float
    depreciation_amortization: float
    capital_expenditure: float
    change_nwc: float
    cash: float
    total_debt: float
    diluted_shares: float
    market_price: float
    wacc: float
    terminal_growth: float
    revenue_growth: float
    forecast_years: int = 5
    margin_of_safety: float = 0.10
    # Forecast ratios of annual revenue; D&A and capex default to base-year / base revenue.
    da_ratio: float | None = None
    capex_ratio: float | None = None
    nwc_ratio: float | None = None

    def validate(self):
        numeric = [v for k,v in asdict(self).items() if isinstance(v,(int,float)) and not isinstance(v,bool)]
        if not all(math.isfinite(float(v)) for v in numeric): raise ValueError('All inputs must be finite')
        if self.revenue <= 0 or self.diluted_shares <= 0 or self.market_price <= 0: raise ValueError('Revenue, shares and market price must be positive')
        if not (0 < self.wacc < 1 and -0.05 <= self.terminal_growth < self.wacc): raise ValueError('Require 0 < WACC < 1 and -5% <= terminal growth < WACC')
        if not (0 <= self.tax_rate <= 1 and -1 < self.revenue_growth < 2): raise ValueError('Invalid tax or revenue growth')
        if not (1 <= self.forecast_years <= 20 and 0 <= self.margin_of_safety < 1): raise ValueError('Invalid horizon or margin of safety')
        if self.total_debt < 0 or self.cash < 0 or self.depreciation_amortization < 0 or self.capital_expenditure < 0: raise ValueError('Negative debt/cash/DA/capex')
        for k in ('da_ratio','capex_ratio','nwc_ratio'):
            v=getattr(self,k)
            if v is not None and abs(v)>5: raise ValueError(f'Unreasonable {k}')


def value_dcf(x: DCFInputs) -> dict:
    x.validate()
    da_ratio = x.da_ratio if x.da_ratio is not None else x.depreciation_amortization/x.revenue
    capex_ratio = x.capex_ratio if x.capex_ratio is not None else x.capital_expenditure/x.revenue
    nwc_ratio = x.nwc_ratio if x.nwc_ratio is not None else x.change_nwc/x.revenue
    forecast=[]; revenue=x.revenue
    for year in range(1,x.forecast_years+1):
        revenue *= 1+x.revenue_growth
        ebit=revenue*x.ebit_margin
        nopat=ebit - max(ebit,0)*x.tax_rate  # no assumed tax benefit for negative EBIT
        fcff=nopat+revenue*da_ratio-revenue*capex_ratio-revenue*nwc_ratio
        pv=fcff/(1+x.wacc)**year
        forecast.append({'year':year,'revenue':revenue,'ebit':ebit,'fcff':fcff,'pv_fcff':pv})
    terminal_fcff=forecast[-1]['fcff']*(1+x.terminal_growth)
    terminal_value=terminal_fcff/(x.wacc-x.terminal_growth)
    enterprise_value=sum(z['pv_fcff'] for z in forecast)+terminal_value/(1+x.wacc)**x.forecast_years
    equity_value=enterprise_value+x.cash-x.total_debt
    fair_value_per_share=equity_value/x.diluted_shares
    upside=fair_value_per_share/x.market_price-1
    if fair_value_per_share <= 0:
        judgment='Overvalued (nonpositive modeled equity value)'
    elif upside > x.margin_of_safety:
        judgment='Undervalued'
    elif upside < -x.margin_of_safety:
        judgment='Overvalued'
    else:
        judgment='Fairly valued'
    return {'ticker':x.ticker,'asof_date':x.asof_date,'market_price':x.market_price,
            'fair_value_per_share':fair_value_per_share,'upside_pct':100*upside,
            'judgment':judgment,'enterprise_value':enterprise_value,'equity_value':equity_value,
            'pv_terminal_value':terminal_value/(1+x.wacc)**x.forecast_years,
            'terminal_value_fraction':(terminal_value/(1+x.wacc)**x.forecast_years)/enterprise_value if enterprise_value else None,
            'forecast':forecast,'assumptions':asdict(x)}


def sensitivity(x: DCFInputs, wacc_shifts=(-0.02,0,0.02), g_shifts=(-0.01,0,0.01)) -> pd.DataFrame:
    from dataclasses import replace
    rows=[]
    for dw in wacc_shifts:
        for dg in g_shifts:
            w=x.wacc+dw; g=x.terminal_growth+dg
            if w<=g or w<=0: continue
            res=value_dcf(replace(x,wacc=w,terminal_growth=g))
            rows.append({'wacc':w,'terminal_growth':g,'fair_value_per_share':res['fair_value_per_share'],
                         'upside_pct':res['upside_pct'],'judgment':res['judgment']})
    return pd.DataFrame(rows)


def value_csv(path: str):
    data=pd.read_csv(path)
    required=set(DCFInputs.__dataclass_fields__)-{'forecast_years','margin_of_safety','da_ratio','capex_ratio','nwc_ratio'}
    if not required.issubset(data.columns): raise ValueError(f'Missing DCF inputs: {sorted(required-set(data.columns))}')
    outputs=[]
    for row in data.to_dict('records'):
        kwargs={k:v for k,v in row.items() if k in DCFInputs.__dataclass_fields__ and pd.notna(v)}
        outputs.append(value_dcf(DCFInputs(**kwargs)))
    return pd.DataFrame([{k:v for k,v in r.items() if k not in ('forecast','assumptions')} for r in outputs]),outputs
