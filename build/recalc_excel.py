"""Recalculate a workbook with Microsoft Excel via COM. Drop-in replacement for recalc.py
on machines without LibreOffice.

    python recalc_excel.py v5_core.xlsx [timeout_seconds]

Opens the file in a hidden Excel instance, forces a full dependency-tree rebuild
(equivalent to Ctrl+Alt+F9), writes cached values back, saves in place, and prints the
same JSON shape recalc.py produces:

    {"status": "success"|"errors_found", "total_formulas": N, "total_errors": N,
     "error_summary": {...}}

Exit code is 0 for success AND for errors_found (matching recalc.py); a non-zero exit
means nothing was recalculated.

IMPORTANT - what this does NOT catch. Excel evaluates XLOOKUP, FILTER, UNIQUE, SORT and
SEQUENCE happily; LibreOffice, which produced the delivered file, cannot, and bakes
#NAME? into it. Excel alone will therefore give a clean recalc on a workbook that is
broken for the client. Always run `verify.py --lint` alongside this.
"""
import sys, os, json, re, zipfile

XL_CALCULATION_MANUAL = -4135
XL_CALCULATION_AUTOMATIC = -4105

# Excel reports formula errors as negative sentinel longs via COM.
CVERR = {-2146826281: '#DIV/0!', -2146826246: '#N/A', -2146826259: '#NAME?',
         -2146826288: '#NULL!', -2146826252: '#NUM!', -2146826265: '#REF!',
         -2146826273: '#VALUE!', -2146826237: '#GETTING_DATA'}


def count_formulas(path):
    """Count formula cells straight off the zip - cheaper and safer than asking COM."""
    z = zipfile.ZipFile(path)
    return sum(len(re.findall(r'<f[ >]', z.read(n).decode('utf-8', 'replace')))
               for n in z.namelist() if re.match(r'xl/worksheets/sheet\d+\.xml$', n))


def scan_errors(path):
    """Find cached error values in the saved file, by sheet and error type."""
    z = zipfile.ZipFile(path)
    wbxml = z.read('xl/workbook.xml').decode('utf-8', 'replace')
    sheets = re.findall(r'<sheet name="([^"]+)"[^>]*r:id="(rId\d+)"', wbxml)
    rels = dict(re.findall(r'Id="(rId\d+)"[^>]*Target="([^"]+)"',
                           z.read('xl/_rels/workbook.xml.rels').decode('utf-8', 'replace')))
    summary, total = {}, 0
    for name, rid in sheets:
        raw = z.read('xl/' + rels[rid].lstrip('/')).decode('utf-8', 'replace')
        for cell, val in re.findall(r'<c r="([A-Z]+\d+)"[^>]*t="e"[^>]*>.*?<v>([^<]*)</v>', raw, re.S):
            total += 1
            loc = summary.setdefault(val, [])
            if len(loc) < 100:
                loc.append(f'{name}!{cell}')
    return total, summary


def recalc(path, timeout=600):
    import win32com.client
    from win32com.client import constants  # noqa: F401
    import pythoncom

    path = os.path.abspath(path)
    if not os.path.exists(path):
        return {'error': f'file not found: {path}'}

    pythoncom.CoInitialize()
    excel = None
    try:
        excel = win32com.client.DispatchEx('Excel.Application')
        excel.Visible = False
        excel.DisplayAlerts = False
        excel.AskToUpdateLinks = False
        excel.EnableEvents = False

        wb = excel.Workbooks.Open(path, UpdateLinks=0, ReadOnly=False)
        # Application.Calculation is only settable once a workbook is open.
        excel.Calculation = XL_CALCULATION_MANUAL
        # Full dependency-tree rebuild, not just a dirty-cell pass.
        excel.CalculateFullRebuild()
        while excel.CalculationState != 0:   # 0 = xlDone
            pass
        wb.Save()
        wb.Close(SaveChanges=False)
    except Exception as e:                     # noqa: BLE001
        return {'error': f'{type(e).__name__}: {e}'}
    finally:
        try:
            if excel is not None:
                excel.Quit()
        except Exception:                      # noqa: BLE001
            pass
        pythoncom.CoUninitialize()

    total_formulas = count_formulas(path)
    total_errors, summary = scan_errors(path)
    return {'status': 'errors_found' if total_errors else 'success',
            'engine': 'Microsoft Excel (COM)',
            'total_formulas': total_formulas,
            'total_errors': total_errors,
            'error_summary': summary}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'usage: python recalc_excel.py <file.xlsx> [timeout]'}))
        sys.exit(1)
    t = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    res = recalc(sys.argv[1], t)
    print(json.dumps(res, indent=2))
    sys.exit(1 if 'error' in res else 0)
