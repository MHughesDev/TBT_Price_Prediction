# Open questions — for estimating, finance, procurement and product

**From:** the data engineering work on `TBT_Tank_Quote_Analytics_v5.xlsx`
**Updated:** 2026-09-24 (supersedes the 2026-09-24 draft — two questions are now closed)
**Scope:** facts about the business that analysis cannot settle, and data that does not exist
in the export yet.

---

## CLOSED — verified, no action needed

### The Proposal Total "uplift" was sales tax

An earlier draft of this document asked what sat inside Proposal Total that was not in the five
buckets, and put $31.1M against the question. **That was wrong and the question is withdrawn.**

The archive obeys two exact identities, checked on all 4,423 training rows to a maximum relative
error of 7.1e-07:

```
Proposal Total = bucket sum + Total Tax          (carries NO freight)
Total Price    = bucket sum + Freight Price      (carries NO tax)
grand total    = bucket sum + Freight + Tax      (in NEITHER source column)
```

Proposal Total and Total Price are two different **subtotals**. Neither is a grand total, which is
why "buckets + freight + tax" failed against both. The correlation between the supposed uplift and
`Total Tax` is **1.0000000000**: every one of the 1,726 non-tying rows is a taxed row, and every one
of the 2,697 tying rows has zero tax. The mean effective rate is 4.83%, which is the "+4.7% uplift".

The apparent pattern by sales manager was real but spurious — tax follows jurisdiction, and managers
own territories:

| Sales manager | Tanks | Taxed | International |
|---|---:|---:|---:|
| Jorge Gomez | 142 | 0.0% | 99.3% |
| Claudia Descamps | 658 | 0.8% | 87.8% |
| John Petersen | 1,149 | 89.1% | 1.7% |

By country: US 57.9% taxed, Canada 2.2%, Mexico / Peru / Chile / Argentina 0%.

**What changed in the build:** `ML_Tank_Training` previously encoded `Total Price − (Proposal +
Freight + Tax)`, which double-counts tax and tied on only 61% of rows. It now carries
`recon_proposal_diff`, `recon_total_diff` and a new `Ref Grand Total` column, all against the
verified identities. Both reconciliations tie on 4,423/4,423. HANDOFF §5 item 5 is closed.

### Bucket prices are per tank, not per line

Confirmed independently. A controlled log-log regression gives a `log(quantity)` coefficient of
+0.06 (material) to −0.11 (construction); per-line pricing would give ~1.0. The descriptive check
agrees — blended `$/shell-sqft` at quantity 2 is **1.15×** quantity 1 (n=433), not 2×.

**Do not divide the targets by `Quantity`.** HANDOFF P0-1 is closed.

---

## OPEN

### Q1 — External steel price index, monthly, Jan 2023 to present *(procurement)*

**Blocking.** The material bucket shows a step change in 2026 Q1–Q3 after two flat years. Every
backward-looking model under-prices by 3–4% for roughly two quarters after a shock like that. An
index that moves *before* TBT's quoted prices is the only thing that corrects it, and the idea
cannot be tested without the series.

> **The ask:** monthly HRC and/or plate price, Jan 2023 to present — CRU, Platts, AMM, or whatever
> procurement already subscribes to. A single column of month + price is enough.
>
> **Also valuable:** TBT's own purchased steel cost per ton by month, if it is recorded anywhere.

### Q2 — Quote-form scope inputs *(product / web app)* — confirmed product gap

Today the training table infers scope from the answers: `is_insulated` is
`(Insulation Material Price + Insulation Construction Price) > 1` and `scope_class` comes from
`Construction Price > 1`. Both are derived from the targets, so training on them is training on the
answer. Both are excluded from the modelling export for that reason.

**I checked whether the existing insulation columns could stand in. They cannot:**

| Column | Uninsulated rows | Insulated rows |
|---|---:|---:|
| `Insulation Margin (%)` non-zero | **98.1%** | 98.8% |
| `Insulation Contingency (%)` non-zero | 0.0% | 0.0% |

`Insulation Margin (%)` is populated at a median of 5.0 on essentially every row regardless of
whether the tank is insulated. It carries no signal. The source export has 42 columns and none of
them records the estimator's scope selections.

> **The ask:** does the quote form collect **"insulation selected — yes/no"** and **"erection in
> scope — yes/no"** as inputs?
>
> - If yes: add both to the export. This is the single highest-value field pair available.
> - If no: it is a product gap. The service cannot gate insulation or construction on anything
>   except the price it is trying to predict.

### Q3 — Are any quotes booked in a currency other than USD? *(finance)*

Mexican work prices below US work, but **most of that is scope** — 96.9% of Mexican tanks are
materials-only against 6.2% in the US. Comparing like for like:

| Scope | US $/shell-sqft | Mexico $/shell-sqft | Gap |
|---|---:|---:|---:|
| `materials_only` | $55.92 (n=185) | $36.92 (n=849) | **−34.0%** |
| `tank_quote` | $95.90 (n=2,790) | $52.19 (n=27) | −45.6% |

A 34% gap remains inside identical scope on a healthy sample. That is the size of a genuine market
difference — cheaper Mexican steel and labour — but also the size of an FX effect, and the archive
cannot separate them.

> **The ask:** is every row recorded in USD? If any are booked in local currency, which, and is there
> a field or convention that identifies them? If everything is USD that is a complete answer, and the
> gap is regional pricing the model can learn from the country feature.

### Q4 — Confirm the pricing clock *(estimating / IT)*

`Due Date` is being used as the pricing date. Mason has confirmed it is the date the sales manager
needed the quote back by.

**Verified here:** the quote number encodes **YYMM of job origination**, not pricing. All 7,438
seven-digit quote groups have month digits in 1–12, and `Due Date` lands in a *later* month than the
quote number on 38.4% of rows, by up to **85 months**. Nobody should index time on the quote number.

**Also verified:** `Due Date` is the *only* date field in the 42-column source export.

> **The ask:** confirm against the source system that `Due Date` is when the revision was priced, and
> say whether a true **"quote created"** or **"quote sent"** timestamp exists per revision. If one
> does, it is a better pricing clock and should be exported.

### Q5 — Confirm Wage Type semantics *(estimating)*

| Wage Type | Rows | International | Materials-only | Median construction |
|---|---:|---:|---:|---:|
| Non-Union / Non-Prevailing | 4,466 | 5.0% | 6.2% | $81,334 |
| **(null)** | **1,567** | **86.2%** | **97.8%** | **$0** |
| No Erection Included | 629 | 84.3% | 82.2% | $0 |
| Prevailing Wage | 603 | 0.0% | 4.8% | $134,163 |
| Union Wage | 214 | 0.0% | 0.9% | $166,657 |
| Erection Advisor Only | 1 | 0.0% | 100% | $0 |

Null (20.9% of rows) behaves almost identically to "No Erection Included" — 86.2% international,
97.8% materials-only, construction priced on only 2.1%. It reads as "export, materials only" rather
than missing.

**On the contradictory rows:** 112 "No Erection Included" rows carry construction price (median
$57,039, 0.93× their material price). **109 of them are in 2024 and one is in 2025.** That is a
legacy entry pattern that stopped, not an ongoing scope pattern — which means the scope gate can be
a lookup going forward, with 2024 treated as suspect.

> **The ask:**
> 1. Is null a selectable state in the app, or a legacy gap that should be "No Erection Included"?
> 2. Did something change in the form or in practice during 2024/2025 that explains the 109 rows?

### Q6 — Tank spec fields that exist in the source system but not in this export *(estimating / IT)*

Two tanks identical on all nine currently-visible spec fields, priced in the same quarter, still
differ by a median 4.6% (material) and 8.2% (construction). Some of that is real spec difference that
is invisible here.

> **The ask:** which of these does the source system hold, and can they be exported?
> - shell plate thickness / course schedule
> - nozzle count and sizes
> - appurtenances (ladders, platforms, mixers)
> - coating or lining specification
> - wind and snow design loads, and any seismic parameters beyond `Ss` and `S1`
>
> Anything the **estimator supplies at quote time** is usable. Anything derived later in engineering
> is not — it would not exist when the service is asked for a price.

### Q7 — Are historical prices ever restated? *(estimating / IT)*

The monthly recalibration feed re-estimates a price level from recently-priced quotes. If a quote's
price can be edited after the fact, the feed needs an as-of snapshot rather than a live query, or the
recalibration will silently drift.

> **The ask:** once a revision is priced, can its bucket prices change later? If yes, is there an
> audit trail or a last-modified timestamp?

### Q8 — Change orders *(estimating)*

`CO#` rows are treated as separate work sharing a parent job. If the business considers a change
order part of the parent job, the de-duplication rule needs revisiting.

### Q9 — Zero freight on distant sites *(estimating)*

813 source rows carry no freight on sites more than 100 miles out. FOB / customer pickup, or missing
data? It changes how the freight percentages on `Dashboard_Geographic` should be read.

---

## What each answer changes

| Answer | Consequence |
|---|---|
| Q1 — index supplied | A leading price feature becomes testable; the post-shock under-pricing can be measured and corrected. |
| Q2 — scope inputs exist | They replace two leakage columns. Insulation and construction gates become real inputs instead of unusable. |
| Q2 — they do not exist | Product gap. Raise it with whoever owns the quote form. |
| Q3 — all USD | No change; the country feature carries the regional difference. |
| Q3 — mixed | New FX normalization column, needs booking date + rate source. International rows held out until then. |
| Q4 — a pricing timestamp exists | Better time index than `Due Date`; re-cut `months_since_2020` against it. |
| Q5 — null is "no erection" | The scope gate becomes a lookup, not a model. |
| Q6 — any field exported | Directly lowers the error floor on the residual 4.6% / 8.2%. |
| Q7 — prices are restated | Recalibration feed needs an as-of snapshot, not a mutable table. |
