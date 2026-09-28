"""PHASE 2 - serving. Load a bundle, answer a request.

Nothing is fitted here. The bundle carries models, level offsets, the monthly level adjustment
and the conformal calibration; this module only applies them.

    from service.predict import Predictor
    p = Predictor.load()
    resp = p.predict(TankRequest(...))
"""
from __future__ import annotations
import sys, pickle, pathlib
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

from schema import TankRequest, PredictionResponse, BucketPrediction, BUCKETS
from features import build_frame
import guards as G
from aci import conformal_q

ARTIFACTS = HERE / 'artifacts'

# Which buckets a tank is in scope for, given its gates.
def buckets_in_scope(req: TankRequest) -> dict:
    erection, esrc = req.erection_scope()
    insul, isrc = req.insulation_scope()
    return {
        'material': True,
        'fabrication': True,
        'construction': erection,
        'insul_material': insul,
        'insul_construction': insul,
    }, {'erection': esrc, 'insulation': isrc}


class Predictor:
    def __init__(self, bundle: dict):
        self.b = bundle
        self._models, self._book, self._ens = {}, {}, {}
        for name, spec in bundle['buckets'].items():
            self._models[name] = [lgb.Booster(model_str=s) for s in spec['models']]
            self._book[name] = [lgb.Booster(model_str=s) for s in spec.get('book_models', [])]
            e = spec.get('ensemble')
            if e:
                bst = xgb.Booster()
                bst.load_model(bytearray(e['xgb']))
                self._ens[name] = dict(xgb=bst, cat=e['cat'], xgb_cols=e['xgb_cols'],
                                       cat_features=e['cat_features'])

    @classmethod
    def load(cls, path=None):
        if path is None:
            latest = (ARTIFACTS / 'latest.txt').read_text(encoding='utf-8').strip()
            path = ARTIFACTS / latest
        opener = gzip.open if str(path).endswith('.gz') else open
        with opener(path, 'rb') as f:
            return cls(pickle.load(f))   # gzip or raw, both supported

    # ------------------------------------------------------------------ internals
    def _frame(self, req, spec):
        """Build the model frame and report any category the model never saw in training.

        An unseen level is not an error - LightGBM treats it as missing - but it does mean the
        model is pricing this tank without that signal, so the caller surfaces it.
        """
        X = build_frame([req])
        cols = spec['features']
        for c in cols:
            if c not in X.columns:
                X[c] = np.nan
        X = X[cols].copy()
        unseen = []
        for c, cats in spec['categories'].items():
            raw = X[c].iloc[0]
            val = None if raw is None or (isinstance(raw, float) and raw != raw) else str(raw)
            if val is not None and val not in cats:
                unseen.append((c, val))
                val = None                      # unseen level -> missing, never a silent coercion
            X[c] = pd.Categorical([val], categories=cats)
        for c in X.columns:
            if c not in spec['categories'] and str(X[c].dtype) not in ('float64', 'int64'):
                X[c] = pd.to_numeric(X[c], errors='coerce')
        return X, unseen

    def _ensemble_logp(self, name, X, off_add):
        """XGBoost + CatBoost log predictions, to average with LightGBM."""
        e = self._ens.get(name)
        if not e:
            return []
        out = []
        Xd = pd.get_dummies(X, dummy_na=True).astype(float).fillna(0)
        Xd.columns = [re.sub(r'[^0-9a-zA-Z_]+', '_', str(c)) for c in Xd.columns]
        Xd = Xd.loc[:, ~Xd.columns.duplicated()].reindex(columns=e['xgb_cols'], fill_value=0.0)
        out.append(e['xgb'].inplace_predict(Xd.to_numpy(dtype=np.float32)) + off_add)
        C = X.copy()
        for c in e['cat_features']:
            C[c] = C[c].astype(str).fillna('NA')
        out.append(e['cat'].predict(C) + off_add)
        return out

    def _offset(self, spec, X, req):
        off = spec['offset']
        if off is None:
            return None
        vals = []
        for col in off['regime']:
            v = req.material if col == 'Material' else (req.wage_type if col == 'Wage Type' else None)
            vals.append('NA' if v is None else str(v))
        key = '|'.join(vals)
        lv = off['levels'].get(key, off['pooled'])
        area = float(np.pi * req.diameter_ft * req.height_ft +
                     2 * np.pi * (req.diameter_ft / 2) ** 2)
        return np.array([np.log(max(area, 1.0)) + lv])

    def _drivers(self, name, X, spec, top=5):
        """SHAP contributions from the first seed, in log space, reported as % effect."""
        try:
            contrib = self._models[name][0].predict(X, pred_contrib=True)[0]
        except Exception:
            return []
        names = list(X.columns) + ['<base>']
        pairs = sorted(zip(names, contrib), key=lambda kv: -abs(kv[1]))
        out = []
        for n, v in pairs:
            if n == '<base>' or abs(v) < 1e-6:
                continue
            out.append(dict(feature=n, effect_pct=round((float(np.exp(v)) - 1) * 100, 1)))
            if len(out) >= top:
                break
        return out

    # ------------------------------------------------------------------ batch
    def predict_many(self, reqs, bucket):
        """Vectorised scoring of one bucket for many requests, for validation and backtesting.

        Uses the SAME feature builder, offset and calibration as predict(), so a backtest
        exercises the shipped path rather than a parallel research one. Returns
        (price, lo, hi, in_scope) arrays.
        """
        spec = self.b['buckets'][bucket]
        X = build_frame(reqs)
        for c in spec['features']:
            if c not in X.columns:
                X[c] = np.nan
        X = X[spec['features']].copy()
        for c, cats in spec['categories'].items():
            vals = X[c].astype('object').where(X[c].notna(), None)
            vals = [v if (v is None or str(v) in cats) else None for v in vals]
            X[c] = pd.Categorical([None if v is None else str(v) for v in vals], categories=cats)
        for c in X.columns:
            if c not in spec['categories'] and str(X[c].dtype) not in ('float64', 'int64'):
                X[c] = pd.to_numeric(X[c], errors='coerce')

        off = spec['offset']
        if off is None:
            offv = None
        else:
            keys = []
            for r in reqs:
                vals = [(r.material if c == 'Material' else
                         (r.wage_type if c == 'Wage Type' else None)) for c in off['regime']]
                keys.append('|'.join('NA' if v is None else str(v) for v in vals))
            lv = np.array([off['levels'].get(k, off['pooled']) for k in keys])
            area = np.array([np.pi * r.diameter_ft * r.height_ft +
                             2 * np.pi * (r.diameter_ft / 2) ** 2 for r in reqs])
            offv = np.log(np.maximum(area, 1.0)) + lv

        # Must mirror predict() exactly, ensemble included - otherwise validate.py measures a
        # different model than the one the service returns.
        o_add = 0.0 if offv is None else offv
        heads = [np.mean([m.predict(X) for m in self._models[bucket]], axis=0) + o_add]
        heads += self._ensemble_logp(bucket, X, o_add)
        lp = np.mean(heads, axis=0) + float(spec.get('level_adjustment', 0.0))

        cal = spec['calibration']
        q0 = conformal_q(np.asarray(cal['scores']), cal['alpha'])
        q = q0 * np.array([float(cal['grade_scales'].get(r.material, 1.0)) for r in reqs])
        scope, _ = zip(*[buckets_in_scope(r) for r in reqs]) if reqs else ([], [])
        in_scope = np.array([s[bucket] for s in scope], dtype=bool)
        # book head (conditional mean) alongside the quote head, so a backtest can score the
        # head that is actually responsible for aggregate dollars
        if self._book.get(bucket):
            expected = np.maximum(np.mean([m.predict(X) for m in self._book[bucket]], axis=0), 0.0)
        else:
            expected = np.exp(lp)
        return np.exp(lp), np.exp(lp - q), np.exp(lp + q), in_scope, lp, expected

    # ------------------------------------------------------------------ public
    def predict(self, req: TankRequest) -> PredictionResponse:
        req_flags = G.check_request(req)
        refused = any(s == 'refuse' for s, _ in req_flags)
        scope, scope_src = buckets_in_scope(req)
        meta = self.b['meta']
        out, warnings = {}, [m for _, m in req_flags]

        for name in BUCKETS:
            spec = self.b['buckets'][name]
            if refused:
                out[name] = BucketPrediction(bucket=name, in_scope=scope[name], price=0.0,
                                             confidence='refused',
                                             notes=[m for s, m in req_flags if s == 'refuse'])
                continue
            if not scope[name]:
                out[name] = BucketPrediction(bucket=name, in_scope=False, price=0.0,
                                             confidence='normal',
                                             notes=['out of scope for this tank'])
                continue

            X, unseen = self._frame(req, spec)
            off = self._offset(spec, X, req)
            o_add = 0.0 if off is None else off
            heads = [np.mean([m.predict(X) for m in self._models[name]], axis=0) + o_add]
            heads += self._ensemble_logp(name, X, o_add)
            lp = np.mean(heads, axis=0)
            lp = lp + float(spec.get('level_adjustment', 0.0))

            cal = spec['calibration']
            q = conformal_q(np.asarray(cal['scores']), cal['alpha'])
            q = q * float(cal['grade_scales'].get(req.material, 1.0))
            price = float(np.exp(lp[0]))
            lo, hi = float(np.exp(lp[0] - q)), float(np.exp(lp[0] + q))
            # book head: conditional MEAN, for aggregation. Falls back to the median if the
            # bundle predates the dual head.
            if self._book.get(name):
                expected = float(max(np.mean([m.predict(X) for m in self._book[name]]), 0.0))
            else:
                expected = price

            pflags = G.check_prediction(name, price, lo, hi,
                                        drift_alarm=bool(spec.get('drift_alarm', False)))
            for col, val in unseen:
                pflags.append(('low', f'{name}: {col}={val!r} was never seen in training; '
                                      f'the model is pricing without that signal'))
            notes = [m for _, m in pflags]
            conf = G.worst(req_flags + pflags)
            warnings.extend(m for _, m in pflags)
            out[name] = BucketPrediction(
                bucket=name, in_scope=True, price=round(price, 2),
                price_expected=round(expected, 2),
                low=round(lo, 2), high=round(hi, 2),
                interval_pct=round((hi / lo - 1) * 100, 1),
                drivers=self._drivers(name, X, spec), confidence=conf, notes=notes)

        return PredictionResponse(
            buckets=out,
            model_version=meta['version'],
            calibration_version=meta['version'],
            trained_on=f"{meta['date_min']}..{meta['date_max']} ({meta['train_rows']} tanks)",
            interval_level=1 - meta['alpha_target'],
            warnings=sorted(set(warnings)),
            scope_sources=scope_src,
        )


if __name__ == '__main__':
    p = Predictor.load()
    r = TankRequest(diameter_ft=30, height_ft=32, material='CS',
                    use_type='Fire Protection Storage Tank',
                    deck_style='2:12 Roof (Comp/Tension Ring - 2 inch Rise to 12 inch Run)',
                    floor_style='Flat Steel Floor', wage_type='Non-Union / Non-Prevailing',
                    country='US', state='TX', ss=0.12, s1=0.05,
                    miles_from_tbt=210, miles_from_gt=0, usable_capacity='150,000 gal',
                    freeboard_in=12, erection_in_scope=True, insulation_selected=False)
    resp = p.predict(r)
    print(f"model {resp.model_version}   trained on {resp.trained_on}")
    print(f"intervals at {resp.interval_level:.0%}\n")
    for name, b in resp.buckets.items():
        if not b.in_scope:
            print(f"  {name:20s}  --- out of scope")
            continue
        print(f"  {name:20s} ${b.price:>12,.0f}   [{b.low:>10,.0f} .. {b.high:>10,.0f}]"
              f"  {b.confidence}")
        for d in b.drivers[:3]:
            print(f"        {d['feature']:<28s} {d['effect_pct']:+7.1f}%")
    print(f"\n  sum of buckets (quote / median)  ${resp.total_predicted():,.0f}")
    print(f"  sum of buckets (book / expected) ${resp.total_expected():,.0f}"
          f"   <- aggregate THIS across tanks, not the medians")
    print("  (the estimating software still adds freight + tax to either)")
    if resp.warnings:
        print("\n  warnings:")
        for w in resp.warnings:
            print("   -", w)
