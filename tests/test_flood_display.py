"""Known-answer paint for the open-water overlay. Hand-written 5 by 5 only.

The numbers below are display arithmetic, not observations. They never enter
the cache, a report, or the video. See validation/ALLOWLIST.md.
"""

import numpy as np
import pytest

from mcp_servers.flood_display import display_legend, paint_open_water

# Ramp endpoints in flood_display.py: dark (8, 47, 120), pale (186, 220, 248).
# t = hand / 10. Channel = round(dark + (pale - dark) * t).
# t=0.1 -> (26, 64, 133). t=0.9 -> (168, 203, 235).


def test_interior_ramp_border_and_missing_hand_keep_the_wet_count():
    wet = np.ones((5, 5), dtype=bool)
    hand = np.full((5, 5), 5.0)
    hand[2, 2] = 1.0
    hand[2, 1] = 9.0
    hand[1, 1] = np.nan
    rgba = paint_open_water(wet, hand, 10)

    assert tuple(rgba[2, 2]) == (26, 64, 133, 140)
    assert tuple(rgba[2, 1]) == (168, 203, 235, 140)
    assert int(rgba[2, 2, :3].sum()) < int(rgba[2, 1, :3].sum())
    assert tuple(rgba[0, 0]) == (4, 30, 90, 235)
    assert rgba[0, 0, 3] > rgba[2, 2, 3]
    assert tuple(rgba[1, 1]) == (37, 99, 168, 170)
    assert int(np.count_nonzero(rgba[:, :, 3] > 0)) == 25

    wet[4, 4] = False
    dry = paint_open_water(wet, hand, 10)
    assert dry[4, 4, 3] == 0
    assert int(np.count_nonzero(dry[:, :, 3] > 0)) == int(np.count_nonzero(wet))


def test_missing_hand_or_zero_scale_stays_flat_and_visible():
    wet = np.ones((3, 3), dtype=bool)
    flat = paint_open_water(wet, None, 10)
    assert tuple(flat[1, 1]) == (37, 99, 168, 170)
    assert tuple(flat[0, 0, :3]) == (4, 30, 90)
    assert int(np.count_nonzero(flat[:, :, 3] > 0)) == 9

    zero_scale = paint_open_water(wet, np.ones((3, 3)), 0)
    assert tuple(zero_scale[1, 1]) == (37, 99, 168, 170)
    assert int(np.count_nonzero(zero_scale[:, :, 3] > 0)) == 9


def test_hand_grid_must_match_the_mask():
    wet = np.ones((2, 2), dtype=bool)
    with pytest.raises(ValueError, match="hand grid"):
        paint_open_water(wet, np.ones((2, 3)), 10)


def test_legend_names_hand_and_refuses_a_surveyed_depth():
    shown = display_legend(hand_cached=True, hand_max_m=10)
    assert shown["not_surveyed_depth"] is True
    assert shown["hand_max_m"] == 10.0
    assert "MERIT HAND" in shown["text"]
    assert "not a surveyed inundation depth" in shown["text"]
    assert "Damage class is not classified" in shown["text"]
    assert "GEE MERIT/Hydro/v1_0_1 band hnd" in shown["text"]

    missing = display_legend(hand_cached=False, hand_max_m=10)
    assert missing["hand_cached"] is False
    assert missing["hand_source"] == "not cached"
    assert missing["hand_max_m"] is None
    assert "not a surveyed inundation depth" in missing["text"]
    assert "not cached" in missing["text"]
