"""Archive pagination with evidence coverage and original-document downloads.

This crawler collects *candidate* AAER records; manual review is required.
"""
from __future__ import annotations
import argparse,json,os,re,hashlib
from pathlib import Path
from urllib.parse import urljoin,urlparse,parse_qs,urlencode,urlunparse
import pandas as pd
from bs4 import BeautifulSoup
from historical_pipeline import SECClient,AAER,aaer_candidates

def crawl_archive(client,start_year=2005,end_year=2025,max_pages=100):
    """Traverse year-filtered pages and visible 'next' links; log every page.
    Does not assert completeness if page templates, access or navigation fail.
    """
    if start_year>end_year:raise ValueError('Invalid years')
    records=[];coverage=[]
    for year in range(start_year,end_year+1):
        next_url=f'{AAER}?year={year}'
        seen=set();stop='PAGE_LIMIT_OR_INCOMPLETE'
        for page in range(max_pages):
            if next_url in seen:
                stop='REPEATED_LINK';break
            seen.add(next_url)
            try:payload,meta=client.get(next_url)
            except Exception as exc:
                coverage.append({'year':year,'page':page,'url':next_url,
                       'status':'ERROR','error':str(exc)})
                stop='ERROR';break
            soup=BeautifulSoup(payload,'html.parser')
            rows=aaer_candidates(payload,through=f'{end_year}-12-31')
            coverage.append({'year':year,'page':page,'url':next_url,
                'status':'RETRIEVED_UNVALIDATED','records':len(rows),
                'sha256':meta['sha256']})
            if len(rows):
                rows['archive_url']=next_url;rows['year_filter']=year
                records.append(rows)
            candidates=[]
            for a in soup.find_all('a',href=True):
                rel=a.get('rel',[])
                label=' '.join(a.get_text(' ',strip=True).lower().split())
                attrs=(a.get('aria-label') or '').lower()
                if ('next' in rel or 'next' in label or 'next' in attrs) and 'page=' in a['href']:
                    u=urljoin(next_url,a['href'])
                    if u.startswith(AAER) and u not in seen:candidates.append(u)
            if not candidates:
                stop='NO_NEXT_LINK_REVIEW_REQUIRED';break
            next_url=candidates[0]
        coverage.append({'year':year,'page':'END','status':stop})
    events=pd.concat(records,ignore_index=True).drop_duplicates('aaer_number') if records else pd.DataFrame()
    return events,pd.DataFrame(coverage)

def download_evidence(client, urls,output_dir):
    output=Path(output_dir);output.mkdir(parents=True,exist_ok=True)
    items=[]
    for url in urls:
        if not isinstance(url,str) or not url.startswith(('https://www.sec.gov/','https://data.sec.gov/')):
            continue
        key=hashlib.sha256(url.encode()).hexdigest()
        row={'source_url':url,'document_id':key,'validation_status':'DOWNLOAD_FAILED'}
        try:
            raw,meta=client.get(url)
            soup=BeautifulSoup(raw,'html.parser')
            for x in soup(['script','style']):x.decompose()
            (output/(key+'.html')).write_bytes(raw)
            (output/(key+'.txt')).write_text(soup.get_text(' ',strip=True),encoding='utf-8')
            row.update({'sha256':meta['sha256'],'retrieved_utc':meta['retrieved_utc'],
                        'validation_status':'RAW_DOCUMENT_UNREVIEWED'})
        except Exception as exc:row['error']=str(exc)
        items.append(row)
    return pd.DataFrame(items)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--start',type=int,default=2005)
    parser.add_argument('--end',type=int,default=2025)
    parser.add_argument('--output',default='aaer_research')
    parser.add_argument('--max-pages',type=int,default=100)
    parser.add_argument('--download-documents',action='store_true')
    args=parser.parse_args()
    dest=Path(args.output);dest.mkdir(parents=True,exist_ok=True)
    client=SECClient(os.getenv('SEC_USER_AGENT',''),dest/'cache')
    archive,coverage=crawl_archive(client,args.start,args.end,args.max_pages)
    archive.to_csv(dest/'aaer_candidates.csv',index=False)
    coverage.to_csv(dest/'crawl_coverage.csv',index=False)
    if args.download_documents and len(archive):
        urls=archive.source_url.dropna().drop_duplicates().tolist()
        download_evidence(client,urls,dest/'documents').to_csv(dest/'download_manifest.csv',index=False)
    print('SEC documents are UNVERIFIED. Review coverage log and manually reconcile each case.')
if __name__=='__main__':main()
