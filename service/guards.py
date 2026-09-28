"""Refusal and low-confidence rules.

The service declines to answer rather than guessing. A refusal is a product feature: an
estimator who is told "I cannot price this" reaches for judgment, whereas one given a confident
wrong number does not.

Each rule returns (severity, message). Severity is 'refuse' or 'low'.
"""
from __future__ import annotations
import numpy as np

# Envelope measured on the training data (design §11).
MIN_HEIGHT_FT = 3.0          # below this the archive rows are deck/floor/roof replacement jobs
MIN_DIAMETER_FT = 3.0        # quoted as tanks, not tanks
SMALL_AREA_SQFT = 600.0      # only 108 training tanks below this
THIN_GRADES = {'304SS': 258, '316SS': 71}
MAX_INTERVAL_RATIO = 3.0     # hi/lo wider than this is not a usable quote anchor


def check_request(req, bundle_meta=None) -> list:
    """Rules that depend only on the request."""
    out = []
    if req.height_ft < MIN_HEIGHT_FT:
        out.append(('refuse', f'height {req.height_ft:g} ft is below {MIN_HEIGHT_FT:g} ft; rows '
                              f'like this in the archive are deck/floor/roof replacement jobs '
                              f'quoted as tanks, not tanks'))
    if req.diameter_ft < MIN_DIAMETER_FT:
        out.append(('refuse', f'diameter {req.diameter_ft:g} ft is below {MIN_DIAMETER_FT:g} ft'))

    area = np.pi * req.diameter_ft * req.height_ft + 2 * np.pi * (req.diameter_ft / 2) ** 2
    if area < SMALL_AREA_SQFT:
        out.append(('low', f'total area {area:,.0f} sqft is in a thinly populated band '
                           f'(108 training tanks below {SMALL_AREA_SQFT:g} sqft)'))

    if req.material in THIN_GRADES:
        out.append(('low', f'{req.material} has only {THIN_GRADES[req.material]} training rows; '
                           f'grade level is shrunk toward the pooled rate'))

    _, esrc = req.erection_scope()
    if esrc != 'input':
        out.append(('low', 'erection scope was inferred from wage type, which is 93.4% accurate; '
                           'a gate error is worth ~$88K - confirm scope before accepting'))
    _, isrc = req.insulation_scope()
    if isrc != 'input':
        out.append(('low', 'insulation scope was not supplied and is assumed absent'))

    if req.ss is None or req.s1 is None:
        out.append(('low', 'seismic Ss/S1 missing; site effects cannot be modelled'))
    if req.miles_from_tbt is None and req.miles_from_gt is None:
        out.append(('low', 'no plant distance supplied'))
    return out


def check_prediction(bucket, price, lo, hi, drift_alarm=False) -> list:
    """Rules that depend on what came out."""
    out = []
    if lo is not None and hi is not None and lo > 0:
        ratio = hi / lo
        if ratio > MAX_INTERVAL_RATIO:
            out.append(('low', f'{bucket}: 80% interval spans {ratio:.1f}x '
                               f'(${lo:,.0f}-${hi:,.0f}); too wide to anchor a quote'))
    if drift_alarm:
        out.append(('low', f'{bucket}: drift alarm active - the monthly level correction has '
                           f'moved beyond its normal band, a price regime may be changing'))
    return out


def worst(severities) -> str:
    if any(s == 'refuse' for s, _ in severities):
        return 'refused'
    if any(s == 'low' for s, _ in severities):
        return 'low'
    return 'normal'
