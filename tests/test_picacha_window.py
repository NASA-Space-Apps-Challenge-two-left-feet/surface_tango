"""Known-answer checks for a native-grid parent window. Not a cache observation."""

from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_bounds

from scripts.window_parent_cache import read_native_window


def test_native_window_copies_the_addressed_cells(tmp_path: Path):
    """A 4 by 4 grid of 0..15. The box [1, 1, 3, 3] addresses the center four cells.

    Pixel edges are 1 degree. Row 0 is the north edge. Columns 1 and 2, rows 1
    and 2, are the values 5, 6, 9 and 10. No other cell is written.
    """
    source = np.arange(16, dtype=np.float32).reshape(4, 4)
    raster_file = tmp_path / "parent.tif"
    transform = from_bounds(0, 0, 4, 4, 4, 4)
    with rasterio.open(
        raster_file,
        "w",
        driver="GTiff",
        height=4,
        width=4,
        count=1,
        dtype="float32",
        crs="EPSG:4326",
        transform=transform,
    ) as dataset:
        dataset.write(source, 1)
    window, window_transform, crs = read_native_window(raster_file, [1, 1, 3, 3])
    assert crs == "EPSG:4326"
    assert window.shape == (2, 2)
    assert np.array_equal(window, np.array([[5, 6], [9, 10]], dtype=np.float32))
    assert window_transform.c == 1
    assert window_transform.f == 3
