"""Tests for Markdown/JSON reporting, including abstention and as-of alignment."""
import json
import pandas as pd
from report import generate_summary_report


def test_report_abstains_on_incomplete_agent_scores(tmp_path):
    scores=pd.DataFrame([{
        'ticker':'TEST','date':'2025-01-31','valuation_score':float('nan'),
        'credibility_score':0.7,'predicted_return':0.01,
        'predictability_score':0.8,'combined_score':float('nan')
    }])
    result=generate_summary_report(scores,tmp_path,data_label='SYNTHETIC DEMO')
    content=(tmp_path/'summary_report.md').read_text()
    assert 'Insufficient evidence (abstain)' in content
    assert 'SYNTHETIC DEMONSTRATION ONLY' in content
    assert result['company_count']==1
    assert json.loads((tmp_path/'summary_report.json').read_text())['company_count']==1


def test_future_dcf_assumption_not_included(tmp_path):
    scores=pd.DataFrame([{
        'ticker':'TEST','date':'2025-01-31','valuation_score':0.6,
        'credibility_score':0.7,'predicted_return':0.03,
        'predictability_score':0.9,'combined_score':0.72
    }])
    dcf=pd.DataFrame([{
        'ticker':'TEST','asof_date':'2025-02-01','market_price':10,
        'fair_value_per_share':20,'upside_pct':100,'judgment':'Undervalued'
    }])
    output=generate_summary_report(scores,tmp_path,dcf)
    company=output['latest_assessments'][0]
    assert company['dcf_judgment']=='Not available'
    assert company['overall_conclusion']=='High combined evidence'


def test_dcf_is_displayed_for_valid_historical_asof(tmp_path):
    scores=pd.DataFrame([{
        'ticker':'TEST','date':'2025-01-31','valuation_score':0.6,
        'credibility_score':0.7,'predicted_return':-0.02,
        'predictability_score':0.1,'combined_score':0.48
    }])
    dcf=pd.DataFrame([{
        'ticker':'TEST','asof_date':'2025-01-20','market_price':10,
        'fair_value_per_share':15,'upside_pct':50,'judgment':'Undervalued'
    }])
    report=generate_summary_report(scores,tmp_path,dcf)
    company=report['latest_assessments'][0]
    assert company['dcf_judgment']=='Undervalued'
    assert company['dcf_upside_pct']=='50.00%'
    assert company['predicted_return_pct']=='-2.00%'
