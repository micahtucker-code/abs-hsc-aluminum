"""Rule factors that the Rules give only as graphs (FD, Kv, Fv, F1, M, shear F1/F2).

The graphs cannot be read reliably from the text, so this program ships no
curve data. Provide each factor one of two ways:

  1. a direct value in the input JSON (e.g. "FD": 0.62), or
  2. a curve, digitised by you from the Rule figure, in the "curves" block:
        "curves": {"FD": {"x": [0.001, 0.01, 0.1, 1.0], "y": [1.0, 0.8, 0.5, 0.4]}}

Curves are linearly interpolated and clamped at the ends.
"""
from __future__ import annotations

from bisect import bisect_right

# What each factor's abscissa is, for error messages (Rule figure references).
FACTOR_X = {
    "FD": "AD/AR  (3-2-2/1.1.3 FIGURE 3)",
    "Kv": "x/L position along length  (3-2-2/1.1.3 FIGURE 4)",
    "Fv": "x/L position along length  (3-2-2/1.1.3 FIGURE 5)",
    "F1_wetdeck": "wet deck position  (3-2-2/3.5 FIGURE 6)",
    "M": "x/L  (3-2-1/1.3 FIGURE 2)",
    "F1_shear": "x/L  (3-2-1/1.9.2 FIGURE 3)",
    "F2_shear": "x/L  (3-2-1/1.9.2 FIGURE 4)",
}


class Curve:
    def __init__(self, x: list[float], y: list[float]):
        if len(x) != len(y) or len(x) < 2:
            raise ValueError("curve needs >= 2 points with equal x and y lengths")
        if any(b <= a for a, b in zip(x, x[1:])):
            raise ValueError("curve x values must be strictly increasing")
        self.x, self.y = list(x), list(y)

    def __call__(self, v: float) -> float:
        if v <= self.x[0]:
            return self.y[0]
        if v >= self.x[-1]:
            return self.y[-1]
        i = bisect_right(self.x, v)
        x0, x1, y0, y1 = self.x[i - 1], self.x[i], self.y[i - 1], self.y[i]
        return y0 + (y1 - y0) * (v - x0) / (x1 - x0)


class Factors:
    """Resolves a figure-based factor from an override, else from a curve."""

    def __init__(self, curves: dict | None = None):
        self.curves = {k: Curve(**v) for k, v in (curves or {}).items()}

    def resolve(self, name: str, x: float | None, override: float | None) -> float:
        if override is not None:
            return float(override)
        if name in self.curves and x is not None:
            return self.curves[name](x)
        raise ValueError(
            f"No value for factor {name}. Supply it directly, or add a digitised "
            f"curve under 'curves.{name}'. Abscissa: {FACTOR_X.get(name, '?')}."
        )
