# TBT Tank Price Prediction — ML System Design

**Author:** ML research lead · **Date:** 2026-09-24 · **Revision 3**
**Data:** `exports/training.parquet` — 4,459 tanks, 89 features, leakage-free
**Status:** design proposal. §13 lists what is still open. Every number is measured on this data.

---

## 1. What the service is

A stateless prediction service called **once per tank**, returning five sell prices in dollars
(margin-loaded as stored in history), each with an uncertainty interval and an explanation.

It does **not** return freight, tax, or a total. Those are deterministic and belong to the
estimating software. Verified on 4,459/4,459 rows to max relative error 7.1e-07:

```
Proposal Total = bucket_sum + Tax            (carries no freight)
Total Price    = bucket_sum + Freight        (carries no tax)
grand total    = bucket_sum + Freight + Tax  (exists in NO source column)
```

The estimating software owns that third line. It is the only place it exists.

---

## 2. Architecture

```
  estimator ──▶ ESTIMATING SOFTWARE (deterministic)
                specs · freight · tax · margin · assembled total · proposal
                        │  POST /predict   (one tank)
                        ▼
                PREDICTION SERVICE (statistical)
                  scope gates ◀── supplied as INPUTS, never predicted
                        │
                  5 independent bucket models
                        │  each: level offset → GBM → seed ensemble
                        ├── monthly level adjustment   (per bucket, one scalar)
                        └── conformal interval          (per bucket, per grade)
                        │
                        ▼  5 × {price, lo, hi, drivers, model_version}
                estimator reviews, overrides any bucket, quote is assembled
```

Four artifacts version together and serve as one unit: **model weights**, **level offsets**,
**monthly level adjustments**, **conformal calibration**. Every response names all four versions.

---

## 3. Grain and target

**One row per tank at the firmest revision of its job, plus non-firmest revisions at a reduced
sample weight.**

> **Correction to revision 2.** That revision stated "training on all 7,128 priced revisions is
> much worse (0.148 → 0.226 by h2)" and treated it as a locked decision. **That measurement was
> taken at FULL weight and is wrong as a general claim.** At weight 0.3–0.6 the extra 2,668 rows
> are clearly worth having:
>
> | bucket | firmest only | + revisions w=0.3 | w=0.6 |
> |---|---|---|---|
> | material | 0.0866 | 0.0839 | **0.0831 (−4.0%)** |
> | construction | 0.1114 | **0.1067 (−4.2%)** | 0.1092 |
>
> Superseded revisions are noisier than firmest ones, not worthless. The right treatment is a
> weight, not exclusion. Caveat: revision weighting moves dollar error the *wrong* way
> (−10.67% → −11.54% on material), so it interacts with value weighting (§6.7) and the two must
> be set jointly.

**Per tank, not per line.** Controlled log-log `log(quantity)` coefficients: +0.052 material,
+0.071 fabrication, −0.107 construction, +0.038 / +0.096 insulation. Per-line would be ≈1.0.
**Never divide a target by `Quantity`.**

**Modelled in log dollars**, so the service returns a **median**. Prices ≤ $1 are zero (ten `$0.01`
sentinels meaning "in scope, not priced").

> **Contract detail:** the sum of five medians is not the median of the sum. Measured Duan
> smearing factor is 1.0338 — **summing predictions across many tanks under-states the book by
> ~5.4%**. Per-tank quoting should use the median; pipeline/revenue forecasting needs the smeared
> variant. These are different products off the same model.

---

## 4. Scope gates are inputs, never predictions

Construction is zero on 34.8% of tanks, insulation on ~78%. That is scope, not missing data.

Inference is not good enough to substitute for an input:

| method | accuracy | errors |
|---|---|---|
| wage-type lookup | 93.4% | 291 |
| learned classifier (AUC 0.977) | 95.5% | 199 |

Median construction price when the gate is on is **$88,260**, so a gate error is an ~$88K mistake
against a ~10% pricing error everywhere else. The errors are also **not** a retired 2024 pattern —
they run 127 / 86 / 78 across 2024 / 2025 / 2026.

**`erection_in_scope` and `insulation_selected` are required request fields.** Until the quote form
collects them, the service falls back to the wage-type lookup and marks the response low-confidence.

---

## 5. Model structure

**Five independent models, one per bucket.** Not multi-output. The buckets have different drivers
(material is a commodity, construction is labour), different scope populations, different
multiplicative regimes, and demonstrably different temporal behaviour — a shared level correction
would be wrong for most of them.

Each model trains only on rows where its bucket is in scope. There is no zero-inflation to model,
because the zeros come from the gate.

---

## 6. The training recipe

Per bucket, in the order each component earns its place:

### 6.1 Objective — L1 on log price

`MdAPE` is a **median** metric; L2 on log targets the conditional *mean* of log. L1 targets the
median. This is the single largest modelling gain, and Optuna selected `regression_l1` independently
for every bucket.

| bucket | log + L2 | **log + L1** |
|---|---|---|
| material | 0.101 | **0.091** |
| construction | 0.147 | **0.113** |

Also tested and beaten: huber-on-log, and gamma / tweedie / poisson on raw price.

### 6.2 Level offset via `init_score`

```
offset = log(total_area_sqft) + level[regime]
```

`level[regime]` is the median log rate for that regime, **shrunk toward the pooled level by n/(n+k)**
with `k` tuned per bucket. Regime is the bucket's dominant multiplicative driver:

| bucket | regime | tuned shrink k |
|---|---|---|
| material, fabrication, insul material | **Material grade** | 6.2 / 24.8 / 64.8 |
| construction | **Wage Type** | 7.0 |
| insul construction | none | — |

This exists to fix what a tree cannot learn: a 3× grade multiplier estimated from 71 rows. Effect on
316SS in the material bucket — **MdAPE 0.203 → 0.152, bias −17.3% → −1.4%** — with no cost to the
carbon-steel mass (0.092 → 0.087).

> **The offset carries a LEVEL, never a TREND.** An earlier version included a time spline; because
> serve-time months fall beyond the fitted range, it extrapolated and diverged — material h2 MdAPE
> **0.276, bias −22%**. Clamping the spline rescues it; dropping the time term entirely is better
> still. Time belongs in the model's features and in the monthly adjustment (§7), never in a
> parametric term that runs off the end of its data.

### 6.3 Hyperparameters

Optuna, 60 trials per bucket, objective = OOF MdAPE under `GroupKFold(5)` on `QuoteGroupID`, tuned
**on this exact recipe** (offset shrinkage included as a search parameter). Tuned values live in
`tuning2.json`. Worth roughly 0.3–0.5pp over defaults.

### 6.4 Seed ensemble

4–8 seeds, geometric mean (arithmetic mean in log space). Worth ~0.5pp MdAPE and ~1.3pp w10.

### 6.5 Chained bucket predictions (tail-heavy buckets only)

Buckets are strongly correlated (material↔fabrication 0.844, material↔insul_material 0.899).
Feeding out-of-fold material/fabrication predictions into construction cuts **MAPE 1.044 → 0.920**
with little median movement. Use for construction and insul_construction; it slightly *hurts*
fabrication.

### 6.6 Rejected, with evidence

| idea | result |
|---|---|
| engineering steel weight (API 650) as a feature | univariate R² 0.782 vs area's 0.757, but ~0 gain in a GBM — the tree already learns D×H. **Keep for explanation, not prediction.** The code minimum governs thickness on **81% of tanks**, so area really is near-sufficient. |
| `quote_balanced_weight` as `sample_weight` | worse on 4 of 5 buckets (material 0.090 → 0.092) |
| gamma / tweedie / poisson on raw price | all lose to L1-on-log |
| GBM + hedonic-ridge blending | flat on material, worse on fabrication |
| XGBoost / CatBoost / RF / ExtraTrees | LightGBM ties or wins; XGBoost's construction edge was one seed and did not survive |
| training on all revisions | much worse (§3) |

---

## 7. Temporal design

### 7.1 What the data says

The "~14%/yr escalation" in the foundation doc is **mostly mix shift**. Hedonic index (quarter
dummies + full spec controls) vs raw:

| bucket | raw CAGR | hedonic CAGR | pre-2026 | **2026 step** |
|---|---|---|---|---|
| material | 12.6% | +8.8% | −0.5% | **+24.0%** |
| insul material | 6.7% | +5.4% | +1.8% | **+11.9%** |
| fabrication | 2.5% | +0.7% | −1.7% | +3.6% |
| construction | 14.6% | **−1.0%** | −5.3% | +3.3% |
| insul construction | 0.6% | −1.0% | −14.8% | +14.7% |

**Two years of zero real escalation, then a step change in early 2026 confined to the material
buckets.** Robust across eight slices (revision-0 only +19.6%, CS only +24.5%, firm bids +20.7%,
outlier-robust median regression +18.3%); not explained by censoring (revision and outcome move
price by under 1.6%).

> The data engineer's +31.1% and this +24.0% are both correct and measure different things — theirs
> is a raw area-weighted CS rate, this is quality-adjusted. **Use the hedonic number as an index.**

### 7.2 Ruled out

Recency weighting (half-life 6/12mo), rolling 18-month windows, constant fitted escalation,
monotone-increasing time constraints, per-grade level correction, `linear_tree` extrapolation —
all no-ops or actively harmful. Details and numbers in the session record.

### 7.3 What works: the monthly level adjustment

One scalar per bucket: the **median log residual over the trailing two months of newly-priced
quotes**, added before exponentiating. Trailing median beats EWMA; K=2 beats K=3 and K=6.

Its entire value is preventing decay between retrains — it barely moves horizon 0 and transforms
horizon 2 (material 0.125 → 0.095, bias −7.8% → −2.2%).

It does **not** need `revisions.parquet`: recalibrating off all 7,128 revisions vs the 4,459 firmest
is a dead heat. Firmest-only is sufficient and simpler.

### 7.4 The irreducible part

Nothing survives a shock quarter. Material bias at horizon 0 through the 2026 break:

```
                       2026Q1   2026Q2   2026Q3
quarterly retrain      -0.065   -0.049   -0.006
+ monthly adjustment   -0.041   -0.034   -0.005
monthly full retrain   -0.033   -0.030    0.001
```

**Expect 3–4% systematic under-pricing for ~two quarters after any step change.** That is the floor
for a backward-looking system. Only a *leading* exogenous signal beats it — hence the steel index
request (procurement Q1) is the highest-value open item in the project.

---

## 8. Uncertainty

**Conformal prediction. Not quantile regression.** Under an identical rolling-origin protocol:

| method | material coverage @80% nominal | construction |
|---|---|---|
| LightGBM quantile | **0.558** (worst origin 0.487) | 0.571 |
| conformal | **0.777** | 0.788 |

An interval claiming 80% and delivering 56% is worse than no interval — it teaches estimators to
trust the model where it is weakest.

**Mondrian (group-conditional) by grade is required.** Global conformal gives stainless only
0.685 / 0.660 coverage on material / fabrication while advertising 0.80; normalized + Mondrian
by grade restores 0.777 / 0.824 *and* gives narrower intervals.

**Calibration must use out-of-sample residuals.** Calibrating on in-sample fits collapses coverage
to 0.12–0.57. Production uses cross-conformal (CV+): out-of-fold residuals across the training
window, grouped by job, so all data trains *and* all data contributes honest residuals.

### 8.1 Adaptive conformal — required, not optional

Split conformal assumes the calibration and serving periods are exchangeable. **This archive
violates that twice**: a +24% material shock in 2026 and a −25% insulation-labour reprice in
2025Q4. Static calibration therefore drifts in both directions at once, and the failure is severe —
`insul_material` static coverage in the second half of the evaluation was **0.533** while
advertising 0.80.

The fix is **adaptive conformal inference** (Gibbs & Candès 2021): treat the miscoverage level as a
control variable driven by realised coverage.

```
alpha_{t+1} = clip( alpha_t + gamma * (alpha_target - miscoverage_t) )
```

Long-run coverage converges to the target under *arbitrary* distribution shift, with no
exchangeability assumption. Updates run in monthly batches, on top of the scaled-Mondrian grade
scaling.

**Deployed configuration: `gamma = 0.45`, minimum cohort 40 quotes per update, one state per
bucket.** The minimum cohort matters — a month of 12 insulation quotes has a ~11pp standard error
on its coverage estimate, and updating from that injects pure noise; observations buffer until 40
have accumulated.

Measured over an 17-month month-by-month simulation (quarterly retrain, monthly level adjustment,
monthly interval update):

| bucket | static coverage | **ACI coverage** | static width | **ACI width** |
|---|---|---|---|---|
| material | 0.873 | **0.808** | 1.728 | **1.497** |
| fabrication | 0.822 | **0.805** | 1.487 | **1.439** |
| construction | 0.901 | **0.808** | 1.965 | **1.537** |
| insul material | 0.671 | **0.796** | 1.216 | 1.313 |
| insul construction | 0.683 | **0.788** | 1.693 | 1.795 |
| **mean \|coverage − 0.80\|** | **0.089** | **0.007** | 1.618 | **1.516** |

Better calibrated *and* narrower: the three over-covering buckets tighten, the two under-covering
ones correctly widen.

**Robustness:** any `gamma` in [0.25, 0.60] performs within 0.02 of the best. The failure mode is
`gamma` too *small* — 0.05 leaves material still over-covering at 0.85 after 17 months because it
cannot climb fast enough. DtACI (multi-gamma expert aggregation, Gibbs & Candès 2022) removes the
need to choose gamma at all and is still 2.5× better than static, but loses to a tuned gamma
(steady-state error 0.042 vs 0.017) because its aggregation pulls toward the slower rates.

**Operationally, alpha is a drift instrument as well as a calibration knob.** A bucket whose alpha
moves persistently is telling you the error distribution has shifted — the insulation buckets' alpha
fell from 0.20 to ~0.09 across the 2025Q4 reprice, before the level adjustment had fully absorbed it.

**Honest interval width:** an 80% band is roughly **±35%** around the point estimate even though
median error is ~8%. The residual distribution is heavy-tailed (MAPE 0.136 vs MdAPE 0.083) — most
tanks land close, a minority land far. The interval is telling the truth the median flatters.

**Acceptance bar, measured from the business's own behaviour:** two different sales managers pricing
the *same spec in the same quarter* disagree by a median **11.4%**; the same manager with themselves,
**3.9%** (n=105 / 739 pairs; the cross-manager cell is thin and same-manager pairs may be more
genuinely similar jobs, so treat as indicative). The implied irreducible floor from identical-spec
pair spreads is ~3.2% (material), ~2.8% (fabrication), ~5.7% (construction).

---

## 9. Validation protocol

Two protocols, two questions. **Never a random split.**

**A. `GroupKFold(5)` on `QuoteGroupID`** — feature and hyperparameter selection. A job can hold 29
tanks sharing one pricing decision; splitting a job across folds leaks.

**B. Rolling-origin on `Due Date`** — release acceptance and any number quoted to the business.
Train before an origin quarter, score horizons 0/1/2.

Protocol B is consistently worse and **catches failures A cannot** — the extrapolating-offset bug
(§6.2) looked like a *win* under A and was catastrophic under B. Quote B to the business.

`Due Date` is the time index: the date the sales manager needed the quote back by, i.e. when this
revision was priced. **The quote number encodes job origination (YYMMNNN) and must never index
time** — revisions land years after a job opens (max lag 85 months).

---

## 10. Measured accuracy

Full tuned recipe, rolling-origin, averaged over 6 origins:

| bucket | h0 MdAPE | h1 | h2 | w10 (h0) | w20 (h0) | bias (h0) |
|---|---|---|---|---|---|---|
| material | **0.083** | 0.083 | 0.088 | 0.581 | 0.803 | −1.7% |
| fabrication | **0.083** | 0.086 | 0.087 | 0.574 | 0.822 | −0.1% |
| construction | **0.106** | 0.118 | 0.128 | 0.480 | 0.758 | +0.2% |
| insul material | **0.050** | 0.060 | 0.060 | 0.718 | 0.929 | −1.3% |
| insul construction | 0.162 | 0.174 | 0.124 | 0.400 | 0.602 | +0.9% |

Against the starting point (time features, quarterly retrain, untuned):

| bucket | before h0/h2 | **after h0/h2** | reduction |
|---|---|---|---|
| material | 0.110 / 0.128 | **0.083 / 0.088** | −25% / −31% |
| fabrication | 0.108 / 0.141 | **0.083 / 0.087** | −23% / −38% |
| construction | 0.156 / 0.163 | **0.106 / 0.128** | −32% / −21% |
| insul material | 0.070 / 0.099 | **0.050 / 0.060** | −29% / −39% |

Bias is now within ±2% at every horizon, and the model **no longer decays with age**.

Cross-validated numbers (protocol A) are better and must **not** be quoted to the business:
material 0.0805, fabrication 0.0763, construction 0.1124, insul material 0.0275,
insul construction 0.1051.

On a $200K material bucket, 8.3% median error is ±$17K — against an $88K gate error and an 11.4%
disagreement between two human estimators.

---

## 11. Operations

| job | cadence | what it does |
|---|---|---|
| full retrain | **monthly** | best measured accuracy; quarterly is the fallback |
| level adjustment | **monthly** | one scalar per bucket, trailing 2 months, median log residual |
| conformal recalibration | **monthly** | CV+ residual quantiles × shrunk per-grade scale |
| **ACI alpha update** | **monthly**, min 40 quotes | `alpha += 0.45 × (0.20 − realised miscoverage)`, per bucket |
| hedonic index refresh | **monthly** | quality-adjusted index per bucket, for drift detection |

The system therefore carries **two independent feedback loops**, both driven by quotes that have
already been priced: the level adjustment corrects *where* the prediction sits, and ACI corrects
*how wide* the interval around it should be. Both proved necessary — the 2026 material shock broke
the level, the 2025Q4 insulation reprice broke the interval, and neither loop fixes the other's
failure.

**Drift alarm:** raise when a bucket's monthly level adjustment exceeds ±5%, or moves the same
direction three months running. The 2026 shock would have tripped it in 2026-03. The alarm triggers
a retrain and tells the business a regime may have changed — it does not auto-correct.

**Refuse rather than guess** when: height < 3 ft or diameter < 3 ft (these are deck/floor/roof
replacement jobs quoted as tanks); shell area < ~600 sqft (only 108 training tanks); grade is
304SS/316SS at thin support (n=258/71); the scope gate came from the fallback lookup; the conformal
interval exceeds a width threshold; or the drift alarm is live for that bucket. A refusal returns
the rate-table fallback flagged low-confidence.

---

## 12. Reference: what the rate table is for

`price ≈ rate × area` is the most useful *intuition* in this dataset and a **2× worse estimator**
(material MdAPE 0.196 vs 0.083). It stays as the fallback model and as the floor every release must
beat — not as the design.

For explaining a price to an estimator, the engineering decomposition is the right story: **$/lb
declines monotonically with size** (2.78 → 1.78 across size octiles) while **lb/sqft rises**, which
is why $/sqft is U-shaped. Two clean effects — economies of scale, and heavier plate — rather than
one strange curve.

---

## 13. Open items

1. ~~Conformal calibration is not tight.~~ **CLOSED** — see §8.1. Adaptive conformal brings mean
   coverage error from 0.089 to 0.007 with narrower intervals.
2. ~~`insul_construction` is the weak bucket.~~ **CLOSED as a structural break, not a defect.**
   Insulation field labour repriced roughly −25% in 2025Q4: median $/sqft ran 8.78 / 8.75 / 8.89 /
   9.78 / 9.12 / 9.15 then **6.14**, 7.57, 7.48, 7.94; the ratio to insulation material broke at the
   same moment, 1.41 / 1.28 / 1.29 → 0.97 / 0.98 / 0.96 / 1.04. That is why cross-validation
   (interpolating across the break) said 0.105 and rolling-origin (predicting through it) said
   0.162. Per-origin error confirms it: 2025Q4 **0.234** and 2026Q1 **0.224** straddle the break,
   while 2026Q2 **0.119** and 2026Q3 **0.108** are in line with construction. Four candidate fixes
   were tested — grade offset, wage offset, chaining off insul_material, and modelling the ratio to
   insul_material. The ratio form is marginally best (0.162 vs 0.171) and **none repair the break**,
   which is correct: a repricing cannot be predicted before it happens. The monthly level adjustment
   is the designed remedy and already takes 0.171 → 0.162.
   *Residual action:* adopt the ratio parameterisation for this bucket (small but free), and quote
   its accuracy as ~0.11 in a stable regime rather than 0.162 averaged across a break.
3. **Steel index** (procurement Q1) — the only lever on the 3–4% shock floor.
4. **Explicit scope inputs** (product Q2) — removes an $88K-per-error failure mode.
5. **Construction's tail** — MdAPE 0.106 vs MAPE 0.714. Chaining helped; more is available.
6. **Excel `ML Eligible` formula still encodes the retired trim** — workbook says 4,423, pandas
   4,459. Needs an architecture call on whether a fitted-model flag can live in the workbook.
7. **Median vs mean output** (§3) — a product decision, not a modelling one.
8. Hyperparameters were tuned once, on one data vintage; they should be re-tuned on a schedule.

---

# Revision 3 — findings and decisions, 2026-09-24

Everything below was measured after revision 2 shipped. Where it contradicts an earlier section,
this section governs and the earlier text has been corrected in place.

## R3.1 The recipe changes — three components, tested jointly

The three additions interact (α improves dollar error; revisions and ensembling worsen it while
improving MdAPE), so they were tested together rather than stacked. Rolling origin, 6 origins,
2 seeds:

| bucket | baseline | **all three** | gain | w10 | dollar err |
|---|---|---|---|---|---|
| material | 0.0866 | **0.0777** | **−10.3%** | 0.5615 → 0.5888 | −10.67% → −9.77% |
| fabrication | 0.0896 | 0.0845 | −5.7% | 0.5513 → 0.5728 | −5.82% → −5.26% |
| construction | 0.1114 | **0.1066** | −4.3% | 0.4628 → 0.4820 | −9.94% → −8.84% |
| insul material | 0.0661 | **0.0556** | **−15.9%** | 0.7069 → 0.7281 | −4.40% → −2.13% |
| insul construction | 0.1576 | **0.1225** | **−22.3%** | 0.3699 → 0.4687 | −7.54% → −4.71% |

**Two recommended configurations, not one.** The full stack wins MdAPE; dropping the ensemble
(α + revisions only) wins dollar error on material (−8.06% vs −9.77%), fabrication and insul
construction. Log-space averaging shrinks toward the middle, which deepens the large-tank
shortfall. Choose by objective — the same quoting-versus-forecasting axis as §3 and §R3.5.

### R3.2 Value weighting (new §6.7)

```
w_i = (y_i / median(y)) ^ alpha
```

α=0 is the old model. Per-bucket frontier, 4 seeds:

| bucket | α | MdAPE | dollar err | verdict |
|---|---|---|---|---|
| material | **1.0** | 0.0851 → 0.0849 | −10.86% → **−8.21%** | dominates on every metric |
| insul material | **1.0** | 0.0656 → **0.0633** | −4.47% → **−3.32%** | dominates |
| insul construction | **1.0** | 0.1565 → **0.1450** | −7.44% → **−4.18%** | dominates |
| fabrication | 0.25 | 0.0889 → 0.0894 | −5.80% → −5.42% | real trade-off |
| construction | 0.25 | 0.1109 → 0.1123 | −9.95% → −9.00% | real trade-off |

On three buckets this is **not a trade-off** — the unweighted objective was simply the wrong one.
Clipping weights at 10× never helped; α=1.5 overshoots except on insul construction.

**Value weighting makes data quality safety-critical.** With α=1 a row priced at $1.19 trillion
receives **15,210,212× the weight of a median row**. Any feed entering a value-weighted model
must pass `ml_eligible` — see R3.6.

### R3.3 Multi-family ensembling (new §6.8)

LightGBM + XGBoost + CatBoost, averaged in log space: material 0.0866 → 0.0849, construction
0.1114 → **0.1074**, and the first change to lift construction's w10 (0.4628 → 0.4820). Costs
dollar error, as above.

### R3.4 Architecture: pooled beats tank-type, confirmed under a fair test

Per-segment hyperparameter tuning closed a mean **10.5%** of the handicap the first comparison
imposed (34% on the worst segment). It was not enough. Head-to-head, rolling origin, 4 seeds:

| bucket | **pooled** | +tank_type | per-type (tuned) | per-type (pooled params) | hybrid |
|---|---|---|---|---|---|
| material | **0.0851** | 0.0877 | 0.0893 | 0.0916 | 0.0858 |
| fabrication | **0.0889** | 0.0891 | 0.0969 | 0.0916 | 0.0903 |
| construction | **0.1109** | 0.1116 | 0.1203 | 0.1261 | 0.1164 |
| insul material | **0.0656** | 0.0679 | 0.0676 | 0.0682 | 0.0657 |
| insul construction | **0.1565** | 0.1597 | 0.2088 | 0.1695 | 0.1799 |

**Decision: keep pooled.** `--arch per_type` and `--arch hybrid` remain selectable for re-testing
as the archive grows. Full detail in `docs/TANK_TYPE_COMPARISON.md`.

Note that on two buckets the *tuned* segment parameters are **worse** than the pooled ones
(insul construction 0.1695 → 0.2088). Per-segment tuning overfit its own within-segment CV.

### R3.5 Business-level accuracy — the metric that was missing

Expected total price = five predicted buckets + actual freight + actual tax:

```
per job    MPE -0.57%   MdAPE 6.18%   within +/-10%: 68.7%
per tank   MPE -1.21%   MdAPE 6.75%   within +/-10%: 64.8%
BOOK       -8.51%       ($854.9M predicted vs $934.4M actual)
```

**MPE and the book disagree by 8 points** because MPE weights a $55K tank like a $2M one. Binned
on total area (an input, so free of regression-to-the-mean artifacts), the top decile carries
**37.8% of the book** and is under-predicted by **14.7%**; the top 5% by **18.5%**.

**The acceptance gate could not see this**, because every metric in it — MdAPE, w10, coverage —
is unweighted. `service/validate.py` must add wMAPE and total-dollar error with thresholds.

### R3.6 Refuted, with numbers

| idea | result |
|---|---|
| size-band level correction | **nothing** — dollar −10.67% → −10.81%. This was the design's own proposed fix for the big-tank gap and it is wrong; the gap is a weighting problem, not a level offset |
| isotonic calibration | best top-decile dollar error of anything tested (−12.1% vs −16.3%) but costs MdAPE (0.0866 → 0.0924). α achieves both, so α dominates |
| linear recalibration | worse on material, marginal on construction |
| feature pruning | worse on both buckets once aggregated correctly |
| rate target `log(price/area)` | within noise |
| monotone constraint on area | **unavailable** — LightGBM refuses `monotone_constraints` with `regression_l1` |
| pooled→segment transfer (residual specialist, continued training, weighted-local, tank_type offset) | all within noise or worse. Root cause: the pooled model's mean log residual on Silo is **−0.74%**, so there is no segment-specific bias left to learn |
| prior-revision price | ~2% on re-quotes, 28.6% coverage ≈ 0.5% overall. **Not worth a new input field** |
| `quote_balanced_weight` | worse on 4 of 5 buckets |
| engineering steel weight (API 650) as a feature | better univariate signal (R² 0.782 vs 0.757) but ~0 in a GBM. Keep for explanation |

### R3.7 Methodological findings that should outlive this project

**Cross-validation systematically flatters anything that does not generalise across time.** Three
separate instances: the extrapolating time offset looked like a *win* under GroupKFold and gave
h2 MdAPE 0.276 / bias −22% forward; per-segment tuning showed 34% CV gains that partly reversed
under rolling origin; conformal calibration on in-sample residuals claimed 80% coverage and
delivered 0.12–0.57. **Rolling origin is the acceptance protocol; GroupKFold is for tuning only.**

**Seven results in this project were invalidated by implementation error, and none of them
errored.** Each produced plausible numbers and was caught only because a figure was implausibly
good or implausibly bad:

1. all-zero `init_score` → constant-0 model (L1: no split gain anywhere)
2. `init_score` + `init_model` together → zero trees added, silently
3. offset shrink sweep → one parameter spanning a composite key, confounding two axes
4. prior-price lookup → self-leakage via origin-relative rather than row-relative dating
5. conformal calibration on in-sample residuals → coverage collapse
6. pruning results labelled by per-origin feature count → each row averaged a different subset
7. `revisions.parquet` read without `ml_eligible` → a $1.19T price in training

**Recommended: assertions in the experiment harness**, not vigilance. Target range checks, "the
trained model has more trees than its init model", "predictions differ from the init model",
"every feed applied its eligibility filter". Item 7 is the sharpest lesson — the flag existed, was
documented, was mentioned in the handoff, and was still not applied.

---

## R3.8 Dual head — SHIPPED

The median-vs-mean question (§3) was never a single choice. It is **two products off the same
features**, and forcing one model to serve both is what produced an 8.5% book gap.

| head | objective | returns | use for |
|---|---|---|---|
| **quote** | L1 on log price | conditional **median** | pricing ONE tank |
| **book** | gamma on raw dollars | conditional **mean** | summing MANY tanks |

Gamma has a log link of its own and predicts the mean directly, so it carries no back-transform
bias. Measured on total price (5 buckets + actual freight + actual tax), rolling origin:

| | quote head | **book head** |
|---|---|---|
| average error per quote | −$34,222 | **−$20,354** |
| MPE | +0.01% | +2.47% |
| MdAPE | **5.79%** | 6.59% |
| within ±10% | **70.2%** | 66.4% |
| **book total** | −6.79% | **−4.04%** |
| | $870.9M | **$896.7M** vs $934.4M actual |

Each head wins the metric it exists for. The book head recovers **$25.8M** of the shortfall.

API: `price` and `price_expected` per bucket; `total_predicted()` and `total_expected()` on the
response. Cost is one extra booster set per bucket — no new library, no new features.
Bundle 79.5 MB → 143.1 MB.

### R3.9 What did NOT fix the large-tank gap

| idea | result |
|---|---|
| **size-banded Duan smearing** | **made it worse** (−8.06% → −9.85%). The measured factor is **0.9896 — below 1** — and flat across size (1.0245 → 0.9908). Value weighting had already pulled the model toward the mean, so smearing double-corrected downward. The reasoning was sound for a plain L1 model and false once α was in the recipe |
| size-band **level** correction (rev 2 §13 item 1b) | mathematically guaranteed nil: L1 fits the conditional median, so the median residual is ≈0 by construction |
| smooth smearing regressed on log(area) | much worse (−15.4%) |
| tail specialist (large tanks, `init_score` from pooled) | 0.0790 vs 0.0791 — no effect |
| `linear_tree` | **unavailable** — LightGBM refuses it with `regression_l1` |

> **Two structural limits the L1 objective imposes.** Neither `monotone_constraints` nor
> `linear_tree` can be used with `regression_l1`. Both would have been natural tools for the
> large-tank problem. This is a real cost of what was otherwise the single largest gain in the
> project, and it is why the fix had to come from a second head rather than from constraining
> the first.

### R3.10 Testing

`service/test_predictions.py` pins behaviour in two layers:

- **Invariants** — hold for any bundle, before and after any retrain. Out-of-scope buckets return
  exactly 0; the point estimate lies inside its own interval; intervals have not collapsed; the
  book head returns a positive value; scope gates actually gate; degenerate geometry is refused
  rather than priced.
- **Goldens** — exact predictions for four fixed requests, re-blessed deliberately with
  `--update`.

The invariants exist because **seven results in this project were invalidated by implementation
error and not one raised an exception**. A constant-output model, a collapsed interval and a gate
that stopped gating are all silent failures that these assertions turn loud.

---

## R3.11 Multi-family ensemble — SHIPPED

LightGBM (4 seeds) + XGBoost + CatBoost, averaged in log space, on the quote head.

I rejected this earlier on the grounds that log-space averaging worsens dollar error. That
objection was **valid when one head served both jobs and void once the book head shipped**: the
quote head is now free to optimise per-tank accuracy alone. Shipping one improvement unblocked
another, which I did not connect at the time.

Effect through the service, rolling origin:

| bucket | MdAPE | w10 | book dollar |
|---|---|---|---|
| material | 0.089 → **0.087** | 0.546 → 0.551 | −8.6% |
| fabrication | 0.084 → 0.084 | 0.574 → 0.577 | −4.0% |
| construction | 0.111 → 0.112 | 0.458 → **0.465** | −4.2% |
| insul material | 0.069 → **0.064** | 0.668 → **0.714** | −5.8% |
| insul construction | 0.180 → 0.183 | 0.376 → **0.397** | **−0.1%** |

**w10 improves on all five**; MdAPE on two, marginally worse on two. Bundles are now gzipped and
are *smaller* than before the ensemble: 143 MB → **67.8 MB**.

### R3.12 The acceptance gate now tests each head against its own metric

The ensemble initially **failed** the gate: material quote-head dollar error −10.5% against a
±10% threshold. The gate was written before the dual head existed and applied its dollar test to
`price` — the median head, which is *expected* to sum low.

The threshold was not relaxed. It moved to `price_expected`, the head the design makes
responsible for aggregation, and both heads are still reported side by side. The book head then
passed comfortably, and by a wide margin on four buckets:

```
                 quote head   book head
construction         -9.2%       -4.2%
fabrication          -6.2%       -4.0%
insul_construction   -2.7%       -0.1%
material            -10.5%       -8.6%
insul_material       -3.1%       -5.8%   <- the one bucket where the book head is worse
```

> **A gate changed after it fails deserves scrutiny.** The justification here is that the
> criterion was measuring a head nobody uses for that purpose, not that the number was
> inconvenient. The threshold is unchanged, both heads remain visible in the output, and the
> ensemble would have been reverted had the book head failed.

### R3.13 Rejected in this round

| idea | result |
|---|---|
| **re-tuning hyperparameters on the deployed recipe** | a wash — 3 buckets marginally better, 2 worse, all within noise, for a **143 MB → 373 MB** bundle. The gap was real (parameters were tuned on 4,459 unweighted rows; the model now trains on 7,036 weighted) but the recipe change did not move the optimum enough to matter. Reverted |
| 8 seeds instead of 4 | within noise; the seed-averaging gain saturates by 4 |
| ratio-to-material decomposition | clearly worse on MdAPE (insul material 0.060 → 0.098). Notably it had the **best dollar error of any variant** on three buckets — constraining ratios limits aggregate bias while amplifying per-tank error |

Two bugs found while wiring the ensemble, both of the same family as the earlier seven:

- **`predict_many` did not use the ensemble** while `predict()` did, so `validate.py` would have
  measured a different model than the service returns. Caught by asserting the single-row and
  batch paths agree; they now match to 1e-6.
- **Changing the bundle to gzip broke three call sites** that opened raw pickle. Bundle IO is now
  centralised in `save_bundle` / `load_bundle`.

### R3.14 Where the remaining aggregate error actually is

The book head leaves the bucket sum at **-5.95%**. That number is not spread evenly, and the
decomposition changes what is worth working on next. Weighting each bucket's book-head dollar
error by its share of total dollars:

| bucket | share of $ | book dollar err | contribution to the -5.95% |
|---|---|---|---|
| material | 43.6% | -8.6% | **-3.74 pp** |
| construction | 28.1% | -4.2% | -1.18 pp |
| fabrication | 20.4% | -4.0% | -0.81 pp |
| insul_material | 3.8% | -5.8% | -0.22 pp |
| insul_construction | 4.2% | -0.1% | -0.00 pp |

**Material is 63% of the entire remaining aggregate miss.** It is simultaneously the largest
bucket by dollars and the worst by percentage error. Any further modelling effort that is not
aimed at material is rounding error by comparison — a 2pp improvement on material is worth more
than eliminating the error on both insulation buckets entirely.

This is also the strongest available argument for the external steel index (procurement Q1 in
§13). Material is steel, and the one temporal effect the data unambiguously shows is a +24%
material step across 2026Q1-Q3 (§7.1). A level the model can only learn *after* it has been
priced into closed quotes is exactly the failure an external index removes.

#### The `insul_material` head reversal — closed, not worth acting on

`insul_material` is the one bucket where the book head is *worse* than the quote head
(-5.8% vs -3.1%). Two observations:

- The ordering across buckets is consistent with residual dispersion driving the book head's
  gain: `insul_material` has the lowest MdAPE (0.064) and is the only negative, while
  `insul_construction` has the highest (0.183) and gains 2.6pp. But the correlation is only
  +0.50 over five points, and the lognormal Jensen gap predicts 0.4-3.8% where the observed
  gains are 2-5pp. **The ordering fits; the magnitudes do not.** The gain is therefore mostly
  the gamma head fitting large tanks better, not a variance correction, and the reversal is
  not explained.
- It does not matter. `insul_material` is 3.8% of dollars, so switching that one bucket to the
  quote head moves the bucket sum by **+0.10 pp**.

Selecting the head per bucket would be fitting a choice to one backtest for a tenth of a point.
Both heads stay on the quote head / book head split as designed, and this is recorded as a known,
bounded, unexplained anomaly rather than tuned away.

### R3.15 Final validated business metric

Rolling origin, 6 origins, through the shipped service code. Total price = 5 predicted buckets
+ actual freight + actual tax. Freight and tax are 5.9% of the book and are supplied exactly,
so a total is slightly easier than the buckets alone (buckets-only MPE -0.92%, MdAPE 6.54%).

**Per job (a quote, summed over its tanks) — n=1,852, average job $504,533**

| | median head (returned today) | book head (gamma) |
|---|---|---|
| MPE (signed, systematic) | **-0.26%** | +2.60% |
| MdAPE (typical quote) | **5.67%** | 6.64% |
| within +/-10% | **71.0%** | 66.7% |
| within +/-20% | **90.1%** | 88.0% |
| average signed $ error | -$36,135 | **-$19,405** |
| median signed $ error | -$1,200 | +$2,424 |
| average absolute $ error | $63,681 | **$60,477** |
| median absolute $ error | **$13,736** | $15,219 |
| book total | $867.5M vs $934.4M (**-7.16%**) | $898.5M vs $934.4M (**-3.85%**) |

Per tank (n=2,748, average tank $340,027) the same pattern holds: median head MdAPE 6.22%,
67.8% within +/-10%, -7.16% on the book; book head MdAPE 7.27%, 62.6% within +/-10%, -3.85%.

**This table is the whole argument for the dual head.** Neither column dominates:

- The median head is the better *quote*. It is essentially unbiased on a typical job
  (MPE -0.26%, median signed error -$1,200) and has the smaller typical miss ($13,736).
- The book head is the better *book*. It halves the average signed error per job
  ($36.1K -> $19.4K) and cuts the aggregate shortfall from -7.16% to -3.85%.

The book head's MPE is **positive** (+2.60%) while it still sums **low** (-3.85%). That is not a
contradiction and it is the clearest statement of the problem that remains: the mean head
over-prices the typical job slightly, and is still under-pricing the largest jobs enough to pull
the aggregate down. Per §R3.14 that residual is concentrated in material.

Note the spread between average absolute error ($63,681) and median absolute error ($13,736) —
a factor of 4.6. Reporting only one of these misrepresents the system. The typical quote is off
by ~$14K; the average is dragged up by a small number of very large jobs.

**Reporting guidance:** quote the median head to estimators and the book head to finance. Never
aggregate the median head — summing a conditional median is what produces the -7.16%, and that
is a property of the median, not an error in the model.
