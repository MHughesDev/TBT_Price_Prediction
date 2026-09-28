# Claude Code — Initializer Prompt

Paste everything below the line into a fresh Claude Code session, in a folder containing
`HANDOFF.md`, `TBT_Tank_Quote_Analytics_v5.xlsx`, `archive.08-26-26(1).csv`, and the build
scripts (`prep.py`, `prep2.py`, `build_core.py`, `build_ml.py`, `build_dash.py`, `build_docs.py`).

---

You are picking up a data-engineering project mid-stream. A previous agent built and verified the
foundation; your job is to finish the backlog it left.

**Read `HANDOFF.md` in this folder before doing anything else.** It contains the build procedure, seven
gotchas that already cost real time, and a prioritized P0/P1/P2 backlog. Do not start work until you have
read it. Then open `TBT_Tank_Quote_Analytics_v5.xlsx` and look at the `README`, `Audit_V4_to_V5`, and
`ML_Modeling_Plan` sheets so you understand the decisions already locked in.

## What this project is

TBT quotes steel storage tanks. We are building a price-prediction service: a web app collects tank and
project specs, the service returns **five price buckets** (material, fabrication, construction, insulation
material, insulation construction), and the estimating software computes freight and tax separately and
assembles the total. **The service returns only the five predicted buckets — never freight, never tax,
never a total.** Freight and tax are deterministic and stay in the estimating software.

The deliverable so far is a single workbook: 18 sheets, ~1.27M live Excel formulas, 0 errors, 10/10
validation checks passing. `ML_Tank_Training` is the training table — 4,481 unique tanks, one row per tank
at the firmest revision of its job, 126 columns.

## Non-negotiable constraints

1. **Every computed cell stays a live formula** traceable back to `Raw_Import`. Never paste values over
   formulas. Traceability is an explicit requirement from the client.
2. **Formulas are written compact, no spaces** (`=PI()*W3*X3`, not `= PI() * W3 * X3`).
3. **Never use XLOOKUP, XMATCH, FILTER, UNIQUE, SORT, or SEQUENCE.** The LibreOffice recalc engine cannot
   evaluate them and bakes `#NAME?` into the delivered file. Use INDEX/MATCH. `_xlfn.MAXIFS` works but only
   with the prefix.
4. **Never reverse a locked decision** in §6 of `HANDOFF.md` without saying so explicitly and explaining why.
5. **Never ship a workbook that `recalc.py` reports errors on.**

## Working method — this is not optional

A green recalc proves formulas *evaluate*, not that they are *correct*. After every change:

1. Rebuild in order: `build_core.py` → **recalc** → `build_ml.py` → `build_dash.py` → `build_docs.py` → **recalc**.
   Skipping the intermediate recalc silently produces an empty ML sheet. This has already happened once.
2. Diff the Excel output against the pandas ground truth in `prep2.py` (`featured3.pkl`), column by column.
   Report mismatch counts. The current baseline is 0 mismatches on every flag and feature — hold that line.
3. If Excel and pandas disagree, **work out which one is right before assuming it's Excel.** Two of the
   previous agent's "bugs" turned out to be Excel being more correct than the pandas reference.

## Start here

Work the P0 items in `HANDOFF.md` in order. They are correctness risks, not polish:

- **P0-2 (State normalization)** is the one you can finish without a human. 207 distinct values mix US
  abbreviations, Mexican state codes, cities, and countries. Build the crosswalk in `Ref_Lists`, add
  `State Normalized` to `Clean_Data` via INDEX/MATCH, then build the geographic dashboard (P1-1) that it unblocks.
- **P0-4 (segment-aware outlier bounds)** is also self-contained.
- **P0-1 and P0-3** need answers from the business — draft the specific questions, don't guess.

Then P1-7 (the segment baseline rate table), which is the highest-value analysis item remaining: `$/shell-sqft`
by material × use type × year × scope class. It serves as both a non-ML fallback estimator and the benchmark
any model must beat.

## Do not

- **Do not train any models.** ML is deliberately deferred until the open questions in §5 of `HANDOFF.md`
  are answered. If you think the data is ready, say so and ask — don't start fitting.
- Do not rebuild the workbook from scratch. Extend the existing build scripts.
- Do not add dependencies without saying why.

## How to report back

After each unit of work: what changed, the recalc result (formula count + error count), the pandas-vs-Excel
mismatch counts, and anything you found that contradicts `HANDOFF.md`. Flag surprises early rather than
working around them — the last three real bugs in this project were all found by someone noticing a number
that looked slightly wrong.
