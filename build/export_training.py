"""Leakage-free training exports for modelling, plus a machine-readable column manifest.

Produces, in ../exports/ :

  training.parquet          one row per tank at the firmest revision of its job,
                            DQ-eligible rows only - the filtered default.
                            Leakage columns are PHYSICALLY ABSENT, not just marked.
  training.csv              same content, for tools that prefer text.
  training_full.parquet     SAME grain, UNFILTERED: every row with valid geometry and a
                            positive target, before the DQ eligibility rule, with the
                            geometry-based dq_* flags kept as ordinary columns. Row
                            exclusion is a modelling decision; this export hands it over.
                            training == training_full[training_full.ml_eligible == 1]
  training_full.csv
  revisions.parquet         EVERY priced revision with its Due Date (P1 item 4), for the
                            monthly price-level recalibration feed. Same leakage policy.
  revisions.csv
  column_manifest.csv       role of every column in the source table:
                            feature | target | identifier | leakage | reference
  column_manifest.json      same, plus the leakage reasons and the export contents.

Run from the build/ directory after prep2.py:

    python prep.py && python prep2.py && python export_training.py

WHY LEAKAGE COLUMNS ARE DROPPED RATHER THAN FLAGGED
A flagged column still ends up in a model the first time someone writes
`X = df.drop(columns=[target])`. The only reliable filter is absence, so the modelling
export does not contain them at all. ML_Tank_Training in the workbook keeps them - it is
the research and audit surface - and the manifest records exactly what was removed and why.
"""
import json
import pathlib
import numpy as np
import pandas as pd

OUT = pathlib.Path('../exports')

# --------------------------------------------------------------------- roles
TARGETS = ['target_material', 'target_fabrication', 'target_construction',
           'target_insul_material', 'target_insul_construction']

IDENTIFIERS = ['Tank Key', 'QuoteNumber', 'QuoteGroupID', 'JobKey', 'JobTankKey',
               'Quote-Rev', 'RevisionNumber', 'EffectiveRevision', 'Tank Name',
               'Company Name', 'Customer Name', 'Sales Manager', 'Sales Rep',
               'Project Name', 'Status', 'Outcome', 'Bid Type', 'QuoteVariantType',
               'Due Date', 'City',
               # P1-6 canonicalized names. Encode on the Canonical column, not the raw
               # one: 4 company and 3 customer spellings collapse into it.
               'Company Key', 'Company Canonical', 'Customer Key', 'Customer Canonical']
# 'Name Has Option' and 'Name Partial Scope' are deliberately NOT listed anywhere here, so
# they classify as FEATURES. They are parsed from the tank name the estimator typed, carry
# no price information, and are the only scope signal in the table that is not derived from
# a target - see docs/REPLY_TO_ML_LEAD.md.

# Column -> why it leaks. Every one of these is computed from a target, or is a
# post-pricing accounting figure that is not known when a quote is being priced.
LEAKAGE = {
    'target_bucket_sum': 'sum of the five targets',
    'price_per_gal': 'target / capacity',
    'price_per_shellsqft': 'target / area',
    'material_per_shellsqft': 'target / area',
    'rate_per_shellsqft_dq': 'target / area (data-quality diagnostic)',
    'shell_area_dq': 'only defined alongside the DQ rate; use shell_area_sqft instead',
    'scope_class': 'derived from Construction Price > 1',
    'scope_class_dq': 'derived from Construction Price > 1',
    'price_segment': 'contains scope_class, which is derived from a target',
    'segment_n': 'segment membership derived from scope_class',
    'segment_rank_below': 'rank of this row\'s $/sqft among its segment',
    'segment_pctile': 'percentile of this row\'s $/sqft',
    'dq_price_sane_segment': 'computed from the row\'s own price percentile',
    'price_resid_z': 'studentized residual of log(target_material) on a fitted size/grade/'
                     'scope model - built from a target',
    'dq_price_residual_outlier': 'computed from price_resid_z, which is built from a target',
    'is_insulated': 'derived from the two insulation targets',
    'inc_material': 'derived from Material Price > 1',
    'inc_fabrication': 'derived from Fabrication Price > 1',
    'inc_construction': 'derived from Construction Price > 1',
    'inc_insul_material': 'derived from Insulation Material Price > 1',
    'inc_insul_construction': 'derived from Insulation Construction Price > 1',
    'Proposal Total': 'bucket sum + tax; contains the targets',
    'Total Price': 'bucket sum + freight; contains the targets',
    'Total Tax': 'computed on the priced total',
    'Freight Price': 'priced separately after the buckets; not a quote-time input',
    'Ref Grand Total': 'buckets + freight + tax',
    'First Revision Total': 'a priced total from an earlier revision of the same job',
    'recon_proposal_diff': 'difference of two priced totals',
    'recon_proposal_ok': 'difference of two priced totals',
    'recon_total_diff': 'difference of two priced totals',
    'recon_total_ok': 'difference of two priced totals',
    'is_taxed': 'derived from Total Tax',
    'construction_scope_conflict': 'compares Wage Type against Construction Price > 1',
    'dq_has_positive_target': 'derived from the target sum',
    'dq_price_sane': 'derived from Proposal Total',
    'Material Price': 'raw target column (use target_material)',
    'Fabrication Price': 'raw target column (use target_fabrication)',
    'Construction Price': 'raw target column (use target_construction)',
    'Insulation Material Price': 'raw target column (use target_insul_material)',
    'Insulation Construction Price': 'raw target column (use target_insul_construction)',
    'target_material_per_unit': 'target restated per unit',
    'target_fabrication_per_unit': 'target restated per unit',
    'target_construction_per_unit': 'target restated per unit',
    'target_insul_material_per_unit': 'target restated per unit',
    'target_insul_construction_per_unit': 'target restated per unit',
}

# Kept in the export but not model inputs: audit and grouping aids.
REFERENCE = ['ML Training Row V2', 'ml_eligible', 'ml_training_row', 'IsJobFirmest',
             'JobTankFirstOccurrence', 'JobMaxRevision', 'IsScopeVariant', 'QuoteSuffix',
             'SuffixRevision', 'Max Revision', 'Is Current Revision', 'Revision Count',
             'Won Rows On Quote', 'Lost Rows On Quote', 'Row Outcome', 'Key Dup Index',
             'Geo Match Level', 'dq_geo_resolved', 'dq_has_geometry', 'dq_has_capacity',
             'dq_looks_nontank', 'dq_is_unfinished', 'dq_implausible_geometry',
             'quote_balanced_weight',
             'Country', 'State']

# Free-text note attached to a NON-leakage column in the manifest. The `note` column is
# additive - `column`, `role`, `dtype`, `null_share`, `n_distinct` and `leakage_reason`
# keep their names, meanings and order, so an existing reader is unaffected.
NOTES = {
    'quote_balanced_weight': 'SAMPLE WEIGHT (1 / tanks on the quote-revision). Pass it as '
                             'sample_weight. It must NEVER enter the feature matrix.',
    'dq_implausible_geometry': 'Geometry-only junk flag: Height < 3 ft OR Diameter < 3 ft. '
                               'Price-independent, so it is safe as a feature as well as a '
                               'row filter. Replaces part of the retired P0-4 segment trim.',
    'ml_eligible': 'Row-level DQ verdict. training.parquet keeps ml_eligible == 1; '
                   'training_full.parquet keeps every row at the grain so you can choose.',
}


def classify(col):
    if col in LEAKAGE:
        return 'leakage'
    if col in TARGETS:
        return 'target'
    if col in IDENTIFIERS:
        return 'identifier'
    if col in REFERENCE:
        return 'reference'
    return 'feature'


def build_manifest(df):
    rows = []
    for c in df.columns:
        role = classify(c)
        rows.append({
            'column': c,
            'role': role,
            'dtype': str(df[c].dtype),
            'null_share': round(float(df[c].isna().mean()), 4),
            'n_distinct': int(df[c].nunique(dropna=True)),
            'leakage_reason': LEAKAGE.get(c, ''),
            'note': NOTES.get(c, ''),
        })
    return pd.DataFrame(rows).sort_values(
        ['role', 'column'], key=lambda s: s.map(
            {'target': 0, 'feature': 1, 'identifier': 2, 'reference': 3, 'leakage': 4}
        ) if s.name == 'role' else s)


#: the DQ rules that gate ml_eligible, as (label, column, passing value).
ELIGIBILITY_RULES = [
    ('dq_price_sane == 0', 'dq_price_sane', 1),
    ('dq_implausible_geometry == 1', 'dq_implausible_geometry', 0),
    ('dq_price_residual_outlier == 1', 'dq_price_residual_outlier', 0),
    ('dq_looks_nontank == 1', 'dq_looks_nontank', 0),
    ('dq_is_unfinished == 1', 'dq_is_unfinished', 0),
]


def exclusion_breakdown(d, full_mask):
    """Which flag knocks each training_full row out of training. Reported two ways:
    a per-rule count (a row can fail several rules, so these overlap and do not sum) and
    an 'only reason' count that attributes the row to its single cause."""
    sub = d[full_mask]
    fails = {label: sub[col].ne(ok) for label, col, ok in ELIGIBILITY_RULES}
    n_fail = pd.DataFrame(fails).sum(axis=1)
    out = {label: int(m.sum()) for label, m in fails.items()}
    for label, m in fails.items():
        out[f'only {label}'] = int((m & n_fail.eq(1)).sum())
    out['failed more than one rule'] = int(n_fail.ge(2).sum())
    out['TOTAL excluded'] = int(n_fail.ge(1).sum())
    return out


def write(df, name):
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT / f'{name}.parquet', index=False)
    df.to_csv(OUT / f'{name}.csv', index=False)
    print(f'  {name:12s} {len(df):>6,} rows x {df.shape[1]:>3} cols  -> {name}.parquet / .csv')


def main():
    d = pd.read_pickle('featured3.pkl')
    manifest = build_manifest(d)
    drop = manifest.loc[manifest.role == 'leakage', 'column'].tolist()

    OUT.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(OUT / 'column_manifest.csv', index=False)

    print('roles across the source table:')
    for role, n in manifest.role.value_counts().items():
        print(f'  {role:12s} {n:>4}')

    print('\nexports:')
    train = d[d['ML Training Row V2'] == 1].drop(columns=drop, errors='ignore').reset_index(drop=True)
    write(train, 'training')

    # Row exclusion is a MODELLING decision, not a data-engineering one. training_full is
    # every row at the same firmest-revision grain that has valid geometry and a positive
    # target - i.e. everything BEFORE the DQ eligibility filter - with the geometry-based
    # dq_* flags kept as ordinary columns so the choice is yours. The grain, the targets
    # and the leakage policy are identical to training.parquet; only the row filter differs.
    # Target-derived flags (dq_price_sane, dq_price_sane_segment, dq_price_residual_outlier,
    # price_resid_z, dq_has_positive_target) remain leakage and are still physically absent.
    # `ml_eligible` is present as a reference column and reproduces training.parquet exactly:
    #     training == training_full[training_full.ml_eligible == 1]
    at_grain = (d['IsJobFirmest'] == 1) & (d['JobTankFirstOccurrence'] == 1)
    full_mask = at_grain & (d['dq_has_geometry'] == 1) & (d['dq_has_positive_target'] == 1)
    full = d[full_mask].drop(columns=drop, errors='ignore').reset_index(drop=True)
    write(full, 'training_full')

    excl = exclusion_breakdown(d, full_mask)
    print(f'\n  training_full - training = {len(full) - len(train):,} rows, by excluding flag:')
    for label, n in excl.items():
        print(f'    {label:38s} {n:>5,}')

    # P1 item 4: every PRICED revision, not only the firmest. A revision counts as priced
    # when its buckets sum above zero. Rows the DQ layer rejects as non-tanks, unfinished
    # or geometry-less are still excluded - they are not prices, they are junk.
    rev = d[(d['target_bucket_sum'] > 0) & (d['dq_has_geometry'] == 1) &
            (d['dq_looks_nontank'] == 0) & (d['dq_is_unfinished'] == 0)]
    rev = rev.drop(columns=drop, errors='ignore').reset_index(drop=True)
    write(rev, 'revisions')

    meta = {
        'generated_from': 'featured3.pkl (prep.py -> prep2.py)',
        'source_csv': 'archive.csv  (7,480 rows x 42 columns)',
        'grain': {
            'training': 'one row per tank at the firmest revision of its job, DQ-eligible only',
            'training_full': 'same grain as training, UNFILTERED: every row with valid '
                             'geometry and a positive target, before the DQ eligibility '
                             'rule. Filter it yourself with ml_eligible or the dq_* flags.',
            'revisions': 'one row per tank per PRICED revision, for monthly recalibration',
        },
        'row_counts': {'training': int(len(train)), 'training_full': int(len(full)),
                       'revisions': int(len(rev))},
        'training_full_exclusions': excl,
        'sample_weight': {
            'column': 'quote_balanced_weight',
            'role': 'reference',
            'definition': '1 / tanks on the quote-revision',
            'note': 'Pass it as sample_weight. It must NEVER enter the feature matrix.',
        },
        'eligibility_rule': {
            'definition': 'dq_has_geometry==1 AND dq_has_positive_target==1 AND '
                          'dq_price_sane==1 AND dq_implausible_geometry==0 AND '
                          'dq_price_residual_outlier==0 AND dq_looks_nontank==0 AND '
                          'dq_is_unfinished==0',
            'changed_2026_09_24': 'dq_price_sane_segment RETIRED as a gate (P0-4R). It '
                                  'ranked raw $/shell-sqft inside a Material x scope_class '
                                  'segment with no size term, and $/sqft is U-shaped in '
                                  'size, so it deleted the extremes of the SIZE '
                                  'distribution rather than price outliers. Replaced by '
                                  'dq_implausible_geometry (Height<3ft OR Diameter<3ft) and '
                                  'dq_price_residual_outlier (|studentized residual|>4 from '
                                  'an OLS of log(target_material) on log(area), '
                                  'log(area)^2, log(H), log(D) and dummies for Material, '
                                  'Wage Type and scope, fitted on eligible rows only). '
                                  'The column is still computed and still published in the '
                                  'workbook as research output, and it stays LEAKAGE.',
        },
        'targets': TARGETS,
        'leakage_columns_removed': {c: LEAKAGE[c] for c in drop},
        'reference_notes': NOTES,
        'verified_money_identities': {
            'Proposal Total': 'bucket sum + Total Tax   (carries no freight)',
            'Total Price': 'bucket sum + Freight Price  (carries no tax)',
            'grand total': 'bucket sum + Freight + Tax  (in neither source column)',
            'checked_on': 'all training rows, max relative error 7.1e-07',
        },
        'known_gaps': [
            'WORKBOOK DIVERGENCE (P0-4R). build_core.py still encodes the retired segment '
            'trim in the Excel ML Eligible formula, and dq_price_residual_outlier is a '
            'fitted model that cannot be written as a cell formula. verify.py --diff '
            'therefore reports Excel 4,423 vs pandas 4,459 training rows. These exports are '
            'the modelling surface and are correct; the workbook carries the old rule until '
            'build_core.py is updated. See docs/REPLY_TO_ML_LEAD_2.md section 5.',
            'revisions.parquet is NOT gated on dq_implausible_geometry (or on any price '
            'rule) and still contains 27 rows the geometry flag marks. The flag is in the '
            'export, so filter it there if you want it.',
            'No quote-form input exists for "insulation selected" or "erection in scope". '
            'Insulation Margin (%) is non-zero on 98.1% of uninsulated rows and 98.8% of '
            'insulated rows, so it is not a usable proxy. Product gap - see '
            'docs/OPEN_QUESTIONS_FOR_THE_BUSINESS.md.',
            'Due Date is the only date in the source. There is no quote-created or '
            'quote-sent timestamp per revision.',
            'The quote number encodes YYMM of JOB ORIGINATION, not pricing. Due Date falls '
            'in a later month than the quote number on 38.4% of rows, by up to 85 months. '
            'Do not index time on the quote number.',
            'min_miles was previously MIN(Miles TBT, Miles GT) with a blank read as zero. '
            'Miles GT is a literal 0 on 1,853 source rows and rising (1.4% of 2024 rows, '
            '51.2% of 2026), so 1,192 training rows - 27% - reported a distance of 0 and '
            '1,170 were banded "<100 mi" against a true median of 800 miles. Fixed: the '
            'minimum is taken over the POSITIVE distances and the band is "Unknown" when '
            'neither is available. Re-check any earlier distance or freight analysis.',
            'Name Has Option and Name Partial Scope are parsed from the tank name and are '
            'the only price-independent scope signal available. 162 rows name a roof, deck, '
            'floor or demo/replacement scope, and 16.3% of the P0-4 segment outliers are '
            'among them - an independent confirmation of those rejections.',
        ],
    }
    (OUT / 'column_manifest.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(f'\n  manifest     {len(manifest):>6,} columns  -> column_manifest.csv / .json')
    print(f'  dropped as leakage: {len(drop)} columns')


if __name__ == '__main__':
    main()
