// --- 6. Automated 5-Chapter Story Map Tour & Curtain Choreographer ---

const STORY_CHAPTERS = [
  {
    id: 0,
    domain: "biomass",
    coords_label: "6.345°N, 75.525°W | Vereda El Carmelo / Upper Eastern Escarpment (2,480m)",
    camera: { center: [-75.525, 6.345], zoom: 13.5, pitch: 54, bearing: -28, duration: 2400 },
    curtains: { split1: 22, split2: 46 }, // Widens NISAR L-band panel to 54% while showing cloudy S2 & saturated S1
    duration_ms: 14000,
    show_cascading_arcs: false,
    title_en: "1. Root-Zone Trigger: High-Andean Biomass Degradation (NISAR GCOV HV)",
    title_es: "1. Detonante Forestal: Pérdida de Biomasa Altoandina (NISAR GCOV HV)",
    narrative_en: "Our waltz begins on the upper eastern ridges above Bello. Andean clouds block Sentinel-2 (left) and C-band saturates at 60 Mg/ha (center). NISAR's 24 cm L-band (right) penetrates foliage to measure trunk/branch volume scattering (HV), detecting 612.8 tC of forest loss (RFDI > 0.55) that destabilizes root cohesion.",
    narrative_es: "Iniciamos en los escarpes orientales sobre Bello. Las nubes bloquean Sentinel-2 (izq.) y la banda C se satura en el dosel (centro). La banda L de NISAR (24 cm, der.) penetra el follaje midiendo dispersión volumétrica HV en troncos, detectando 612.8 tC de pérdida forestal (RFDI > 0.55) que reduce la cohesión radicular.",
    radar_badge: "📡 Radar Driver: L-Band HV Volume Scattering + GEDI L4A GBDT Regression (WFR_L/C)"
  },
  {
    id: 1,
    domain: "landslide",
    coords_label: "6.332°N, 75.542°W | Bello Oriental Hillslopes & La Gabriela Corridor (1,890m)",
    camera: { center: [-75.542, 6.332], zoom: 14.1, pitch: 60, bearing: 35, duration: 2600 },
    curtains: { split1: 15, split2: 32 }, // Sweeps NISAR L-band open across 68% of screen to showcase GUNW fringes
    duration_ms: 16000,
    show_cascading_arcs: false,
    title_en: "2. Slope Kinematics: 22.4 mm Rotational Creep under 145 mm Rain (NISAR GUNW)",
    title_es: "2. Cinemática de Laderas: Reptación de 22.4 mm bajo 145 mm de Lluvia (NISAR GUNW)",
    narrative_en: "Moving downslope into Bello's steep residential hillsides: C-band InSAR completely decorrelates over tropical vegetation. NISAR L-band GUNW (ionosphere & troposphere corrected) maintains coherence (γ = 0.61) off the soil beneath trees, projecting 22.4 mm of creep onto bare-earth FABDEM slopes under 145 mm of 15-day CHIRPS rain.",
    narrative_es: "Descendiendo hacia las laderas de Bello: InSAR en banda C pierde coherencia por la vegetación. NISAR GUNW en banda L (corregido por ionosfera y troposfera) mantiene coherencia (γ = 0.61) en el suelo bajo los árboles, proyectando 22.4 mm de reptación sobre pendientes FABDEM con 145 mm de lluvia CHIRPS.",
    radar_badge: "📡 Radar Driver: d_LOS = -(λ_L · Δφ_corr)/4π projected onto 3D FABDEM (u_LOS · u_slope)"
  },
  {
    id: 2,
    domain: "flood",
    coords_label: "6.308°N, 75.558°W | Río Medellín & Quebrada La García Confluence (1,440m)",
    camera: { center: [-75.558, 6.308], zoom: 13.8, pitch: 48, bearing: -10, duration: 2400 },
    curtains: { split1: 28, split2: 55 }, // Balanced view comparing C-band open water vs L-band sub-canopy double bounce
    duration_ms: 15000,
    show_cascading_arcs: false,
    title_en: "3. Valley Inundation: Specular Open Water vs. Sub-Canopy Double-Bounce (GCOV)",
    title_es: "3. Inundación Aluvial: Reflexión Especular vs. Doble Rebote bajo Dosel (GCOV)",
    narrative_en: "At the valley floor along Río Medellín and Quebrada La García, water's high dielectric constant (ε_r ≈ 80) creates two distinct radar signatures: Cyan marks open-channel specular reflection (-7.2 dB HH drop), while Magenta reveals 31.2 ha of hidden sub-canopy flooding via dihedral water-to-trunk double-bounce (+4.1 dB HH surge).",
    narrative_es: "En el fondo del valle del Río Medellín y la Quebrada La García, la alta constante dieléctrica del agua (ε_r ≈ 80) genera dos firmas: Cian muestra reflexión especular en aguas abiertas (-7.2 dB HH) y Magenta revela 31.2 ha de inundación bajo árboles mediante doble rebote agua-tronco (+4.1 dB HH).",
    radar_badge: "📡 Radar Driver: Freeman C2 Covariance Decomposition (Specular -5.5dB vs Dihedral +3.0dB HH)"
  },
  {
    id: 3,
    domain: "earthquake",
    coords_label: "6.295°N, 75.572°W | Dense Urban Infrastructure & Romeral Fault System (1,510m)",
    camera: { center: [-75.572, 6.295], zoom: 13.9, pitch: 56, bearing: -42, duration: 2400 },
    curtains: { split1: 20, split2: 42 },
    duration_ms: 13000,
    show_cascading_arcs: false,
    title_en: "4. Urban Vulnerability: Coherence Damage Proxy Map & VIDA Footprints (GUNW + GOFF)",
    title_es: "4. Vulnerabilidad Urbana: Mapa Proxy de Daño (DPM) y Huellas VIDA (GUNW + GOFF)",
    narrative_en: "Scanning dense urban commune footprints across northwestern Medellín and Bello: our Seismic Agent evaluates Z-score interferometric coherence loss (Δγ DPM) fused with Google-Microsoft-OSM VIDA building polygons and WorldPop density, ready to pinpoint collapsed structures and near-fault GOFF slip within minutes of a tremor.",
    narrative_es: "Evaluando la infraestructura urbana densa entre Medellín y Bello: el Agente Sísmico calcula la caída de coherencia interferométrica (Δγ DPM) sobre las edificaciones del catálogo comunitario VIDA y WorldPop, listo para identificar colapsos estructurales y desplazamiento GOFF minutos después de un sismo.",
    radar_badge: "📡 Radar Driver: ARIA Z-Score Coherence Loss (Δγ >= 0.28) + L2 GOFF 3D Pixel Offsets"
  },
  {
    id: 4,
    domain: "landslide",
    coords_label: "6.322°N, 75.548°W | Full Aburrá Basin Cascading Multi-Hazard Synthesis",
    camera: { center: [-75.548, 6.322], zoom: 12.5, pitch: 58, bearing: -22, duration: 2800 },
    curtains: { split1: 12, split2: 24 }, // Opens NISAR + 3D Deck.gl Cascading Arcs across 76% of the viewport
    duration_ms: 18000,
    show_cascading_arcs: true,
    title_en: "5. Cross-Hazard Agent Synthesis: The Cascading Waltz of Surface Change",
    title_es: "5. Síntesis Multi-Agente: El Vals en Cascada de Amenazas Compuestas",
    narrative_en: "Here the Cross-Hazard Synthesis Agent connects all four NISAR domains into a single physical cascade (glowing 3D arcs): Upper-watershed deforestation (Green, 612 tC) reduces root strength on 34° slopes, accelerating 22.4 mm of L-band InSAR hillside creep (Orange) under 145 mm rain, threatening sediment damming and flash flooding (Cyan/Magenta) across urban Bello.",
    narrative_es: "Aquí el Agente de Síntesis conecta los 4 dominios de NISAR en una cascada física (arcos 3D): la deforestación en la cuenca alta (Verde, 612 tC) debilita las raíces en pendientes de 34°, acelerando 22.4 mm de reptación InSAR (Naranja) bajo 145 mm de lluvia, amenazando con represamiento y avenida torrencial (Cian/Magenta) hacia Bello.",
    radar_badge: "🧠 Multi-Agent Synthesis: Biomass HV Loss ➔ GUNW Slope Creep ➔ GCOV Torrencial Flood Risk"
  }
];

let currentChapterIdx = 0;
let autoPlayTimer = null;
let progressInterval = null;
let diagnosticRgbMode = false;

// Smoothly animate the 3-panel curtain dividers (split1 and split2) over 900ms
function animateCurtainsTo(targetSplit1, targetSplit2, duration = 900) {
  const startSplit1 = split1;
  const startSplit2 = split2;
  const startTime = performance.now();

  function step(now) {
    const t = Math.min(1, (now - startTime) / duration);
    // Ease-in-out cubic
    const ease = t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
    split1 = startSplit1 + (targetSplit1 - startSplit1) * ease;
    split2 = startSplit2 + (targetSplit2 - startSplit2) * ease;
    updateCurtainClips();
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// Upgrade Deck.gl overlay to render 3D Cascading Hazard Arcs during Chapter 5
function updateDeckTourLayers(showCascadingArcs, activeDomain) {
  const data = Object.values(hazardReportsStore);
  const colorMap = {
    landslide: [249, 115, 22, 235],
    flood: [56, 189, 248, 235],
    earthquake: [239, 68, 68, 235],
    biomass: [34, 197, 94, 235]
  };

  const layers = [
    new deck.ColumnLayer({
      id: "hazard-hotspots-3d",
      data,
      diskResolution: 24,
      radius: 250,
      extruded: true,
      pickable: true,
      elevationScale: 20,
      getPosition: d => d.hotspot_coordinates,
      getFillColor: d => colorMap[d.domain] || [56, 189, 248, 220],
      getElevation: d => (d.domain === activeDomain || showCascadingArcs) ? 135 : 65,
      onClick: ({ object }) => {
        if (object) inspectHazardDomain(object.domain);
      }
    }),
    new deck.ScatterplotLayer({
      id: "active-hotspot-halo",
      data: showCascadingArcs ? data : data.filter(d => d.domain === activeDomain),
      getPosition: d => d.hotspot_coordinates,
      getRadius: 580,
      stroked: true,
      filled: true,
      lineWidthMinPixels: 3,
      getFillColor: d => [...(colorMap[d.domain] || [56, 189, 248]).slice(0, 3), 45],
      getLineColor: d => [...(colorMap[d.domain] || [56, 189, 248]).slice(0, 3), 255]
    })
  ];

  // In Chapter 5 (Cascading Synthesis), draw glowing 3D parabolic arcs connecting the physical hazard chain
  if (showCascadingArcs) {
    const cascadeLinks = [
      {
        name: "Deforestation -> Slope Instability",
        source: hazardReportsStore.biomass.hotspot_coordinates,    // [-75.525, 6.345] Upper Watershed
        target: hazardReportsStore.landslide.hotspot_coordinates,  // [-75.542, 6.332] Bello Steep Slope
        sourceColor: [34, 197, 94],
        targetColor: [249, 115, 22]
      },
      {
        name: "Slope Failure -> Tributary Damming & Flood",
        source: hazardReportsStore.landslide.hotspot_coordinates,  // [-75.542, 6.332] Bello Steep Slope
        target: hazardReportsStore.flood.hotspot_coordinates,      // [-75.558, 6.308] Rio Medellin / La Garcia
        sourceColor: [249, 115, 22],
        targetColor: [56, 189, 248]
      },
      {
        name: "Seismic Trigger -> Urban & Slope Decorrelation",
        source: hazardReportsStore.earthquake.hotspot_coordinates, // [-75.572, 6.295] Fault / Urban Zone
        target: hazardReportsStore.landslide.hotspot_coordinates,
        sourceColor: [239, 68, 68],
        targetColor: [249, 115, 22]
      }
    ];

    layers.push(
      new deck.ArcLayer({
        id: "cascading-hazard-arcs",
        data: cascadeLinks,
        getSourcePosition: d => d.source,
        getTargetPosition: d => d.target,
        getSourceColor: d => d.sourceColor,
        getTargetColor: d => d.targetColor,
        getWidth: 6,
        getHeight: 0.65,
        greatCircle: false
      })
    );
  }

  deckOverlay.setProps({ layers });
}

function goToStoryChapter(idx) {
  currentChapterIdx = (idx + STORY_CHAPTERS.length) % STORY_CHAPTERS.length;
  const ch = STORY_CHAPTERS[currentChapterIdx];

  // 1. Update Story Pill Highlights
  const pills = document.querySelectorAll("#story-step-pills .story-pill");
  pills.forEach((pill, i) => {
    pill.className = i === currentChapterIdx
      ? "story-pill px-2.5 py-1 rounded-full text-[11px] font-bold bg-cyan-400 text-slate-950 shadow"
      : "story-pill px-2.5 py-1 rounded-full text-[11px] font-bold bg-slate-800 text-slate-400 hover:text-white";
  });

  // 2. Update Text Narrative & Bilingual Bulletin
  document.getElementById("story-title").textContent = currentLang === "es" ? ch.title_es : ch.title_en;
  document.getElementById("story-coords").textContent = ch.coords_label;
  document.getElementById("story-narrative").textContent = currentLang === "es" ? ch.narrative_es : ch.narrative_en;
  document.getElementById("story-radar-badge").textContent = ch.radar_badge;

  // 3. Synchronize Top Domain Selector, Radar Physics SVG & GEE Metrics
  ["landslide", "flood", "earthquake", "biomass"].forEach(d => {
    const btn = document.getElementById(`btn-${d}`);
    if (btn) {
      btn.className = d === ch.domain
        ? "px-3 py-1 rounded bg-cyan-600 text-white font-semibold"
        : "px-3 py-1 rounded text-slate-400 hover:text-white";
    }
  });

  const report = hazardReportsStore[ch.domain];
  if (report) {
    document.getElementById("insp-domain").textContent = `${ch.domain.toUpperCase()} (NISAR L2)`;
    document.getElementById("insp-alert").textContent = report.alert_level;
    document.getElementById("insp-driver").textContent = report.physical_radar_driver;
    document.getElementById("insp-metrics").textContent = JSON.stringify(report.key_quantitative_metrics, null, 2);
    renderPhysicsDiagram(ch.domain);

    const activeTileUrl = (diagnosticRgbMode && report.diagnostic_rgb_tile_url)
      ? report.diagnostic_rgb_tile_url
      : report.gee_xyz_tile_url;
    if (activeTileUrl) {
      setTileLayer(mapNisar, "nisar-active-raster", activeTileUrl);
    }
  }

  // 4. Choreograph 3-Panel Curtain Sweep & 3D Camera Flight
  animateCurtainsTo(ch.curtains.split1, ch.curtains.split2, 1100);
  mapNisar.flyTo(ch.camera);

  // 5. Update Deck.gl 3D Columns + Cascading Synthesis Arcs
  updateDeckTourLayers(ch.show_cascading_arcs, ch.domain);
}

function nextStoryChapter() {
  goToStoryChapter(currentChapterIdx + 1);
  if (autoPlayTimer) restartChapterTimer();
}

function prevStoryChapter() {
  goToStoryChapter(currentChapterIdx - 1);
  if (autoPlayTimer) restartChapterTimer();
}

function restartChapterTimer() {
  clearTimeout(autoPlayTimer);
  clearInterval(progressInterval);
  const duration = STORY_CHAPTERS[currentChapterIdx].duration_ms;
  const start = performance.now();
  const bar = document.getElementById("story-progress-bar");

  progressInterval = setInterval(() => {
    const pct = Math.min(100, ((performance.now() - start) / duration) * 100);
    bar.style.width = `${pct}%`;
  }, 80);

  autoPlayTimer = setTimeout(() => {
    goToStoryChapter(currentChapterIdx + 1);
    restartChapterTimer();
  }, duration);
}

function toggleAutoPlayTour() {
  const icon = document.getElementById("autoplay-icon");
  const label = document.getElementById("autoplay-label");
  const bar = document.getElementById("story-progress-bar");

  if (autoPlayTimer) {
    clearTimeout(autoPlayTimer);
    clearInterval(progressInterval);
    autoPlayTimer = null;
    bar.style.width = "0%";
    icon.textContent = "▶";
    label.textContent = "Auto-Tour (3:00 Pitch)";
  } else {
    icon.textContent = "⏸";
    label.textContent = "Pause Tour";
    goToStoryChapter(currentChapterIdx);
    restartChapterTimer();
  }
}

// Keyboard Shortcuts for Seamless Hands-Free Live Pitching
window.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
  if (e.code === "ArrowRight") nextStoryChapter();
  if (e.code === "ArrowLeft") prevStoryChapter();
  if (e.code === "Space") {
    e.preventDefault();
    toggleAutoPlayTour();
  }
  if (["Digit1", "Digit2", "Digit3", "Digit4", "Digit5"].includes(e.code)) {
    const idx = parseInt(e.code.replace("Digit", ""), 10) - 1;
    goToStoryChapter(idx);
  }
  // Press 'D' to toggle between Primary Hazard Alert Tile and 3-Band Radar Physics Diagnostic RGB Tile
  if (e.code === "KeyD") {
    diagnosticRgbMode = !diagnosticRgbMode;
    goToStoryChapter(currentChapterIdx);
  }
});
