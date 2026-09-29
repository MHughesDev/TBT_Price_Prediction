# Lessons already paid for

Each of these was learned the hard way. Results live in `results/SCOREBOARD.md`, not here.

## Modelling

| Lesson | Detail |
|---|---|
| Test on the future, never on shuffled folds. | Cross-validation grouped by job once made a broken model look like a win. Only `backtest.py` numbers count. |
| `init_score` of all zeros is not "no offset". | It switches off LightGBM's starting average. With an L1 objective the model then learns nothing and predicts a constant. Pass `None`. |
| The offset must be a level, never a trend. | A time trend in the offset extrapolated past the training dates: material bias −22% two quarters out. |
| Summing medians under-states the book. | The median is right for one tank. Added up over many tanks, it runs about 7% low. A mean model (`lgbm_gamma`) targets the sum. |
| Value weighting needs the eligibility filter. | With price-weighted samples, one corrupt $1.19 trillion row would have outweighed millions of real ones. `methods/lgbm.py` asserts on it. |
| Scope is an input, not a prediction. | Guessing erection/insulation scope is 93–95% right, and a miss costs ~$88K. That is far worse than normal pricing error. |
| One pooled model beats one model per tank type. | There is not enough data per type yet. |
| Prices move in steps, not smoothly. | Material rose ~24% across 2026 Q1–Q3. Insulation field labour fell ~25% in 2025 Q4. Expect a model to lag a step change for about two quarters. |
| The human baseline is not zero error. | Two sales managers pricing the same spec in the same quarter differ by a median of 11.4%. |

## Open questions for the business

| # | Question | Who |
|---|---|---|
| 1 | Can we get a monthly steel price index? It is the only way to see a price step before our own quotes show it. | Procurement |
| 2 | Will the quote form collect "erection in scope" and "insulation selected" as inputs? | Product |
| 3 | Are all prices in USD? Mexican tanks price ~34% below US ones with the same scope. | Finance |
| 4 | What exactly is `Due Date`? Is there a created or sent timestamp? | Estimating / IT |
| 5 | Is a blank `Wage Type` a real choice in the estimating software? | Estimating |
| 6 | Can more spec fields be exported (plate thickness, nozzles, coating, design loads)? | Estimating / IT |
| 7 | Are historical prices ever changed after the fact? | Estimating / IT |
| 8 | Is a change order the same job or new work? | Estimating |
| 9 | 813 sites more than 100 miles away have $0 freight. Customer pickup, or missing data? | Estimating |
