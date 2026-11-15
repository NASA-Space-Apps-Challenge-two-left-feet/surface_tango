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
const chapterTools = {
  landslide: "analyze_landslide_kinematics",
  earthquake: "rank_first_aid_barrios",
  flood: "analyze_flood_inundation",
  synthesis: "cross_hazard_synthesis",
};
const resultStates = { live: "Live", cached: "Cached", gate: "Gate result" };
let storyRequest;

function setCurtainLabels(chapter) {
  const labels = chapter === "earthquake" ? quakeLabels : comparisonLabels;
  storyPanels.forEach(({ id }, index) => {
    document.getElementById(`${id}-label`).textContent = labels[index];
  });
  document.getElementById("handle-label-1").textContent = `◀ ${labels[0]} | ${labels[1]} ▶`;
  document.getElementById("handle-label-2").textContent = `◀ ${labels[1]} | ${labels[2]} ▶`;
  return labels;
}

function showStoryResult(state, summary, source = "") {
  storyResult.hidden = false;
  document.getElementById("story-state").textContent = state;
  document.getElementById("story-summary").textContent = summary;
  const citation = document.getElementById("story-source");
  citation.textContent = source;
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
  const tile = new URL(panel.tile_url, location.origin);
  if (!["http:", "https:"].includes(tile.protocol)) return false;
  if (panel.state === "cached") return tile.origin === location.origin;
  return panel.state === "live";
}

function drawMeasuredOverlays(chapter, result) {
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
  showStoryResult("Not cached", `Awaiting approved output from ${chapterTools[chapter]}.`);

  try {
    const response = await fetch("/api/story-results", { signal: request.signal, cache: "no-store" });
    if (response.status === 404) return;
    if (!response.ok) throw new Error("Story results unavailable");
    const results = await response.json();
    if (request.signal.aborted) return;
    const result = results[chapter];
    if (!result) return;
    const state = Object.hasOwn(resultStates, result.state) && resultStates[result.state];
    if (!state || !result.summary?.trim() || !result.source?.trim()) {
      throw new Error("Story result requires a state, summary, and evidence source");
    }
    showStoryResult(state, result.summary, result.source);
    if (Array.isArray(result.bounds) && result.bounds.length === 4) {
      const [west, south, east, north] = result.bounds;
      if (isMapPoint([west, south]) && isMapPoint([east, north]) && west < east && south < north) {
        mapNisar.fitBounds([[west, south], [east, north]], { padding: 40, duration: 0 });
      }
    }
    if (result.state === "gate") {
      resetStoryPanels(labels, state, "See coverage decision");
      return;
    }
    storyPanels.forEach(({ id, map, sourceId }, index) => {
      const panel = result.panels?.[index];
      if (usableTile(panel)) {
        setTileLayer(map, sourceId, panel.tile_url);
        panelStatus(id, resultStates[panel.state], labels[index]);
      }
    });
    drawMeasuredOverlays(chapter, result);
  } catch {
    if (request.signal.aborted) return;
    resetStoryPanels(labels, "Error", "Use Retry in Story map");
    showStoryResult("Error", "Could not load the chapter's approved results.");
  }
}

chapterSelect.addEventListener("change", () => openStoryChapter(chapterSelect.value));
storyRetry.addEventListener("click", () => openStoryChapter(chapterSelect.value));
