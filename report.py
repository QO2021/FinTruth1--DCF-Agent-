"""Readable, evidence-conscious FinTruth I research summary reports.

The report summarizes supplied/generated model outputs; it does not fetch filings,
verify disclosures, or provide investment recommendations.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import pandas as pd


def _number(value, digits=2, suffix=''):
    try:
        x=float(value)
        if not math.isfinite(x): return 'Not available'
        return f'{x:,.{digits}f}{suffix}'
    except (TypeError, ValueError):
        return 'Not available'


def _text(value):
    if pd.isna(value) or str(value).strip()=='':
        return 'Not available'
    return str(value).replace('|', '/').replace('\n', ' ')


def _markdown_table(headers, rows):
    return ('| ' + ' | '.join(headers) + ' |\n'
            + '| ' + ' | '.join(['---']*len(headers)) + ' |\n'
            + ''.join('| ' + ' | '.join(str(x) for x in row) + ' |\n' for row in rows))


def generate_summary_report(scores: pd.DataFrame, output_dir: str | Path,
                            dcf: pd.DataFrame | None = None,
                            metrics: dict | None = None,
                            data_label: str = 'USER-SUPPLIED') -> dict:
    """Write summary_report.md and summary_report.json to output_dir.

    Input scores should be the FinTruth pipeline's integrated_scores DataFrame.
    This function summarizes output only; it never manufactures missing signals.
    """
    required={'ticker','date','valuation_score','credibility_score',
              'predicted_return','predictability_score','combined_score'}
    missing=required-set(scores.columns)
    if missing: raise ValueError(f'Missing report columns: {sorted(missing)}')
    out=Path(output_dir);out.mkdir(parents=True,exist_ok=True)
    d=scores.copy()
    d['date']=pd.to_datetime(d['date'],errors='coerce')
    if d['date'].isna().any(): raise ValueError('Invalid dates')
    if d.duplicated(['ticker','date']).any():
        raise ValueError('Duplicate ticker/date rows')
    d=d.sort_values(['ticker','date'])
    latest=d.groupby('ticker',sort=True).tail(1).sort_values('ticker')
    if dcf is not None:
        required_dcf={'ticker','asof_date','market_price','fair_value_per_share',
                      'upside_pct','judgment'}
        if not required_dcf.issubset(dcf.columns):
            raise ValueError(f'Missing DCF columns: {sorted(required_dcf-set(dcf.columns))}')
        v=dcf.copy()
        v['asof_date']=pd.to_datetime(v['asof_date'],errors='coerce')
        if v['asof_date'].isna().any(): raise ValueError('Invalid DCF asof_date')
        if v.duplicated(['ticker','asof_date']).any(): raise ValueError('Duplicate DCF company/date')
        v=v.sort_values('asof_date')
        # Use a valuation only where its as-of date is no later than the score date.
        latest=pd.merge_asof(latest.sort_values('date'),v[
            ['ticker','asof_date','market_price','fair_value_per_share','upside_pct','judgment']
        ].sort_values('asof_date'),left_on='date',right_on='asof_date',
            by='ticker',direction='backward',suffixes=('','_dcf'))
        latest=latest.sort_values('ticker')
    elif 'judgment' not in latest.columns:
        for col in ['market_price','fair_value_per_share','upside_pct','judgment','asof_date']:
            if col not in latest.columns: latest[col]=float('nan')

    metrics=metrics or {}
    weights=metrics.get('weights',{})
    empirical=metrics.get('metrics',{})
    rows=[]; detail=[]
    for row in latest.to_dict('records'):
        ticker=_text(row.get('ticker'))
        when=str(pd.Timestamp(row['date']).date())
        valuation=row.get('valuation_score')
        credibility=row.get('credibility_score')
        predictability=row.get('predictability_score')
        combined=row.get('combined_score')
        judgment=row.get('judgment')
        if pd.isna(combined):
            overall='Insufficient evidence (abstain)'
        elif combined >= 0.60:
            overall='High combined evidence'
        elif combined <= 0.40:
            overall='Low combined evidence'
        else:
            overall='Mixed / neutral'
        item={
            'ticker':ticker,'asof_date':when,'dcf_judgment':_text(judgment),
            'market_price':_number(row.get('market_price')),
            'intrinsic_value_per_share':_number(row.get('fair_value_per_share')),
            'dcf_upside_pct':_number(row.get('upside_pct'),suffix='%'),
            'valuation_score':_number(valuation,3),
            'credibility_score':_number(credibility,3),
            'predicted_return_pct':_number(
                float(row['predicted_return'])*100 if pd.notna(row.get('predicted_return')) else None,
                suffix='%'),
            'predictability_score':_number(predictability,3),
            'combined_score':_number(combined,3),
            'overall_conclusion':overall
        }
        detail.append(item)
        rows.append([ticker,when,item['dcf_judgment'],item['dcf_upside_pct'],
                     item['predicted_return_pct'],item['combined_score'],overall])
    is_demo='SYNTHETIC' in data_label.upper() or 'DEMO' in data_label.upper()
    lines=['# FinTruth I — Valuation, Credibility & Predictability Summary',
           '',f'**Data classification:** {data_label}',f'**Companies assessed:** {len(detail)}',
           f'**Observations in panel:** {len(d):,}',
           f'**Latest decision date:** {latest.date.max().date() if len(latest) else "Not available"}',
           '']
    if is_demo:
        lines.extend(['**WARNING: SYNTHETIC DEMONSTRATION ONLY. No conclusions about real U.S. stocks may be drawn.**',''])
    lines.extend(['## Executive Summary','',
        'DCF judgments estimate intrinsic value under explicit cash-flow and discount-rate assumptions. '
        'The combined FinTruth score is a relative evidence ranking, **not** a probability of price appreciation '
        'and **not** a buy/sell recommendation. Missing inputs cause the integrated engine to abstain.',
        ''])
    lines.extend(['## Latest Company Assessments','',
        _markdown_table(['Ticker','As-of','DCF assessment','DCF upside','Forecast return',
                         'Combined score','Overall assessment'],rows),''])
    lines.extend(['## Model Configuration and Out-of-Sample Evaluation',''])
    if weights:
        lines.append('Weights: '+', '.join(f'{k}={_number(v,3)}' for k,v in weights.items())+'.')
    else:
        lines.append('Weights: not supplied in the metrics record.')
    if empirical:
        for label,key in [('Completed predictions','n'),('OOS R² vs zero benchmark','oos_r2_vs_zero'),
                          ('Rank information coefficient','rank_ic'),('Mean squared error','mse')]:
            if key in empirical:
                lines.append(f'- {label}: {_number(empirical[key],5)}')
        if 'status' in empirical: lines.append(f'- Evaluation status: {_text(empirical["status"])}')
    else:
        lines.append('No out-of-sample evaluation metrics supplied.')
    lines.extend(['','## Company-Level Agent Assessments',''])
    for item in detail:
        lines.extend([f'### {item["ticker"]} — {item["asof_date"]}','',
            f'- **DCF:** {item["dcf_judgment"]}; market price {item["market_price"]}; '
            f'intrinsic value/share {item["intrinsic_value_per_share"]}; modeled upside {item["dcf_upside_pct"]}.',
            f'- **Fundamental Valuation Agent:** {item["valuation_score"]} / 1.',
            f'- **Financial Disclosure Credibility Agent:** {item["credibility_score"]} / 1; '
            'proxy-feature score only, **not verified financial-statement credibility or fraud probability**.',
            f'- **Return Predictability Agent:** {_text(item["predicted_return_pct"])} forward predicted return; '
            f'rank score {item["predictability_score"]} / 1.',
            f'- **Integrated conclusion:** {item["overall_conclusion"]} '
            f'(score {item["combined_score"]} / 1).',''])
    lines.extend(['## Data Quality, Scope, and Limitations','',
        '- This report does **not** independently verify SEC 10-K, AAER, price, or analyst forecast data.',
        '- A DCF output is only as reliable as its revenue growth, margin, WACC, terminal growth, '
          'debt, cash, and diluted-share assumptions; review WACC and terminal growth sensitivity.',
        '- The credibility score uses provided accounting and text proxy features; no automated '
          'full-text SEC/AAER evidence adjudication has been performed.',
        '- Point-in-time availability must be independently verified, including filing timestamps '
          'and the as-of dates used for valuations and market prices.',
        '- Forecast returns reflect the pipeline horizon (5 trading days by default); assess '
          'signal calibration, transaction costs, economic significance, and out-of-sample robustness.',
        '- Scores and the 40/30/30 default weighting are experimental and uncalibrated.',
        '- This document is for reproducible academic research, not investment advice.',''])
    report='\n'.join(lines)
    (out/'summary_report.md').write_text(report,encoding='utf-8')
    manifest={'data_classification':data_label,'company_count':len(detail),
              'observation_count':len(d),'latest_assessments':detail,
              'metrics':metrics,
              'limitations':['No independently verified live SEC/AAER facts',
                             'Uncalibrated research weights and signal scores']}
    (out/'summary_report.json').write_text(json.dumps(manifest,indent=2,default=str),
                                           encoding='utf-8')
    return manifest


def main():
    p=argparse.ArgumentParser(description='Generate FinTruth I summary report from pipeline outputs')
    p.add_argument('--scores',required=True)
    p.add_argument('--dcf',help='Optional DCF valuations CSV')
    p.add_argument('--metrics',help='Optional metrics.json')
    p.add_argument('--output',default='results')
    args=p.parse_args()
    metrics=json.loads(Path(args.metrics).read_text(encoding='utf-8')) if args.metrics else None
    generate_summary_report(pd.read_csv(args.scores),args.output,
        pd.read_csv(args.dcf) if args.dcf else None,
        metrics, 'USER-SUPPLIED' if metrics is None else metrics.get('data_type','USER-SUPPLIED'))
    print(f'Wrote {Path(args.output)/"summary_report.md"} and summary_report.json')


if __name__=='__main__': main()
