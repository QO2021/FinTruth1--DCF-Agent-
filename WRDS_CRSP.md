# WRDS/CRSP Integration — FinTruth I

The project now includes `wrds_crsp.py`, a **read-only** interface for licensed
WRDS/CRSP historical equities data. Run it on a machine where your own WRDS
subscription is configured. **No WRDS login credentials or licensed raw data
should be committed to this public repository.**

## 1. Install and sign in locally

```bash
python -m pip install -r requirements.txt
python -m pip install wrds
python wrds_crsp.py --inspect --out local_crsp_private
```

The optional `wrds` package manages authentication interactively or through
the supported WRDS credential mechanism. Do not place credentials in a notebook,
message, or environment file committed to GitHub.

## 2. Verify historical security identifiers

The pilot registry in `pilot30.py` lists *candidate current tickers*, not
historically validated PERMNO mappings. Manually validate PERMNO, PERMCO,
historical ticker intervals, name changes, corporate actions, and CIK links.
Only use a verified PERMNO after that audit.

Inspect available tables and columns first. Table names and products can differ
by WRDS subscription. The built-in adapter currently checks
`crsp.dsf_v2` and supporting schema metadata, and only queries a verified list
of PERMNO values.

## 3. Download 2005–2025 records

Substitute real **manually verified** PERMNOs:

```bash
python wrds_crsp.py --permnos 14593,10107 --start 2005-01-01 --end 2025-12-31 --out local_crsp_private
```

Local outputs: `ciz_daily_private.csv`, `crsp_schema.json`. Raw CRSP
observations are licensed: keep files in local/private storage, subject
to WRDS/CRSP agreements. This command cannot run without valid credentials,
subscription rights, and network access.

## 4. Return conventions and audit

Current CRSP CIZ (version 2) `DlyRet` includes delisting returns.
**Do not also compound legacy `DLRET`**; doing so double-counts delistings.
Use permanent security IDs and `DlyCalDt`; flag missing-return codes,
`DlyRetMissFlg`, `DlyDelFlg`, multiple share classes, and terminal dates.

`daily_forward_returns(ciz, signals, horizons=(1,5,21))` holds out
incomplete observation windows rather than returning a fabricated return.
The function assumes a complete daily security extract and next-observed-day
entry. A final paper must additionally set an execution-price policy, trading
availability filters, market holiday alignment, transaction costs, and
risk-adjusted benchmark returns.

Do not accidentally use `validation.delisting_aware_backtest` with CIZ:
that earlier module expects **legacy** separated `ret` and `dlret`.
For CIZ use `wrds_crsp.daily_forward_returns` only.

## 5. Integration into FinTruth I

1. Generate `pilot30/pilot_30_company_candidates.csv`.
2. Review SEC CIK / original filing accession / AAER original order.
3. Review CRSP historical PERMNO and match security to issuer date ranges.
4. Run `wrds_crsp.py` for the verified PERMNOs.
5. Align SEC fundamental signals to release times before market decisions.
6. Produce dated FinTruth scores from validated fundamental and credibility features.
7. Evaluate with `daily_forward_returns`, report coverage and unavailable labels,
   and compare with market/sector benchmarks.

The current pipeline **does not yet assemble** those steps into a single
automated empirical 30-company dataset. The 30-firm pilot and source
audits are still outstanding.

## Official reference
- WRDS CRSP CIZ transition: https://wrds-www.wharton.upenn.edu/pages/data-announcements/changes-to-crsp-data/
- WRDS CIZ event-study code: https://wrds-www.wharton.upenn.edu/pages/wrds-research/macros/run-an-event-study-ciz-format-macro/
