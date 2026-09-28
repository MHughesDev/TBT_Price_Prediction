"""Business-level validation: the expected TOTAL PRICE of a quote.

The service predicts five buckets. The estimating software adds freight and tax, which are
deterministic and known per row. So the number that matters to the business is:

    predicted_total = sum(5 predicted buckets) + actual freight + actual tax
    actual_total    = sum(5 actual buckets)    + actual freight + actual tax

Freight and tax are taken from the row being compared against - they are inputs, not predictions,
so they appear identically on both sides and simply dampen the percentage error, which is the
honest representation of what an estimator sees.

Reported per TANK and per JOB (a quote can hold up to 29 tanks and is priced as one document).

MPE is a SIGNED mean - it measures systematic over/under-pricing and offsetting errors cancel.
MAPE/MdAPE are reported alongside so a small MPE cannot be mistaken for a small error.

    python service/validate_total.py
"""
from __future__ import annotations
import sys, pickle, pathlib, warnings, argparse
warnings.filterwarnings('ignore')

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'ml'))

import numpy as np
import pandas as pd

import train as T
import ops as OPS
from predict import Predictor
from validate import build_requests, ORIGINS

# Duan smearing factor measured on this data (design §3). exp(mean log) under-states the MEAN,
# so a sum of medians under-states a book of quotes.
SMEARING = 1.0338


def load_freight_tax():
    F = pd.read_pickle(ROOT / 'build' / 'featured3.pkl')
    F = F[['Tank Key', 'Freight Price', 'Total Tax']].drop_duplicates('Tank Key')
    return F


def main(quick=False):
    origins = ORIGINS[-2:] if quick else ORIGINS
    D = T.load_training()
    D = D[D['Due Date'].notna()].reset_index(drop=True)
    D['_month'] = ((D['Due Date'].dt.year - 2020) * 12 + D['Due Date'].dt.month).astype(int)

    ft = load_freight_tax()
    D = D.merge(ft, on='Tank Key', how='left')
    D['Freight Price'] = D['Freight Price'].fillna(0.0)
    D['Total Tax'] = D['Total Tax'].fillna(0.0)

    reqs_all, ok_idx = build_requests(D)
    D = D.iloc[ok_idx].reset_index(drop=True)
    print(f"{len(D)} tanks, {D._group.nunique()} jobs\n")

    rows = []
    prev_path = None
    for origin in origins:
        s0 = pd.Period(origin, 'Q').start_time
        print(f"=== origin {origin} ===", flush=True)
        path = T.build(as_of=s0.date(), note=f'total-price validation {origin}',
                       inherit_from=prev_path, promote=False)
        prev_path = path
        bundle = T.load_bundle(path)
        pred = Predictor(bundle)

        test_months = sorted(D.loc[(D['Due Date'] >= s0) &
                                   (D['Due Date'] < s0 + pd.DateOffset(months=3)), '_month'].unique())
        priced = []
        for m_i in test_months:
            sel = (D._month == m_i).to_numpy()
            if sel.sum() < 8:
                continue
            if priced:
                bundle, _ = OPS.run_month(bundle, pd.concat(priced, ignore_index=True),
                                          m_i, verbose=False)
                OPS.save(bundle, path)
                pred = Predictor(bundle)

            idx = np.where(sel)[0]
            batch = [reqs_all[i] for i in idx]
            sub = D.iloc[idx]

            pred_sum = np.zeros(len(idx))
            book_sum = np.zeros(len(idx))
            act_sum = np.zeros(len(idx))
            for bucket, target in T.BUCKET_TARGET.items():
                y = D[target].to_numpy()[idx]
                price, lo, hi, in_scope, lp, expected = pred.predict_many(batch, bucket)
                # out of scope -> the service returns a hard zero, and so does the archive
                pred_sum += np.where(in_scope, price, 0.0)
                book_sum += np.where(in_scope, expected, 0.0)
                act_sum += y
                live = in_scope & (y > 0)
                if live.sum() >= 5:
                    covered = (y[live] >= lo[live]) & (y[live] <= hi[live])
                    priced.append(pd.DataFrame(dict(
                        bucket=bucket, month=int(m_i),
                        log_residual=np.log(y[live]) - lp[live], covered=covered)))

            rows.append(pd.DataFrame(dict(
                origin=origin, month=int(m_i),
                job=sub._group.to_numpy(), tank=sub['Tank Key'].to_numpy(),
                pred_buckets=pred_sum, book_buckets=book_sum, act_buckets=act_sum,
                freight=sub['Freight Price'].to_numpy(), tax=sub['Total Tax'].to_numpy())))

    R = pd.concat(rows, ignore_index=True)
    R['pred_total'] = R.pred_buckets + R.freight + R.tax
    R['act_total'] = R.act_buckets + R.freight + R.tax
    # the real book head, not the smearing approximation it replaced
    R['book_total'] = R.book_buckets + R.freight + R.tax
    R['pred_total_smeared'] = R.pred_buckets * SMEARING + R.freight + R.tax
    R = R[R.act_total > 0].reset_index(drop=True)
    R.to_csv(HERE / 'validation_total.csv', index=False)

    def report(label, pred, act, n_units):
        err = (pred - act) / act
        ape = np.abs(err)
        print(f"\n  {label}  (n={n_units})")
        print(f"    MPE   (signed, systematic) : {err.mean()*100:+7.2f}%")
        print(f"    MdPE  (signed, median)     : {np.median(err)*100:+7.2f}%")
        print(f"    MAPE  (absolute)           : {ape.mean()*100:7.2f}%")
        print(f"    MdAPE (absolute, median)   : {np.median(ape)*100:7.2f}%")
        print(f"    within +/-10%              : {(ape<=.10).mean()*100:7.1f}%")
        print(f"    within +/-20%              : {(ape<=.20).mean()*100:7.1f}%")
        print(f"    total $ predicted vs actual: "
              f"${pred.sum()/1e6:,.1f}M vs ${act.sum()/1e6:,.1f}M "
              f"({(pred.sum()/act.sum()-1)*100:+.2f}%)")

    print("\n" + "=" * 86)
    print("EXPECTED TOTAL PRICE  =  predicted 5 buckets + actual freight + actual tax")
    print("=" * 86)

    print("\n--- PER TANK ---")
    report("median output (what the service returns today)",
           R.pred_total.to_numpy(), R.act_total.to_numpy(), len(R))
    report("BOOK HEAD (gamma) - aggregate with this",
           R.book_total.to_numpy(), R.act_total.to_numpy(), len(R))

    J = R.groupby(['origin', 'job'], as_index=False).agg(
        pred_total=('pred_total', 'sum'), act_total=('act_total', 'sum'),
        book_total=('book_total', 'sum'), tanks=('tank', 'size'))
    print("\n--- PER JOB (a quote, summed over its tanks) ---")
    report("median output", J.pred_total.to_numpy(), J.act_total.to_numpy(), len(J))
    report("BOOK HEAD (gamma)", J.book_total.to_numpy(), J.act_total.to_numpy(), len(J))

    print("\n" + "=" * 86)
    print("CONTEXT")
    print("=" * 86)
    share = (R.freight + R.tax).sum() / R.act_total.sum()
    print(f"  freight + tax are {share*100:.1f}% of the total book, and are supplied exactly,")
    print(f"  so the percentage error on a TOTAL is smaller than on the predicted buckets alone.")
    bo = (R.pred_buckets - R.act_buckets) / R.act_buckets
    print(f"  buckets-only MPE {bo.mean()*100:+.2f}%   MdAPE {np.median(np.abs(bo))*100:.2f}%")
    print(f"\n  multi-tank jobs: {(J.tanks>1).mean()*100:.1f}% of jobs, {J.loc[J.tanks>1,'tanks'].sum()} tanks")
    return R, J


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true')
    main(ap.parse_args().quick)
