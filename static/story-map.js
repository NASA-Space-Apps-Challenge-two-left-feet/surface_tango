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
  landslide: "The Aburrá noise-floor verdict is unavailable.",
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

function showStoryResult(state, summary, source = "", provenance = "", factSources = []) {
  storyResult.hidden = false;
  document.getElementById("story-state").textContent = state;
  document.getElementById("story-summary").textContent = summary;
  const citation = document.getElementById("story-source");
  citation.textContent = source;
  citation.title = provenance;
  citation.hidden = !source;
  // Each on-screen number keeps the report section it was parsed from.
  citation.dataset.factSources = factSources.join(" ");
  storyRetry.hidden = state !== "Error";
}

// Numbers come only from /api/pitch-facts, which parses the merged reports.
// This only substitutes display text; it never computes a value.
function renderFacts(template, facts) {
  return template.replace(/\{([a-z_]+(?:\.[a-z0-9_]+)+)\}/g, (placeholder, path) => {
    const node = path.split(".").reduce((value, key) => value?.[key], facts);
    if (node === undefined || node === null) throw new Error(`Missing fact ${placeholder}`);
    return typeof node === "object" ? node.text : String(node);
  });
}

function withFacts(chapter, evidence, facts) {
  if (!evidence) return evidence;
  const summary = renderFacts(evidence.summary, facts);
  const factSources = (evidence.facts ?? []).map(path =>
    path.split(".").reduce((value, key) => value?.[key], facts)?.source).filter(Boolean);
  const chapterFacts = facts[chapter] ?? {};
  return {
    ...evidence,
    summary,
    factSources,
    granule: chapterFacts.granule ?? evidence.granule,
    date: chapterFacts.date ?? evidence.date,
    command: chapterFacts.command ?? evidence.command,
  };
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

function hasStoryEvidence(result) {
  return !!result && Object.hasOwn(resultStates, result.state)
    && typeof result.summary === "string" && result.summary.trim()
    && typeof result.source === "string" && result.source.trim();
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
  if (chapter === "earthquake" && evidence?.ranking_available === true && Array.isArray(result.ranked_barrios)) {
    const barrios = result.ranked_barrios.filter(entry =>
      isMapPoint(entry?.position) && Number.isInteger(entry.rank) && entry.rank > 0
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
    const links = result.links.filter(entry =>
      isMapPoint(entry?.from) && isMapPoint(entry.to) && typeof entry.source === "string" && entry.source.trim()
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
  const value = await response.json();
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("Invalid story input");
  return value;
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
    const [published, staged, sentinel, landslide, reportFacts, bands] = await Promise.allSettled([
      readStoryInput("/static/story-evidence.json", request.signal),
      readStoryInput("/api/story-results", request.signal),
      aoi ? readStoryInput(`/api/sentinel-tiles/${aoi}`, request.signal) : {},
      chapter === "landslide" ? readStoryInput("/api/local-tiles/landslide", request.signal) : null,
      readStoryInput("/api/pitch-facts", request.signal),
      aoi ? readStoryInput(`/api/cache-bands/${aoi}`, request.signal) : {},
    ]);
    if (request.signal.aborted) return;

    let evidence;
    let factsFailed = reportFacts.status === "rejected";
    try {
      evidence = factsFailed ? undefined : withFacts(chapter, published.value?.[chapter], reportFacts.value);
    } catch {
      factsFailed = true;
    }
    const cachedResult = staged.value?.[chapter];
    const hasStagedEvidence = hasStoryEvidence(cachedResult);
    const result = chapter === "earthquake" && evidence?.ranking_available !== true
      ? evidence : hasStagedEvidence ? cachedResult : evidence;
    if (hasStoryEvidence(result)) {
      const provenance = [result.granule, result.command].filter(Boolean).join(" · ");
      showStoryResult(resultStates[result.state], result.summary, result.source, provenance, result.factSources);
    } else if (factsFailed) {
      showStoryResult("Error", "Could not read the measured numbers from the reports.");
    } else if (staged.status === "rejected" || published.status === "rejected") {
      showStoryResult("Error", "Could not load the chapter's evidence.");
    }
    const references = sentinel.value ?? {};
    const water = cachedResult?.open_water;
    fitChapter(result?.bounds ?? water?.bounds ?? references.s2?.bounds ?? references.s1?.bounds);
    const cached = cachedChapterPanels(chapter, references, landslide.value);
    storyPanels.forEach(({ id, map, sourceId }, index) => {
      if (chapter === "earthquake" && index === 2) {
        // C and K stay sealed until the pre-registration freeze, whatever the cache holds.
        const status = bands.value?.bands?.coherence_C?.status ?? "withheld";
        panelStatus(id, "Not cached", `Co-event coherence C/K sealed · manifest: ${status}`);
        return;
      }
      const approved = hasStagedEvidence ? cachedResult.panels?.[index] : null;
      const panel = usableTile(approved) ? approved : cached[index];
      if (usableTile(panel)) {
        const options = panel.bounds ? { bounds: panel.bounds, minzoom: panel.minzoom, maxzoom: panel.maxzoom } : {};
        setTileLayer(map, sourceId, panel.tile_url, options);
        const coverage = Number.isFinite(panel.coverage_pct) ? `${panel.coverage_pct}% of AOI imaged` : "";
        const detail = [labels[index], panel.date, coverage].filter(Boolean).join(" · ");
        panelStatus(id, resultStates[panel.state], detail, (panel.scene_ids ?? panel.granule_ids ?? []).join(", "));
      } else if (chapter === "earthquake" && index === 1) {
        const image = cachedResult?.pre_event_coherence;
        if (image?.url?.startsWith("data:image/png;base64,") && typeof image.granule === "string"
            && Array.isArray(image.corners) && image.corners.length === 4 && image.corners.every(isMapPoint)) {
          setTileLayer(map, sourceId, image.url, { type: "image", url: image.url, coordinates: image.corners });
          panelStatus(id, "Cached", [labels[index], image.dates?.join(" to ")].filter(Boolean).join(" · "), image.granule);
        }
      } else if ((index < 2 && cached[index] !== null && sentinel.status === "rejected")
          || (chapter === "landslide" && index === 2 && landslide.status === "rejected")) {
        panelStatus(id, "Error", `${labels[index]} unavailable`);
      }
    });
    drawMeasuredOverlays(chapter, { ...(hasStagedEvidence ? cachedResult : {}), open_water: water }, evidence);
  } catch {
    if (request.signal.aborted) return;
    resetStoryPanels(labels, "Error", "Use Retry in Story map");
    showStoryResult("Error", "Could not load the chapter's approved results.");
  }
}

chapterSelect.addEventListener("change", () => openStoryChapter(chapterSelect.value));
storyRetry.addEventListener("click", () => openStoryChapter(chapterSelect.value));

// La Mojana is the ratified headline (validation/README.md), so the page opens on it.
// `?chapter=live` keeps mission control; `?chapter=<name>` opens another chapter.
const requestedChapter = new URLSearchParams(location.search).get("chapter") ?? "flood";
if ([...chapterSelect.options].some(option => option.value && option.value === requestedChapter)) {
  chapterSelect.value = requestedChapter;
  openStoryChapter(requestedChapter);
}
