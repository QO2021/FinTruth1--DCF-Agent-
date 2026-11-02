"""WRDS/CRSP to SEC DCF bridge: point-in-time, fail-closed research utility.

No tokens, passwords, or licensed CRSP data are stored in this module.
The supported WRDS Python client authenticates locally via wrds.Connection().
Use this module with SEC accounting inputs that were independently audited.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from dcf import DCFInputs, value_dcf, sensitivity

ACCOUNTING = (
    "revenue", "operating_income", "tax_rate", "depreciation_amortization",
    "capital_expenditure", "change_nwc", "cash", "total_debt", "diluted_shares"
)
ASSUMPTIONS = ("risk_free_rate", "equity_risk_premium", "cost_of_debt",
               "target_debt_weight", "terminal_growth", "revenue_growth")


def estimate_market_beta(stock_returns, market_returns, asof_date,
                         min_observations=126, window=252):
    """CAPM OLS beta, using dates strictly BEFORE the valuation date.

    stock_returns: date, total_return (CRSP CIZ; already delisting inclusive).
    market_returns: date, market_return (a comparably timed, licensed series).
    """
    s=stock_returns[["date", "total_return"]].copy()
    m=market_returns[["date", "market_return"]].copy()
    s["date"]=pd.to_datetime(s.date)
    m["date"]=pd.to_datetime(m.date)
    if s.date.duplicated().any() or m.date.duplicated().any():
        raise ValueError("Duplicate return dates")
    joined=s.merge(m,on="date",validate="one_to_one").sort_values("date")
    joined=joined[joined.date<pd.Timestamp(asof_date)].tail(window)
    joined=joined.replace([np.inf,-np.inf],np.nan).dropna()
    if len(joined)<min_observations:
        raise ValueError("Insufficient strictly historical returns for beta")
    variance=float(joined.market_return.var(ddof=1))
    if variance<=0:raise ValueError("Market benchmark has zero variance")
    beta=float(joined.total_return.cov(joined.market_return)/variance)
    return {"beta":beta,"beta_observations":int(len(joined)),
            "beta_first_date":str(joined.date.min().date()),
            "beta_last_date":str(joined.date.max().date())}


def compute_wacc(risk_free_rate, equity_risk_premium, beta, cost_of_debt,
                 target_debt_weight, tax_rate):
    """CAPM cost of equity + after-tax cost of debt; inputs annual decimals."""
    values=[risk_free_rate,equity_risk_premium,beta,cost_of_debt,
            target_debt_weight,tax_rate]
    if not all(np.isfinite(float(v)) for v in values):
        raise ValueError("Nonfinite WACC component")
    if not (0<=target_debt_weight<=1 and 0<=tax_rate<=1):
        raise ValueError("Invalid capital structure or tax rate")
    if risk_free_rate < 0 or equity_risk_premium < 0 or cost_of_debt < 0:
        raise ValueError("Negative discount-rate components require explicit model revision")
    ke=float(risk_free_rate+beta*equity_risk_premium)
    kd=float(cost_of_debt)
    w=float(target_debt_weight)
    result=(1-w)*ke+w*kd*(1-tax_rate)
    if not (0<result<1):
        raise ValueError("DCF WACC must lie between 0 and 1")
    return {"cost_of_equity":ke,"cost_of_debt":kd,"debt_weight":w,"wacc":result}


def audit_inputs(financial, assumption, decision_date):
    """Reject data whose original publication timestamps or audits are missing."""
    decision=pd.Timestamp(decision_date)
    if pd.isna(decision):raise ValueError("Invalid decision date")
    for k in ACCOUNTING:
        if k not in financial or pd.isna(financial[k]):
            raise ValueError(f"Missing audited accounting input {k}")
        if str(financial.get(k+"_verified","")).lower() not in ("true","1"):
            raise ValueError(f"Not manually reconciled: {k}")
        timestamp=pd.to_datetime(financial.get(k+"_available_at"),errors="coerce")
        if pd.isna(timestamp) or timestamp>=decision:
            raise ValueError(f"Future/missing accounting availability: {k}")
    for k in ASSUMPTIONS:
        if k not in assumption or pd.isna(assumption[k]):
            raise ValueError(f"Missing historical assumption: {k}")
    if str(assumption.get("assumptions_verified","")).lower() not in ("true","1"):
        raise ValueError("Historical assumptions require documented approval")
    stamp=pd.to_datetime(assumption.get("available_at"),errors="coerce")
    if pd.isna(stamp) or stamp>=decision:
        raise ValueError("Future/missing WACC/growth assumption vintage")
    if not financial.get("source_accession") or not financial.get("source_url"):
        raise ValueError("Missing original SEC source accession/URL")
    if not assumption.get("assumption_source"):
        raise ValueError("Historical assumption source required")


def market_snapshot(crsp_daily, permno, decision_date):
    """Use latest observed nonzero CRSP unadjusted price strictly before decision.

    dlyprc is not a total-return-adjusted price. Its magnitude is used because
    historical CRSP conventions can use signed price markers.
    Security ID must already have been audited to the issuer and share class.
    """
    from wrds_crsp import normalize_ciz_daily
    data=normalize_ciz_daily(crsp_daily)
    if "dlyprc" not in data:
        raise ValueError("CRSP CIZ dlyprc absent; cannot determine historical price")
    x=data[(data.permno.astype(int)==int(permno))&
           (data.date<pd.Timestamp(decision_date))].sort_values("date")
    if x.empty:raise ValueError("No historical CRSP price before decision date")
    row=x.iloc[-1]
    price=abs(float(row.dlyprc))
    if not np.isfinite(price) or price<=0:raise ValueError("Invalid security price")
    return {"permno":int(permno),"price_date":str(row.date.date()),
            "market_price":price}


def historical_dcf(financial,assumption,crsp_daily,stock_returns,market_returns,
                   ticker,permno,decision_date):
    """One audited, company-specific historical DCF point estimate + stress grid.

    All amounts use identical monetary units and diluted shares in matching
    units. Results are *modeled*, not verified true intrinsic value.
    """
    audit_inputs(financial,assumption,decision_date)
    px=market_snapshot(crsp_daily,permno,decision_date)
    beta=estimate_market_beta(stock_returns,market_returns,decision_date)
    rates=compute_wacc(
        float(assumption["risk_free_rate"]),
        float(assumption["equity_risk_premium"]),
        beta["beta"],float(assumption["cost_of_debt"]),
        float(assumption["target_debt_weight"]),float(financial["tax_rate"])
    )
    inp=DCFInputs(
        ticker=ticker,asof_date=str(pd.Timestamp(decision_date).date()),
        revenue=float(financial["revenue"]),
        ebit_margin=float(financial["operating_income"])/float(financial["revenue"]),
        tax_rate=float(financial["tax_rate"]),
        depreciation_amortization=float(financial["depreciation_amortization"]),
        capital_expenditure=float(financial["capital_expenditure"]),
        change_nwc=float(financial["change_nwc"]),
        cash=float(financial["cash"]),
        total_debt=float(financial["total_debt"]),
        diluted_shares=float(financial["diluted_shares"]),
        market_price=px["market_price"],wacc=rates["wacc"],
        terminal_growth=float(assumption["terminal_growth"]),
        revenue_growth=float(assumption["revenue_growth"])
    )
    value=value_dcf(inp)
    value.update({"permno":int(permno),"price_date":px["price_date"],
                  "source_accession":financial["source_accession"],
                  "source_url":financial["source_url"],
                  "assumption_source":assumption["assumption_source"],
                  "historical_beta":beta["beta"],
                  "beta_observations":beta["beta_observations"],
                  "cost_of_equity":rates["cost_of_equity"],
                  "validation_status":"AUDITED_INPUTS_MODEL_ESTIMATE"})
    stress=sensitivity(inp)
    return value,stress


def save_result(value,stress,output):
    """Write modeled outputs only; never put licensed input market data in Git."""
    path=Path(output);path.mkdir(parents=True,exist_ok=True)
    summary={k:v for k,v in value.items() if k not in ("forecast","assumptions")}
    (path/"historical_dcf.json").write_text(json.dumps(
        {"summary":summary,"forecast":value["forecast"],
         "assumptions":value["assumptions"]},indent=2,default=str))
    stress.to_csv(path/"dcf_sensitivity.csv",index=False)
    return path


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--financial",required=True,help="Locally audited SEC inputs JSON")
    ap.add_argument("--assumptions",required=True,help="Historically sourced assumptions JSON")
    ap.add_argument("--crsp",required=True,help="Locally licensed CRSP CIZ CSV")
    ap.add_argument("--market-returns",required=True,help="Historical market returns CSV")
    ap.add_argument("--ticker",required=True)
    ap.add_argument("--permno",type=int,required=True)
    ap.add_argument("--asof",required=True)
    ap.add_argument("--output",default="local_dcf_results")
    a=ap.parse_args()
    financial=json.loads(Path(a.financial).read_text())
    assumptions=json.loads(Path(a.assumptions).read_text())
    crsp=pd.read_csv(a.crsp)
    if "permno" not in crsp:raise ValueError("CRSP file needs permno")
    crsp["permno"]=pd.to_numeric(crsp.permno,errors="raise")
    stock=crsp[crsp.permno==a.permno].copy()
    from wrds_crsp import normalize_ciz_daily
    stock=normalize_ciz_daily(stock)
    market=pd.read_csv(a.market_returns)
    value,stress=historical_dcf(financial,assumptions,stock,
                               stock[["date","total_return"]],market,
                               a.ticker,a.permno,a.asof)
    dest=save_result(value,stress,a.output)
    print(f'{value["ticker"]}: {value["judgment"]}; fair value/share '
          f'{value["fair_value_per_share"]:.2f} (modeled only)')
    print(f'Wrote model results to {dest}')


if __name__=="__main__":
    main()
