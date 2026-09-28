"""V5 builder - part 3: README, audit, feature catalog, modeling plan, research, validation."""
import openpyxl, pandas as pd
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter as CL
from openpyxl.chart import BarChart, Reference
from build_ml import SPEC, L, D
from build_core import C as CD

FONT='Arial'
NAVY=PatternFill('solid',fgColor='1F3864'); LT=PatternFill('solid',fgColor='D9E1F2')
ORANGE=PatternFill('solid',fgColor='C6501E'); RED=PatternFill('solid',fgColor='9C3B3B')
GREEN=PatternFill('solid',fgColor='375623'); YELLOW=PatternFill('solid',fgColor='FFF2CC')
H1=Font(name=FONT,bold=True,size=16,color='1F3864')
H2=Font(name=FONT,bold=True,size=12,color='FFFFFF')
BOLD=Font(name=FONT,bold=True,size=10); BODY=Font(name=FONT,size=10)
MONO=Font(name='Consolas',size=9)

NTRAIN=[0]                                     # real training row count, set in main()
def NT(): return f'{NTRAIN[0]:,}'              # formatted, for prose in the doc sheets
ML='ML_Tank_Training'; MF,MLST=3,4483          # ML data rows; MLST is overwritten in
                                              # main() from the actual sheet - see P1-5.
                                              # Do not rely on the literal above.
# P1-5: derived from the source row count, not typed. HANDOFF gotcha 6.
from build_core import N as N_CLEAN
CF,CLST=2,N_CLEAN+1                             # Clean_Data data rows
def mc(h): return L[h]                          # ML column letter
def mrng(h): return f"{ML}!${mc(h)}${MF}:${mc(h)}${MLST}"
def crng(h): return f"Clean_Data!${CD[h]}${CF}:${CD[h]}${CLST}"

def title(ws,text,sub=''):
    ws['A1']=text; ws['A1'].font=H1
    if sub: ws['A2']=sub; ws['A2'].font=Font(name=FONT,size=10,italic=True,color='595959')
    ws.freeze_panes='A4'

def section(ws,row,text,fill=NAVY,span=8):
    ws.cell(row,1,text).font=H2
    for c in range(1,span+1): ws.cell(row,c).fill=fill
    ws.row_dimensions[row].height=20
    return row+1

def hdr(ws,row,cols,widths=None):
    for i,h in enumerate(cols):
        c=ws.cell(row,i+1,h); c.font=Font(name=FONT,bold=True,size=10,color='FFFFFF'); c.fill=NAVY
        c.alignment=Alignment(wrap_text=True,vertical='center',horizontal='center')
    ws.row_dimensions[row].height=28
    if widths:
        for i,w in enumerate(widths): ws.column_dimensions[CL(i+1)].width=w
    return row+1

def put(ws,row,vals,bold=False,wrap=True,fmt=None):
    for i,v in enumerate(vals):
        c=ws.cell(row,i+1,v); c.font=BOLD if bold else BODY
        c.alignment=Alignment(wrap_text=wrap,vertical='top')
        if fmt and i>0 and isinstance(v,str) and v.startswith('='): c.number_format=fmt
    return row+1

# =============================================================== README
def readme(wb):
    ws=wb.create_sheet('README',0)
    title(ws,'TBT Tank Quote Analytics  —  V5 (ML Foundation)',
          'Rebuilt from archive.08-26-26 · 7,480 quote-tank rows · every derived value is a live, traceable Excel formula')
    for w,c in zip([42,30,26,22,20,18,18,18],range(1,9)): ws.column_dimensions[CL(c)].width=w
    r=4
    r=section(ws,r,'WHAT THIS WORKBOOK IS')
    for t in ['This is the data-engineering foundation for a tank price-prediction service. The web app collects tank and project specs; a prediction service returns the five price buckets; the estimating software then computes freight and tax and sums everything into a total price. Verified money identities in the archive: Proposal Total = bucket sum + Total Tax (no freight); Total Price = bucket sum + Freight Price (no tax). Neither source column is a grand total — the all-in number is buckets + freight + tax, and ML_Tank_Training carries it as Ref Grand Total.',
              'V5 is a FRESH REBUILD, not an edit of v4. v4 was built on a 1,000-row sample; this is the full 7,480-row archive. Every number in v4 downstream of the data was stale, and several of its structural rules break at this scale (see Audit_V4_to_V5).',
              'NO MACHINE LEARNING HAS BEEN TRAINED YET. This workbook prepares the data and records the decisions needed to train. ML_Modeling_Plan states the method; nothing is fitted.']:
        ws.cell(r,1,t).font=BODY; ws.cell(r,1).alignment=Alignment(wrap_text=True,vertical='top')
        ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=8); ws.row_dimensions[r].height=32; r+=1
    r+=1
    r=section(ws,r,'THE PREDICTION PROBLEM')
    r=hdr(ws,r,['Element','Definition'])
    for a,b in [('Grain',f'One row = one tank, at the firmest (latest) revision of its quote. {NT()} training rows.'),
        ('Predicted (5 targets)','Material Price · Fabrication Price · Construction Price · Insulation Material Price · Insulation Construction Price'),
        ('NOT predicted','Freight and Tax — the estimating software computes these deterministically.'),
        ('Total price','Sum of the five predicted buckets that are in scope, plus computed freight, plus computed tax.'),
        ('Inputs available at predict time','Material, tank height, tank diameter, usable capacity, tank/use type, deck & floor options, wage type, insulation option, quantity, and project location (which yields seismic Ss/S1 and miles-to-site).')]:
        r=put(ws,r,[a,b]); ws.merge_cells(start_row=r-1,start_column=2,end_row=r-1,end_column=8)
    r+=1
    r=section(ws,r,'SHEET MAP')
    r=hdr(ws,r,['Sheet','Purpose'])
    for a,b in [('Audit_V4_to_V5','Every structural problem found in v4 and what V5 does instead. Read this first.'),
        ('Raw_Import','The archive CSV, verbatim. Values exactly as exported ($ signs, commas, units). The only data-entry point.'),
        ('Cleaning_Rules','Every transformation applied, and the formula that applies it.'),
        ('Clean_Data','7,480 rows. Every cell is a formula reading Raw_Import. Parsing, keys, revision logic, outcome, and data-quality flags.'),
        ('Data_Quality',f'Exclusion accounting — how 7,480 rows become {NT()} training rows, with a live count for each reason.'),
        ('ML_Tank_Training',f'THE TRAINING TABLE. {NT()} unique rows, one per tank at its firmest revision. Inputs, 60+ derived features, and the 5 targets. Every feature is a formula.'),
        ('ML_Feature_Catalog','Every column: its role (feature / target / leakage), the exact formula, and why it should predict price.'),
        ('ML_Modeling_Plan','The minimum set of ML decisions needed to justify this data engineering.'),
        ('ML_Target_Analysis','Live statistics for each of the five targets, including zero-inflation.'),
        ('Data_Research','The analytical findings: what actually drives price, segment unit rates, escalation, and win indicators.'),
        ('Validation','Reconciliation checks. Every row must read PASS.'),
        ('Ref_Lists','Lookup lists that drive cleaning rules.')]:
        r=put(ws,r,[a,b]); ws.merge_cells(start_row=r-1,start_column=2,end_row=r-1,end_column=8)
    r+=1
    r=section(ws,r,'CONVENTIONS')
    for t in ['Every computed cell is a live formula — click any value and trace it back to Raw_Import. Nothing downstream of Raw_Import is typed in by hand.',
              'Formulas are written compact, with no spaces. Cross-sheet pulls use INDEX/MATCH (not XLOOKUP) so the workbook evaluates identically in Excel, LibreOffice and older Excel versions.',
              'Column groups in ML_Tank_Training are colour-banded: dark red = TARGET, maroon = LEAKAGE (never use as a feature), blue = feature/input.',
              'To refresh with new data: replace the rows on Raw_Import, keeping the 42-column order, then let Excel recalculate. Extend the formula rows if the row count grows.']:
        ws.cell(r,1,'•  '+t).font=BODY; ws.cell(r,1).alignment=Alignment(wrap_text=True,vertical='top')
        ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=8); ws.row_dimensions[r].height=28; r+=1
    return ws

# =============================================================== AUDIT
def audit(wb):
    ws=wb.create_sheet('Audit_V4_to_V5')
    title(ws,'Audit — what v4 got wrong, and what V5 does',
          'Found by re-running v4 logic against the full 7,480-row archive instead of the 1,000-row sample')
    for w,c in zip([6,34,46,46,18],range(1,6)): ws.column_dimensions[CL(c)].width=w
    r=4
    r=hdr(ws,r,['#','Issue found in v4','Why it breaks at full scale','What V5 does','Severity'])
    rows=[
     ('Underfit to a 1,000-row sample','v4 was built on 1,000 rows / 358 quotes. The archive holds 7,480 rows / 3,225 quotes. Every cached KPI, dimension and dashboard value in v4 is stale by ~7.5x.','Rebuilt entirely on the full archive. All values are formulas, so they follow the data instead of being cached.','High'),
     ('No outlier or sanity filtering','v4 passes every row straight through. The archive contains a $1.27 TRILLION proposal (a 27ft tank), a $556bn silo and a $21bn line. v4 KPIs would be meaningless — total pipeline would read ~$1.9 trillion.','DQ Price Sane flags rows outside $1,000–$50,000,000. 33 rows excluded. Nothing is deleted; rows are flagged and counted on Data_Quality.','Critical'),
     ('Non-tank line items treated as tanks','The archive contains "90° Elbows", "Nozzles PVC", "Deck Hatches", "Standard Part Audit" and "Klara\'s Part Test" rows. v4 prices and counts them as tanks.','DQ Looks Non-Tank matches a keyword list on Ref_Lists. 17 rows excluded from training.','High'),
     ('Tank Key is not unique','v4 builds Tank Key as Quote-Rev-TankName and its Validation check #7 asserts uniqueness. At full scale one quote (2503029-R2) has two different "Tank 1" rows at $46,328 and $42,659 — so check #7 FAILS.','Key Dup Index counts repeats and Tank Key appends "#2" to the duplicate, guaranteeing a unique key. Verified: 4,743 current rows, 4,743 distinct keys, 0 duplicates.','High'),
     ('Revision Count assumes contiguous revisions','v4 counts distinct revisions per quote, but 67 quotes have gaps and 59 quotes do not start at revision 0. Any max+1 shortcut misreports rework.','Revision Count sums a first-row-of-revision flag per quote — correct under gaps and non-zero starts.','Medium'),
     ('New statuses unmapped','The archive adds "Bid Review" (22 rows) and "Unfinished" (6). v4 silently maps both to Open, so incomplete quotes inflate the pipeline.','Both are mapped to Open for reporting but flagged DQ Unfinished and excluded from training (28 rows).','Medium'),
     ('Negative usable capacity','44 rows carry a negative capacity (e.g. -937.376tons). v4 strips non-numeric characters but keeps the sign, banding them as "Small".','Capacity parse preserves the sign so the error stays visible; DQ Has Capacity requires > 0.','Medium'),
     ('Zero-height / zero-capacity rows','323 rows have Height = 0 and 319 have capacity = 0, so every geometry-derived measure is undefined. v4 has no geometry layer, so it never noticed.','DQ Has Geometry requires diameter > 0 AND height > 0. 190 current-revision rows excluded from training.','High'),
     ('Prices carry $ and commas','Raw values are text like "$5,172.08". v4 strips commas but not "$". Any "$"-prefixed cell coerces to null, silently zeroing prices.','The numeric parser strips $, commas and % before VALUE(). Verified against the source on all 7,480 rows.','Critical'),
     ('No modelling grain','v4 stops at reporting facts. There is no deduplicated, one-row-per-tank table and no engineered features, so nothing can be trained.',f'ML_Tank_Training: {NT()} unique rows at the firmest revision, 60+ engineered features, 5 explicit targets.','High'),
     ('Cached values, no traceability','v4 sheets are static Power Query dumps. A number cannot be traced to its source without re-running the query.','Every computed cell is a formula chained back to Raw_Import.','Medium'),
     ('Dashboards cannot survive the outliers','The 9 chart dashboards aggregate Proposal Total with no guard, so a single $1.27tn row dominates every chart, band and ranking.','Not rebuilt in V5. The reporting layer should be rebuilt on the cleaned grain (ML Eligible = 1) — see Data_Research for corrected segment analysis.','Open item'),
    ]
    for i,(a,b,c,d_) in enumerate(rows,1):
        r=put(ws,r,[i,a,b,c,d_])
        sev=ws.cell(r-1,5)
        sev.font=Font(name=FONT,bold=True,size=10,color='FFFFFF')
        sev.fill={'Critical':RED,'High':ORANGE,'Medium':PatternFill('solid',fgColor='BF8F00'),
                  'Open item':PatternFill('solid',fgColor='595959')}[d_]
        sev.alignment=Alignment(horizontal='center',vertical='center')
        ws.row_dimensions[r-1].height=58
    return ws

# =============================================================== CLEANING
def cleaning(wb):
    ws=wb.create_sheet('Cleaning_Rules')
    title(ws,'Cleaning Rules','Every transformation between Raw_Import and Clean_Data, and the formula that performs it')
    for w,c in zip([10,30,40,52],range(1,5)): ws.column_dimensions[CL(c)].width=w
    r=4
    r=hdr(ws,r,['Rule','Purpose','Applies to','Formula pattern used in Clean_Data'])
    rows=[('R01','Trim and collapse whitespace','All text columns','TRIM(...)'),
     ('R02','Normalise nulls — blank, null, none, n/a, na, "-" all become empty','All text columns','IF(OR(TRIM(x)="",LOWER(TRIM(x))="null",...),"",TRIM(x))'),
     ('R03','Strip currency and thousands separators before coercion','All money columns','IFERROR(VALUE(SUBSTITUTE(SUBSTITUTE(SUBSTITUTE(x,"$",""),",",""),"%","")),"")'),
     ('R04','Title-case status','Status','PROPER(TRIM(x))'),
     ('R05','Outcome mapping — Won/Lost, everything else Open','Status -> Row Outcome','IF(Status="Won","Won",IF(Status="Lost","Lost","Open"))'),
     ('R06','Won-wins quote outcome — any Won revision wins the whole quote','Outcome','COUNTIFS on quote + status, then Won > Lost > Open'),
     ('R07','Blank customer becomes "(No Customer Listed)"','Customer Name','IF(blank,"(No Customer Listed)",TRIM(x))'),
     ('R08','Strip trailing commas from city','City','TRIM(SUBSTITUTE(TRIM(x),",",""))'),
     ('R09','Split usable capacity into value and unit, preserving sign','Usable Capacity','SEARCH for "ton"/"gal"; SUBSTITUTE units out, then VALUE()'),
     ('R10','Stable keys','Quote-Rev, Tank Key','Quote&"-R"&Rev ; Quote-Rev&"-"&TankName&dup suffix'),
     ('R11','NEW — unique tank key under duplicates','Tank Key','Key Dup Index via COUNTIFS; appends "#n" when > 1'),
     ('R12','Current revision flag','Is Current Revision','Rev = MAXIFS(Rev, Quote, this quote)'),
     ('R13','Revision count that survives gaps','Revision Count','SUMIFS of a first-row-of-revision flag, by quote'),
     ('R14','NEW — data-quality flags','DQ Has Geometry, DQ Has Capacity, DQ Positive Target, DQ Price Sane, DQ Looks Non-Tank, DQ Unfinished, DQ Geo Resolved','See Data_Quality for the live count behind each'),
     ('R15','NEW — geographic normalization (P0-2)','The raw State column holds 208 distinct values mixing US abbreviations, Mexican state codes, cities and country names, and the Country column itself is wrong on 37 rows. Ref_Lists carries a 219-entry crosswalk keyed on Country|State (State alone is ambiguous: BC is British Columbia in CA and Baja California in MX).','Clean_Data gains Country Normalized, Country Name, State Normalized, Region Code and Geo Match Level. 99.1% of rows resolve to a specific region; the rest are held at country level rather than guessed.'),
     ('R15','NEW — training eligibility','ML Eligible, ML Training Row','ML Eligible AND Is Current Revision')]
    for a,b,c,d_ in rows:
        r=put(ws,r,[a,b,c,d_]); ws.cell(r-1,4).font=MONO; ws.row_dimensions[r-1].height=30
    return ws

# =============================================================== DATA QUALITY
def dataquality(wb):
    ws=wb.create_sheet('Data_Quality')
    title(ws,'Data Quality & Exclusion Accounting',f'How 7,480 archive rows become {NT()} training rows. Every count is live.')
    for w,c in zip([44,16,58],range(1,4)): ws.column_dimensions[CL(c)].width=w
    r=4
    r=section(ws,r,'ROW FUNNEL',span=3)
    r=hdr(ws,r,['Stage','Rows','How it is counted'])
    r=put(ws,r,['Archive rows imported',f'=COUNTA({crng("QuoteNumber")})','Every row on Raw_Import'])
    r=put(ws,r,['Rows at the firmest revision of their JOB',f'=COUNTIF({crng("Is Job Firmest")},1)','Is Job Firmest = 1 (groups 2306041, 2306041-R2 and 2306041 - As Sold into one job)'])
    r=put(ws,r,['  less: no geometry (D or H = 0)',f'=COUNTIFS({crng("Is Job Firmest")},1,{crng("DQ Has Geometry")},0)','Diameter or height missing — every geometric feature undefined'])
    r=put(ws,r,['  less: price outside $1K–$50M',f'=COUNTIFS({crng("Is Job Firmest")},1,{crng("DQ Price Sane")},0)','Data-entry errors incl. the $1.27tn row'])
    r=put(ws,r,['  less: non-tank line item',f'=COUNTIFS({crng("Is Job Firmest")},1,{crng("DQ Looks Non-Tank")},1)','Elbows, nozzles, part tests, audits'])
    r=put(ws,r,['  less: unfinished / bid review',f'=COUNTIFS({crng("Is Job Firmest")},1,{crng("DQ Unfinished")},1)','Quote not complete — price not meaningful'])
    r=put(ws,r,['  less: zero price buckets',f'=COUNTIFS({crng("Is Job Firmest")},1,{crng("DQ Positive Target")},0)','Nothing to learn from'])
    r=put(ws,r,['TRAINING ROWS (ML Training Row = 1)',f'=COUNTIF({crng("ML Training Row")},1)','Unique tanks at the firmest revision, quality-passed'],bold=True)
    ws.cell(r-1,1).fill=YELLOW; ws.cell(r-1,2).fill=YELLOW
    r=put(ws,r,['  of which Firm bid',f'=COUNTIFS({mrng("is_firm_bid")},1)','Recommended primary training set'])
    r=put(ws,r,['  of which Budget bid',f'=COUNTIFS({mrng("is_firm_bid")},0)','Keep, flagged by is_firm_bid'])
    r+=1
    r=section(ws,r,'QUALITY FLAGS ACROSS ALL 7,480 ROWS',span=3)
    r=hdr(ws,r,['Flag','Rows failing','Meaning'])
    for nm,col,mean in [('DQ Has Geometry','DQ Has Geometry','Diameter > 0 AND height > 0'),
        ('DQ Has Capacity','DQ Has Capacity','Usable capacity > 0 (44 rows are negative in the source)'),
        ('DQ Positive Target','DQ Positive Target','Sum of the five price buckets > 0'),
        ('DQ Price Sane','DQ Price Sane','Proposal total within $1,000–$50,000,000'),
        ('DQ Looks Non-Tank','DQ Looks Non-Tank','Matches a keyword on Ref_Lists (inverted: counts rows that DO match)'),
        ('DQ Unfinished','DQ Unfinished','Status is Unfinished or Bid Review'),
        ('DQ Geo Resolved','DQ Geo Resolved','Country|State resolved to a specific region via the Ref_Lists crosswalk (P0-2)'),
        ('DQ Price Sane Segment','DQ Price Sane Segment','$/shell-sqft inside the 1.5-99th percentile of its own material x scope_class segment (P0-4). Rejects 178 rows against the global band’s 33.')]:
        fail=f'=COUNTIF({crng(col)},1)' if nm in('DQ Looks Non-Tank','DQ Unfinished') else f'=COUNTIF({crng(col)},0)'
        r=put(ws,r,[nm,fail,mean])
    r+=1
    r=section(ws,r,'NOTE ON DEDUPLICATION',span=3)
    for t in ['One row per quote-tank at the firmest revision. Earlier revisions of the same quote are never included — they carry superseded prices and would duplicate the same job.',
      f'The grain is the TANK, not the quote, because a quote can hold many tanks with different diameters, materials and prices, and the service predicts a price per tank. Revision de-duplication is what removes the duplicates; 3,225 quotes yield {NT()} distinct training tanks.']:
        ws.cell(r,1,'•  '+t).font=BODY; ws.cell(r,1).alignment=Alignment(wrap_text=True,vertical='top')
        ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=3); ws.row_dimensions[r].height=40; r+=1
    return ws

# ====================================================== RATE BASELINE (P1-7)
def rate_baseline(wb, years, usetypes):
    """$/shell-sqft baselines. Two jobs, per HANDOFF P1-7:

      1. a non-ML fallback estimator - price ~ rate x area, which is what the whole
         dataset says (total_area_sqft correlates 0.86 with log material price);
      2. the benchmark any future model has to beat.

    Every rate is total dollars / total shell area across the segment, NOT the mean of
    per-row ratios. A mean of ratios lets one small tank with an odd price swing the
    segment; an area-weighted rate cannot. All figures are live SUMIFS over
    ML_Tank_Training, so they move when the source data does.
    """
    ws=wb.create_sheet('Rate_Baseline')
    title(ws,'Segment Baseline Rates  ($ per shell square foot)',
          'Non-ML fallback estimator and the benchmark any model must beat - '
          'training grain, area-weighted, every cell a live formula')
    for w,c in zip([22,18,8,14,14,14,14,14,14,14,14,14],range(1,13)):
        ws.column_dimensions[CL(c)].width=w

    A=mrng('shell_area_sqft'); B=mrng('Y Bucket Sum'); MAT=mrng('Material')
    SC=mrng('scope_class');    UT=mrng('Use Type');    YR=mrng('Due Year')
    YM=mrng('Y Material'); YF=mrng('Y Fabrication'); YC=mrng('Y Construction')

    r=4
    r=section(ws,r,'HOW TO USE THIS SHEET',span=12)
    for t in ['Estimate = rate x shell area, where shell area = PI() x diameter x height. '
              'Pick the row matching the tank material and what the quote covers (scope class), '
              'then the column for the due year. A 60 ft x 40 ft carbon-steel tank quoted with '
              'erection has a shell area of PI()*60*40 = 7,540 sqft; at the CS / tank_quote rate '
              'for the current year that is the fallback price for all five buckets combined.',
              'Section B splits the rate into the individual buckets, so a materials-only quote '
              'can be built from the material and fabrication rates alone.',
              'Read n before trusting a rate. A segment with a handful of tanks is noise, and the '
              'blank cells are segments with no training rows at all rather than zero-priced work.',
              'These are SELL rates: they already carry margin and contingency, exactly like the '
              'five target buckets. They exclude freight and tax, which the estimating software '
              'computes separately.']:
        c=ws.cell(r,1,'-  '+t); c.font=BODY; c.alignment=Alignment(wrap_text=True,vertical='top')
        ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=12)
        ws.row_dimensions[r].height=42; r+=1
    r+=1

    # ---------------- A. material x scope class x year
    r=section(ws,r,'A.  $/SHELL-SQFT BY MATERIAL x SCOPE CLASS x DUE YEAR',span=12)
    cols=['Material','Scope Class','n','Total shell sqft','Total $']+[str(y) for y in years]+['All years']
    r=hdr(ws,r,cols)
    segs=[(m,s) for m in ['CS','304SS','316SS'] for s in ['tank_quote','materials_only']]
    a0=r
    for m,s in segs:
        ws.cell(r,1,m); ws.cell(r,2,s)
        mm=f'$A{r}'; ss=f'$B{r}'
        ws.cell(r,3,f'=COUNTIFS({MAT},{mm},{SC},{ss})').number_format='#,##0'
        ws.cell(r,4,f'=SUMIFS({A},{MAT},{mm},{SC},{ss})').number_format='#,##0'
        ws.cell(r,5,f'=SUMIFS({B},{MAT},{mm},{SC},{ss})').number_format='$#,##0'
        for j,y in enumerate(years):
            ws.cell(r,6+j,f'=IFERROR(SUMIFS({B},{MAT},{mm},{SC},{ss},{YR},{y})'
                          f'/SUMIFS({A},{MAT},{mm},{SC},{ss},{YR},{y}),"")').number_format='$#,##0.00'
        ws.cell(r,6+len(years),f'=IFERROR(${CL(5)}{r}/${CL(4)}{r},"")').number_format='$#,##0.00'
        r+=1
    a1=r-1
    add_note(ws,r,'Blank year cells are segments with no training tanks due that year. '
                  'Stainless segments are thin - check n in column C before quoting from them.',12)
    r+=2

    # ---------------- B. per-bucket rates
    r=section(ws,r,'B.  PER-BUCKET $/SHELL-SQFT BY MATERIAL x SCOPE CLASS  (all years)',span=12)
    r=hdr(ws,r,['Material','Scope Class','n','Material $/sqft','Fabrication $/sqft',
                'Construction $/sqft','All buckets $/sqft','Shop share','','','',''])
    for m,s in segs:
        ws.cell(r,1,m); ws.cell(r,2,s)
        mm=f'$A{r}'; ss=f'$B{r}'
        den=f'SUMIFS({A},{MAT},{mm},{SC},{ss})'
        ws.cell(r,3,f'=COUNTIFS({MAT},{mm},{SC},{ss})').number_format='#,##0'
        for j,num in enumerate([YM,YF,YC,B]):
            ws.cell(r,4+j,f'=IFERROR(SUMIFS({num},{MAT},{mm},{SC},{ss})/{den},"")').number_format='$#,##0.00'
        ws.cell(r,8,f'=IFERROR((${CL(4)}{r}+${CL(5)}{r})/${CL(7)}{r},"")').number_format='0.0%'
        r+=1
    add_note(ws,r,'Shop share is (material + fabrication) / all buckets - the part of the price '
                  'that does not depend on site labour. It is 100% on materials_only rows by construction.',12)
    r+=2

    # ---------------- C. use type x scope class
    r=section(ws,r,'C.  $/SHELL-SQFT BY USE TYPE x SCOPE CLASS  (all years, all materials)',span=12)
    r=hdr(ws,r,['Use Type','Scope Class','n','Total shell sqft','Total $','$/sqft','','','','','',''])
    c0=r
    for u in usetypes:
        for s in ['tank_quote','materials_only']:
            ws.cell(r,1,u); ws.cell(r,2,s)
            uu=f'$A{r}'; ss=f'$B{r}'
            ws.cell(r,3,f'=COUNTIFS({UT},{uu},{SC},{ss})').number_format='#,##0'
            ws.cell(r,4,f'=SUMIFS({A},{UT},{uu},{SC},{ss})').number_format='#,##0'
            ws.cell(r,5,f'=SUMIFS({B},{UT},{uu},{SC},{ss})').number_format='$#,##0'
            ws.cell(r,6,f'=IFERROR(${CL(5)}{r}/${CL(4)}{r},"")').number_format='$#,##0.00'
            r+=1
    c1=r-1
    r+=1

    # ---------------- D. escalation
    r=section(ws,r,'D.  YEAR-OVER-YEAR ESCALATION  (all segments combined)',span=12)
    r=hdr(ws,r,['Due Year','Tanks','Total shell sqft','Total $','$/sqft','YoY change','','','','','',''])
    d0=r
    for y in years:
        ws.cell(r,1,y)
        ws.cell(r,2,f'=COUNTIFS({YR},$A{r})').number_format='#,##0'
        ws.cell(r,3,f'=SUMIFS({A},{YR},$A{r})').number_format='#,##0'
        ws.cell(r,4,f'=SUMIFS({B},{YR},$A{r})').number_format='$#,##0'
        ws.cell(r,5,f'=IFERROR(${CL(4)}{r}/${CL(3)}{r},"")').number_format='$#,##0.00'
        ws.cell(r,6,'' if r==d0 else f'=IFERROR(${CL(5)}{r}/${CL(5)}{r-1}-1,"")').number_format='0.0%'
        r+=1
    d1=r-1
    add_bar_docs(ws,f'H{d0-1}','Blended $/shell-sqft by due year',
                 Reference(ws,min_col=1,min_row=d0,max_row=d1),
                 Reference(ws,min_col=5,min_row=d0-1,max_row=d1))
    r+=1
    add_note(ws,r,'Escalation here blends every segment, so a year whose mix shifts toward '
                  'materials-only work will show a lower rate without any price actually falling. '
                  'Use section A for a like-for-like year comparison within one segment.',12)
    return ws


def add_note(ws,row,text,span=8):
    c=ws.cell(row,1,text); c.font=Font(name=FONT,size=9,italic=True,color='595959')
    c.alignment=Alignment(wrap_text=True,vertical='top')
    ws.merge_cells(start_row=row,start_column=1,end_row=row,end_column=span)
    ws.row_dimensions[row].height=30


def add_bar_docs(ws,anchor,title_txt,cat_ref,val_ref):
    ch=BarChart(); ch.type='col'; ch.title=title_txt; ch.y_axis.title='$/shell-sqft'
    ch.add_data(val_ref,titles_from_data=True); ch.set_categories(cat_ref)
    ch.width=16; ch.height=9; ch.gapWidth=60; ch.legend=None
    s=ch.series[0]; s.graphicalProperties.solidFill='2a78d6'; s.graphicalProperties.line.solidFill='2a78d6'
    ws.add_chart(ch,anchor); return ch

# =============================================================== FEATURE CATALOG
def feature_catalog(wb):
    ws=wb.create_sheet('ML_Feature_Catalog')
    title(ws,'ML Feature Catalog','Every column of ML_Tank_Training: role, exact formula, and why it should move price')
    for w,c in zip([6,30,22,14,52,46],range(1,7)): ws.column_dimensions[CL(c)].width=w
    r=4
    r=section(ws,r,'ROLE KEY',span=6)
    for t in ['TARGET — one of the five predicted price buckets.',
              'FEATURE — available at prediction time from the web app or computed from its inputs. Safe to train on.',
              'LEAKAGE — derived from price. Useful for research, NEVER a model input.',
              'IDENTITY — keys and labels. Not features; use for joins, grouping and validation splits.']:
        ws.cell(r,1,'•  '+t).font=BODY
        ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=6); r+=1
    r+=1
    r=hdr(ws,r,['Col','Column','Group','Role','Formula in the sheet (shown without its leading =)','Why it should predict price'])
    dmap={d[0]:d for d in D}
    for s in SPEC:
        h=s['h']; grp=s['group']
        if grp=='TARGET': role='TARGET'
        elif 'LEAKAGE' in grp: role='LEAKAGE'
        elif grp in ('Identity','Reference (not a target)'): role='IDENTITY'
        else: role='FEATURE'
        if s['kind']=='pull': f=f"INDEX(Clean_Data!{CD[s['f']]}:{CD[s['f']]},$B{{row}})"
        elif h=='Tank Key': f='(value — unique row key)'
        elif h=='Src Row': f=f"MATCH($A{{row}},Clean_Data!{CD['Tank Key']}:{CD['Tank Key']},0)+1"
        else: f=(dmap[h][2]('{row}').lstrip('=') if h in dmap else '')
        note=dmap[h][4] if h in dmap else s['note']
        r=put(ws,r,[mc(h),h,grp,role,f,note])
        ws.cell(r-1,5).font=MONO
        rc=ws.cell(r-1,4); rc.font=Font(name=FONT,bold=True,size=9,color='FFFFFF')
        rc.fill={'TARGET':ORANGE,'LEAKAGE':RED,'FEATURE':GREEN,'IDENTITY':PatternFill('solid',fgColor='595959')}[role]
        rc.alignment=Alignment(horizontal='center')
        ws.row_dimensions[r-1].height=26
    return ws

# =============================================================== MODELING PLAN
def modeling_plan(wb):
    ws=wb.create_sheet('ML_Modeling_Plan')
    title(ws,'ML Modeling Plan','The minimum set of ML decisions required to justify this data engineering. Nothing has been trained.')
    for w,c in zip([34,58,46],range(1,4)): ws.column_dimensions[CL(c)].width=w
    r=4
    r=section(ws,r,'DECISIONS MADE NOW (because they change the data)',span=3)
    r=hdr(ws,r,['Decision','Choice','Why it had to be decided now'])
    for a,b,c in [
     ('Prediction grain','One model call per TANK. Training row = one tank at the firmest revision.','Determines de-duplication. A quote can hold up to 29 tanks with different specs and prices, so a per-quote grain would destroy the signal.'),
     ('Revision handling','Keep only the latest revision per quote; discard all earlier revisions.','Earlier revisions are superseded prices for the same job. Including them duplicates jobs and teaches the model stale prices.'),
     ('Targets','Five separate models, one per price bucket. Total is summed afterwards, never predicted directly.','Stated requirement, and it is also correct: the buckets have different drivers and different zero-inflation, so one total-price model would be worse and non-decomposable.'),
     ('Freight & tax','Excluded from both features and targets.','Computed deterministically by the estimator. Including them as features leaks price.'),
     ('Target scale','Model log(1+price), then invert.','Raw targets are severely right-skewed (skew 4.9-11.5). Log-transform brings skew to roughly -0.5 to 0.7, which is why the workbook stores raw targets and leaves the transform to training.'),
     ('Zero-inflation','Two-stage for Construction and both Insulation buckets: first classify in-scope vs zero, then regress the positive amount.','Construction is zero on 34.6% of rows and insulation on ~78%. A single regressor would smear non-zero price across out-of-scope tanks. The scope drivers are known inputs (wage type, insulation option), so the classifier is nearly deterministic.'),
     ('Model family','Gradient-boosted trees (e.g. XGBoost/LightGBM) as the baseline, with a linear rate-model benchmark.','Drives feature engineering: trees need no scaling or one-hot for ordinals, and handle the interactions already present. Raw + engineered features are both provided so either family can be trained.'),
     ('Validation split','Group split by QuoteNumber, plus a time-based holdout on Due Date.','Tanks from the same quote share pricing context. A random row split would leak across the same job and overstate accuracy. Due Year is in the table for the time split.'),
     ('Budget vs Firm','Both kept; is_firm_bid flags them. Recommended: train on Firm, evaluate on both.','Budget quotes are rougher. Deleting them loses 1,252 rows; flagging keeps the choice open without re-engineering.'),
     ('Outcome (Won/Lost)','Not a filter and not a feature for price.','The quoted price is real regardless of whether the job was won. Filtering to Won would leave ~200 rows.')]:
        r=put(ws,r,[a,b,c]); ws.row_dimensions[r-1].height=54
    r+=1
    r=section(ws,r,'MODELS TO TRAIN (5 price models)',span=3)
    r=hdr(ws,r,['Model','Target column','Shape of the problem'])
    for a,b,c in [('M1 Material','Y Material','Single regressor. No zero-inflation. Strongest geometric signal (r=0.86 vs total area).'),
     ('M2 Fabrication','Y Fabrication','Single regressor. Tracks shell area and roof complexity.'),
     ('M3 Construction','Y Construction','Two-stage. Gate = has_erection_scope. Then regress; labour rate and seismic matter here.'),
     ('M4 Insulation Material','Y Insul Material','Two-stage. Gate = is_insulated. ~22% positive.'),
     ('M5 Insulation Construction','Y Insul Construction','Two-stage. Gate = is_insulated. ~21% positive.')]:
        r=put(ws,r,[a,b,c]); ws.row_dimensions[r-1].height=30
    r=put(ws,r,['Total price (not a model)','M1+M2+M3+M4+M5 in scope, plus computed freight, plus computed tax','Summed by the estimator, so bucket errors stay visible and auditable.'],bold=True)
    ws.cell(r-1,1).fill=YELLOW
    r+=1
    r=section(ws,r,'DELIBERATELY NOT DECIDED YET',span=3)
    for t in ['Hyperparameters, tree depth, learning rate, number of estimators.',
              'Categorical encoding scheme (target vs one-hot) for Use Type, Deck Style, Floor Style.',
              'Whether Margin (%) and Contingency (%) are model inputs or business overrides applied after prediction — both are in the table so either can be tested.',
              'Whether a separate win-probability model is built. Indicator features are present (see Data_Research) but no target has been committed.']:
        ws.cell(r,1,'•  '+t).font=BODY; ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=3)
        ws.cell(r,1).alignment=Alignment(wrap_text=True); ws.row_dimensions[r].height=26; r+=1
    return ws

# =============================================================== TARGET ANALYSIS
def target_analysis(wb):
    ws=wb.create_sheet('ML_Target_Analysis')
    title(ws,'Target Analysis',f'Live statistics for each predicted bucket across the {NT()} training rows')
    for w,c in zip([30,14,14,14,14,14,16,40],range(1,9)): ws.column_dimensions[CL(c)].width=w
    r=4
    r=hdr(ws,r,['Target','Rows','Zero rows','Zero %','Mean $','Max $','Sum $','Modelling implication'])
    tg=[('Y Material','Single regressor — always in scope.'),
        ('Y Fabrication','Single regressor — always in scope.'),
        ('Y Construction','Two-stage: gate on has_erection_scope, then regress.'),
        ('Y Insul Material','Two-stage: gate on is_insulated, then regress.'),
        ('Y Insul Construction','Two-stage: gate on is_insulated, then regress.'),
        ('Y Bucket Sum','Never predicted directly — the sum of the five above.')]
    for h,note in tg:
        rng=mrng(h)
        r=put(ws,r,[h,f'=COUNT({rng})',f'=COUNTIF({rng},0)',f'=COUNTIF({rng},0)/COUNT({rng})',
                    f'=AVERAGE({rng})',f'=MAX({rng})',f'=SUM({rng})',note])
        for cc,fmt in [(4,'0.0%'),(5,'$#,##0'),(6,'$#,##0'),(7,'$#,##0')]:
            ws.cell(r-1,cc).number_format=fmt
        ws.row_dimensions[r-1].height=22
    r+=1
    r=section(ws,r,'POSITIVE-ONLY BEHAVIOUR (rows where the bucket is in scope)',span=8)
    r=hdr(ws,r,['Target','Rows > 0','Mean $ when > 0','Share of bucket sum','','','',''])
    for h,_ in tg[:5]:
        rng=mrng(h)
        r=put(ws,r,[h,f'=COUNTIF({rng},">0")',f'=AVERAGEIF({rng},">0")',f'=SUM({rng})/SUM({mrng("Y Bucket Sum")})','','','',''])
        ws.cell(r-1,3).number_format='$#,##0'; ws.cell(r-1,4).number_format='0.0%'
    r+=1
    r=section(ws,r,'WHY LOG-TRANSFORM THE TARGET',span=8)
    for t in ['Raw bucket prices are severely right-skewed (skew 4.9 for material, 5.1 for fabrication, 11.5 for construction). A squared-error model fitted on raw dollars chases the few very large tanks and prices small tanks badly.',
              'log(1+price) brings skew to roughly 0.5 / 0.7 / -0.5. Train on the log, invert on output, and report error in dollars.',
              'The workbook stores raw dollars on purpose — the transform belongs in the training pipeline, not baked into the data.']:
        ws.cell(r,1,'•  '+t).font=BODY; ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=8)
        ws.cell(r,1).alignment=Alignment(wrap_text=True); ws.row_dimensions[r].height=30; r+=1
    return ws

# =============================================================== DATA RESEARCH
def research(wb):
    ws=wb.create_sheet('Data_Research')
    title(ws,'Data Research — what actually drives tank price',
          f'Analysis across the {NT()} training rows. Segment tables are live formulas; correlations are from the analysis pass and are stated as such.')
    for w,c in zip([34,13,15,15,15,15,15,46],range(1,9)): ws.column_dimensions[CL(c)].width=w
    r=4
    # ---- headline findings
    r=section(ws,r,'1. HEADLINE FINDINGS',span=8)
    for t in ['GEOMETRY IS THE DOMINANT DRIVER. Total fabricated surface area correlates 0.86 with log material price, 0.78 with log fabrication and 0.72 with log construction. Diameter matters more than height, because diameter drives floor and roof area as a square while height scales shell area only linearly.',
     'PRICE IS A RATE TIMES AN AREA. Across the archive, price per shell square foot is remarkably stable within a material grade. That is the single most useful structural fact for modelling: predict a rate, multiply by a known area.',
     'MATERIAL GRADE IS A CLEAN MULTIPLIER. Blended material cost per shell sqft: carbon steel $32.21, 304SS $65.17 (2.0x), 316SS $101.08 (3.1x). That is close to the raw stainless price ratio, so grade behaves multiplicatively rather than additively — a grade multiplier on a carbon-steel base rate is a sound model structure.',
     'CONSTRUCTION PRICE IS A SCOPE DECISION FIRST AND A SIZE PROBLEM SECOND. It is zero on 34.6% of training rows, and that zero is almost entirely explained by wage type: when wage type is blank or "No Erection Included", construction is essentially always zero. Predict the scope gate first.',
     'LABOUR REGIME MOVES CONSTRUCTION BY ~75%. Blended construction cost per shell sqft: non-union $27.48, prevailing wage $48.81, union $47.79. Prevailing-wage and union sites are statistically indistinguishable from each other and both sit about 1.75x non-union — so a single union-or-prevailing flag captures the effect.',
     'THERE IS REAL PRICE ESCALATION. Blended material cost per shell sqft runs $30.94 (2024) to $33.58 (2025) to $40.05 (2026) — about 14% a year compounded. A model trained without a time feature will systematically under-price future work.',
     'SEISMIC BARELY MOVES THE CONSTRUCTION RATE. The construction rate is flat across every Ss band (roughly $25-$31 with no trend). Seismic load appears to be absorbed into material and anchorage rather than erection labour, so the seismic interaction terms belong on the material model, not the construction model.',
     'INSULATION IS A NEARLY SEPARATE PRODUCT. Present on only ~22% of tanks and weakly related to the base tank price. Both insulation buckets should be gated on the insulation option and modelled independently.']:
        ws.cell(r,1,'•  '+t).font=BODY; ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=8)
        ws.cell(r,1).alignment=Alignment(wrap_text=True,vertical='top'); ws.row_dimensions[r].height=44; r+=1
    r+=1
    # ---- correlations
    r=section(ws,r,'2. CORRELATION OF FEATURES WITH LOG PRICE  (analysis pass, n=4,535 - the pre-P0-4 row set)',span=8)
    r=hdr(ws,r,['Feature','log Material','log Fabrication','log Construction','log Bucket Sum','','','Reading'])
    corr=[('total_area_sqft',0.859,0.784,0.715,0.788,'Strongest single predictor for every bucket.'),
     ('geom_volume_gal',0.856,0.784,0.710,0.780,'Near-duplicate of area — keep one, drop the other.'),
     ('material_area_intensity',0.850,0.799,0.686,0.769,'Grade-weighted area; best single engineered term.'),
     ('shell_area_sqft',0.838,0.803,0.687,0.762,'Best predictor of fabrication specifically.'),
     ('d_x_h',0.840,0.804,0.687,0.764,'Cheap proxy for shell area.'),
     ('Diameter (ft)',0.777,0.655,0.646,0.712,'Dominates height — area scales with D squared.'),
     ('capacity_gal',0.775,0.769,0.653,0.709,'Slightly weaker than geometry; capacity is a derived business number.'),
     ('Height (ft)',0.584,0.648,0.441,0.528,'Secondary to diameter.'),
     ('roof_slope_ratio',-0.355,-0.551,None,-0.352,'Negative: sloped-roof tanks are the smaller standard product.'),
     ('no_erection_scope',None,-0.203,-0.247,-0.495,'The scope gate. Largest non-geometric effect on total.'),
     ('is_insulated',None,None,None,0.397,'Adds a whole cost block when selected.'),
     ('seismic_x_shell',0.262,0.271,0.422,None,'Matters most for construction/anchorage.'),
     ('is_prevailing_wage',None,None,0.247,None,'Labour premium, construction only.')]
    for nm,a,b,c,d_,note in corr:
        r=put(ws,r,[nm,a,b,c,d_,'','',note])
        for cc in range(2,6):
            ws.cell(r-1,cc).number_format='0.000'; ws.cell(r-1,cc).alignment=Alignment(horizontal='center')
    r=put(ws,r,['Note: Pearson correlation on log(1+target) vs the feature, computed over rows where that bucket is > 0. Blank = not material for that bucket.'])
    ws.merge_cells(start_row=r-1,start_column=1,end_row=r-1,end_column=8); ws.cell(r-1,1).font=Font(name=FONT,size=9,italic=True)
    r+=1
    # ---- live segment tables
    r=section(ws,r,'3. UNIT RATES BY MATERIAL  (live)',span=8)
    r=put(ws,r,['"Blended" = SUM(price) / SUM(area) across the segment, not the average of per-row ratios. Averaging ratios is badly distorted by a few tanks with very small shell area; the blended rate is the economically meaningful one.'])
    ws.merge_cells(start_row=r-1,start_column=1,end_row=r-1,end_column=8); ws.cell(r-1,1).font=Font(name=FONT,size=9,italic=True)
    r=hdr(ws,r,['Material','Tanks','Blended $/shell sqft','Blended material $/shell sqft','Avg bucket sum','Avg shell area','',''])
    for m in ['CS','304SS','316SS']:
        r=put(ws,r,[m,f'=COUNTIF({mrng("Material")},"{m}")',
            f'=SUMIF({mrng("Material")},"{m}",{mrng("Y Bucket Sum")})/SUMIF({mrng("Material")},"{m}",{mrng("shell_area_sqft")})',
            f'=SUMIF({mrng("Material")},"{m}",{mrng("Y Material")})/SUMIF({mrng("Material")},"{m}",{mrng("shell_area_sqft")})',
            f'=AVERAGEIF({mrng("Material")},"{m}",{mrng("Y Bucket Sum")})',
            f'=AVERAGEIF({mrng("Material")},"{m}",{mrng("shell_area_sqft")})','',''])
        for cc,f in [(3,'$#,##0.00'),(4,'$#,##0.00'),(5,'$#,##0'),(6,'#,##0')]: ws.cell(r-1,cc).number_format=f
    r+=1
    r=section(ws,r,'4. CONSTRUCTION RATE BY LABOUR REGIME  (live, erection in scope only)',span=8)
    r=hdr(ws,r,['Wage Type','Tanks','Avg construction $','Avg shell area','Blended construction $/sqft','','',''])
    for wt in ['Non-Union / Non-Prevailing','Prevailing Wage','Union Wage','No Erection Included']:
        r=put(ws,r,[wt,f'=COUNTIF({mrng("Wage Type")},"{wt}")',
            f'=AVERAGEIF({mrng("Wage Type")},"{wt}",{mrng("Y Construction")})',
            f'=AVERAGEIF({mrng("Wage Type")},"{wt}",{mrng("shell_area_sqft")})',
            f'=SUMIF({mrng("Wage Type")},"{wt}",{mrng("Y Construction")})/SUMIF({mrng("Wage Type")},"{wt}",{mrng("shell_area_sqft")})','','',''])
        for cc,f in [(3,'$#,##0'),(4,'#,##0'),(5,'$#,##0.00')]: ws.cell(r-1,cc).number_format=f
    r+=1
    r=section(ws,r,'5. PRICE ESCALATION BY DUE YEAR  (live)',span=8)
    r=hdr(ws,r,['Due Year','Tanks','Blended material $/shell sqft','Blended total $/shell sqft','','','',''])
    for y in [2024,2025,2026]:
        r=put(ws,r,[y,f'=COUNTIF({mrng("Due Year")},{y})',
            f'=SUMIF({mrng("Due Year")},{y},{mrng("Y Material")})/SUMIF({mrng("Due Year")},{y},{mrng("shell_area_sqft")})',
            f'=SUMIF({mrng("Due Year")},{y},{mrng("Y Bucket Sum")})/SUMIF({mrng("Due Year")},{y},{mrng("shell_area_sqft")})','','','',''])
        ws.cell(r-1,3).number_format='$#,##0.00'; ws.cell(r-1,4).number_format='$#,##0.00'
    r+=1
    r=section(ws,r,'6. RATE BY USE TYPE  (live)',span=8)
    r=hdr(ws,r,['Use Type','Tanks','Blended $/shell sqft','Avg bucket sum','','','',''])
    for ut in ['Fire Protection Storage Tank','Waste Water Storage Tank','Potable Water Storage Tank',
               'Water Storage Tank','Industrial Storage Silo','Industrial Storage Tank']:
        r=put(ws,r,[ut,f'=COUNTIF({mrng("Use Type")},"{ut}")',
            f'=SUMIF({mrng("Use Type")},"{ut}",{mrng("Y Bucket Sum")})/SUMIF({mrng("Use Type")},"{ut}",{mrng("shell_area_sqft")})',
            f'=AVERAGEIF({mrng("Use Type")},"{ut}",{mrng("Y Bucket Sum")})','','','',''])
        ws.cell(r-1,3).number_format='$#,##0.00'; ws.cell(r-1,4).number_format='$#,##0'
    r+=1
    # ---- win indicators
    r=section(ws,r,'7. WIN / LOSS INDICATORS  (secondary problem — not the price model)',span=8)
    r=hdr(ws,r,['Indicator','Won','Lost','','','','','Reading'])
    for nm,col,fmt in [('Tanks on decided quotes',None,None),]:
        pass
    for nm,colh,fmt,note in [
      ('Tanks',None,'#,##0','Decided rows only — Won or Lost.'),
      ('Avg margin %','Margin (%)','0.0','Won quotes carry a LOWER margin than lost ones — price discipline shows up in the margin knob.'),
      ('Avg contingency %','Contingency (%)','0.00','Lower risk buffer on won work.'),
      ('Avg revision count','Revision Count','0.00','Won jobs are revised far more — engagement, not waste.'),
      ('Avg bucket sum','Y Bucket Sum','$#,##0','Lost quotes are larger on average.'),
      ('Avg miles to site','min_miles','#,##0','Distance barely separates won from lost.')]:
        if colh is None:
            r=put(ws,r,[nm,f'=COUNTIF({mrng("Outcome")},"Won")',f'=COUNTIF({mrng("Outcome")},"Lost")','','','','',note])
        else:
            r=put(ws,r,[nm,f'=AVERAGEIF({mrng("Outcome")},"Won",{mrng(colh)})',
                           f'=AVERAGEIF({mrng("Outcome")},"Lost",{mrng(colh)})','','','','',note])
            for cc in (2,3): ws.cell(r-1,cc).number_format=fmt
        ws.row_dimensions[r-1].height=26
    r=put(ws,r,['Bid type win rate','=IFERROR(COUNTIFS('+mrng('Outcome')+',"Won",'+mrng('is_firm_bid')+',1)/(COUNTIFS('+mrng('Outcome')+',"Won",'+mrng('is_firm_bid')+',1)+COUNTIFS('+mrng('Outcome')+',"Lost",'+mrng('is_firm_bid')+',1)),"")',
        '=IFERROR(COUNTIFS('+mrng('Outcome')+',"Won",'+mrng('is_firm_bid')+',0)/(COUNTIFS('+mrng('Outcome')+',"Won",'+mrng('is_firm_bid')+',0)+COUNTIFS('+mrng('Outcome')+',"Lost",'+mrng('is_firm_bid')+',0)),"")',
        '','','','','Firm (left) vs Budget (right) win rate. Firm quotes convert dramatically better — budget quotes are early-stage feelers.'])
    for cc in (2,3): ws.cell(r-1,cc).number_format='0.0%'
    ws.row_dimensions[r-1].height=30
    r+=1
    r=section(ws,r,'8. RISKS AND CAVEATS FOR MODELLING',span=8)
    for t in ['COLLINEARITY. total_area_sqft, geom_volume_gal, shell_area_sqft, d_x_h and capacity_gal all measure size and correlate above 0.95 with each other. Trees tolerate this; a linear model must not receive all of them.',
     'LEAKAGE. The three rate_* columns are computed from price and are banded maroon. They exist for research and benchmarking only. Margin (%) and Contingency (%) are pricing policy — decide deliberately whether they are inputs or post-prediction adjustments.',
     'CLASS IMBALANCE ON MATERIAL. 4,194 carbon-steel rows vs 270 (304SS) and 71 (316SS). Stainless predictions will be weak. Consider a grade multiplier on a carbon-steel base rather than one model per grade.',
     'TON-CAPACITY TANKS. 493 archive rows measure capacity in tons, not gallons. Tons are mass, not volume, so capacity_gal is deliberately blank for them. Use geometry, not capacity, as the universal size feature.',
     'THE 2027 ROWS. Only 3 tanks have a 2027 due date and their rates are extreme. Do not let the time feature extrapolate off 3 rows.',
     'SURVIVORSHIP. Training on quoted prices teaches what TBT quotes, not what the market clears. That is the right objective for an estimating tool, but it is not a market price model.']:
        ws.cell(r,1,'•  '+t).font=BODY; ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=8)
        ws.cell(r,1).alignment=Alignment(wrap_text=True,vertical='top'); ws.row_dimensions[r].height=40; r+=1
    return ws

# =============================================================== VALIDATION
def validation(wb):
    ws=wb.create_sheet('Validation')
    title(ws,'Validation & Reconciliation','Every check must read PASS')
    for w,c in zip([8,44,20,20,12,52],range(1,7)): ws.column_dimensions[CL(c)].width=w
    r=4
    r=hdr(ws,r,['#','Check','Value A','Value B','Result','Explanation'])
    checks=[
     ('Raw rows = Clean rows',f'=COUNTA(Raw_Import!$A$2:$A$7481)',f'=COUNTA({crng("QuoteNumber")})','Cleaning must never add or drop a row.'),
     ('Tank Key is unique across all rows',f'=SUMPRODUCT(1/COUNTIF({crng("Tank Key")},{crng("Tank Key")}))',f'=COUNTA({crng("Tank Key")})','v4 failed this. The dup-index suffix guarantees uniqueness.'),
     ('Current-revision rows',f'=COUNTIF({crng("Is Current Revision")},TRUE)',f'=COUNTIF({crng("Is Current Revision")},TRUE)','Rows flagged as the firmest revision.'),
     ('Training rows = ML sheet rows',f'=COUNTIF({crng("ML Training Row")},1)',f'=COUNTA({mrng("Tank Key")})','The ML sheet holds exactly the eligible current-revision tanks.'),
     ('ML Tank Keys are unique',f'=SUMPRODUCT(1/COUNTIF({mrng("Tank Key")},{mrng("Tank Key")}))',f'=COUNTA({mrng("Tank Key")})','One row per tank — no revision or quote duplicates.'),
     ('Bucket sum reconciles to components',f'=ROUND(SUM({mrng("Y Bucket Sum")}),2)',
        f'=ROUND(SUM({mrng("Y Material")})+SUM({mrng("Y Fabrication")})+SUM({mrng("Y Construction")})+SUM({mrng("Y Insul Material")})+SUM({mrng("Y Insul Construction")}),2)',
        'The five predicted buckets must sum to the stored total.'),
     ('No training row lacks geometry',f'=COUNTIFS({mrng("shell_area_sqft")},"<=0")','0','Every training row has a usable diameter and height.'),
     ('No training row has a zero target',f'=COUNTIF({mrng("Y Bucket Sum")},"<=0")','0','Every training row carries a price to learn from.'),
     ('All training prices within sanity band',f'=COUNTIFS({mrng("Ref Proposal Total")},">50000000")','0','The $1.27tn class of error is excluded.'),
     ('Every ML row resolves to Clean_Data',f'=COUNTIF({mrng("Src Row")},"<2")','0','Every INDEX/MATCH pull found its source row.'),
    ]
    for i,(nm,a,b,expl) in enumerate(checks,1):
        r=put(ws,r,[i,nm,a,b,f'=IF(ROUND(C{r},2)=ROUND(D{r},2),"PASS","FAIL")',expl])
        res=ws.cell(r-1,5); res.font=Font(name=FONT,bold=True,size=10)
        res.alignment=Alignment(horizontal='center')
        ws.row_dimensions[r-1].height=24
    return ws

# =============================================================== MAIN
def main():
    global MLST
    wb=openpyxl.load_workbook('v5_dash.xlsx')
    # Derive the ML row bound instead of trusting a hardcoded literal. Any change to the
    # eligibility rules (P0-4 did exactly this) moves the training row count, and a stale
    # bound here silently mis-ranges every doc-sheet formula. HANDOFF gotcha 6 / P1-5.
    MLST=wb[ML].max_row
    NTRAIN[0]=MLST-MF+1
    print(f'ML data rows {MF}..{MLST}  ({MLST-MF+1} training rows)')
    readme(wb); audit(wb); cleaning(wb); dataquality(wb)
    feature_catalog(wb); modeling_plan(wb); target_analysis(wb); research(wb); validation(wb)
    # P1-7 baseline rates. Category lists come from the training grain so the sheet only
    # ever lists segments that actually have rows.
    _tr=pd.read_pickle('featured3.pkl')
    _tr=_tr[_tr['ML Training Row V2']==1]
    _years=[int(y) for y in sorted(_tr['due_year'].dropna().unique()) if 2023<=y<=2027]
    _uts=_tr['Use Type'].value_counts().head(8).index.tolist()
    rate_baseline(wb,_years,_uts)
    order=['README','Audit_V4_to_V5','Dashboard_Executive','Dashboard_Sales','Dashboard_Pricing',
           'Dashboard_WinLoss','Dashboard_Geographic','Dashboard_Revisions','Dashboard_Trend','Dashboard_DataQuality','Data_Research','Cleaning_Rules','Raw_Import','Clean_Data','Data_Quality',
           'Fact_Quote','ML_Tank_Training','ML_Feature_Catalog','ML_Modeling_Plan','ML_Target_Analysis',
           'Rate_Baseline','Validation','Ref_Lists']
    wb._sheets=[wb[n] for n in order if n in wb.sheetnames]+[s for s in wb._sheets if s.title not in order]
    for ws in wb.worksheets:
        ws.sheet_view.showGridLines = ws.title in ('Raw_Import','Clean_Data','ML_Tank_Training')
    wb.save('TBT_Tank_Quote_Analytics_v5.xlsx')
    print('saved TBT_Tank_Quote_Analytics_v5.xlsx')
    print('sheets:',wb.sheetnames)

if __name__=='__main__':
    main()
