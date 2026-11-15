// Approved validation outputs are read from the shared cache via /api/story-results.
// Each chapter key maps to {summary, source, state, bounds?, panels?, ranked_barrios?, links?}.
// See status/frontend-video.md for the data handoff.
const chapterSelect = document.getElementById("story-chapter");
const storyResult = document.getElementById("story-result");
const storyRetry = document.getElementById("story-retry");
const physicsInspector = document.getElementById("physics-inspector");
const storyPanels = [
  { id: "optical", map: mapOptical, sourceId: "s2-optical" },
  { id: "cband", map: mapCBand, sourceId: "s1-cband" },
  { id: "nisar", map: mapNisar, sourceId: "nisar-active-raster" },
];
const comparisonLabels = ["Sentinel-2 optical", "Sentinel-1 C-band", "NISAR L-band"];
const quakeLabels = ["Sentinel-2 post-event optical", "NISAR pre-event coherence", "NISAR co-event coherence loss"];
const chapterAreas = { landslide: "aburra", earthquake: "eje_cafetero", flood: "mojana" };
const pendingResults = {
  landslide: "Aburrá displacement is available as context. The noise-floor verdict is pending.",
  earthquake: "The quake coverage decision is pending.",
  flood: "The La Mojana result is unavailable.",
  synthesis: "No measured cross-hazard links have been published.",
};
const resultStates = { live: "Live", cached: "Cached", gate: "Gate result" };
let storyRequest;

function setCurtainLabels(chapter) {
  const labels = chapter === "earthquake" ? quakeLabels : comparisonLabels;
  storyPanels.forEach(({ id }, index) => {
    document.getElementById(`${id}-label`).textContent = labels[index];
  });
  const short = chapter === "earthquake" ? ["Optical", "Pre-event", "Co-event"] : ["Optical", "C-band", "L-band"];
  document.getElementById("handle-label-1").textContent = `◀ ${short[0]} | ${short[1]} ▶`;
  document.getElementById("handle-label-2").textContent = `◀ ${short[1]} | ${short[2]} ▶`;
  return labels;
}

function showStoryResult(state, summary, source = "", provenance = "") {
  storyResult.hidden = false;
  document.getElementById("story-state").textContent = state;
  document.getElementById("story-summary").textContent = summary;
  const citation = document.getElementById("story-source");
  citation.textContent = source;
  citation.title = provenance;
  citation.hidden = !source;
  storyRetry.hidden = state !== "Error";
}

function resetStoryPanels(labels, state, detail) {
  storyPanels.forEach(({ id, map, sourceId }, index) => {
    setTileLayer(map, sourceId, null);
    panelStatus(id, state, `${labels[index]} · ${detail}`);
  });
}

function isMapPoint(point) {
  return Array.isArray(point) && point.length === 2 && point.every(Number.isFinite)
    && Math.abs(point[0]) <= 180 && Math.abs(point[1]) <= 85;
}

function usableTile(panel) {
  if (typeof panel?.tile_url !== "string" || !panel.tile_url.trim()) return false;
  let tile;
  try { tile = new URL(panel.tile_url, location.origin); } catch { return false; }
  if (!["http:", "https:"].includes(tile.protocol)) return false;
  if (panel.state === "cached") return tile.origin === location.origin;
  return panel.state === "live";
}

function drawMeasuredOverlays(chapter, result, evidence) {
  const water = result.open_water;
  if (chapter === "flood" && water && evidence && !usableTile(result.panels?.[2])
      && water.granule === evidence.granule && water.date === evidence.date
      && water.geojson?.type === "FeatureCollection" && water.geojson.features?.length) {
    deckOverlay.setProps({ layers: [new deck.GeoJsonLayer({
      id: "measured-open-water",
      data: water.geojson,
      stroked: false,
      getFillColor: [14, 165, 233, 220],
    })] });
    panelStatus("nisar", "Cached", `Open water · ${water.date}`, water.granule);
    return;
  }
  if (chapter === "earthquake" && Array.isArray(result.ranked_barrios)) {
    const barrios = result.ranked_barrios.filter(({ position, rank }) =>
      isMapPoint(position) && Number.isInteger(rank) && rank > 0
    );
    deckOverlay.setProps({ layers: [new deck.ColumnLayer({
      id: "ranked-barrios",
      data: barrios,
      getPosition: barrio => barrio.position,
      getElevation: barrio => 1 / barrio.rank,
      elevationScale: 500,
      getFillColor: [239, 68, 68, 220],
      radius: 180,
      extruded: true,
    })] });
  } else if (chapter === "synthesis" && Array.isArray(result.links)) {
    const links = result.links.filter(({ from, to, source }) =>
      isMapPoint(from) && isMapPoint(to) && typeof source === "string" && source.trim()
    );
    deckOverlay.setProps({ layers: [new deck.ArcLayer({
      id: "measured-hazard-links",
      data: links,
      getSourcePosition: link => link.from,
      getTargetPosition: link => link.to,
      getSourceColor: [56, 189, 248],
      getTargetColor: [249, 115, 22],
      getWidth: 2,
    })] });
  }
}

async function readStoryInput(path, signal) {
  const response = await fetch(path, { signal, cache: "no-store" });
  if (response.status === 404) return {};
  if (!response.ok) throw new Error("Story input unavailable");
  return response.json();
}

function cachedChapterPanels(chapter, references, los) {
  const panels = [references.s2, references.s1, los];
  if (chapter === "earthquake") {
    // The middle panel changes to NISAR pre-event coherence in this layout.
    panels[1] = null;
  }
  return panels;
}

function fitChapter(bounds) {
  if (!Array.isArray(bounds) || bounds.length !== 4) return;
  const [west, south, east, north] = bounds;
  if (isMapPoint([west, south]) && isMapPoint([east, north]) && west < east && south < north) {
    mapNisar.jumpTo({ pitch: 0, bearing: 0 });
    mapNisar.fitBounds([[west, south], [east, north]], { padding: 40, duration: 0 });
  }
}

function openLiveView() {
  if (!activeStory) return;
  storyRequest?.abort();
  activeStory = "";
  chapterSelect.value = "";
  storyResult.hidden = true;
  physicsInspector.style.display = "";
  maps.forEach(map => map.resize());
  setCurtainLabels("");
  mapNisar.jumpTo(INITIAL_VIEW);
  restoreReferencePanels();
  refreshDeckHotspots();
  inspectHazardDomain(selectedDomain);
}

async function openStoryChapter(chapter) {
  if (!chapter) {
    openLiveView();
    return;
  }
  storyRequest?.abort();
  const request = new AbortController();
  storyRequest = request;
  activeStory = chapter;
  ++currentInspection;
  physicsInspector.style.display = "none";
  maps.forEach(map => map.resize());
  const labels = setCurtainLabels(chapter);
  deckOverlay.setProps({ layers: [] });
  resetStoryPanels(labels, "Not cached", "Awaiting chapter tiles");
  showStoryResult("Not cached", pendingResults[chapter]);

  try {
    const aoi = chapterAreas[chapter];
    const [evidenceByChapter, results, references, los] = await Promise.all([
      readStoryInput("/static/story-evidence.json", request.signal),
      readStoryInput("/api/story-results", request.signal),
      aoi ? readStoryInput(`/api/sentinel-tiles/${aoi}`, request.signal) : {},
      chapter === "landslide" ? readStoryInput("/api/local-tiles/landslide", request.signal) : null,
    ]);
    if (request.signal.aborted) return;

    const evidence = evidenceByChapter[chapter];
    const result = { ...evidence, ...results[chapter] };
    const state = Object.hasOwn(resultStates, result.state) && resultStates[result.state];
    if (state && result.summary?.trim() && result.source?.trim()) {
      showStoryResult(state, result.summary, result.source, [evidence?.granule, evidence?.command].filter(Boolean).join(" · "));
    }
    fitChapter(result.bounds ?? result.open_water?.bounds ?? references.s2?.bounds ?? references.s1?.bounds);
    const cached = cachedChapterPanels(chapter, references, los);
    storyPanels.forEach(({ id, map, sourceId }, index) => {
      const approved = result.panels?.[index];
      const panel = usableTile(approved) ? approved : cached[index];
      if (usableTile(panel)) {
        const options = panel.bounds ? { bounds: panel.bounds, minzoom: panel.minzoom, maxzoom: panel.maxzoom } : {};
        setTileLayer(map, sourceId, panel.tile_url, options);
        const detail = [labels[index], panel.date].filter(Boolean).join(" · ");
        panelStatus(id, resultStates[panel.state], detail, (panel.scene_ids ?? panel.granule_ids ?? []).join(", "));
      } else if (chapter === "earthquake" && index === 1) {
        const image = result.pre_event_coherence;
        if (image?.url?.startsWith("data:image/png;base64,") && typeof image.granule === "string"
            && Array.isArray(image.corners) && image.corners.length === 4 && image.corners.every(isMapPoint)) {
          setTileLayer(map, sourceId, image.url, { type: "image", url: image.url, coordinates: image.corners });
          panelStatus(id, "Cached", [labels[index], image.dates?.join(" to ")].filter(Boolean).join(" · "), image.granule);
        }
      } else if (chapter === "earthquake" && index === 2) {
        panelStatus(id, "Not cached", "Co-event coherence withheld");
      }
    });
    drawMeasuredOverlays(chapter, result, evidence);
  } catch {
    if (request.signal.aborted) return;
    resetStoryPanels(labels, "Error", "Use Retry in Story map");
    showStoryResult("Error", "Could not load the chapter's approved results.");
  }
}

chapterSelect.addEventListener("change", () => openStoryChapter(chapterSelect.value));
storyRetry.addEventListener("click", () => openStoryChapter(chapterSelect.value));
