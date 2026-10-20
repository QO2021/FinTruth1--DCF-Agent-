# FinTruth I — DCF Integrated Research Agents

Research prototype integrating **Fundamental Valuation**, **Financial Disclosure Credibility**, and **Equity Return Predictability** for U.S. equities. The DCF module uses FCFF to estimate per-share intrinsic value and classify securities as **Undervalued**, **Fairly valued**, or **Overvalued** with a configurable 10% margin-of-safety band.

## Installation

```bash
python -m pip install -r requirements.txt
pytest -q
```

## DCF demo (illustrative values only)

```bash
python -c "from dcf import value_csv; d,_=value_csv('dcf_example.csv'); print(d.to_string(index=False))"
```

The CSV must contain as-of date, revenues, EBIT margin, tax rate, depreciation and amortization, capital expenditures, change in working capital, cash, debt, diluted shares, market price, WACC, terminal growth and revenue growth. All financial values must use consistent currency units.

## Three-agent demonstration

```bash
python fintruth.py --demo --dcf-input dcf_example.csv --output demo_results
```

**Important:** The DCF example ticker is EXAMPLE, whereas the synthetic demo tickers are DEMO000, etc.; accordingly, this command outputs a standalone EXAMPLE DCF valuation but **does not attach that DCF to demo-company scoring**. Use matching tickers and appropriately dated DCF assumptions when working with an actual financial panel.

## Real input panel

```bash
python fintruth.py --input your_point_in_time_panel.csv --dcf-input your_dcf_assumptions.csv --output results
```

Required daily panel fields: `date,ticker,available_at,adjusted_close,fcf_yield,earnings_yield,gross_margin,roe,debt_to_assets,accruals_to_assets,revenue_growth,cash_conversion,filing_delay_days,restatement_known,text_uncertainty,text_inconsistency`.

- **Valuation Agent**: Cross-sectional ratio ranking and optional DCF; when supplied, 50% relative fundamentals and 50% DCF signal.
- **Credibility Agent**: Supplied accounting and narrative-warning proxies. Not a fraud probability and not yet an automated SEC filing / AAER reader.
- **Predictability Agent**: Ridge expanding-window supervised forecasting of 5-trading-day forward adjusted returns with matured historical targets only.
- **Integration**: Illustrative 40% valuation, 30% credibility, 30% predictability, with no integrated score when any required component is missing. These weights are **research hypotheses** rather than fitted/calibrated values.

DCF per-share value is derived from discounted five-year forecast FCFF plus terminal value, adjusted for cash and debt and divided by diluted shares. The model assumes constant revenue growth, margins, forecast cash-flow ratios, WACC and terminal growth. A 10% DCF margin band determines the three-way classification.

Outputs include `integrated_scores.csv`, `metrics.json`, `dcf_valuations.csv` and `dcf_audit.json`. Data and forecasts must be constructed *point-in-time*: never backfill SEC restatements, AAER findings or future information. Sample data in this repository are illustrative, **not live SEC/AAER/price data and not tested investment recommendations**. The implementation does not automatically fetch market or SEC information. Before publication, add point-in-time SEC/AAER data collection, delisting coverage, financial assumptions validation, out-of-sample ablation tests, risk calibration and uncertainty estimates.

## Academic research notes

- A negative DCF modeled equity value is not a literal negative trading price; it indicates model and liability assumptions require careful interpretation.
- DCF terminal value and WACC assumptions can dominate estimated equity value; use `sensitivity()` in `dcf.py`.
- The combined score is a relative ranking, **not** a calibrated probability that a stock rises.
- Model evaluation against synthetic data is a software demonstration, not an empirical U.S.-equities result.


## Automated Summary Report (v0.3)

Every pipeline run now generates:
- `summary_report.md`: readable executive summary and company-by-company DCF, fundamental, credibility, predictability and weighted assessments.
- `summary_report.json`: structured summaries suitable for downstream analysis.

Run the synthetic software demonstration:

```bash
python fintruth.py --demo --output demo_results
```

Or supply point-in-time financial panels and DCF assumptions:

```bash
python fintruth.py --input your_point_in_time_panel.csv --dcf-input your_dcf_assumptions.csv --output results
```

Generate a report independently from previous results:

```bash
python report.py --scores results/integrated_scores.csv --dcf results/dcf_valuations.csv --metrics results/metrics.json --output results
```

If no DCF file exists, omit `--dcf`. The report will explicitly state that valuation information is unavailable rather than fabricate it. If the full three-agent composite is unavailable, the reporting engine abstains. Example output is **not an empirical investment recommendation**.

Run the report tests alongside the valuation tests:

```bash
pytest -q
```


## Historical SEC/AAER Evidence Pipeline

See [HISTORICAL_DATA.md](HISTORICAL_DATA.md) for compliant SEC EDGAR downloading, historical filing provenance, raw AAER index candidates, CIK matching, manually reviewed 20–30-company pilot registry, data-quality audit, and point-in-time backtesting interface. **The pilot has not yet been populated or validated.**

```bash
python historical_pipeline.py init-pilot --output pilot
# Set SEC_USER_AGENT before live data downloads; see HISTORICAL_DATA.md
python historical_pipeline.py collect --tickers AAPL,MSFT,JPM,GE --start 2005-01-01 --end 2025-12-31 --output sec_research
pytest -q
```


## WRDS / CRSP CIZ data integration

See [WRDS_CRSP.md](WRDS_CRSP.md) for read-only CRSP CIZ (v2) download using user-managed WRDS credentials, audited PERMNO linkage, delisting-inclusive daily returns, and local-only licensed outputs.

```bash
pip install wrds
python wrds_crsp.py --inspect --out local_crsp_private
# Only after verifying security identifiers:
python wrds_crsp.py --permnos 14593,10107 --out local_crsp_private
```

Do **not** publish licensed CRSP data or WRDS credentials. CRSP CIZ daily returns include delisting; never add a separate legacy DLRET. No full 30-company empirical dataset has been validated yet.
