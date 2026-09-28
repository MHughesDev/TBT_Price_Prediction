# `service/` — the tank price prediction service

Returns five predicted sell prices per tank, each with an interval, drivers and a confidence
status. It does **not** return freight, tax or a total — those are deterministic and belong to
the estimating software.

```
grand total = sum(five buckets) + freight + tax      <- the estimating software owns this line
```

## Quick start

```bash
python service/test_parity.py        # feature parity gate (must pass before anything else)
python service/train.py              # build a versioned bundle into service/artifacts/
python service/test_predictions.py   # behaviour invariants + golden predictions
python service/predict.py            # score one example tank
python service/validate.py           # rolling-origin backtest + acceptance gate
python service/validate_total.py     # business metric: expected TOTAL price
```

## Two heads — read this before aggregating anything

| field | objective | meaning | use for |
|---|---|---|---|
| `price` | L1 on log | conditional **median** | quoting ONE tank |
| `price_expected` | gamma on $ | conditional **mean** | summing MANY tanks |

`total_predicted()` sums medians; `total_expected()` sums means. **Summing medians under-states
the book by ~6.8%; the expected head cuts that to ~4.0%** ($25.8M recovered across the test set).
A forecast built from `price` will be systematically low and it will not look wrong per tank.

## Measured performance

Rolling-origin backtest **through this code**, 6 origins, weighted by tanks:

| bucket | n | MdAPE | within ±10% | within ±20% | bias | dollar err | rate baseline |
|---|---|---|---|---|---|---|---|
| material | 6,795 | **0.089** | 54.6% | 80.1% | −2.8% | −8.7% | 0.165 |
| fabrication | 6,795 | **0.084** | 57.4% | 83.7% | +1.2% | −5.3% | 0.250 |
| construction | 4,419 | **0.111** | 45.8% | 74.4% | +1.6% | −9.4% | 0.342 |
| insul material | 1,643 | **0.069** | 66.8% | 89.5% | −1.6% | −3.3% | 0.099 |
| insul construction | 1,593 | 0.180 | 37.6% | 61.0% | +3.3% | −1.6% | 0.296 |

80% intervals: coverage 0.793 / 0.798 / 0.793 / 0.786 / 0.797 — every bucket within 3pp.
Guards: 91.6% of live requests scored `normal`, 8.4% `low`.

**Business metric** (total price = 5 buckets + actual freight + actual tax), per quote:
median error −$1,352, MdAPE **5.79%**, **70.2% within ±10%**, MPE +0.01%.
Book: −6.79% summing medians, **−4.04% summing the expected head**.

`insul_construction` is the weak bucket and the reason is understood: insulation field labour
repriced about −25% in 2025Q4, and the window straddles that break. Post-break it runs 0.108–0.119.

For context, two different sales managers pricing the *same spec in the same quarter* disagree by
a median **11.4%**.

## Layout

| file | role |
|---|---|
| `schema.py` | request/response contract and validation |
| `features.py` | **request → model features.** Highest-risk module; mirrors `build/prep.py` |
| `test_parity.py` | **the gate.** 76 features must match the pipeline on all 4,459 rows |
| `train.py` | builds a versioned, immutable bundle. Refuses to run if parity fails |
| `predict.py` | loads a bundle and answers requests. Fits nothing |
| `guards.py` | refusal and low-confidence rules |
| `ops.py` | the monthly jobs: level adjustment, adaptive conformal, drift alarm |
| `validate.py` | rolling-origin backtest through the shipped path, with an acceptance gate |
| `validate_total.py` | the business metric: expected TOTAL price per tank and per job |
| `tank_types.py` | preset tank-type mapping (measured not to pay as an architecture — see docs) |
| `test_predictions.py` | behaviour invariants + golden predictions |

## Design rules that are load-bearing

**Scope gates are inputs, never predictions.** `erection_in_scope` and `insulation_selected` come
from the estimator. Inference is only 93–95% accurate and a gate error is worth ~**$88K** — an
order of magnitude more than the ~10% pricing error. Without them the service falls back to the
wage-type lookup and marks the answer low-confidence.

**The service returns TWO numbers per bucket, and which one you use matters.** `price` is the
conditional median — right for quoting one tank, and systematically low when summed.
`price_expected` is the conditional mean from a gamma head — right for aggregation. This is not a
refinement; using the wrong one across a pipeline costs ~3pp of book error.

**Two feedback loops, and they are not interchangeable.** The level adjustment corrects *where*
the prediction sits; adaptive conformal corrects *how wide* the interval is. The 2026 material
shock broke the level; the 2025Q4 insulation reprice broke the interval. Neither loop fixes the
other's failure.

**Calibration state survives retraining.** α and the level history are learned from realised
coverage on priced quotes and are independent of the model fit. Discarding them on each retrain
resets adaptation to zero — that bug kept the insulation buckets stuck at their initial α through
a whole validation run, under-covering at 0.759 while advertising 0.80.

## Things that will bite you

1. **An all-zero `init_score` is not the same as no `init_score`.** It disables LightGBM's
   `boost_from_average`; under an L1 objective every split gain is then equal, no split is taken,
   and the model emits a constant 0. `fit_offset` returns `None`, never zeros.
2. **The offset carries a level, never a trend.** A time term inside it extrapolates past its
   fitted range at serve time and diverges — measured at h2: MdAPE 0.276, bias −22%.
3. **Conformal calibration must use out-of-sample residuals.** In-sample fits collapse coverage
   from 0.80 to 0.12–0.57.
4. **ACI must consume every cohort**, not just last month's. Months skipped for low volume are
   otherwise silently dropped and the bucket never adapts.
5. **Validate through this code, not a research script.** Cross-validation cannot see the
   extrapolating-offset failure — it looked like a *win* under GroupKFold.
6. **Any feed entering a value-weighted model must pass `ml_eligible`.** With α=1 a corrupt row
   gets weight proportional to its price; the $1.19T row in the ungated revisions feed would
   carry ~15,000,000x a median row. `load_revisions()` refuses to build without the filter, and
   `training_set()` refuses if max/median weight exceeds 5,000x.
7. **`monotone_constraints` and `linear_tree` are both unavailable under `regression_l1`.** Two
   natural tools for the large-tank problem are off the table as a consequence of the objective
   choice. That is why the fix is a second head rather than a constraint on the first.

## Operating it

| job | cadence | what it does |
|---|---|---|
| retrain | monthly | `python service/train.py --inherit <previous bundle>` |
| level adjustment | monthly | trailing-2-month median log residual, per bucket |
| ACI α update | monthly, min 40 quotes | `α += 0.45 × (0.20 − realised miscoverage)` |
| drift alarm | monthly | fires at \|level\| > 5% or 3 consecutive same-direction months |

The ops jobs need the as-of priced-quote feed described in `docs/HANDOFF_TO_DATA_ENG.md` P0-A.
Until historical prices are confirmed immutable, snapshot that feed on every run.

## What this service does not do

- It does not compute freight, tax, margin, contingency or any total.
- It does not decide scope — it is told.
- It does not predict whether a quote will be won.
- It does not know about price shocks before they appear in TBT's own quotes. Expect **3–4%
  systematic under-pricing for roughly two quarters** after a step change. Only a leading external
  signal (the steel index request, procurement Q1) can improve on that.
