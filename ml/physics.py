"""API 650 / AWWA D100 style engineering estimates of tank steel weight.

The point: material price should track STEEL WEIGHT, not surface area. Weight is not
proportional to area because shell thickness is itself a function of D and H, floored by a
diameter-dependent code minimum.

API 650 one-foot method, design shell thickness at the bottom of a course:
    td = 2.6 * D * (H - 1) * G / (Sd * E)        D,H in ft, Sd in psi, td in inches
Minimum shell thickness by nominal diameter (API 650 5.6.1.1):
    D <  50 ft -> 3/16"      50 <= D < 120 -> 1/4"
    120 <= D < 200 -> 5/16"  D >= 200 -> 3/8"
Steel: 0.2836 lb/in^3  ->  40.84 lb per ft^2 per inch of thickness.
"""
import numpy as np
import pandas as pd

LB_PER_SQFT_PER_INCH = 0.2836 * 144.0          # 40.84
COURSE_FT = 8.0                                 # standard plate course height

# allowable design stress (psi) and density ratio by grade
GRADE = {
    'CS':    dict(Sd=23200.0, E=0.85, rho=1.000, ca=0.0625),
    '304SS': dict(Sd=20000.0, E=0.85, rho=1.011, ca=0.0),
    '316SS': dict(Sd=20000.0, E=0.85, rho=1.019, ca=0.0),
}


def _min_shell_t(D):
    return np.select([D < 50, D < 120, D < 200], [0.1875, 0.25, 0.3125], default=0.375)


def shell_weight_lb(D, H, grade, G=1.0, n_courses=None):
    """Sum plate weight course by course, thickness set by the governing rule in each course."""
    D = np.asarray(D, float); H = np.asarray(H, float)
    tmin = _min_shell_t(D)
    Sd = np.array([GRADE.get(g, GRADE['CS'])['Sd'] for g in grade], float)
    E = np.array([GRADE.get(g, GRADE['CS'])['E'] for g in grade], float)
    ca = np.array([GRADE.get(g, GRADE['CS'])['ca'] for g in grade], float)
    rho = np.array([GRADE.get(g, GRADE['CS'])['rho'] for g in grade], float)

    ncrs = int(np.nanmax(np.ceil(np.clip(H, 1, None) / COURSE_FT))) if n_courses is None else n_courses
    ncrs = max(1, min(ncrs, 40))
    w = np.zeros_like(D)
    for i in range(ncrs):
        bot = i * COURSE_FT
        top = np.minimum((i + 1) * COURSE_FT, H)
        hgt = np.clip(top - bot, 0, None)             # this course's height, 0 above the shell
        # design liquid head measured from 1 ft above the bottom of THIS course
        head = np.clip(H - bot - 1.0, 0, None)
        td = 2.6 * D * head * G / (Sd * E) + ca
        t = np.maximum(td, tmin)
        w += np.pi * D * hgt * t * LB_PER_SQFT_PER_INCH * rho
    return w


def floor_weight_lb(D, grade, t_floor=0.25):
    D = np.asarray(D, float)
    rho = np.array([GRADE.get(g, GRADE['CS'])['rho'] for g in grade], float)
    return (np.pi / 4.0) * D ** 2 * t_floor * LB_PER_SQFT_PER_INCH * rho


def roof_weight_lb(D, grade, slope=None, supported=None, t_roof=0.1875):
    """Plate + an allowance for rafters/columns that grows with span."""
    D = np.asarray(D, float)
    rho = np.array([GRADE.get(g, GRADE['CS'])['rho'] for g in grade], float)
    sl = np.nan_to_num(np.asarray(slope, float) if slope is not None else 0.0, nan=0.0)
    plate = (np.pi / 4.0) * D ** 2 * np.sqrt(1 + sl ** 2) * t_roof * LB_PER_SQFT_PER_INCH * rho
    # structural allowance: rafter steel per sqft rises with clear span
    sup = np.nan_to_num(np.asarray(supported, float) if supported is not None else 1.0, nan=1.0)
    struct = sup * (np.pi / 4.0) * D ** 2 * (0.9 + 0.045 * D) / 40.0
    return plate + struct


def add_physics(d):
    """Attach engineering features. Pure function of quote-time inputs."""
    o = pd.DataFrame(index=d.index)
    D = pd.to_numeric(d['Diameter (ft)'], errors='coerce').clip(lower=1).to_numpy()
    H = pd.to_numeric(d['Height (ft)'], errors='coerce').clip(lower=1).to_numpy()
    grade = d['Material'].astype(str).fillna('CS').to_numpy()
    slope = pd.to_numeric(d.get('roof_slope_ratio', pd.Series(0.0, index=d.index)),
                          errors='coerce').fillna(0.0).to_numpy()
    open_top = pd.to_numeric(d.get('deck_is_open_top', pd.Series(0, index=d.index)),
                             errors='coerce').fillna(0).to_numpy()
    has_raft = pd.to_numeric(d.get('deck_has_rafters', pd.Series(1, index=d.index)),
                             errors='coerce').fillna(1).to_numpy()
    # liquid height drives design head; fall back to shell height
    LH = pd.to_numeric(d.get('liquid_height_ft', pd.Series(np.nan, index=d.index)),
                       errors='coerce').to_numpy()
    LH = np.where(np.isfinite(LH) & (LH > 0), LH, H)

    o['phys_shell_lb'] = shell_weight_lb(D, np.maximum(LH, 1.0), grade)
    o['phys_floor_lb'] = floor_weight_lb(D, grade)
    o['phys_roof_lb'] = roof_weight_lb(D, grade, slope, np.where(open_top == 1, 0.0, has_raft))
    o['phys_steel_lb'] = o.phys_shell_lb + o.phys_floor_lb + o.phys_roof_lb
    o['phys_log_steel_lb'] = np.log(o.phys_steel_lb.clip(lower=1))
    o['phys_shell_share'] = o.phys_shell_lb / o.phys_steel_lb.clip(lower=1)

    # design thickness and whether the code minimum governs (this is the U-shape mechanism)
    tmin = _min_shell_t(D)
    Sd = np.array([GRADE.get(g, GRADE['CS'])['Sd'] for g in grade], float)
    td = 2.6 * D * np.clip(LH - 1, 0, None) / (Sd * 0.85)
    o['phys_t_design_in'] = td
    o['phys_t_min_in'] = tmin
    o['phys_t_governing_in'] = np.maximum(td, tmin)
    o['phys_min_governs'] = (td < tmin).astype(int)
    o['phys_t_ratio'] = td / tmin

    # weight per unit area: the quantity a rate table implicitly assumes is constant
    area = pd.to_numeric(d['total_area_sqft'], errors='coerce').clip(lower=1).to_numpy()
    o['phys_lb_per_sqft'] = o.phys_steel_lb / area

    # seismic: API 650 App. E overturning moment ~ mass * height, scaled by Ss
    Ss = pd.to_numeric(d.get('Ss', pd.Series(0.0, index=d.index)), errors='coerce').fillna(0).to_numpy()
    liq_lb = (np.pi / 4.0) * D ** 2 * LH * 62.4
    o['phys_liquid_lb'] = liq_lb
    o['phys_overturn_moment'] = Ss * liq_lb * LH * 0.5
    o['phys_anchorage_ratio'] = o.phys_overturn_moment / (D ** 2 * o.phys_steel_lb.clip(lower=1))
    o['phys_slenderness'] = LH / np.sqrt(D)
    o['phys_hoop_force'] = D * LH
    return o
