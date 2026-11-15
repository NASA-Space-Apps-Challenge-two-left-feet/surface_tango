"use strict";

// Geographic context for the visor. This is not a Surface Tango measurement.
// Esri World Imagery uses row/column order: /tile/{z}/{y}/{x}.
const CONTEXT_BASEMAP_SOURCE_ID = "context-basemap";
const CONTEXT_BASEMAP_TILES = [
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
];
const CONTEXT_BASEMAP_ATTRIBUTION =
  "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community. Geographic context, not a measurement.";

function contextBasemapStyle(fallbackColor) {
  return {
    version: 8,
    sources: {
      [CONTEXT_BASEMAP_SOURCE_ID]: {
        type: "raster",
        tiles: CONTEXT_BASEMAP_TILES,
        tileSize: 256,
        maxzoom: 19,
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
