# Build pipeline — the actual scripts

**These are the real build scripts that produced `TBT_Tank_Quote_Analytics_v5.xlsx`.** They were never
lost; they just weren't shipped with the first handoff. Nothing needs to be reconstructed, and the
workbook does not need to be extended in place via COM — regenerate it from source instead.

Put every file in this folder together with `TBT_Tank_Quote_Analytics_v5.xlsx` and `HANDOFF.md`.

## Files

| File | Role |
|---|---|
| `archive.csv` | The source data. 7,480 rows, 42 columns. **Scripts expect it at this exact relative path.** |
| `prep.py` | Pandas ground truth: cleaning, feature engineering, DQ flags. Writes `featured.pkl`. |
| `prep2.py` | Extends `prep.py` with quote-group / dedup / scope rules. Writes `featured3.pkl`, `train3.pkl`. **This is the verification reference.** |
| `build_core.py` | Builds `Raw_Import` + `Clean_Data` (7,480 rows × 76 formula columns) → `v5_core.xlsx` |
| `build_ml.py` | Builds `ML_Tank_Training` (4,481 × 126) → `v5_ml.xlsx` |
| `build_dash.py` | Builds `Fact_Quote` + 4 dashboards with 12 charts → `v5_dash.xlsx` |
| `build_docs.py` | Builds README/audit/catalog/research/validation, orders sheets → final workbook |
| `recalc.py` | LibreOffice recalculation + error report. Copied from the xlsx skill. |

Dependencies: `pandas`, `numpy`, `openpyxl`. `recalc.py` additionally needs LibreOffice (`soffice`) on PATH.

## Build order — the intermediate recalc is mandatory

```bash
python3 build_core.py
python3 recalc.py v5_core.xlsx 1200      # REQUIRED: build_ml.py reads computed values
python3 build_ml.py
python3 build_dash.py
python3 build_docs.py
python3 recalc.py TBT_Tank_Quote_Analytics_v5.xlsx 1500
```

Skip the middle recalc and `build_ml.py` reads a column of un-evaluated formulas as NaN, silently
producing a header-only ML sheet with zero training rows. This has already happened once. Full run is
about 8–10 minutes, most of it in the two recalcs.

Expected final state: **1,274,706 formulas, 0 errors, 10/10 validation PASS**, ~20 MB.

## Verify before shipping anything

A green recalc proves formulas evaluate, not that they are correct. Always diff against the pandas
reference:

```python
import pandas as pd
ml = pd.read_excel('TBT_Tank_Quote_Analytics_v5.xlsx', sheet_name='ML_Tank_Training', header=1)
gt = pd.read_pickle('featured3.pkl')            # from prep2.py
# join on Tank Key, compare column by column, report mismatch counts
```

Current baseline is **0 mismatches** on every flag and engineered feature. Hold that line.

Two known and intentional exceptions where Excel is *more* correct than the pandas reference — do not
"fix" these by changing Excel to match:

- `Capacity Value` — Excel preserves the sign on 44 negative-capacity rows; the pandas regex drops it.
- `liquid_height_ft` — Excel clips at 0; pandas does not, producing negative wetted heights.

## If LibreOffice isn't available

`recalc.py` needs `soffice`. Without it you can still build, and Excel will recalculate on open — but you
lose automated error detection, which is how every formula bug in this project was caught. Install
LibreOffice, or open the workbook in Excel, force a full recalculation (Ctrl+Alt+F9), save, and check for
error values manually before shipping.

## Known debt in these scripts

- Row bounds are hardcoded (`Clean_Data` 2–7481, ML 3–4483). Changing the source row count requires
  editing `N`/`FIRST`/`LAST` in `build_core.py` and the `MF`/`MLST` constants in `build_docs.py`.
- `build_dash.py` sets the ML row count through a module-level `ML_LAST` list used as a mutable global.
- `prep.py` and `prep2.py` overlap; `prep2` imports and extends `prep`.
- There is no automated regression test. The pandas-vs-Excel diff above is run by hand.
