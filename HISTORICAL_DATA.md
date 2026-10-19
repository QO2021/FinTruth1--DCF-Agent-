# Historical SEC/AAER Validation — FinTruth I

## Research status

This module collects candidate original SEC filings, XBRL facts, and archive references. **Downloaded data are not manually verified. No 2005–2025 empirical panel, AAER-labeled dataset, or claim of predictive significance exists yet.**

### Install
```bash
python -m pip install -r requirements.txt
```
Set a legitimate descriptive email address, replacing placeholders:
```bash
export SEC_USER_AGENT="AcademicResearch YourName research@example.edu"
```
On Windows PowerShell: `$env:SEC_USER_AGENT="AcademicResearch YourName research@example.edu"`.

### Pilot audit templates
```bash
python historical_pipeline.py init-pilot --output pilot
```
Populate 20–30 candidate firms *after* manually verifying CIK / historical ticker identity, original 10-K/10-Q filings, and AAER case identity. Use positive (verified SEC accounting-related enforcement), comparable unlabeled controls, and other representative issuers. **Absence of an AAER is not proof of absence of misconduct.**

### Retrieve the original SEC evidence
```bash
python historical_pipeline.py collect --tickers AAPL,MSFT,JPM,GE --start 2005-01-01 --end 2025-12-31 --include-aaer-page --output sec_research
```
Outputs include identifier candidates, filing manifests, full available companyfacts facts for the requested period, optionally AAER archive **one-page candidates**, and a per-URL cached response with SHA-256 + retrieval timestamp. This command does not populate or certify 30 companies, does not download filing body text, and does **not** crawl the complete paginated AAER historical archive.

### Validate manually and audit
Inspect original filing accession documents and annotate `pilot/filing_manual_audit.csv`, including source URL, reviewer, verification date, SHA-256, and reconciliation status. For AAER, inspect each original enforcement release and record allegation, disposition, alleged accounting periods, release date, issuer CIK, and company identifier matching.

```bash
python historical_pipeline.py audit --ledger pilot/filing_manual_audit.csv
pytest -q
```

### Point-in-time features and predictive evaluation

Functions in `historical_pipeline.py`:
- `match_ciks(...)`: candidate current ticker-to-CIK lookup (requires historical identity review)
- `all_filings(...)`: SEC submissions plus older shards, 10-K/10-Q and amendments
- `companyfacts_table(...)`: structured US-GAAP values with full accession and filing date
- `aaer_candidates(...)`: single-page archive index candidate parser; **not verified enforcement labels**
- `point_in_time_facts(...)`: restrict features to filings available strictly before decision date, preserving original accession
- `audit_ledger(...)`: fail closed if a manual reconciliation record is missing
- `price_backtest(...)`: next-trading-day price entry, forward 1/5/21-day outcomes, assumes supplied adjusted price series is already point-in-time correct

**Important scientific limitations:** Never treat retrospective XBRL feeds as a fully historical disclosure snapshot without original-document reconciliation. Deduplicate GAAP variants carefully; distinguish instant vs duration, annual vs quarterly and fiscal year vs trailing twelve months. The included feature prototype is a long-format provenance table, not yet a calibrated fundamental-signal panel. The price interface does not include a price vendor, transaction costs, delisting returns, historical sector universe, or causally interpreted AAER labels. SEC AAER publication is frequently much later than relevant accounting periods; use it as a subsequent outcome, **not a historical predictor**. Assign any label only after human verification and temporal restriction.

This package does not yet establish any empirical FinTruth I results; report claims should remain explicitly preliminary.
