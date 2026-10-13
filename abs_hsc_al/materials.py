"""Aluminum material properties and the derived rule factors.

No alloy values are built in. ABS publishes the minimum tensile properties
(unwelded and as-welded) in Part 2, Chapter 5, Section 5 (2-5-5). Enter the
values for the alloy/temper/product form you are actually using, from that
table, so every number in a report traces to the Rules.

Units: N/mm2 (SI) or psi (US, `units="US"`).
"""
from __future__ import annotations

from dataclasses import dataclass

from . import units as UN

E_ALUMINUM = 6.9e4  # N/mm2, 3-2-3/1.5.1(a); the US value (10 x 10^6 psi) is UN.US.E


@dataclass(frozen=True)
class AluminumMaterial:
    name: str
    sigma_y_unwelded: float  # minimum yield, unwelded
    sigma_u_unwelded: float  # minimum ultimate, unwelded
    sigma_y_welded: float  # minimum yield, as-welded
    sigma_u_welded: float  # minimum ultimate, as-welded
    source: str = "user supplied"
    units: str = "SI"

    @property
    def U(self) -> UN.UnitSystem:
        return UN.get(self.units)

    @property
    def E(self) -> float:
        return self.U.E

    def __post_init__(self):
        for f in ("sigma_y_unwelded", "sigma_u_unwelded", "sigma_y_welded", "sigma_u_welded"):
            if getattr(self, f) <= 0:
                raise ValueError(f"{f} must be positive")
        if self.sigma_y_welded > self.sigma_y_unwelded:
            raise ValueError("welded yield cannot exceed unwelded yield")

    # --- design strengths used by the plating/internals tables -------------
    @property
    def sigma_y_design(self) -> float:
        """3-2-3/1.3.1 Table 2 note 1 and 3-2-4/1.3.1 Table 1: welded yield,
        not greater than 70% of the as-welded ultimate."""
        return min(self.sigma_y_welded, 0.7 * self.sigma_u_welded)

    @property
    def sigma_ya(self) -> float:
        """3-2-3/1.3.3(a): unwelded yield, not more than 0.7 of the as-welded
        ultimate (used in q_a and Q)."""
        return min(self.sigma_y_unwelded, 0.7 * self.sigma_u_welded)

    @property
    def tau_yw(self) -> float:
        """3-2-3/1.5.2(b): shear yield = welded yield / sqrt(3)."""
        return self.sigma_y_welded / 3 ** 0.5

    @property
    def q_a(self) -> float:
        """3-2-3/1.3.3(a): qa = 115 / sigma_ya (SI), 17000 / sigma_ya (US, psi)."""
        return self.U.q5_n / self.sigma_ya

    @property
    def Q(self) -> float:
        """3-2-1/1.1.1: Q = 0.9 + q5, not less than Q0.
        q5 = 115/sigma_y ; Q0 = 635/(sigma_y + sigma_u)
        sigma_y: unwelded yield (<= 0.7 sigma_u) ; sigma_u: as-welded ultimate."""
        sy = self.sigma_ya
        q5 = self.U.q5_n / sy  # 115 / sigma_y (SI), 17000 / sigma_y (US)
        q0 = self.U.Q0_n / (sy + self.sigma_u_welded)  # 635 / (sy + su) (SI), 92000 / (sy + su) (US)
        return max(0.9 + q5, q0)

    @classmethod
    def from_dict(cls, d: dict, units: str = "SI") -> "AluminumMaterial":
        if "alloy" in d:  # library lookup: {"alloy": "5083-H116", "product": "plate", "thickness_mm": 8}  (inches if US)
            from .alloys import lookup
            d = lookup(d["alloy"], d.get("product", "plate"), float(d["thickness_mm"]), units)
        keys = ("name", "sigma_y_unwelded", "sigma_u_unwelded", "sigma_y_welded", "sigma_u_welded")
        missing = [k for k in keys if k not in d]
        if missing:
            raise ValueError(f"material is missing {missing}; take values from ABS 2-5-5")
        return cls(**{k: d[k] for k in keys}, source=d.get("source", "user supplied"), units=UN.get(units).name)
