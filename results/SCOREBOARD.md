# Scoreboard

Backtest on 2,748 tanks (1,852 jobs, $878,838,876 of quoted
buckets) due 2025-04 to 2026-08. Each method only saw quotes due
before the quarter it was predicting.

**Error = |predicted - actual| of the five bucket prices added up, per tank.** Freight and
tax are known, identical on both sides, and cancel out, so they are left out. The method
with the lowest total $ error leads.

## Standings

| method | total $ error | mean $ error per tank | median $ error per tank | book bias (predicted - actual) | median % error |
|---|---|---|---|---|---|
| lgbm_dollar_weights | $115,656,647 | $42,088 | $11,891 | -$48,161,015 | 6.9% |
| lgbm_gamma | $121,973,734 | $44,386 | $13,883 | -$44,358,131 | 7.7% |
| lgbm | $123,578,426 | $44,970 | $11,855 | -$64,252,479 | 6.8% |
| ensemble | $124,471,213 | $45,295 | $11,807 | -$74,845,387 | 6.9% |
| rate_table | $232,260,708 | $84,520 | $29,320 | -$29,491,057 | 17.2% |

## Is the leader's win real?

"$ saved per tank" is how much less error the leader makes on an average tank. The interval
comes from resampling whole jobs 2,000 times. A win only counts when the whole
interval is above $0.

| comparison | $ saved per tank | 95% interval | verdict |
|---|---|---|---|
| lgbm_dollar_weights vs lgbm_gamma | $2,299 | $661 to $3,906 | lgbm_dollar_weights wins |
| lgbm_dollar_weights vs lgbm | $2,883 | $333 to $6,564 | lgbm_dollar_weights wins |
| lgbm_dollar_weights vs ensemble | $3,208 | $674 to $6,546 | lgbm_dollar_weights wins |
| lgbm_dollar_weights vs rate_table | $42,432 | $35,328 to $50,593 | lgbm_dollar_weights wins |

## Where the dollars of error are, by bucket

| method | material | fabrication | construction | insul_material | insul_construction |
|---|---|---|---|---|---|
| ensemble | $65,327,302 | $26,027,134 | $47,536,145 | $3,430,752 | $7,308,099 |
| lgbm | $63,396,930 | $27,095,380 | $49,193,978 | $3,417,433 | $7,266,152 |
| lgbm_dollar_weights | $63,396,930 | $25,548,257 | $45,645,151 | $3,417,433 | $7,267,680 |
| lgbm_gamma | $66,713,058 | $26,497,636 | $51,231,206 | $3,762,627 | $7,279,995 |
| rate_table | $118,771,700 | $66,288,684 | $105,786,331 | $6,935,325 | $16,328,497 |
