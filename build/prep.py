"""
TBT Tank Quote Analytics V5 - core data prep + feature engineering.
Loads archive.csv, cleans it, builds the modeling grain, and engineers
derived features. Importable by both the EDA and the workbook builder.
"""
import pandas as pd, numpy as np, re
import geo_crosswalk as GEO

CSV = 'archive.csv'

PRICE_BUCKETS = ['Material Price','Fabrication Price','Construction Price',
                 'Insulation Material Price','Insulation Construction Price']
GAL_PER_CUFT = 7.48052

# Canonical non-tank keyword list. build_core.py imports this and writes it to
# Ref_Lists!Ref_JunkWords, so the Excel rule and this reference cannot drift apart.
# Previously the two were maintained separately and had diverged: this list was missing
# 'part test', 'conduit', 'platform only', 'test 1', 'options test' and 'estimate 1',
# which let 18 test/demo rows (6 of them training rows) past the pandas filter.
JUNK_WORDS = ['elbow','audit','standard part','part test','nozzle','fitting','spare',
              'conduit','platform only','test 1','options test','estimate 1']

def _num(s):
    """Robust numeric parse: strips $ , % and treats (x) as negative."""
    s = s.astype(str).str.strip()
    neg = s.str.startswith('(') & s.str.endswith(')')
    s = s.str.replace(r'[\$,%()]', '', regex=True).str.replace(',', '', regex=False).str.strip()
    v = pd.to_numeric(s, errors='coerce')
    v[neg] = -v[neg]
    return v

def _clean_text(s):
    s = s.astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
    junk = {'', 'null', 'none', 'n/a', 'na', '-', 'nan'}
    return s.where(~s.str.lower().isin(junk), np.nan)

def load_clean():
    df = pd.read_csv(CSV, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    numcols = PRICE_BUCKETS + ['Total Tax','Proposal Total','Freight Price','Total Price',
        'Margin (%)','Contingency (%)','Insulation Margin (%)','Insulation Contingency (%)',
        'Diameter (ft)','Height (ft)','Freeboard (in)','Ss','S1',
        'Miles to Site (From TBT)','Miles to Site (From GT)','Quantity','Commission (%)','Revision #']
    for c in numcols:
        df[c] = _num(df[c])

    textcols = ['Project Name','Bid Type','Status','Tank Name','Company Name','Customer Name',
        'Country','State','City','Sales Manager','Sales Rep','Wage Type','Material','Use Type',
        'Deck Style','Floor Style','Usable Capacity']
    for c in textcols:
        df[c] = _clean_text(df[c])

    # keys
    df['QuoteNumber'] = df['Quote #'].astype(str).str.strip()
    df['RevisionNumber'] = df['Revision #']
    df['Quote-Rev'] = df['QuoteNumber'] + '-R' + df['RevisionNumber'].astype('Int64').astype(str)
    df['Tank Name'] = df['Tank Name'].fillna('Tank ?')
    df['Tank Key'] = df['Quote-Rev'] + '-' + df['Tank Name'].astype(str)

    # dates
    df['Due Date'] = pd.to_datetime(df['Due Date'], errors='coerce')

    # City cleanup: strip trailing commas/spaces
    df['City'] = df['City'].astype(str).str.replace(r'[,\s]+$', '', regex=True).replace('nan', np.nan)

    # capacity parse
    def parse_cap(v):
        if pd.isna(v): return (np.nan, None)
        s = str(v).lower().replace(',', '').strip()
        # Keep the sign. 44 source rows read like "-937.376tons"; dropping the minus
        # silently turned an impossible value into a plausible one.
        m = re.search(r'(-?[\d.]+)', s)
        val = float(m.group(1)) if m else np.nan
        unit = 'tons' if 'ton' in s else ('gal' if 'gal' in s else None)
        return (val, unit)
    cap = df['Usable Capacity'].apply(parse_cap)
    df['Capacity Value'] = [c[0] for c in cap]
    df['Capacity Unit'] = [c[1] for c in cap]

    # status normalization (title case) + outcome mapping (Won/Lost/else Open)
    df['Status'] = df['Status'].astype(str).str.title().replace('Nan', np.nan)
    df['Row Outcome'] = np.where(df['Status'].eq('Won'), 'Won',
                          np.where(df['Status'].eq('Lost'), 'Lost', 'Open'))

    # quote-level outcome (won-wins rule) + revision meta
    g = df.groupby('QuoteNumber')
    df['Max Revision'] = g['RevisionNumber'].transform('max')
    df['Revision Count'] = g['RevisionNumber'].transform('nunique')
    def quote_outcome(sub):
        s = set(sub)
        return 'Won' if 'Won' in s else ('Lost' if 'Lost' in s else 'Open')
    qo = g['Status'].apply(lambda x: quote_outcome(x))
    df['Outcome'] = df['QuoteNumber'].map(qo)
    df['Is Current Revision'] = df['RevisionNumber'] == df['Max Revision']

    # first-revision total per quote
    def first_rev_total(sub):
        mn = sub['RevisionNumber'].min()
        return sub.loc[sub['RevisionNumber'] == mn, 'Proposal Total'].sum()
    frt = df.groupby('QuoteNumber').apply(first_rev_total)
    df['First Revision Total'] = df['QuoteNumber'].map(frt)

    return df

# ------------------------------------------------------------------ features
def add_features(df):
    d = df.copy()

    D = d['Diameter (ft)']; H = d['Height (ft)']
    # ---- geometry
    d['geom_volume_cuft'] = np.pi * (D/2)**2 * H
    d['geom_volume_gal']  = d['geom_volume_cuft'] * GAL_PER_CUFT
    d['shell_area_sqft']  = np.pi * D * H            # lateral -> shell plate / material driver
    d['floor_area_sqft']  = np.pi * (D/2)**2
    d['roof_area_sqft']   = d['floor_area_sqft']     # ~ flat-projected; slope adj below
    d['total_area_sqft']  = d['shell_area_sqft'] + d['floor_area_sqft'] + d['roof_area_sqft']
    d['circumference_ft'] = np.pi * D
    d['aspect_ratio_hd']  = H / D.replace(0, np.nan)     # slenderness
    d['diameter_sq']      = D**2
    d['height_sq']        = H**2
    d['d_x_h']            = D * H
    d['freeboard_ft']     = d['Freeboard (in)'] / 12.0
    d['freeboard_ratio']  = d['freeboard_ft'] / H.replace(0, np.nan)

    # ---- capacity normalization
    # A negative capacity is treated as missing - see build_core.py, P1-6.
    _pos = d['Capacity Value'] > 0
    d['capacity_gal'] = np.where(d['Capacity Unit'].eq('gal') & _pos, d['Capacity Value'], np.nan)
    d['capacity_tons'] = np.where(d['Capacity Unit'].eq('tons') & _pos, d['Capacity Value'], np.nan)
    d['is_ton_capacity'] = d['Capacity Unit'].eq('tons').astype(int)
    d['fill_ratio'] = d['capacity_gal'] / d['geom_volume_gal'].replace(0, np.nan)

    # ---- material
    grade = {'CS':1, '304SS':2, '316SS':3}
    d['material_grade_rank'] = d['Material'].map(grade).fillna(0).astype(int)
    d['is_stainless'] = d['Material'].isin(['304SS','316SS']).astype(int)
    # material-weighted surface (SS ~ pricier per area): rough intensity proxy
    dens = {'CS':1.0, '304SS':1.15, '316SS':1.25}
    d['material_area_intensity'] = d['shell_area_sqft'] * d['Material'].map(dens).fillna(1.0)

    # ---- seismic
    Ss = d['Ss']; S1 = d['S1']
    def sband(x):
        if pd.isna(x): return 'Unknown'
        if x < 0.25: return '1. Very Low (<0.25)'
        if x < 0.50: return '2. Low (0.25-0.5)'
        if x < 1.00: return '3. Moderate (0.5-1.0)'
        if x < 1.50: return '4. High (1.0-1.5)'
        return '5. Very High (1.5+)'
    d['seismic_band'] = Ss.apply(sband)
    d['high_seismic'] = (Ss >= 0.5).astype(int)
    d['s1_ss_ratio'] = S1 / Ss.replace(0, np.nan)
    d['seismic_x_height'] = Ss * H            # anchorage / overturning proxy
    d['seismic_x_shell']  = Ss * d['shell_area_sqft']

    # ---- P0-2 geographic normalization (mirrors the Clean_Data INDEX/MATCH exactly).
    # Keyed on Country|State because State alone is ambiguous across countries, and the
    # Country column itself is wrong on 37 rows. See geo_crosswalk.py.
    _cc = d['Country'].fillna('').astype(str).str.strip()
    _st = d['State'].fillna('').astype(str).str.strip()
    _geo = [GEO.lookup(a, b) for a, b in zip(_cc, _st)]
    d['Country Normalized'] = [g[0] for g in _geo]
    d['Country Name']       = [g[1] for g in _geo]
    d['State Normalized']   = [g[2] for g in _geo]
    d['Region Code']        = [g[3] for g in _geo]
    d['Geo Match Level']    = [g[4] for g in _geo]
    d['dq_geo_resolved']    = (d['Geo Match Level'] == 'region').astype(int)

    # ---- freight / logistics
    mt = d['Miles to Site (From TBT)']; mg = d['Miles to Site (From GT)']
    # Minimum over the POSITIVE distances only. A zero plant distance means the figure was
    # never computed (Miles GT is a literal 0 on 1,853 rows, 51.2% of 2026), not that the
    # site sits at the plant - only 26 rows have both zero. A plain min let one zero drag
    # the result to zero on 1,827 rows whose real distance had a median of 800 miles.
    _mt = mt.where(mt > 0); _mg = mg.where(mg > 0)
    d['min_miles'] = pd.concat([_mt, _mg], axis=1).min(axis=1, skipna=True)
    # Keys off the normalized country, not the raw one (wrong on 37 rows).
    d['is_domestic'] = d['Country Normalized'].eq('US').astype(int)
    d['is_international'] = (~d['Country Normalized'].eq('US')).astype(int)
    d['is_local_site'] = (d['min_miles'].notna() & (d['min_miles'] < 50)).astype(int)
    def dband(x):
        if pd.isna(x): return 'Unknown'
        if x < 100: return '1. <100 mi'
        if x < 500: return '2. 100-500 mi'
        if x < 1000: return '3. 500-1000 mi'
        if x < 2000: return '4. 1000-2000 mi'
        return '5. 2000+ mi'
    d['distance_band'] = d['min_miles'].apply(dband)

    # ---- wage / labor / erection scope
    wt = d['Wage Type']
    d['is_prevailing_wage'] = wt.eq('Prevailing Wage').astype(int)
    d['is_union'] = wt.eq('Union Wage').astype(int)
    d['no_erection_scope'] = (wt.isin(['No Erection Included','Erection Advisor Only']) | wt.isna()).astype(int)
    d['has_erection_scope'] = (1 - d['no_erection_scope']).astype(int)

    # ---- deck / roof options (parse)
    deck = d['Deck Style'].fillna('(Not Specified)')
    d['deck_is_dome'] = deck.str.contains('Dome', case=False, na=False).astype(int)
    d['deck_is_open_top'] = deck.str.contains('Open-Top', case=False, na=False).astype(int)
    d['deck_has_rafters'] = deck.str.contains('Rafter', case=False, na=False).astype(int)
    d['deck_is_selfsupp'] = deck.str.contains('Self Supported', case=False, na=False).astype(int)
    d['deck_is_centersupp'] = deck.str.contains('Center Supported', case=False, na=False).astype(int)
    slope = deck.str.extract(r'(\d+):12')[0].astype(float)
    d['roof_slope_ratio'] = slope / 12.0
    d['roof_area_sloped_sqft'] = d['floor_area_sqft'] * np.sqrt(1 + d['roof_slope_ratio'].fillna(0)**2)

    # ---- floor options
    floor = d['Floor Style'].fillna('(Not Specified)')
    d['floor_is_embedded_ring'] = floor.str.contains('Embedded Ring', case=False, na=False).astype(int)
    d['floor_is_flat'] = floor.str.contains('Flat', case=False, na=False).astype(int)
    d['floor_is_sloped'] = floor.str.contains('Slope', case=False, na=False).astype(int)
    d['floor_is_special'] = floor.eq('Special').astype(int)

    # ---- insulation (option selected -> insulation buckets nonzero)
    ins_amt = d['Insulation Material Price'].fillna(0) + d['Insulation Construction Price'].fillna(0)
    d['is_insulated'] = (ins_amt > 1).astype(int)

    # ---- mix / context
    d['quantity'] = d['Quantity'].fillna(1)
    tc = d.groupby('Quote-Rev')['Tank Key'].transform('nunique')
    d['tank_count_in_quoterev'] = tc
    d['is_multi_tank_quote'] = (tc > 1).astype(int)

    # ---- temporal (steel-price / inflation proxy)
    d['due_year'] = d['Due Date'].dt.year
    d['due_quarter'] = d['Due Date'].dt.quarter
    d['due_month'] = d['Due Date'].dt.month
    ref = pd.Timestamp('2020-01-01')
    d['months_since_2020'] = (d['Due Date'] - ref).dt.days / 30.44

    # ---- capacity category (fixed bands, gal & tons)
    def capcat(v, u):
        if pd.isna(v) or v <= 0 or u is None: return 'Unknown'
        if u == 'gal':
            if v < 50000: return 'Small (<50K gal)'
            if v < 250000: return 'Medium (50K-250K gal)'
            if v < 1000000: return 'Large (250K-1M gal)'
            return 'Very Large (1M+ gal)'
        if u == 'tons':
            if v < 100: return 'Small (<100 tons)'
            if v < 500: return 'Medium (100-500 tons)'
            return 'Large (500+ tons)'
        return 'Unknown'
    d['Capacity Category'] = [capcat(v, u) for v, u in zip(d['Capacity Value'], d['Capacity Unit'])]

    # ------------------------------------------------------------- targets
    d['target_material'] = d['Material Price']
    d['target_fabrication'] = d['Fabrication Price']
    d['target_construction'] = d['Construction Price']
    d['target_insul_material'] = d['Insulation Material Price']
    d['target_insul_construction'] = d['Insulation Construction Price']
    d['target_bucket_sum'] = d[PRICE_BUCKETS].sum(axis=1, min_count=1)
    q = d['quantity'].replace(0, 1)
    for t in ['material','fabrication','construction','insul_material','insul_construction']:
        d[f'target_{t}_per_unit'] = d[f'target_{t}'] / q

    # research ratios (NOT targets; leakage if used as features)
    d['price_per_gal'] = d['target_bucket_sum'] / d['capacity_gal'].replace(0, np.nan)
    d['price_per_shellsqft'] = d['target_bucket_sum'] / d['shell_area_sqft'].replace(0, np.nan)
    d['material_per_shellsqft'] = d['target_material'] / d['shell_area_sqft'].replace(0, np.nan)

    return d

# ------------------------------------------------------------- data quality
def add_cleaning_columns(d):
    """P1-6: canonical company/customer names and price-independent scope markers,
    mirroring the Clean_Data formulas."""
    d = d.copy()
    for src, key, canon in [('Company Name', 'Company Key', 'Company Canonical'),
                            ('Customer Name', 'Customer Key', 'Customer Canonical')]:
        s = d[src].fillna('').astype(str)
        k = s.str.replace(r'[.,\-& ]', '', regex=True).str.upper()
        d[key] = k
        first = s.groupby(k).transform('first')
        d[canon] = np.where(k == '', '', first)
    n = d['Tank Name'].fillna('').astype(str).str.lower()
    d['Name Has Option'] = n.str.contains('option', regex=False).astype(int)
    terms = ['roof', 'deck', 'floor', 'demo', 'replacement', 'rings', 'shell course',
             'nozzle', 'ladder']
    d['Name Partial Scope'] = n.apply(lambda s: int(any(t in s for t in terms)))
    return d


def add_segment_price_flags(d):
    """P0-4: flag rows whose $/shell-sqft sits in the tails of its own
    material x scope_class segment. Mirrors the Clean_Data formulas exactly, including
    the rank-based percentile (fraction of the segment strictly below this row), so the
    Excel and pandas sides agree cell for cell.

    RETIRED AS A GATE (P0-4R, 2026-09-24). These columns are still computed and still
    published in the workbook as research output, but `dq_price_sane_segment` no longer
    enters `ml_eligible`. The rule was measured to be a SMALL-TANK filter rather than an
    outlier filter: $/shell-sqft is U-shaped in size (866 sqft -> $32.39 median, 3,377 ->
    $23.80, 9,041 -> $37.50) because small tanks amortize fixed cost over less area and
    very large tanks carry heavier plate. A segment key of Material x scope_class carries
    no size term, so ranking raw $/sqft inside it deletes the extremes of the SIZE
    distribution - including a $1,011,218 bioreactor (H=65.5, D=24.6) and a $1,346,843
    anaerobic digester (H=51.2, D=111.7). The linear corr(log area, log rate) is 0.016,
    which hides the U and is why the rule looked safe. It is replaced by
    `dq_implausible_geometry` (junk) and `dq_price_residual_outlier` (price, size-aware)."""
    d = d.copy()
    shell = np.pi * d['Diameter (ft)'] * d['Height (ft)']
    d['shell_area_dq'] = np.where((d['Diameter (ft)'] > 0) & (d['Height (ft)'] > 0), shell, np.nan)
    bs = d['target_bucket_sum']
    d['rate_per_shellsqft_dq'] = np.where((d['shell_area_dq'] > 0) & (bs > 0),
                                          bs / d['shell_area_dq'], np.nan)
    m = (d['Material Price'].fillna(0) > 1) | (d['Fabrication Price'].fillna(0) > 1)
    c = d['Construction Price'].fillna(0) > 1
    d['scope_class_dq'] = np.select([m & c, m & ~c, ~m & c],
                                    ['tank_quote', 'materials_only', 'construction_only'],
                                    default='unknown')
    d['price_segment'] = d['Material'].fillna('').astype(str) + '|' + d['scope_class_dq']

    rate = d['rate_per_shellsqft_dq']
    valid = rate.notna() & (rate > 0)
    seg_n = d['price_segment'].map(d.loc[valid, 'price_segment'].value_counts()).fillna(0).astype(int)
    d['segment_n'] = seg_n
    rank = pd.Series(np.nan, index=d.index)
    for s, idx in d.loc[valid].groupby('price_segment').groups.items():
        vals = rate.loc[idx]
        rank.loc[idx] = vals.apply(lambda v: int((vals < v).sum()))
    d['segment_rank_below'] = rank
    d['segment_pctile'] = np.where(seg_n > 0, rank / seg_n.replace(0, np.nan), np.nan)
    pct = d['segment_pctile']
    d['dq_price_sane_segment'] = np.where(
        pct.isna(), 1, np.where(seg_n < 30, 1, np.where((pct < 0.015) | (pct > 0.99), 0, 1))).astype(int)
    return d


def add_quality_flags(d):
    d = d.copy()
    d['dq_has_geometry'] = ((d['Diameter (ft)'] > 0) & (d['Height (ft)'] > 0)).astype(int)
    d['dq_has_capacity'] = (d['Capacity Value'] > 0).astype(int)
    d['dq_has_positive_target'] = (d['target_bucket_sum'] > 0).astype(int)
    # price sanity: reasonable per-tank proposal band
    pt = d['Proposal Total']
    d['dq_price_sane'] = ((pt >= 1000) & (pt <= 50_000_000)).astype(int)
    # non-tank / junk heuristics
    name = (d['Tank Name'].astype(str) + ' ' + d['QuoteNumber'].astype(str) + ' ' +
            d['Use Type'].fillna('').astype(str)).str.lower()
    d['dq_looks_nontank'] = name.apply(lambda s: int(any(k in s for k in JUNK_WORDS)))
    d['dq_is_unfinished'] = d['Status'].astype(str).str.lower().isin(['unfinished','bid review']).astype(int)

    # P0-4R (a): the junk rule the retired segment trim was actually built for. Deck,
    # floor and roof REPLACEMENT jobs are quoted as tanks with the height entered as a
    # placeholder - the motivating rows all carry Height = 0.22 ft. Shell area is
    # meaningless on them, so every rate-based statistic explodes. This is pure geometry:
    # it touches no price, so unlike the segment trim it cannot delete an expensive tank
    # for being expensive. 3 ft is below the smallest genuine tank height in the archive.
    h, dia = d['Height (ft)'], d['Diameter (ft)']
    d['dq_implausible_geometry'] = ((h < 3) | (dia < 3)).fillna(False).astype(int)
    return d


# Studentized-residual cutoff for the P0-4R price rule. 4 sigma on a log-price model with
# ~4.4K observations is roughly a 1-in-15,000 event under normality, so it fires on the
# genuinely unexplainable rows rather than on the tails of the size distribution.
PRICE_RESID_Z_CUTOFF = 4.0
# A categorical level thinner than this is pooled into '(Other)' so the design matrix stays
# well conditioned; a singleton level would otherwise have leverage 1 and residual 0.
_MIN_LEVEL_N = 10


def add_price_residual_flag(d, z_cut=PRICE_RESID_Z_CUTOFF):
    """P0-4R (b): a price-outlier rule that respects SIZE, GRADE and SCOPE together
    instead of raw $/shell-sqft.

    Fits, on the eligible rows only, an OLS model of

        log(target_material) ~ log(area) + log(area)^2 + log(H) + log(D)
                               + C(Material) + C(Wage Type) + C(scope)

    and flags |studentized residual| > 4. The quadratic in log(area) is what the retired
    segment trim was missing: it lets the model carry the U-shape in $/sqft, so being a
    very small or a very large tank is priced in rather than punished.

    statsmodels is not installed in this environment, so the fit is sklearn's
    LinearRegression (a least-squares driver, not a hand-rolled solve) and the hat
    diagonal comes from numpy's pseudo-inverse.

    Leaves two columns:
      price_resid_z                  signed studentized residual (LEAKAGE - it is built
                                     from target_material; research output only)
      dq_price_residual_outlier      1 when |price_resid_z| > z_cut (also leakage)
    """
    from sklearn.linear_model import LinearRegression

    d = d.copy()
    H, D, A = d['Height (ft)'], d['Diameter (ft)'], d['shell_area_sqft']
    y = d['target_material']
    usable = ((A > 0) & (H > 0) & (D > 0) & (y > 0)).fillna(False)

    # Fit sample = rows the DQ layer keeps on every rule EXCEPT this one. Row grain, not
    # firmest grain, matching how every other dq_* flag is evaluated.
    base_ok = (d['dq_has_geometry'].eq(1) & d['dq_has_positive_target'].eq(1) &
               d['dq_price_sane'].eq(1) & d['dq_looks_nontank'].eq(0) &
               d['dq_is_unfinished'].eq(0) & d['dq_implausible_geometry'].eq(0))
    fit_mask = usable & base_ok

    log_area = np.log(A.where(usable))
    num = pd.DataFrame({
        'log_area': log_area,
        'log_area_sq': log_area ** 2,
        'log_height': np.log(H.where(usable)),
        'log_diameter': np.log(D.where(usable)),
    }, index=d.index)

    cats = pd.DataFrame({
        'material': d['Material'].fillna('(Missing)').astype(str),
        'wage_type': d['Wage Type'].fillna('(Missing)').astype(str),
        'scope': d['scope_class_dq'].astype(str),
    }, index=d.index)
    for c in cats.columns:
        vc = cats.loc[fit_mask, c].value_counts()
        keep = set(vc[vc >= _MIN_LEVEL_N].index)
        cats[c] = cats[c].where(cats[c].isin(keep), '(Other)')

    X = pd.concat([num, pd.get_dummies(cats, drop_first=True, dtype=float)], axis=1)
    X = X.astype(float).fillna(0.0)

    Xf = X[fit_mask].to_numpy()
    yf = np.log(y[fit_mask].to_numpy(dtype=float))
    model = LinearRegression().fit(Xf, yf)

    # Hat diagonal from the design matrix WITH its intercept column.
    Zf = np.column_stack([np.ones(len(Xf)), Xf])
    ztz_inv = np.linalg.pinv(Zf.T @ Zf)
    rank = int(np.linalg.matrix_rank(Zf))
    resid_f = yf - model.predict(Xf)
    sigma = float(np.sqrt((resid_f ** 2).sum() / max(len(Xf) - rank, 1)))

    idx = d.index[usable]
    Xu = X.loc[idx].to_numpy()
    Zu = np.column_stack([np.ones(len(Xu)), Xu])
    hu = np.clip(np.einsum('ij,jk,ik->i', Zu, ztz_inv, Zu), 0.0, 0.999)
    resid_u = np.log(y.loc[idx].to_numpy(dtype=float)) - model.predict(Xu)
    z = resid_u / (sigma * np.sqrt(1.0 - hu))

    d['price_resid_z'] = pd.Series(z, index=idx).reindex(d.index)
    d['dq_price_residual_outlier'] = (d['price_resid_z'].abs() > z_cut).fillna(False).astype(int)
    return d


def add_eligibility(d):
    """Row eligibility for modelling.

    P0-4R: `dq_price_sane_segment` is GONE from this rule - it was a small-tank filter,
    see add_segment_price_flags. In its place are a pure-geometry junk rule and a
    size-aware residual price rule. The global $1K-$50M band stays as the backstop."""
    d = d.copy()
    d['ml_eligible'] = (
        d['dq_has_geometry'].eq(1) &
        d['dq_has_positive_target'].eq(1) &
        d['dq_price_sane'].eq(1) &                  # global band, backstop
        d['dq_implausible_geometry'].eq(0) &        # P0-4R (a) junk geometry
        d['dq_price_residual_outlier'].eq(0) &      # P0-4R (b) size-aware price residual
        d['dq_looks_nontank'].eq(0) &
        d['dq_is_unfinished'].eq(0)
    ).astype(int)
    # recommended training set: eligible + current (firmest) revision
    d['ml_training_row'] = (d['ml_eligible'].eq(1) & d['Is Current Revision']).astype(int)
    return d


def build_all():
    df = load_clean()
    df = add_features(df)
    df = add_cleaning_columns(df)        # P1-6
    df = add_segment_price_flags(df)     # P0-4 research output, no longer a gate
    df = add_quality_flags(df)
    df = add_price_residual_flag(df)     # P0-4R (b), needs the base dq_* flags
    df = add_eligibility(df)
    return df

if __name__ == '__main__':
    d = build_all()
    d.to_pickle('featured.pkl')
    print('rows', len(d), 'cols', d.shape[1])
    print('ml_eligible', d['ml_eligible'].sum(), ' training rows (eligible+current)', d['ml_training_row'].sum())
