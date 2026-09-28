"""V5 builder - part 4: Fact_Quote (job grain) + executive dashboards with charts."""
import pandas as pd, numpy as np, openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter as CL
from openpyxl.chart import BarChart, LineChart, Reference
from build_core import C as CD
from build_ml import L as ML_L

FONT='Arial'
NAVY=PatternFill('solid',fgColor='1F3864'); LT=PatternFill('solid',fgColor='D9E1F2')
KPI=PatternFill('solid',fgColor='EAF0FA'); YELLOW=PatternFill('solid',fgColor='FFF2CC')
H1=Font(name=FONT,bold=True,size=16,color='1F3864')
H2=Font(name=FONT,bold=True,size=12,color='FFFFFF')
BOLD=Font(name=FONT,bold=True,size=10); BODY=Font(name=FONT,size=10)
SER=['2a78d6','eb6834','1baf7a','eda100']          # validated categorical slots
THIN=Side(style='thin',color='BFBFBF'); BOX=Border(left=THIN,right=THIN,top=THIN,bottom=THIN)

# P1-5: derived from the source row count, not typed. HANDOFF gotcha 6.
from build_core import N as N_CLEAN
CF,CLST=2,N_CLEAN+1
def crng(h): return f"Clean_Data!${CD[h]}${CF}:${CD[h]}${CLST}"
FQ_FIRST=None; FQ_LAST=None
def qrng(col): return f"Fact_Quote!${col}${FQ_FIRST}:${col}${FQ_LAST}"

def title(ws,t,sub=''):
    ws['A1']=t; ws['A1'].font=H1
    if sub: ws['A2']=sub; ws['A2'].font=Font(name=FONT,size=10,italic=True,color='595959')

def section(ws,row,text,span=10):
    ws.cell(row,1,text).font=H2
    for c in range(1,span+1): ws.cell(row,c).fill=NAVY
    ws.row_dimensions[row].height=20
    return row+1

def hdr(ws,row,cols,widths=None):
    for i,h in enumerate(cols):
        c=ws.cell(row,i+1,h); c.font=Font(name=FONT,bold=True,size=10,color='FFFFFF'); c.fill=NAVY
        c.alignment=Alignment(wrap_text=True,vertical='center',horizontal='center')
    ws.row_dimensions[row].height=26
    if widths:
        for i,w in enumerate(widths): ws.column_dimensions[CL(i+1)].width=w
    return row+1

def kpi_tile(ws,row,col,label,formula,fmt):
    l=ws.cell(row,col,label); l.font=Font(name=FONT,size=9,color='595959'); l.fill=KPI; l.border=BOX
    l.alignment=Alignment(horizontal='center')
    v=ws.cell(row+1,col,formula); v.font=Font(name=FONT,bold=True,size=14,color='1F3864')
    v.fill=KPI; v.number_format=fmt; v.border=BOX
    v.alignment=Alignment(horizontal='center')

def add_bar(ws,anchor,title_txt,cat_ref,val_ref,ylab,color=SER[0],horiz=False,width=18,height=9):
    ch=BarChart(); ch.type='bar' if horiz else 'col'; ch.style=None
    ch.title=title_txt; ch.y_axis.title=ylab; ch.x_axis.title=None
    ch.add_data(val_ref,titles_from_data=True); ch.set_categories(cat_ref)
    ch.width=width; ch.height=height; ch.gapWidth=60
    s=ch.series[0]; s.graphicalProperties.solidFill=color; s.graphicalProperties.line.solidFill=color
    ch.legend=None
    ws.add_chart(ch,anchor); return ch

def add_multibar(ws,anchor,title_txt,cat_ref,val_ref,ylab,width=18,height=9):
    ch=BarChart(); ch.type='col'; ch.title=title_txt; ch.y_axis.title=ylab
    ch.add_data(val_ref,titles_from_data=True); ch.set_categories(cat_ref)
    ch.width=width; ch.height=height; ch.gapWidth=60
    for i,s in enumerate(ch.series):
        s.graphicalProperties.solidFill=SER[i%len(SER)]
        s.graphicalProperties.line.solidFill=SER[i%len(SER)]
    ws.add_chart(ch,anchor); return ch

def add_line(ws,anchor,title_txt,cat_ref,val_ref,ylab,width=18,height=9):
    ch=LineChart(); ch.title=title_txt; ch.y_axis.title=ylab
    ch.add_data(val_ref,titles_from_data=True); ch.set_categories(cat_ref)
    ch.width=width; ch.height=height
    s=ch.series[0]; s.graphicalProperties.line.solidFill=SER[0]; s.graphicalProperties.line.width=22000
    s.smooth=False; ch.legend=None
    ws.add_chart(ch,anchor); return ch

# ============================================================ GEOGRAPHIC (P1-1)
def dash_geo(wb,countries,states,bands):
    """Geographic dashboard. Unblocked by P0-2: every figure here groups on
    Country Normalized / State Normalized, never on the raw Country/State columns,
    which mix US abbreviations, Mexican state codes, cities and country names and are
    outright wrong on 37 rows."""
    ws=wb.create_sheet('Dashboard_Geographic')
    title(ws,'Geographic Dashboard',
          'Job grain - groups on the normalized Country/State from the Ref_Lists crosswalk (P0-2), not the raw source fields')
    for w,c in zip([30,14,14,16,16,14,14,16,16,16],range(1,11)): ws.column_dimensions[CL(c)].width=w
    P=qrng(FQ['Proposal Total']); O=qrng(FQ['Outcome']); W=qrng(FQ['Is Won']); D=qrng(FQ['Is Decided'])
    CN=qrng(FQ['Country Name']); CNZ=qrng(FQ['Country Normalized']); SN=qrng(FQ['State Normalized'])
    DOM=qrng(FQ['Is Domestic']); T=qrng(FQ['Tank Count']); FR=qrng(FQ['Freight Price'])
    DB=qrng(FQ['Distance Band'])

    r=4; r=section(ws,r,'DOMESTIC vs INTERNATIONAL')
    tiles=[('Domestic pipeline',f'=SUMIF({DOM},1,{P})','$#,##0,,"M"'),
           ('International pipeline',f'=SUMIF({DOM},0,{P})','$#,##0,,"M"'),
           ('Domestic win rate',f'=IFERROR(SUMIFS({W},{DOM},1)/SUMIFS({D},{DOM},1),"")','0.0%'),
           ('Intl win rate',f'=IFERROR(SUMIFS({W},{DOM},0)/SUMIFS({D},{DOM},0),"")','0.0%'),
           ('Countries',f'=SUMPRODUCT(({CNZ}<>"")/COUNTIF({CNZ},{CNZ}&""))','#,##0'),
           ('Regions',f'=SUMPRODUCT(({SN}<>"")/COUNTIF({SN},{SN}&""))','#,##0'),
           ('Domestic freight %',f'=IFERROR(SUMIF({DOM},1,{FR})/SUMIF({DOM},1,{P}),"")','0.0%'),
           ('Intl freight %',f'=IFERROR(SUMIF({DOM},0,{FR})/SUMIF({DOM},0,{P}),"")','0.0%')]
    for i,(l,f,fmt) in enumerate(tiles[:4]): kpi_tile(ws,r,i*2+1,l,f,fmt)
    r+=3
    for i,(l,f,fmt) in enumerate(tiles[4:]): kpi_tile(ws,r,i*2+1,l,f,fmt)
    r+=3
    ws.cell(r,1,'Read win rates with their denominator: only 210 of 3,171 jobs have been decided '
                '(127 Won / 83 Lost); the other 2,961 are still Open. The "Decided" column below is '
                'that denominator - a country or state with a handful of decided jobs will show an '
                'extreme win rate that carries no signal.'
           ).font=Font(name=FONT,size=9,italic=True,color='595959')
    ws.cell(r,1).alignment=Alignment(wrap_text=True,vertical='top')
    ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=8)
    ws.row_dimensions[r].height=30
    r+=2

    r=section(ws,r,'PIPELINE BY COUNTRY')
    hr=r; r=hdr(ws,r,['Country','Jobs','Tanks','Pipeline $','Won $','Decided','Win rate','Freight %','',''])
    c0=r
    for cv in countries:
        ws.cell(r,1,cv); a=f'$A{r}'
        ws.cell(r,2,f'=COUNTIF({CN},{a})').number_format='#,##0'
        ws.cell(r,3,f'=SUMIF({CN},{a},{T})').number_format='#,##0'
        ws.cell(r,4,f'=SUMIF({CN},{a},{P})').number_format='$#,##0'
        ws.cell(r,5,f'=SUMIFS({P},{CN},{a},{O},"Won")').number_format='$#,##0'
        ws.cell(r,6,f'=SUMIFS({D},{CN},{a})').number_format='#,##0'
        ws.cell(r,7,f'=IFERROR(SUMIFS({W},{CN},{a})/SUMIFS({D},{CN},{a}),"")').number_format='0.0%'
        ws.cell(r,8,f'=IFERROR(SUMIF({CN},{a},{FR})/SUMIF({CN},{a},{P}),"")').number_format='0.0%'
        r+=1
    c1=r-1
    add_bar(ws,f'I{hr}','Pipeline by country',
            Reference(ws,min_col=1,min_row=c0,max_row=c1),
            Reference(ws,min_col=4,min_row=hr,max_row=c1),'Pipeline $',horiz=True,height=11)
    r+=1

    r=section(ws,r,'PIPELINE BY US STATE  (top 15 by pipeline)')
    hr=r; r=hdr(ws,r,['State','Jobs','Tanks','Pipeline $','Won $','Decided','Win rate','Freight %','',''])
    s0=r
    for sv in states:
        ws.cell(r,1,sv); a=f'$A{r}'
        ws.cell(r,2,f'=COUNTIFS({SN},{a},{CNZ},"US")').number_format='#,##0'
        ws.cell(r,3,f'=SUMIFS({T},{SN},{a},{CNZ},"US")').number_format='#,##0'
        ws.cell(r,4,f'=SUMIFS({P},{SN},{a},{CNZ},"US")').number_format='$#,##0'
        ws.cell(r,5,f'=SUMIFS({P},{SN},{a},{CNZ},"US",{O},"Won")').number_format='$#,##0'
        ws.cell(r,6,f'=SUMIFS({D},{SN},{a},{CNZ},"US")').number_format='#,##0'
        ws.cell(r,7,f'=IFERROR(SUMIFS({W},{SN},{a},{CNZ},"US")/SUMIFS({D},{SN},{a},{CNZ},"US"),"")').number_format='0.0%'
        ws.cell(r,8,f'=IFERROR(SUMIFS({FR},{SN},{a},{CNZ},"US")/SUMIFS({P},{SN},{a},{CNZ},"US"),"")').number_format='0.0%'
        r+=1
    s1=r-1
    add_bar(ws,f'I{hr}','Pipeline by US state',
            Reference(ws,min_col=1,min_row=s0,max_row=s1),
            Reference(ws,min_col=4,min_row=hr,max_row=s1),'Pipeline $',horiz=True,height=11,color=SER[2])
    r+=1

    r=section(ws,r,'FREIGHT BY DISTANCE BAND')
    hr=r; r=hdr(ws,r,['Distance to site','Jobs','Pipeline $','Freight $','Freight % of proposal','','','','',''])
    b0=r
    for bv in bands:
        ws.cell(r,1,bv); a=f'$A{r}'
        ws.cell(r,2,f'=COUNTIF({DB},{a})').number_format='#,##0'
        ws.cell(r,3,f'=SUMIF({DB},{a},{P})').number_format='$#,##0'
        ws.cell(r,4,f'=SUMIF({DB},{a},{FR})').number_format='$#,##0'
        ws.cell(r,5,f'=IFERROR(SUMIF({DB},{a},{FR})/SUMIF({DB},{a},{P}),"")').number_format='0.0%'
        r+=1
    b1=r-1
    add_bar(ws,f'G{hr}','Freight as % of proposal, by distance to site',
            Reference(ws,min_col=1,min_row=b0,max_row=b1),
            Reference(ws,min_col=5,min_row=hr,max_row=b1),'Freight %',color=SER[1],height=10)
    r+=1
    ws.cell(r,1,'Note: 813 source rows carry zero freight on sites over 100 miles out. '
                'DQ Freight Present flags them; whether that is FOB / customer pickup or missing data '
                'is still open (HANDOFF P1-6). Freight % bands are understated to that extent.'
           ).font=Font(name=FONT,size=9,italic=True,color='595959')
    ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=7)
    return ws

# ====================================================== REVISIONS / REWORK (P1-2)
def dash_revisions(wb,managers):
    """Revision and rework dashboard. All of this data existed and none of it was shown.

    The headline finding it makes visible: won jobs are revised far more than lost ones.
    That is not a lever - it is selection. A job only keeps getting revised while the
    customer is still engaged, so revision count is an OUTCOME of interest, not a cause of
    it. Read it as an engagement signal and as a measure of what rework costs, never as
    'revise more to win more'.
    """
    ws=wb.create_sheet('Dashboard_Revisions')
    title(ws,'Revision & Rework Dashboard',
          'Job grain - how many times a job is repriced, what that does to the price, and where the rework sits')
    for w,c in zip([30,14,14,16,16,16,16,16,16,16],range(1,11)): ws.column_dimensions[CL(c)].width=w
    P=qrng(FQ['Proposal Total']); O=qrng(FQ['Outcome']); W=qrng(FQ['Is Won']); D=qrng(FQ['Is Decided'])
    RC=qrng(FQ['Job Revision Count']); GR=qrng(FQ['Quote Growth Pct']); FRT=qrng(FQ['First Revision Total'])
    MG=qrng(FQ['Sales Manager']); VT=qrng(FQ['Scope Class'])

    r=4; r=section(ws,r,'REWORK HEADLINE')
    tiles=[('Avg revisions - WON',f'=IFERROR(AVERAGEIFS({RC},{O},"Won"),"")','0.00'),
           ('Avg revisions - LOST',f'=IFERROR(AVERAGEIFS({RC},{O},"Lost"),"")','0.00'),
           ('Avg revisions - OPEN',f'=IFERROR(AVERAGEIFS({RC},{O},"Open"),"")','0.00'),
           ('Jobs revised 2+ times',f'=COUNTIF({RC},">1")','#,##0'),
           ('Avg growth, repriced jobs',f'=IFERROR(AVERAGEIFS({GR},{RC},">1",{GR},">=-0.5",{GR},"<=2"),"")','0.0%'),
           ('Pipeline on repriced jobs',f'=SUMIF({RC},">1",{P})','$#,##0,,"M"'),
           ('First-revision value',f'=SUM({FRT})','$#,##0,,"M"'),
           ('Firmest value',f'=SUM({P})','$#,##0,,"M"')]
    for i,(l,f,fmt) in enumerate(tiles[:4]): kpi_tile(ws,r,i*2+1,l,f,fmt)
    r+=3
    for i,(l,f,fmt) in enumerate(tiles[4:]): kpi_tile(ws,r,i*2+1,l,f,fmt)
    r+=3
    ws.cell(r,1,'Won jobs carry more revisions than lost ones - but that is selection, not a lever: '
                'a job keeps getting repriced only while the customer is still engaged. The sharper '
                'signal is in the PRICE MOVEMENT, not the count. On jobs that were repriced, won jobs '
                'moved +3.2% while lost jobs moved +20.0%. A large upward re-quote is a losing sign, '
                'most likely scope growth or a correction the customer will not absorb - worth a look '
                'the moment a revision pushes a job up by double digits.'
           ).font=Font(name=FONT,size=9,italic=True,color='595959')
    ws.cell(r,1).alignment=Alignment(wrap_text=True,vertical='top')
    ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=8); ws.row_dimensions[r].height=30
    r+=2

    r=section(ws,r,'REVISIONS BY OUTCOME')
    hr=r; r=hdr(ws,r,['Outcome','Jobs','Avg revisions','Max revisions','Pipeline $','Avg growth (repriced)','','','',''])
    o0=r
    for ov in ['Won','Lost','Open']:
        ws.cell(r,1,ov); a=f'$A{r}'
        ws.cell(r,2,f'=COUNTIF({O},{a})').number_format='#,##0'
        ws.cell(r,3,f'=IFERROR(AVERAGEIFS({RC},{O},{a}),"")').number_format='0.00'
        ws.cell(r,4,f'=_xlfn.MAXIFS({RC},{O},{a})').number_format='0'
        ws.cell(r,5,f'=SUMIF({O},{a},{P})').number_format='$#,##0'
        ws.cell(r,6,f'=IFERROR(AVERAGEIFS({GR},{O},{a},{RC},">1",{GR},">=-0.5",{GR},"<=2"),"")').number_format='0.0%'
        r+=1
    o1=r-1
    add_bar(ws,f'H{hr}','Average revisions by outcome',
            Reference(ws,min_col=1,min_row=o0,max_row=o1),
            Reference(ws,min_col=3,min_row=hr,max_row=o1),'Revisions',height=8)
    r+=1

    r=section(ws,r,'PRICE MOVEMENT FROM FIRST TO FIRMEST REVISION')
    hr=r; r=hdr(ws,r,['Revisions on the job','Jobs','First-rev $','Firmest $','Change $','Avg growth %','Win rate','','',''])
    g0=r
    for lbl,lo,hi in [('1 (never repriced)',1,1),('2',2,2),('3',3,3),('4',4,4),('5 or more',5,99)]:
        ws.cell(r,1,lbl)
        crit=f'{RC},">={lo}",{RC},"<={hi}"'
        ws.cell(r,2,f'=COUNTIFS({crit})').number_format='#,##0'
        ws.cell(r,3,f'=SUMIFS({FRT},{crit})').number_format='$#,##0'
        ws.cell(r,4,f'=SUMIFS({P},{crit})').number_format='$#,##0'
        ws.cell(r,5,f'=${CL(4)}{r}-${CL(3)}{r}').number_format='$#,##0'
        ws.cell(r,6,f'=IFERROR(AVERAGEIFS({GR},{RC},">={lo}",{RC},"<={hi}",{GR},">=-0.5",{GR},"<=2"),"")').number_format='0.0%'
        ws.cell(r,7,f'=IFERROR(SUMIFS({W},{crit})/SUMIFS({D},{crit}),"")').number_format='0.0%'
        r+=1
    g1=r-1
    add_bar(ws,f'J{hr}','Average quote growth by revision count',
            Reference(ws,min_col=1,min_row=g0,max_row=g1),
            Reference(ws,min_col=6,min_row=hr,max_row=g1),'Growth %',color=SER[1],height=9)
    r+=1

    r=section(ws,r,'REWORK CONCENTRATION BY SALES MANAGER')
    hr=r; r=hdr(ws,r,['Sales Manager','Jobs','Avg revisions','Jobs repriced','Repriced share','Avg growth (repriced)','Pipeline $','','',''])
    m0=r
    for mv in managers:
        ws.cell(r,1,mv); a=f'$A{r}'
        ws.cell(r,2,f'=COUNTIF({MG},{a})').number_format='#,##0'
        ws.cell(r,3,f'=IFERROR(AVERAGEIFS({RC},{MG},{a}),"")').number_format='0.00'
        ws.cell(r,4,f'=COUNTIFS({MG},{a},{RC},">1")').number_format='#,##0'
        ws.cell(r,5,f'=IFERROR(${CL(4)}{r}/${CL(2)}{r},"")').number_format='0.0%'
        ws.cell(r,6,f'=IFERROR(AVERAGEIFS({GR},{MG},{a},{RC},">1",{GR},">=-0.5",{GR},"<=2"),"")').number_format='0.0%'
        ws.cell(r,7,f'=SUMIF({MG},{a},{P})').number_format='$#,##0'
        r+=1
    m1=r-1
    add_bar(ws,f'J{hr}','Share of jobs repriced, by manager',
            Reference(ws,min_col=1,min_row=m0,max_row=m1),
            Reference(ws,min_col=5,min_row=hr,max_row=m1),'Repriced share',horiz=True,color=SER[2],height=10)
    r+=1
    ws.cell(r,1,'Growth columns cover REPRICED jobs only (revision count > 1) and are trimmed to '
                '-50%..+200%. Across all jobs the figure would be 0% by construction, since a job still '
                'at its first revision has no growth. Trimming keeps a single re-scoped re-quote from '
                'dragging the average.'
           ).font=Font(name=FONT,size=9,italic=True,color='595959')
    ws.cell(r,1).alignment=Alignment(wrap_text=True,vertical='top'); ws.row_dimensions[r].height=30
    ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=8)
    return ws


# ====================================================== MONTHLY / QUARTERLY TREND (P1-3)
def dash_trend(wb,periods,years):
    """Everything in this workbook was annual. Due Date supports month granularity, so
    this is the seasonality and monthly-trend view (HANDOFF P1-3)."""
    ws=wb.create_sheet('Dashboard_Trend')
    title(ws,'Monthly & Quarterly Trend',
          'Job grain - pipeline, deal size and blended $/shell-sqft by month and by quarter')
    for w,c in zip([16,12,14,16,16,16,16,16,16,16],range(1,11)): ws.column_dimensions[CL(c)].width=w
    P=qrng(FQ['Proposal Total']); O=qrng(FQ['Outcome']); W=qrng(FQ['Is Won']); D=qrng(FQ['Is Decided'])
    PER=qrng(FQ['Due Period']); MO=qrng(FQ['Due Month']); YR=qrng(FQ['Due Year'])
    AR=qrng(FQ['Total Shell SqFt']); BS=qrng(FQ['Bucket Sum']); T=qrng(FQ['Tank Count'])

    r=4; r=section(ws,r,'MONTHLY PIPELINE')
    hr=r; r=hdr(ws,r,['Month','Jobs','Tanks','Pipeline $','Avg deal $','Shell sqft','$/shell-sqft','Win rate','',''])
    p0=r
    for pv in periods:
        ws.cell(r,1,pv); a=f'$A{r}'
        ws.cell(r,2,f'=COUNTIF({PER},{a})').number_format='#,##0'
        ws.cell(r,3,f'=SUMIF({PER},{a},{T})').number_format='#,##0'
        ws.cell(r,4,f'=SUMIF({PER},{a},{P})').number_format='$#,##0'
        ws.cell(r,5,f'=IFERROR(${CL(4)}{r}/${CL(2)}{r},"")').number_format='$#,##0'
        ws.cell(r,6,f'=SUMIF({PER},{a},{AR})').number_format='#,##0'
        ws.cell(r,7,f'=IFERROR(SUMIF({PER},{a},{BS})/${CL(6)}{r},"")').number_format='$#,##0.00'
        ws.cell(r,8,f'=IFERROR(SUMIFS({W},{PER},{a})/SUMIFS({D},{PER},{a}),"")').number_format='0.0%'
        r+=1
    p1=r-1
    add_line(ws,f'J{hr}','Pipeline by month',
             Reference(ws,min_col=1,min_row=p0,max_row=p1),
             Reference(ws,min_col=4,min_row=hr,max_row=p1),'Pipeline $',width=22,height=9)
    add_line(ws,f'J{hr+20}','Blended $/shell-sqft by month',
             Reference(ws,min_col=1,min_row=p0,max_row=p1),
             Reference(ws,min_col=7,min_row=hr,max_row=p1),'$/shell-sqft',width=22,height=9)
    r+=1

    r=section(ws,r,'SEASONALITY - CALENDAR MONTH ACROSS ALL YEARS')
    hr=r; r=hdr(ws,r,['Calendar month','Jobs','Pipeline $','Share of year','Avg deal $','$/shell-sqft','','','',''])
    s0=r
    for i,mn in enumerate(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],start=1):
        ws.cell(r,1,mn); ws.cell(r,2,f'=COUNTIF({MO},{i})').number_format='#,##0'
        ws.cell(r,3,f'=SUMIF({MO},{i},{P})').number_format='$#,##0'
        ws.cell(r,4,f'=IFERROR(${CL(3)}{r}/SUM({P}),"")').number_format='0.0%'
        ws.cell(r,5,f'=IFERROR(${CL(3)}{r}/${CL(2)}{r},"")').number_format='$#,##0'
        ws.cell(r,6,f'=IFERROR(SUMIF({MO},{i},{BS})/SUMIF({MO},{i},{AR}),"")').number_format='$#,##0.00'
        r+=1
    s1=r-1
    add_bar(ws,f'H{hr}','Pipeline by calendar month (all years)',
            Reference(ws,min_col=1,min_row=s0,max_row=s1),
            Reference(ws,min_col=3,min_row=hr,max_row=s1),'Pipeline $',color=SER[3],height=9)
    r+=1
    ws.cell(r,1,'Calendar-month totals mix years, and the archive does not cover every year evenly - '
                '2023 and 2027 have a handful of jobs each. Read the shape, not the level.'
           ).font=Font(name=FONT,size=9,italic=True,color='595959')
    ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=7)
    r+=2

    r=section(ws,r,'QUARTERLY, BY YEAR')
    hr=r; r=hdr(ws,r,['Quarter']+[str(y) for y in years]+['']*(9-len(years)))
    q0=r
    for q in [1,2,3,4]:
        ws.cell(r,1,f'Q{q}')
        for j,y in enumerate(years):
            ws.cell(r,2+j,f'=SUMIFS({P},{qrng(FQ["Due Quarter"])},{q},{YR},{y})').number_format='$#,##0,,"M"'
        r+=1
    q1=r-1
    add_multibar(ws,f'{CL(3+len(years))}{hr}','Pipeline by quarter and year',
                 Reference(ws,min_col=1,min_row=q0,max_row=q1),
                 Reference(ws,min_col=2,max_col=1+len(years),min_row=hr,max_row=q1),'Pipeline $',width=20,height=10)
    return ws

# ====================================================== DATA QUALITY SCORECARD (P1-4)
# (flag, polarity, meaning). polarity 'pass1' means 1 is good; 'fail1' means 1 is the problem.
DQ_FLAGS=[
 ('DQ Has Geometry','pass1','Diameter > 0 AND height > 0'),
 ('DQ Has Capacity','pass1','Usable capacity parses above zero'),
 ('DQ Positive Target','pass1','The five buckets sum above zero'),
 ('DQ Price Sane','pass1','Proposal total inside the global $1K-$50M band'),
 ('DQ Price Sane Segment','pass1','$/shell-sqft inside the 1.5-99th pct of its material x scope segment (P0-4)'),
 ('DQ Quote Id Numeric','pass1','Quote number starts with 7 digits'),
 ('DQ Fill Ratio Valid','pass1','Usable capacity does not exceed geometric volume by more than 5%'),
 ('DQ Seismic Consistent','pass1','S1 <= Ss'),
 ('DQ Aspect Plausible','pass1','Height/diameter between 0.05 and 6'),
 ('DQ Freight Present','pass1','Freight priced, or the site is within 100 miles'),
 ('DQ Geo Resolved','pass1','Country|State resolved to a specific region (P0-2)'),
 ('DQ Looks Non-Tank','fail1','Matches a non-tank keyword on Ref_Lists'),
 ('DQ Unfinished','fail1','Status is Unfinished or Bid Review'),
 ('DQ Miles GT Zero','fail1','Distance from the GT plant is zero'),
]

def dash_quality(wb,years):
    """Data-quality scorecard. Data_Quality is a static table with no charts; this is the
    monitored version - pass rate per flag, trended by due year, plus the exclusion
    waterfall from raw rows to training rows."""
    ws=wb.create_sheet('Dashboard_DataQuality')
    title(ws,'Data Quality Scorecard',
          'Source-row grain - every flag as a live pass rate, trended by year, so quality is monitored rather than measured once')
    for w,c in zip([30,12,12,12,12,12,12,12,12,56],range(1,11)): ws.column_dimensions[CL(c)].width=w
    ALL=f'Clean_Data!$A${CF}:$A${CLST}'
    ML=crng('ML Eligible'); TR=crng('ML Training Row'); YR=crng('Due Year')

    r=4; r=section(ws,r,'HEADLINE',span=10)
    tiles=[('Source rows',f'=COUNTA({ALL})','#,##0'),
           ('ML eligible',f'=SUM({ML})','#,##0'),
           ('Training rows',f'=SUM({TR})','#,##0'),
           ('Eligible share',f'=IFERROR(SUM({ML})/COUNTA({ALL}),"")','0.0%')]
    for i,(l,f,fmt) in enumerate(tiles): kpi_tile(ws,r,i*2+1,l,f,fmt)
    r+=4

    r=section(ws,r,'EXCLUSION WATERFALL - HOW SOURCE ROWS BECOME TRAINING ROWS',span=10)
    hr=r; r=hdr(ws,r,['Step','Rows','','','','','','','','Why'])
    steps=[('Source rows (Raw_Import)',f'=COUNTA({ALL})','Every line in archive.csv, verbatim.'),
     ('  less: no geometry',f'=COUNTIFS({crng("DQ Has Geometry")},0)','Diameter or height missing - every geometric feature undefined.'),
     ('  less: no positive target',f'=COUNTIFS({crng("DQ Has Geometry")},1,{crng("DQ Positive Target")},0)','All five buckets zero - nothing to learn a price from.'),
     ('  less: outside global band',f'=COUNTIFS({crng("DQ Has Geometry")},1,{crng("DQ Positive Target")},1,{crng("DQ Price Sane")},0)','Proposal total outside $1K-$50M. Catches the $1.27tn class of error.'),
     ('  less: segment outlier',f'=COUNTIFS({crng("DQ Has Geometry")},1,{crng("DQ Positive Target")},1,{crng("DQ Price Sane")},1,{crng("DQ Price Sane Segment")},0)','$/shell-sqft in the tails of its own segment - mostly deck and floor replacement jobs with placeholder heights.'),
     ('  less: non-tank',f'=COUNTIFS({crng("DQ Has Geometry")},1,{crng("DQ Positive Target")},1,{crng("DQ Price Sane")},1,{crng("DQ Price Sane Segment")},1,{crng("DQ Looks Non-Tank")},1)','Elbows, nozzles, conduit, demo and test rows.'),
     ('  less: unfinished',f'=COUNTIFS({crng("DQ Has Geometry")},1,{crng("DQ Positive Target")},1,{crng("DQ Price Sane")},1,{crng("DQ Price Sane Segment")},1,{crng("DQ Looks Non-Tank")},0,{crng("DQ Unfinished")},1)','Status Unfinished or Bid Review - not a settled price.'),
     ('ML eligible',f'=SUM({ML})','Rows a model could legitimately learn from.'),
     ('  less: superseded revision / duplicate tank',f'=SUM({ML})-SUM({TR})','Only the firmest revision of each job, and each tank once within it.'),
     ('TRAINING ROWS',f'=SUM({TR})','The table the service is trained on.')]
    for lbl,f,why in steps:
        # NB: never start a label with '=' - HANDOFF gotcha 5, a text cell beginning
        # with '=' is parsed as a formula and bakes #NAME? into the delivered file.
        bold = not lbl.startswith('  ')
        c=ws.cell(r,1,lbl); c.font=Font(name=FONT,bold=bold,size=10)
        v=ws.cell(r,2,f); v.number_format='#,##0'; v.font=Font(name=FONT,bold=bold,size=10)
        if bold:
            for cc in range(1,3): ws.cell(r,cc).fill=LT
        n=ws.cell(r,10,why); n.font=Font(name=FONT,size=9,color='595959'); n.alignment=Alignment(wrap_text=True,vertical='top')
        ws.row_dimensions[r].height=24
        r+=1
    r+=1

    r=section(ws,r,'PASS RATE BY FLAG',span=10)
    hr=r; r=hdr(ws,r,['Flag','Rows failing','Pass rate']+[str(y) for y in years]+['']*(6-len(years))+['Meaning'])
    f0=r
    for flag,pol,mean in DQ_FLAGS:
        ws.cell(r,1,flag)
        fail = '0' if pol=='pass1' else '1'
        ws.cell(r,2,f'=COUNTIF({crng(flag)},{fail})').number_format='#,##0'
        ws.cell(r,3,f'=IFERROR(1-${CL(2)}{r}/COUNTA({ALL}),"")').number_format='0.0%'
        for j,y in enumerate(years):
            ws.cell(r,4+j,f'=IFERROR(1-COUNTIFS({crng(flag)},{fail},{YR},{y})'
                          f'/MAX(1,COUNTIFS({YR},{y})),"")').number_format='0.0%'
        n=ws.cell(r,10,mean); n.font=Font(name=FONT,size=9,color='595959'); n.alignment=Alignment(wrap_text=True,vertical='top')
        ws.row_dimensions[r].height=22
        r+=1
    f1=r-1
    add_bar(ws,f'A{r+1}','Pass rate by data-quality flag',
            Reference(ws,min_col=1,min_row=f0,max_row=f1),
            Reference(ws,min_col=3,min_row=hr,max_row=f1),'Pass rate',horiz=True,color=SER[2],width=20,height=12)
    r+=26
    ws.cell(r,1,'Pass rate is measured on ALL source rows, not just eligible ones, so it reports the '
                'health of the incoming data rather than of the filtered set. A flag trending down by '
                'year is a process change worth chasing; DQ Miles GT Zero and DQ Freight Present are '
                'informational and do not gate training.'
           ).font=Font(name=FONT,size=9,italic=True,color='595959')
    ws.cell(r,1).alignment=Alignment(wrap_text=True,vertical='top')
    ws.merge_cells(start_row=r,start_column=1,end_row=r,end_column=9); ws.row_dimensions[r].height=30
    return ws

# ============================================================ FACT_QUOTE
FQ_COLS=['Job Key','Quote Group ID','Quote Number','Firmest Revision','Tank Count','Total Quantity',
 'Outcome','Status','Bid Type','Due Date','Due Year','Company Name','Customer Name','Sales Manager',
 'Country','State',
 # P1-1: normalized geography at job grain. Country/State above are the raw source values.
 'Country Normalized','Country Name','State Normalized','Region Code','Is Domestic',
 'Min Miles','Distance Band',
 'Proposal Total','Bucket Sum','Freight Price','Total Tax','Total Price','Freight Pct',
 'Total Shell SqFt','Rate Per SqFt',
 # P1-3 time granularity: everything was annual.
 'Due Month','Due Quarter','Due Period',
 # P1-2 revision economics: what the job cost in rework and how the price moved.
 'Job Revision Count','First Revision','First Revision Total','Quote Growth Pct',
 'Wtd Margin (%)','Deal Size Band','Has Construction','Scope Class','Is Won','Is Lost','Is Decided']
FQ={h:CL(i+1) for i,h in enumerate(FQ_COLS)}

def build_fact_quote(wb,jobkeys):
    global FQ_FIRST,FQ_LAST
    ws=wb.create_sheet('Fact_Quote')
    ws.append(FQ_COLS); FQ_FIRST=2; FQ_LAST=len(jobkeys)+1
    jk=lambda r:f'$A{r}'
    RR=crng('Reporting Row'); JKC=crng('Job Key')
    def sifs(col,r): return f'=SUMIFS({crng(col)},{JKC},{jk(r)},{RR},1)'
    def first(col,r): return f'=IFERROR(INDEX({crng(col)},MATCH({jk(r)},{JKC},0)),"")'
    for i,k in enumerate(jobkeys):
        r=i+2
        row=[k]
        row.append(f'=IFERROR(LEFT($A{r},FIND("|",$A{r})-1),$A{r})')
        row.append(first('QuoteNumber',r))
        row.append(f'=_xlfn.MAXIFS({crng("Effective Revision")},{JKC},{jk(r)},{RR},1)')
        row.append(f'=COUNTIFS({JKC},{jk(r)},{RR},1)')
        row.append(sifs('Quantity',r))
        row.append(first('Outcome',r)); row.append(first('Status',r)); row.append(first('Bid Type',r))
        row.append(f'=_xlfn.MAXIFS({crng("Due Date")},{JKC},{jk(r)},{RR},1)')
        row.append(f'=IF(${FQ["Due Date"]}{r}=0,"",YEAR(${FQ["Due Date"]}{r}))')
        row.append(first('Company Name',r)); row.append(first('Customer Name',r))
        row.append(first('Sales Manager',r)); row.append(first('Country',r)); row.append(first('State',r))
        # --- P1-1 normalized geography, taken from the job's first reporting row
        for gcol in ('Country Normalized','Country Name','State Normalized','Region Code'):
            row.append(first(gcol,r))
        row.append(f'=IF(${FQ["Country Normalized"]}{r}="US",1,0)')
        # Distance to site: MIN of the two plant distances, matching the ML min_miles
        # convention (N() treats a blank plant distance as 0).
        _mt=first("Miles TBT",r)[1:]; _mg=first("Miles GT",r)[1:]
        row.append(f'=IFERROR(IF(AND(N({_mt})>0,N({_mg})>0),MIN(N({_mt}),N({_mg})),'
                   f'IF(N({_mt})>0,N({_mt}),IF(N({_mg})>0,N({_mg}),""))),"")')
        mm=f'${FQ["Min Miles"]}{r}'
        row.append(f'=IF({mm}="","Unknown",IF({mm}<100,"1. <100mi",IF({mm}<500,"2. 100-500mi",'
                   f'IF({mm}<1000,"3. 500-1000mi",IF({mm}<2000,"4. 1000-2000mi","5. 2000+mi")))))')
        row.append(sifs('Proposal Total',r)); row.append(sifs('Bucket Sum',r))
        row.append(sifs('Freight Price',r)); row.append(sifs('Total Tax',r)); row.append(sifs('Total Price',r))
        row.append(f'=IFERROR(${FQ["Freight Price"]}{r}/${FQ["Proposal Total"]}{r},"")')
        row.append(sifs('Shell Area SqFt',r))
        row.append(f'=IFERROR(${FQ["Bucket Sum"]}{r}/${FQ["Total Shell SqFt"]}{r},"")')
        # ---- P1-3 month / quarter / sortable period
        dd=f'${FQ["Due Date"]}{r}'
        row.append(f'=IF({dd}=0,"",MONTH({dd}))')
        row.append(f'=IF({dd}=0,"",ROUNDUP(MONTH({dd})/3,0))')
        row.append(f'=IF({dd}=0,"",TEXT({dd},"yyyy-mm"))')
        # ---- P1-2 revision economics. Uses Reporting Eligible, not Reporting Row: the
        # first revision is by definition NOT the firmest, so it is outside RR.
        RE=crng('Reporting Eligible'); ER=crng('Effective Revision')
        row.append(f'=IFERROR(INDEX({crng("Job Revision Count")},MATCH({jk(r)},{JKC},0)),"")')
        row.append(f'=_xlfn.MINIFS({ER},{JKC},{jk(r)},{RE},1)')
        row.append(f'=SUMIFS({crng("Proposal Total")},{JKC},{jk(r)},{RE},1,'
                   f'{ER},${FQ["First Revision"]}{r})')
        row.append(f'=IF(N(${FQ["First Revision Total"]}{r})<=0,"",'
                   f'${FQ["Proposal Total"]}{r}/${FQ["First Revision Total"]}{r}-1)')
        # proposal-weighted margin
        row.append(f'=IFERROR(SUMPRODUCT(({JKC}={jk(r)})*({RR}=1)*{crng("Margin (%)")}*{crng("Proposal Total")})'
                   f'/SUMIFS({crng("Proposal Total")},{JKC},{jk(r)},{RR},1),"")')
        p=f'${FQ["Proposal Total"]}{r}'
        row.append(f'=IF({p}<100000,"1. <$100K",IF({p}<250000,"2. $100K-$250K",IF({p}<500000,"3. $250K-$500K",'
                   f'IF({p}<1000000,"4. $500K-$1M","5. $1M+"))))')
        row.append(f'=IF(SUMIFS({crng("Construction Price")},{JKC},{jk(r)},{RR},1)>1,1,0)')
        row.append(f'=IF(${FQ["Has Construction"]}{r}=1,"tank_quote","materials_only")')
        row.append(f'=IF(${FQ["Outcome"]}{r}="Won",1,0)')
        row.append(f'=IF(${FQ["Outcome"]}{r}="Lost",1,0)')
        row.append(f'=IF(OR(${FQ["Outcome"]}{r}="Won",${FQ["Outcome"]}{r}="Lost"),1,0)')
        ws.append(row)
    for c in range(1,len(FQ_COLS)+1):
        cell=ws.cell(1,c); cell.fill=NAVY; cell.font=Font(name=FONT,bold=True,size=10,color='FFFFFF')
        cell.alignment=Alignment(wrap_text=True,horizontal='center',vertical='center')
        ws.column_dimensions[CL(c)].width=15
    for c in ['Proposal Total','Bucket Sum','Freight Price','Total Tax','Total Price']:
        for r in range(2,FQ_LAST+1): ws.cell(r,FQ_COLS.index(c)+1).number_format='$#,##0'
    for r in range(2,FQ_LAST+1):
        ws.cell(r,FQ_COLS.index('Due Date')+1).number_format='yyyy-mm-dd'
        ws.cell(r,FQ_COLS.index('Wtd Margin (%)')+1).number_format='0.0'
        ws.cell(r,FQ_COLS.index('Min Miles')+1).number_format='#,##0'
        ws.cell(r,FQ_COLS.index('Freight Pct')+1).number_format='0.0%'
        ws.cell(r,FQ_COLS.index('Total Shell SqFt')+1).number_format='#,##0'
        ws.cell(r,FQ_COLS.index('Rate Per SqFt')+1).number_format='$#,##0.00'
        ws.cell(r,FQ_COLS.index('First Revision Total')+1).number_format='$#,##0'
        ws.cell(r,FQ_COLS.index('Quote Growth Pct')+1).number_format='0.0%'
    ws.freeze_panes='C2'; ws.row_dimensions[1].height=30
    return ws

# ============================================================ DASHBOARDS
def dash_exec(wb,years,companies):
    ws=wb.create_sheet('Dashboard_Executive')
    title(ws,'Executive Dashboard','Job grain (one row per quote at its firmest revision) · cleaned data only · every figure is a live formula')
    for w,c in zip([26,16,16,16,16,16,16,16,16,16],range(1,11)): ws.column_dimensions[CL(c)].width=w
    P=qrng(FQ['Proposal Total']); O=qrng(FQ['Outcome']); W=qrng(FQ['Is Won']); LS=qrng(FQ['Is Lost'])
    D=qrng(FQ['Is Decided']); Y=qrng(FQ['Due Year']); T=qrng(FQ['Tank Count']); B=qrng(FQ['Bid Type'])
    r=4; r=section(ws,r,'HEADLINE')
    tiles=[('Total pipeline',f'=SUM({P})','$#,##0,,"M"'),('Won revenue',f'=SUMIF({O},"Won",{P})','$#,##0,,"M"'),
     ('Lost revenue',f'=SUMIF({O},"Lost",{P})','$#,##0,,"M"'),('Open pipeline',f'=SUMIF({O},"Open",{P})','$#,##0,,"M"'),
     ('Jobs',f'=COUNTA({qrng(FQ["Job Key"])})','#,##0'),('Tanks',f'=SUM({T})','#,##0'),
     ('Win rate',f'=IFERROR(SUM({W})/SUM({D}),"")','0.0%'),('Avg deal size',f'=AVERAGE({P})','$#,##0')]
    for i,(l,f,fmt) in enumerate(tiles[:4]): kpi_tile(ws,r,i*2+1,l,f,fmt)
    r+=3
    for i,(l,f,fmt) in enumerate(tiles[4:]): kpi_tile(ws,r,i*2+1,l,f,fmt)
    r+=4
    r=section(ws,r,'PIPELINE BY DUE YEAR')
    hr=r; r=hdr(ws,r,['Due Year','Jobs','Pipeline $','Won $','Win rate','','','','',''])
    y0=r
    for yv in years:
        ws.cell(r,1,yv)
        ws.cell(r,2,f'=COUNTIF({Y},{yv})')
        ws.cell(r,3,f'=SUMIF({Y},{yv},{P})').number_format='$#,##0'
        ws.cell(r,4,f'=SUMIFS({P},{Y},{yv},{O},"Won")').number_format='$#,##0'
        ws.cell(r,5,f'=IFERROR(SUMIFS({W},{Y},{yv})/SUMIFS({D},{Y},{yv}),"")').number_format='0.0%'
        r+=1
    add_bar(ws,f'G{hr}','Pipeline by due year',Reference(ws,min_col=1,min_row=y0,max_row=r-1),
            Reference(ws,min_col=3,min_row=y0-1,max_row=r-1),'Pipeline $')
    r+=1
    r=section(ws,r,'OUTCOME SPLIT')
    hr=r; r=hdr(ws,r,['Outcome','Jobs','Pipeline $','Share of $','','','','','',''])
    o0=r
    for ov in ['Won','Lost','Open']:
        ws.cell(r,1,ov); ws.cell(r,2,f'=COUNTIF({O},"{ov}")')
        ws.cell(r,3,f'=SUMIF({O},"{ov}",{P})').number_format='$#,##0'
        ws.cell(r,4,f'=IFERROR(SUMIF({O},"{ov}",{P})/SUM({P}),"")').number_format='0.0%'
        r+=1
    add_bar(ws,f'G{hr}','Pipeline by outcome',Reference(ws,min_col=1,min_row=o0,max_row=r-1),
            Reference(ws,min_col=3,min_row=o0-1,max_row=r-1),'Pipeline $')
    r+=1
    r=section(ws,r,'BID TYPE')
    r=hdr(ws,r,['Bid Type','Jobs','Pipeline $','Win rate','','','','','',''])
    for bv in ['Firm','Budget']:
        ws.cell(r,1,bv); ws.cell(r,2,f'=COUNTIF({B},"{bv}")')
        ws.cell(r,3,f'=SUMIF({B},"{bv}",{P})').number_format='$#,##0'
        ws.cell(r,4,f'=IFERROR(SUMIFS({W},{B},"{bv}")/SUMIFS({D},{B},"{bv}"),"")').number_format='0.0%'
        r+=1
    r+=1
    r=section(ws,r,'TOP 15 END CUSTOMERS BY PIPELINE')
    hr=r; r=hdr(ws,r,['Company','Jobs','Pipeline $','Won $','Win rate','','','','',''])
    c0=r; CO=qrng(FQ['Company Name'])
    for cn in companies:
        ws.cell(r,1,cn); ws.cell(r,2,f'=COUNTIF({CO},$A{r})')
        ws.cell(r,3,f'=SUMIF({CO},$A{r},{P})').number_format='$#,##0'
        ws.cell(r,4,f'=SUMIFS({P},{CO},$A{r},{O},"Won")').number_format='$#,##0'
        ws.cell(r,5,f'=IFERROR(SUMIFS({W},{CO},$A{r})/SUMIFS({D},{CO},$A{r}),"")').number_format='0.0%'
        r+=1
    add_bar(ws,f'G{hr}','Top end customers by pipeline',Reference(ws,min_col=1,min_row=c0,max_row=r-1),
            Reference(ws,min_col=3,min_row=c0-1,max_row=r-1),'Pipeline $',horiz=True,height=11)
    return ws

def dash_sales(wb,managers,customers):
    ws=wb.create_sheet('Dashboard_Sales')
    title(ws,'Sales Performance','By internal sales manager and external rep/dealer · job grain')
    for w,c in zip([30,14,16,16,14,14,16,16,16,16],range(1,11)): ws.column_dimensions[CL(c)].width=w
    P=qrng(FQ['Proposal Total']); O=qrng(FQ['Outcome']); W=qrng(FQ['Is Won']); D=qrng(FQ['Is Decided'])
    SM=qrng(FQ['Sales Manager']); CU=qrng(FQ['Customer Name']); M=qrng(FQ['Wtd Margin (%)'])
    r=4; r=section(ws,r,'BY SALES MANAGER')
    hr=r; r=hdr(ws,r,['Sales Manager','Jobs','Pipeline $','Won $','Win rate','Avg deal $','Avg margin %','','',''])
    m0=r
    for mn in managers:
        ws.cell(r,1,mn); ws.cell(r,2,f'=COUNTIF({SM},$A{r})')
        ws.cell(r,3,f'=SUMIF({SM},$A{r},{P})').number_format='$#,##0'
        ws.cell(r,4,f'=SUMIFS({P},{SM},$A{r},{O},"Won")').number_format='$#,##0'
        ws.cell(r,5,f'=IFERROR(SUMIFS({W},{SM},$A{r})/SUMIFS({D},{SM},$A{r}),"")').number_format='0.0%'
        ws.cell(r,6,f'=IFERROR(AVERAGEIF({SM},$A{r},{P}),"")').number_format='$#,##0'
        ws.cell(r,7,f'=IFERROR(AVERAGEIF({SM},$A{r},{M}),"")').number_format='0.0'
        r+=1
    add_bar(ws,f'I{hr}','Pipeline by sales manager',Reference(ws,min_col=1,min_row=m0,max_row=r-1),
            Reference(ws,min_col=3,min_row=m0-1,max_row=r-1),'Pipeline $',horiz=True,height=11)
    r+=1
    r=section(ws,r,'TOP 15 REPS / DEALERS')
    hr=r; r=hdr(ws,r,['Customer (rep/dealer)','Jobs','Pipeline $','Won $','Win rate','','','','',''])
    c0=r
    for cn in customers:
        ws.cell(r,1,cn); ws.cell(r,2,f'=COUNTIF({CU},$A{r})')
        ws.cell(r,3,f'=SUMIF({CU},$A{r},{P})').number_format='$#,##0'
        ws.cell(r,4,f'=SUMIFS({P},{CU},$A{r},{O},"Won")').number_format='$#,##0'
        ws.cell(r,5,f'=IFERROR(SUMIFS({W},{CU},$A{r})/SUMIFS({D},{CU},$A{r}),"")').number_format='0.0%'
        r+=1
    add_bar(ws,f'G{hr}','Top reps by pipeline',Reference(ws,min_col=1,min_row=c0,max_row=r-1),
            Reference(ws,min_col=3,min_row=c0-1,max_row=r-1),'Pipeline $',horiz=True,height=11)
    return ws

MLF,MLL=3,None
def mr(h): return f"ML_Tank_Training!${ML_L[h]}${MLF}:${ML_L[h]}${MLL}"

def dash_pricing(wb,years,usetypes):
    ws=wb.create_sheet('Dashboard_Pricing')
    title(ws,'Pricing & Rate Analytics','Tank grain (ML_Tank_Training) · "blended" rate = SUM(price)/SUM(area), robust to small-area outliers')
    for w,c in zip([32,12,18,18,16,16,16,16,16,16],range(1,11)): ws.column_dimensions[CL(c)].width=w
    MAT=mr('Material'); SA=mr('shell_area_sqft'); BS=mr('Y Bucket Sum'); YM=mr('Y Material')
    YC=mr('Y Construction'); UT=mr('Use Type'); DY=mr('Due Year'); WT=mr('Wage Type'); SC=mr('scope_class')
    r=4; r=section(ws,r,'BLENDED UNIT RATE BY MATERIAL GRADE')
    hr=r; r=hdr(ws,r,['Material','Tanks','Blended $/shell sqft','Material $/shell sqft','Avg tank $','','','','',''])
    m0=r
    for mv in ['CS','304SS','316SS']:
        ws.cell(r,1,mv); ws.cell(r,2,f'=COUNTIF({MAT},"{mv}")')
        ws.cell(r,3,f'=IFERROR(SUMIF({MAT},"{mv}",{BS})/SUMIF({MAT},"{mv}",{SA}),"")').number_format='$#,##0.00'
        ws.cell(r,4,f'=IFERROR(SUMIF({MAT},"{mv}",{YM})/SUMIF({MAT},"{mv}",{SA}),"")').number_format='$#,##0.00'
        ws.cell(r,5,f'=IFERROR(AVERAGEIF({MAT},"{mv}",{BS}),"")').number_format='$#,##0'
        r+=1
    add_bar(ws,f'G{hr}','Blended $/shell sqft by grade',Reference(ws,min_col=1,min_row=m0,max_row=r-1),
            Reference(ws,min_col=3,min_row=m0-1,max_row=r-1),'$/sqft')
    r+=1
    r=section(ws,r,'PRICE ESCALATION BY DUE YEAR')
    hr=r; r=hdr(ws,r,['Due Year','Tanks','Material $/shell sqft','Total $/shell sqft','','','','','',''])
    y0=r
    for yv in years:
        ws.cell(r,1,yv); ws.cell(r,2,f'=COUNTIF({DY},{yv})')
        ws.cell(r,3,f'=IFERROR(SUMIF({DY},{yv},{YM})/SUMIF({DY},{yv},{SA}),"")').number_format='$#,##0.00'
        ws.cell(r,4,f'=IFERROR(SUMIF({DY},{yv},{BS})/SUMIF({DY},{yv},{SA}),"")').number_format='$#,##0.00'
        r+=1
    add_line(ws,f'G{hr}','Material rate escalation ($/shell sqft)',Reference(ws,min_col=1,min_row=y0,max_row=r-1),
             Reference(ws,min_col=3,min_row=y0-1,max_row=r-1),'$/sqft')
    r+=1
    r=section(ws,r,'RATE BY USE TYPE')
    hr=r; r=hdr(ws,r,['Use Type','Tanks','Blended $/shell sqft','Avg tank $','','','','','',''])
    u0=r
    for uv in usetypes:
        ws.cell(r,1,uv); ws.cell(r,2,f'=COUNTIF({UT},$A{r})')
        ws.cell(r,3,f'=IFERROR(SUMIF({UT},$A{r},{BS})/SUMIF({UT},$A{r},{SA}),"")').number_format='$#,##0.00'
        ws.cell(r,4,f'=IFERROR(AVERAGEIF({UT},$A{r},{BS}),"")').number_format='$#,##0'
        r+=1
    add_bar(ws,f'G{hr}','Blended $/shell sqft by use type',Reference(ws,min_col=1,min_row=u0,max_row=r-1),
            Reference(ws,min_col=3,min_row=u0-1,max_row=r-1),'$/sqft',horiz=True,height=10)
    r+=1
    r=section(ws,r,'CONSTRUCTION RATE BY LABOUR REGIME')
    hr=r; r=hdr(ws,r,['Wage Type','Tanks','Construction $/shell sqft','Avg construction $','','','','','',''])
    w0=r
    for wv in ['Non-Union / Non-Prevailing','Prevailing Wage','Union Wage','No Erection Included']:
        ws.cell(r,1,wv); ws.cell(r,2,f'=COUNTIF({WT},$A{r})')
        ws.cell(r,3,f'=IFERROR(SUMIF({WT},$A{r},{YC})/SUMIF({WT},$A{r},{SA}),"")').number_format='$#,##0.00'
        ws.cell(r,4,f'=IFERROR(AVERAGEIF({WT},$A{r},{YC}),"")').number_format='$#,##0'
        r+=1
    add_bar(ws,f'G{hr}','Construction $/sqft by labour regime',Reference(ws,min_col=1,min_row=w0,max_row=r-1),
            Reference(ws,min_col=3,min_row=w0-1,max_row=r-1),'$/sqft',horiz=True,height=8)
    r+=1
    r=section(ws,r,'SCOPE MIX')
    r=hdr(ws,r,['Scope','Tanks','Share of tanks','Avg tank $','','','','','',''])
    for sv in ['tank_quote','materials_only','construction_only']:
        ws.cell(r,1,sv); ws.cell(r,2,f'=COUNTIF({SC},$A{r})')
        ws.cell(r,3,f'=IFERROR(COUNTIF({SC},$A{r})/COUNTA({mr("Tank Key")}),"")').number_format='0.0%'
        ws.cell(r,4,f'=IFERROR(AVERAGEIF({SC},$A{r},{BS}),"")').number_format='$#,##0'
        r+=1
    return ws

def dash_winloss(wb,materials,usetypes,managers):
    ws=wb.create_sheet('Dashboard_WinLoss')
    title(ws,'Win / Loss Analytics','Decided jobs only (Won or Lost). Open jobs are excluded from every win rate.')
    for w,c in zip([32,12,12,14,16,16,16,16,16,16],range(1,11)): ws.column_dimensions[CL(c)].width=w
    P=qrng(FQ['Proposal Total']); O=qrng(FQ['Outcome']); W=qrng(FQ['Is Won']); D=qrng(FQ['Is Decided'])
    B=qrng(FQ['Bid Type']); DB=qrng(FQ['Deal Size Band']); SM=qrng(FQ['Sales Manager'])
    SCQ=qrng(FQ['Scope Class']); M=qrng(FQ['Wtd Margin (%)'])
    r=4; r=section(ws,r,'HEADLINE')
    for i,(l,f,fmt) in enumerate([('Decided jobs',f'=SUM({D})','#,##0'),('Won',f'=SUM({W})','#,##0'),
        ('Lost',f'=SUM({D})-SUM({W})','#,##0'),('Win rate',f'=IFERROR(SUM({W})/SUM({D}),"")','0.0%')]):
        kpi_tile(ws,r,i*2+1,l,f,fmt)
    r+=4
    r=section(ws,r,'WON vs LOST - WHAT SEPARATES THEM')
    r=hdr(ws,r,['Metric','Won','Lost','Reading','','','','','',''])
    for nm,rng,fmt,note in [('Avg deal size',P,'$#,##0','Lost jobs are materially larger - big jobs are more competitive.'),
        ('Avg weighted margin %',M,'0.00','Won jobs carry a lower margin. Price discipline shows in the margin knob.')]:
        ws.cell(r,1,nm)
        ws.cell(r,2,f'=IFERROR(AVERAGEIF({O},"Won",{rng}),"")').number_format=fmt
        ws.cell(r,3,f'=IFERROR(AVERAGEIF({O},"Lost",{rng}),"")').number_format=fmt
        ws.cell(r,4,note); ws.cell(r,4).font=BODY; ws.cell(r,4).alignment=Alignment(wrap_text=True)
        r+=1
    r+=1
    def block(hdr_label,rng,vals,anchor_col='G',chart_title=None,horiz=False,h=9):
        nonlocal r
        hr=r; r2=hdr(ws,r,[hdr_label,'Won','Lost','Win rate','Pipeline $','','','','',''])
        s0=r2
        for v in vals:
            ws.cell(r2,1,v)
            ws.cell(r2,2,f'=SUMIFS({W},{rng},$A{r2})')
            ws.cell(r2,3,f'=SUMIFS({D},{rng},$A{r2})-SUMIFS({W},{rng},$A{r2})')
            ws.cell(r2,4,f'=IFERROR(SUMIFS({W},{rng},$A{r2})/SUMIFS({D},{rng},$A{r2}),"")').number_format='0.0%'
            ws.cell(r2,5,f'=SUMIF({rng},$A{r2},{P})').number_format='$#,##0'
            r2+=1
        if chart_title:
            add_multibar(ws,f'{anchor_col}{hr}',chart_title,Reference(ws,min_col=1,min_row=s0,max_row=r2-1),
                         Reference(ws,min_col=2,max_col=3,min_row=s0-1,max_row=r2-1),'Jobs',height=h)
        r=r2+1
    r=section(ws,r,'WIN RATE BY BID TYPE'); block('Bid Type',B,['Firm','Budget'],chart_title='Won vs lost by bid type',h=7)
    r=section(ws,r,'WIN RATE BY DEAL SIZE'); block('Deal Size Band',DB,
        ['1. <$100K','2. $100K-$250K','3. $250K-$500K','4. $500K-$1M','5. $1M+'],chart_title='Won vs lost by deal size',h=9)
    r=section(ws,r,'WIN RATE BY SCOPE'); block('Scope Class',SCQ,['tank_quote','materials_only'],chart_title=None)
    r=section(ws,r,'WIN RATE BY SALES MANAGER'); block('Sales Manager',SM,managers,chart_title='Won vs lost by manager',horiz=True,h=11)
    return ws

def main():
    import prep2
    d=prep2.add_scope_and_recon(prep2.add_grouping(prep2.build_all()))
    numeric_q=d['QuoteNumber'].astype(str).str[:7].str.fullmatch(r'\d{7}').fillna(False)
    rep=((d['dq_price_sane']==1)&(d['dq_looks_nontank']==0)&(d['dq_is_unfinished']==0)
         &numeric_q&(d['IsJobFirmest']==1))
    R=d[rep]
    jobs=R.drop_duplicates('JobKey')
    jobkeys=sorted(R['JobKey'].unique())
    jr=R.groupby('JobKey')['Proposal Total'].sum()
    years=[int(y) for y in sorted(R['due_year'].dropna().unique()) if 2023<=y<=2027]
    companies=jr.to_frame().join(jobs.set_index('JobKey')[['Company Name']]).groupby('Company Name')['Proposal Total'].sum().nlargest(15).index.tolist()
    customers=jr.to_frame().join(jobs.set_index('JobKey')[['Customer Name']]).groupby('Customer Name')['Proposal Total'].sum().nlargest(15).index.tolist()
    managers=sorted([m for m in jobs['Sales Manager'].dropna().unique()])
    tr=d[d['ML Training Row V2']==1]
    usetypes=tr['Use Type'].value_counts().head(8).index.tolist()
    materials=['CS','304SS','316SS']
    # P1-1 category lists, ranked by pipeline at job grain on NORMALIZED geography
    _jg=jobs.set_index('JobKey'); _p=jr.to_frame()
    geo_countries=(_p.join(_jg[['Country Name']]).groupby('Country Name')['Proposal Total']
                     .sum().nlargest(12).index.tolist())
    _us=_p.join(_jg[['Country Normalized','State Normalized']])
    _us=_us[_us['Country Normalized']=='US']
    geo_states=(_us.groupby('State Normalized')['Proposal Total'].sum().nlargest(15).index.tolist())
    geo_bands=['1. <100mi','2. 100-500mi','3. 500-1000mi','4. 1000-2000mi','5. 2000+mi','Unknown']
    # P1-3: the months that actually carry jobs, in order, capped to a readable window
    _per=(jobs.dropna(subset=['Due Date'])['Due Date'].dt.to_period('M').value_counts())
    trend_periods=[str(p) for p in sorted(_per[_per>=5].index)]

    global MLL
    wb=openpyxl.load_workbook('v5_ml.xlsx')
    MLL=wb['ML_Tank_Training'].max_row
    build_fact_quote(wb,jobkeys)
    dash_exec(wb,years,companies); dash_sales(wb,managers,customers)
    dash_pricing(wb,years,usetypes); dash_winloss(wb,materials,usetypes,managers)
    dash_geo(wb,geo_countries,geo_states,geo_bands)
    dash_revisions(wb,managers)
    dash_trend(wb,trend_periods,years)
    dash_quality(wb,years)
    wb.save('v5_dash.xlsx')
    print('saved v5_dash.xlsx | jobs:',len(jobkeys),'| ML last row:',MLL)
    print('sheets:',wb.sheetnames)

if __name__=='__main__': main()
