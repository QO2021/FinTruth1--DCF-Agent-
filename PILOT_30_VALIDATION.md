# FinTruth I — First 30-Company Historical Validation Pilot

**Current status: 30 candidate companies, 0 fully validated.**

The roster is a proposed sampling frame, not a statement that any company
committed accounting fraud or that any comparison company is misconduct-free.
The 12 AAER-number/name associations are *research leads requiring independent
confirmation against the original SEC archive and enforcement orders.*
Ticker identities, company names and AAER numbers require manual verification.

## Research period

2005-01-01 to 2025-12-31 (historical data). Use the original filing acceptance
timestamp and only information available *strictly before* each decision date.

## Install and prepare the pilot

```bash
pip install -r requirements.txt
python pilot30.py --output pilot30
```

This produces `pilot30/pilot_30_company_candidates.csv`. Edit it using
documented original 10-Ks, SEC accession IDs, source URLs and human audit
signoff. You must manually verify identifiers and historical ticker changes.
The `pilot30.py --audit pilot30/pilot_30_company_candidates.csv` command
fails until every required gate is independently verified.

## Retrieve SEC metadata and original annual filings

Set `SEC_USER_AGENT` to a valid identifying organization and actual contact
email. Follow SEC fair-access rules and do not publicly commit cached raw files.

```bash
python historical_pipeline.py collect --tickers AAPL,MSFT,JPM,GE --start 2005-01-01 --end 2025-12-31 --output sec_research
```

`historical_pipeline.py` collects submissions data and US-GAAP facts.
For original filing documents use `aaer_archive.download_evidence(client,urls,out)`,
supplying actual SEC `primary_document_url` values from the filing manifest,
then reconcile original financial-statement context, scaling, fiscal duration and
amendments. Automated extraction alone does not complete this human audit.

## Crawl AAER archive pages across 2005–2025

```bash
python aaer_archive.py --start 2005 --end 2025 --output aaer_research --download-documents
```

This walks visible pagination links for year-filtered archive pages. **Completeness
is not assumed:** inspect `aaer_research/crawl_coverage.csv` for errors and
year-filter navigation failures; SEC may modify archive pagination or block
requests. Check archive year and case counts against a manually reviewed index.
The archive is not exhaustive of every relevant enforcement action.

Do not use AAER release dates, allegations, or later-discovered accounting
misconduct as predictors at earlier dates. Document alleged conduct period,
original SEC order URL, issuer CIK, release time, case disposition and whether
findings are allegations, admissions or adjudications.

## Validate financial facts and DCF

`validation.py` offers:
- `reconcile_financial_records(extracted_facts, human_audit_ledger)`
- `audited_dcf(verified_company_snapshot, dated_model_assumptions)`
- `delisting_aware_backtest(licensed_security_returns, signals)`

DCF is **blocked** if any required original financial metric is not reconciled
or discount-rate and growth assumptions were not available and verified at
the model's as-of date. DCF is a scenario-based estimate, not objectively
verified intrinsic value.

## Delisted equities

Use a defensible security-history dataset (ideally WRDS/CRSP if the researcher
has institutional access), tracking PERMNO, PERMCO, exchange/listing periods,
ret and dlret, and licensed usage terms. The software **does not** access
WRDS/CRSP without your own access or substitute present-day Yahoo constituents.
Audit delisting adjustments. If delisting returns are missing, model abstains.

## Publication-grade validation thresholds

- 30 unique firms with verified issuer/security histories and source document
  provenance.
- Enforcement cohort original orders reviewed, coded by allegations and outcomes.
- Financial metrics reconciled with original context and cash-flow identities.
- Point-in-time histories, including vintage and amendment dates.
- Delisting- and dividend-aware returns.
- Historical DCF assumptions and sensitivity tables, with source citations.
- Walk-forward train/test with no future enforcement labels in historical features.
- Explicit sampling limits, matching selection rules, class imbalance, review log,
  model uncertainty and honest out-of-sample ablation tests.

**None of these gates has been signed off for 30 firms yet.**
