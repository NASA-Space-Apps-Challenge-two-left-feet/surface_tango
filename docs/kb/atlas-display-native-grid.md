---
status: verified
source: https://docs.xarray.dev/en/stable/user-guide/io.html
accessed: 2026-11-15
quote: "Xarray can’t open just any zarr dataset"
used_in: app.py, scripts/build_regional_cube.py
verified_by: Codex, official Xarray documentation and local pixel round-trip tests
---

# Atlas keeps analysis grids separate from display projection

Xarray uses dimension metadata to interpret Zarr arrays. Atlas preserves each
extracted raster's native pixel-center coordinates in its own Xarray dataset
group. It does not align unrelated grids or invent a temporal dimension.
The map preview reprojects a bounded, strided sample to EPSG:3857 with nearest
neighbor resampling. Pixel inspection reads the native grid instead of the preview.
Missing values remain NaN in arrays and transparent in previews.

Interface references:
- [NASA Worldview](https://worldview.earthdata.nasa.gov/): layer and date exploration.
- [Pangeo CMIP6 access](https://pangeo-data.github.io/pangeo-cmip6-cloud/accessing_data.html):
  Xarray access to cloud Zarr collections used for climate-model data.

Atlas adopts these interaction/storage patterns, not their full scale or dataset coverage.
