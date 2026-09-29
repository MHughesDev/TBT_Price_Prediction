# TBT Tank Price Prediction

Predict the price of a TBT steel storage tank from its spec, and find out, in dollars, which
way of predicting it is best.

A tank's price has five parts, called **buckets**: material, fabrication, construction,
insulation material and insulation construction. We predict each one. Freight and tax are
calculated exactly by the estimating software, so we don't predict them.

## Run it

```bash
pip install -r requirements.txt
python prepare.py          # data/archive.csv -> data/tanks.parquet        (~5 s)
python backtest.py all     # replay history for every method              (~15 min)
python score.py            # -> results/SCOREBOARD.md
```

## How a winner is decided

`backtest.py` replays the last six quarters. For each quarter, every method trains only on
quotes due before it and then predicts that quarter's tanks. Each tank is predicted exactly
once, and every method predicts the same tanks.

`score.py` measures each tank's error in dollars: |predicted − actual| for the five buckets
added up. **The method with the lowest total dollar error leads.** It then checks whether the
lead is real by resampling whole jobs 2,000 times. A method "wins" only if the whole 95%
interval of dollars saved per tank is above $0. Otherwise the scoreboard says "no real
difference".

Current standings: [`results/SCOREBOARD.md`](results/SCOREBOARD.md).

## Add a method

1. Copy a file in `methods/`, for example `methods/lgbm.py`, and change it. It must define
   `fit_predict(train, test)` and return predicted dollars, one column per bucket.
2. Add one line to `methods/__init__.py`.
3. Run `python backtest.py <name>`, then `python score.py`.

`train` holds every eligible priced tank revision due before the test quarter. Use
`is_firmest == 1` for the final price of each tank; older revisions are also allowed. Scope
is handled for you: a bucket that is not in scope is set to $0.

## Files

| File | What it does |
|---|---|
| `data/archive.csv` | The raw quote export. The only input. |
| `prepare.py` | Cleans it: jobs, features, prices, data-quality rules. |
| `geo.py`, `physics.py` | Location cleanup; steel-weight estimates used as features. |
| `methods/` | The competing methods, one file each. |
| `backtest.py`, `score.py` | The competition and the scoreboard. |
| `docs/DATA.md` | What the data means and how money adds up. **Read before changing prepare.py.** |
| `docs/LESSONS.md` | Mistakes already made once, and open questions for the business. |

The old Excel workbook, prediction service and design notes are in git history, at commit `364a578`.
