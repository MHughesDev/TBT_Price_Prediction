# Scoreboard

Backtest on 2,748 tanks (1,852 jobs, $878,838,876 of quoted
buckets) due 2025-04 to 2026-08. Each method only saw quotes due
before the quarter it was predicting.

**Error = |predicted - actual| of the five bucket prices added up, per tank.** Freight and
tax are known, identical on both sides, and cancel out, so they are left out. The method
with the lowest total $ error leads. The % columns are for context only: the median is a
typical tank, and the mean is pulled up by a few cheap tanks with big % misses.

## Standings

| method | total $ error | mean $ error per tank | median $ error per tank | book bias (predicted - actual) | median % error | mean % error |
|---|---|---|---|---|---|---|
| lgbm | $115,655,790 | $42,087 | $11,891 | -$48,158,731 | 6.9% | 11.0% |
| ensemble | $121,632,690 | $44,262 | $12,169 | -$68,137,787 | 6.9% | 10.7% |
| lgbm_gamma | $123,694,360 | $45,013 | $14,256 | -$41,697,379 | 7.7% | 12.0% |
| rate_table | $232,260,708 | $84,520 | $29,320 | -$29,491,057 | 17.2% | 23.6% |

## Is the leader's win real?

"$ saved per tank" is how much less error the leader makes on an average tank. The interval
comes from resampling whole jobs 2,000 times. A win only counts when the whole
interval is above $0.

| comparison | $ saved per tank | 95% interval | verdict |
|---|---|---|---|
| lgbm vs ensemble | $2,175 | $272 to $4,740 | lgbm wins |
| lgbm vs lgbm_gamma | $2,925 | $1,175 to $4,738 | lgbm wins |
| lgbm vs rate_table | $42,433 | $35,328 to $50,594 | lgbm wins |

## Where the dollars of error are, by bucket

| method | material | fabrication | construction | insul_material | insul_construction |
|---|---|---|---|---|---|
| ensemble | $65,327,302 | $25,657,636 | $46,952,012 | $3,430,752 | $7,307,967 |
| lgbm | $63,396,930 | $25,548,257 | $45,645,151 | $3,417,433 | $7,266,014 |
| lgbm_gamma | $66,713,058 | $26,856,582 | $51,604,117 | $3,762,627 | $7,279,995 |
| rate_table | $118,771,700 | $66,288,684 | $105,786,331 | $6,935,325 | $16,328,497 |
