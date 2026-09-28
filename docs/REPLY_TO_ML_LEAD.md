# Reply to the ML research lead — data requests

**From:** data engineering
**Date:** 2026-09-24
**Re:** your request list against `ML_Tank_Training`
**Workbook:** `dist/TBT_Tank_Quote_Analytics_v5.4.xlsx` · **Exports:** `exports/`

---

## Read this first: the training row count changed under you

Your analysis is on **4,481 tanks**. The current table has **4,423**.

HANDOFF P0-4 (segment-aware outlier bounds) landed after your cut. It ranks each row's
`$/shell-sqft` *within its own material × scope_class segment* and rejects the 1.5% / 99% tails,
with the old global $1K–$50M band kept as a backstop. It removes 178 rows overall, 58 of which were
training rows.

What it removes is not a pricing problem — it is a **scope** problem:

```
2411243   Tank 1 40' Dome/Roof                H=0.22 ft   $136,607   $4,964/sqft
2410258   Sloped Deck Replacement             H=0.22 ft   $130,636   $5,326/sqft
2407248   Ammonium Hydroxide - Welded Floor   H=0.22 ft    $75,188   $4,239/sqft
```

Deck, floor and roof *replacement* jobs quoted as tanks, with height entered as a placeholder. Shell
area is meaningless on them and `$/sqft` explodes. They would have distorted anything rate-based.

**Please re-run your regressions against `exports/training.parquet`.** I would expect your
`log(quantity)` coefficients and the median within-spec spread to tighten slightly.

---

## Your two resolved items — confirmed, and I had one wrong

### Proposal Total / Total Price

Independently re-verified on all 4,423 rows. Both hold to a maximum relative error of **7.1e-07**:

```
Proposal Total = bucket sum + Total Tax          (carries NO freight)
Total Price    = bucket sum + Freight Price      (carries NO tax)
grand total    = bucket sum + Freight + Tax      (in NEITHER source column)
```

Correlation between `(Proposal Total − bucket sum)` and `Total Tax` is **1.0000000000**. All 1,726
non-tying rows are taxed; all 2,697 tying rows have zero tax. Mean effective rate 4.83%.

I had reported this as an unexplained adder worth $31.1M and had even built a case that it tracked
individual estimators. That was wrong — I tested it against contingency, commission and margin but
never against tax. The estimator pattern was real but spurious: tax follows jurisdiction and
managers own territories. Jorge Gomez is 99.3% international and 0% taxed; John Petersen is 1.7%
international and 89.1% taxed. By country: US 57.9%, Canada 2.2%, Mexico / Peru / Chile / Argentina 0%.

**Build change.** The workbook had encoded `Total Price − (Proposal + Freight + Tax)`, which
double-counts tax and tied on only 61% of rows. `ML_Tank_Training` now carries `recon_proposal_diff`
and `recon_total_diff` against the verified identities (both tie 4,423/4,423), plus a new
**`Ref Grand Total`** = buckets + freight + tax, which is the all-in number no source column holds.
HANDOFF §5 item 5 is closed and the README sheet states the identities.

### Per-tank pricing

Recorded. The descriptive check agrees with your regression — blended `$/shell-sqft` at quantity 2 is
**1.15×** quantity 1 (n=433), not 2×; at quantities 3/4/5/6 it is 0.93 / 1.01 / 0.97 / 0.95.
Targets are **not** divided by `Quantity` anywhere in the pipeline. HANDOFF P0-1 closed.

---

## P0

### 1. Steel price index — escalated to procurement, and here is the evidence attached to the ask

I cannot source an external index. It is written up as Q1 in
`docs/OPEN_QUESTIONS_FOR_THE_BUSINESS.md`, addressed to procurement, asking for monthly HRC and/or
plate from Jan 2023 and for TBT's own purchased cost per ton if it is recorded.

I quantified the shock so the ask carries a number. Material bucket only, **carbon steel only**,
area-weighted by quarter, quarters with n ≥ 25:

| Quarter | n | $/shell-sqft | | Quarter | n | $/shell-sqft |
|---|---:|---:|---|---|---:|---:|
| 2024Q1 | 38 | $25.74 | | 2025Q1 | 485 | $28.45 |
| 2024Q2 | 349 | $29.82 | | 2025Q2 | 446 | $29.75 |
| 2024Q3 | 366 | $28.49 | | 2025Q3 | 436 | $35.82 |
| 2024Q4 | 326 | $23.99 | | 2025Q4 | 432 | $30.22 |
| | | | | **2026Q1** | 453 | **$36.03** |
| | | | | **2026Q2** | 462 | **$37.54** |
| | | | | **2026Q3** | 298 | **$40.65** |

- 2024–2025 mean **$29.03**, range $23.99–$35.82 — noisy quarter to quarter but **no trend in level**.
- 2026 mean **$38.07**, range $36.03–$40.65.
- **Step change +31.1%**, and every 2026 quarter sits above the entire two-year prior range.

That is a regime shift, not drift — which strengthens your case that a backward-looking time feature
cannot track it. Your ~24% was on the pre-P0-4 cut and all materials; on carbon steel alone after
outlier removal it is larger.

### 2. Quote-form scope inputs — confirmed product gap

The source export is 42 columns and **none of them records the estimator's scope selections**.

I tested whether the existing insulation columns could proxy for "insulation selected". They cannot:

| Column | Uninsulated rows | Insulated rows |
|---|---:|---:|
| `Insulation Margin (%)` non-zero | **98.1%** | 98.8% |
| `Insulation Contingency (%)` non-zero | 0.0% | 0.0% |

`Insulation Margin (%)` sits at a median of 5.0 on essentially every row regardless of whether the
tank is insulated. No signal. Your read is correct.

Raised as Q2 in the questions doc, addressed to whoever owns the quote form, asking whether
**"insulation selected yes/no"** and **"erection in scope yes/no"** are collected. If they are, they
replace two leakage columns and the scope gates become real inputs.

### 3. Leakage-free export — done

`exports/training.parquet` and `.csv` — **4,423 rows × 139 columns**, one row per tank at the firmest
revision. **44 leakage columns are physically absent**, not flagged, because a flagged column still
survives `X = df.drop(columns=[target])`.

Everything on your list is gone: `rate_*`, `shop_cost`, `price_per_*`, `material_per_shellsqft`,
`scope_class`, `is_insulated`, `recon_*`, `inc_*`, `Proposal Total`, `Total Price`, `Total Tax`,
`Freight Price`, `First Revision Total`.

**Also removed, which your list did not name:**

| Column | Why it leaks |
|---|---|
| `segment_pctile`, `segment_rank_below`, `segment_n` | New in P0-4 — each row's own `$/sqft` percentile within its segment |
| `dq_price_sane_segment` | Computed from that percentile |
| `dq_price_sane` | Derived from `Proposal Total` |
| `dq_has_positive_target` | Derived from the target sum |
| `construction_scope_conflict` | Compares Wage Type against `Construction Price > 1` |
| `price_segment`, `scope_class_dq` | Contain scope_class |
| `target_*_per_unit` (5) | Targets restated per unit |
| `Ref Grand Total` | Buckets + freight + tax |
| `is_taxed` | Derived from `Total Tax` |
| `quote_balanced_weight` | **Not leakage — a sample weight.** Pass it as `sample_weight`, do not use it as a feature. It is kept out of the feature set deliberately. |

**Verified two ways.** By name: none of your patterns match any surviving column. Data-driven: I
correlated every remaining numeric feature against `log1p(target_material)`. The maximum is **0.858**
(`material_area_intensity` — the legitimate area signal), then `d_x_h` 0.846 and `shell_area_sqft`
0.846. **Zero columns above 0.95.**

`exports/column_manifest.csv` marks all 183 source columns as
**feature (89) / target (5) / identifier (24) / reference (21) / leakage (44)**, each leakage entry
with its reason. `column_manifest.json` repeats it with row counts, the verified money identities and
the known gaps.

The workbook keeps the leakage columns — it is the research and audit surface, and they stay banded
maroon there. The export is the modelling surface.

---

## P1

### 4. All priced revisions — done

`exports/revisions.parquet` — **7,128 rows**, one per tank per priced revision, same leakage policy,
same 139 columns. A revision counts as priced when its buckets sum above zero; rows the DQ layer
rejects as non-tank, unfinished or geometry-less are still excluded, since those are junk rather than
prices.

It adds **+61.2%** over firmest-only, and the gain is concentrated exactly where you said the current
table thins out:

| Month | firmest only | all priced revisions |
|---|---:|---:|
| 2026-04 | 175 | 253 |
| 2026-05 | 142 | **242  (+70%)** |
| 2026-06 | 181 | 245 |
| 2026-07 | 158 | 216 |

**On restatement:** I cannot answer that from a single CSV snapshot — nothing in the export records
whether a price was edited after the fact. Raised as Q7 to estimating/IT, asking whether bucket
prices can change after a revision is priced and whether an audit trail or last-modified timestamp
exists. Until that comes back, treat the feed as potentially mutable and snapshot it as-of each run.

### 5. State normalization — done (HANDOFF P0-2)

`Country Normalized`, `State Normalized` and `Region Code` are in both exports and in the workbook.

I deviated from the HANDOFF spec deliberately. It asked for a crosswalk keyed on `State`; that cannot
be correct, because ten State values resolve differently depending on country —
`BC`+`CA` is British Columbia, `BC`+`MX` is Baja California; `Santiago`+`CL` is Región Metropolitana,
`Santiago`+`EC` is Guayas (city Guayaquil). The key is the **`Country|State` pair**: 219 distinct
pairs, all 219 mapped, zero gaps.

The `Country` column is dirty too — **37 rows had a wrong country corrected** (`US|Jalisco` is
Zapopan, Mexico; `MO|MA` is Uxbridge, Massachusetts; `SA|TX` is Al Jubail, Saudi Arabia).

- **99.1%** of rows resolve to a specific ISO 3166-2 region
- 46 rows held at country level, 24 are non-locations — **not guessed**, marked via `Geo Match Level`
- 208 raw State values → 163 clean regions

`is_domestic` now keys off the corrected country; it was wrong on 37 rows. The crosswalk lives in
`Ref_Lists` in the workbook and in `build/geo_crosswalk.py`, with a note on every entry where the
source was wrong. There is also a `Dashboard_Geographic`.

### 6. Pricing clock — your claim verified, and there is no better field

**Quote number confirmed as job origination.** All 7,438 seven-digit quote groups have month digits
in 1–12. `Due Date` falls in a **later** month than the quote number on 38.4% of rows, same month on
60.0%, earlier on 1.6% — with a maximum lag of **85 months**. Agreed: nobody should index time on it.

**`Due Date` is the only date field in the 42-column source.** There is no created or sent timestamp
to export today. Raised as Q4 to estimating/IT to confirm the semantics against the source system and
to say whether such a timestamp exists and could be added.

---

## P2

### 7. Missing spec fields — escalated

Raised as Q6, asking which of shell plate thickness / course schedule, nozzle count and sizes,
appurtenances, coating or lining spec, and wind/snow loads beyond `Ss`/`S1` the source system holds.

One constraint I added to the ask: only fields the **estimator supplies at quote time** are usable.
Anything produced later in engineering would not exist when the service is asked for a price, so it
would leak in production even though it looks clean in the archive.

### 8. Wage Type — analysed, with one finding worth your attention

| Wage Type | Rows | International | Materials-only | Median construction |
|---|---:|---:|---:|---:|
| Non-Union / Non-Prevailing | 4,466 | 5.0% | 6.2% | $81,334 |
| **(null)** | **1,567** | **86.2%** | **97.8%** | **$0** |
| No Erection Included | 629 | 84.3% | 82.2% | $0 |
| Prevailing Wage | 603 | 0.0% | 4.8% | $134,163 |
| Union Wage | 214 | 0.0% | 0.9% | $166,657 |
| Erection Advisor Only | 1 | 0.0% | 100% | $0 |

Null (20.9%) behaves almost identically to "No Erection Included" — 86.2% international, 97.8%
materials-only, construction priced on only 2.1%. Your read is right: it means "export, materials
only", not missing.

**On the contradictory rows:** I find **112**, not 88 — you are on the 4,481 training grain, I am on
all 7,480 source rows. Median construction $57,039, 0.93× their material price, 65.2% international.

The useful part is the timing: **109 of the 112 are in 2024, and one is in 2025.**

That makes it a legacy entry pattern that stopped rather than a live scope pattern. So the scope gate
can be a **lookup**, not a model — provided 2024 rows are treated as suspect. I have raised Q5 asking
whether something changed in the form or in practice during 2024/2025, and whether null is a
selectable state or a gap that should read "No Erection Included".

---

## Summary

| # | Item | Status |
|---|---|---|
| — | Proposal/Total identities | **Verified.** Workbook corrected; I had this wrong |
| — | Per-tank pricing | **Verified.** Targets never divided by Quantity |
| 1 | Steel price index | **Escalated** to procurement, with the +31.1% step change quantified |
| 2 | Quote-form scope inputs | **Confirmed product gap.** Existing insulation columns are not a proxy |
| 3 | Leakage-free export + manifest | **Done.** 44 columns removed, verified by name and by correlation |
| 4 | All priced revisions | **Done.** +61.2% rows. Restatement question escalated |
| 5 | State normalization | **Done.** 219-pair crosswalk, 99.1% to region, 37 countries corrected |
| 6 | Pricing clock | **Verified.** No better date field exists; semantics escalated |
| 7 | Missing spec fields | **Escalated** to estimating/IT |
| 8 | Wage Type semantics | **Analysed.** Null = export/materials-only; 109 of 112 conflicts are 2024 |

Regenerate the exports at any time with:

```bash
cd build
python prep.py && python prep2.py && python export_training.py
```

Open items needing the business are all in `docs/OPEN_QUESTIONS_FOR_THE_BUSINESS.md`.

---

# Addendum — 2026-09-24, after the P1 backlog

Three things below change numbers you already have. The first is a bug that was in the data
when you pulled it.

## `min_miles` was wrong on 27% of training rows

`Miles to Site (From GT)` is a **literal 0** on 1,853 source rows, and the rate is degrading:
1.4% of 2024 rows, 25.6% of 2025, **51.2% of 2026**. `min_miles` was
`MIN(N(Miles TBT), N(Miles GT))`, so a single zero dragged the minimum to zero.

Only 26 rows have *both* distances zero, so a zero means "never computed", not "at the plant".

**Damage:** 1,827 rows had a real TBT distance — median 800 miles, up to 10,000 — reported as 0.
**1,192 of them are training rows (27%)**, and 1,170 were banded `1. <100mi`.

| | before | after |
|---|---:|---:|
| `1. <100mi` | 1,281 | **100** |
| `2. 100-500mi` | 451 | 540 |
| `3. 500-1000mi` | 1,461 | 2,134 |
| `4. 1000-2000mi` | 1,090 | 1,462 |
| `5. 2000+mi` | 140 | 178 |
| `Unknown` | — | 9 |
| `is_local_site = 1` | ~1,266 | **85** |

`min_miles`, `is_local_site` and `distance_band` are all affected, so **discard any earlier
result that used them.** The fix takes the minimum over the positive distances and emits
`Unknown` when neither exists.

Worth noting how this got missed: pandas and Excel had the *identical* bug, so the
Excel-vs-pandas diff stayed green throughout. Agreement between two implementations is not
correctness. It surfaced from the new data-quality scorecard, where `DQ Miles GT Zero` visibly
falls 98.6% → 74.4% → 48.8% by year.

## Two new price-independent scope features

`Name Has Option` (932 rows) and `Name Partial Scope` (162 rows) are parsed from the **tank name
the estimator typed**. They carry no price information, so unlike `scope_class` and
`is_insulated` they are safe as model inputs — and they are currently the only scope signal in
the table that is not derived from a target.

`Name Partial Scope` fires on names such as *"Tank 2 - Flat Steel Floor"* and
*"Flash Aeration (Roof Option)"* — roof, deck, floor, demo, replacement, rings, shell course,
nozzle, ladder. **16.3% of the P0-4 segment outliers are among them**, which is independent,
price-free corroboration of those rejections.

Both are classified `feature` in the manifest and are in the export.

## Capacity sign, and two divergences that no longer exist

`prep.py`'s capacity regex was `([\d.]+)`, which silently dropped the minus on 44
negative-capacity rows and turned an impossible value into a plausible one. It now preserves
the sign, and a negative capacity is treated as **missing** on both sides — `capacity_gal` and
`capacity_tons` are blank, while `Capacity Value` keeps the signed original so the error stays
traceable. Two entries left the known-divergence list permanently as a result.

## Canonical names for encoding

`Company Canonical` (937 → 933) and `Customer Canonical` (1,297 → 1,294) collapse case,
comma and trailing-period variants — *"American Tank Company Inc"* / *"American Tank Company,
Inc."*, *"HDR Inc"* / *"HDR Inc."*. Small, but for a 937-level field the cardinality is the
point. **Encode on the Canonical column, not the raw one.** Both are in the export as
identifiers.

## Current state

**v5.4 — 23 sheets, 1,532,827 formulas, 0 errors, 24 charts, 4,423 training rows.**
Exports are 139 columns wide now. Regenerate everything in about 100 seconds:

```bash
cd build
python prep.py && python prep2.py && python build_core.py
python recalc_excel.py v5_core.xlsx 1800
python build_ml.py && python build_dash.py && python build_docs.py
python recalc_excel.py TBT_Tank_Quote_Analytics_v5.xlsx 1800
python verify.py TBT_Tank_Quote_Analytics_v5.xlsx
python export_training.py
```
