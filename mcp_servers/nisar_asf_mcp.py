# mcp_servers/nisar_asf_mcp.py
import os
from typing import Any

import asf_search as asf
import earthaccess
import rioxarray
from fastmcp import FastMCP
from google.cloud import storage

mcp = FastMCP(name="nisar-asf-subsetter")

GCS_BUCKET = os.environ.get("GCS_NISAR_BUCKET", "spaceapps-medellin-nisar")
earthaccess.login(strategy="netrc")


def _upload_cog_to_gcs(da, local_path: str, blob_name: str) -> str:
    da.rio.to_raster(
        local_path,
        driver="COG",
        compress="DEFLATE",
        predictor=2,
        overview_resampling="AVERAGE",
    )
    client = storage.Client()
    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(blob_name)
    blob.upload_from_filename(local_path)
    return f"gs://{GCS_BUCKET}/{blob_name}"


@mcp.tool
def search_nisar_granules(
    bbox: list[float],
    start_date: str,
    end_date: str,
    product_level: str = "GCOV",
) -> list[dict[str, Any]]:
    """
    Search NASA ASF DAAC for NISAR Level-2 granules (GCOV, GUNW, GOFF) intersecting a bounding box.
    bbox format: [min_lon, min_lat, max_lon, max_lat] (e.g., [-75.70, 6.15, -75.45, 6.40] for Medellin/Bello).
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    wkt = (
        f"POLYGON(({min_lon} {min_lat}, {max_lon} {min_lat}, "
        f"{max_lon} {max_lat}, {min_lon} {max_lat}, {min_lon} {min_lat}))"
    )
    results = asf.geo_search(
        platform=[asf.PLATFORM.NISAR],
        processingLevel=[product_level],
        intersectsWith=wkt,
        start=start_date,
        end=end_date,
    )
    granules = []
    for r in results[:5]:
        props = r.properties
        granules.append(
            {
                "scene_name": props.get("sceneName"),
                "start_time": props.get("startTime"),
                "https_url": props.get("url"),
                "s3_url": props.get("s3Urls", [None])[0],
                "product_level": product_level,
            }
        )
    return granules


@mcp.tool
def stage_nisar_gcov_to_gcs(
    https_url: str,
    scene_name: str,
    bbox: list[float],
    polarizations: list[str] | None = None,
) -> dict[str, str]:
    """
    Zero-download byte-range extraction of NISAR L2 GCOV polarimetric backscatter covariance grids
    (/science/LSAR/GCOV/grids/frequencyA/{pol}) into Cloud-Optimized GeoTIFFs on GCS for GEE ingestion.
    """
    gcs_uris = {}
    for pol in polarizations or ["HHHH", "HVHV"]:
        h5_path = f"/science/LSAR/GCOV/grids/frequencyA/{pol}"
        vsi_uri = f'HDF5:"/vsicurl/{https_url}":{h5_path}'
        da = rioxarray.open_rasterio(vsi_uri, masked=True, chunks="auto")
        da_clipped = da.rio.clip_box(*bbox, crs="EPSG:4326")

        local_cog = f"/tmp/{scene_name}_GCOV_{pol}.tif"
        blob_name = f"nisar_gcov/{scene_name}_{pol}.tif"
        gcs_uris[pol] = _upload_cog_to_gcs(da_clipped, local_cog, blob_name)

    return gcs_uris


@mcp.tool
def stage_nisar_gunw_ionosphere_corrected_to_gcs(
    https_url: str,
    scene_name: str,
    bbox: list[float],
) -> dict[str, str]:
    """
    Extracts NISAR L2 GUNW unwrappedPhase, subtracts the equatorial ionosphericPhaseScreen,
    and exports corrected phase + coherenceMagnitude as COGs on GCS for Landslide & Earthquake agents.
    """
    base_grid = "/science/LSAR/GUNW/grids/frequencyA"
    unw_uri = f'HDF5:"/vsicurl/{https_url}":{base_grid}/unwrappedPhase'
    iono_uri = f'HDF5:"/vsicurl/{https_url}":{base_grid}/ionosphericPhaseScreen'
    coh_uri = f'HDF5:"/vsicurl/{https_url}":{base_grid}/coherenceMagnitude'

    da_unw = rioxarray.open_rasterio(unw_uri, masked=True).rio.clip_box(*bbox, crs="EPSG:4326")
    da_iono = rioxarray.open_rasterio(iono_uri, masked=True).rio.clip_box(*bbox, crs="EPSG:4326")
    da_coh = rioxarray.open_rasterio(coh_uri, masked=True).rio.clip_box(*bbox, crs="EPSG:4326")

    # Remove equatorial dispersive ionospheric phase screen (critical for Colombia latitudes)
    da_corrected_phase = da_unw - da_iono
    da_corrected_phase.rio.write_crs(da_unw.rio.crs, inplace=True)

    phase_gcs = _upload_cog_to_gcs(
        da_corrected_phase,
        f"/tmp/{scene_name}_GUNW_phase_corr.tif",
        f"nisar_gunw/{scene_name}_phase_corr.tif",
    )
    coh_gcs = _upload_cog_to_gcs(
        da_coh,
        f"/tmp/{scene_name}_GUNW_coh.tif",
        f"nisar_gunw/{scene_name}_coh.tif",
    )
    return {"corrected_phase_gcs": phase_gcs, "coherence_gcs": coh_gcs}


if __name__ == "__main__":
    mcp.run()
