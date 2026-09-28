# Model Card — TBT Tank Price Prediction

**Deployed bundle:** `bundle-pooled-20260924-1723-71b8b7a773ae.pkl.gz` (68 MB) — attached to the
[v1.0.0 release](../../releases/tag/v1.0.0) of this repo, not committed to git. Download it and
point `service/artifacts/latest.txt` at it, or run `python service/train.py` to build your own
from `exports/training.parquet`.

This is a summary for anyone pulling the model artifact off GitHub without reading the full
design doc. For the complete rationale behind every decision here, see
[`docs/ML_SYSTEM_DESIGN.md`](ML_SYSTEM_DESIGN.md); for the deployed contract, see
[`service/README.md`](../service/README.md).

## What it predicts

Five independent sell-price buckets per storage tank quote — **material, fabrication,
construction, insulation material, insulation construction** — each with an uncertainty interval,
a confidence status, and driver attribution.

It does **not** predict freight, tax, margin, contingency, or a grand total, and it does not
decide whether a tank is in scope for construction or insulation. Those are supplied by the
estimator as inputs (`erection_in_scope`, `insulation_selected`) — inferring them was measured at
93–95% accuracy, and a scope error is worth ~$88K against a ~10% pricing error everywhere else, so
the service refuses to guess.

## Architecture

Each of the five buckets is modelled **independently**, and each bucket has **two heads** built
from the same features and the same trees:

| head | objective | statistic | use for |
|---|---|---|---|
| **quote head** (`price`) | L1 (or Huber) on log price | conditional **median** | pricing one tank |
| **book head** (`price_expected`) | gamma on raw dollars | conditional **mean** | summing many tanks |

One model cannot serve both — summing per-tank medians is not the median of the sum, and
systematically under-states a book of business. Measured on total price: **book error −6.79%**
summing quote-head medians vs **−4.04%** summing book-head means. The gamma head exists purely to
fix that aggregation bias.

Per head, per bucket:

- **Level offset** — `log(total_area_sqft)` plus a shrunk median-log-residual level by regime
  (grade/wage-type), passed in as `init_score`. A *level*, never a trend: no time term, since that
  would extrapolate past its fitted range at serve time.
- **Multi-family ensemble** — LightGBM + XGBoost + CatBoost, each fit on the same target and
  offset, averaged in log space. Wins or ties on every bucket; largest gains on the weakest
  buckets (insul_construction −9.5% MdAPE, insul_material −7.4%).
- **Seed ensemble** — the LightGBM member is itself 4 seeds, geometric mean.
- **Monthly level adjustment** — trailing-2-month median log residual on realised quotes, applied
  on top of the trained model (corrects *where* the prediction sits).
- **Conformal interval** — CV+ conformal, scaled per grade, under adaptive conformal inference
  (ACI: `α += 0.45 × (0.20 − realised miscoverage)`, monthly, min 40 quotes per cohort). Corrects
  *how wide* the interval is — a separate feedback loop from the level adjustment.

Architecture name in the bundle metadata: `pooled` (one model per bucket across all tank types —
measured to beat a per-type or hybrid split at current data volume; see
[`docs/TANK_TYPE_COMPARISON.md`](TANK_TYPE_COMPARISON.md)).

## Training data

- Source: `build/archive.csv`, 7,480 rows × 42 columns, the single data-entry point for the whole
  pipeline.
- Modelling export: `exports/training.parquet`, **4,459 tanks, 89 leakage-free features**, one row
  per tank at its firmest quote revision.
- Non-firmest revisions are included too, at 0.5 sample weight (2,668 extra rows) — tested at
  several weights, and shown to reduce error rather than just adding noise, provided it's a weight
  and not a hard inclusion/exclusion choice.
- Per-bucket **value weighting** (`w = (price / median price) ** α`) is applied so the loss isn't
  dominated by small tanks: α = 1.0 for material / insul_material / insul_construction, 0.5 for
  construction, 0.25 for fabrication (fabrication's α was kept low because raising it traded ~3pp
  of per-tank MdAPE for book-error headroom construction needed more).

## Hyperparameters (quote head, Optuna-tuned per bucket)

| bucket | objective | learning rate | num_leaves | num_boost_round | min_data_in_leaf |
|---|---|---|---|---|---|
| material | L1 | 0.0749 | 162 | 402 | 40 |
| fabrication | L1 | 0.0309 | 28 | 1104 | 21 |
| construction | L1 | 0.0445 | 164 | 452 | 39 |
| insul_material | L1 | 0.0185 | 49 | 508 | 19 |
| insul_construction | Huber | 0.0299 | 149 | 642 | 9 |

Full tuned parameters (feature/bagging fractions, L1/L2 regularisation, categorical handling) are
in [`ml/tuned_params.json`](../ml/tuned_params.json). The book head reuses the same offset and
features per bucket, with `objective='gamma'` substituted (gamma has its own log link, so no
`init_score` offset is added there).

## Measured performance

Rolling-origin backtest **through the deployed serving code** (not a research script — see
"things that will bite you" below), 6 origins, weighted by tanks:

| bucket | n | MdAPE | within ±10% | within ±20% | bias | dollar err | rate baseline |
|---|---|---|---|---|---|---|---|
| material | 6,795 | 0.089 | 54.6% | 80.1% | −2.8% | −8.7% | 0.165 |
| fabrication | 6,795 | 0.084 | 57.4% | 83.7% | +1.2% | −5.3% | 0.250 |
| construction | 4,419 | 0.111 | 45.8% | 74.4% | +1.6% | −9.4% | 0.342 |
| insul material | 1,643 | 0.069 | 66.8% | 89.5% | −1.6% | −3.3% | 0.099 |
| insul construction | 1,593 | 0.180 | 37.6% | 61.0% | +3.3% | −1.6% | 0.296 |

80% interval coverage: 0.793 / 0.798 / 0.793 / 0.786 / 0.797 — every bucket within 3pp of nominal.

**Business metric** (total price = 5 buckets + actual freight + actual tax), per quote: median
error −$1,352, MdAPE **5.79%**, **70.2% within ±10%**, MPE +0.01%. Summed across the book:
**−6.79%** using the quote head, **−4.04%** using the book head.

For context: two sales managers pricing the *same spec in the same quarter* disagree by a median
of **11.4%** — the floor this model is measured against, not zero.

`insul_construction` is the weak bucket, and the cause is understood, not mysterious: insulation
field labour repriced ~−25% in 2025 Q4, and the backtest window straddles that break. Post-break
it runs 0.108–0.119 MdAPE, in line with the other buckets.

## Known limitations

- **No external price signal.** The model only knows about a cost shock once it shows up in TBT's
  own priced quotes — expect 3–4% systematic under-pricing for roughly two quarters after a step
  change (e.g. the 2026 material shock). A leading indicator (steel price index) has been
  requested but is not wired in.
- **Scope gates must be supplied, not inferred.** Without `erection_in_scope` /
  `insulation_selected`, the service falls back to a wage-type lookup and marks the response
  low-confidence rather than guessing.
- **Calibration state is not re-derivable from the model weights alone.** The level-adjustment
  history and ACI α are learned from realised coverage on priced quotes and must be carried
  forward across retrains — discarding them on retrain silently resets adaptation to zero (this
  has happened; it froze the insulation buckets' α at their initial value for a full validation
  run, under-covering at 0.759 while advertising 0.80).
- **`monotone_constraints` and `linear_tree` are unavailable** under the `regression_l1` objective
  used for four of the five quote heads — the large-tank extrapolation problem is solved with the
  second (gamma) head instead of a monotonicity constraint on the first.

## Reproducing this bundle

```bash
python service/test_parity.py   # gate: 76 features must match build/prep.py on all rows
python service/train.py         # refuses to run if the parity gate fails
```

`train.py` refuses to build silently-wrong models — see `service/README.md` §"Things that will
bite you" for the specific failure modes it guards against (all-zero `init_score` collapsing a
model to a constant, in-sample conformal residuals collapsing coverage, un-gated revision rows
getting catastrophic sample weight, etc.).
