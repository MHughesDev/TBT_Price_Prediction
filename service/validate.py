"""PHASE 4 - train and validate for real, through the shipped code path.

This is NOT a research script. It builds real bundles with service/train.py, runs the real
service/ops.py jobs month by month, and scores with the real service/predict.py. Anything that
would break in production breaks here.

Protocol: rolling origin on Due Date. Train on everything priced before an origin quarter, then
walk forward month by month, running the ops jobs on quotes that have since been priced.

    python service/validate.py                # full backtest (slow - builds a bundle per origin)
    python service/validate.py --quick        # two origins
"""
from __future__ import annotations
import sys, pickle, pathlib, argparse, warnings
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
from schema import TankRequest
from test_parity import row_to_request
import guards as G

ORIGINS = ['2025Q2', '2025Q3', '2025Q4', '2026Q1', '2026Q2', '2026Q3']
BASE_RATE_BUCKET = 'material'


def build_requests(D):
    """Reconstruct the request an estimator would have sent, INCLUDING the scope gates.

    row_to_request() deliberately omits the gates so the parity test exercises the wage-type
    fallback. Here we supply them, because at serve time the estimator knows the scope and the
    design requires it as an input (§4). Supplying the gate is not leakage - the gate is an
    input, and only the PRICE is predicted.
    """
    reqs, ok = [], []
    for i in range(len(D)):
        try:
            r = row_to_request(D.iloc[i])
            r.erection_in_scope = bool(D['target_construction'].iloc[i] > 0)
            r.insulation_selected = bool(D['target_insul_material'].iloc[i] > 0)
            reqs.append(r)
            ok.append(i)
        except Exception:
            pass
    return reqs, np.array(ok)


def rate_baseline(train_d, test_d, target):
    """The floor every release must beat: median $/sqft x area, fitted on the training window."""
    r = np.median(train_d[target].to_numpy() / train_d.total_area_sqft.clip(lower=1).to_numpy())
    return r * test_d.total_area_sqft.clip(lower=1).to_numpy()


def main(quick=False):
    origins = ORIGINS[-2:] if quick else ORIGINS
    D = T.load_training()
    n0 = len(D)
    D = D[D['Due Date'].notna()].reset_index(drop=True)   # cannot be time-indexed, so cannot be backtested
    if len(D) < n0:
        print(f"dropped {n0 - len(D)} row(s) with no Due Date")
    D['_month'] = ((D['Due Date'].dt.year - 2020) * 12 + D['Due Date'].dt.month).astype(int)
    reqs_all, ok_idx = build_requests(D)
    D = D.iloc[ok_idx].reset_index(drop=True)
    reqs_all = [reqs_all[i] for i in range(len(reqs_all))]
    print(f"{len(D)} rows, {len(reqs_all)} requests reconstructed\n")

    acc, cov, guard_rows = [], [], []
    prev_bundle_path = None
    for origin in origins:
        s0 = pd.Period(origin, 'Q').start_time
        print(f"=== origin {origin}: building bundle as-of {s0.date()} ===", flush=True)
        path = T.build(as_of=s0.date(), note=f'validation origin {origin}',
                       inherit_from=prev_bundle_path)
        prev_bundle_path = path
        bundle = T.load_bundle(path)
        pred = Predictor(bundle)

        tr_mask = (D['Due Date'] < s0).to_numpy()
        test_months = sorted(D.loc[(D['Due Date'] >= s0) &
                                   (D['Due Date'] < s0 + pd.DateOffset(months=9)), '_month'].unique())

        priced = []          # accumulates already-priced quotes for the ops jobs
        for m_i in test_months:
            sel = (D._month == m_i).to_numpy()
            if sel.sum() < 8:
                continue
            # --- run the monthly ops jobs on what has been priced so far
            if priced:
                bundle, _ = OPS.run_month(bundle, pd.concat(priced, ignore_index=True),
                                          m_i, verbose=False)
                OPS.save(bundle, path)     # ops state must persist, or inherit_from re-reads 0.20
                pred = Predictor(bundle)

            idx = np.where(sel)[0]
            batch = [reqs_all[i] for i in idx]
            for bucket, target in T.BUCKET_TARGET.items():
                y = D[target].to_numpy()[idx]
                price, lo, hi, in_scope, lp, expected = pred.predict_many(batch, bucket)
                live = in_scope & (y > 0)
                if live.sum() < 5:
                    continue
                ape = np.abs(price[live] - y[live]) / y[live]
                covered = (y[live] >= lo[live]) & (y[live] <= hi[live])
                acc.append(dict(origin=origin, month=int(m_i), bucket=bucket, n=int(live.sum()),
                                MdAPE=float(np.median(ape)), w10=float((ape <= .1).mean()),
                                w20=float((ape <= .2).mean()),
                                bias=float(np.median(price[live] / y[live]) - 1),
                                wMAPE=float(np.abs(price[live] - y[live]).sum() / y[live].sum()),
                                dollar_err=float(price[live].sum() / y[live].sum() - 1),
                                book_dollar_err=float(expected[live].sum() / y[live].sum() - 1)))
                cov.append(dict(origin=origin, month=int(m_i), bucket=bucket, n=int(live.sum()),
                                coverage=float(covered.mean()),
                                width=float(np.median(hi[live] / lo[live])),
                                alpha=float(bundle['buckets'][bucket]['calibration']['alpha'])))
                priced.append(pd.DataFrame(dict(
                    bucket=bucket, month=int(m_i),
                    log_residual=np.log(y[live]) - lp[live],
                    covered=covered)))

            # guard behaviour on this month's live requests
            for r in batch:
                fl = G.check_request(r)
                guard_rows.append(dict(month=int(m_i), status=G.worst(fl),
                                       n_flags=len(fl)))

        # --- baseline comparison on the first test quarter
        te = ((D['Due Date'] >= s0) & (D['Due Date'] < s0 + pd.DateOffset(months=3))).to_numpy()
        for bucket, target in T.BUCKET_TARGET.items():
            trd = D[tr_mask & (D[target] > 0).to_numpy()]
            ted = D[te & (D[target] > 0).to_numpy()]
            if len(ted) < 20 or len(trd) < 100:
                continue
            bp = rate_baseline(trd, ted, target)
            yv = ted[target].to_numpy()
            ape = np.abs(bp - yv) / yv
            acc.append(dict(origin=origin, month=-1, bucket=bucket + ' [rate baseline]',
                            n=len(ted), MdAPE=float(np.median(ape)),
                            w10=float((ape <= .1).mean()), w20=float((ape <= .2).mean()),
                            bias=float(np.median(bp / yv) - 1),
                            wMAPE=float(np.abs(bp - yv).sum() / yv.sum()),
                            dollar_err=float(bp.sum() / yv.sum() - 1)))

    A = pd.DataFrame(acc); C = pd.DataFrame(cov); Gd = pd.DataFrame(guard_rows)
    A.to_csv(HERE / 'validation_accuracy.csv', index=False)
    C.to_csv(HERE / 'validation_coverage.csv', index=False)

    def wavg(df, col):
        return np.average(df[col], weights=df.n)

    print("\n" + "=" * 92)
    print("ACCURACY - service code path, rolling origin, weighted by tanks")
    print("=" * 92)
    model = A[A.month >= 0]
    base = A[A.month < 0]
    rows = []
    for b in sorted(model.bucket.unique()):
        s = model[model.bucket == b]
        bs = base[base.bucket == b + ' [rate baseline]']
        rows.append(dict(bucket=b, n=int(s.n.sum()), MdAPE=wavg(s, 'MdAPE'),
                         w10=wavg(s, 'w10'), w20=wavg(s, 'w20'), bias=wavg(s, 'bias'),
                         baseline_MdAPE=wavg(bs, 'MdAPE') if len(bs) else np.nan))
    R = pd.DataFrame(rows)
    R['beats_baseline'] = R.MdAPE < R.baseline_MdAPE
    print(R.to_string(index=False, float_format=lambda x: f'{x:8.3f}'))

    # --- DOLLAR-WEIGHTED metrics. The original gate used MdAPE, w10 and coverage, all
    # unweighted, so a systematic miss concentrated in the highest-value 10% of tanks was
    # invisible to it: the service passed while running -8.5% on the book.
    print("\n" + "=" * 92)
    print("DOLLAR-WEIGHTED ACCURACY  (what the book sees, not what a typical quote sees)")
    print("=" * 92)
    drows = []
    for b in sorted(model.bucket.unique()):
        s_ = model[model.bucket == b]
        drows.append(dict(bucket=b, n=int(s_.n.sum()), wMAPE=wavg(s_, 'wMAPE'),
                          quote_dollar=wavg(s_, 'dollar_err'),
                          book_dollar=wavg(s_, 'book_dollar_err')))
    DW = pd.DataFrame(drows)
    print(DW.to_string(index=False, float_format=lambda x: f'{x:8.3f}'))

    print("\n" + "=" * 92)
    print("INTERVALS - target 80%")
    print("=" * 92)
    rows = []
    for b in sorted(C.bucket.unique()):
        s = C[C.bucket == b]
        rows.append(dict(bucket=b, coverage=wavg(s, 'coverage'), width=s.width.median(),
                         alpha_final=s.alpha.iloc[-1],
                         within_3pp=abs(wavg(s, 'coverage') - 0.80) <= 0.03))
    print(pd.DataFrame(rows).to_string(index=False, float_format=lambda x: f'{x:8.3f}'))

    print("\n" + "=" * 92)
    print("GUARDS - share of live requests by status")
    print("=" * 92)
    print((Gd.status.value_counts(normalize=True) * 100).round(1).to_string())

    print("\n" + "=" * 92)
    print("ACCEPTANCE GATE")
    print("=" * 92)
    fails = []
    for _, r in R.iterrows():
        if not (r.MdAPE < r.baseline_MdAPE):
            fails.append(f"{r.bucket}: MdAPE {r.MdAPE:.3f} does not beat rate baseline {r.baseline_MdAPE:.3f}")
    for _, r in pd.DataFrame(rows).iterrows():
        if not r.within_3pp:
            fails.append(f"{r.bucket}: coverage {r.coverage:.3f} is outside 80% +/-3pp")
    # dollar criterion - added because the original gate was blind to it
    # The dollar criterion is evaluated on the BOOK head, because that is the head the design
    # makes responsible for aggregation. The quote head is deliberately a median and is expected
    # to sum low; testing it against a book threshold measures a number nobody uses that way.
    for _, r in DW.iterrows():
        if abs(r.book_dollar) > 0.10:
            fails.append(f"{r.bucket}: BOOK dollar error {r.book_dollar:+.1%} exceeds +/-10%")
    if fails:
        print("FAIL - these buckets ship in fallback mode, not at all:")
        for f in fails:
            print("   -", f)
    else:
        print("PASS - every bucket beats the rate baseline and is calibrated within 3pp")
    return 0 if not fails else 1


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--quick', action='store_true')
    raise SystemExit(main(ap.parse_args().quick))
