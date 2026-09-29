"""Turn the raw quote export into one clean modelling table.

Reads  data/archive.csv    one row per tank per quote revision, prices as text like "$5,172.08"
Writes data/tanks.parquet  every priced tank revision, with features, prices and flags

    python prepare.py
"""
import re
import numpy as np
import pandas as pd

import geo
from physics import add_physics

SOURCE = 'data/archive.csv'
OUTPUT = 'data/tanks.parquet'

# The five things we predict, all in dollars per tank. Freight and tax are NOT predicted.
BUCKETS = {
    'material': 'Material Price',
    'fabrication': 'Fabrication Price',
    'construction': 'Construction Price',
    'insul_material': 'Insulation Material Price',
    'insul_construction': 'Insulation Construction Price',
}
PRICE = {bucket: f'price_{bucket}' for bucket in BUCKETS}

# Words in a tank name that mean the row is a part, a test, or a demo - not a tank.
NOT_A_TANK = ['elbow', 'audit', 'standard part', 'part test', 'nozzle', 'fitting', 'spare',
              'conduit', 'platform only', 'test 1', 'options test', 'estimate 1']

# Model inputs. Everything here is known when an estimator asks for a price. Deliberately
# left out: margin, contingency, commission (pricing policy, applied after), quote number and
# revision fields (identity, not spec), and anything computed from a price.
CATEGORICAL = [
    'Material', 'Wage Type', 'Use Type', 'Deck Style', 'Floor Style',
    'country', 'region', 'seismic_band', 'distance_band', 'capacity_band',
    'roof_type', 'floor_type',
]
NUMERIC = [
    # the spec as entered
    'Diameter (ft)', 'Height (ft)', 'Freeboard (in)', 'Ss', 'S1', 'quantity',
    'Miles to Site (From TBT)', 'Miles to Site (From GT)', 'capacity_gal', 'capacity_tons',
    # scope, which the estimator decides and tells us
    'erection_in_scope', 'insulation_selected',
    # geometry
    'shell_area_sqft', 'floor_area_sqft', 'roof_area_sqft', 'total_area_sqft',
    'volume_gal', 'liquid_height_ft', 'liquid_volume_gal', 'aspect_ratio', 'freeboard_ratio',
    'fill_ratio', 'roof_slope', 'quantity_x_shell_area',
    # options, parsed from the style text
    'deck_is_dome', 'deck_is_open_top', 'deck_has_rafters', 'deck_is_self_supported',
    'deck_is_center_supported', 'floor_is_embedded_ring', 'floor_is_flat', 'floor_is_sloped',
    # material, labour, site
    'material_rank', 'is_stainless', 'is_prevailing_wage', 'is_union', 'is_domestic',
    'min_miles', 'is_local_site', 'seismic_x_height', 'seismic_x_shell', 's1_to_ss',
    # time
    'due_year', 'due_month', 'months_since_2020',
]
PHYSICS = [
    'phys_shell_lb', 'phys_floor_lb', 'phys_roof_lb', 'phys_steel_lb', 'phys_log_steel_lb',
    'phys_shell_share', 'phys_t_design_in', 'phys_t_min_in', 'phys_t_governing_in',
    'phys_min_governs', 'phys_t_ratio', 'phys_lb_per_sqft', 'phys_liquid_lb',
    'phys_overturn_moment', 'phys_anchorage_ratio', 'phys_slenderness', 'phys_hoop_force',
]
FEATURES = CATEGORICAL + NUMERIC + PHYSICS


# ---------------------------------------------------------------------------- load
def to_number(text):
    """'$5,172.08' -> 5172.08, '20%' -> 20, '(5)' -> -5."""
    text = text.astype(str).str.strip()
    negative = text.str.startswith('(') & text.str.endswith(')')
    number = pd.to_numeric(text.str.replace(r'[$,%()]', '', regex=True), errors='coerce')
    return number.where(~negative, -number)


def to_text(text):
    text = text.astype(str).str.strip().str.replace(r'\s+', ' ', regex=True)
    blank = text.str.lower().isin(['', 'null', 'none', 'n/a', 'na', '-', 'nan'])
    return text.where(~blank)


def load():
    tanks = pd.read_csv(SOURCE, dtype=str)
    numbers = list(BUCKETS.values()) + [
        'Total Tax', 'Proposal Total', 'Freight Price', 'Diameter (ft)', 'Height (ft)',
        'Freeboard (in)', 'Ss', 'S1', 'Miles to Site (From TBT)', 'Miles to Site (From GT)',
        'Quantity', 'Revision #']
    texts = ['Status', 'Tank Name', 'Country', 'State', 'Wage Type', 'Material', 'Use Type',
             'Deck Style', 'Floor Style', 'Usable Capacity']
    for column in numbers:
        tanks[column] = to_number(tanks[column])
    for column in texts:
        tanks[column] = to_text(tanks[column])
    tanks['Quote #'] = tanks['Quote #'].str.strip()
    tanks['Tank Name'] = tanks['Tank Name'].fillna('Tank ?')
    tanks['due_date'] = pd.to_datetime(tanks['Due Date'], format='%m/%d/%Y', errors='coerce')
    for bucket, column in BUCKETS.items():
        # Prices of $1 or less are placeholders ($0.01 = "in scope, not priced yet").
        tanks[PRICE[bucket]] = tanks[column].fillna(0).where(tanks[column] > 1, 0.0)
    tanks['freight'] = tanks['Freight Price'].fillna(0)
    tanks['tax'] = tanks['Total Tax'].fillna(0)
    return tanks


# ---------------------------------------------------------------------------- jobs
def quote_suffix_kind(suffix):
    """What the text after the 7-digit quote number means."""
    s = suffix.lower()
    if s == '':
        return 'none'
    if 'as sold' in s or 'as approved' in s:
        return 'snapshot'
    if re.search(r'co#|\bco\s*\d|option|only|materials|eng', s):
        return 'scope_variant'   # change orders, options, "materials only": different work
    if re.match(r'^r\d', s):
        return 'revision'
    return 'scope_variant'


def add_jobs(tanks):
    """A job is the first 7 digits of the quote number. Keep one row per tank at the job's
    firmest (highest) revision: that is the price the customer actually saw last."""
    quote = tanks['Quote #']
    numeric = quote.str[:7].str.fullmatch(r'\d{7}').fillna(False)
    tanks['job_id'] = np.where(numeric, quote.str[:7], quote)
    suffix = np.where(numeric, quote.str[7:].str.strip().str.lstrip('-').str.strip(), '')
    kind = pd.Series(suffix, index=tanks.index).map(quote_suffix_kind)
    suffix_revision = pd.Series(suffix, index=tanks.index).str.extract(r'^[Rr](\d+)')[0]
    suffix_revision = suffix_revision.astype(float).where(kind == 'revision', 0).fillna(0)
    revision = np.maximum(tanks['Revision #'].fillna(0), suffix_revision)

    # Scope variants of one job are separate pieces of work, so they keep separate rows.
    variant = tanks['job_id'] + '|' + np.where(kind == 'scope_variant', suffix, '')
    firmest = revision == revision.groupby(variant).transform('max')
    tank_in_variant = variant + '|' + tanks['Tank Name']
    first_time_seen = ~tank_in_variant.where(firmest).duplicated() & firmest
    tanks['is_firmest'] = first_time_seen.astype(int)
    tanks['tank_key'] = tanks['Quote #'] + '-R' + tanks['Revision #'].astype('Int64').astype(str) \
        + '-' + tanks['Tank Name']
    return tanks


# ---------------------------------------------------------------------------- features
def band(value, edges, labels):
    return pd.cut(value, [-np.inf] + edges + [np.inf], labels=labels, right=False) \
        .astype(str).where(value.notna(), 'Unknown')


def add_features(tanks):
    t = tanks
    diameter, height = t['Diameter (ft)'], t['Height (ft)']
    t['quantity'] = t['Quantity'].fillna(1)
    t['erection_in_scope'] = (t[PRICE['construction']] > 0).astype(int)
    t['insulation_selected'] = ((t[PRICE['insul_material']] + t[PRICE['insul_construction']]) > 0).astype(int)

    # geometry
    t['shell_area_sqft'] = np.pi * diameter * height
    t['floor_area_sqft'] = np.pi * (diameter / 2) ** 2
    t['roof_slope'] = t['Deck Style'].str.extract(r'(\d+):12')[0].astype(float) / 12
    t['roof_area_sqft'] = t['floor_area_sqft'] * np.sqrt(1 + t['roof_slope'].fillna(0) ** 2)
    # The rate-table unit: shell + floor + a flat roof. Kept exactly as before so the
    # baseline stays comparable with earlier work.
    t['total_area_sqft'] = t['shell_area_sqft'] + 2 * t['floor_area_sqft']
    t['volume_gal'] = t['floor_area_sqft'] * height * 7.48052
    t['liquid_height_ft'] = height.fillna(0) - t['Freeboard (in)'].fillna(0) / 12
    t['liquid_volume_gal'] = t['floor_area_sqft'].fillna(0) * t['liquid_height_ft'].clip(lower=0) * 7.48052
    t['aspect_ratio'] = height / diameter.replace(0, np.nan)
    t['freeboard_ratio'] = t['Freeboard (in)'] / 12 / height.replace(0, np.nan)
    t['quantity_x_shell_area'] = t['quantity'] * t['shell_area_sqft']

    # capacity is free text like "250,000gal" or "937.4tons"; negative means missing
    capacity = t['Usable Capacity'].str.lower().str.replace(',', '')
    amount = capacity.str.extract(r'(-?[\d.]+)')[0].astype(float)
    amount = amount.where(amount > 0)
    t['capacity_gal'] = amount.where(capacity.str.contains('gal', na=False))
    t['capacity_tons'] = amount.where(capacity.str.contains('ton', na=False))
    t['fill_ratio'] = t['capacity_gal'] / t['volume_gal'].replace(0, np.nan)
    t['capacity_band'] = np.select(
        [t['capacity_gal'] < 50e3, t['capacity_gal'] < 250e3, t['capacity_gal'] < 1e6,
         t['capacity_gal'] >= 1e6, t['capacity_tons'] < 100, t['capacity_tons'] < 500,
         t['capacity_tons'] >= 500],
        ['gal <50K', 'gal 50K-250K', 'gal 250K-1M', 'gal 1M+',
         'tons <100', 'tons 100-500', 'tons 500+'], default='Unknown')

    # roof and floor options
    deck, floor = t['Deck Style'].fillna(''), t['Floor Style'].fillna('')
    for column, word in [('deck_is_dome', 'Dome'), ('deck_is_open_top', 'Open-Top'),
                         ('deck_has_rafters', 'Rafter'), ('deck_is_self_supported', 'Self Supported'),
                         ('deck_is_center_supported', 'Center Supported')]:
        t[column] = deck.str.contains(word, case=False).astype(int)
    for column, word in [('floor_is_embedded_ring', 'Embedded Ring'), ('floor_is_flat', 'Flat'),
                         ('floor_is_sloped', 'Slope')]:
        t[column] = floor.str.contains(word, case=False).astype(int)
    t['roof_type'] = np.select([deck.str.contains('Dome'), deck.str.contains('Open-Top'),
                                deck.str.contains(':12'), deck.eq('')],
                               ['dome', 'open_top', 'pitched', 'unknown'], default='flat')
    t['floor_type'] = np.select([floor.str.contains('Slope'), floor.str.contains('Flat'),
                                 floor.str.contains('Ring|Base Angle'), floor.eq('')],
                                ['sloped', 'flat', 'no_floor_plate', 'unknown'], default='special')

    # material and labour
    t['material_rank'] = t['Material'].map({'CS': 1, '304SS': 2, '316SS': 3}).fillna(0)
    t['is_stainless'] = t['Material'].isin(['304SS', '316SS']).astype(int)
    t['is_prevailing_wage'] = t['Wage Type'].eq('Prevailing Wage').astype(int)
    t['is_union'] = t['Wage Type'].eq('Union Wage').astype(int)

    # site
    places = [geo.lookup(c, s) for c, s in zip(t['Country'], t['State'])]
    t['country'] = [country for country, _ in places]
    t['region'] = [region for _, region in places]
    t['is_domestic'] = t['country'].eq('US').astype(int)
    miles = t[['Miles to Site (From TBT)', 'Miles to Site (From GT)']]
    t['min_miles'] = miles.where(miles > 0).min(axis=1)   # 0 means "never computed", not "on site"
    t['is_local_site'] = (t['min_miles'] < 50).astype(int)
    t['distance_band'] = band(t['min_miles'], [100, 500, 1000, 2000],
                              ['<100', '100-500', '500-1000', '1000-2000', '2000+'])
    t['seismic_band'] = band(t['Ss'], [0.25, 0.5, 1.0, 1.5],
                             ['very low', 'low', 'moderate', 'high', 'very high'])
    t['seismic_x_height'] = t['Ss'] * height
    t['seismic_x_shell'] = t['Ss'] * t['shell_area_sqft']
    t['s1_to_ss'] = t['S1'] / t['Ss'].replace(0, np.nan)

    # time: the due date is the only date in the data
    t['due_year'] = t['due_date'].dt.year
    t['due_month'] = t['due_date'].dt.month
    t['months_since_2020'] = (t['due_year'] - 2020) * 12 + t['due_month']

    t = pd.concat([t, add_physics(t)], axis=1)
    t[CATEGORICAL] = t[CATEGORICAL].fillna('Unknown').astype('category')
    return t


# ---------------------------------------------------------------------------- quality
def price_outliers(tanks, usable):
    """Flag tanks whose material price is > 4 standard errors from what a simple size-aware
    regression expects. Size must be in the model: $/sqft is U-shaped in tank size, so a
    rule without it throws away the smallest and largest real tanks."""
    area, height, diameter = tanks['shell_area_sqft'], tanks['Height (ft)'], tanks['Diameter (ft)']
    price = tanks[PRICE['material']]
    has_values = (area > 0) & (height > 0) & (diameter > 0) & (price > 0)
    supply = (tanks[PRICE['material']] > 0) | (tanks[PRICE['fabrication']] > 0)
    erect = tanks[PRICE['construction']] > 0
    scope = np.select([supply & erect, supply, erect], ['full', 'supply_only', 'erect_only'], 'other')
    columns = {'log_area': np.log(area), 'log_area_sq': np.log(area) ** 2,
               'log_height': np.log(height), 'log_diameter': np.log(diameter)}
    design = pd.DataFrame(columns, index=tanks.index)
    design.loc[~has_values] = 0.0
    for name, values in [('material', tanks['Material'].astype(str)),
                         ('wage', tanks['Wage Type'].astype(str)), ('scope', scope)]:
        values = pd.Series(values, index=tanks.index)
        common = values[usable & has_values].value_counts()
        values = values.where(values.isin(common[common >= 10].index), 'other')
        design = design.join(pd.get_dummies(values, prefix=name, drop_first=True, dtype=float))
    design.insert(0, 'intercept', 1.0)

    fit = usable & has_values
    x, y = design[fit].to_numpy(), np.log(price[fit].to_numpy())
    coef, *_ = np.linalg.lstsq(x, y, rcond=None)
    sigma = np.sqrt(((y - x @ coef) ** 2).sum() / (len(y) - np.linalg.matrix_rank(x)))
    x_all = design.to_numpy()
    leverage = np.einsum('ij,jk,ik->i', x_all, np.linalg.pinv(x.T @ x), x_all).clip(0, 0.999)
    residual = (np.log(price.where(has_values, 1)) - x_all @ coef) / (sigma * np.sqrt(1 - leverage))
    return has_values & (residual.abs() > 4)


def add_quality(tanks):
    """eligible = 1 if the row is a real, sensibly priced tank. Returns rule counts too."""
    name = (tanks['Tank Name'] + ' ' + tanks['Quote #'] + ' ' + tanks['Use Type'].astype(str)).str.lower()
    total = tanks['Proposal Total']
    rules = {
        'price outside $1K-$50M': ~total.between(1_000, 50_000_000),
        # deck/floor/roof repair jobs entered as tanks, with a placeholder height like 0.22 ft
        'height or diameter < 3 ft': (tanks['Height (ft)'] < 3) | (tanks['Diameter (ft)'] < 3),
        'not a tank (part/test/demo)': name.apply(lambda s: any(word in s for word in NOT_A_TANK)),
        'quote unfinished': tanks['Status'].str.lower().isin(['unfinished', 'bid review']),
    }
    usable = ~pd.concat(rules, axis=1).any(axis=1)
    rules['material price outlier'] = price_outliers(tanks, usable)
    failed = pd.concat(rules, axis=1)
    tanks['eligible'] = (~failed.any(axis=1)).astype(int)
    return tanks, failed


def main():
    tanks = add_features(add_jobs(load()))
    priced = tanks[list(PRICE.values())].sum(axis=1) > 0
    has_geometry = (tanks['Diameter (ft)'] > 0) & (tanks['Height (ft)'] > 0)
    tanks = tanks[priced & has_geometry].reset_index(drop=True)
    tanks, failed = add_quality(tanks)

    keep = ['tank_key', 'job_id', 'due_date', 'is_firmest', 'eligible', 'freight', 'tax'] \
        + list(PRICE.values()) + FEATURES
    tanks[keep].to_parquet(OUTPUT, index=False)

    firmest = tanks['is_firmest'] == 1
    print(f'wrote {OUTPUT}: {len(tanks):,} priced tank revisions')
    print(f'  firmest revision of each tank: {firmest.sum():,}, of which eligible: '
          f'{(firmest & (tanks.eligible == 1)).sum():,}')
    print('  firmest tanks failing each rule:')
    for rule, count in failed[firmest].sum().items():
        print(f'    {rule:30s} {count:5,}')


if __name__ == '__main__':
    main()
