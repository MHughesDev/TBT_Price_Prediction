# TBT Tank Price Prediction — V5 Data Foundation

Price-prediction service for TBT steel storage tanks. The service returns **five price
buckets** (material, fabrication, construction, insulation material, insulation
construction). Freight, tax and the assembled total stay in the estimating software.

## Layout

| Path | Contents |
|---|---|
| `build/` | The build pipeline and its source data. **Run every script with `build/` as the working directory** — all paths are bare relative filenames. |
| `build/archive.csv` | Source data: 7,480 rows x 42 columns. The only data-entry point. |
| `dist/` | Deliverable workbooks. `v5.4` is current; `v5` is the originally shipped baseline, kept for comparison. |
| `exports/` | Leakage-free modelling exports and the column manifest. Regenerate with `python export_training.py`. `training.parquet` is the filtered default; `training_full.parquet` is the same grain unfiltered, so row exclusion stays a modelling decision. `quote_balanced_weight` is present in both with role `reference` — **it is a sample weight, pass it as `sample_weight`; it must never enter the feature matrix.** |
| `docs/` | Handoff, build procedure, and design notes. |

## Read first

1. `docs/HANDOFF.md` — build procedure, gotchas, and the P0/P1/P2 backlog. **Read before changing anything.**
2. `docs/BUILD_README.md` — the pipeline in detail.
3. `docs/Tank Price Prediction — Purpose & Service Design.md` — what the service is for.
4. `docs/OPEN_QUESTIONS_FOR_THE_BUSINESS.md` — the three decisions only estimating and
   finance can make, with the evidence for each. **Q3 will cause a visible defect if it
   ships unanswered.**

## What changed after v5

| Item | Change |
|---|---|
| P0-2 | Geographic normalization. 219-entry `Country|State` crosswalk in `Ref_Lists`; 8 new `Clean_Data` columns; 99.1% of rows resolve to an ISO region; 37 rows had a wrong country corrected. |
| P0-4 | Segment-aware outlier bounds. `$/shell-sqft` ranked within its own material x scope_class segment; rejects 178 rows against the global band's 33. Training rows 4,481 -> 4,423. |
| P1-1 | `Dashboard_Geographic` — pipeline and win rate by country and US state, domestic vs international, freight % by distance band. |
| P1-7 | `Rate_Baseline` — `$/shell-sqft` by material x use type x year x scope class, plus per-bucket rates. The non-ML fallback estimator and the benchmark any model must beat. |
| Bug | `prep.py` and `build_core.py` held two different junk-keyword lists; 18 test rows leaked past the pandas filter. Now one canonical list. |
| Bug | `Due Date` had no explicit date format and only rendered correctly because LibreOffice inferred one during recalc. |
| Bug | `roof_slope_ratio` read one character before `:12`, so a `12:12` pitch would parse as `2:12`. No such value exists today. |
| Debt | The ML row bound in `build_docs.py` is now derived from the sheet instead of hardcoded. |
| Money | Reconciliation corrected. The workbook had encoded `Total Price = Proposal + Freight + Tax`, which double-counts tax and held on only 61% of rows. Verified identities: `Proposal Total = buckets + Tax` and `Total Price = buckets + Freight`, both 4,423/4,423 at max relative error 7.1e-07. New `Ref Grand Total` = buckets + freight + tax. |
| P1-2 | `Dashboard_Revisions` — revisions by outcome, price movement first-to-firmest, rework concentration by manager. |
| P1-3 | `Dashboard_Trend` — monthly pipeline and blended $/shell-sqft, calendar-month seasonality, quarterly by year. |
| P1-4 | `Dashboard_DataQuality` — exclusion waterfall (reconciles both ways) and a pass rate per flag trended by year. |
| P1-5 | Every Clean_Data and ML row bound now derived from the source row count. No literal row numbers left in the build scripts. |
| P1-6 | Company/customer canonicalization (937→933, 1,297→1,294); `Name Has Option` / `Name Partial Scope` parsed from the tank name; negative capacity treated as missing on both sides. |
| Bug | `min_miles` was `MIN(Miles TBT, Miles GT)` with a zero read as a real distance. Miles GT is a literal 0 on 1,853 source rows and rising (1.4% of 2024, 51.2% of 2026), so 1,192 training rows reported distance 0 and 1,170 were banded "<100 mi" against a true median of 800 miles. Now the minimum over positive distances, with an Unknown band. |
| Export | `export_training.py` emits `training.parquet` (4,459 tanks, firmest revision), `training_full.parquet` (4,504 — same grain, before the DQ filter) and `revisions.parquet` (7,128 rows, every priced revision — +61.2% coverage for monthly recalibration), with 45 leakage columns physically removed and a `column_manifest` marking every field feature / target / identifier / reference / leakage. |
| P0-4R | **The P0-4 segment trim is retired as a gate.** It ranked raw `$/shell-sqft` inside a `Material x scope_class` segment with no size term, and `$/sqft` is U-shaped in size ($32.55 at 866 sqft, $23.68 at 3,377, $37.33 at 9,149), so it deleted the extremes of the *size* distribution — 30 of its 64 rejections were top-tail, at a median size percentile of 1.0. Replaced by `dq_implausible_geometry` (Height < 3 ft OR Diameter < 3 ft — pure geometry, no price) and `dq_price_residual_outlier` (\|studentized residual\| > 4 from an OLS of `log(target_material)` on `log(area)`, `log(area)^2`, `log(H)`, `log(D)` and dummies for Material, Wage Type and scope; R² 0.808). `dq_price_sane_segment` is still computed and still published as research output, and stays leakage. Training rows 4,423 -> 4,459. See `docs/REPLY_TO_ML_LEAD_2.md`. |

## Rebuild

```bash
cd build
python prep.py && python prep2.py            # pandas ground truth -> featured3.pkl
python build_core.py
python recalc_excel.py v5_core.xlsx 1200     # REQUIRED before build_ml.py
python build_ml.py
python build_dash.py
python build_docs.py
python recalc_excel.py TBT_Tank_Quote_Analytics_v5.xlsx 1500
python verify.py TBT_Tank_Quote_Analytics_v5.xlsx
python export_training.py                    # -> ../exports/
```

Expected at v5.4: **23 sheets, 1,532,827 formulas, 0 errors, 24 charts, 4,423 training rows**.
A full clean run takes about 100 seconds.

> **Open after P0-4R.** `prep.py` no longer gates on `dq_price_sane_segment`; `build_core.py`
> still does, and `dq_price_residual_outlier` cannot be written as a Clean_Data formula. So
> `verify.py --diff` now reports **Excel 4,423 vs pandas 4,459** training rows. The exports
> are the modelling surface and are correct; the workbook carries the old rule until
> `build_core.py` is updated. Deciding how the Excel side should carry a fitted-model flag —
> a value column from `featured.pkl`, or the geometry half only — is an owner call, so it is
> left open rather than guessed. See `docs/REPLY_TO_ML_LEAD_2.md` §5.

## Recalculation engine

`recalc.py` needs LibreOffice, which is not installed on this machine. `recalc_excel.py`
is a drop-in replacement driving Microsoft Excel over COM: same JSON output, same
exit-code contract, and about 17 seconds instead of four minutes on the full workbook.

Excel evaluates XLOOKUP/FILTER/UNIQUE/SORT happily; LibreOffice, which produced the
original V5, cannot and bakes `#NAME?` into the file. `verify.py --lint` catches that
statically, so run it alongside every recalc.

## Verification

`verify.py` runs three checks and exits non-zero if any fails:

1. **audit** - formula count, error cells, formulas missing cached values (reads the zip
   directly; needs no Excel).
2. **lint** - functions the LibreOffice engine cannot evaluate, and post-2007 functions
   missing their `_xlfn.` prefix.
3. **diff** - `ML_Tank_Training` against the pandas ground truth, column by column.

A green recalc proves formulas evaluate, not that they are correct. The diff is what
proves correctness, and it records an expected row count for each known Excel/pandas
divergence so a real regression cannot hide behind one.
