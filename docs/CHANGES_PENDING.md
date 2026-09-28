# Pending changes — noted, not yet implemented

**As of:** 2026-09-24 · Raised during total-price validation and bundle inventory.
Nothing here is done. Each item says what, why, and how big.

---

## P0 — must land before any revenue/pipeline use

### 1. Large tanks are under-priced, and the acceptance gate cannot see it

Binned on **total area** (an input, so free of regression-to-the-mean artifacts):

| area decile | median area | median total | MPE | MdAPE | **dollar error** | share of book |
|---|---|---|---|---|---|---|
| 0–6 | 1,187–6,212 sqft | $75K–$282K | −1.4% … +2.1% | 5.2–8.9% | −0.3% … −4.3% | 2.4–8.4% |
| 7 | 7,427 | $352K | −3.8% | 6.6% | **−8.8%** | 10.9% |
| 8 | 9,855 | $432K | −2.0% | 6.7% | **−7.6%** | 14.3% |
| 9 | 19,424 | $1.07M | −5.5% | 12.0% | **−14.7%** | **37.8%** |

Top 5% by area (n=138, 25.7% of the book): MPE −10.4%, dollar error **−18.5%**.

Net effect: MPE on the expected total is **−0.57% per job**, but the book is **−8.51%**
($854.9M predicted vs $934.4M actual). Duan smearing recovers only about a third
(−8.51% → −5.62%), so this is mostly a size effect, not the median/mean Jensen gap.

**Two changes:**

**1a. Add dollar-weighted metrics to the acceptance gate.** The gate used MdAPE, w10 and
coverage — all unweighted — so a miss concentrated in the highest-value 10% of tanks was
invisible. Add `wMAPE` and total-dollar error, with a threshold. *This is a defect in the gate I
wrote, not just a model limitation.* Small change, high value: it would have caught this on the
first run.

**1b. Size-conditional level correction.** The same shrunk-offset machinery that took 316SS bias
from −17.3% to −1.4% on the grade axis, applied to the size axis. The top two area deciles carry
~550 test tanks, enough to estimate. Must be validated on rolling origin, not CV — a size
correction fitted in-sample will look better than it is.

Until both land: **do not use this service for revenue or pipeline forecasting.** Per-tank quoting
is unaffected (MdAPE 6.2%, 68.7% within ±10%).

---

## P1 — operational correctness

### 2. Validation runs clobber the production pointer

`service/validate.py` and `validate_total.py` call `train.build()`, which writes
`artifacts/latest.txt`. After a backtest, `latest.txt` pointed at a bundle trained as-of
2026-06-30 on 4,128 tanks instead of the production bundle on 4,459. A predict call would have
silently served a stale model.

**Fix:** backtest bundles go to `artifacts/validation/` and never touch `latest.txt`; only an
explicit production build updates the pointer. Add a `--no-promote` flag to `train.build()`.

### 3. Bundle size

47.8 MB per bundle (20 boosters, 12,432 trees, stored as text). Fine on disk, wasteful to ship
and slow to load. **Fix:** store boosters compressed, or drop to 2 seeds if the measured
0.5pp accuracy gain does not justify 2× the size.

### 4. `insul_construction` uses a `huber` objective while the other four use `regression_l1`

Optuna chose it and it won on that bucket's CV. It is not wrong, but it is an inconsistency worth
a second look, particularly since this bucket also straddles the 2025Q4 structural break — the
objective may be compensating for something a level correction should handle.

---

## P2 — worth doing, not blocking

### 5. HTTP transport

`predict.py` exposes `Predictor.predict()`. No endpoint yet; a thin wrapper once the app team
says what it speaks.

### 6. Golden-prediction regression test

A fixed set of requests with expected outputs, so a refactor that changes predictions fails
loudly. Currently only feature parity is pinned, not predictions.

### 7. Re-test `revisions.parquet` for the ACI cohort

Insulation buckets produce 12–20 quotes/month against a 40-quote minimum, so they buffer 2–3
months before adapting. The all-revisions feed would roughly double the cohort. Measured as a
dead heat for the *level* adjustment; never tested for *interval* adaptation.

### 8. Hyperparameters were tuned once, on one data vintage

They should be re-tuned on a schedule, and the tuning should optimise the dollar-weighted metric
from item 1a rather than unweighted MdAPE.

---

## Open with the business (unchanged, still the highest-value items)

1. **External steel index** (procurement Q1) — the only lever on the 3–4% bias that persists ~2
   quarters after a price shock.
2. **Explicit `erection_in_scope` / `insulation_selected` inputs** (product Q2) — removes an
   ~$88K-per-error failure mode.
3. **Median vs mean output** — now sharper than when first raised: the answer differs by use case,
   and item 1 above shows smearing alone does not fix the forecasting case.

---

## Added 2026-09-24 (tank-type work)

### 9. Production pointer protection — **DONE**
`train.build()` now takes `promote=True/False`; backtests write to `artifacts/validation/` and
never touch `latest.txt`. Was item 2 above.

### 10. `tank_type` should move into the data pipeline
Currently derived in `service/tank_types.py`. It is a deterministic function of `Use Type`, so it
belongs in `build/prep.py` alongside the other derived columns, exported as `role=feature`, and
covered by the parity test like everything else. Ask the data engineer.

### 11. Per-type architecture is built but NOT promoted
`--arch per_type` and `--arch hybrid` produce 96 boosters / 60,792 trees against the pooled 20 /
12,432, and a 124 MB bundle against 48 MB. Measured comparison in
`docs/TANK_TYPE_COMPARISON.md`. Kept selectable, not default.

### 12. Segment hyperparameters are inherited from the pooled tuning
Per-type models reuse the pooled Optuna parameters. A segment with 235 rows almost certainly
wants a smaller tree than one tuned on 4,459. This makes the per-type comparison **conservative**
— re-tuning per segment is the fair test and has not been run.

### 13. `Use Type` carries almost no independent signal
Gain share 0.71% (material, rank 47/95) and 0.28% (construction, rank 58/95); `tank_type` 0.52%
and 0.15%. Most of what looks like a tank-type effect is already captured by geometry, grade,
wage regime and deck style. Worth revisiting only if the business adds tank-type-specific inputs
the model cannot currently see.

---

## Added 2026-09-24 (transfer / accuracy round)

### 14. **Value-weighted training works** — recommended, not yet promoted
Sample weight `w = price / mean(price)` aligns the training objective with the dollar metric.
Rolling origin, 6 origins, 2 seeds:

**material — improves every metric at once, no trade-off**

| variant | MdAPE | w10 | wMAPE | dollar err | top-decile MdAPE | top-decile dollar |
|---|---|---|---|---|---|---|
| pooled | 0.0866 | 0.5615 | 0.1823 | −10.67% | 0.1770 | −16.28% |
| **value-weighted** | **0.0858** | **0.5684** | **0.1728** | **−8.04%** | **0.1517** | **−13.11%** |
| sqrt-value-weighted | **0.0844** | 0.5670 | 0.1787 | −9.25% | 0.1673 | −14.08% |

**construction — a real trade-off**

| variant | MdAPE | w10 | wMAPE | dollar err | top-decile dollar |
|---|---|---|---|---|---|
| pooled | **0.1114** | **0.4628** | 0.2263 | −9.94% | −16.10% |
| value-weighted | 0.1243 | 0.4257 | **0.2229** | **−4.85%** | **−8.47%** |
| sqrt-value-weighted | 0.1125 | 0.4561 | 0.2202 | −8.17% | −13.25% |

**Proposal:** make the weight exponent a tuned hyperparameter, `w = (y/ȳ)^α`, `α ∈ [0,1]`.
α=0 is today's model, α=0.5 is sqrt, α=1 is full value weighting. Tune per bucket against a
stated objective — which forces the quoting-vs-forecasting decision to be made explicitly
instead of by default.

### 15. ~~Size-band level correction~~ — **REFUTED**
Item 1b above. Tested as an out-of-fold shrunk level per area quintile: material dollar error
−10.67% → −10.81%, top decile −16.28% → −16.39%. It does **nothing**. The big-tank gap is not a
level offset, it is a weighting problem — see item 14. My proposed fix was wrong.

### 16. Rate target (`log(price/area)`) — no effect
material 0.0870 vs pooled 0.0866; construction 0.1109 vs 0.1114. Within noise.

### 17. Monotone constraints are unavailable
LightGBM refuses `monotone_constraints` with `regression_l1`, and L1 is the objective that earned
the single biggest gain. Enforcing "price non-decreasing in area" would mean giving that up.

### 18. Transfer from pooled to segment models — all negative
- **H2 residual specialist** (segment model with `init_score` = pooled prediction): material
  0.0864 vs pooled 0.0866. Helps Waste Water (.1368→.1322), hurts Potable (.0849→.0914).
- **H3 continued training** (`init_model` = pooled booster): 0.0859 vs 0.0866, within noise.
- **H5 sample-weighted local**: 0.0879, worse.
- **H6 tank_type in the offset**: best single segment result anywhere — Silo material
  .1622→.1406 (−13.3%) — but Water Storage .0929→.1148 and construction worse overall.

**Why they all fail:** the pooled model's mean log residual on Silo is **−0.74%**. There is
essentially no segment-specific *bias* left to learn. Silo's error is variance, and specialising
increases variance rather than reducing it.

**Two implementation bugs found in the process**, both worth remembering:
- Passing `init_score` together with `init_model` makes LightGBM add **zero trees** — silently.
  This is the third distinct `init_score` failure mode hit on this project.
- My offset-shrinkage sweep was **confounded**: one shrink parameter applies to the whole
  composite key, so raising it changed the grade dimension at the same time as tank_type. That
  sweep does not test what it claimed to and its conclusion should be disregarded.

---

## Added 2026-09-24 (error-reduction round 2)

### 19. **Value-weight exponent α, tuned per bucket** — CONFIRMED, recommend adopting
`w = (y/median(y))^α`. Rolling origin, 6 origins, 4 seeds. **Three of five buckets improve on
every metric at once** — this was never a bias/variance trade, the unweighted objective was
simply the wrong one:

| bucket | α | MdAPE | wMAPE | dollar err | verdict |
|---|---|---|---|---|---|
| material | 0 → **1.0** | 0.0851 → **0.0849** | 0.1807 → **0.1726** | −10.86% → **−8.21%** | dominates |
| insul material | 0 → **1.0** | 0.0656 → **0.0633** | 0.1083 → **0.1044** | −4.47% → **−3.32%** | dominates |
| insul construction | 0 → **1.0** | 0.1565 → **0.1450** | 0.2148 → **0.2062** | −7.44% → **−4.18%** | dominates |
| fabrication | 0 | 0.0889 (α=1: 0.0931) | — | −5.80% (α=1: −3.44%) | real trade-off |
| construction | 0 | 0.1109 (α=1: 0.1237) | — | −9.95% (α=1: −4.69%) | real trade-off |

Clipping weights at 10x never helped. α=1.5 overshoots everywhere except insul_construction.
For the two trade-off buckets α becomes the dial for the quoting-vs-forecasting decision.

### 20. **Down-weighted non-firmest revisions** — CONFIRMED, and it overturns a locked decision
| bucket | firmest only | +revisions w=0.3 | w=0.6 |
|---|---|---|---|
| material | 0.0866 | 0.0839 | **0.0831 (−4.0%)** |
| construction | 0.1114 | **0.1067 (−4.2%)** | 0.1092 |

`docs/ML_SYSTEM_DESIGN.md` §3 states "training on all revisions is much worse" and cites
0.148 → 0.226. **That was measured at FULL weight and is wrong as a general claim.** At weight
0.3–0.6 the extra 2,668 rows are clearly worth having. Design doc §3 needs correcting.
Caveat: dollar error moves the wrong way (−10.67% → −11.54% on material), so this interacts
with α and must be tested jointly, not stacked.

### 21. Prior-revision price — real but small, NOT worth a new input field
Corrected result: **~2.0% on material re-quotes, ~1.4% on construction re-quotes**, over 28.6% of
rows ≈ 0.5% overall. A separate re-quote model is worse (less data). Prior-as-offset blew up
(wMAPE 17.3) because it mixes an absolute log price with a log-area-plus-level offset in one
training run — different scales the model cannot reconcile.

**An earlier version of this test reported −11.4% on construction re-quotes. That was
self-leakage** — the prior was looked up as "last revision before the ORIGIN", which for a
training row can return its own price. Corrected to "last revision before THIS ROW'S own date".
All numbers from the first run are void.

### 22. Running tally of implementation bugs that produced false results
Worth keeping because the pattern is consistent — every one was caught by a number looking too
good or suspiciously identical, never by the code looking wrong:

1. all-zero `init_score` → constant-0 model (L1 objective, no split gain)
2. `init_score` + `init_model` together → zero trees added, silently
3. offset shrink sweep → one parameter applied to the whole composite key, confounding two axes
4. prior-price lookup → self-leakage via origin-relative rather than row-relative dating
5. calibration on in-sample residuals → coverage 0.80 claimed, 0.12–0.57 delivered
