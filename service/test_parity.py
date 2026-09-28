"""PHASE 0 EXIT TEST - serving features must match the training pipeline exactly.

Reconstructs a TankRequest from every row of training.parquet, runs it through
service/features.py, and compares each serve-safe feature against the value build/prep.py
produced. A single mismatch fails the build.

This is the only test that can catch train/serve skew before it silently degrades predictions
in production, so it is deliberately unforgiving.

    python service/test_parity.py
"""
from __future__ import annotations
import sys, pathlib
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import numpy as np
import pandas as pd

from schema import TankRequest
from features import build_row, SERVE_SAFE_EXCLUDED

TOL = 1e-9


def row_to_request(r) -> TankRequest:
    """Rebuild the request an estimator would have sent for this archive row.

    Deliberately does NOT pass erection_in_scope / insulation_selected as inputs - it lets the
    wage-type fallback run, which is exactly what prep.py did. That keeps the comparison honest.
    """
    def s(v):
        if v is None or (isinstance(v, float) and v != v):
            return None
        v = str(v)
        return None if v in ('nan', 'None', 'NaT', '') else v

    def f(v):
        if v is None or (isinstance(v, float) and v != v):
            return None
        return float(v)

    return TankRequest(
        diameter_ft=float(r['Diameter (ft)']),
        height_ft=float(r['Height (ft)']),
        material=str(r['Material']),
        use_type=s(r.get('Use Type')) or 'Unknown',
        deck_style=s(r.get('Deck Style')),
        floor_style=s(r.get('Floor Style')),
        freeboard_in=f(r.get('Freeboard (in)')),
        usable_capacity=s(r.get('Usable Capacity')),
        quantity=int(r.get('Quantity') or 1),
        wage_type=s(r.get('Wage Type')),
        # the crosswalk is keyed on the RAW country/state the quote form collects,
        # not on the normalized output
        country=s(r.get('Country')),
        state=s(r.get('State')),
        ss=f(r.get('Ss')), s1=f(r.get('S1')),
        miles_from_tbt=f(r.get('Miles to Site (From TBT)')),
        miles_from_gt=f(r.get('Miles to Site (From GT)')),
        priced_on=pd.Timestamp(r['Due Date']).date(),
    )


def equalish(a, b):
    a_na = a is None or (isinstance(a, float) and np.isnan(a)) or (isinstance(a, str) and a == 'nan')
    b_na = b is None or (isinstance(b, float) and np.isnan(b)) or (isinstance(b, str) and b == 'nan')
    if a_na and b_na:
        return True
    if a_na != b_na:
        return False
    if isinstance(a, (int, float, np.integer, np.floating)) and \
       isinstance(b, (int, float, np.integer, np.floating)):
        a, b = float(a), float(b)
        if a == b:
            return True
        scale = max(abs(a), abs(b), 1.0)
        return abs(a - b) <= 1e-7 * scale
    return str(a) == str(b)


def main():
    D = pd.read_parquet(ROOT / 'exports' / 'training.parquet')
    man = pd.read_csv(ROOT / 'exports' / 'column_manifest.csv')
    pipeline_features = set(man.loc[man.role == 'feature', 'column'])

    # what the serving layer claims to produce, restricted to things the pipeline also has
    sample = build_row(row_to_request(D.iloc[0]))
    serving = set(sample) & set(D.columns)
    checked = sorted((serving & pipeline_features) - set(SERVE_SAFE_EXCLUDED))

    print(f"rows            : {len(D)}")
    print(f"pipeline features: {len(pipeline_features)}")
    print(f"serve-safe checked: {len(checked)}")
    missing = sorted(pipeline_features - serving - set(SERVE_SAFE_EXCLUDED))
    if missing:
        print(f"\nNOT PRODUCED BY THE SERVING LAYER ({len(missing)}):")
        for c in missing:
            print("   ", c)

    bad = {}
    for i in range(len(D)):
        r = D.iloc[i]
        try:
            got = build_row(row_to_request(r))
        except Exception as e:                       # a request we cannot even build is a failure
            bad.setdefault('<request build>', []).append((i, repr(e), ''))
            continue
        for c in checked:
            if not equalish(got.get(c), r.get(c)):
                bad.setdefault(c, []).append((i, got.get(c), r.get(c)))

    print("\n" + "=" * 78)
    if not bad:
        print(f"PARITY PASS - {len(checked)} features match on all {len(D)} rows")
        return 0
    print(f"PARITY FAIL - {len(bad)} column(s) disagree")
    for c, items in sorted(bad.items(), key=lambda kv: -len(kv[1])):
        print(f"\n  {c}: {len(items)} mismatches ({len(items)/len(D):.1%})")
        for i, g, e in items[:3]:
            print(f"      row {i}: serving={g!r}  pipeline={e!r}")
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
