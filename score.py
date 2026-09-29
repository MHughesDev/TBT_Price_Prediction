"""Rank the methods by dollars, and say which differences are real.

Reads  results/predictions/*.parquet   (from backtest.py)
Writes results/SCOREBOARD.md

    python score.py                    every method with predictions
    python score.py lgbm ensemble      only these
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from prepare import PRICE

PREDICTIONS = Path('results/predictions')
SCOREBOARD = Path('results/SCOREBOARD.md')
BOOTSTRAP_DRAWS = 2000


def load(names):
    """One frame per method, all restricted to the same tanks so every comparison is paired."""
    runs = {path.stem: pd.read_parquet(path) for path in sorted(PREDICTIONS.glob('*.parquet'))}
    runs = {name: run for name, run in runs.items() if not names or name in names}
    shared = set.intersection(*(set(run['tank_key']) for run in runs.values()))
    for name, run in runs.items():
        run = run[run['tank_key'].isin(shared)].sort_values('tank_key').reset_index(drop=True)
        run['predicted'] = run[[f'predicted_{b}' for b in PRICE]].sum(axis=1)
        run['actual'] = run[[f'actual_{b}' for b in PRICE]].sum(axis=1)
        run['error'] = (run['predicted'] - run['actual']).abs()
        runs[name] = run
    return runs


def standings(runs):
    """One row per method, best first. Numbers are formatted as text for the table."""
    rows = []
    for name, run in runs.items():
        rows.append({
            'method': name,
            'total $ error': run['error'].sum(),
            'mean $ error per tank': money(run['error'].mean()),
            'median $ error per tank': money(run['error'].median()),
            'book bias (predicted - actual)': money(run['predicted'].sum() - run['actual'].sum()),
            'median % error': f"{100 * (run['error'] / run['actual']).median():.1f}%",
        })
    table = pd.DataFrame(rows).sort_values('total $ error').reset_index(drop=True)
    table['total $ error'] = table['total $ error'].map(money)
    return table


def dollars_saved(leader, other):
    """Mean $ per tank that `leader` saves over `other`, with a 95% interval.

    Tanks on one job were priced together, so they are not independent evidence. The
    bootstrap resamples whole jobs, which keeps the interval honest."""
    saved = pd.DataFrame({'job': leader['job_id'], 'saved': other['error'] - leader['error']})
    per_job = saved.groupby('job')['saved'].agg(['sum', 'size'])
    draws = np.random.default_rng(0).integers(0, len(per_job), (BOOTSTRAP_DRAWS, len(per_job)))
    means = per_job['sum'].to_numpy()[draws].sum(axis=1) / per_job['size'].to_numpy()[draws].sum(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return saved['saved'].mean(), low, high


def head_to_head(runs, table):
    leader = table['method'][0]
    rows = []
    for other in table['method'][1:]:
        mean, low, high = dollars_saved(runs[leader], runs[other])
        verdict = (f'{leader} wins' if low > 0 else f'{other} wins' if high < 0
                   else 'no real difference')
        rows.append({'comparison': f'{leader} vs {other}', '$ saved per tank': money(mean),
                     '95% interval': f'{money(low)} to {money(high)}', 'verdict': verdict})
    return pd.DataFrame(rows)


def by_bucket(runs):
    rows = {}
    for name, run in runs.items():
        rows[name] = {bucket: money((run[f'predicted_{bucket}'] - run[f'actual_{bucket}']).abs().sum())
                      for bucket in PRICE}
    return pd.DataFrame(rows).T.rename_axis('method').reset_index()


def money(value):
    return f'-${-value:,.0f}' if value < 0 else f'${value:,.0f}'


def markdown(frame):
    lines = ['| ' + ' | '.join(frame.columns) + ' |', '|' + '---|' * len(frame.columns)]
    for row in frame.itertuples(index=False):
        lines.append('| ' + ' | '.join(str(value) for value in row) + ' |')
    return '\n'.join(lines)


def main(names):
    runs = load(names)
    table = standings(runs)
    first = next(iter(runs.values()))
    text = f"""# Scoreboard

Backtest on {len(first):,} tanks ({first['job_id'].nunique():,} jobs, {money(first['actual'].sum())} of quoted
buckets) due {first['due_date'].min():%Y-%m} to {first['due_date'].max():%Y-%m}. Each method only saw quotes due
before the quarter it was predicting.

**Error = |predicted - actual| of the five bucket prices added up, per tank.** Freight and
tax are known, identical on both sides, and cancel out, so they are left out. The method
with the lowest total $ error leads.

## Standings

{markdown(table)}

## Is the leader's win real?

"$ saved per tank" is how much less error the leader makes on an average tank. The interval
comes from resampling whole jobs {BOOTSTRAP_DRAWS:,} times. A win only counts when the whole
interval is above $0.

{markdown(head_to_head(runs, table))}

## Where the dollars of error are, by bucket

{markdown(by_bucket(runs))}
"""
    SCOREBOARD.write_text(text)
    print(text)


if __name__ == '__main__':
    main(sys.argv[1:])
