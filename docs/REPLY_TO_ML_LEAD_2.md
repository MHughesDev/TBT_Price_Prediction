# Reply to the ML research lead — the four data-layer changes

**From:** data engineering
**Date:** 2026-09-24
**Re:** P0-4 trim replacement, row-exclusion policy, `quote_balanced_weight`
**Exports:** `exports/` · **Pipeline:** `build/prep.py -> prep2.py -> export_training.py`

All four are done. Every number below is printed from the regenerated export, not carried
over from an earlier run. Nothing in this change touches a target definition, the
firmest-revision grain, or the leakage policy.

---

## Headline

```
training.parquet        4,423  ->  4,459 rows    (+36 net)
training_full.parquet         NEW  4,504 rows    (same grain, before the DQ filter)
revisions.parquet             7,128 rows         (unchanged)
columns                   139  ->  141
max |corr| feature vs log1p(target_material)   0.858   (was 0.858, threshold 0.95)
feature-role column count       89  ->  89       (unchanged)
```

Your diagnosis holds on the current grain: of the 64 rows the trim rejected there, **30 are
top-tail, at a median size percentile of 1.0**. Retiring it releases 41 rows and costs
nothing in coverage — the two extreme data-entry errors in the archive (**$11.2 billion** and
**$1.30 billion** material prices) were caught by the trim, are caught by the `$50M` global
band, and are caught *again* by the new residual rule at **29σ** and **20σ**. Three
independent rules agree on the genuine junk; only the trim also deleted the small and the
very large tanks.

---

## 1. The P0-4 segment trim is retired as a gate

### Your U-shape, reproduced independently

Median `$/shell-sqft`, material bucket, by area octile. Left column is the old 4,423-row
training set — I reproduced it exactly before changing anything, so the two tables are
comparable.

| octile | median area | **old set** $/sqft | **new set** $/sqft |
|---|---:|---:|---:|
| 1 | 866 | $32.39 | $32.55 |
| 2 | 1,427 | $27.17 | $27.13 |
| 3 | 2,141 | $25.80 | $25.80 |
| 4 | 2,836 | $24.93 | $24.75 |
| 5 | 3,377 | $23.76 | $23.68 |
| 6 | 3,994 | $25.29 | $25.17 |
| 7 | 5,186 | $24.79 | $24.82 |
| 8 | 9,149 | $37.22 | $37.33 |

Linear `corr(log area, log rate)` is **0.005** on the new set. Confirmed: the linear
correlation is near zero *because* the relationship is U-shaped, and a rule keyed on
`Material x scope_class` with no size term therefore reads the ends of the size
distribution as price outliers.

**Measured at the firmest-revision grain (4,504 rows), the old rule flagged 64, of which 30
were top-tail. Those 30 sit at a median size percentile of 1.0 and a 75th of 2.7.** Your
numbers were 45 and 17 — you were on the pre-P0-4 4,481-row cut, I am on the current grain.
Same conclusion, larger: it is a small-tank filter.

`dq_price_sane_segment`, `segment_pctile`, `segment_rank_below` and `segment_n` are **still
computed and still in the workbook** as research output. They are **out of `ml_eligible`**
and they stay **leakage**.

### (a) `dq_implausible_geometry` — the junk rule

```python
dq_implausible_geometry = 1 when Height < 3 ft OR Diameter < 3 ft
```

Pure geometry. It touches no price, so unlike the trim it cannot delete a tank for being
expensive.

**The 3 ft threshold sits in a natural gap.** The highest flagged height in the whole
archive is **2.539 ft**; the lowest unflagged one is **3.5 ft**. Nothing is near the line.

| | rows |
|---|---:|
| flagged over all 7,480 source rows | **350** |
| ...of which `Height` is literally 0 (already excluded by `dq_has_geometry`) | 323 |
| **...incremental catch, i.e. rows that have valid geometry** | **27** |
| at the firmest-revision grain | **13** |

**Cross-tab against `dq_looks_nontank`, on the 7,157 rows that have geometry:**

| | nontank = 0 | nontank = 1 | total |
|---|---:|---:|---:|
| **implausible_geometry = 0** | 7,119 | 11 | 7,130 |
| **implausible_geometry = 1** | **27** | **0** | 27 |
| total | 7,146 | 11 | 7,157 |

**The overlap is zero.** The two rules are completely independent: the junk-word list catches
11 rows the geometry rule misses, the geometry rule catches 27 the word list misses. At the
training grain the overlap is also zero (13 vs 6). Keep both.

One honest note: **the `Diameter < 3` half currently catches nothing on its own** — all 27
incremental catches come from `Height < 3`. It is kept as a symmetric guard, not because it
is doing work today.

**The 13 rows it removes at the training grain:**

| Tank Name | H | D | area | material $ |
|---|---:|---:|---:|---:|
| Ammonium Hydroxide - Welded Floor | 0.219 | 25.78 | 18 | $10,226 |
| Tank 2 - 64' Dome/Roof | 0.219 | 63.03 | 43 | $90,216 |
| 35.62 Diameter 2:12 Sloped Deck Replacement (EXTERNAL RAFTERS) | 0.219 | 35.65 | 25 | $21,330 |
| 35.62 Diameter 2:12 Sloped Deck Replacement (INTERNAL RAFTERS) | 0.219 | 35.65 | 25 | $17,057 |
| Tank 1 | 0.219 | 30.77 | 21 | $1,051 |
| Tank 1 40' Dome/Roof | 0.219 | 40.00 | 28 | $55,198 |
| Stripped Permeate - Welded Floor | 0.260 | 34.38 | 28 | $16,974 |
| Biomass - Welded Floor | 0.260 | 34.38 | 28 | $16,970 |
| Embed Ring + 1 Ring | 0.333 | 9.23 | 10 | $2,310 |
| Centrifuge Mix Tank - Rectangular Tank #2 (10'-6"T x 10'W x 14'-1½"L) | 0.333 | 3.08 | 3 | $91,080 |
| Centrifuge Mix Tank - Square Tank #1 (10'T x 10'W x 10'L) | 0.333 | 3.08 | 3 | $66,847 |
| Anaerobic Digester - Welded Floor | 1.448 | 74.49 | 339 | $60,623 |
| Option 1 - Glass Coated | 1.594 | 61.54 | 308 | $401,594 |

Every one is a deck / floor / roof / ring job, or a rectangular tank whose dimensions were
typed into the wrong fields (the two Centrifuge rows are 10 ft tall in their own names and
carry H = 0.333, D = 3.077 — the old trim **passed both**).

### (b) `dq_price_residual_outlier` — the size-aware price rule

statsmodels is not installed in this environment, so the fit is `sklearn.linear_model.
LinearRegression` and the hat diagonal comes from `numpy.linalg.pinv`. No hand-rolled solve.

```
log(target_material) ~ log(area) + log(area)^2 + log(H) + log(D)
                       + C(Material) + C(Wage Type) + C(scope)
```

Fitted on **eligible rows only** — every DQ rule applied *except this one*, at row grain
(the same grain every other `dq_*` flag is evaluated on), so the billion-dollar rows and the
junk geometry are out of the fit and are still scored by it. Categorical levels with fewer
than 10 rows are pooled into `(Other)` so the design matrix stays conditioned.

```
fit n = 7,090     parameters (design rank, incl. intercept) = 12     R2 = 0.8076
residual sigma = 0.4012 log units  ->  1 sigma = x1.49 in price,  4 sigma = x4.98
flag: |studentized residual| > 4
```

The quadratic in `log(area)` is the whole point — it lets the model carry the U, so being a
very small or a very large tank is priced in rather than punished.

| | rows |
|---|---:|
| flagged over all 7,480 source rows | 72 |
| at the firmest-revision grain | **16** |

**Size-percentile distribution of the 16, against the old rule's top tail:**

| | n | min | p25 | median | p75 | max |
|---|---:|---:|---:|---:|---:|---:|
| **new residual rule** | 16 | 0.1 | 1.6 | **19.0** | 57.6 | 96.7 |
| old segment trim, top tail only | 30 | — | — | **1.0** | 2.7 | — |
| old segment trim, all | 64 | — | — | 25.1 | 58.1 | — |

The new rule spans the size distribution instead of clustering at the bottom of it.

**All 16, for you to eyeball** (`z` = studentized residual, `size %` = area percentile):

| Tank Name | H | D | area | material $ | Material | scope | z | size % |
|---|---:|---:|---:|---:|---|---|---:|---:|
| Option 1: Demo and Replacement of Deck, Deck Structure, and Rings 11, 12, 13 — Daylight only Build w/ crane | 14.84 | 71.30 | 3,325 | **$11,154,680,000** | CS | tank_quote | **+28.98** | 56.0 |
| 03CT & 04CT - Anaerobic Sludge Digestate Tanks - D702A & D702B | 58.59 | 65.36 | 12,031 | **$1,303,980,000** | CS | tank_quote | **+19.78** | 96.7 |
| Tank 1 | 0.22 | 30.77 | 21 | $1,051 | CS | materials_only | −9.41 | 0.1 |
| Embed Ring + 1 Ring | 0.33 | 9.23 | 10 | $2,310 | CS | tank_quote | −7.76 | 0.1 |
| Option 1 - Glass Coated | 1.59 | 61.54 | 308 | $401,594 | CS | tank_quote | +6.96 | 0.8 |
| Sludge Storage Tank | 27.98 | 21.54 | 1,893 | $989,443 | 304SS | materials_only | +6.01 | 26.2 |
| Tank 1 | 4.83 | 12.31 | 187 | $1,272 | CS | materials_only | −5.91 | 0.3 |
| Tank 1 | 10.05 | 30.77 | 972 | $4,315 | CS | materials_only | −4.66 | 9.2 |
| Tank 1 | 31.76 | 33.85 | 3,377 | $13,508 | CS | tank_quote | −4.58 | 57.6 |
| Tank 1 | 24.60 | 27.69 | 2,141 | $16,854 | 304SS | tank_quote | −4.45 | 31.2 |
| Tank 1 | 41.42 | 29.71 | 3,866 | $13,880 | CS | materials_only | −4.37 | 66.4 |
| Tank 1 | 14.94 | 20.05 | 941 | $4,375 | CS | tank_quote | −4.23 | 8.3 |
| Tank 1 | 4.83 | 30.77 | 467 | $3,733 | CS | materials_only | −4.22 | 1.8 |
| Dome Replacement | 5.05 | 68.33 | 1,085 | $225,784 | CS | tank_quote | +4.18 | 11.7 |
| Tank 2 | 31.76 | 33.85 | 3,377 | $16,443 | CS | tank_quote | −4.09 | 57.6 |
| Tank 1 | 31.76 | 33.85 | 3,377 | $16,443 | CS | tank_quote | −4.09 | 57.6 |

My read on these: the first two are data-entry errors by three and six orders of magnitude.
Both were already rejected by `dq_price_sane` on the $50M band *and* by the retired trim, so
the residual rule is a third independent confirmation rather than a new catch. Rows 3–7 are junk geometry or
scope. The nine `|z|` between 4.0 and 4.7 are the debatable band: a 3,377 sqft tank at
$13,508 of material is $4/sqft against a $24 median, so they look like scope that was priced
elsewhere rather than genuine prices — but they are the rows most worth a second opinion,
and `training_full.parquet` keeps them so you can test both ways.

### What moved, in total

| | rows |
|---|---:|
| at the firmest-revision grain | 4,504 |
| excluded under the OLD rule | 81 → training 4,423 |
| excluded under the NEW rule | **45** → training **4,459** |
| excluded then, kept now | **41** |
| kept then, excluded now | **5** |
| excluded by both | 40 |

The 41 released have a median size percentile of **39.1** and run up to the **99.5th**
(median material price $28,235, maximum $1,346,843). The five newly excluded are:

| Tank Name | H | D | area | material $ | caught by | z |
|---|---:|---:|---:|---:|---|---:|
| Centrifuge Mix Tank - Square Tank #1 (10'T x 10'W x 10'L) | 0.333 | 3.08 | 3 | $66,847 | geometry | −2.90 |
| Centrifuge Mix Tank - Rectangular Tank #2 (10'-6"T x 10'W x 14'-1½"L) | 0.333 | 3.08 | 3 | $91,080 | geometry | −1.92 |
| Sludge Storage Tank (304SS) | 27.98 | 21.54 | 1,893 | $989,443 | residual | +6.01 |
| Tank 1 | 10.05 | 30.77 | 972 | $4,315 | residual | −4.66 |
| Tank 1 | 14.94 | 20.05 | 941 | $4,375 | residual | −4.23 |

The two billion-dollar rows are not in this list because `dq_price_sane` already excluded
them under both rules — the residual rule finds them a second way, it does not rescue them.

`dq_price_sane` (the global $1K–$50M band) is untouched and still the backstop.

---

## 2. `training_full.parquet` — row exclusion is yours now

`exports/training_full.parquet` / `.csv`: **4,504 rows x 141 columns**. Same firmest-revision
grain, same targets, same leakage policy, same columns as `training.parquet` — the *only*
difference is the row filter. It is every row at the grain with valid geometry and a positive
target, i.e. everything before the DQ eligibility rule.

The geometry-based flags ride along as ordinary columns: `dq_has_geometry`,
`dq_has_capacity`, `dq_looks_nontank`, `dq_is_unfinished`, `dq_implausible_geometry`,
`dq_geo_resolved`. Target-derived flags (`dq_price_sane`, `dq_price_sane_segment`,
`dq_price_residual_outlier`, `price_resid_z`, `dq_has_positive_target`) stay in the leakage
list and are physically absent, per your instruction and the existing policy.

`ml_eligible` is present with role `reference` and reproduces the default exactly — verified,
not asserted:

```python
training == training_full[training_full.ml_eligible == 1]      # True, 4,459 rows, keys match
```

Use that when you want the filtered set and the flags in one frame. It is `reference`, never
`feature` — it is derived from the price rules.

**`training_full` − `training` = 45 rows.** A row can fail several rules, so the per-rule
counts overlap; the sole-reason column attributes each row to its single cause.

| excluding flag | rows failing | sole reason |
|---|---:|---:|
| `dq_price_sane == 0` | 2 | 0 |
| `dq_implausible_geometry == 1` | 13 | 10 |
| `dq_price_residual_outlier == 1` | 16 | 9 |
| `dq_looks_nontank == 1` | 6 | 5 |
| `dq_is_unfinished == 1` | 15 | 14 |
| *failed more than one rule* | — | 7 |
| **TOTAL excluded** | | **45** |

`exports/training.parquet` is unchanged in shape and contract — 141 columns instead of 139
(see §3 and §6), same grain, same name — so nothing downstream breaks.

**One decision left with you.** `revisions.parquet` is still filtered on `dq_has_geometry`,
`dq_looks_nontank` and `dq_is_unfinished` only, so it is **unchanged at 7,128 rows** and
still contains **27** rows that `dq_implausible_geometry` now flags. I did not gate it,
because that count is quoted in the previous reply and you may be building on it. The flag is
present in the export, so `revisions[revisions.dq_implausible_geometry == 0]` is one filter
away. Say the word and I will gate it in the pipeline.

---

## 3. `quote_balanced_weight` is exported

Moved from the leakage list to `reference`, and it is now in **all three** exports
(`training`, `training_full`, `revisions`). It was never leakage — it was in that list only
because that list was also doing duty as "not a feature", which was a mistake in the
contract, not in the column.

```
manifest role : reference
manifest note : SAMPLE WEIGHT (1 / tanks on the quote-revision). Pass it as sample_weight.
                It must NEVER enter the feature matrix.
```

Summary stats on `training.parquet` (n = 4,459):

| stat | value |
|---|---:|
| mean | 0.6869 |
| std | 0.3430 |
| min | 0.0345 (a 29-tank quote-revision) |
| 25% | 0.3333 |
| median | 1.0000 |
| 75% | 1.0000 |
| max | 1.0000 |
| **sum** | **3,062.95** |

That sum is your effective n: 4,459 tank rows carry the weight of 3,063 independent
quote-revisions. 2,311 rows are single-tank quotes (weight 1.0), 1,028 are weight 0.5.

The note is in three places: the new `note` column in `column_manifest.csv`, a
`sample_weight` block in `column_manifest.json`, and the `exports/` row of the root
`README.md`.

---

## 4. Verification

Everything below is printed output from the regenerated export.

**Row counts**

```
training.parquet        4,459 rows x 141 cols   (was 4,423 x 139)
training_full.parquet   4,504 rows x 141 cols   (new)
revisions.parquet       7,128 rows x 141 cols   (unchanged)
training_full - training = 45
```

**New geometry rule vs old segment trim, at the training grain**

```
rows at the grain                       4,504
OLD dq_price_sane_segment == 0             64      (30 of them top-tail, median size pct 1.0)
NEW dq_implausible_geometry == 1           13
NEW dq_price_residual_outlier == 1         16
NEW rules combined (union)                 26
  caught by both old and new               21
  flagged by the old trim, by neither new rule   43
  flagged by a new rule, not by the old trim      5
```

At the level of the *whole* eligibility rule — which is what actually moves rows, since
`dq_looks_nontank` and `dq_is_unfinished` also exclude some of those 43 — the movement is
**81 excluded before, 45 now: 41 rows released, 5 newly removed, net +36.** The 41 released
have a median size percentile of **39.1** (p25 2.2, max 99.5), a median material price of
$28,235 and a maximum of $1,346,843.

**The two large legitimate tanks — RETAINED**

```
Bioreactor Tank                    $1,011,218.23  H=65.508  D=24.616  area=5,066
    Tank Key 2410281-R0-Bioreactor Tank                                    ml_eligible=1
Anaerobic Digester - Membrane Roof $1,346,843.35  H=51.205  D=111.727 area=17,973
    Tank Key 2508082 - Materials ONLY-R6-Anaerobic Digester - Membrane Roof ml_eligible=1
```

Both are in `training.parquet`, looked up by name **and** price. For reference their
studentized residuals are **+3.85** and **+0.82** — the digester is unremarkable to the
model, and the bioreactor is elevated but well inside the 4σ line.

**"Embed Ring + 1 Ring" (H = 0.33) — STILL EXCLUDED**

```
rows in training.parquet      : 0
rows in training_full.parquet : 1     (visible, with its flags, as intended)

Tank Key   Sheet and Hardware Test - Sales-R0-Embed Ring + 1 Ring
H=0.333  D=9.231  area=9.66  material=$2,309.72
dq_implausible_geometry=1   dq_price_residual_outlier=1   price_resid_z=-7.758
ml_eligible=0
```

Both new rules fire on it independently.

**Leakage correlation scan** — max |corr| between any `role=feature` numeric column and
`log1p(target_material)`:

| export | numeric feature columns | max abs corr | top column | above 0.95 |
|---|---:|---:|---|---:|
| `training.parquet` | 71 | **0.858** | `material_area_intensity` | **0** |
| `training_full.parquet` | 71 | 0.829 | `material_area_intensity` | **0** |

Unchanged at 0.858, well under the 0.95 threshold. Runners-up on `training`:
`shell_area_sqft` 0.846, `d_x_h` 0.846, `total_area_sqft` 0.770 — all the legitimate area
signal, same as before.

**Columns whose role changed**

| column | before | after |
|---|---|---|
| `quote_balanced_weight` | leakage | **reference** |
| `dq_implausible_geometry` | *(new column)* | reference |
| `dq_price_residual_outlier` | *(new column)* | leakage |
| `price_resid_z` | *(new column)* | leakage |

That is the complete list: **one genuine reclassification and three new columns.**

| role | before | after |
|---|---:|---:|
| feature | 89 | **89** |
| target | 5 | 5 |
| identifier | 24 | 24 |
| reference | 21 | 23 |
| leakage | 44 | 45 |

**The feature count is unchanged at 89. No column entered or left the feature role.**

---

## 5. One open item I did not decide for you

`build/build_core.py` writes the Excel `Clean_Data` sheet, and its `ML Eligible` formula
still encodes the retired segment trim. The geometry rule is trivially expressible as a
formula; **`dq_price_residual_outlier` is not** — it is a fitted model over 7,090 rows.

So `verify.py --diff` now reports **Excel 4,423 vs pandas 4,459** training rows.

The exports are the modelling surface and they are correct. The workbook is the research and
audit surface and it carries the old rule until `build_core.py` is updated. Carrying a fitted
flag into Excel means either writing it as a **value** column sourced from `featured.pkl` —
which breaks the sheet's "every cell is a traceable formula" principle and creates a new
`prep.py -> build_core.py` dependency — or implementing only the geometry half, which would
leave `ML Eligible` deliberately different on the two sides. That is an architecture call on
the workbook, so I left it open rather than guessing. It is flagged in the root `README.md`
under **Rebuild**.

Nothing else in the workbook build is affected; I did not run it, so `dist/` is untouched.

---

## Summary

| # | Item | Status |
|---|---|---|
| 1 | Retire the P0-4 segment rate trim | **Done.** Out of `ml_eligible`, still computed, still leakage |
| 1a | `dq_implausible_geometry` (H<3 or D<3) | **Done.** 27 incremental catches, 13 at the grain, **zero** overlap with `dq_looks_nontank` |
| 1b | `dq_price_residual_outlier` (\|z\|>4) | **Done.** R² 0.808, σ 0.401; 16 at the grain, median size pct 19.0 vs the old rule's 1.0 |
| 2 | `training_full.parquet`, no pre-filtering | **Done.** 4,504 rows; 45-row gap fully attributed |
| 3 | `quote_balanced_weight` exported | **Done.** role `reference`, in all three exports, noted in manifest + README |
| 4 | Verification | **Done.** Both large tanks retained, Embed Ring excluded, max corr 0.858, feature count unchanged |
| 5 | Excel `ML Eligible` still on the old rule | **Open — owner call.** `verify.py --diff` reports 4,423 vs 4,459 |

Regenerate at any time:

```bash
cd build
python prep.py && python prep2.py && python export_training.py
```
