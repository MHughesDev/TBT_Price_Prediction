"""Request -> model feature row.

THIS IS THE HIGHEST-RISK MODULE IN THE SYSTEM. Every derivation here must match build/prep.py
exactly, or training and serving quietly disagree and the model degrades with no error raised.
`service/test_parity.py` enforces that against all 4,459 training rows and must stay green.

Anything that cannot be known when an estimator asks for a price is deliberately absent - see
SERVE_SAFE_EXCLUDED and docs/BUILD_PLAN.md.
"""
from __future__ import annotations
import re
import numpy as np
import pandas as pd

from schema import TankRequest
from tank_types import tank_type as _tank_type

GAL_PER_CUFT = 7.48052
GRADE_RANK = {'CS': 1, '304SS': 2, '316SS': 3}
GRADE_DENSITY = {'CS': 1.0, '304SS': 1.15, '316SS': 1.25}
REF_DATE = pd.Timestamp('2020-01-01')

# Columns present in the export but NOT usable at serve time. Kept here as documentation so a
# future change that reintroduces one is an obvious diff.
SERVE_SAFE_EXCLUDED = (
    'Quote #', 'Revision #', 'Job Revision Count', 'Job Rev First Row',       # process / identity
    'Margin (%)', 'Contingency (%)', 'Commission (%)',                        # business policy
    'Insulation Margin (%)', 'Insulation Contingency (%)',
    'Name Has Option', 'Name Partial Scope',                                  # free-text parse
    'tank_count_in_quoterev', 'is_multi_tank_quote',                          # whole-quote context
    # Free text with 3,154 distinct values in 4,459 rows - a near-identifier that duplicates
    # Capacity Value / Unit / Category. Measured contribution 0.00% gain, and removing it
    # slightly IMPROVES both buckets (material .0837->.0834, construction .1147->.1137).
    # Left in it would also make almost every live request report an unseen category.
    'Usable Capacity',
)


# --------------------------------------------------------------------------- small parsers
def parse_capacity(v):
    """Mirrors prep.py parse_cap, including keeping a leading minus: 44 source rows read like
    '-937.376tons', and dropping the sign turns an impossible value into a plausible one."""
    if v is None or (isinstance(v, float) and v != v):
        return (np.nan, None)
    s = str(v).lower().replace(',', '').strip()
    m = re.search(r'(-?[\d.]+)', s)
    val = float(m.group(1)) if m else np.nan
    unit = 'tons' if 'ton' in s else ('gal' if 'gal' in s else None)
    return (val, unit)


def seismic_band(x):
    if x is None or (isinstance(x, float) and x != x):
        return 'Unknown'
    if x < 0.25: return '1. Very Low (<0.25)'
    if x < 0.50: return '2. Low (0.25-0.5)'
    if x < 1.00: return '3. Moderate (0.5-1.0)'
    if x < 1.50: return '4. High (1.0-1.5)'
    return '5. Very High (1.5+)'


def distance_band(x):
    if x is None or (isinstance(x, float) and x != x):
        return 'Unknown'
    if x < 100: return '1. <100 mi'
    if x < 500: return '2. 100-500 mi'
    if x < 1000: return '3. 500-1000 mi'
    if x < 2000: return '4. 1000-2000 mi'
    return '5. 2000+ mi'


def capacity_category(v, u):
    if v is None or (isinstance(v, float) and v != v) or v <= 0 or u is None:
        return 'Unknown'
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


def roof_geometry(deck_style):
    s = str(deck_style)
    if 'Dome' in s: return 'dome'
    if 'Open-Top' in s: return 'open_top'
    if ':12' in s: return 'pitched'
    if s in ('', 'nan', 'None', '(Not Specified)'): return 'unknown'
    return 'flat'


def floor_geometry(floor_style):
    s = str(floor_style)
    if 'Slope' in s: return 'sloped'
    if 'Flat' in s: return 'flat'
    if 'Ring' in s or 'Base Angle' in s: return 'no_supplied_floor_plate'
    if s in ('', 'nan', 'None', '(Not Specified)'): return 'unknown'
    return 'special'


def _geo_lookup(country, state):
    """Country|State -> (country_iso, country_name, region_name, region_code, level, note).

    State alone is ambiguous across countries (BC+CA is British Columbia, BC+MX is Baja
    California), and the source Country column is wrong on 37 rows, so the key is the pair.
    """
    import sys, pathlib
    bd = str(pathlib.Path(__file__).resolve().parents[1] / 'build')
    if bd not in sys.path:
        sys.path.insert(0, bd)
    import geo_crosswalk as GEO
    return GEO.lookup(str(country or '').strip(), str(state or '').strip())


# --------------------------------------------------------------------------- the feature row
def build_row(req: TankRequest) -> dict:
    """One request -> one dict of model features. Pure; no I/O beyond the geo crosswalk."""
    D = float(req.diameter_ft)
    H = float(req.height_ft)
    mat = req.material

    shell_area = np.pi * D * H
    floor_area = np.pi * (D / 2) ** 2
    roof_area = floor_area
    total_area = shell_area + floor_area + roof_area

    freeboard_in = np.nan if req.freeboard_in is None else float(req.freeboard_in)
    freeboard_ft = freeboard_in / 12.0
    geom_cuft = np.pi * (D / 2) ** 2 * H
    geom_gal = geom_cuft * GAL_PER_CUFT

    cap_val, cap_unit = parse_capacity(req.usable_capacity)
    pos = (not np.isnan(cap_val)) and cap_val > 0
    capacity_gal = cap_val if (cap_unit == 'gal' and pos) else np.nan
    capacity_tons = cap_val if (cap_unit == 'tons' and pos) else np.nan

    ss = np.nan if req.ss is None else float(req.ss)
    s1 = np.nan if req.s1 is None else float(req.s1)
    m_tbt = np.nan if req.miles_from_tbt is None else float(req.miles_from_tbt)
    m_gt = np.nan if req.miles_from_gt is None else float(req.miles_from_gt)
    # Minimum over POSITIVE distances only. A zero plant distance means the figure was never
    # computed (Miles GT is a literal 0 on 1,853 archive rows), not that the site sits at the
    # plant. A plain min drags the result to zero on rows whose real distance is ~800 miles.
    _pos = [x for x in (m_tbt, m_gt) if x == x and x > 0]
    min_miles = float(min(_pos)) if _pos else np.nan

    cc, cname, st_norm, region, _lvl, _note = _geo_lookup(req.country, req.state)

    # The pipeline keeps the RAW value in these columns and only fills for derived flags.
    deck, floor = req.deck_style, req.floor_style
    dstr = str(deck) if deck is not None else '(Not Specified)'
    fstr = str(floor) if floor is not None else '(Not Specified)'
    slope_m = re.search(r'(\d+):12', dstr)
    roof_slope = (float(slope_m.group(1)) / 12.0) if slope_m else np.nan

    erection, _src = req.erection_scope()
    d = pd.Timestamp(req.priced_on)

    row = {
        # --- raw, as the pipeline stores them
        'Diameter (ft)': D, 'Height (ft)': H, 'Material': mat,
        'Use Type': req.use_type, 'Deck Style': deck, 'Floor Style': floor,
        'Freeboard (in)': freeboard_in, 'Usable Capacity': req.usable_capacity,
        'Quantity': req.quantity, 'Wage Type': req.wage_type,
        'Ss': ss, 'S1': s1,
        'Miles to Site (From TBT)': m_tbt, 'Miles to Site (From GT)': m_gt,
        'Capacity Value': cap_val, 'Capacity Unit': cap_unit,
        'Country Normalized': cc, 'Country Name': cname,
        'State Normalized': st_norm, 'Region Code': region,

        # --- geometry
        'geom_volume_cuft': geom_cuft, 'geom_volume_gal': geom_gal,
        'shell_area_sqft': shell_area, 'floor_area_sqft': floor_area,
        'roof_area_sqft': roof_area, 'total_area_sqft': total_area,
        'circumference_ft': np.pi * D,
        'aspect_ratio_hd': H / D if D else np.nan,
        'diameter_sq': D ** 2, 'height_sq': H ** 2, 'd_x_h': D * H,
        'freeboard_ft': freeboard_ft,
        'freeboard_ratio': freeboard_ft / H if H else np.nan,
        'capacity_gal': capacity_gal, 'capacity_tons': capacity_tons,
        'is_ton_capacity': int(cap_unit == 'tons'),
        'fill_ratio': (capacity_gal / geom_gal) if geom_gal else np.nan,
        'liquid_height_ft': H - (0.0 if np.isnan(freeboard_in) else freeboard_in / 12.0),
        'Capacity Category': capacity_category(cap_val, cap_unit),

        # --- material
        'material_grade_rank': GRADE_RANK.get(mat, 0),
        'is_stainless': int(mat in ('304SS', '316SS')),
        'material_area_intensity': shell_area * GRADE_DENSITY.get(mat, 1.0),

        # --- seismic
        'seismic_band': seismic_band(ss), 'high_seismic': int(ss >= 0.5) if ss == ss else 0,
        's1_ss_ratio': (s1 / ss) if (ss == ss and ss != 0) else np.nan,
        'seismic_x_height': ss * H, 'seismic_x_shell': ss * shell_area,

        # --- site
        'min_miles': min_miles, 'distance_band': distance_band(min_miles),
        'is_domestic': int(cc == 'US'), 'is_international': int(cc != 'US'),
        'is_local_site': int(min_miles == min_miles and min_miles < 50),

        # --- labour / scope
        'is_prevailing_wage': int(req.wage_type == 'Prevailing Wage'),
        'is_union': int(req.wage_type == 'Union Wage'),
        'no_erection_scope': int(not erection), 'has_erection_scope': int(erection),

        # --- deck / floor
        'deck_is_dome': int('dome' in dstr.lower()),
        'deck_is_open_top': int('open-top' in dstr.lower()),
        'deck_has_rafters': int('rafter' in dstr.lower()),
        'deck_is_selfsupp': int('self supported' in dstr.lower()),
        'deck_is_centersupp': int('center supported' in dstr.lower()),
        'roof_slope_ratio': roof_slope,
        'roof_area_sloped_sqft': floor_area * np.sqrt(1 + (0.0 if roof_slope != roof_slope
                                                           else roof_slope) ** 2),
        'floor_is_embedded_ring': int('embedded ring' in fstr.lower()),
        'floor_is_flat': int('flat' in fstr.lower()),
        'floor_is_sloped': int('slope' in fstr.lower()),
        'floor_is_special': int(fstr == 'Special'),
        'roof_geometry': roof_geometry(dstr), 'floor_geometry': floor_geometry(fstr),

        # --- quantity
        'quantity': req.quantity,
        'qty_x_shell_area': req.quantity * shell_area,

        # --- time
        'due_year': d.year, 'due_quarter': d.quarter, 'due_month': d.month,
        'months_since_2020': (d - REF_DATE).days / 30.44,
        't_year': float(d.year), 't_month': (d.year - 2020) * 12 + d.month,
    }
    row['liquid_volume_gal'] = np.pi * (D / 2) ** 2 * max(row['liquid_height_ft'], 0) * GAL_PER_CUFT
    row['gate_insul'] = int(req.insulation_scope()[0])
    row['tank_type'] = _tank_type(req.use_type)
    return row


def build_frame(reqs) -> pd.DataFrame:
    """Requests -> model-ready frame, physics features included."""
    df = pd.DataFrame([build_row(r) for r in reqs])
    return pd.concat([df, _physics(df)], axis=1)


def _physics(df: pd.DataFrame) -> pd.DataFrame:
    import sys, pathlib
    md = str(pathlib.Path(__file__).resolve().parents[1] / 'ml')
    if md not in sys.path:
        sys.path.insert(0, md)
    from physics import add_physics
    return add_physics(df)


# --------------------------------------------------------------------------- feature contract
def model_features(manifest_features, has_insul_gate: bool, with_tank_type: bool = False) -> list:
    """The ordered feature list a model consumes: serve-safe pipeline features, plus time,
    plus physics, plus the insulation gate for the two insulation buckets.

    `with_tank_type` adds the preset segment as a categorical. Measured as roughly neutral
    (see docs/TANK_TYPE_COMPARISON.md) - kept selectable rather than assumed."""
    base = [c for c in manifest_features if c not in SERVE_SAFE_EXCLUDED]
    return (base + ['t_year', 't_month'] + PHYSICS_FEATURES
            + (['gate_insul'] if has_insul_gate else [])
            + (['tank_type'] if with_tank_type else []))


PHYSICS_FEATURES = [
    'phys_shell_lb', 'phys_floor_lb', 'phys_roof_lb', 'phys_steel_lb', 'phys_log_steel_lb',
    'phys_shell_share', 'phys_t_design_in', 'phys_t_min_in', 'phys_t_governing_in',
    'phys_min_governs', 'phys_t_ratio', 'phys_lb_per_sqft', 'phys_liquid_lb',
    'phys_overturn_moment', 'phys_anchorage_ratio', 'phys_slenderness', 'phys_hoop_force',
]
