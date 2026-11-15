"""Paint the measured open-water mask for the map overlay.

The border is the 4-connected edge of mask value 1. Interior color is MERIT
HAND (height above the nearest drainage) on those same pixels. Darker blue is
lower HAND. This is not a surveyed inundation depth, and a missing HAND value
stays a flat blue so the wet-pixel count does not change.

Color bytes and alpha are display opacity. They are not flood-classifier
thresholds. The scale top is the frozen ``flood.hand_max_m`` passed in by the
caller. Nearest resampling of HAND onto the water grid happens before this
function, and this function does not invent values.
"""

from __future__ import annotations

import numpy as np

# Display bytes only. Not classifier thresholds.
_DARK = np.array([8, 47, 120], dtype=np.float64)
_PALE = np.array([186, 220, 248], dtype=np.float64)
_BORDER_RGB = np.array([4, 30, 90], dtype=np.uint8)
_FLAT_RGB = np.array([37, 99, 168], dtype=np.uint8)
_INTERIOR_ALPHA = 140
_FLAT_ALPHA = 170
_BORDER_ALPHA = 235

HAND_SOURCE = "GEE MERIT/Hydro/v1_0_1 band hnd"


def paint_open_water(water, hand, hand_max_m) -> np.ndarray:
    """Return an HxWx4 uint8 image. Dry pixels stay alpha 0.

    ``hand`` may be ``None`` when the HAND raster is not cached. A non-finite
    HAND sample on a wet pixel is painted flat blue, still with alpha above 0.
    """
    wet = np.asarray(water, dtype=bool)
    if wet.ndim != 2:
        raise ValueError("water mask must be 2-D")
    height, width = wet.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    if not wet.any():
        return rgba

    hand_grid = None if hand is None else np.asarray(hand, dtype=np.float64)
    if hand_grid is not None and hand_grid.shape != wet.shape:
        raise ValueError("hand grid must match the water mask")

    scale = _positive_scale(hand_max_m)
    if hand_grid is None or scale is None:
        rgba[wet, :3] = _FLAT_RGB
        rgba[wet, 3] = _FLAT_ALPHA
    else:
        finite = wet & np.isfinite(hand_grid)
        missing = wet & ~finite
        if finite.any():
            tone = np.clip(hand_grid / scale, 0.0, 1.0)
            rgb = _DARK + (_PALE - _DARK) * tone[..., None]
            rgba[finite, :3] = np.rint(rgb[finite]).astype(np.uint8)
            rgba[finite, 3] = _INTERIOR_ALPHA
        if missing.any():
            rgba[missing, :3] = _FLAT_RGB
            rgba[missing, 3] = _FLAT_ALPHA

    border = wet & ~_interior(wet)
    rgba[border, :3] = _BORDER_RGB
    rgba[border, 3] = _BORDER_ALPHA
    return rgba


def display_legend(*, hand_cached: bool, hand_max_m) -> dict[str, object]:
    """Legend sentences for the flood timeline. The browser copies ``text``."""
    scale = _positive_scale(hand_max_m) if hand_cached else None
    if scale is None:
        text = (
            "Border is the measured open-water mask, value 1. "
            "MERIT HAND is not cached, so wet pixels stay a flat translucent blue. "
            "This is not a surveyed inundation depth. Damage class is not classified."
        )
        return {
            "text": text,
            "hand_cached": False,
            "hand_source": "not cached",
            "hand_max_m": None,
            "not_surveyed_depth": True,
            "damage": "not classified",
        }
    text = (
        "Border is the measured open-water mask, value 1. "
        "Interior blue is MERIT HAND in meters on those pixels. "
        "Darker blue is lower height above the nearest drainage. "
        f"The pale end of the ramp is the frozen gate, {scale:g} m. "
        "This is not a surveyed inundation depth. The interior is translucent. "
        "A wet pixel with no HAND stays flat blue. Damage class is not classified. "
        f"Source: {HAND_SOURCE}."
    )
    return {
        "text": text,
        "hand_cached": True,
        "hand_source": HAND_SOURCE,
        "hand_max_m": scale,
        "not_surveyed_depth": True,
        "damage": "not classified",
    }


def _positive_scale(value) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(number) or number <= 0:
        return None
    return number


def _interior(wet: np.ndarray) -> np.ndarray:
    """Wet pixels whose four neighbors are wet. Outside the array counts as dry."""
    up = np.zeros_like(wet)
    down = np.zeros_like(wet)
    left = np.zeros_like(wet)
    right = np.zeros_like(wet)
    up[1:, :] = wet[:-1, :]
    down[:-1, :] = wet[1:, :]
    left[:, 1:] = wet[:, :-1]
    right[:, :-1] = wet[:, 1:]
    return wet & up & down & left & right
