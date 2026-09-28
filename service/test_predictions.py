"""Prediction regression test: structural invariants + golden values.

Seven results in this project were invalidated by implementation errors, and NOT ONE of them
raised an exception. Each produced plausible numbers and was caught only because a figure looked
implausibly good or bad. Feature parity is pinned by test_parity.py; this pins behaviour.

Two layers, because they catch different things:

  INVARIANTS   must hold for ANY bundle, before and after any retrain. These catch structural
               breakage - a constant-output model, a collapsed interval, a gate that stopped
               gating - without anyone having to eyeball a number.

  GOLDENS      exact predictions for fixed requests. These change legitimately on retrain, so
               they are regenerated deliberately with --update. They catch a refactor that
               silently moves predictions when nothing was supposed to move.

    python service/test_predictions.py            # check
    python service/test_predictions.py --update   # re-bless goldens after an intended change
"""
from __future__ import annotations
import sys, json, pathlib, argparse, warnings
warnings.filterwarnings('ignore')
HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np
from schema import TankRequest, BUCKETS
from predict import Predictor

GOLDEN = HERE / 'golden_predictions.json'
TOL = 0.02          # 2% drift allowed on goldens (seed/library jitter)

CASES = {
    'typical_cs_fire_protection': dict(
        diameter_ft=30, height_ft=32, material='CS',
        use_type='Fire Protection Storage Tank',
        deck_style='2:12 Roof (Comp/Tension Ring - 2 inch Rise to 12 inch Run)',
        floor_style='Flat Steel Floor', wage_type='Non-Union / Non-Prevailing',
        country='US', state='TX', ss=0.12, s1=0.05, miles_from_tbt=210, miles_from_gt=0,
        usable_capacity='150,000 gal', freeboard_in=12,
        erection_in_scope=True, insulation_selected=False, priced_on='2026-06-01'),
    'large_waste_water_prevailing': dict(
        diameter_ft=85, height_ft=40, material='CS', use_type='Waste Water Storage Tank',
        deck_style='Open-Top w/ Top Girder', floor_style='Embedded Ring',
        wage_type='Prevailing Wage', country='US', state='CA', ss=1.4, s1=0.55,
        miles_from_tbt=1600, miles_from_gt=1750, usable_capacity='1,900,000 gal',
        erection_in_scope=True, insulation_selected=True, priced_on='2026-06-01'),
    'materials_only_export_mx': dict(
        diameter_ft=24, height_ft=28, material='304SS', use_type='Industrial Storage Tank',
        deck_style='Aluminum Geodesic Dome', floor_style='Flat Steel Floor',
        wage_type=None, country='MX', state='NL', ss=0.2, s1=0.08,
        miles_from_tbt=900, miles_from_gt=0, usable_capacity='95,000 gal',
        erection_in_scope=False, insulation_selected=False, priced_on='2026-06-01'),
    'small_silo': dict(
        diameter_ft=12, height_ft=45, material='CS', use_type='Industrial Storage Silo',
        deck_style='2:12 Roof (Comp/Tension Ring - 2 inch Rise to 12 inch Run)',
        floor_style='Base Angle Only', wage_type='Non-Union / Non-Prevailing',
        country='US', state='OH', ss=0.15, s1=0.06, miles_from_tbt=400, miles_from_gt=250,
        usable_capacity='320 tons', erection_in_scope=True, insulation_selected=False,
        priced_on='2026-06-01'),
}
# must be REFUSED, not priced: a deck-replacement job entered as a tank
REFUSE_CASE = dict(diameter_ft=40, height_ft=0.22, material='CS',
                   use_type='Water Storage Tank', erection_in_scope=True,
                   insulation_selected=False, priced_on='2026-06-01')


def check_invariants(p) -> list:
    fails = []

    def bad(msg):
        fails.append(msg)

    for name, kw in CASES.items():
        r = TankRequest(**kw)
        resp = p.predict(r)
        for b, pred in resp.buckets.items():
            if not pred.in_scope:
                if pred.price != 0.0:
                    bad(f"{name}/{b}: out of scope but price={pred.price}")
                continue
            if not (pred.price > 0):
                bad(f"{name}/{b}: in scope but price={pred.price} (a constant-output model "
                    f"predicts a fixed value - check init_score handling)")
            if pred.low is None or pred.high is None:
                bad(f"{name}/{b}: missing interval")
            else:
                if not (pred.low < pred.price < pred.high):
                    bad(f"{name}/{b}: point estimate outside its own interval "
                        f"({pred.low:,.0f} / {pred.price:,.0f} / {pred.high:,.0f})")
                if pred.high / pred.low < 1.02:
                    bad(f"{name}/{b}: interval collapsed ({pred.high/pred.low:.3f}x) - "
                        f"calibration is probably fitted on in-sample residuals")
            if pred.price_expected <= 0:
                bad(f"{name}/{b}: book head returned {pred.price_expected}")

        # scope gates must actually gate
        if kw.get('erection_in_scope') is False and resp.buckets['construction'].in_scope:
            bad(f"{name}: erection_in_scope=False but construction is in scope")
        if kw.get('insulation_selected') is False and resp.buckets['insul_material'].in_scope:
            bad(f"{name}: insulation_selected=False but insul_material is in scope")

        # the book head exists to be >= the median in aggregate; per tank allow either way but
        # flag an implausible gap
        tot_q, tot_b = resp.total_predicted(), resp.total_expected()
        if tot_q > 0 and not (0.7 < tot_b / tot_q < 1.5):
            bad(f"{name}: expected/median total ratio {tot_b/tot_q:.2f} is implausible")

    # a degenerate-geometry request must be refused, never priced
    rr = p.predict(TankRequest(**REFUSE_CASE))
    if not all(b.confidence == 'refused' for b in rr.buckets.values()):
        bad("deck-replacement geometry (H=0.22ft) was NOT refused")
    if rr.total_predicted() != 0.0:
        bad(f"refused request still returned ${rr.total_predicted():,.0f}")
    return fails


def snapshot(p) -> dict:
    out = {}
    for name, kw in CASES.items():
        resp = p.predict(TankRequest(**kw))
        out[name] = {b: dict(price=v.price, expected=v.price_expected,
                             low=v.low, high=v.high, in_scope=v.in_scope)
                     for b, v in resp.buckets.items()}
    return out


def main(update=False):
    p = Predictor.load()
    print(f"bundle: {p.b['meta']['version']}\n")

    fails = check_invariants(p)
    print(f"INVARIANTS: {'PASS' if not fails else 'FAIL'} "
          f"({len(CASES)} cases + 1 refusal case)")
    for f in fails:
        print("   -", f)

    snap = snapshot(p)
    if update or not GOLDEN.exists():
        json.dump(snap, open(GOLDEN, 'w'), indent=1)
        print(f"\nGOLDENS: written ({len(snap)} cases) -> {GOLDEN.name}")
        return 1 if fails else 0

    old = json.load(open(GOLDEN))
    drift = []
    for name, buckets in snap.items():
        for b, v in buckets.items():
            o = old.get(name, {}).get(b)
            if o is None:
                drift.append(f"{name}/{b}: new in this bundle")
                continue
            for k in ('price', 'expected'):
                a, c = o.get(k) or 0.0, v.get(k) or 0.0
                if max(a, c) > 0 and abs(c - a) / max(a, 1.0) > TOL:
                    drift.append(f"{name}/{b}.{k}: {a:,.0f} -> {c:,.0f} "
                                 f"({(c-a)/max(a,1)*100:+.1f}%)")
    print(f"\nGOLDENS: {'PASS' if not drift else f'{len(drift)} changed beyond {TOL:.0%}'}")
    for d in drift[:12]:
        print("   -", d)
    if drift:
        print("\n   If this change was intended, re-bless with --update.")
    return 1 if fails else 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--update', action='store_true')
    raise SystemExit(main(ap.parse_args().update))
