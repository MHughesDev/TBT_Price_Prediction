"""Preset tank types.

The raw `Use Type` field has 13 levels with a very long tail (Brine Concentrator n=1,
Agricultural Storage Tank n=3). This collapses them into presets that are large enough to
support a segment-specific model and that group tanks the business considers alike.

Deterministic function of `Use Type`, so it is derivable at serve time and adds no new input.
Mapping supplied by Mason, 2026-09-24.
"""
from __future__ import annotations

USE_TYPE_TO_TANK_TYPE = {
    'Potable Water Storage Tank':      'Potable Water Storage Tank',
    'Water Storage Tank':              'Water Storage Tank',
    'Waste Water Storage Tank':        'Waste Water Storage Tank',
    'Fire Protection Storage Tank':    'Fire Protection Storage Tank',
    'Industrial Storage Silo':         'Silo',
    'Bio Mass Storage Silo':           'Silo',
    'Agricultural Storage Silo':       'Silo',
    'Industrial Storage Tank':         'Waste Water Storage Tank',
    'Bio Mass Storage Tank':           'Waste Water Storage Tank',
    'Petroleum Storage Tank':          'Waste Water Storage Tank',
    'Agricultural Storage Tank':       'Waste Water Storage Tank',
    'Brine Concentrator':              'Waste Water Storage Tank',
    'Energy / Utilities Storage Tank': 'Energy / Utilities Storage Tank',
    'Unknown':                         'Unknown',
    '0':                               '0',
}

TANK_TYPES = sorted(set(USE_TYPE_TO_TANK_TYPE.values()))
FALLBACK = 'Unknown'


def tank_type(use_type) -> str:
    """Map a raw Use Type to its preset. Anything unmapped falls back to 'Unknown' rather than
    silently creating a new one-off segment."""
    if use_type is None:
        return FALLBACK
    s = str(use_type).strip()
    if s in ('', 'nan', 'None', 'NaT'):
        return FALLBACK
    return USE_TYPE_TO_TANK_TYPE.get(s, FALLBACK)


def add_tank_type(df, col='Use Type'):
    df = df.copy()
    df['tank_type'] = df[col].map(tank_type) if hasattr(df[col], 'map') else \
        [tank_type(v) for v in df[col]]
    return df
