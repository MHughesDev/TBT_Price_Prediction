"""Engineering estimates of how much steel a tank needs (API 650 style).

Price tracks steel WEIGHT, not surface area: shell plate gets thicker with diameter and
liquid height, and never goes below a code minimum. add_physics(tanks) returns phys_* columns.
"""
import numpy as np
import pandas as pd

LB_PER_SQFT_PER_INCH = 0.2836 * 144.0   # steel is 0.2836 lb per cubic inch
COURSE_FT = 8.0                          # height of one ring of shell plate

# allowable stress (psi), weld efficiency, density vs carbon steel, corrosion allowance (in)
GRADE = {
    'CS':    dict(stress=23200.0, weld=0.85, density=1.000, corrosion=0.0625),
    '304SS': dict(stress=20000.0, weld=0.85, density=1.011, corrosion=0.0),
    '316SS': dict(stress=20000.0, weld=0.85, density=1.019, corrosion=0.0),
}


def grade_property(grades, name):
    return np.array([GRADE.get(g, GRADE['CS'])[name] for g in grades], float)


def min_shell_thickness(diameter):
    """API 650 minimum shell thickness (inches) by tank diameter (ft)."""
    return np.select([diameter < 50, diameter < 120, diameter < 200],
                     [0.1875, 0.25, 0.3125], default=0.375)


def shell_weight_lb(diameter, height, grades):
    """Add up the shell one 8 ft ring at a time, each ring as thick as its liquid head needs."""
    stress = grade_property(grades, 'stress')
    weld = grade_property(grades, 'weld')
    corrosion = grade_property(grades, 'corrosion')
    density = grade_property(grades, 'density')
    n_rings = int(min(40, max(1, np.nanmax(np.ceil(height / COURSE_FT)))))
    weight = np.zeros_like(diameter)
    for ring in range(n_rings):
        bottom = ring * COURSE_FT
        ring_height = np.clip(np.minimum(bottom + COURSE_FT, height) - bottom, 0, None)
        head = np.clip(height - bottom - 1.0, 0, None)   # "one-foot method"
        thickness = 2.6 * diameter * head / (stress * weld) + corrosion
        thickness = np.maximum(thickness, min_shell_thickness(diameter))
        weight += np.pi * diameter * ring_height * thickness * LB_PER_SQFT_PER_INCH * density
    return weight


def add_physics(tanks: pd.DataFrame) -> pd.DataFrame:
    diameter = tanks['Diameter (ft)'].clip(lower=1).to_numpy(float)
    height = tanks['Height (ft)'].clip(lower=1).to_numpy(float)
    grades = tanks['Material'].astype(str).to_numpy()
    density = grade_property(grades, 'density')
    slope = tanks['roof_slope'].fillna(0).to_numpy(float)
    has_roof_frame = np.where(tanks['deck_is_open_top'] == 1, 0.0, tanks['deck_has_rafters'])
    liquid_height = tanks['liquid_height_ft'].to_numpy(float)
    liquid_height = np.where(liquid_height > 0, liquid_height, height)
    floor_sqft = np.pi / 4 * diameter ** 2

    out = pd.DataFrame(index=tanks.index)
    out['phys_shell_lb'] = shell_weight_lb(diameter, np.maximum(liquid_height, 1.0), grades)
    out['phys_floor_lb'] = floor_sqft * 0.25 * LB_PER_SQFT_PER_INCH * density
    roof_plate = floor_sqft * np.sqrt(1 + slope ** 2) * 0.1875 * LB_PER_SQFT_PER_INCH * density
    roof_frame = has_roof_frame * floor_sqft * (0.9 + 0.045 * diameter) / 40.0  # grows with span
    out['phys_roof_lb'] = roof_plate + roof_frame
    out['phys_steel_lb'] = out.phys_shell_lb + out.phys_floor_lb + out.phys_roof_lb
    out['phys_log_steel_lb'] = np.log(out.phys_steel_lb.clip(lower=1))
    out['phys_shell_share'] = out.phys_shell_lb / out.phys_steel_lb.clip(lower=1)

    # Is the tank thin enough that the code minimum sets the thickness? This is why $/sqft
    # is U-shaped in size: small tanks pay for plate they don't structurally need.
    stress = grade_property(grades, 'stress')
    design_t = 2.6 * diameter * np.clip(liquid_height - 1, 0, None) / (stress * 0.85)
    min_t = min_shell_thickness(diameter)
    out['phys_t_design_in'] = design_t
    out['phys_t_min_in'] = min_t
    out['phys_t_governing_in'] = np.maximum(design_t, min_t)
    out['phys_min_governs'] = (design_t < min_t).astype(int)
    out['phys_t_ratio'] = design_t / min_t
    out['phys_lb_per_sqft'] = out.phys_steel_lb / tanks['total_area_sqft'].clip(lower=1)

    # Seismic overturning ~ liquid weight x height x ground-motion factor Ss.
    seismic = tanks['Ss'].fillna(0).to_numpy(float)
    liquid_lb = floor_sqft * liquid_height * 62.4
    out['phys_liquid_lb'] = liquid_lb
    out['phys_overturn_moment'] = seismic * liquid_lb * liquid_height * 0.5
    out['phys_anchorage_ratio'] = out.phys_overturn_moment / (diameter ** 2 * out.phys_steel_lb.clip(lower=1))
    out['phys_slenderness'] = liquid_height / np.sqrt(diameter)
    out['phys_hoop_force'] = diameter * liquid_height
    return out
