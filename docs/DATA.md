# The data

`data/archive.csv` is the quote export: 7,480 rows, 42 columns. It is one row per tank per quote
revision. `prepare.py` turns it into `data/tanks.parquet`.

## Rows: tanks, quotes and jobs

| Term | Meaning |
|---|---|
| quote | A `Quote #`, such as `1707012` or `1707012-R2` or `1707012 CO#1`. |
| job | The first 7 digits of the quote number. One job can hold many tanks (up to 29). |
| revision | Re-pricing of the same job. It can come from `Revision #` or a suffix like `-R2`. |
| scope variant | A suffix like `CO#1`, `Option`, `Materials Only`. This is different work, so it stays a separate row. |
| firmest | The highest revision of a job (or of a scope variant). This is the price the customer saw last. |

We score on **one row per tank at its firmest revision** (`is_firmest == 1`), which gives
4,459 eligible tanks on 3,055 jobs. Older revisions are real prices too, and methods may train on them.

## Money

- Every price is **per tank**. Never divide by `Quantity`.
- Prices are text in the CSV (`"$5,172.08"`). `prepare.py` parses them.
- A price of $1 or less (usually $0.01) means "in scope, not priced yet". It is treated as $0.
- The two totals in the CSV are **not** the grand total. Both identities hold on every priced row:

| Column | Equals |
|---|---|
| `Proposal Total` | buckets + tax |
| `Total Price` | buckets + freight |
| grand total (in no column) | buckets + freight + tax |

- Margin, contingency and commission are pricing policy applied on top. They are not model inputs.

## Scope

Whether a tank includes erection (construction) or insulation is decided by the estimator,
not predicted. `erection_in_scope` and `insulation_selected` are inputs. An out-of-scope bucket is $0.

## Which rows are eligible

A row is dropped from training and scoring if any rule below fires. It is kept if none does.

| Rule | Why |
|---|---|
| Proposal Total outside $1K–$50M | Not a real tank price |
| Height or diameter < 3 ft | Deck, floor or roof repair jobs entered as tanks (placeholder heights like 0.22 ft) |
| Name contains a part/test word | Parts, tests, demos |
| Status is Unfinished or Bid Review | Not a finished price |
| Material price > 4 standard errors from a size-aware regression | Typos and one-offs |

The size term matters. $/sqft is U-shaped in tank size: small tanks carry fixed costs, and
big tanks need thick plate. A rule without size deletes the smallest and largest real tanks.

## Gotchas

- `Due Date` is the only date and the time index. The quote number encodes when the *job*
  opened, sometimes years earlier. Don't use it for time.
- `Wage Type` blank usually means export or materials only, not missing data.
- `Miles to Site (From GT)` is often 0, meaning "never computed". Use `min_miles`, which ignores zeros.
- `Country` is wrong on a few rows. `geo.py` fixes them using the city.
- Use `total_area_sqft` (shell + floor + flat roof) as the size unit. The rate table and the offset in `methods/lgbm.py` both depend on it.
