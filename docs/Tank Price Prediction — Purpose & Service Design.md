# Tank Price Prediction — Purpose & Service Design

Sep 24, 2026 · @Mason Hughes

## The problem

Pricing a storage tank today depends on who is doing the estimating. TBT quotes roughly 3,200 jobs and 4,600 tanks across the archive we analyzed, and the price of any one tank is assembled by hand from engineering judgment, historical feel and a spreadsheet. That makes quoting slow, hard to staff, and inconsistent between estimators.

The archive shows the pricing itself is far more regular than the process. Price behaves almost entirely as a rate times an area: total fabricated surface area alone correlates 0.86 with log material price. Material grade acts as a clean multiplier (carbon steel $32.21 per shell square foot, 304SS $65.17, 316SS $101.08). Labour regime moves construction about 1.75x. These are learnable relationships, not art.

So we are building a price prediction service: the estimator enters the tank and the project, and the system returns the expected price of each cost bucket in seconds, with the estimator still in control of the final number.

## Two systems, one hard boundary

There are two pieces, and the line between them is the most important design decision in this project.

|  | Estimating software | ML price prediction service |
| --- | --- | --- |
| Nature | Deterministic. Same inputs always give the same answer. | Statistical. Returns an expected value learned from history. |
| Owns | The web app, site calculations, freight, tax, margin policy, the assembled total, the proposal | Five predicted price buckets. Nothing else. |
| Answerable for | Being auditable and arithmetically correct | Being accurate on average and honest about uncertainty |
| Changes when | Business rules, tax tables or freight contracts change | The model is retrained on newer quotes |

The rule: anything the business can compute exactly stays in the estimating software. Only the things that genuinely require judgment learned from history go to the service.

This matters because a predicted number and a calculated number carry different kinds of trust. A tax figure that is 4% off is a defect. A material price that is 4% off is a good estimate. Mixing them into one output would make the whole quote feel unreliable, and would make errors impossible to attribute.

## What the service predicts

Five price buckets, each its own model. Every bucket is returned as a price in dollars, already carrying margin — these are sell prices, not raw costs.

| Bucket | What it covers | In scope on |
| --- | --- | --- |
| Material Price | The steel and components that make up the tank | 100% of tanks |
| Fabrication Price | Shop work: cutting, rolling, welding, coating | 100% of tanks |
| Construction Price | Field erection labour at the site | 65% of tanks |
| Insulation Material Price | Insulation system materials | 22% of tanks |
| Insulation Construction Price | Installing the insulation in the field | 21% of tanks |

The last three are not always in scope, and that is a feature of the business, not missing data. About 35% of tanks are sold materials-only with no erection at all, and insulation is a selected option. The service predicts zero for a bucket that is out of scope, and it knows which is which from the inputs the app already collects — the wage type tells it whether erection is included, and the insulation option tells it whether insulation applies.
