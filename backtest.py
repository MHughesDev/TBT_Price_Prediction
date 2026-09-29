"""Replay history: train on the past, predict the next quarter, compare with what was quoted.

Reads  data/tanks.parquet
Writes results/predictions/<method>.parquet   one row per scored tank, predicted and actual $

    python backtest.py lgbm            one method
    python backtest.py all             every method in methods/__init__.py

Every method sees exactly the same training rows and is scored on exactly the same tanks.
"""
import sys
import time
from pathlib import Path

import pandas as pd

from methods import METHODS
from prepare import OUTPUT as TANKS, PRICE

# Each origin: train on everything due before it, test on the tanks due in the 3 months after.
# The test windows don't overlap, so every tank is scored exactly once.
ORIGINS = ['2025-04-01', '2025-07-01', '2025-10-01', '2026-01-01', '2026-04-01', '2026-07-01']
TEST_MONTHS = 3
RESULTS = Path('results/predictions')


def windows(tanks):
    """Yield (origin, train, test) for each origin."""
    for origin in pd.to_datetime(ORIGINS):
        end = origin + pd.DateOffset(months=TEST_MONTHS)
        train = tanks[tanks['due_date'] < origin]
        test = tanks[(tanks['due_date'] >= origin) & (tanks['due_date'] < end)
                     & (tanks['is_firmest'] == 1)]
        yield origin, train, test


def backtest(method_name, tanks):
    fit_predict = METHODS[method_name]
    scored = []
    for origin, train, test in windows(tanks):
        started = time.time()
        predicted = fit_predict(train, test)
        result = test[['tank_key', 'job_id', 'due_date']].assign(origin=origin)
        for bucket, actual in PRICE.items():
            # Scope is an input the estimator gives us, never a guess: a bucket that is not
            # in scope costs $0, whatever the model says.
            in_scope = test[actual] > 0
            result[f'predicted_{bucket}'] = predicted[bucket].where(in_scope, 0.0)
            result[f'actual_{bucket}'] = test[actual]
        scored.append(result)
        print(f'  {method_name:12s} {origin:%Y-%m}  train {len(train):5,}  test {len(test):4,}'
              f'  {time.time() - started:5.0f}s', flush=True)
    return pd.concat(scored, ignore_index=True)


def main(names):
    if names == ['all']:
        names = list(METHODS)
    tanks = pd.read_parquet(TANKS)
    tanks = tanks[(tanks['eligible'] == 1) & tanks['due_date'].notna()]
    RESULTS.mkdir(parents=True, exist_ok=True)
    for name in names:
        backtest(name, tanks).to_parquet(RESULTS / f'{name}.parquet', index=False)
    print('next: python score.py')


if __name__ == '__main__':
    if len(sys.argv) < 2 or not all(n in METHODS or n == 'all' for n in sys.argv[1:]):
        sys.exit(f'usage: python backtest.py all | {" | ".join(METHODS)}')
    main(sys.argv[1:])
