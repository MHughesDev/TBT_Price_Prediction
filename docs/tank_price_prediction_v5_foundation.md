# Tank Price Prediction — V5 Data Foundation (handoff)

> **Full agent handoff with the prioritized backlog lives in `HANDOFF.md`** (delivered to Mason in chat).
> This doc is the durable summary; HANDOFF.md is the work order.

## Status
Data engineering + reporting **complete and verified**. No ML trained (deliberate).
Deliverable: `TBT_Tank_Quote_Analytics_v5.xlsx` — 18 sheets, 1,274,706 live formulas, 0 errors, 10/10 validation PASS, ~20MB.

Headline: **$1.398B pipeline · 3,171 jobs · 4,634 tanks · 60.3% win rate · $441K avg deal.**

## Source data
`archive.08-26-26(1).csv` — 7,480 rows, 3,225 raw quote strings, 42 columns. Superseded the 1,000-row sample v4 used.
Prices are text with `$` and commas (`"$5,172.08"`) — strip `$`, `,`, `%` before VALUE/float. v4 stripped only commas and silently zeroed every price.

## The ML problem
- **Grain: one row per TANK at the firmest revision of its JOB.** 4,481 training rows.
- **5 targets:** Material, Fabrication, Construction, Insulation Material, Insulation Construction.
- **Not predicted:** Freight, Tax (computed deterministically).

## Locked decisions
- **Job identity:** quote numbers carry suffixes (`2306041 - As Sold`, `2212046-R2`, `2302133 R1`). `Quote Group ID` = first 7 digits = the job. Revision/status variants collapse to the firmest price; scope variants (`CO#`, `Option`, `Materials ONLY`) stay separate rows in the same group. **This fixed 77 duplicate training rows** — and "As Sold" is literally the firmest price (rev 5 $519,770 vs bare rev 4 $620,281 on identical specs).
- Model `log(1+price)`, invert on output. Raw skew 4.9–11.5 → ~−0.5 to 0.7 logged.
- **Two-stage** for Construction + both Insulation buckets. Gates `inc_construction` / `inc_insul_*` are in the sheet as stage-1 labels.
- **Validation split: group by `Quote Group ID` + time holdout on Due Year.** Never split a job.
- All outcomes train; outcome is not a price feature. Budget kept behind `is_firm_bid`.
- `rate_*` and `shop_cost` are **LEAKAGE** (derived from price) — research only.

## Strongest findings
- **Price ≈ rate × area.** `total_area_sqft` corr 0.86 with log material price. Most useful structural fact in the dataset.
- **Grade is a multiplier:** blended material $/shell-sqft CS $32.21 → 304SS $65.17 (2.0x) → 316SS $101.08 (3.1x).
- **Labour regime moves construction ~1.75x:** non-union $27.48/sqft, prevailing $48.81, union $47.79.
- **~14%/yr escalation:** $30.94 (2024) → $33.58 (2025) → $40.05 (2026). Time feature is mandatory.
- **Seismic does NOT move the construction rate** (flat across all Ss bands) — put seismic interactions on the material model.
- **35% of tanks are materials-only** (no erection scope).
- Won jobs are revised **3.58×** vs **1.72×** for lost; won jobs carry *lower* margin (18.1 vs 19.3).

## Critical open questions (need a human)
1. **Quantity basis** — price per tank or per line? Evidence leans per-unit (blended $/sqft flat across qty) but unconfirmed. Changes every target.
2. **Currency** on international rows. Mexico blends $36.91/sqft vs US $94.23 — **96.6% explained by scope** (MX is materials-only) but a ~35% residual remains within like-for-like scope.
3. **Margin/Contingency** — model inputs or post-prediction overrides?
4. **Proposal Total ≠ bucket sum on 39% of rows** (median **+4.7%** uplift, not matching the Contingency column). **The stated total formula "buckets + freight + tax" is incomplete** — resolve before the service ships.

## v4 bugs fixed (full list on the Audit_V4_to_V5 sheet)
Critical: `$`-prefixed prices silently zeroed; no outlier guard (a **$1.27 trillion** row, plus $556bn and $21bn).
High: non-tank line items priced as tanks (elbows, nozzles, part tests); **Tank Key not unique** (v4's own check #7 fails at scale); 323 zero-height rows.
Medium: revision count assumed contiguous revisions (67 quotes have gaps); Bid Review/Unfinished unmapped; 44 negative capacities.

## Known gotchas for the next agent
- **Pipeline order:** `build_ml.py` reads *computed* values — recalc `v5_core.xlsx` first or you get an empty ML sheet.
- **Excel parses a trailing minus as negative:** `VALUE("3-")` → `-3`.
- **No XLOOKUP/XMATCH/FILTER/UNIQUE/SORT** — the recalc engine bakes `#NAME?`. Use INDEX/MATCH; `_xlfn.MAXIFS` needs the prefix.
- Text cells starting with `=` become formulas.
- Row bounds are hardcoded (Clean_Data 2–7481, ML 3–4483).

## Top backlog items
P0: resolve quantity basis · normalize the `State` field (207 values mixing US codes, Mexican codes, cities and countries — geographic reporting is wrong until fixed) · confirm currency · segment-aware outlier bounds.
P1: geographic + revision/rework dashboards · monthly trends · DQ scorecard · Excel Tables & extend runbook · **segment baseline rate table ($/sqft by material × use type × year)** — highest-value analysis left.
P2: materialize the train/test split · export training.csv · collinearity matrix · categorical encoding.