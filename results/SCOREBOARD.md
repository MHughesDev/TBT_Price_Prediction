# Scoreboard

Rolling-origin backtest: 2,748 tanks on 1,852 jobs, due
2025-04 to 2026-08. Each method was trained only on quotes due before
each test quarter.

**Error = |predicted - actual| of the five bucket prices added up, per tank.** Freight and
tax are known, identical on both sides, and cancel out, so they are left out. The method
with the lowest total $ error leads.

## Standings

| method | total $ error | mean $ error per tank | median $ error per tank | book bias (predicted - actual) | median % error |
|---|---|---|---|---|---|
| lgbm | $123,578,426 | $44,970 | $11,855 | -$64,252,479 | 6.8% |
| rate_table | $232,260,708 | $84,520 | $29,320 | -$29,491,057 | 17.2% |

## Is the leader's win real?

"$ saved per tank" is how much less error the leader makes on an average tank. The interval
comes from resampling whole jobs 2,000 times. A win only counts when the whole
interval is above $0.

| comparison | $ saved per tank | 95% interval | verdict |
|---|---|---|---|
| lgbm vs rate_table | $39,550 | $33,716 to $45,690 | lgbm wins |

## Where the dollars of error are, by bucket

| method | material | fabrication | construction | insul_material | insul_construction |
|---|---|---|---|---|---|
| lgbm | $63,396,930 | $27,095,380 | $49,193,978 | $3,417,433 | $7,266,152 |
| rate_table | $118,771,700 | $66,288,684 | $105,786,331 | $6,935,325 | $16,328,497 |
