"""FinTruth I historical SEC/AAER evidence pipeline.

SEC downloads are raw public evidence, not audited research labels.
AAER releases may concern issuers or individuals and are not automatic fraud findings.
Use a named SEC_USER_AGENT and comply with SEC fair-access policies.
"""
from __future__ import annotations
import os, re, json, time, hashlib, argparse
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin
import requests
import pandas as pd
from bs4 import BeautifulSoup

API='https://data.sec.gov'
SITE='https://www.sec.gov'
AAER=SITE+'/enforcement-litigation/accounting-auditing-enforcement-releases'
TAGS={'revenue':['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet'],
      'net_income':['NetIncomeLoss'],'assets':['Assets'],'liabilities':['Liabilities'],
      'equity':['StockholdersEquity'],'operating_cash_flow':['NetCashProvidedByUsedInOperatingActivities'],
      'capex':['PaymentsToAcquirePropertyPlantAndEquipment'],'diluted_shares':['WeightedAverageNumberOfDilutedSharesOutstanding'],
      'ebit':['OperatingIncomeLoss'],'cash':['CashAndCashEquivalentsAtCarryingValue'],
      'long_term_debt':['LongTermDebtCurrent','LongTermDebtNoncurrent']}

class SECClient:
    def __init__(self,user_agent,cache_dir,min_interval=.20,session=None):
        if '@' not in user_agent or len(user_agent)<10:
            raise ValueError('Set SEC_USER_AGENT to organization/person plus contact email')
        if min_interval < .10:raise ValueError('SEC fair access: at most 10 requests/sec')
        self.ua=user_agent
        self.cache=Path(cache_dir);self.cache.mkdir(parents=True,exist_ok=True)
        self.interval=min_interval;self.session=session or requests.Session()
        self.last=0.
    def get(self,url):
        if not url.startswith((API+'/',SITE+'/')):
            raise ValueError('Official SEC URLs only')
        key=hashlib.sha256(url.encode()).hexdigest()
        file=self.cache/(key+'.bin');meta=self.cache/(key+'.json')
        if file.exists() and meta.exists():return file.read_bytes(),json.loads(meta.read_text())
        wait=self.interval-(time.monotonic()-self.last)
        if wait>0:time.sleep(wait)
        self.last=time.monotonic()
        resp=self.session.get(url,headers={'User-Agent':self.ua,'Accept-Encoding':'gzip, deflate'},
                              timeout=40)
        resp.raise_for_status()
        raw=resp.content
        info={'url':url,'retrieved_utc':datetime.now(timezone.utc).isoformat(),
              'sha256':hashlib.sha256(raw).hexdigest(),'status_code':resp.status_code,
              'status':'RAW_UNREVIEWED'}
        file.write_bytes(raw);meta.write_text(json.dumps(info,indent=2))
        return raw,info
    def get_json(self,url):return json.loads(self.get(url)[0])
    def tickers(self):
        obj=self.get_json(SITE+'/files/company_tickers.json')
        return pd.DataFrame(obj.values()).rename(columns={'cik_str':'cik'}).assign(
            cik=lambda d:d.cik.astype(int),ticker=lambda d:d.ticker.str.upper())
    def submissions(self,cik):
        return self.get_json(f'{API}/submissions/CIK{int(cik):010d}.json')
    def companyfacts(self,cik):
        return self.get_json(f'{API}/api/xbrl/companyfacts/CIK{int(cik):010d}.json')

def match_ciks(mapping,wanted):
    """Ticker map is CURRENT and not reliable as a historical identity timeline."""
    indexed=mapping.set_index('ticker')
    rows=[]
    for ticker in wanted:
        t=ticker.strip().upper()
        if t not in indexed.index:
            rows.append({'ticker':t,'cik':pd.NA,'name':None,'status':'UNMATCHED_MANUAL_REVIEW'})
        else:
            row=indexed.loc[t]
            if isinstance(row,pd.DataFrame):
                rows.append({'ticker':t,'cik':pd.NA,'name':None,'status':'AMBIGUOUS_MANUAL_REVIEW'})
            else:
                rows.append({'ticker':t,'cik':int(row.cik),'name':row.get('title'),
                             'status':'CURRENT_MAP_HISTORICAL_ID_UNVERIFIED'})
    return pd.DataFrame(rows)

def filing_table(data,cik,start='2005-01-01',end='2025-12-31'):
    rec=data.get('filings',{}).get('recent',data)
    rows=[]
    forms=rec.get('form',[])
    for i,form in enumerate(forms):
        if form not in ('10-K','10-Q','10-K/A','10-Q/A'):continue
        date=rec['filingDate'][i]
        if date<start or date>end:continue
        acc=rec['accessionNumber'][i]
        accepted=rec.get('acceptanceDateTime',[])
        period=rec.get('reportDate',[])
        primary=rec['primaryDocument'][i]
        rows.append({'cik':int(cik),'form':form,'accession':acc,'filing_date':date,
         'acceptance_datetime':accepted[i] if i<len(accepted) else None,
         'period_end':period[i] if i<len(period) else None,
         'source_url':f'{SITE}/Archives/edgar/data/{int(cik)}/{acc.replace("-","")}/{primary}',
         'validation':'SEC_METADATA_UNREVIEWED'})
    return pd.DataFrame(rows)

def all_filings(client,cik,start='2005-01-01',end='2025-12-31'):
    root=client.submissions(cik)
    frames=[filing_table(root,cik,start,end)]
    for shard in root.get('filings',{}).get('files',[]):
        raw=client.get_json(f'{API}/submissions/{shard["name"]}')
        frames.append(filing_table(raw,cik,start,end))
    frames=[f for f in frames if len(f)]
    if not frames:return pd.DataFrame()
    return pd.concat(frames,ignore_index=True).drop_duplicates('accession').sort_values('filing_date')

def companyfacts_table(data,cik,through='2025-12-31'):
    out=[]; facts=data.get('facts',{}).get('us-gaap',{})
    for metric,tags in TAGS.items():
        for tag in tags:
            for unit,observations in facts.get(tag,{}).get('units',{}).items():
                if unit not in ('USD','shares'):continue
                for x in observations:
                    if x.get('form') not in ('10-K','10-Q','10-K/A','10-Q/A'):continue
                    if x.get('filed','9999')>through:continue
                    out.append({'cik':int(cik),'metric':metric,'tag':tag,'unit':unit,
                     'value':x.get('val'),'period_start':x.get('start'),
                     'period_end':x.get('end'),'filed':x.get('filed'),
                     'accession':x.get('accn'),'form':x.get('form'),
                     'fy':x.get('fy'),'fp':x.get('fp'),'frame':x.get('frame'),
                     'status':'RAW_XBRL_UNRECONCILED'})
    return pd.DataFrame(out)

def aaer_candidates(html,through='2025-12-31'):
    """One archive HTML page only. Page navigation requires additional retrieval."""
    soup=BeautifulSoup(html,'html.parser');rows=[]
    for tr in soup.select('tr'):
        words=tr.get_text(' ',strip=True)
        matches=sorted(set(re.findall(r'AAER\s*[-–]\s*(\d+)',words,re.I)))
        if not matches:continue
        links=[urljoin(SITE,a['href']) for a in tr.select('a[href]')]
        rawdate=tr.find('time')
        parsed=pd.to_datetime(rawdate.get('datetime') if rawdate else words[:30],errors='coerce')
        date=parsed.strftime('%Y-%m-%d') if pd.notna(parsed) else None
        if date and date>through:continue
        for n in matches:
            rows.append({'aaer_number':n,'release_date':date,'listing_text':words,
                         'source_url':links[0] if links else None,'company_cik':pd.NA,
                         'alleged_start':None,'alleged_end':None,
                         'case_resolution':None,'status':'CANDIDATE_MANUAL_REVIEW_REQUIRED'})
    return pd.DataFrame(rows)

def point_in_time_facts(facts,filings,dates):
    """Join by original filing accession; select only filings known strictly before date.

    This does NOT certify that companyfacts is revision-free. Manual original-document
    XBRL reconciliation is required before marking any input validated.
    """
    if facts.empty or filings.empty:return pd.DataFrame()
    fm=filings[['cik','accession','filing_date','acceptance_datetime','source_url']]
    d=facts.merge(fm,on=['cik','accession'],how='inner',validate='many_to_one')
    d['released']=pd.to_datetime(d.acceptance_datetime,errors='coerce')
    d['released']=d.released.fillna(pd.to_datetime(d.filing_date)+pd.Timedelta(days=1))
    d['period_end']=pd.to_datetime(d.period_end)
    out=[]
    for date in pd.to_datetime(dates):
        eligible=d[(d.released<date)&(d.period_end<=date)]
        for (cik,metric),g in eligible.groupby(['cik','metric']):
            row=g.sort_values(['period_end','released','accession'],ascending=False).iloc[0]
            same=g[(g.period_end==row.period_end)&(g.accession==row.accession)&(g.unit==row.unit)]
            if same.value.nunique()!=1:continue
            out.append({'date':date.date().isoformat(),'cik':int(cik),
                        'metric':metric,'value':row.value,'period_end':str(row.period_end.date()),
                        'available_at':str(row.released),'accession':row.accession,
                        'source_url':row.source_url,'status':'PIT_UNAUDITED'})
    return pd.DataFrame(out)

def audit_ledger(ledger):
    required={'cik','accession','filing_date','period_end','source_url',
              'checked_by','checked_at','reconciled','sha256'}
    if not required.issubset(ledger):
        raise ValueError(f'Missing audit columns: {sorted(required-set(ledger))}')
    good=ledger[list(required)].notna().all(axis=1)&ledger.reconciled.astype(str).str.lower().eq('true')
    duplicates=int(ledger.duplicated(['cik','accession']).sum())
    return {'total':len(ledger),'reviewed':int(good.sum()),'unreviewed':int((~good).sum()),
            'duplicate_accessions':duplicates,'pass':bool(len(ledger)>0 and good.all() and duplicates==0)}

def price_backtest(signals,prices,horizons=(1,5,21)):
    """Forward total-return targets; enter NEXT trading day strictly after signal date."""
    need={'ticker','asof_date','signal'}
    if not need.issubset(signals):raise ValueError(f'Missing signal columns {need-set(signals)}')
    need={'ticker','date','adjusted_close'}
    if not need.issubset(prices):raise ValueError(f'Missing price columns {need-set(prices)}')
    p=prices.copy();s=signals.copy()
    p['date']=pd.to_datetime(p.date);s['asof_date']=pd.to_datetime(s.asof_date)
    if p.duplicated(['ticker','date']).any() or (p.adjusted_close<=0).any():
        raise ValueError('Invalid or duplicate price observations')
    if s.duplicated(['ticker','asof_date']).any():raise ValueError('Duplicate signals')
    p=p.sort_values(['ticker','date'])
    for h in horizons:
        p[f'forward_{h}d']=p.groupby('ticker').adjusted_close.shift(-h)/p.adjusted_close-1
        p[f'label_end_{h}d']=p.groupby('ticker').date.shift(-h)
    merged=s.merge(p,on='ticker')
    merged=merged[merged.date>merged.asof_date].sort_values(['ticker','asof_date','date'])
    merged=merged.drop_duplicates(['ticker','asof_date'],keep='first')
    keep=['ticker','asof_date','signal','date']+[f'forward_{h}d' for h in horizons]+[f'label_end_{h}d' for h in horizons]
    return merged[keep].rename(columns={'date':'entry_date'}).reset_index(drop=True)

def make_templates(directory):
    d=Path(directory);d.mkdir(parents=True,exist_ok=True)
    samples={
      'pilot_30_company_registry.csv':['ticker','cik','company_name','cohort','sector',
       'selection_reason','matched_control_ticker','identity_verified','reviewer','review_date'],
      'filing_manual_audit.csv':['cik','accession','filing_date','period_end',
       'source_url','checked_by','checked_at','reconciled','sha256','notes'],
      'aaer_manual_audit.csv':['aaer_number','company_cik','source_url','release_date',
       'alleged_start','alleged_end','accounting_issue','allegation_vs_final',
       'case_status','reviewer','review_date','document_quote','manual_verified']}
    for path,cols in samples.items():pd.DataFrame(columns=cols).to_csv(d/path,index=False)

def main():
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest='cmd',required=True)
    init=sub.add_parser('init-pilot');init.add_argument('--output',default='pilot')
    collect=sub.add_parser('collect');collect.add_argument('--tickers',required=True)
    collect.add_argument('--output',default='sec_research')
    collect.add_argument('--start',default='2005-01-01')
    collect.add_argument('--end',default='2025-12-31')
    collect.add_argument('--include-aaer-page',action='store_true')
    audit=sub.add_parser('audit');audit.add_argument('--ledger',required=True)
    a=ap.parse_args()
    if a.cmd=='init-pilot':
        make_templates(a.output);print('Blank audit templates created; no companies verified');return
    if a.cmd=='audit':
        result=audit_ledger(pd.read_csv(a.ledger));print(json.dumps(result,indent=2))
        if not result['pass']:raise SystemExit(1)
        return
    client=SECClient(os.getenv('SEC_USER_AGENT',''),Path(a.output)/'cache')
    root=Path(a.output);root.mkdir(parents=True,exist_ok=True)
    matches=match_ciks(client.tickers(),a.tickers.split(','))
    matches.to_csv(root/'identifier_candidates.csv',index=False)
    for entry in matches.to_dict('records'):
        if pd.isna(entry['cik']):continue
        cik=int(entry['cik']);d=root/str(cik);d.mkdir(exist_ok=True)
        all_filings(client,cik,a.start,a.end).to_csv(d/'filing_manifest.csv',index=False)
        companyfacts_table(client.companyfacts(cik),cik,a.end).to_csv(d/'xbrl_raw_facts.csv',index=False)
    if a.include_aaer_page:
        aaer_candidates(client.get(AAER)[0],a.end).to_csv(root/'aaer_page_candidates.csv',index=False)
    print('Collection complete: data remain UNVERIFIED pending manual review')

if __name__=='__main__':main()
