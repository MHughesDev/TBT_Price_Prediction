"""Reference implementation of the recommended training recipe.

This is a RESEARCH REPRODUCTION artifact, not the deployable service. It exists so that every
number in docs/ML_SYSTEM_DESIGN.md can be regenerated and so the data layer can see exactly which
columns the models consume.

    python ml/recipe.py              # train + report rolling-origin accuracy and coverage
    python ml/recipe.py --cv         # cross-validated numbers (tuning protocol, optimistic)

Recipe, per bucket:
  offset      log(total_area_sqft) + shrunk LEVEL by regime, via init_score. A level, never a trend.
  objective   L1 on log price (conditional median - matches the MdAPE we report)
  params      Optuna-tuned on this exact recipe, in ml/tuned_params.json
  ensemble    4 seeds, geometric mean
  level adj   monthly: trailing-2-month median log residual of already-priced quotes
  interval    CV+ conformal x shrunk per-grade scale, with ACI alpha control
"""
import sys, os, json, argparse, pathlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import lightgbm as lgb
from sklearn.model_selection import GroupKFold

from data import load, feature_cols, Xy, metrics, TARGETS
from physics import add_physics
from aci import ACI, conformal_q, scaled_mondrian_q

HERE = pathlib.Path(__file__).resolve().parent
TUNED = json.load(open(HERE / 'tuned_params.json'))

TIME_FEATURES = ['t_year', 't_month']

# The dominant multiplicative driver per bucket. This is what the offset absorbs so the tree
# does not have to learn a 3x grade multiplier from 71 rows.
REGIME = {
    'target_material':           ['Material'],
    'target_fabrication':        ['Material'],
    'target_construction':       ['Wage Type'],
    'target_insul_material':     ['Material'],
    'target_insul_construction': None,
}

ALPHA_TARGET = 0.20      # 80% intervals
ACI_GAMMA = 0.45
ACI_MIN_COHORT = 40
LEVEL_ADJ_MONTHS = 2
N_SEEDS = 4


def params_for(target):
    bp = dict(TUNED[target]['params'])
    shrink = bp.pop('offset_shrink')
    bp.update(metric='l1', verbose=-1, bagging_freq=1)
    return bp, shrink


def level_offset(d, target, fit_mask, shrink):
    """log(area) + shrunk level by regime. Returns None when the bucket has no regime.

    NOTE: returning None matters. An all-zero init_score is NOT equivalent to no init_score -
    it disables boost_from_average, and under an L1 objective every split gain is then identical,
    so the model never splits and emits a constant 0.
    """
    regime = REGIME.get(target)
    if not regime:
        return None
    z = np.log(d[target].to_numpy()) - np.log(d.total_area_sqft.clip(lower=1).to_numpy())
    key = d[regime].astype(str).fillna('NA').agg('|'.join, axis=1).to_numpy()
    zf, kf = z[fit_mask], key[fit_mask]
    pooled = float(np.median(zf))
    lev = {}
    for k in np.unique(kf):
        sel = kf == k
        n = int(sel.sum())
        lam = n / (n + shrink)
        lev[k] = lam * float(np.median(zf[sel])) + (1 - lam) * pooled
    return np.log(d.total_area_sqft.clip(lower=1).to_numpy()) + \
        np.array([lev.get(x, pooled) for x in key])


def feature_list(d, target):
    return feature_cols(d) + TIME_FEATURES + [c for c in d.columns if c.startswith('phys_')] + \
        (['gate_insul'] if 'insul' in target else [])


def train_predict(d, target, fit_mask, seeds=range(N_SEEDS)):
    """Fit on fit_mask, return log-space predictions for EVERY row.

    Predictions are produced for all rows because the monthly level adjustment needs the model's
    residuals on quotes that were priced after training.
    """
    bp, shrink = params_for(target)
    X, _ = Xy(d, feature_list(d, target), target)
    y = np.log(d[target].to_numpy())
    off = level_offset(d, target, fit_mask, shrink)
    preds = []
    for s in seeds:
        ds = lgb.Dataset(X[fit_mask], y[fit_mask],
                         init_score=None if off is None else off[fit_mask])
        m = lgb.train(dict(bp, seed=s, bagging_seed=s, feature_fraction_seed=s), ds)
        preds.append(m.predict(X) + (0.0 if off is None else off))
    return np.mean(preds, axis=0)


def oof_residuals(d, target, fit_mask, n_splits=5):
    """Honest residuals inside the training window, grouped by job so a quote never leaks."""
    ly = np.log(d[target].to_numpy())
    res = np.full(len(d), np.nan)
    idx = np.where(fit_mask)[0]
    groups = d._group.to_numpy()[idx]
    for a, b in GroupKFold(n_splits=n_splits).split(idx, groups=groups):
        sub = np.zeros(len(d), bool)
        sub[idx[a]] = True
        res[idx[b]] = ly[idx[b]] - train_predict(d, target, sub, seeds=(0,))[idx[b]]
    return res


def level_adjustment(month, months, residuals, window=LEVEL_ADJ_MONTHS, min_n=25):
    """One scalar: median log residual over quotes priced strictly before `month`."""
    w = (months >= month - window) & (months < month) & np.isfinite(residuals)
    return float(np.median(residuals[w])) if w.sum() >= min_n else 0.0


def evaluate(cv_only=False):
    D = load('training')
    D = pd.concat([D, add_physics(D)], axis=1)
    origins = ['2025Q2', '2025Q3', '2025Q4', '2026Q1', '2026Q2', '2026Q3']
    acc, cov = [], []

    for target in TARGETS:
        d = D[(D[target] > 0) & D['Due Date'].notna()].copy().reset_index(drop=True)
        months = d.t_month.to_numpy()
        ly = np.log(d[target].to_numpy())
        yv = d[target].to_numpy()
        grade = d.Material.astype(str).to_numpy()

        if cv_only:
            X, _ = Xy(d, feature_list(d, target), target)
            oof = np.zeros(len(d))
            for a, b in GroupKFold(n_splits=5).split(X, groups=d._group):
                m = np.zeros(len(d), bool); m[a] = True
                oof[b] = train_predict(d, target, m)[b]
            acc.append(dict(bucket=target.replace('target_', ''), protocol='GroupKFold',
                            **metrics(yv, np.exp(oof))))
            continue

        state = ACI(ALPHA_TARGET, gamma=ACI_GAMMA)
        buf_cov = buf_n = 0
        for origin in origins:
            s0 = pd.Period(origin, 'Q').start_time
            tr = (d['Due Date'] < s0).to_numpy()
            if tr.sum() < 300:
                continue
            pred = train_predict(d, target, tr)
            res = oof_residuals(d, target, tr)
            res[~tr] = ly[~tr] - pred[~tr]          # post-origin rows are truly out-of-sample
            cal = tr & np.isfinite(res)

            in_q = (d['Due Date'] >= s0) & (d['Due Date'] < s0 + pd.DateOffset(months=3))
            for m_i in sorted(np.unique(months[in_q])):
                sel = months == m_i
                if sel.sum() < 12:
                    continue
                lp = pred[sel] + level_adjustment(m_i, months, res)
                q = scaled_mondrian_q(np.abs(res[cal]), grade[cal], grade[sel], state.alpha())
                lo, hi = np.exp(lp - q), np.exp(lp + q)
                covered = (yv[sel] >= lo) & (yv[sel] <= hi)

                acc.append(dict(bucket=target.replace('target_', ''), protocol='rolling',
                                origin=origin, month=int(m_i), **metrics(yv[sel], np.exp(lp))))
                cov.append(dict(bucket=target.replace('target_', ''), n=int(sel.sum()),
                                coverage=float(covered.mean()),
                                width=float(np.median(hi / lo)), alpha=state.alpha()))
                buf_cov += int(covered.sum()); buf_n += int(covered.size)
                if buf_n >= ACI_MIN_COHORT:
                    state.a_t = state.a_t + ACI_GAMMA * (ALPHA_TARGET - (1 - buf_cov / buf_n))
                    state.a_t = float(np.clip(state.a_t, state.lo, state.hi))
                    buf_cov = buf_n = 0

    A = pd.DataFrame(acc)
    if cv_only:
        print(A.to_string(index=False, float_format=lambda x: f'{x:7.4f}'))
        return
    print("=" * 92)
    print("ACCURACY - rolling origin (quote this protocol to the business, not GroupKFold)")
    print("=" * 92)
    g = A.groupby('bucket').apply(
        lambda s: pd.Series(dict(n=s.n.sum(),
                                 MdAPE=np.average(s.MdAPE, weights=s.n),
                                 w10=np.average(s.w10, weights=s.n),
                                 w20=np.average(s.w20, weights=s.n),
                                 bias=np.average(s.bias, weights=s.n))), include_groups=False)
    print(g.to_string(float_format=lambda x: f'{x:7.3f}'))
    C = pd.DataFrame(cov)
    print("\n" + "=" * 92)
    print(f"INTERVALS - target {1-ALPHA_TARGET:.0%}, ACI gamma={ACI_GAMMA}, min cohort {ACI_MIN_COHORT}")
    print("=" * 92)
    print(C.groupby('bucket').apply(
        lambda s: pd.Series(dict(coverage=np.average(s.coverage, weights=s.n),
                                 width=s.width.median(), alpha_final=s.alpha.iloc[-1])),
        include_groups=False).to_string(float_format=lambda x: f'{x:7.3f}'))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--cv', action='store_true', help='cross-validated numbers (optimistic)')
    evaluate(cv_only=ap.parse_args().cv)
