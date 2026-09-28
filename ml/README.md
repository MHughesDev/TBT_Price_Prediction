# `ml/` — research reproduction code

Reference implementation of the recommended recipe from `docs/ML_SYSTEM_DESIGN.md`.
**This is not the deployable service.** It exists so every number in the design doc can be
regenerated, and so the data layer can see exactly which columns the models consume.

```bash
python ml/recipe.py          # rolling-origin accuracy + interval coverage  <- quote these
python ml/recipe.py --cv     # cross-validated numbers (tuning protocol)    <- do NOT quote
```

| file | what it is |
|---|---|
| `data.py` | loads `exports/*.parquet`, defines the feature contract off `column_manifest.csv` |
| `physics.py` | API 650 / AWWA D100 steel-weight estimates. Used for **explanation**, not prediction — see design §6.6 |
| `aci.py` | adaptive conformal inference (Gibbs & Candès), plus scaled-Mondrian grade conditioning |
| `recipe.py` | the recipe end to end: offset → GBM → seed ensemble → level adjustment → interval |
| `tuned_params.json` | Optuna results per bucket, tuned on this exact recipe |

## Three things that will bite you

1. **An all-zero `init_score` is not the same as no `init_score`.** It disables LightGBM's
   `boost_from_average`; under an L1 objective every split gain is then identical, no split is ever
   taken, and the model emits a constant 0. `level_offset()` returns `None`, not zeros, for buckets
   with no regime.
2. **The offset carries a level, never a trend.** An earlier version included a time spline; serve
   time falls beyond its fitted range, so it extrapolated and diverged — material h2 MdAPE 0.276,
   bias −22%. Time belongs in the model features and the monthly level adjustment.
3. **Conformal calibration must use out-of-sample residuals.** Calibrating on in-sample fits
   collapses coverage from 0.80 to 0.12–0.57. `oof_residuals()` refits out-of-fold, grouped by job.

## Protocols

`GroupKFold` on `QuoteGroupID` is for tuning only — a job can hold 29 tanks sharing one pricing
decision. Rolling-origin on `Due Date` is what gets quoted, and it catches failures cross-validation
cannot: the extrapolating-offset bug above looked like a *win* under GroupKFold.
