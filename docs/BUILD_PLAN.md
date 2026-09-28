# Build plan — tank price prediction service

**Owner:** ML research lead (also engineering) · **Started:** 2026-09-24
**Design:** `docs/ML_SYSTEM_DESIGN.md` · **Research reproduction:** `ml/`

Three stages: design the pipeline, implement it, then actually train and validate the models.
Each phase has an exit test that must pass before the next one starts.

---

## Founding decision: the serve-safe feature set

A live request carries only what the quote form collects. Rather than reimplement 89 pipeline
derivations and hope they don't drift, **the models are trained only on features a request can
carry.** Train/serve skew then becomes structurally impossible for the feature *list* — only the
derivation logic needs parity, and that gets a test.

Excluded, with measured cost:

| excluded | why | gain share |
|---|---|---|
| `Quote #` | identifier, ~3000 levels, encodes YYMM | 0.00% |
| `Revision #`, `Job Revision Count`, `Job Rev First Row` | outcomes of the quoting process; at serve time you are always at revision 0 | 0.24–0.44% |
| `Margin/Contingency/Commission (%)` ×5 | business policy, applied downstream by the estimating software | 2.1–3.4% |
| `Name Has Option`, `Name Partial Scope` | parsed from free-text tank name the app may not send | small |
| `tank_count_in_quoterev`, `is_multi_tank_quote` | needs whole-quote context, not one tank | 0.87–1.43% |

**Total cost: +0.2pp MdAPE on material, +0.6pp on construction, ~0 elsewhere.** Accepted.

---

## Phase 0 — Feature contract and parity  ✅ exit test: parity on 4,459 rows

- `service/schema.py` — the request/response contract, with validation and units
- `service/features.py` — pure function: raw request → model feature row, mirroring `build/prep.py`
- **Exit test:** run `features.py` over every row of `training.parquet` reconstructed as a request,
  and assert every serve-safe feature matches the pipeline's value. Any mismatch fails the build.

This is the highest-risk component in the whole system. It gets the strictest test.

## Phase 1 — Training pipeline  exit test: bundle round-trips and reproduces research numbers

- `service/train.py` — fits a versioned artifact bundle:
  - 5 bucket models × 4 seeds, L1 on log price, tuned params
  - level offsets (shrunk, by regime — a level, never a trend)
  - CV+ conformal calibration + per-grade scales
  - initial ACI state per bucket
  - metadata: training row count, date range, feature hash, git SHA, metrics
- Bundles are immutable and content-addressed; nothing is fitted at serve time.
- **Exit test:** a freshly trained bundle reproduces the rolling-origin numbers from `ml/recipe.py`
  within tolerance.

## Phase 2 — Serving  exit test: golden predictions, guards fire correctly

- `service/predict.py` — load bundle, produce 5 buckets with intervals, drivers, versions
- `service/guards.py` — refusal conditions (§11 of the design): out-of-envelope geometry, thin
  grade support, fallback scope gate, interval too wide, drift alarm live
- `service/api.py` — HTTP endpoint over the above
- **Exit test:** golden-prediction regression file; guard unit tests; a request missing a required
  scope gate must come back flagged, never silently guessed.

## Phase 3 — Operations  exit test: replaying history reproduces the ACI trajectory

- monthly level adjustment job (trailing 2 months of priced quotes)
- monthly ACI update (γ=0.45, min cohort 40)
- monthly hedonic index + drift alarm (±5%, or 3 consecutive same-direction months)
- **Exit test:** replaying 2025Q2→2026Q3 through the ops jobs reproduces the measured coverage.

## Phase 4 — Train and validate for real  exit test: acceptance gate

- Train the production bundle on all 4,459 rows
- Full validation report: rolling-origin accuracy per bucket, interval coverage, per-segment
  breakdown (grade, size, use type, geography, wage regime), guard hit rates
- **Acceptance gate:** every bucket must beat the rate×area fallback, and interval coverage must be
  within ±3pp of nominal. A bucket that fails ships in fallback mode, not at all.

## Phase 5 — Handover

- `service/README.md`, runbook, and a written statement of what the service does *not* do

---

## Progress

| phase | status | exit test |
|---|---|---|
| 0 — feature contract + parity | **done** | PARITY PASS — 76 features on all 4,459 rows |
| 1 — training pipeline | **done** | bundle builds, parity gate enforced, reproduces research |
| 2 — serving | **done** | golden prediction runs; guards refuse/flag correctly |
| 3 — operations | **done** | level adjustment + ACI + drift alarm, state persists across retrain |
| 4 — train + validate | **done** | **ACCEPTANCE GATE PASS** — see below |
| 5 — handover | **done** | `service/README.md` |

## Phase 4 result — acceptance gate PASS

Rolling-origin backtest through the shipped code path, 6 origins, weighted by tanks:

| bucket | n | MdAPE | w10 | w20 | bias | rate baseline | beats |
|---|---|---|---|---|---|---|---|
| material | 6,795 | 0.092 | 0.532 | 0.783 | −3.3% | 0.165 | yes |
| fabrication | 6,795 | 0.086 | 0.562 | 0.819 | +1.5% | 0.250 | yes |
| construction | 4,419 | 0.120 | 0.438 | 0.723 | +1.3% | 0.342 | yes |
| insul material | 1,643 | 0.070 | 0.671 | 0.901 | −1.6% | 0.099 | yes |
| insul construction | 1,593 | 0.191 | 0.309 | 0.579 | +1.9% | 0.296 | yes |

80% interval coverage: 0.793 / 0.802 / 0.798 / 0.782 / 0.805 — all within 3pp.
Guards: 91.6% `normal`, 8.4% `low`.

These are lower than `ml/recipe.py` (material 0.083) because the service trains only on
serve-safe features and is scored through the real ops loop. **The service numbers are the
honest ones**; the research numbers had access to inputs a live request cannot carry.

## Defects this build caught that research had not

| found by | defect |
|---|---|
| parity test | `min_miles` used a plain min, letting "never computed" zeros through on 27% of tanks |
| parity test | `Deck Style`/`Floor Style` emitted a filled placeholder instead of the raw value |
| serving layer | `Usable Capacity` was a `role=feature` free-text near-identifier (3,154 levels, 0.00% gain) |
| validation | calibration state was discarded on every retrain, so ACI never adapted |
| validation | ACI consumed only last month, silently dropping low-volume insulation cohorts |
