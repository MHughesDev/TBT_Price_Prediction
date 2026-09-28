"""Ground-truth replica of the NEW V5.1 grouping/dedup + scope rules (mirrors the Excel formulas exactly)."""
import pandas as pd, numpy as np, re
from prep import build_all

def variant_type(qs):
    s=str(qs).strip(); l=s.lower()
    if s=='': return 'bare'
    if 'as sold' in l or 'as approved' in l: return 'status_snapshot'
    if 'co#' in l or re.search(r'\bco\s*\d',l) or re.search(r'\bco\d',l): return 'change_order'
    if 'option' in l: return 'option'
    if 'only' in l or 'materials' in l or 'eng' in l: return 'scope_variant'
    if re.match(r'^r\d',l): return 'revision'
    return 'other'

def add_grouping(d):
    d=d.copy()
    q=d['QuoteNumber'].astype(str).str.strip()
    seven=q.str[:7]
    isnum=seven.str.fullmatch(r'\d{7}').fillna(False)
    d['QuoteGroupID']=np.where(isnum,seven,q)
    raw_suf=[s[7:].strip() if n else '' for s,n in zip(q,isnum)]
    d['QuoteSuffix']=[t[1:].strip() if t.startswith('-') else t for t in raw_suf]
    d['QuoteVariantType']=d['QuoteSuffix'].apply(variant_type)
    d['IsScopeVariant']=d['QuoteVariantType'].isin(['change_order','option','scope_variant','other']).astype(int)
    def sufrev(vt,qs):
        if vt!='revision': return 0
        m=re.match(r'^[Rr](\d+)',str(qs))
        return int(m.group(1)) if m else 0
    d['SuffixRevision']=[sufrev(v,s) for v,s in zip(d['QuoteVariantType'],d['QuoteSuffix'])]
    d['EffectiveRevision']=np.maximum(d['RevisionNumber'].fillna(0).astype(float),d['SuffixRevision'].astype(float))
    d['JobKey']=d['QuoteGroupID']+'|'+np.where(d['IsScopeVariant']==1,d['QuoteSuffix'],'')
    d['JobMaxRevision']=d.groupby('JobKey')['EffectiveRevision'].transform('max')
    d['IsJobFirmest']=(d['EffectiveRevision']==d['JobMaxRevision']).astype(int)
    d['JobTankKey']=d['JobKey']+'|'+d['Tank Name'].astype(str)
    # P1-2: distinct effective revisions per JOB (mirrors the Clean_Data growing COUNTIFS)
    _seen=set(); _first=[]
    for jk,er in zip(d['JobKey'],d['EffectiveRevision']):
        k=(jk,er); _first.append(0 if k in _seen else 1); _seen.add(k)
    d['Job Rev First Row']=_first
    d['Job Revision Count']=d.groupby('JobKey')['Job Rev First Row'].transform('sum')
    # first occurrence among firmest rows (mirrors the Excel growing-COUNTIFS)
    seen={}; first=[]
    for jtk,f in zip(d['JobTankKey'],d['IsJobFirmest']):
        if f==1:
            seen[jtk]=seen.get(jtk,0)+1
            first.append(1 if seen[jtk]==1 else 0)
        else: first.append(0)
    d['JobTankFirstOccurrence']=first
    d['ML Training Row V2']=((d['ml_eligible']==1)&(d['IsJobFirmest']==1)&(d['JobTankFirstOccurrence']==1)).astype(int)
    return d

def add_scope_and_recon(d):
    d=d.copy()
    for nm,col in [('inc_material','Material Price'),('inc_fabrication','Fabrication Price'),
                   ('inc_construction','Construction Price'),('inc_insul_material','Insulation Material Price'),
                   ('inc_insul_construction','Insulation Construction Price')]:
        d[nm]=(d[col].fillna(0)>1).astype(int)
    # Verified identities (max relative error 7.1e-07 on every training row):
    #   Proposal Total = bucket sum + Total Tax      (no freight)
    #   Total Price    = bucket sum + Freight Price  (no tax)
    # Neither column is a grand total; the all-in number is buckets + freight + tax.
    d['Ref Grand Total']=d['target_bucket_sum'].fillna(0)+d['Freight Price'].fillna(0)+d['Total Tax'].fillna(0)
    d['recon_proposal_diff']=d['Proposal Total'].fillna(0)-(d['target_bucket_sum'].fillna(0)+d['Total Tax'].fillna(0))
    d['recon_proposal_ok']=(d['recon_proposal_diff'].abs()<=1).astype(int)
    d['recon_total_diff']=d['Total Price'].fillna(0)-(d['target_bucket_sum'].fillna(0)+d['Freight Price'].fillna(0))
    d['recon_total_ok']=(d['recon_total_diff'].abs()<=1).astype(int)
    d['is_taxed']=(d['Total Tax'].fillna(0)>0).astype(int)
    d['construction_scope_conflict']=(((d['no_erection_scope']==1)&(d['Construction Price'].fillna(0)>1))|
                                      ((d['no_erection_scope']==0)&(d['Construction Price'].fillna(0)<=1))).astype(int)
    d['liquid_height_ft']=d['Height (ft)'].fillna(0)-d['Freeboard (in)'].fillna(0)/12.0
    d['liquid_volume_gal']=np.pi*(d['Diameter (ft)'].fillna(0)/2)**2*d['liquid_height_ft'].clip(lower=0)*7.48052
    d['qty_x_shell_area']=d['quantity']*d['shell_area_sqft']
    def roofg(s):
        s=str(s)
        if 'Dome' in s: return 'dome'
        if 'Open-Top' in s: return 'open_top'
        if ':12' in s: return 'pitched'
        if s in ('','nan','(Not Specified)'): return 'unknown'
        return 'flat'
    d['roof_geometry']=d['Deck Style'].apply(roofg)
    def floorg(s):
        s=str(s)
        if 'Slope' in s: return 'sloped'
        if 'Flat' in s: return 'flat'
        if 'Ring' in s or 'Base Angle' in s: return 'no_supplied_floor_plate'
        if s in ('','nan','(Not Specified)'): return 'unknown'
        return 'special'
    d['floor_geometry']=d['Floor Style'].apply(floorg)
    def scope(r):
        m=r['inc_material'] or r['inc_fabrication']; c=r['inc_construction']
        if m and c: return 'tank_quote'
        if m and not c: return 'materials_only'
        if c and not m: return 'construction_only'
        return 'unknown'
    d['scope_class']=d.apply(scope,axis=1)
    d['quote_balanced_weight']=1.0/d['tank_count_in_quoterev'].replace(0,1)
    return d

if __name__=='__main__':
    d=build_all(); d=add_grouping(d); d=add_scope_and_recon(d)
    d.to_pickle('featured3.pkl')
    tr=d[d['ML Training Row V2']==1].copy(); tr.to_pickle('train3.pkl')
    print('all rows',len(d),'| training V2',len(tr),'| was 4535')
    print('variant types:',d['QuoteVariantType'].value_counts().to_dict())
    print('scope_class (training):',tr['scope_class'].value_counts().to_dict())
    print('construction_scope_conflict (training):',int(tr['construction_scope_conflict'].sum()))
    print('proposal = buckets+tax (training):',int(tr['recon_proposal_ok'].sum()),'/',len(tr))
    print('total price = buckets+freight (training):',int(tr['recon_total_ok'].sum()),'/',len(tr))
    print('taxed rows (training):',int(tr['is_taxed'].sum()),'/',len(tr))
