"""PHASE 3 - the monthly operations jobs.

Two independent feedback loops, both driven by quotes that have already been priced:

  level adjustment   corrects WHERE the prediction sits   (median log residual, trailing 2 months)
  adaptive conformal corrects HOW WIDE the interval is    (alpha += 0.45 * (0.20 - miscoverage))

Both proved necessary. The 2026 material shock broke the level; the 2025Q4 insulation reprice
broke the interval; neither loop fixes the other's failure.

    python service/ops.py --month 2026-08      # run both jobs for a month, update the bundle
"""
from __future__ import annotations
import sys, pickle, pathlib, argparse, datetime as dt

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'ml'))

import numpy as np
import pandas as pd

ARTIFACTS = HERE / 'artifacts'
LEVEL_WINDOW_MONTHS = 2
LEVEL_MIN_N = 25
ACI_GAMMA = 0.45
ACI_MIN_COHORT = 40
ALPHA_LO, ALPHA_HI = 1e-3, 0.60
DRIFT_ABS = 0.05             # |level adjustment| beyond this raises the alarm
DRIFT_RUN = 3                # ... or this many consecutive months in the same direction


def month_index(ts) -> int:
    ts = pd.Timestamp(ts)
    return (ts.year - 2020) * 12 + ts.month


def update_level(spec, residuals, months, target_month) -> float:
    """Median log residual over quotes priced strictly before `target_month`."""
    w = (months >= target_month - LEVEL_WINDOW_MONTHS) & (months < target_month) & np.isfinite(residuals)
    if w.sum() < LEVEL_MIN_N:
        return float(spec.get('level_adjustment', 0.0))
    return float(np.median(residuals[w]))


def update_alpha(spec, covered: np.ndarray) -> tuple[float, bool]:
    """Adaptive conformal. Buffers until ACI_MIN_COHORT observations - a month of 12 insulation
    quotes has ~11pp standard error on its coverage, and updating off that is updating on noise.
    Returns (alpha, did_update)."""
    cal = spec['calibration']
    buf_c = int(cal.get('buffer_covered', 0)) + int(np.sum(covered))
    buf_n = int(cal.get('buffer_n', 0)) + int(covered.size)
    if buf_n < ACI_MIN_COHORT:
        cal['buffer_covered'], cal['buffer_n'] = buf_c, buf_n
        return float(cal['alpha']), False
    miscov = 1.0 - buf_c / buf_n
    a = float(cal['alpha']) + ACI_GAMMA * (float(cal['alpha_target']) - miscov)
    cal['alpha'] = float(np.clip(a, ALPHA_LO, ALPHA_HI))
    cal['buffer_covered'], cal['buffer_n'] = 0, 0
    return cal['alpha'], True


def check_drift(spec, new_level: float) -> bool:
    hist = list(spec.get('level_history', []))[-(DRIFT_RUN - 1):] + [new_level]
    if abs(new_level) > DRIFT_ABS:
        return True
    if len(hist) >= DRIFT_RUN and (all(h > 0 for h in hist) or all(h < 0 for h in hist)):
        return True
    return False


def run_month(bundle, priced, target_month, verbose=True):
    """`priced` : DataFrame of quotes priced BEFORE target_month, carrying, per bucket,
    the actual price, the model's prediction, and whether the interval covered it."""
    report = []
    for name, spec in bundle['buckets'].items():
        sub = priced[priced.bucket == name]
        if sub.empty:
            continue
        res = sub.log_residual.to_numpy()
        mo = sub.month.to_numpy()
        lvl = update_level(spec, res, mo, target_month)
        prev = float(spec.get('level_adjustment', 0.0))
        spec['level_adjustment'] = lvl
        spec.setdefault('level_history', []).append(lvl)

        # Consume every cohort not yet seen, not just last month. Insulation months are often
        # skipped for low volume, and keying on target_month-1 silently drops those cohorts -
        # which is why the insulation buckets never adapted in the first validation run.
        cal = spec['calibration']
        seen_through = int(cal.get('consumed_through_month', -10**9))
        fresh = sub[(sub.month > seen_through) & (sub.month < target_month)]
        if not fresh.empty:
            alpha, did = update_alpha(spec, fresh.covered.to_numpy().astype(bool))
            cal['consumed_through_month'] = int(fresh.month.max())
        else:
            alpha, did = float(cal['alpha']), False
        alarm = check_drift(spec, lvl)
        spec['drift_alarm'] = bool(alarm)
        report.append(dict(bucket=name, level=lvl, level_delta=lvl - prev,
                           alpha=alpha, alpha_updated=did, drift_alarm=alarm, n=len(sub)))
    if verbose and report:
        print(pd.DataFrame(report).to_string(index=False, float_format=lambda x: f'{x:8.4f}'))
    return bundle, pd.DataFrame(report)


def save(bundle, path=None):
    if path is None:
        latest = (ARTIFACTS / 'latest.txt').read_text(encoding='utf-8').strip()
        path = ARTIFACTS / latest
    import train as T
    return T.save_bundle(bundle, path)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--month', required=True, help='YYYY-MM the jobs are being run for')
    a = ap.parse_args()
    print("ops jobs are exercised end-to-end by service/validate.py; running them against live\n"
          "priced-quote data requires the as-of feed described in docs/HANDOFF_TO_DATA_ENG.md P0-A.")
