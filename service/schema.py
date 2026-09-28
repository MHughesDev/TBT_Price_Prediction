"""Request / response contract for the price prediction service.

One request describes ONE TANK. The service returns five predicted sell prices in dollars,
margin-loaded as stored in history, each with an interval and its drivers.

It never returns freight, tax, or a total. Those are deterministic and belong to the estimating
software, which owns:   grand total = sum(buckets) + freight + tax
(verified on 4,459/4,459 archive rows; no source column holds that sum).
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Optional, Literal
import datetime as _dt

BUCKETS = ['material', 'fabrication', 'construction', 'insul_material', 'insul_construction']

MATERIALS = ('CS', '304SS', '316SS')
WAGE_TYPES = ('Non-Union / Non-Prevailing', 'Prevailing Wage', 'Union Wage',
              'No Erection Included', 'Erection Advisor Only')


class RequestError(ValueError):
    """The request cannot be scored. Distinct from a low-confidence prediction."""


@dataclass
class TankRequest:
    # --- geometry (required)
    diameter_ft: float
    height_ft: float

    # --- material and configuration (required)
    material: str                      # CS | 304SS | 316SS
    use_type: str
    deck_style: Optional[str] = None
    floor_style: Optional[str] = None
    freeboard_in: Optional[float] = None
    usable_capacity: Optional[str] = None      # free text, e.g. "250,000 gal" / "937 tons"
    quantity: int = 1

    # --- scope gates.
    # These are INPUTS, never predictions. The estimator knows them; inference is only
    # 93-95% accurate and a gate error is worth ~$88K (design §4).
    erection_in_scope: Optional[bool] = None
    insulation_selected: Optional[bool] = None

    # --- labour regime (drives construction ~1.75x)
    wage_type: Optional[str] = None

    # --- site
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    ss: Optional[float] = None                 # seismic Ss, derived by the app from location
    s1: Optional[float] = None
    miles_from_tbt: Optional[float] = None
    miles_from_gt: Optional[float] = None

    # --- when the price is being set. Defaults to today.
    # This is the analogue of `Due Date` in the archive: the date the quote is needed back by.
    priced_on: Optional[_dt.date] = None

    def __post_init__(self):
        if self.diameter_ft is None or self.height_ft is None:
            raise RequestError("diameter_ft and height_ft are required")
        for name in ('diameter_ft', 'height_ft'):
            v = getattr(self, name)
            if not isinstance(v, (int, float)) or v != v or v <= 0:
                raise RequestError(f"{name} must be a positive number, got {v!r}")
        if self.material not in MATERIALS:
            raise RequestError(f"material must be one of {MATERIALS}, got {self.material!r}")
        if self.wage_type is not None and self.wage_type not in WAGE_TYPES:
            raise RequestError(f"wage_type must be one of {WAGE_TYPES} or None")
        if self.quantity is None or int(self.quantity) < 1:
            raise RequestError("quantity must be >= 1")
        self.quantity = int(self.quantity)
        if self.priced_on is None:
            self.priced_on = _dt.date.today()
        if isinstance(self.priced_on, str):
            self.priced_on = _dt.date.fromisoformat(self.priced_on)

    # scope resolution -------------------------------------------------------
    def erection_scope(self) -> tuple[bool, str]:
        """(in_scope, source). Falls back to the wage-type lookup, which is only 93.4% accurate,
        and the caller is expected to surface that as low confidence."""
        if self.erection_in_scope is not None:
            return bool(self.erection_in_scope), 'input'
        if self.wage_type in (None, 'No Erection Included', 'Erection Advisor Only'):
            return False, 'wage_type_fallback'
        return True, 'wage_type_fallback'

    def insulation_scope(self) -> tuple[bool, str]:
        if self.insulation_selected is not None:
            return bool(self.insulation_selected), 'input'
        return False, 'assumed_absent'


@dataclass
class BucketPrediction:
    bucket: str
    in_scope: bool
    price: float                      # dollars; 0.0 when out of scope. MEDIAN - quote with this.
    price_expected: float = 0.0       # conditional MEAN. Sum THIS across tanks, not `price`.
    low: Optional[float] = None       # interval bounds, None when out of scope
    high: Optional[float] = None
    interval_pct: Optional[float] = None
    drivers: list = field(default_factory=list)
    confidence: Literal['normal', 'low', 'refused'] = 'normal'
    notes: list = field(default_factory=list)


@dataclass
class PredictionResponse:
    buckets: dict                     # bucket name -> BucketPrediction
    model_version: str
    calibration_version: str
    trained_on: str
    interval_level: float
    warnings: list = field(default_factory=list)
    scope_sources: dict = field(default_factory=dict)

    def total_predicted(self) -> float:
        """Sum of the five MEDIAN prices. Correct for one tank; do NOT aggregate this across
        many tanks - see total_expected()."""
        return sum(b.price for b in self.buckets.values())

    def total_expected(self) -> float:
        """Sum of the five EXPECTED prices (gamma book head). Use this for pipeline or revenue
        forecasting. Measured book error -4.04% vs -6.79% for the sum of medians."""
        return sum((b.price_expected or b.price) for b in self.buckets.values())

    def to_dict(self):
        d = asdict(self)
        d['buckets'] = {k: asdict(v) if not isinstance(v, dict) else v
                        for k, v in self.buckets.items()}
        return d
