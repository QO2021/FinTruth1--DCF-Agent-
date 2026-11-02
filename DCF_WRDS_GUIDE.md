# FinTruth I — WRDS/CRSP-linked Historical DCF

**Status:** implementation and unit-test fixtures committed; no authenticated WRDS
data has been fetched during this development session, and no real SEC filings
have been manually reconciled by this module. Do **not** interpret sample output
as published empirical evidence.

## Important: API credentials

A credential appeared in a chat message. **Rotate/revoke it in WRDS before
further use**, and store the replacement only in your local secret manager.
Do not save an API token in source code, a README, notebook, CSV, prompt, or
GitHub Actions secret unless you have explicitly chosen and configured a secure
workflow. The code here does not consume, embed, or transmit that token.

WRDS documents Python access using the `wrds` Python client and account-based
authentication. The `https://wrds-api.wharton.upenn.edu/` endpoint may expose
other interfaces, but no guessed token header or undocumented URL is used here.
Use official WRDS instructions for the API key. You can request WRDS technical
support if your account uses a different web API flow.

## Pipeline design

1. **SEC**: obtain the original 10-K/10-Q accession and accounting context;
   manually reconcile and preserve the original publication timestamp.
2. **Issuer–security bridge**: verify issuer CIK to historical CRSP PERMNO and
   share class, with date-effective mappings. Historical ticker alone is not sufficient.
3. **CRSP CIZ**: download `DlyRet`, `DlyPrc` for audited PERMNOs
   (license-controlled data remain on your own computer).
4. **Market benchmark**: source a consistent historical total-return series.
   Use observations before the valuation timestamp for historical OLS beta.
5. **WACC**: CAPM cost of equity (risk-free rate + beta × equity risk premium),
   blended with after-tax cost of debt using a documented target debt weight.
6. **FCFF DCF**: use reconciled revenue, operating income, tax rate, D&A, CapEx,
   change in net working capital, cash, debt, diluted shares, and historical
   market price. Run WACC/terminal-growth sensitivity and produce a judgment.
7. **Research**: combine DCF with credibility and predictability agents only
   after timestamp and data checks. Do not use eventual AAER releases as earlier
   predictors. All modeling assumptions are contestable and should be evaluated
   with alternative assumptions and a pre-registered out-of-sample protocol.

## Commands (Windows PowerShell)

```powershell
git clone https://github.com/QO2021/FinTruth1--DCF-Agent-.git
cd FinTruth1--DCF-Agent-
python -m pip install -r requirements.txt
python -m pip install wrds
pytest -q
python wrds_crsp.py --inspect --out local_crsp_private
```

Use your authenticated, locally configured WRDS account for the command above.
The CRSP extract requires **manually verified PERMNOs**:

```powershell
python wrds_crsp.py --permnos 14593,10107 --start 2005-01-01 --end 2025-12-31 --out local_crsp_private
```

These PERMNOs are examples only; they are not automatically certified for the
30-company research sample. Keep WRDS-licensed data in `local_crsp_private/`.

## Run DCF with locally audited inputs

Prepare two local JSON files:
- `local_financial.json`: source_accession, source_url, and the fields
  `revenue`, `operating_income`, `tax_rate`, `depreciation_amortization`,
  `capital_expenditure`, `change_nwc`, `cash`, `total_debt`,
  `diluted_shares`. For *every* metric provide `<metric>_verified: true`
  and `<metric>_available_at` (publication timestamp).
- `local_assumptions.json`: risk_free_rate, equity_risk_premium, cost_of_debt,
  target_debt_weight, terminal_growth, revenue_growth, `assumptions_verified:
  true`, `available_at`, `assumption_source`. These are dated research
  assumptions, not objective financial-statement facts.

Prepare `local_market_returns.csv` with `date,market_return`. Use the
appropriate licensed historic market return series; do not mix price return and
total return conventions.

```powershell
python dcf_wrds_bridge.py --financial local_financial.json --assumptions local_assumptions.json --crsp local_crsp_private/ciz_daily_private.csv --market-returns local_market_returns.csv --ticker YOUR_TICKER --permno YOUR_VERIFIED_PERMNO --asof 2020-03-02 --output local_dcf_results
```

The market data CSV needs `permno,dlycaldt,dlyret,dlyprc` (available in the
WRDS adapter if the CIZ table exposes them). The DCF bridge refuses missing
audits, missing timestamps, future-dated inputs and insufficient beta history.
Outputs: `historical_dcf.json` and `dcf_sensitivity.csv`.

## Limitations and warnings

- CRSP CIZ total returns already include delisting adjustments; do not append
  a separate legacy delisting return.
- CIZ `DlyPrc` is an unadjusted historical price indicator, not a
  total-return index; signed prices may carry CRSP price convention.
- A 252-day regression beta can be unstable, especially for distressed,
  short-history or delisted issuers; benchmark and estimates require scrutiny.
- Historical WACC and growth forecasts are not recoverable objectively
  from annual SEC statements; maintain a documented vintage of assumptions.
- Per-share valuations require consistent monetary and shares units, and may
  need adjustments for preferred stock, minority interests, leases, option
  dilution, excess cash and nonoperating assets.
- A fixed-growth FCFF model may be inappropriate for financial institutions.
  Use sector-appropriate valuation, such as excess-return / dividend models,
  instead of a generic enterprise FCFF DCF.
- The 10% valuation classification is an exploratory threshold, not empirical
  proof of mispricing.
- Do not publish licensed CRSP extracts or credentials to a public GitHub repo.

## Verification

```powershell
pytest -q test_dcf_wrds_bridge.py
```

Tests use *artificial fixtures*, not authenticated WRDS data or validated SEC
historical values.
