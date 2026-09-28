"""PHASE 1 - build a versioned, immutable prediction bundle.

Nothing is fitted at serve time. A bundle carries everything needed to answer a request:
models, level offsets, conformal calibration and the ACI state, plus the metadata to prove
which data produced it.

    python service/train.py                 # build a bundle from all training rows
    python service/train.py --as-of 2026-01-01   # only quotes priced before this date

Refuses to build if the feature-parity test fails. That test is the only guard against
train/serve skew, so it is a hard gate rather than a suggestion.
"""
from __future__ import annotations
import sys, json, hashlib, pathlib, argparse, datetime as dt

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / 'ml'))

import re
import gzip
import numpy as np
import pandas as pd
import lightgbm as lgb
import xgboost as xgb
from catboost import CatBoostRegressor, Pool
import pickle
from sklearn.model_selection import GroupKFold

from features import SERVE_SAFE_EXCLUDED, model_features
from tank_types import add_tank_type, TANK_TYPES
from physics import add_physics
from aci import ACI

BUCKET_TARGET = {
    'material': 'target_material',
    'fabrication': 'target_fabrication',
    'construction': 'target_construction',
    'insul_material': 'target_insul_material',
    'insul_construction': 'target_insul_construction',
}
# The dominant multiplicative driver the offset absorbs, per bucket (design §6.2).
REGIME = {
    'material': ['Material'], 'fabrication': ['Material'],
    'construction': ['Wage Type'], 'insul_material': ['Material'],
    'insul_construction': None,
}
N_SEEDS = 4
ALPHA_TARGET = 0.20

# --- Value weighting (design R3.2).  w_i = (y_i / median(y)) ** VALUE_ALPHA[bucket]
# alpha=1.0 on the three buckets where the sweep showed it improves MdAPE AND dollar error
# simultaneously; 0.25 where the trade-off is real.
# construction raised 0.25 -> 0.5 because the acceptance gate failed it at -10.1% dollar error.
# The sweep puts alpha=0.5 at dollar -7.8% for MdAPE 0.1146 (vs 0.1109 at 0.25) - a deliberate
# ~3% MdAPE cost to bring the book error inside tolerance.
VALUE_ALPHA = {'material': 1.0, 'fabrication': 0.25, 'construction': 0.5,
               'insul_material': 1.0, 'insul_construction': 1.0}
# --- Non-firmest revisions, included at reduced weight (design §3 correction).
USE_REVISIONS = True
REVISION_WEIGHT = 0.5

# --- Dual head (design R3.8).
# quote head : L1 on log price  -> conditional MEDIAN. The anchor for pricing ONE tank.
# book  head : gamma on raw $   -> conditional MEAN, no back-transform bias. What a SUM needs.
# One model cannot serve both: the median is right per tank and systematically low in aggregate.
# Measured on total price: book error -6.79% (quote head) vs -4.04% (book head).
BUILD_BOOK_HEAD = True

# --- Multi-family ensemble (design R3.11). LightGBM + XGBoost + CatBoost, averaged in log space.
# Wins or ties on all five buckets; largest gains where the model is weakest
# (insul_construction -9.5%, insul_material -7.4%). It worsens the quote head's dollar error,
# which used to be an objection - the gamma book head now owns aggregation, so the quote head
# is free to optimise per-tank accuracy alone.
USE_ENSEMBLE = True

# Architectures. 'pooled' is production; the others are kept so the comparison in
# docs/TANK_TYPE_COMPARISON.md can be re-run when more data arrives.
ARCHITECTURES = ('pooled', 'tank_type_feature', 'per_type', 'hybrid')
SEGMENT_MIN_N = 150      # a segment below this falls back to the pooled model
BLEND_K = 400            # hybrid weight on the segment model: n / (n + K)
ARTIFACTS = HERE / 'artifacts'


# --------------------------------------------------------------------------- data
def load_training(as_of=None) -> pd.DataFrame:
    D = pd.read_parquet(ROOT / 'exports' / 'training.parquet').copy()
    for t in BUCKET_TARGET.values():
        D[t] = np.where(D[t] <= 1, 0.0, D[t])        # $0.01 sentinels mean "scoped, not priced"
    D['Due Date'] = pd.to_datetime(D['Due Date'])
    D['_group'] = D['QuoteGroupID'].astype(str)
    D['t_year'] = D['Due Date'].dt.year.astype(float)
    D['t_month'] = ((D['Due Date'].dt.year - 2020) * 12 + D['Due Date'].dt.month).astype(float)
    D['gate_insul'] = (D.target_insul_material > 0).astype(int)
    D = pd.concat([D, add_physics(D)], axis=1)
    D = add_tank_type(D)
    if as_of is not None:
        D = D[D['Due Date'] < pd.Timestamp(as_of)]
    return D.reset_index(drop=True)


def load_revisions(as_of=None) -> pd.DataFrame:
    """Non-firmest priced revisions, for inclusion at reduced weight.

    MUST filter on ml_eligible. Without it the feed carries 11 corrupt rows including a
    $1,189,189,238,895 material price; under value weighting that single row would receive
    ~15,000,000x the weight of a median row. The flag exists precisely for this.
    """
    RV = pd.read_parquet(ROOT / 'exports' / 'revisions.parquet').copy()
    for t in BUCKET_TARGET.values():
        RV[t] = np.where(RV[t] <= 1, 0.0, RV[t])
    RV['Due Date'] = pd.to_datetime(RV['Due Date'])
    RV = RV[RV['Due Date'].notna()]
    n0 = len(RV)
    RV = RV[RV['ml_eligible'] == 1].copy()
    if len(RV) == n0:
        raise SystemExit("REFUSING TO BUILD - revisions feed has no ineligible rows to drop, "
                         "which means ml_eligible is missing or already applied upstream. "
                         "Verify before proceeding.")
    RV['_group'] = RV['QuoteGroupID'].astype(str)
    RV['t_year'] = RV['Due Date'].dt.year.astype(float)
    RV['t_month'] = ((RV['Due Date'].dt.year - 2020) * 12 + RV['Due Date'].dt.month).astype(float)
    RV['gate_insul'] = (RV.target_insul_material > 0).astype(int)
    RV = pd.concat([RV, add_physics(RV)], axis=1)
    RV = add_tank_type(RV).reset_index(drop=True)
    if as_of is not None:
        RV = RV[RV['Due Date'] < pd.Timestamp(as_of)]
    return RV


def value_weights(y, alpha, base=None):
    """Sample weight proportional to price^alpha. See the eligibility warning in
    load_revisions(): value weighting makes a single corrupt row catastrophic."""
    y = np.asarray(y, float)
    w = np.ones(len(y)) if alpha == 0 else (y / np.median(y)) ** alpha
    w = w / w.mean()
    return w if base is None else w * base


def manifest_features() -> list:
    m = pd.read_csv(ROOT / 'exports' / 'column_manifest.csv')
    return m.loc[m.role == 'feature', 'column'].tolist()


def frame_for(D, bucket, feats):
    X = D[[c for c in feats if c in D.columns]].copy()
    for c in X.columns:
        if X[c].dtype == object or str(X[c].dtype) in ('str', 'string'):
            X[c] = X[c].astype('category')
        elif str(X[c].dtype) == 'boolean':
            X[c] = X[c].astype(float)
    return X


# --------------------------------------------------------------------------- offset
def fit_offset(d, target, regime, shrink):
    """Shrunk LEVEL by regime. A level, never a trend - a time term here extrapolates past the
    fitted range at serve time and diverges (design §6.2)."""
    if not regime:
        return None
    z = np.log(d[target].to_numpy()) - np.log(d.total_area_sqft.clip(lower=1).to_numpy())
    key = d[regime].astype(str).fillna('NA').agg('|'.join, axis=1).to_numpy()
    pooled = float(np.median(z))
    levels = {}
    for k in np.unique(key):
        sel = key == k
        n = int(sel.sum())
        lam = n / (n + shrink)
        levels[k] = lam * float(np.median(z[sel])) + (1 - lam) * pooled
    return dict(regime=list(regime), pooled=pooled, levels=levels, shrink=float(shrink))


def apply_offset(off, frame):
    if off is None:
        return None
    key = frame[off['regime']].astype(str).fillna('NA').agg('|'.join, axis=1).to_numpy()
    lv = np.array([off['levels'].get(k, off['pooled']) for k in key])
    return np.log(frame.total_area_sqft.clip(lower=1).to_numpy()) + lv


# --------------------------------------------------------------------------- models
def fit_models(X, y, params, offset, seeds=range(N_SEEDS), weight=None):
    models = []
    for s in seeds:
        ds = lgb.Dataset(X, y, weight=weight, init_score=None if offset is None else offset)
        m = lgb.train(dict(params, seed=s, bagging_seed=s, feature_fraction_seed=s), ds)
        # Guard: an all-zero init_score, or L1 with no differential split gain, yields a model
        # with no trees that silently predicts a constant. This has bitten this project twice.
        if m.num_trees() == 0:
            raise RuntimeError("model trained 0 trees - check init_score handling")
        models.append(m)
    return models


def save_bundle(bundle, path):
    """Bundles are gzipped: they carry three model families x five buckets."""
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'wb') as f:
        pickle.dump(bundle, f)
    return path


def load_bundle(path):
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rb') as f:
        return pickle.load(f)


def _dense(X, cols=None):
    """One-hot copy for XGBoost, with names it will accept."""
    Xd = pd.get_dummies(X, dummy_na=True).astype(float).fillna(0)
    Xd.columns = [re.sub(r'[^0-9a-zA-Z_]+', '_', str(c)) for c in Xd.columns]
    Xd = Xd.loc[:, ~Xd.columns.duplicated()]
    return Xd if cols is None else Xd.reindex(columns=cols, fill_value=0.0)


def fit_ensemble(X, y, offset, weight):
    """XGBoost + CatBoost on the same target, to average with LightGBM in log space."""
    tgt = y if offset is None else y - offset
    Xd = _dense(X)
    xm = xgb.XGBRegressor(n_estimators=600, learning_rate=0.05, max_depth=6, subsample=0.8,
                          colsample_bytree=0.8, reg_lambda=1.0, tree_method='hist',
                          objective='reg:absoluteerror', verbosity=0, random_state=0)
    xm.fit(Xd, tgt, sample_weight=weight)
    cats = [c for c in X.columns if str(X[c].dtype) == 'category']
    C = X.copy()
    for c in cats:
        C[c] = C[c].astype(str).fillna('NA')
    cb = CatBoostRegressor(iterations=800, learning_rate=0.05, depth=7, loss_function='MAE',
                           random_seed=0, verbose=0, allow_writing_files=False)
    cb.fit(Pool(C, tgt, weight=weight, cat_features=cats))
    return dict(xgb=xm.get_booster().save_raw('json'), cat=cb, xgb_cols=list(Xd.columns),
                cat_features=cats)


def predict_models(models, X, offset):
    p = np.mean([m.predict(X) for m in models], axis=0)
    return p if offset is None else p + offset


def training_set(D, RV, bucket, target):
    """Firmest rows for this bucket, plus non-firmest revisions at reduced weight, plus the
    per-bucket value weights. Returns (frame, sample_weight)."""
    d = D[D[target] > 0].reset_index(drop=True)
    base = None
    if USE_REVISIONS and RV is not None:
        firm = set(D['Tank Key'].astype(str))
        extra = RV[(~RV['Tank Key'].astype(str).isin(firm)) & (RV[target] > 0)]
        if len(extra) > 50:
            cols = d.columns.intersection(extra.columns)
            d2 = pd.concat([d[cols], extra[cols]], ignore_index=True)
            base = np.concatenate([np.ones(len(d)), np.full(len(extra), REVISION_WEIGHT)])
            d = d2
    w = value_weights(d[target].to_numpy(), VALUE_ALPHA.get(bucket, 0.0), base)
    # Guard: value weighting turns one corrupt row into a catastrophe. Refuse absurd weights.
    if np.max(w) / np.median(w) > 5000:
        raise RuntimeError(f"{bucket}: max/median sample weight = {np.max(w)/np.median(w):,.0f}; "
                           f"a corrupt row is almost certainly present in the feed")
    return d, w


# --------------------------------------------------------------------------- calibration
def cv_residuals(D, RV, bucket, feats, params, regime, shrink, n_splits=5):
    """Out-of-fold residuals, grouped by job, using the SAME recipe the deployed model uses.
    In-sample residuals collapse coverage (design §8). Residuals are reported on firmest rows
    only, because that is the population the service is scored on."""
    target = BUCKET_TARGET[bucket]
    d, w = training_set(D, RV, bucket, target)
    X = frame_for(d, bucket, feats)
    y = np.log(d[target].to_numpy())
    res = np.full(len(d), np.nan)
    for a, b in GroupKFold(n_splits=n_splits).split(X, groups=d._group):
        off_tr = fit_offset(d.iloc[a], target, regime, shrink)
        otr = apply_offset(off_tr, d.iloc[a])
        ms = fit_models(X.iloc[a], y[a], params, otr, seeds=(0,), weight=w[a])
        ote = apply_offset(off_tr, d.iloc[b])
        res[b] = y[b] - predict_models(ms, X.iloc[b], ote)
    firm = d['Tank Key'].astype(str).isin(set(D['Tank Key'].astype(str))).to_numpy()
    return d[firm].reset_index(drop=True), res[firm]


def grade_scales(scores, grades, shrink=40.0, min_n=12):
    med_all = float(np.median(scores)) or 1e-6
    out = {}
    for g in np.unique(grades):
        sel = grades == g
        n = int(sel.sum())
        if n < min_n:
            out[g] = 1.0
            continue
        lam = n / (n + shrink)
        out[g] = lam * (float(np.median(scores[sel])) / med_all) + (1 - lam) * 1.0
    return out


# --------------------------------------------------------------------------- bundle
def build(as_of=None, note='', inherit_from=None, arch='pooled', promote=True):
    """inherit_from: a previous bundle whose LEARNED CALIBRATION STATE should carry forward.

    Retraining refits the models, but the ACI alpha and the level history were learned from
    realised coverage on priced quotes and are independent of the model fit. Discarding them on
    every retrain resets adaptation to zero - which is exactly why the insulation buckets never
    converged in the first validation run (alpha stuck at its 0.20 initial value).
    """
    import subprocess
    print("gate: feature parity ...", flush=True)
    rc = subprocess.run([sys.executable, str(HERE / 'test_parity.py')],
                        capture_output=True, text=True)
    if rc.returncode != 0:
        print(rc.stdout[-2000:])
        raise SystemExit("REFUSING TO BUILD - feature parity failed. Fix service/features.py.")
    print("      parity OK\n", flush=True)

    if arch not in ARCHITECTURES:
        raise SystemExit(f"arch must be one of {ARCHITECTURES}")
    D = load_training(as_of)
    RV = load_revisions(as_of) if USE_REVISIONS else None
    if RV is not None:
        print(f"revisions feed: {len(RV)} eligible rows\n", flush=True)
    tuned = json.load(open(ROOT / 'ml' / 'tuned_params.json'))
    man = manifest_features()
    bundle = dict(buckets={}, meta={})
    print(f"architecture: {arch}\n", flush=True)

    for bucket, target in BUCKET_TARGET.items():
        feats = model_features(man, has_insul_gate='insul' in bucket,
                               with_tank_type=(arch != 'pooled'))
        bp = dict(tuned[target]['params'])
        shrink = bp.pop('offset_shrink')
        bp.update(metric='l1', verbose=-1, bagging_freq=1)
        regime = REGIME[bucket]

        d, w = training_set(D, RV, bucket, target)
        X = frame_for(d, bucket, feats)
        y = np.log(d[target].to_numpy())
        off_spec = fit_offset(d, target, regime, shrink)
        off = apply_offset(off_spec, d)
        models = fit_models(X, y, bp, off, weight=w)

        book_models = []
        if BUILD_BOOK_HEAD:
            gp = {k: v for k, v in bp.items() if k != 'metric'}
            gp.update(objective='gamma', verbose=-1)
            # gamma has a log link of its own, so no init_score offset here
            book_models = fit_models(X, d[target].to_numpy(), gp, None, weight=w)

        ens = fit_ensemble(X, y, off, w) if USE_ENSEMBLE else None

        dres, res = cv_residuals(D, RV, bucket, feats, bp, regime, shrink)
        ok = np.isfinite(res)
        grades = dres.Material.astype(str).to_numpy()
        ape = np.abs(np.expm1(np.abs(res[ok]))) if False else np.abs(np.exp(res[ok]) - 1)

        bundle['buckets'][bucket] = dict(
            target=target,
            features=[c for c in feats if c in X.columns],
            categorical=[c for c in X.columns if str(X[c].dtype) == 'category'],
            categories={c: list(X[c].cat.categories) for c in X.columns
                        if str(X[c].dtype) == 'category'},
            params=bp, offset=off_spec, models=[m.model_to_string() for m in models],
            book_models=[m.model_to_string() for m in book_models],
            ensemble=ens,
            calibration=dict(
                scores=np.abs(res[ok]).astype(float),
                grades=grades[ok],
                grade_scales=grade_scales(np.abs(res[ok]), grades[ok]),
                alpha=ALPHA_TARGET, alpha_target=ALPHA_TARGET,
                n=int(ok.sum())),
            segments={},                   # populated for per_type / hybrid
            level_adjustment=0.0,          # set by the monthly ops job, not at train time
            train_rows=int(len(d)),
            cv_MdAPE=float(np.median(ape)),
            cv_w10=float((ape <= 0.10).mean()),
        )
        if arch in ('per_type', 'hybrid'):
            segs = {}
            for tt in sorted(d.tank_type.unique()):
                sub = d[d.tank_type == tt]
                if len(sub) < SEGMENT_MIN_N:
                    continue                      # too thin: this segment uses the pooled model
                so = fit_offset(sub, target, regime, shrink)
                sm = fit_models(frame_for(sub, bucket, feats), np.log(sub[target].to_numpy()),
                                bp, apply_offset(so, sub))
                segs[tt] = dict(models=[m.model_to_string() for m in sm], offset=so,
                                n=int(len(sub)),
                                blend_w=(len(sub) / (len(sub) + BLEND_K)) if arch == 'hybrid' else 1.0)
            bundle['buckets'][bucket]['segments'] = segs
            covered = d.tank_type.isin(segs).mean()
            print(f"  {bucket:20s} n={len(d):5d}  CV MdAPE={np.median(ape):.4f} "
                  f"w10={(ape<=0.10).mean():.3f}  segments={len(segs)} "
                  f"covering {covered:.0%} of rows", flush=True)
        else:
            print(f"  {bucket:20s} n={len(d):5d}  CV MdAPE={np.median(ape):.4f} "
                  f"w10={(ape<=0.10).mean():.3f}", flush=True)

    # carry forward learned calibration state across the retrain
    if inherit_from is not None:
        prev = load_bundle(inherit_from)
        for name, spec in bundle['buckets'].items():
            ps = prev['buckets'].get(name)
            if not ps:
                continue
            spec['calibration']['alpha'] = float(ps['calibration'].get('alpha', ALPHA_TARGET))
            spec['calibration']['buffer_covered'] = int(ps['calibration'].get('buffer_covered', 0))
            spec['calibration']['buffer_n'] = int(ps['calibration'].get('buffer_n', 0))
            if 'consumed_through_month' in ps['calibration']:
                spec['calibration']['consumed_through_month'] = int(
                    ps['calibration']['consumed_through_month'])
            spec['level_history'] = list(ps.get('level_history', []))
            spec['level_adjustment'] = float(ps.get('level_adjustment', 0.0))
        print(f"  inherited calibration state from {pathlib.Path(inherit_from).name}")

    src = (HERE / 'features.py').read_bytes() + (HERE / 'train.py').read_bytes()
    fingerprint = hashlib.sha256(
        src + str(sorted(D['Tank Key'].astype(str))).encode()).hexdigest()[:12]
    bundle['meta'] = dict(
        version=f"{dt.datetime.now():%Y%m%d-%H%M}-{fingerprint}",
        built_at=dt.datetime.now().isoformat(timespec='seconds'),
        as_of=str(as_of) if as_of else None,
        train_rows=int(len(D)),
        date_min=str(D['Due Date'].min().date()), date_max=str(D['Due Date'].max().date()),
        alpha_target=ALPHA_TARGET, n_seeds=N_SEEDS, architecture=arch,
        value_alpha=dict(VALUE_ALPHA), use_revisions=USE_REVISIONS,
        revision_weight=REVISION_WEIGHT, book_head=BUILD_BOOK_HEAD,
        ensemble=USE_ENSEMBLE,
        segment_min_n=SEGMENT_MIN_N, blend_k=BLEND_K,
        serve_safe_excluded=list(SERVE_SAFE_EXCLUDED),
        note=note,
    )
    out_dir = ARTIFACTS if promote else ARTIFACTS / 'validation'
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"bundle-{arch}-{bundle['meta']['version']}.pkl.gz"
    save_bundle(bundle, path)
    # Only an explicit production build moves the pointer. Backtests must never promote, or a
    # predict call silently serves a stale as-of model.
    if promote:
        (ARTIFACTS / 'latest.txt').write_text(path.name, encoding='utf-8')
    print(f"\nbundle: {path.name}  ({path.stat().st_size/1e6:.1f} MB)")
    return path


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--as-of', default=None, help='train only on quotes priced before this date')
    ap.add_argument('--note', default='')
    ap.add_argument('--arch', default='pooled', choices=list(ARCHITECTURES))
    ap.add_argument('--no-promote', action='store_true',
                    help='write the bundle but do not update latest.txt')
    a = ap.parse_args()
    build(a.as_of, a.note, arch=a.arch, promote=not a.no_promote)
