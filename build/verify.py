"""Verification harness for TBT_Tank_Quote_Analytics_v5.xlsx.

Three independent checks. A green recalc proves formulas evaluate; these prove they are right.

  1. audit      - structural audit straight off the xlsx zip: formula count, error cells,
                  formulas missing cached values. Needs no Excel and no LibreOffice.
  2. lint       - static scan for functions the LibreOffice recalc engine cannot evaluate
                  (XLOOKUP/XMATCH/FILTER/UNIQUE/SORT/SEQUENCE) and for post-2007 functions
                  written without the _xlfn. prefix. This is the failure mode LibreOffice
                  guards against, caught deterministically instead of by recalculation.
  3. diff       - column-by-column diff of ML_Tank_Training against the pandas ground truth
                  in featured3.pkl. Reports a mismatch count per column.

Usage:
    python verify.py ../dist/TBT_Tank_Quote_Analytics_v5.xlsx            # all three
    python verify.py ../dist/TBT_Tank_Quote_Analytics_v5.xlsx --audit    # one check
"""
import sys, re, zipfile, argparse, json
import numpy as np, pandas as pd

# ----------------------------------------------------------------- 1. audit
def audit(path):
    z = zipfile.ZipFile(path)
    wbxml = z.read('xl/workbook.xml').decode('utf-8', 'replace')
    sheets = re.findall(r'<sheet name="([^"]+)"[^>]*r:id="(rId\d+)"', wbxml)
    rels = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"',
                           z.read('xl/_rels/workbook.xml.rels').decode('utf-8', 'replace')))
    total_f = total_e = total_nocache = 0
    per_sheet, errors = [], {}
    for name, rid in sheets:
        raw = z.read('xl/' + rels[rid].lstrip('/')).decode('utf-8', 'replace')
        nf = len(re.findall(r'<f[ >]', raw))
        nocache = len(re.findall(r'</f>\s*</c>', raw))
        errs = re.findall(r'<c r="([A-Z]+\d+)"[^>]*t="e"[^>]*>.*?<v>([^<]*)</v>', raw, re.S)
        total_f += nf; total_nocache += nocache; total_e += len(errs)
        if errs:
            errors[name] = errs[:20]
        per_sheet.append((name, nf, len(errs), nocache))
    print('=== 1. STRUCTURAL AUDIT ===')
    print(f'  sheets                       {len(sheets)}')
    print(f'  formula cells                {total_f:,}')
    print(f'  error cells                  {total_e:,}')
    print(f'  formulas w/o cached value    {total_nocache:,}')
    print(f'  charts                       {len([n for n in z.namelist() if re.match(r"xl/charts/chart\d+\.xml", n)])}')
    for name, errs in errors.items():
        print(f'  ERRORS in {name}: {errs}')
    if total_nocache:
        print('  WARNING: formulas without cached values - recalculate before reading with pandas.')
    return total_e == 0 and total_nocache == 0


# ------------------------------------------------------------------ 2. lint
# Cannot be evaluated by the LibreOffice recalc engine under any prefix. Using one of
# these bakes a literal #NAME? into the delivered file. See HANDOFF.md gotcha 4.
BANNED = ['XLOOKUP', 'XMATCH', 'FILTER', 'UNIQUE', 'SORT', 'SORTBY', 'SEQUENCE',
          'TEXTSPLIT', 'TEXTBEFORE', 'TEXTAFTER', 'LET', 'LAMBDA', 'VSTACK', 'HSTACK']
# Work, but only when written with the _xlfn. prefix.
NEEDS_PREFIX = ['TEXTJOIN', 'CONCAT', 'IFS', 'SWITCH', 'MAXIFS', 'MINIFS']

# Aggregate-over-IF patterns. These are ARRAY formulas: they need Ctrl-Shift-Enter
# metadata that openpyxl does not write, so LibreOffice cannot evaluate them and even
# Excel returns a value on one row and an error on the next. They are invisible to a
# banned-function scan because every name in them is ordinary, so they get their own rule.
# Use SUMIFS / COUNTIFS / AVERAGEIFS instead.
ARRAY_PATTERNS = ['MEDIAN', 'AVERAGE', 'SUM', 'MAX', 'MIN', 'COUNT', 'STDEV', 'PERCENTILE']

def lint(path):
    z = zipfile.ZipFile(path)
    wbxml = z.read('xl/workbook.xml').decode('utf-8', 'replace')
    sheets = re.findall(r'<sheet name="([^"]+)"[^>]*r:id="(rId\d+)"', wbxml)
    rels = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"',
                           z.read('xl/_rels/workbook.xml.rels').decode('utf-8', 'replace')))
    ban_re = re.compile(r'(?<![A-Z0-9_.])(' + '|'.join(BANNED) + r')\s*\(', re.I)
    bare_re = re.compile(r'(?<![A-Z0-9_.])(' + '|'.join(NEEDS_PREFIX) + r')\s*\(', re.I)
    arr_re = re.compile(r'(?<![A-Z0-9_.])(' + '|'.join(ARRAY_PATTERNS) + r')\s*\(\s*IF\s*\(', re.I)
    hits = []
    for name, rid in sheets:
        raw = z.read('xl/' + rels[rid].lstrip('/')).decode('utf-8', 'replace')
        for m in re.finditer(r'<c r="([A-Z]+\d+)"[^>]*>\s*<f[^>]*>([^<]*)</f>', raw):
            cell, f = m.group(1), m.group(2)
            for fn in ban_re.findall(f):
                hits.append((name, cell, 'BANNED', fn.upper()))
            for fn in bare_re.findall(f):
                hits.append((name, cell, 'MISSING _xlfn.', fn.upper()))
            for fn in arr_re.findall(f):
                hits.append((name, cell, 'ARRAY FORMULA', f'{fn.upper()}(IF('))
    print('=== 2. LIBREOFFICE-SAFETY LINT ===')
    if not hits:
        print('  clean - no banned functions, no bare post-2007 names, no array formulas')
        return True
    for h in hits[:40]:
        print(f'  {h[2]:16s} {h[3]:10s} {h[0]}!{h[1]}')
    print(f'  {len(hits)} problem(s)')
    return False


# ------------------------------------------------------------------ 3. diff
# Excel header -> featured3.pkl column. Only names that differ are listed;
# anything not here is matched on its own name.
ALIASES = {
    'Quote Group ID': 'QuoteGroupID', 'Quote Variant Type': 'QuoteVariantType',
    'Is Scope Variant': 'IsScopeVariant', 'Effective Revision': 'EffectiveRevision',
    'Job Tank Key': 'JobTankKey', 'Quantity': 'quantity',
    'Miles TBT': 'Miles to Site (From TBT)', 'Miles GT': 'Miles to Site (From GT)',
    'Y Material': 'target_material', 'Y Fabrication': 'target_fabrication',
    'Y Construction': 'target_construction', 'Y Insul Material': 'target_insul_material',
    'Y Insul Construction': 'target_insul_construction', 'Y Bucket Sum': 'target_bucket_sum',
    'Ref Freight': 'Freight Price', 'Ref Tax': 'Total Tax',
    'Ref Proposal Total': 'Proposal Total', 'Ref Total Price': 'Total Price',
}

# Columns where Excel and pandas are known to differ, with the reason and the expected
# row count. Reported separately so a real regression cannot hide behind an expected
# divergence; a count that moves off the recorded number is reported as a REGRESSION.
#
# Every entry below was adjudicated row by row against the source data. Excel is the
# correct side in all of them. Do not "fix" these by changing Excel to match pandas.
#
# NOTE: HANDOFF.md and BUILD_README.md both claim a baseline of "0 mismatches on every
# flag and feature". That is not reproducible under a strict comparison - the prior diff
# must have coerced NaN to 0. The divergences below are the real baseline.
#
# The counts are tied to the current training row count (4,423 after P0-4 tightened
# eligibility). Any change to the eligibility rules moves them; when that happens, prove
# the movement is pure row removal before re-recording, or a behaviour change will hide
# inside a number that merely "looks smaller".
# Two former entries are gone for good: Capacity Value and capacity_tons diverged only
# because prep.py's regex ([\d.]+) dropped the minus sign on 44 negative-capacity rows.
# P1-6 fixed the regex and made a negative capacity missing on both sides, so they agree.
EXPECTED_DIVERGENCE = {
    'liquid_height_ft': (4, 'Excel clips at 0; pandas does not, producing negative wetted heights. Excel is correct.'),
    'total_area_sqft':  (3712, 'Excel uses the pitch-adjusted roof area; prep.py uses the flat projection. Excel is correct.'),
    'roof_slope_ratio': (711, 'Excel returns 0 for a roof with no "n:12" pitch (open-top/dome/blank); pandas returns NaN. Excel is correct - prep.py itself fillna(0)s it downstream.'),
    'freeboard_ft':     (239, 'Excel N() treats blank freeboard as 0, as the column note documents; pandas returns NaN.'),
    'freeboard_ratio':  (239, 'Propagates from freeboard_ft.'),
    'seismic_x_height': (2, 'Excel N() treats blank Ss as 0; pandas returns NaN. 4 rows have no Ss.'),
    'seismic_x_shell':  (2, 'Propagates from the same 4 blank-Ss rows.'),
    's1_ss_ratio':      (1, 'Quote 2604067 has Ss=-1.697, physically impossible. Excel guards with IF(N(Ss)>0,...) and returns blank; pandas only guards against 0 and returns -0.0666. Excel is correct.'),
    'Customer Name':    (1, 'Clean_Data substitutes "(No Customer Listed)" for a blank customer; pandas leaves NaN. Deliberate.'),
    'City':             (9, 'Clean_Data strips ALL commas ("Charlton, Massachusetts," -> "Charlton Massachusetts"); pandas strips only trailing ones. Not a model feature.'),
    'seismic_band':     (4421, 'Cosmetic: Excel labels "1. Very Low", pandas "1. Very Low (<0.25)".'),
    'distance_band':    (4414, 'Cosmetic: Excel labels "1. <100mi", pandas "1. <100 mi". The 9 rows with no '
                              'computable distance emit "Unknown" on both sides and so match exactly.'),
}

TOL = 1e-6

def _as_text(s):
    """Normalise to plain strings for comparison. An Excel formula returning "" reads
    back as NaN, while the pandas reference holds ''; both mean 'no value', so both
    collapse to ''. Note pandas 3.0 astype(str) PRESERVES NA rather than producing the
    string 'nan', so the fillna has to come first."""
    return (s.astype(object).where(~pd.isna(s), '')
             .map(lambda v: '' if v is None else str(v)).str.strip()
             .replace({'nan': '', 'None': '', 'NaT': ''}))


def _cmp(xl, gt):
    """Return a boolean mask of mismatches, treating null and '' as equal."""
    if pd.api.types.is_numeric_dtype(xl) and pd.api.types.is_numeric_dtype(gt):
        both_null = pd.isna(xl) & pd.isna(gt)
        a = pd.to_numeric(xl, errors='coerce'); b = pd.to_numeric(gt, errors='coerce')
        scale = np.maximum(np.abs(b.fillna(0)), 1.0)
        close = (a - b).abs() <= TOL * scale
        return ~(both_null | close.fillna(False))
    return _as_text(xl) != _as_text(gt)


def diff(path, pkl='featured3.pkl'):
    print('=== 3. EXCEL vs PANDAS GROUND TRUTH ===')
    xl = pd.read_excel(path, sheet_name='ML_Tank_Training', header=1)
    gt = pd.read_pickle(pkl)
    gt = gt[gt['ML Training Row V2'] == 1].copy()
    print(f'  Excel training rows   {len(xl):,}')
    print(f'  pandas training rows  {len(gt):,}')
    if len(xl) != len(gt):
        print(f'  ROW COUNT MISMATCH ({len(xl)} vs {len(gt)})')
    xs, gs = set(xl['Tank Key']), set(gt['Tank Key'])
    if xs != gs:
        print(f'  key mismatch: {len(xs - gs)} Excel-only, {len(gs - xs)} pandas-only')
        for k in list(xs - gs)[:5]: print(f'    Excel-only : {k}')
        for k in list(gs - xs)[:5]: print(f'    pandas-only: {k}')
    m = xl.merge(gt, on='Tank Key', suffixes=('_xl', '_gt'), how='inner')
    print(f'  joined on Tank Key    {len(m):,}')

    unexpected, diverged, regressed, skipped = [], [], [], []
    for h in xl.columns:
        if h == 'Tank Key':
            continue
        g = ALIASES.get(h, h)
        if g not in gt.columns:
            skipped.append(h); continue
        a = m[h + '_xl'] if h + '_xl' in m.columns else m[h]
        b = m[g + '_gt'] if g + '_gt' in m.columns else m[g]
        n = int(_cmp(a, b).sum())
        if h in EXPECTED_DIVERGENCE:
            want, why = EXPECTED_DIVERGENCE[h]
            (diverged if n == want else regressed).append((h, n, want, why))
        elif n:
            unexpected.append((h, n))
    print(f'\n  compared {len(xl.columns) - 1 - len(skipped)} columns; '
          f'{len(skipped)} Excel-only columns have no pandas counterpart')
    if unexpected:
        print(f'\n  *** {len(unexpected)} UNEXPECTED MISMATCH(ES) ***')
        for h, n in sorted(unexpected, key=lambda x: -x[1]):
            print(f'    {h:34s} {n:6,} rows')
    else:
        print('\n  0 unexpected mismatches')
    if regressed:
        print(f'\n  *** {len(regressed)} DIVERGENCE COUNT(S) MOVED - investigate ***')
        for h, n, want, why in regressed:
            print(f'    {h:34s} {n:6,} rows (recorded {want:,})')
    if diverged:
        print(f'\n  {len(diverged)} expected divergence(s), all at their recorded counts (Excel is the correct side):')
        for h, n, want, why in diverged:
            print(f'    {h:34s} {n:6,} rows  - {why}')
    if skipped:
        print(f'\n  Excel-only columns: {", ".join(skipped)}')
    return not unexpected and not regressed


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('workbook')
    ap.add_argument('--audit', action='store_true')
    ap.add_argument('--lint', action='store_true')
    ap.add_argument('--diff', action='store_true')
    ap.add_argument('--pkl', default='featured3.pkl')
    a = ap.parse_args()
    run_all = not (a.audit or a.lint or a.diff)
    ok = True
    if run_all or a.audit: ok &= audit(a.workbook); print()
    if run_all or a.lint:  ok &= lint(a.workbook);  print()
    if run_all or a.diff:  ok &= diff(a.workbook, a.pkl)
    sys.exit(0 if ok else 1)
