# Agent Handoff — TBT Tank Price Prediction, V5 Data Foundation

**To:** Claude Code (next agent)
**From:** the session that built `TBT_Tank_Quote_Analytics_v5.xlsx`
**Status:** Data engineering + reporting layer shipped and verified. ML **not** trained (deliberate).
**Owner:** Mason (masonhughesmwh@gmail.com) · Project "TBT AI"

Read this whole file before touching anything. Section 3 (Gotchas) will save you an hour.

---

## 1. What exists

**Goal:** a web app collects tank + project specs → a prediction service returns five price buckets → the
estimator computes freight and tax and sums a total.

**Targets (predicted):** Material · Fabrication · Construction · Insulation Material · Insulation Construction
**Not predicted:** Freight, Tax (computed deterministically).

**Deliverable:** `TBT_Tank_Quote_Analytics_v5.xlsx` — 18 sheets, 1,274,706 live formulas, 0 errors, 10/10 validation PASS, ~20 MB.

| Sheet | Grain | Rows | Role |
|---|---|---|---|
| `Raw_Import` | source line | 7,480 | Verbatim CSV. **Only** data-entry point. Values, not formulas. |
| `Clean_Data` | source line | 7,480 | Every cell a formula off Raw_Import. Parsing, keys, revision/outcome, 13 DQ flags. |
| `Fact_Quote` | job | 3,171 | Job-grain rollup for exec reporting. |
| `ML_Tank_Training` | tank | 4,481 | **The training table.** 126 cols. Deduped, firmest revision. |
| `Dashboard_*` (4) | — | — | Executive, Sales, Pricing, WinLoss. 12 charts. |
| `Data_Research`, `ML_*` (3), `Audit_V4_to_V5`, `Data_Quality`, `Validation`, `Cleaning_Rules`, `README`, `Ref_Lists` | — | — | Docs + analysis. |

**Headline numbers (verified):** $1.398 B pipeline · 3,171 jobs · 4,634 tanks · 60.3% win rate · $441 K avg deal.

**Build scripts** (in the session workspace, re-create if absent):
`prep.py` → `prep2.py` (pandas ground truth) · `build_core.py` (Raw_Import + Clean_Data) ·
`build_ml.py` (ML_Tank_Training) · `build_dash.py` (Fact_Quote + dashboards) · `build_docs.py` (docs + assemble).

---

## 2. How to rebuild and verify

```bash
python3 build_core.py                                  # -> v5_core.xlsx
python3 <skill>/scripts/recalc.py v5_core.xlsx 1200    # MUST run before the next step
python3 build_ml.py                                    # -> v5_ml.xlsx  (reads recalculated values)
python3 build_dash.py                                  # -> v5_dash.xlsx
python3 build_docs.py                                  # -> TBT_Tank_Quote_Analytics_v5.xlsx
python3 <skill>/scripts/recalc.py TBT_Tank_Quote_Analytics_v5.xlsx 1500
```
Full recalc ≈ 4 min. `recalc.py` lives in the `xlsx` skill's `scripts/`.

**Verification is not optional.** A green recalc proves formulas *evaluate*, not that they're *right*.
Always diff Excel output against the pandas ground truth in `prep2.py`:
```python
xl = pd.read_excel('...xlsx', sheet_name='ML_Tank_Training', header=1)
gt = pd.read_pickle('featured3.pkl')   # produced by prep2.py
# compare column by column; every flag/feature previously matched with 0 mismatches
```

---

## 3. Gotchas that already bit me — do not rediscover these

1. **Pipeline order.** `build_ml.py` reads *computed values* from `v5_core.xlsx`. If you skip the
   intermediate recalc, it silently produces a header-only ML sheet with zero training rows.
2. **Prices carry `$` and commas** (`"$5,172.08"`). Stripping only commas yields null and silently
   zeroes every price. This is the bug that broke v4.
3. **Excel parses a trailing minus as negative.** `VALUE("3-")` → `-3`. Bit the suffix-revision parser.
   Use an explicit digit test, not `IFERROR(VALUE(...))` chains.
4. **No XLOOKUP / XMATCH / FILTER / UNIQUE / SORT.** The LibreOffice recalc engine can't evaluate them
   and bakes `#NAME?` into the delivered file. Use INDEX/MATCH. `_xlfn.MAXIFS` works *with* the prefix.
   (Mason asked for XLOOKUP — this is why it isn't there. Swap only if you drop validation.)
5. **Text cells starting with `=` become formulas.** Rephrase prose like "= sum of buckets".
6. **Hardcoded row bounds.** Clean_Data spans rows 2–7481; ML rows 3–4483. Adding source rows requires
   regenerating, not just pasting. See P1-5.
7. **`data_only=True` is destructive if you save** — it drops every formula permanently.

---

## 4. Backlog — what I wanted to finish and didn't

### P0 — correctness risks, do these first

**P0-1. Resolve the quantity price basis.** *Unresolved and it affects every target.*
Is a bucket price per tank, or per line (× quantity)? Evidence leans **per-unit**: blended $/shell-sqft is
roughly flat across quantity (qty1 $76.76, qty2 $87.86, qty3 $71.28, qty4 $80.88) — per-line pricing would
show ~2× at qty 2. Not conclusive (n=439/98/49). The other agent's CSV independently flagged this as
`quantity_price_basis_unconfirmed` on 389 rows. **Ask the estimating team.** If per-line, every target must
be divided by quantity before training. `ML_Tank_Training` already carries `Quantity` and `qty_x_shell_area`.

**P0-2. Normalize the `State` field — geographic reporting is currently wrong.**
207 distinct values mixing US abbreviations (`CA`, `TX`), Mexican state codes (`COAH`, `JAL`, `QRO`, `TAMPS`,
`GTO`), **cities** (`Lima`, `Santiago`), and **countries** (`Argentina`, `Mexico`). Build a crosswalk in
`Ref_Lists` (raw → ISO region + country) and add `State Normalized` to Clean_Data via INDEX/MATCH.
Until this lands, do not build a geographic dashboard (see P1-1).

**P0-3. Confirm international pricing is USD.** Mexico blends $36.91/shell-sqft vs US $94.23. **Most of this
is scope, not currency** — 96.6% of MX tanks are materials-only (no erection) vs 7.1% US. But a ~35% residual
gap remains within like-for-like `materials_only` ($36.54 MX vs $56.47 US). Confirm with finance whether any
rows are booked in local currency. If so, add an FX normalization column; mixed units would corrupt training.

**P0-4. Segment-aware outlier bounds.** `DQ Price Sane` uses one global band ($1K–$50M) that I chose. A $2M
price is normal for a 1M-gal tank and absurd for a 5-ft one. Replace with a residual rule: flag rows whose
$/shell-sqft sits outside e.g. 1.5–99th percentile *within* material × scope_class. Keep the global band as a
backstop.

### P1 — reporting and cleaning I planned but ran out of runway for

**P1-1. Geographic dashboard.** v4 had one; V5 does not. Blocked on P0-2. Want: pipeline and win rate by
country and normalized region, plus domestic vs international split and freight % by distance band.

**P1-2. Revision / rework dashboard.** All the data is there and unused: `Revision Count`, `Effective
Revision`, `Quote Variant Type`, first-vs-firmest price. Metrics worth showing: average revisions to win vs to
lose (won jobs are revised **3.58×** vs **1.72×** for lost — a real finding already surfaced in `Data_Research`),
quote growth % from first to firmest revision, and rework cost concentration by manager.

**P1-3. Monthly/quarterly trend.** Everything is annual right now. `Due Date` supports month granularity;
`months_since_2020` already exists. Add seasonality to the pricing dashboard.

**P1-4. Data-quality scorecard dashboard.** `Data_Quality` is a table with no charts. Turn the 13 DQ flags
into a trending scorecard so quality is monitored, not just measured once.

**P1-5. Define Excel Tables (ListObjects) + a documented extend procedure.** No sheet is a named table, which
blocks PivotTables and makes growth painful. Either define tables with dynamic ranges, or write an explicit
"adding new data" runbook in the README. Right now formulas are pinned to fixed rows (gotcha 6).

**P1-6. Finish the cleaning pass.**
- Company/Customer canonicalization — v4 had `fnCanonicalize`; V5 dropped it. Impact is genuinely small here
  (only 4 collapsible company names, 2 customers out of 937/1,296) so it's low priority, but the cardinality
  itself matters for ML encoding.
- `Tank Name` is very messy (`"Option 1: Demo and Replacement of Deck, Deck Structure, and Rings 11, 12, 13..."`).
  Parse out option/scope markers into structured flags.
- Group `Deck Style` (21 values) and `Floor Style` (10) into families beyond the current binary flags.
- Decide what to do about the 44 negative-capacity rows — currently flagged and rejected, never corrected.
- `Sales Rep` is 76% null and `Project Name` 81% null in training rows. Probably drop both; confirm first.
- 813 rows have zero freight on sites >100 mi. Determine whether that's FOB/customer-pickup (legitimate) or
  missing data. `DQ Freight Present` flags them.

**P1-7. Segment baseline rate table.** Build `$/shell-sqft` by material × use_type × year × scope_class as a
lookup sheet. Two uses: a non-ML fallback estimator, and the benchmark every ML model must beat. This is the
single highest-value analysis item left — the whole dataset says *price ≈ rate × area*.

### P2 — ML prep (still no training)

**P2-1. Materialize the train/test split.** I specified it but never wrote it: add `split_assignment` to
ML_Tank_Training — **group by `Quote Group ID`** (never split a job across train/test) plus a time holdout on
`Due Year` = latest. Both columns already exist.
**P2-2.** Export a clean `training.csv` / `.parquet` so modeling doesn't depend on a 20 MB workbook.
**P2-3.** Quantify collinearity properly. I asserted >0.95 among size features but never computed the matrix.
**P2-4.** Decide categorical encoding for `Use Type`, `Deck Style`, `Floor Style`, and the high-cardinality
`Company`/`Customer` (937/1,296 levels — target-encode or drop).
**P2-5.** Margin/contingency question (see §5).

---

## 5. Open questions that need a human, not an agent

1. **Quantity basis** — per tank or per line? (P0-1. Blocks target definition.)
2. **Currency** on international quotes. (P0-3.)
3. **Are `Margin (%)` / `Contingency (%)` model inputs or post-prediction business overrides?** Both are in the
   table so either is testable, but the answer changes the model's job. Note the buckets are already
   margin-loaded.
4. **Change orders (`CO#`) — same job or separate work?** I treat them as *separate rows, same group*. If the
   business considers a CO part of the parent job, the dedup rule in `build_core.py` needs revisiting.
5. **Proposal Total doesn't equal the bucket sum on 39% of rows** — a median **+4.7%** uplift, contingency-like
   in magnitude but *not* matching the `Contingency (%)` column (only 15% agree within 0.5pp). **Mason's stated
   total formula — buckets + freight + tax — is therefore incomplete.** Find out what the uplift is before the
   service ships, or totals will be systematically low.

---

## 6. Locked decisions — don't silently reverse these

- **Grain:** one row per tank, at the firmest revision of its **job**. Revision de-dup removes duplicates;
  the tank is the prediction unit (a quote can hold 29 tanks with different specs).
- **Job identity:** quote numbers carry suffixes (`2306041 - As Sold`, `2212046-R2`). `Quote Group ID` (first 7
  digits) is the job. Revision/status variants collapse to the firmest; scope variants (`CO#`, `Option`,
  `Materials ONLY`) stay as separate rows in the same group. This fixed 77 duplicate training rows.
- **Model log(1+price)**, invert on output. Raw skew 4.9–11.5 → ~−0.5 to 0.7 logged.
- **Two-stage for Construction + both Insulation buckets.** Gates are `inc_construction` / `inc_insul_*`
  (stage-1 labels, already in the sheet). Construction is zero on 34.6% of rows, driven by wage type.
- **`rate_*` and `shop_cost` columns are LEAKAGE** (derived from price). Research only. Banded maroon.
- **All outcomes train** (Won/Lost/Open); outcome is not a price feature. Budget rows kept behind `is_firm_bid`.
- **Traceability:** every computed cell is a formula chaining back to Raw_Import. Keep it that way — don't
  paste values.
