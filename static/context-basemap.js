"use strict";

// Geographic context for the visor. This is not a Surface Tango measurement.
// Tiles are cut from the cached Sentinel-2 cloud-free median. Same-origin XYZ.
const CONTEXT_BASEMAP_SOURCE_ID = "context-basemap";
const CONTEXT_BASEMAP_TILES = ["/api/context-basemap/{z}/{x}/{y}.png"];
const CONTEXT_BASEMAP_ATTRIBUTION =
  "Sentinel-2 cloud-free median. Geographic context, not a measurement. Unobserved pixels stay dark.";

function contextBasemapStyle(fallbackColor) {
  return {
    version: 8,
    sources: {
      [CONTEXT_BASEMAP_SOURCE_ID]: {
        type: "raster",
        tiles: CONTEXT_BASEMAP_TILES,
        tileSize: 256,
        maxzoom: 15,
        attribution: CONTEXT_BASEMAP_ATTRIBUTION,
      },
    },
    layers: [
      { id: "background", type: "background", paint: { "background-color": fallbackColor } },
      {
        id: CONTEXT_BASEMAP_SOURCE_ID,
        type: "raster",
        source: CONTEXT_BASEMAP_SOURCE_ID,
      },
    ],
  };
}
