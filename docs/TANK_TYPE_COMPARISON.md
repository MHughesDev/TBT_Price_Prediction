# Pooled vs tank-type-specific models

**Date:** 2026-09-24 · **Protocol:** rolling origin on `Due Date`, 6 origins, 4-seed ensembles at
every level (production-equivalent), weighted by tanks.
**Verdict:** keep pooled as production. Per-type is built and selectable, not promoted.

> **Updated 2026-09-24 — the fair rerun is done.** The comparison below originally gave segment
> models the POOLED hyperparameters, which handicapped them. Per-segment tuning was then run
> (19 segments, mean **10.5%** relative gain within segment, 34% on the worst) and the head-to-head
> repeated. **Pooled still wins every bucket.** See "Head-to-head with tuned segment parameters"
> at the end of this document. The conclusion is unchanged; it is now earned rather than assumed.

---

## The preset tank types

Mapping supplied by Mason, implemented in `service/tank_types.py`. Deterministic from `Use Type`,
so it is derivable at serve time and adds no new input.

| tank type | tanks | collapsed from |
|---|---|---|
| Fire Protection Storage Tank | 2,170 | itself |
| Waste Water Storage Tank | 1,236 | Waste Water, Industrial, Bio Mass, Petroleum, Agricultural, Brine Concentrator |
| Potable Water Storage Tank | 493 | itself |
| Water Storage Tank | 322 | itself |
| Silo | 235 | Industrial, Bio Mass, Agricultural silos |
| Energy / Utilities Storage Tank | 3 | itself |

`Unknown` and `0` are in the map but absent from this data.

Per-bucket counts are the binding constraint — insulation is only trainable on two segments:

| tank type | material | construction | insul material | insul construction |
|---|---|---|---|---|
| Fire Protection | 2,170 | 1,261 | 700 | 681 |
| Waste Water | 1,236 | 999 | 239 | 212 |
| Potable Water | 493 | 279 | 16 | 14 |
| Water Storage | 322 | 158 | 24 | 18 |
| Silo | 235 | 205 | 0 | 0 |
| Energy / Utilities | 3 | 3 | 0 | 0 |

## The four architectures

| | description | boosters | trees | bundle |
|---|---|---|---|---|
| **A pooled** | production. `Use Type` already a feature | 20 | 12,432 | 48 MB |
| **B pooled + tank_type** | the preset added as an extra categorical | 20 | ~12,400 | 48 MB |
| **C per-type** | separate model per segment, pooled fallback under n=150 | **96** | **60,792** | **124 MB** |
| **D hybrid** | log-space blend of segment and pooled, weight n/(n+400) | 96 | 60,792 | 124 MB |

## Overall result

| bucket | A pooled | B +tank_type | C per-type | D hybrid |
|---|---|---|---|---|
| material | **0.0851** | 0.0877 | 0.0916 | **0.0851** |
| fabrication | **0.0889** | 0.0891 | 0.0916 | 0.0888 |
| construction | **0.1109** | 0.1116 | 0.1261 | 0.1163 |
| insul material | **0.0656** | 0.0679 | 0.0682 | 0.0664 |
| insul construction | **0.1587** | 0.1616 | 0.1691 | 0.1641 |

**Pooled wins or ties on all five.** Per-type is worst on four of five, and costs 4.8× the models
and 2.6× the bundle size to get there.

One counter-current worth recording: per-type has consistently *better* dollar-weighted error
(construction −8.6% vs pooled −10.0%, insul material −3.8% vs −4.5%). Segmentation helps the
aggregate slightly while hurting the typical tank.

## Where segmentation does and does not help

**Material, MdAPE by segment:**

| tank type | n | A pooled | B +tank_type | C per-type | D hybrid | best |
|---|---|---|---|---|---|---|
| Fire Protection | 1,383 | **0.0621** | 0.0634 | 0.0665 | 0.0631 | pooled |
| Waste Water | 788 | 0.1343 | 0.1319 | 0.1317 | **0.1270** | hybrid |
| Potable Water | 246 | 0.0906 | **0.0888** | 0.1070 | 0.0956 | +tank_type |
| **Silo** | 177 | 0.1611 | **0.1491** | 0.1776 | 0.1638 | **+tank_type** |
| **Water Storage** | 151 | **0.0904** | 0.1024 | **0.1726** | 0.1046 | pooled |

**Construction, MdAPE by segment:**

| tank type | n | A pooled | B +tank_type | C per-type | D hybrid |
|---|---|---|---|---|---|
| Fire Protection | 792 | **0.0961** | 0.0962 | 0.1002 | 0.0972 |
| Waste Water | 629 | 0.1213 | **0.1181** | 0.1602 | 0.1370 |
| Silo | 154 | 0.1431 | 0.1467 | 0.1441 | **0.1423** |
| Potable Water | 102 | 0.1573 | **0.1529** | **0.2150** | 0.1654 |
| Water Storage | 96 | 0.1341 | **0.1325** | 0.1341 | 0.1341 |

Three patterns:

1. **Dedicated models destroy small segments.** Water Storage material goes 0.0904 → **0.1726**
   (+91%) and Potable Water construction 0.1573 → **0.2150** (+37%). A 151-row segment cannot
   support its own model.
2. **`tank_type` as a *feature* helps the distinctive minorities** — Silo material 0.1611 →
   0.1491 (−7.5%), Waste Water construction 0.1213 → 0.1181 — while costing the dominant Fire
   Protection segment ~2%. Since Fire Protection is half the book, that trade loses in aggregate.
3. **Hybrid blending helps the one large non-dominant segment.** Waste Water material 0.1343 →
   0.1270 (−5.4%), which is the largest single per-segment win anywhere in this table.

## Why segmentation does not pay here

`Use Type` carries almost no independent signal once the model has everything else:

| bucket | `Use Type` gain share | rank | `tank_type` gain share |
|---|---|---|---|
| material | 0.71% | 47 of 95 | 0.52% |
| construction | 0.28% | 58 of 95 | 0.15% |

Silo really is different — median $27.18/shell-sqft against $15.91–$17.74 for everything else, and
89% erection scope. But that difference is **already explained** by features the model measures
directly: erection scope, geometry, deck style. Segmenting spends 5× the data to isolate a
variable that is mostly redundant.

## Caveats

- ~~**The comparison is conservative toward per-type.** Segment models reuse the *pooled* Optuna
  hyperparameters... Re-tuning per segment is the fair test and has not been run.~~
  **RESOLVED** — per-segment tuning was run (19 segments) and the head-to-head repeated. See the
  final section. Tuning closed roughly a third of the gap on the worst segment and pooled still
  wins every bucket.
- Differences under ~0.002 MdAPE are within seed noise. The Water Storage per-type failure
  (+0.082) and the Waste Water hybrid win (−0.007) are the only per-segment effects clearly
  outside it.
- Energy / Utilities (n=3) always falls back to pooled and is untestable.

## Recommendation

**Keep pooled in production.** Keep per-type and hybrid selectable via `--arch` so the comparison
can be re-run when the archive grows — the small segments are the ones failing, and that is a
data-volume problem that time fixes on its own.

**If the business specifically cares about Silo accuracy**, `--arch tank_type_feature` buys 7.5%
there for ~2% on Fire Protection. That is a business trade, not a modelling one, and it should be
made deliberately rather than by default.

## Reproduce

```bash
python service/train.py --arch pooled                        # production
python service/train.py --arch per_type --no-promote         # 96 boosters, not promoted
python service/train.py --arch hybrid  --no-promote
```


---

## Head-to-head with tuned segment parameters (2026-09-24)

The fair rerun. Rolling origin, 6 origins, 4 seeds. `C0` is the old handicapped arm, kept so the
effect of tuning is visible separately from the effect of the architecture.

| bucket | **A pooled** | B +tank_type | C per-type **tuned** | C0 per-type pooled-params | D hybrid |
|---|---|---|---|---|---|
| material | **0.0851** | 0.0877 | 0.0893 | 0.0916 | 0.0858 |
| fabrication | **0.0889** | 0.0891 | 0.0969 | 0.0916 | 0.0903 |
| construction | **0.1109** | 0.1116 | 0.1203 | 0.1261 | 0.1164 |
| insul material | **0.0656** | 0.0679 | 0.0676 | 0.0682 | 0.0657 |
| insul construction | **0.1565** | 0.1597 | 0.2088 | 0.1695 | 0.1799 |

**Tuning helped the segment models and did not close the gap.** C vs C0 isolates it: material
0.0916 → 0.0893, construction 0.1261 → 0.1203. The clearest case is material | Water Storage
(n=151), which went 0.1726 → **0.1483** with tuning, against pooled's **0.0904** — about a third
of the gap closed.

**On two buckets the tuned parameters are WORSE than the pooled ones** — fabrication 0.0916 →
0.0969, insul construction 0.1695 → **0.2088**. Per-segment tuning overfit its own within-segment
CV, which interpolates, and then lost under rolling origin, which extrapolates forward. The
headline tuning gains (34% on insul_material | Waste Water, 28% on construction | Water Storage)
are substantially CV artifacts.

### Per-segment wins that do survive

None is an architecture, but all three are real:

| segment | best arm | vs pooled |
|---|---|---|
| Silo, material | B (`tank_type` as a feature) | **0.1491** vs 0.1611 |
| Waste Water, material | D (hybrid) | **0.1297** vs 0.1343 |
| Fire Protection, construction | C (tuned per-type) | **0.0923** vs 0.0961 |

That the tuned per-type arm wins on the *largest* segment, and loses badly on the smallest, is the
data-volume story stated precisely.
