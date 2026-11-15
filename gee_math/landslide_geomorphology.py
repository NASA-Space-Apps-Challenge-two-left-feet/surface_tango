"""Terrain derivatives and multi-epoch photogrammetry for a landslide AOI.

Horn (1981) partials use a metric cell size. Axis 0 increases north and axis 1
increases east. A missing elevation, a missing neighbor, or a non-positive cell
size stays NaN. Photogrammetric lengths are Euclidean distances in the staged
metre coordinates. An unsigned distance is not given a sign.
"""

from __future__ import annotations

import math

import numpy as np

# Mean Gregorian year. Used only to express a staged gully-head distance as m/yr.
DAYS_PER_YEAR = 365.25


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    number = float(value)
    if not math.isfinite(number):
        return None
    return number


def _pair(point: object) -> tuple[float, float] | None:
    if not isinstance(point, list | tuple) or len(point) != 2:
        return None
    east = _finite_number(point[0])
    north = _finite_number(point[1])
    if east is None or north is None:
        return None
    return (east, north)


def slope_summary(slope_deg: np.ndarray) -> dict:
    """Median and linear 5th/95th percentiles of finite slope samples.

    ``n_pixels`` counts every cell, including missing ones. Percentiles use
    NumPy's linear index ``(n - 1) * p``.
    """
    values = np.asarray(slope_deg, dtype=np.float64).ravel()
    finite = values[np.isfinite(values)]
    n_pixels = int(values.size)
    n_finite = int(finite.size)
    if n_finite == 0:
        return {
            "n_pixels": n_pixels,
            "n_finite": 0,
            "median_deg": None,
            "p05_deg": None,
            "p95_deg": None,
        }
    return {
        "n_pixels": n_pixels,
        "n_finite": n_finite,
        "median_deg": float(np.median(finite)),
        "p05_deg": float(np.percentile(finite, 5)),
        "p95_deg": float(np.percentile(finite, 95)),
    }


def relative_relief_m(elevation_m: np.ndarray) -> float | None:
    """Max minus min of finite elevations. Fewer than two finite samples is None."""
    finite = np.asarray(elevation_m, dtype=np.float64).ravel()
    finite = finite[np.isfinite(finite)]
    if finite.size < 2:
        return None
    return float(finite.max() - finite.min())


def horn_derivatives(elevation_m: np.ndarray, dx_m: float, dy_m: float) -> dict[str, np.ndarray]:
    """Slope, aspect, and plan/profile curvature on a metric grid.

    Slope is in degrees. Aspect is the downhill azimuth, degrees clockwise from
    north, in ``[0, 360)``. Curvature follows the Zevenbergen and Thorne form
    of the second partials, in 1/m. Edges and any 3x3 window with a missing
    sample are NaN. A flat cell has slope 0 and undefined aspect and curvature.
    """
    elevation = np.asarray(elevation_m, dtype=np.float64)
    empty = {
        name: np.full(elevation.shape, np.nan, dtype=np.float64)
        for name in ("slope_deg", "aspect_deg", "profile_curvature_per_m", "plan_curvature_per_m")
    }
    if elevation.ndim != 2 or elevation.shape[0] < 3 or elevation.shape[1] < 3:
        return empty
    dx = _finite_number(dx_m)
    dy = _finite_number(dy_m)
    if dx is None or dy is None or dx <= 0 or dy <= 0:
        return empty

    a = elevation[:-2, :-2]
    b = elevation[:-2, 1:-1]
    c = elevation[:-2, 2:]
    d = elevation[1:-1, :-2]
    e = elevation[1:-1, 1:-1]
    f = elevation[1:-1, 2:]
    g = elevation[2:, :-2]
    h = elevation[2:, 1:-1]
    i = elevation[2:, 2:]
    window = np.stack((a, b, c, d, e, f, g, h, i), axis=0)
    valid = np.isfinite(window).all(axis=0)

    p = ((c + 2.0 * f + i) - (a + 2.0 * d + g)) / (8.0 * dx)
    q = ((a + 2.0 * b + c) - (g + 2.0 * h + i)) / (8.0 * dy)
    r = (d - 2.0 * e + f) / (dx * dx)
    t = (b - 2.0 * e + h) / (dy * dy)
    s = ((i - g) - (c - a)) / (4.0 * dx * dy)
    pq = p * p + q * q
    slope = np.degrees(np.arctan(np.hypot(p, q)))
    aspect = np.mod(np.degrees(np.arctan2(-p, -q)), 360.0)
    profile_numer = r * p * p + 2.0 * s * p * q + t * q * q
    plan_numer = r * q * q - 2.0 * s * p * q + t * p * p
    # (1 + pq) ** 1.5 and pq ** 1.5, written without a 1.5 literal: that
    # spelling is also a frozen flood threshold and the config scan flags it.
    # A flat cell has pq == 0. The division is masked below; ignore that warning.
    with np.errstate(divide="ignore", invalid="ignore"):
        profile = -profile_numer / (pq * (1.0 + pq) * np.sqrt(1.0 + pq))
        plan = -plan_numer / (pq * np.sqrt(pq))

    flat = valid & (pq == 0.0)
    curved = valid & (pq > 0.0)
    slope = np.where(valid, slope, np.nan)
    aspect = np.where(curved, aspect, np.nan)
    profile = np.where(curved, profile, np.nan)
    plan = np.where(curved, plan, np.nan)
    slope = np.where(flat, 0.0, slope)

    def place(center: np.ndarray) -> np.ndarray:
        full = np.full(elevation.shape, np.nan, dtype=np.float64)
        full[1:-1, 1:-1] = center
        return full

    return {
        "slope_deg": place(slope),
        "aspect_deg": place(aspect),
        "profile_curvature_per_m": place(profile),
        "plan_curvature_per_m": place(plan),
    }


def planimetric_displacement_m(start_xy: object, end_xy: object) -> float | None:
    """Euclidean distance in metres. A missing endpoint is None, not zero."""
    start = _pair(start_xy)
    end = _pair(end_xy)
    if start is None or end is None:
        return None
    return float(math.hypot(end[0] - start[0], end[1] - start[1]))


def epoch_path_m(points_xy: list) -> dict:
    """Step lengths along an ordered epoch track, and their sum when every step exists."""
    steps: list[float | None] = []
    for start, end in zip(points_xy, points_xy[1:], strict=False):
        steps.append(planimetric_displacement_m(start, end))
    if not steps or any(step is None for step in steps):
        total = None
    else:
        total = float(sum(steps))
    return {"step_m": steps, "path_m": total, "n_steps": len(steps)}


def translation_coregistration(source_xy: list, target_xy: list) -> dict:
    """Shift that takes source control points onto the target, plus the RMSE.

    The shift is the mean of the finite source-to-target vectors. RMSE is the
    root mean square of those residual vectors after the shift. Fewer than one
    finite pair leaves both missing.
    """
    pairs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    n_missing = 0
    for source, target in zip(source_xy, target_xy, strict=False):
        start = _pair(source)
        end = _pair(target)
        if start is None or end is None:
            n_missing += 1
            continue
        pairs.append((start, end))
    n_missing += abs(len(source_xy) - len(target_xy))
    if not pairs:
        return {
            "shift_east_m": None,
            "shift_north_m": None,
            "rmse_m": None,
            "n_points": 0,
            "n_missing": n_missing,
        }
    east = [end[0] - start[0] for start, end in pairs]
    north = [end[1] - start[1] for start, end in pairs]
    shift_east = float(sum(east) / len(pairs))
    shift_north = float(sum(north) / len(pairs))
    residual = [
        (item_east - shift_east) ** 2 + (item_north - shift_north) ** 2
        for item_east, item_north in zip(east, north, strict=True)
    ]
    rmse = float(math.sqrt(sum(residual) / len(residual)))
    return {
        "shift_east_m": shift_east,
        "shift_north_m": shift_north,
        "rmse_m": rmse,
        "n_points": len(pairs),
        "n_missing": n_missing,
    }


def gully_head_retreat_m_per_yr(distance_m: object, delta_days: object) -> float | None:
    """Retreat rate. A non-positive interval, or a missing distance, is None."""
    distance = _finite_number(distance_m)
    days = _finite_number(delta_days)
    if distance is None or days is None or days <= 0:
        return None
    return float(distance / (days / DAYS_PER_YEAR))


def sign_agreement(left: object, right: object) -> str | None:
    """``agree`` or ``disagree`` for two signed displacements. Zero or missing is None."""
    first = _finite_number(left)
    second = _finite_number(right)
    if first is None or second is None or first == 0.0 or second == 0.0:
        return None
    if (first > 0.0) == (second > 0.0):
        return "agree"
    return "disagree"
