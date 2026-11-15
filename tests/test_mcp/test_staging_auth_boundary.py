"""Staging-boundary checks stop before raster IO; no granules are invented."""

import inspect

import earthaccess
import pytest

from mcp_servers import nisar_asf_mcp


@pytest.mark.parametrize(
    "name", ["stage_nisar_gcov_to_gcs", "stage_nisar_gunw_ionosphere_corrected_to_gcs"]
)
def test_staging_does_not_reintroduce_netrc_login_before_raster_io(name, monkeypatch):
    def forbidden_login(*args, **kwargs):
        pytest.fail("staging must preserve trunk's GDAL authentication boundary")

    def stop_before_raster_io(*args, **kwargs):
        raise RuntimeError("raster boundary reached")

    monkeypatch.setattr(earthaccess, "login", forbidden_login)
    monkeypatch.setattr(nisar_asf_mcp.rioxarray, "open_rasterio", stop_before_raster_io)
    tool = getattr(nisar_asf_mcp, name)
    raw = inspect.unwrap(getattr(tool, "fn", tool))
    with pytest.raises(RuntimeError, match="raster boundary reached"):
        raw(https_url="", scene_name="", bbox=[])
