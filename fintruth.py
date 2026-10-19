"""FinTruth I: integrated, auditable three-agent research prototype.
Research software, not investment advice. No empirical claims until real data validation.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error

FUNDAMENTALS = ['fcf_yield','earnings_yield','gross_margin','roe','debt_to_assets','accruals_to_assets','revenue_growth']
CREDIBILITY = ['accruals_to_assets','cash_conversion','filing_delay_days','restatement_known','text_uncertainty','text_inconsistency']
# Fixed ex-ante directions. Higher values are always more favorable after orientation.
DIRECTION = {'fcf_yield':1,'earnings_yield':1,'gross_margin':1,'roe':1,'debt_to_assets':-1,
             'accruals_to_assets':-1,'revenue_growth':1,'cash_conversion':1,
             'filing_delay_days':-1,'restatement_known':-1,'text_uncertainty':-1,
             'text_inconsistency':-1}

@dataclass(frozen=True)
class Config:
    valuation_weight: float = 0.40
    credibility_weight: float = 0.30
    predictability_weight: float = 0.30
    min_train_dates: int = 12
    retrain_every_dates: int = 1
    horizon_days: int = 5
    def __post_init__(self):
        ws=(self.valuation_weight,self.credibility_weight,self.predictability_weight)
        if any(x < 0 for x in ws) or not np.isclose(sum(ws),1):
            raise ValueError('Weights must be nonnegative and sum to 1')
        if self.horizon_days < 1 or self.min_train_dates < 2 or self.retrain_every_dates < 1:
            raise ValueError('Invalid time settings')


def check_panel(df:pd.DataFrame):
    required={'date','ticker','available_at','adjusted_close'} | set(FUNDAMENTALS) | set(CREDIBILITY)
    missing=required-set(df.columns)
    if missing: raise ValueError(f'Missing columns: {sorted(missing)}')
    if df.duplicated(['ticker','date']).any(): raise ValueError('Duplicate ticker/date rows')
    d=df.copy()
    d['date']=pd.to_datetime(d.date)
    d['available_at']=pd.to_datetime(d.available_at)
    if d[['date','ticker','adjusted_close']].isna().any().any():
        raise ValueError('date/ticker/adjusted_close cannot be null')
    if (d.adjusted_close <= 0).any(): raise ValueError('Prices must be positive')
    # At close-of-day decision time, only information released before that date is allowed.
    if (d.available_at.dt.normalize() > d.date.dt.normalize()).any():
        raise ValueError('Look-ahead: some features became available after their decision date')
    return d.sort_values(['ticker','date']).reset_index(drop=True)

class FundamentalValuationAgent:
    """Relative fundamental attractiveness, not an intrinsic DCF valuation."""
    features=['fcf_yield','earnings_yield','gross_margin','roe','debt_to_assets','revenue_growth']
    def score(self,d): return percentile_composite(d,self.features)

class DisclosureCredibilityAgent:
    """Accounting/text warning-sign proxy; not fraud probability or verified LLM output."""
    features=CREDIBILITY
    def score(self,d): return percentile_composite(d,self.features)


def percentile_composite(d, features):
    """Within-date cross-sectional ranks, missing values excluded (no invented neutral score)."""
    cols=[]
    for name in features:
        oriented=pd.to_numeric(d[name],errors='coerce') * DIRECTION[name]
        # A single observed firm cannot be ranked meaningfully.
        ranked=oriented.groupby(d['date']).transform(lambda x: x.rank(pct=True) if x.notna().sum()>1 else x* np.nan)
        cols.append(ranked)
    frame=pd.concat(cols,axis=1)
    valid=frame.notna().sum(axis=1)
    result=frame.mean(axis=1)
    result[valid < max(2,int(np.ceil(len(features)*0.5)))]=np.nan
    return result.clip(0,1)

class ReturnPredictabilityAgent:
    """Expanding-window supervised return forecasts; strictly matured labels only."""
    features=FUNDAMENTALS + [x for x in CREDIBILITY if x not in FUNDAMENTALS]
    def predict(self,d,cfg):
        out=pd.Series(np.nan,index=d.index,dtype=float)
        dates=sorted(d.date.unique())
        for idx in range(cfg.min_train_dates,len(dates)):
            if (idx-cfg.min_train_dates)%cfg.retrain_every_dates: continue
            test_date=dates[idx]
            # label_end is the date at which a forward return is fully observed.
            train=d[(d.date < test_date)&(d.label_end < test_date)&d.target_return.notna()]
            test=d[d.date==test_date]
            if len(train)<max(20,len(self.features)*2): continue
            model=Pipeline([('impute',SimpleImputer(strategy='median',add_indicator=False)),
                            ('scale',StandardScaler()),('regression',Ridge(alpha=20.0))])
            model.fit(train[self.features],train.target_return)
            out.loc[test.index]=model.predict(test[self.features])
        # If retraining less frequently, leave skipped dates missing rather than backfill predictions.
        return out


def add_forward_returns(d,h):
    d=d.sort_values(['ticker','date']).copy()
    g=d.groupby('ticker',sort=False)
    d['target_return']=g.adjusted_close.shift(-h)/d.adjusted_close-1
    d['label_end']=g.date.shift(-h)
    return d


def integrate(panel,cfg=Config(),dcf_results=None):
    d=add_forward_returns(check_panel(panel),cfg.horizon_days)
    d['valuation_score']=FundamentalValuationAgent().score(d)
    if dcf_results is not None:
        # An intrinsic valuation estimate can only be used after its as-of date.
        # Input CSV should contain assumptions computed from publicly available data.
        v=dcf_results.copy()
        v['asof_date']=pd.to_datetime(v['asof_date'])
        v=v.sort_values(['asof_date','ticker'])
        if v.duplicated(['ticker','asof_date']).any():
            raise ValueError('Duplicate DCF ticker/asof_date')
        d=d.sort_values(['date','ticker']).reset_index(drop=True)
        d=pd.merge_asof(d,v[['ticker','asof_date','upside_pct','fair_value_per_share','judgment']].sort_values('asof_date'),
                        left_on='date',right_on='asof_date',by='ticker',direction='backward')
        # Map DCF upside to [0,1] with 0.5 = fairly valued, +/-50% saturation.
        d['dcf_score']=(0.5+d['upside_pct']/100).clip(0,1)
        d['relative_fundamental_score']=d['valuation_score']
        # Blend only when both scores exist; do not silently invent missing DCF.
        d['valuation_score']=0.5*d['relative_fundamental_score']+0.5*d['dcf_score']

    d['credibility_score']=DisclosureCredibilityAgent().score(d)
    d['predicted_return']=ReturnPredictabilityAgent().predict(d,cfg)
    # Cross-sectional ranking uses only same-date predictions, not realized future returns.
    d['predictability_score']=d.groupby('date').predicted_return.transform(
        lambda x: x.rank(pct=True) if x.notna().sum()>1 else x*np.nan)
    weights={'valuation_score':cfg.valuation_weight,'credibility_score':cfg.credibility_weight,
             'predictability_score':cfg.predictability_weight}
    for key in weights: d[key]=pd.to_numeric(d[key],errors='coerce')
    d['combined_score']=sum(d[k].fillna(0)*v for k,v in weights.items())
    # No renormalization on missing components: avoid overstating incomplete evidence.
    complete=d[list(weights)].notna().all(axis=1)
    d.loc[~complete,'combined_score']=np.nan
    d['conclusion']=pd.cut(d.combined_score,[-0.001,0.4,0.6,1.001],
                           labels=['Low combined evidence','Mixed / neutral','High combined evidence'])
    return d


def evaluate(result):
    d=result.dropna(subset=['predicted_return','target_return'])
    if len(d)<5: return {'n':len(d),'status':'insufficient completed out-of-sample predictions'}
    # Benchmark: unconditional zero return. Not a claim of economic profitability.
    mse=mean_squared_error(d.target_return,d.predicted_return)
    baseline=mean_squared_error(d.target_return,np.zeros(len(d)))
    return {'n':len(d),'mse':float(mse),'zero_return_benchmark_mse':float(baseline),
            'oos_r2_vs_zero':float(1-mse/baseline) if baseline>0 else None,
            'rank_ic':float(d.predicted_return.corr(d.target_return,method='spearman'))}


def synthetic_example(n_firms=30,n_dates=48,seed=7):
    """Artificial demonstration only; NOT actual SEC, AAER, or market observations."""
    rng=np.random.default_rng(seed)
    dates=pd.bdate_range('2021-01-04',periods=n_dates)
    rows=[]
    for t in range(n_firms):
        ticker=f'DEMO{t:03d}'
        px=50+rng.random()*50
        quality=rng.normal()
        for dt in dates:
            features={
                'fcf_yield':0.04+0.03*quality+rng.normal(0,.025),
                'earnings_yield':0.06+0.03*quality+rng.normal(0,.02),
                'gross_margin':0.35+0.07*quality+rng.normal(0,.06),
                'roe':0.12+0.04*quality+rng.normal(0,.04),
                'debt_to_assets':0.4-0.04*quality+rng.normal(0,.05),
                'accruals_to_assets':0.02-0.015*quality+rng.normal(0,.02),
                'revenue_growth':0.08+0.025*quality+rng.normal(0,.05),
                'cash_conversion':1+0.15*quality+rng.normal(0,.15),
                'filing_delay_days':60-3*quality+rng.normal(0,5),
                'restatement_known':int(rng.random()<0.04),
                'text_uncertainty':0.25-0.04*quality+rng.normal(0,.04),
                'text_inconsistency':0.15-0.025*quality+rng.normal(0,.035)}
            rows.append({'date':dt,'ticker':ticker,'available_at':dt-pd.Timedelta(days=1),
                         'adjusted_close':px,**features})
            px*=np.exp(0.0004+0.001*quality+rng.normal(0,.02))
    return pd.DataFrame(rows)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--input',help='CSV of point-in-time feature panel')
    p.add_argument('--dcf-input',help='Optional CSV of point-in-time DCF assumptions')
    p.add_argument('--demo',action='store_true',help='Use synthetic data; NEVER interpret as empirical evidence')
    p.add_argument('--output',default='results')
    p.add_argument('--valuation-weight',type=float,default=.4)
    p.add_argument('--credibility-weight',type=float,default=.3)
    p.add_argument('--predictability-weight',type=float,default=.3)
    a=p.parse_args()
    if not a.demo and not a.input: p.error('Supply --input real_panel.csv or --demo')
    cfg=Config(valuation_weight=a.valuation_weight,credibility_weight=a.credibility_weight,
               predictability_weight=a.predictability_weight)
    data=synthetic_example() if a.demo else pd.read_csv(a.input)
    dcf_results=None
    if a.dcf_input:
        from dcf import value_csv
        dcf_results,dcf_details=value_csv(a.dcf_input)
    result=integrate(data,cfg,dcf_results)
    out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    result.to_csv(out/'integrated_scores.csv',index=False)
    if dcf_results is not None:
        dcf_results.to_csv(out/'dcf_valuations.csv',index=False)
        import json
        (out/'dcf_audit.json').write_text(json.dumps(dcf_details,indent=2,default=str))
    metrics=evaluate(result)
    import json
    (out/'metrics.json').write_text(json.dumps({'data_type':'SYNTHETIC DEMO' if a.demo else 'USER-SUPPLIED',
                  'weights':{'valuation':cfg.valuation_weight,'credibility':cfg.credibility_weight,
                             'predictability':cfg.predictability_weight},'metrics':metrics},indent=2))
    print((out/'metrics.json').read_text())
    print(f'Saved {out / "integrated_scores.csv"}')
if __name__=='__main__': main()
