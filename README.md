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
