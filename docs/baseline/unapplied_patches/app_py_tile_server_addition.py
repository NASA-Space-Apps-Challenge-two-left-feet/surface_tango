# Add to app.py
import io
import numpy as np
import xarray as xr
from PIL import Image
from fastapi import Response
from mcp_servers.cache_guard import ZARR_PATH

@app.get("/api/local-tiles/{domain}/{z}/{x}/{y}.png")
async def serve_local_zarr_tile(domain: str, z: int, x: int, y: int):
    """
    Ultra-fast offline XYZ raster tile generator backed by the local Zarr v3 cube
    so the 3-panel MapLibre GL curtain slider works with zero internet connectivity.
    """
    ds = xr.open_zarr(ZARR_PATH)

    if domain == "landslide":
        arr = np.clip(ds["downslope_disp_mm"].values / 30.0, 0, 1)
        rgba = np.stack([arr * 255, (1 - arr) * 200, np.zeros_like(arr), (arr > 0.15) * 210], axis=-1)
    elif domain == "flood":
        hh_pre = 10 * np.log10(ds["gcov_hhhh_pre"].values + 1e-6)
        hh_post = 10 * np.log10(ds["gcov_hhhh_post"].values + 1e-6)
        diff = hh_post - hh_pre
        open_w = diff < -5.0
        dbl_b = diff > 2.8
        rgba = np.zeros((*diff.shape, 4), dtype=np.uint8)
        rgba[open_w] = [0, 180, 216, 220]     # Cyan for Specular Open Water
        rgba[dbl_b] = [255, 0, 127, 230]      # Magenta for L-band Double-Bounce Flooded Canopy
    elif domain == "earthquake":
        dpm = np.clip((ds["gunw_coherence"].values - ds["coherence_coseismic"].values) / 0.4, 0, 1)
        rgba = np.stack([dpm * 255, (1 - dpm) * 100, np.zeros_like(dpm), (dpm > 0.25) * 220], axis=-1)
    else:  # biomass or cband
        hh = ds["gcov_hhhh_post"].values
        hv = ds["gcov_hvhv_post"].values
        rfdi = np.clip(((hh - hv) / (hh + hv + 1e-6)), 0, 1)
        rgba = np.stack([rfdi * 180, (1 - rfdi) * 220, np.full_like(rfdi, 60), np.full_like(rfdi, 190)], axis=-1)

    img = Image.fromarray(rgba.astype(np.uint8), mode="RGBA").resize((256, 256), Image.Resampling.BILINEAR)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")
