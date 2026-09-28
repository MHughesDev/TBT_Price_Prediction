# Handoff to data engineering — ML research phase complete

**From:** ML research lead · **Date:** 2026-09-24
**Design:** `docs/ML_SYSTEM_DESIGN.md` (revision 2) · **Reference code:** `ml/`
**Prior exchanges:** `docs/REPLY_TO_ML_LEAD.md`, `docs/REPLY_TO_ML_LEAD_2.md`

Research is finished. This closes out the two decisions you flagged for me, records what is now
verified so nobody re-litigates it, and lists what the data layer needs to support the recommended
design. There is no service to build yet — that is deliberate.

---

## 1. Decisions you asked me for

### 1.1 Excel `ML Eligible` divergence (workbook 4,423 vs pandas 4,459) — resolved

**Implement only the geometry half in Excel.** `dq_implausible_geometry` (H < 3 ft OR D < 3 ft) is
an ordinary formula and belongs in the workbook. `dq_price_residual_outlier` is a fitted-model
artifact; a cell formula cannot honestly express it, and forcing it in would break the
"every cell traces back to Raw_Import" principle that makes the workbook worth having.

So: **the parquet export is canonical for modelling, the workbook is canonical for audit**, and the
delta is the 16 residual-flagged rows at the training grain. Please state that number explicitly in
both the README and the Validation sheet rather than trying to reconcile it away. A documented
divergence with a stated cause is fine; a silently different row count is not.

You were right to escalate this rather than pick one.

### 1.2 Gating `revisions.parquet` on the new geometry rule — don't gate, but don't park it yet

Two measured facts:

- **Training on all 7,128 revisions is much worse** than firmest-only (material MdAPE 0.148 → 0.226
  by h2, against 0.110 → 0.128). Superseded revisions are stale prices that duplicate jobs.
- **For the monthly level adjustment the denser feed is a dead heat** — recalibrating off all
  revisions vs firmest-only gives 0.109 / 0.110 / 0.115 either way.

On those two alone I would have parked it. But a third use appeared after those tests, and it
changes the answer:

> The adaptive-conformal loop (§8.1 of the design) needs at least **40 priced quotes per update**.
> The insulation buckets only produce **12–20 firmest-revision quotes per month**, so they currently
> buffer 2–3 months before they can update their interval width. The revisions feed would roughly
> double that cohort and let them update monthly.

**Request:** leave `revisions.parquet` as it is (ungated, 7,128 rows) and add the geometry flag as a
column so I can filter it myself. I will test whether it improves the insulation buckets' interval
adaptation. If it does not, we park it then — with evidence rather than by assumption.

---

## 2. What the data layer needs to support the design

### P0-A. As-of snapshotting of the priced-quote feed (your Q7) — now critical

This was a reasonable question when you raised it. It is now a blocker, because the recommended
design has **two independent feedback loops that both read recently-priced quotes**:

| loop | reads | corrects |
|---|---|---|
| monthly level adjustment | trailing 2 months of priced quotes | *where* the prediction sits |
| adaptive conformal (ACI) | realised coverage on priced quotes | *how wide* the interval is |

If historical bucket prices can be edited after a revision is priced, both loops are reading a
mutable past and will silently mis-correct. Please push Q7 with estimating/IT, and until it comes
back, **snapshot the feed as-of each run** and keep the snapshots. If an audit trail or
last-modified timestamp exists, exporting it is the cleanest fix.

### P0-B. A canonical `priced_month` column

Both loops currently derive their month from `Due Date` inside my code. That derivation should live
in one place in the pipeline, not in every consumer. Please add an integer `priced_month`
(months since 2020-01) computed from `Due Date`, to `training.parquet`, `training_full.parquet` and
`revisions.parquet`.

Note for whoever maintains it: **`Due Date` is the time index** (the date the sales manager needed
the quote back by, i.e. when this revision was priced). **The quote number encodes job origination
and must never be used as a time index** — you verified lags up to 85 months.

### P1-C. Record the two structural breaks in the data documentation

The archive contains two regime changes. Both are real, both survived every robustness check I
could construct, and both will confuse anyone who trains a model without knowing about them:

| when | what | size |
|---|---|---|
| **2026Q1–Q3** | material price step change | **+24.0%** quality-adjusted (+31.1% raw CS, your number) |
| **2025Q4** | insulation field labour reprice | **≈ −25%** |

Evidence for the second, since it is new since your last reply — median insulation-construction
$/sqft by quarter: `8.78 8.75 8.89 9.78 9.12 9.15 │ 6.14 7.57 7.48 7.94`, and the ratio to
insulation material breaks at the same moment: `1.41 1.28 1.29 │ 0.97 0.98 0.96 1.04`.

A short "known regime breaks" section in the README would save the next person a day.

### P1-D. Do **not** add the physics features to the pipeline

I built API 650 shell/floor/roof steel-weight estimates (`ml/physics.py`). They are a genuinely
better size signal in isolation (univariate log-log R² **0.782** vs area's 0.757) but add
essentially nothing to a gradient-boosted model that already has D and H — because the **code
minimum governs shell thickness on 81% of tanks**, so area is near-sufficient for four tanks in five.

They stay in the ML layer as pure functions of existing columns, used for *explaining* a price
rather than predicting one. No pipeline change needed. Flagging it so nobody adds them speculatively.

### P1-E. `quote_balanced_weight` — keep, but mark unused

I asked for this column and then measured that it makes things **worse** on four of five buckets
(material 0.090 → 0.092). Keep it exported with `role = reference` as you have it, and please add
"not used by the recommended recipe (tested 2026-09-24)" to the manifest note so it does not get
quietly adopted later.

### P2-F. Monthly monitoring job

The design calls for a monthly quality-adjusted (hedonic) price index per bucket for drift
detection. That is arguably a data-layer job rather than an ML one. Happy either way — tell me which
side you want it on.

---

## 3. Verified — please record, do not re-derive

Everything here is measured on `exports/training.parquet` (4,459 rows) and reproducible from `ml/`.

| fact | status |
|---|---|
| `Proposal Total = bucket_sum + Tax`; `Total Price = bucket_sum + Freight`; grand total in neither | verified by both of us, 4,459/4,459 |
| Bucket prices are **per tank**, never divided by `Quantity` | verified by both of us |
| **Firmest-revision grain is correct** — now *tested*, not assumed | all-revisions training is far worse |
| The recalibration feed does **not** need all revisions | dead heat, see §1.2 |
| Scope gates cannot be reliably inferred — lookup 93.4%, classifier 95.5%, and a gate error costs **$88,260** median | the case for your Q2 |
| The "~14%/yr escalation" is mostly **mix shift** — hedonic CAGR is +8.8% material, +0.7% fabrication, **−1.0% construction** | use the hedonic number as an index, not the raw one |

---

## 4. The data contract the models consume

From `exports/training.parquet`:

- the **89 `role = feature`** columns, exactly as the manifest defines them
- `t_year`, `t_month` (derived from `Due Date`; see P0-B)
- `gate_insul` — **currently reconstructed in research from `target_insul_material > 0`**. This is
  legitimate for training only because the app supplies the equivalent at inference. **It must become
  a real input field (your Q2).** Until then it is the one place the research harness touches a target.
- physics features, computed in `ml/physics.py` from `Diameter (ft)`, `Height (ft)`, `Material`,
  `roof_slope_ratio`, `deck_is_open_top`, `deck_has_rafters`, `liquid_height_ft`

Never consumed: anything with `role = leakage`, and `quote_balanced_weight`.

---

## 5. Reproducing the results

```bash
python ml/recipe.py          # rolling-origin accuracy + interval coverage (quote these)
python ml/recipe.py --cv     # cross-validated numbers (tuning protocol, optimistic - do not quote)
```

`ml/` contains `data.py` (loader + feature contract), `physics.py` (API 650 weights),
`aci.py` (adaptive conformal), `recipe.py` (reference implementation),
`tuned_params.json` (Optuna results per bucket).

Current output:

```
ACCURACY - rolling origin
bucket                MdAPE    w10    w20    bias
construction          0.107  0.478  0.758   0.000
fabrication           0.083  0.569  0.819  -0.001
insul_construction    0.173  0.401  0.638   0.037
insul_material        0.051  0.719  0.924  -0.008
material              0.083  0.578  0.802  -0.017

INTERVALS - target 80%
bucket              coverage  width
construction           0.809  1.513
fabrication            0.805  1.439
insul_construction     0.800  1.749
insul_material         0.804  1.305
material               0.810  1.490
```

Two caveats on reading those. **`insul_construction` reads 0.173 because the window straddles the
2025Q4 break** — post-break it runs 0.108–0.119, in line with construction; quote it as ~0.11 in a
stable regime. And these aggregate by month weighted by n, which differs by ~0.01 from the
per-origin averages in the design doc; both are defensible, they just answer slightly different
questions.

---

## 6. Still with the business, not with us

Ranked by value, and all three are worth more than any remaining modelling work:

1. **External steel price index** (your Q1, procurement) — the only lever on a 3–4% systematic
   under-pricing that persists ~2 quarters after a price shock. That is now the largest known
   systematic error in the system.
2. **Explicit `erection_in_scope` / `insulation_selected` inputs** (your Q2, product) — removes an
   $88K-per-error failure mode that no amount of modelling can fix.
3. **Median vs mean output** (business) — the service returns a median, which is right for quoting
   a single tank. But the sum of medians is not the median of the sum: **summing predictions across
   many tanks under-states the book by ~5.4%** (Duan smearing factor 1.0338). If anyone plans to use
   this for pipeline or revenue forecasting, they need the smeared variant. That is a product
   decision about what the service is *for*.
